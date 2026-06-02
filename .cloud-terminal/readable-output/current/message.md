# Bad Gateway / nginx chat-start crash investigated

## Result

The task is marked `ready-for-test` in `project_tasks/master.json`.

## Root cause

The Bad Gateway/nginx symptom matches the WebUI `/api/chat/start` request wedging in the `resolve_model_provider` stage. That path could synchronously rebuild the model catalog (`get_available_models()`), which may perform slow network probes for provider model lists or credential refreshes. Behind a default ~60s reverse proxy, the browser sees `502 Bad Gateway` even though the backend may eventually continue the run, creating a duplicate-send risk.

## Fix present in the current tree

`api/routes.py` now short-circuits `_resolve_compatible_session_model_state()` when chat start already carries an explicit `(model, model_provider)` pair and the model is not `@provider:model`-qualified. That avoids the cold catalog rebuild on normal explicit-provider chat starts while preserving the slow path for cases that still need catalog/default-model repair.

I also confirmed recent Laxlyftet sessions store `model_provider: "openai-codex"`, so they use the fixed fast path.

## Verification

- Focused regression tests: `python3 -m pytest tests/test_issue1855_resolve_model_provider_fast_path.py tests/test_issue1855_request_diagnostics.py tests/test_profile_env_isolation.py tests/test_issue803.py -q`
  - Result: `39 passed in 3.98s`
- Project task JSON validation: `python3 -m json.tool project_tasks/master.json >/dev/null`
  - Result: passed
- Live backend smoke on `127.0.0.1:5003`:
  - Created throwaway Laxlyftet session with `model_provider=openai-codex` in `4.8 ms`.
  - `POST /api/chat/start` returned `200` in `41.6 ms` with `effective_model_provider: "openai-codex"`.
  - This validates the HTTP start request no longer approaches a proxy timeout.
  - The throwaway stream was cancelled afterward; `/api/chat/stream/status` reported `active: false` and terminal state `interrupted-by-user`.

## Note

The repository worktree was already broadly dirty with unrelated changes. For this task, the status update was limited to task `7f9e3592-5fb4-4067-b192-00357f349247`; I did not attempt to revert or normalize unrelated files.

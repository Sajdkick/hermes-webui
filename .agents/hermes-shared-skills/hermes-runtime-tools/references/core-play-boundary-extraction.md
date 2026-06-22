# Core Play boundary extraction reference

Use this reference when extracting or refactoring Hermes WebUI Play lifecycle code behind a core/runtime API boundary.

## Session lesson

When the user asks to create shared/core Play capabilities from Hermes WebUI, Cloud Terminal can be legacy/reference-only. Do not assume Cloud Terminal must consume the new core. The useful first slice is an in-process Hermes boundary that preserves behavior while changing caller ownership.

## Proven first-slice shape

1. Add an in-process facade such as `api/core_play.py`.
2. Keep the existing implementation module, such as `api/play_pipeline.py`, intact for the first slice.
3. Make the facade delegate at call time to the existing implementation so monkeypatch-based tests and current process/proxy/log semantics remain valid.
4. Route all Ops callers through the facade, not only HTTP routes. In the proven slice this included:
   - `api/routes_ops_play.py`
   - `api/ops_runs.py`
   - `api/ops_runtime_tools.py`
   - `api/ops_notifications.py`
5. Preserve HTTP route shapes and response envelopes. Do not rename routes as part of the seam.
6. Preserve the implementation error class identity or expose an alias so `except` behavior and `status` handling remain unchanged.
7. Document the boundary in `docs/core-play-contract.md` and link it from `docs/CONTRACTS.md`.
8. Add boundary tests that prove routes call the facade, the facade delegates to the implementation, stop fallback behavior is unchanged, and proxy routing goes through the boundary.

## Contract functions used in the first slice

- `get_project_play_config_file_info(project_id)`
- `get_project_play_config(project_id)`
- `get_project_play_status(project_id)`
- `get_project_play_logs(project_id, limit)`
- `start_project_play(project_id, body=None)`
- `restart_project_play(project_id, body=None)`
- `stop_project_play(project_id, purge=False)`
- `handle_play_proxy_request(handler, project_id, target_path, parsed, method="GET")`
- `register_build_failure_repair_handler(handler)`

## Verification gate

Run at minimum:

```bash
python3 -m py_compile api/core_play.py api/routes_ops_play.py api/ops_runs.py api/ops_runtime_tools.py api/ops_notifications.py tests/test_core_play_boundary.py
pytest -q tests/test_core_play_boundary.py tests/test_ops_play_pipeline_handoff.py tests/test_upstream_restart_phase7_play.py tests/test_runtime_adapter_seam.py tests/test_upstream_restart_phase6_notifications.py
git diff --check -- <touched tracked files>
```

If an optional test filename from a prior session is stale or missing, locate the current equivalent rather than encoding the missing filename as a durable limitation.

## Pitfalls

- Do not move implementation and introduce the boundary in the same first slice unless explicitly requested; that makes behavior preservation harder to prove.
- Do not route only HTTP endpoints. Ops run handoff, runtime summaries, and notification polling can also import Play lifecycle functions.
- Do not force Cloud Terminal adoption when the user has scoped it as legacy/reference-only.
- Do not capture unrelated pre-existing working tree changes as part of the core boundary change.
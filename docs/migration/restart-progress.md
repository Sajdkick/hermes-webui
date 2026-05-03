# Upstream Restart Progress

Last updated: 2026-05-03

## Phase status

- Phase 0: Complete
- Phase 1: Complete
- Phase 2: Complete
- Phase 3: Complete
- Phase 4: Complete
- Phase 5: Complete
- Phase 6: Complete
- Phase 7: Complete
- Phase 8: Complete
- Phase 9 and later: Not started

## Phase 0 deliverables

- [x] Create clean restart branch `upstream-restart/20260503-phase0` from `upstream/master`
- [x] Add `docs/migration/upstream-restart-execution-plan.md`
- [x] Add this progress tracker
- [x] Add a hotspot guardrail script at `upstream_restart_guardrails.py`
- [x] Run focused upstream baseline verification
- [x] Run a merge rehearsal from this clean branch and record the result

## Current branch snapshot

- Branch: `upstream-restart/20260503-phase0`
- Base ref: `upstream/master`
- Base commit: `9e31a2ac65c3fa7c26a733e213a308aa4a04f992`
- Current slice: Phase 8 project defaults and git sync visibility
- Current guardrail result: `ready`
- Current hotspot churn: `4` committed hotspot files, `0` working-tree hotspot files
- Current hotspot detail: `api/routes.py` `+12 / -0` (`12` lines, within budget); `static/boot.js` `+4 / -1` (`5` lines, within budget); `static/index.html` `+3 / -0` (`3` lines, within budget); `static/messages.js` `+1 / -0` (`1` line, within budget)

## Minimal upstream-owned edits in Phase 0

- `.gitignore`
  Added the smallest possible exception so `docs/migration/upstream-restart-execution-plan.md` and `docs/migration/restart-progress.md` can be tracked. The upstream repo ignores `docs/*` by default, so Phase 0 documentation could not be committed without this exception.

## Guardrail usage

Run:

```bash
python upstream_restart_guardrails.py
python upstream_restart_guardrails.py --json
python upstream_restart_guardrails.py --fail-on warning
```

The script reports:

- committed hotspot churn against the merge-base with the preferred upstream ref,
- working-tree hotspot churn,
- whether the restart budget is still `ready`, `warning`, or `blocked`.

## Verification

- `python -m pytest tests/test_upstream_restart_guardrails.py tests/test_extension_hooks.py`
- `python -m py_compile upstream_restart_guardrails.py`
- `python upstream_restart_guardrails.py`
- `git diff --check`

Result:

- `10` tests passed
- guardrail script returned `ready`
- no whitespace or patch-format issues were reported

## Merge rehearsal

- Rehearsal worktree: `/tmp/hermes-webui-upstream-restart-rehearse`
- Rehearsal branch: `tmp/rehearse-upstream-restart-phase0`
- Snapshot commit: `24a2517`
- Command: `git merge --no-edit upstream/master`
- Result: `Already up to date.`
- Conflict files: `0`
- Conflict count: `0`
- Mechanical resolution required: no
- Hotspot files touched by Phase 0 during rehearsal: `0`

## Phase 1 deliverables

- [x] Add a backend fork route registration hook for `/ops` and `/api/ops/*`
- [x] Add a fork-owned shell route module in `api/routes_ops_shell.py`
- [x] Add a fork-owned HTML shell page in `static/ops-shell.html`
- [x] Add a fork-owned frontend entrypoint in `static/cloud-terminal-entry.js`
- [x] Add a fork-owned stylesheet in `static/cloud-terminal.css`
- [x] Add smoke tests for route and asset presence
- [x] Keep Hermes core-file changes small and mechanical
- [x] Run a merge rehearsal for the Phase 1 snapshot

## Phase 1 verification

- `python -m pytest tests/test_upstream_restart_guardrails.py tests/test_upstream_restart_phase1_shell.py tests/test_extension_hooks.py tests/test_session_static_assets.py`
- `python -m py_compile upstream_restart_guardrails.py api/routes_ops_shell.py`
- `python upstream_restart_guardrails.py`
- `git diff --check`

Result:

- `18` tests passed
- guardrail script stayed `ready`
- the only hotspot churn was `api/routes.py` with `6` added lines
- no whitespace or patch-format issues were reported

## Phase 1 merge rehearsal

- Rehearsal worktree: `/tmp/hermes-webui-upstream-restart-rehearse-phase1`
- Rehearsal branch: `tmp/rehearse-upstream-restart-phase1`
- Snapshot commit: `2f0de32`
- Command: `git merge --no-edit upstream/master`
- Result: `Already up to date.`
- Conflict files: `0`
- Conflict count: `0`
- Mechanical resolution required: no
- Hotspot files touched during rehearsal: `api/routes.py` only
- Hotspot budget result during rehearsal: within budget

## Minimal upstream-owned edits in Phase 1

- `api/routes.py`
  Added a `6`-line dispatcher hook that forwards `/ops` and `/api/ops/*` requests into the fork-owned shell route module.

## Phase 2 deliverables

- [x] Add a fork-owned project registry in `api/ops_projects.py`
- [x] Read and write the shared Cloud Terminal `projects.json` registry instead of inventing a separate store
- [x] Use branch-scoped `project_tasks/<branch>.json` files and copy legacy `project_tasks.json` when bootstrapping
- [x] Keep project/task routes in fork-owned modules (`api/routes_ops.py`, `api/routes_ops_projects.py`)
- [x] Keep the `/ops` UI in fork-owned frontend files (`static/ops-projects.js`, `static/cloud-terminal-entry.js`, `static/cloud-terminal.css`, `static/ops-shell.html`)
- [x] Add project creation, epic creation, task creation, and task update round-trips without session coupling
- [x] Add quick-task, filter, and label-chip UI behavior without starting Hermes sessions
- [x] Run focused verification and a merge rehearsal for the Phase 2 snapshot

## Phase 2 verification

- `python -m pytest tests/test_upstream_restart_guardrails.py tests/test_upstream_restart_phase1_shell.py tests/test_upstream_restart_phase2_projects.py tests/test_upstream_restart_phase2_ui.py tests/test_extension_hooks.py tests/test_session_static_assets.py`
- `python -m py_compile upstream_restart_guardrails.py api/routes_ops_shell.py api/routes_ops.py api/routes_ops_projects.py api/ops_projects.py`
- `python upstream_restart_guardrails.py`
- `git diff --check`

Result:

- `21` tests passed
- guardrail script stayed `ready`
- the only hotspot churn remained `api/routes.py`, now `12` added lines total across GET and POST dispatch hooks
- no whitespace or patch-format issues were reported

## Phase 2 merge rehearsal

- Rehearsal worktree: `/tmp/hermes-webui-upstream-restart-rehearse-phase2`
- Rehearsal branch: `tmp/rehearse-upstream-restart-phase2`
- Snapshot commit: `a148040`
- Command: `git merge --no-edit upstream/master`
- Result: `Already up to date.`
- Conflict files: `0`
- Conflict count: `0`
- Mechanical resolution required: no
- Hotspot files touched during rehearsal: `api/routes.py` only
- Hotspot budget result during rehearsal: within budget

## Minimal upstream-owned edits in Phase 2

- `api/routes.py`
  Expanded the fork dispatcher hook to cover both GET and POST `/api/ops/*` requests. Total hotspot churn stayed at `12` added lines, still under the preferred budget.

## Phase 3 deliverables

- [x] Add fork-owned session linkage sidecars in `api/session_sidecars.py`
- [x] Keep fork linkage metadata out of Hermes session JSON
- [x] Enrich project task payloads with `linkedSessions` state from sidecars
- [x] Add a minimal linked-session indicator in the fork-owned `/ops` UI
- [x] Fail closed when a linkage sidecar is missing or corrupt
- [x] Run focused verification and a merge rehearsal for the Phase 3 snapshot

## Phase 3 verification

- `python -m pytest tests/test_upstream_restart_guardrails.py tests/test_upstream_restart_phase1_shell.py tests/test_upstream_restart_phase2_projects.py tests/test_upstream_restart_phase2_ui.py tests/test_upstream_restart_phase3_sidecars.py tests/test_extension_hooks.py tests/test_session_static_assets.py`
- `python -m py_compile upstream_restart_guardrails.py api/routes_ops_shell.py api/routes_ops.py api/routes_ops_projects.py api/ops_projects.py api/session_sidecars.py`
- `python upstream_restart_guardrails.py`
- `git diff --check`

Result:

- `24` tests passed
- guardrail script stayed `ready`
- the only hotspot churn remained `api/routes.py` at `+12 / -0`
- corrupt sidecars now fail closed instead of breaking task reads
- no whitespace or patch-format issues were reported

## Phase 3 merge rehearsal

- Rehearsal worktree: `/tmp/hermes-webui-upstream-restart-rehearse-phase3`
- Rehearsal branch: `tmp/rehearse-upstream-restart-phase3`
- Snapshot commit: `13ed482`
- Command: `git merge --no-edit upstream/master`
- Result: `Already up to date.`
- Conflict files: `0`
- Conflict count: `0`
- Mechanical resolution required: no
- Hotspot files touched during rehearsal: `api/routes.py` only
- Hotspot budget result during rehearsal: within budget

## Minimal upstream-owned edits in Phase 3

- `api/routes.py`
  No additional hotspot churn was introduced in Phase 3. The existing GET and POST `/api/ops/*` dispatcher hook remained the only upstream-owned edit.

## Phase 4 deliverables

- [x] Add fork-owned task session launch helpers in `api/ops_sessions.py`
- [x] Add a task session launch route under `api/routes_ops_projects.py`
- [x] Reuse the Phase 3 sidecar layer to persist task-to-session linkage on launch
- [x] Surface launch and resume controls in the fork-owned `/ops` UI
- [x] Keep deliberate zero-message task sessions active through a narrow boot hook instead of injecting fake starter messages
- [x] Run focused verification and a merge rehearsal for the Phase 4 snapshot

## Phase 4 verification

- `python -m pytest tests/test_upstream_restart_guardrails.py tests/test_upstream_restart_phase1_shell.py tests/test_upstream_restart_phase2_projects.py tests/test_upstream_restart_phase2_ui.py tests/test_upstream_restart_phase3_sidecars.py tests/test_upstream_restart_phase4_sessions.py tests/test_extension_hooks.py tests/test_session_static_assets.py`
- `python -m py_compile upstream_restart_guardrails.py api/routes_ops_shell.py api/routes_ops.py api/routes_ops_projects.py api/ops_projects.py api/ops_sessions.py api/session_sidecars.py`
- `python upstream_restart_guardrails.py`
- `git diff --check`

Result:

- `27` tests passed
- guardrail script stayed `ready`
- hotspot churn remained within budget, with only `api/routes.py` and a five-line `static/boot.js` hook touched
- the `/ops` UI now renders task launch and resume affordances backed by real session URLs
- no whitespace or patch-format issues were reported

## Phase 4 merge rehearsal

- Rehearsal worktree: `/tmp/hermes-webui-upstream-restart-rehearse-phase4`
- Rehearsal branch: `tmp/rehearse-upstream-restart-phase4`
- Snapshot commit: `48a4648`
- Command: `git merge --no-edit upstream/master`
- Result: `Already up to date.`
- Conflict files: `0`
- Conflict count: `0`
- Mechanical resolution required: no
- Hotspot files touched during rehearsal: `api/routes.py`, `static/boot.js`
- Hotspot budget result during rehearsal: within budget

## Minimal upstream-owned edits in Phase 4

- `static/boot.js`
  Added a five-line `_keepEmptySessionActive()` hook so deliberate `ops_task` sessions with zero messages stay active on restore instead of being collapsed back to the empty state.
- `api/routes.py`
  No additional Phase 4 churn was added. The existing `/api/ops/*` dispatcher hook remained unchanged.

## Phase 5 deliverables

- [x] Add fork-owned session readable-output lookup helpers in `api/session_readable_output.py`
- [x] Add fork-owned session readable-output routes in `api/routes_ops_sessions.py`
- [x] Mount a fork-owned readable-output host, stylesheet, and script on the main Hermes page
- [x] Reuse existing session lifecycle globals via wrappers instead of reshaping `sessions.js`
- [x] Add one narrow `messages.js` completion hook so the active session refreshes readable output after a completed turn
- [x] Run focused verification and a merge rehearsal for the Phase 5 snapshot

## Phase 5 verification

- `python -m pytest tests/test_upstream_restart_guardrails.py tests/test_upstream_restart_phase1_shell.py tests/test_upstream_restart_phase2_projects.py tests/test_upstream_restart_phase2_ui.py tests/test_upstream_restart_phase3_sidecars.py tests/test_upstream_restart_phase4_sessions.py tests/test_upstream_restart_phase5_readable_output.py tests/test_extension_hooks.py tests/test_session_static_assets.py`
- `python -m py_compile upstream_restart_guardrails.py api/routes_ops_shell.py api/routes_ops.py api/routes_ops_projects.py api/routes_ops_sessions.py api/ops_projects.py api/ops_sessions.py api/session_sidecars.py api/session_readable_output.py`
- `python upstream_restart_guardrails.py`
- `git diff --check`

Result:

- `30` tests passed
- guardrail script stayed `ready`
- hotspot churn remained within budget, with only `api/routes.py`, `static/boot.js`, `static/index.html`, and `static/messages.js` touched in upstream-owned files
- the main Hermes chat view now loads and refreshes session-scoped readable output from fork-owned routes
- no whitespace or patch-format issues were reported

## Phase 5 merge rehearsal

- Rehearsal worktree: `/tmp/hermes-webui-upstream-restart-rehearse-phase5`
- Rehearsal branch: `tmp/rehearse-upstream-restart-phase5`
- Snapshot commit: `a0b3b0a`
- Command: `git merge --no-edit upstream/master`
- Result: `Already up to date.`
- Conflict files: `0`
- Conflict count: `0`
- Mechanical resolution required: no
- Hotspot files touched during rehearsal: `api/routes.py`, `static/boot.js`, `static/index.html`, `static/messages.js`
- Hotspot budget result during rehearsal: within budget

## Minimal upstream-owned edits in Phase 5

- `static/index.html`
  Added one host mount plus one stylesheet and one script include so the readable-output UI can stay fork-owned.
- `static/messages.js`
  Added a single completion hook that refreshes the active session’s readable output after a successful turn.
- `api/routes.py`
  No additional Phase 5 churn was added. The existing `/api/ops/*` dispatcher hook remained unchanged.

## Phase 6 deliverables

- [x] Add fork-owned workflow notification helpers in `api/ops_notifications.py`
- [x] Add fork-owned workflow notification routes in `api/routes_ops_notifications.py`
- [x] Reuse upstream approval and clarify runtime state instead of forking their queue semantics
- [x] Mount a fork-owned workflow inbox in the `/ops` shell UI with approval and clarify response controls
- [x] Keep upstream streaming ownership unchanged while still updating upstream SSE heads after `/ops` responses
- [x] Run focused verification and a merge rehearsal for the Phase 6 snapshot

## Phase 6 verification

- `python -m pytest tests/test_upstream_restart_guardrails.py tests/test_upstream_restart_phase1_shell.py tests/test_upstream_restart_phase2_projects.py tests/test_upstream_restart_phase2_ui.py tests/test_upstream_restart_phase3_sidecars.py tests/test_upstream_restart_phase4_sessions.py tests/test_upstream_restart_phase5_readable_output.py tests/test_upstream_restart_phase6_notifications.py tests/test_extension_hooks.py tests/test_session_static_assets.py`
- `python -m py_compile upstream_restart_guardrails.py api/routes_ops_shell.py api/routes_ops.py api/routes_ops_projects.py api/routes_ops_sessions.py api/routes_ops_notifications.py api/ops_projects.py api/ops_sessions.py api/ops_notifications.py api/session_sidecars.py api/session_readable_output.py`
- `python upstream_restart_guardrails.py`
- `git diff --check`

Result:

- `33` tests passed
- guardrail script stayed `ready`
- hotspot churn remained within budget, with only `api/routes.py`, `static/boot.js`, `static/index.html`, and `static/messages.js` touched in upstream-owned files
- the `/ops` UI now renders a fork-owned workflow inbox that can review and answer pending approval and clarify work for task-linked sessions
- no whitespace or patch-format issues were reported

## Phase 6 merge rehearsal

- Rehearsal worktree: `/tmp/hermes-webui-upstream-restart-rehearse-phase6`
- Rehearsal branch: `tmp/rehearse-upstream-restart-phase6`
- Snapshot commit: `38bb0de`
- Command: `git merge --no-edit upstream/master`
- Result: `Already up to date.`
- Conflict files: `0`
- Conflict count: `0`
- Mechanical resolution required: no
- Hotspot files touched during rehearsal: `api/routes.py`, `static/boot.js`, `static/index.html`, `static/messages.js`
- Hotspot budget result during rehearsal: within budget

## Minimal upstream-owned edits in Phase 6

- `api/routes.py`
  No additional Phase 6 churn was added. The existing `/api/ops/*` dispatcher hook remained unchanged.
- `static/boot.js`
  No additional Phase 6 churn was added. The existing five-line empty-session keepalive hook remained unchanged.
- `static/index.html`
  No additional Phase 6 churn was added. The existing readable-output host mount remained unchanged.
- `static/messages.js`
  No additional Phase 6 churn was added. The existing readable-output refresh hook remained unchanged.

## Phase 7 runtime-guides checkpoint deliverables

- [x] Add fork-owned runtime gather/report storage in `api/ops_guides.py`
- [x] Add fork-owned runtime summary helpers in `api/ops_runtime_tools.py`
- [x] Add fork-owned runtime evidence routes in `api/routes_ops_runtime.py`
- [x] Mount a lightweight fork-owned runtime evidence panel in `static/ops-runtime.js`
- [x] Wire the selected-project `/ops` UI to the new runtime summary endpoint without editing upstream-owned files
- [x] Run focused verification and a merge rehearsal for this checkpoint

## Phase 7 runtime-guides checkpoint verification

- `python -m pytest tests/test_upstream_restart_guardrails.py tests/test_upstream_restart_phase1_shell.py tests/test_upstream_restart_phase2_projects.py tests/test_upstream_restart_phase2_ui.py tests/test_upstream_restart_phase3_sidecars.py tests/test_upstream_restart_phase4_sessions.py tests/test_upstream_restart_phase5_readable_output.py tests/test_upstream_restart_phase6_notifications.py tests/test_upstream_restart_phase7_runtime_guides.py tests/test_extension_hooks.py tests/test_session_static_assets.py`
- `python -m py_compile upstream_restart_guardrails.py api/routes_ops_shell.py api/routes_ops.py api/routes_ops_projects.py api/routes_ops_sessions.py api/routes_ops_notifications.py api/routes_ops_runtime.py api/ops_projects.py api/ops_sessions.py api/ops_notifications.py api/ops_guides.py api/ops_runtime_tools.py api/session_sidecars.py api/session_readable_output.py`
- `python upstream_restart_guardrails.py`
- `git diff --check`

Result:

- `36` tests passed
- guardrail script stayed `ready`
- Phase 7 checkpoint work stayed entirely in fork-owned files; hotspot churn remained the same four committed files from earlier completed slices
- the `/ops` UI now shows recent runtime gather reports and review requests for the selected project from fork-owned storage and routes
- no whitespace or patch-format issues were reported

## Phase 7 runtime-guides checkpoint merge rehearsal

- Rehearsal worktree: `/tmp/hermes-webui-upstream-restart-rehearse-phase7-runtime-guides`
- Rehearsal branch: `tmp/rehearse-upstream-restart-phase7-runtime-guides`
- Snapshot commit: `43a36de`
- Command: `git merge --no-edit upstream/master`
- Result: `Already up to date.`
- Conflict files: `0`
- Conflict count: `0`
- Mechanical resolution required: no
- Hotspot files touched during rehearsal: `api/routes.py`, `static/boot.js`, `static/index.html`, `static/messages.js` only
- Hotspot budget result during rehearsal: within budget

## Minimal upstream-owned edits in Phase 7 runtime-guides checkpoint

- None.
  This checkpoint kept all new runtime evidence logic in fork-owned backend and frontend modules. No new upstream-owned files were touched beyond the hotspot surface already established in earlier completed slices.

## Phase 7 Play checkpoint deliverables

- [x] Add a fork-owned Play pipeline backend in `api/play_pipeline.py`
- [x] Add fork-owned Play config, status, log, start, stop, restart, and proxy routes in `api/routes_ops_play.py`
- [x] Add a fork-owned proxied Play compatibility bridge in `static/play-proxy-compat.js`
- [x] Surface Play workflow controls in the fork-owned `/ops` runtime panel through `static/ops-runtime.js`, `static/ops-projects.js`, and `static/cloud-terminal.css`
- [x] Keep new Play workflow logic out of Hermes session internals and limit upstream-owned edits to the narrow top-level dispatcher hook
- [x] Run focused verification and a merge rehearsal for this checkpoint

## Phase 7 Play checkpoint verification

- `python -m pytest tests/test_upstream_restart_guardrails.py tests/test_upstream_restart_phase1_shell.py tests/test_upstream_restart_phase2_projects.py tests/test_upstream_restart_phase2_ui.py tests/test_upstream_restart_phase3_sidecars.py tests/test_upstream_restart_phase4_sessions.py tests/test_upstream_restart_phase5_readable_output.py tests/test_upstream_restart_phase6_notifications.py tests/test_upstream_restart_phase7_runtime_guides.py tests/test_upstream_restart_phase7_play.py tests/test_extension_hooks.py tests/test_session_static_assets.py`
- `python -m py_compile upstream_restart_guardrails.py api/routes_ops_shell.py api/routes_ops.py api/routes_ops_projects.py api/routes_ops_sessions.py api/routes_ops_notifications.py api/routes_ops_runtime.py api/routes_ops_play.py api/play_pipeline.py api/ops_projects.py api/ops_sessions.py api/ops_notifications.py api/ops_guides.py api/ops_runtime_tools.py api/session_sidecars.py api/session_readable_output.py`
- `python upstream_restart_guardrails.py`
- `git diff --check`

Result:

- `40` tests passed
- guardrail script stayed `ready`
- the `/ops` runtime panel now exposes Play config, status, logs, start, stop, restart, and proxy launch flows through fork-owned modules
- hotspot churn stayed within budget: the committed hotspot surface did not expand, and the current worktree no longer carries any uncommitted hotspot changes
- no whitespace or patch-format issues were reported

## Phase 7 Play checkpoint merge rehearsal

- Rehearsal worktree: `/tmp/hermes-webui-upstream-restart-rehearse-phase7-play`
- Rehearsal branch: `tmp/rehearse-upstream-restart-phase7-play`
- Snapshot commit: `aa4e131`
- Command: `git merge --no-edit upstream/master`
- Result: `Already up to date.`
- Conflict files: `0`
- Conflict count: `0`
- Mechanical resolution required: no
- Hotspot files touched during rehearsal: `api/routes.py`, `static/boot.js`, `static/index.html`, `static/messages.js` only
- Hotspot budget result during rehearsal: within budget

## Minimal upstream-owned edits in Phase 7 Play checkpoint

- `api/routes.py`
  Expanded the top-level fork dispatcher by four lines so `/play-project/*` GET and POST requests flow into the fork-owned Play route module without coupling the Play workflow to Hermes core modules.

## Phase 7 runtime inspect checkpoint deliverables

- [x] Add a fork-owned `ct-runtime` wrapper in `api/ops_runtime_inspect.py`
- [x] Extend `api/routes_ops_runtime.py` with snapshot, screenshot, and action run/latest endpoints
- [x] Surface the latest snapshot, screenshot, and action records in `api/ops_runtime_tools.py`
- [x] Add an inspect toolkit panel to the fork-owned `/ops` runtime UI through `static/ops-runtime.js`, `static/ops-projects.js`, and `static/cloud-terminal.css`
- [x] Keep the runtime inspect slice entirely in fork-owned modules without expanding the upstream-owned hotspot surface
- [x] Run focused verification and a merge rehearsal for this checkpoint

## Phase 7 runtime inspect checkpoint verification

- `python -m pytest tests/test_upstream_restart_guardrails.py tests/test_upstream_restart_phase1_shell.py tests/test_upstream_restart_phase2_projects.py tests/test_upstream_restart_phase2_ui.py tests/test_upstream_restart_phase3_sidecars.py tests/test_upstream_restart_phase4_sessions.py tests/test_upstream_restart_phase5_readable_output.py tests/test_upstream_restart_phase6_notifications.py tests/test_upstream_restart_phase7_runtime_guides.py tests/test_upstream_restart_phase7_play.py tests/test_upstream_restart_phase7_runtime_inspect.py tests/test_extension_hooks.py tests/test_session_static_assets.py`
- `python -m py_compile upstream_restart_guardrails.py api/ops_runtime_inspect.py api/ops_runtime_tools.py api/routes_ops_runtime.py api/play_pipeline.py api/routes_ops_play.py api/routes_ops_shell.py api/routes_ops.py api/routes_ops_projects.py api/routes_ops_sessions.py api/routes_ops_notifications.py api/ops_projects.py api/ops_sessions.py api/ops_notifications.py api/ops_guides.py api/session_sidecars.py api/session_readable_output.py`
- `python upstream_restart_guardrails.py`
- `git diff --check`

Result:

- `42` tests passed
- guardrail script stayed `ready`
- Phase 7 is now complete: runtime gather/review, Play workflow, and runtime inspect tools all live behind fork-owned backend and frontend modules
- hotspot churn stayed within budget and unchanged from the earlier committed surface: `api/routes.py` `+12 / -0`, `static/boot.js` `+4 / -1`, `static/index.html` `+3 / -0`, `static/messages.js` `+1 / -0`
- no whitespace or patch-format issues were reported

## Phase 7 runtime inspect checkpoint merge rehearsal

- Rehearsal worktree: `/tmp/hermes-webui-upstream-restart-rehearse-phase7-inspect`
- Rehearsal branch: `tmp/rehearse-upstream-restart-phase7-inspect`
- Snapshot commit: `c6812c4`
- Command: `git merge --no-edit upstream/master`
- Result: `Already up to date.`
- Conflict files: `0`
- Conflict count: `0`
- Mechanical resolution required: no
- Hotspot files touched during rehearsal: `api/routes.py`, `static/boot.js`, `static/index.html`, `static/messages.js` only
- Hotspot budget result during rehearsal: within budget

## Minimal upstream-owned edits in Phase 7 runtime inspect checkpoint

- None.
  This checkpoint kept runtime inspect execution, persistence, and UI controls in fork-owned modules. No additional upstream-owned files were touched beyond the hotspot surface established in earlier phases.

## Phase 8 deliverables

- [x] Add project-scoped launch defaults in `api/ops_projects.py`, `api/routes_ops_projects.py`, `api/ops_sessions.py`, and `static/ops-projects.js`
- [x] Validate named launch profiles and resolve profile-local default model/provider values from the target Hermes profile config
- [x] Add a fork-owned project git status helper in `api/ops_git.py` and a matching route bridge in `api/routes_ops_git.py`
- [x] Compare branch drift against the project core branch and ignore fork-owned workflow metadata (`.hermes`, `project_tasks`, `project_tasks.json`) in the git status view
- [x] Surface the new launch defaults and git status controls in the fork-owned `/ops` shell without widening Hermes hotspot churn
- [x] Run focused verification and a merge rehearsal for the Phase 8 snapshot

## Phase 8 verification

- `python -m pytest tests/test_upstream_restart_phase1_shell.py tests/test_upstream_restart_phase2_projects.py tests/test_upstream_restart_phase2_ui.py tests/test_upstream_restart_phase4_sessions.py tests/test_upstream_restart_phase8_project_defaults.py tests/test_upstream_restart_phase8_git_status.py`
- `python -m py_compile api/ops_git.py api/routes_ops_git.py api/routes_ops.py api/routes_ops_shell.py api/ops_projects.py api/ops_sessions.py`
- `python upstream_restart_guardrails.py`
- `git diff --check`

Result:

- `13` tests passed
- guardrail script stayed `ready`
- project launch sessions now inherit either explicit project defaults or the selected profile's own model/provider defaults without mutating Hermes profile hotspots
- the `/ops` detail panel now shows core-branch drift and working-tree health through fork-owned modules while ignoring fork-owned workflow metadata
- hotspot churn stayed unchanged from earlier phases: `api/routes.py` `+12 / -0`, `static/boot.js` `+4 / -1`, `static/index.html` `+3 / -0`, `static/messages.js` `+1 / -0`
- no whitespace or patch-format issues were reported

## Phase 8 merge rehearsal

- Rehearsal worktree: `/tmp/hermes-webui-upstream-restart-rehearse-phase8.6yuGH3`
- Rehearsal branch: `tmp/rehearse-upstream-restart-phase8`
- Snapshot commit: `9425eb4`
- Command: `git merge --no-edit upstream/master`
- Result: `Already up to date.`
- Conflict files: `0`
- Conflict count: `0`
- Mechanical resolution required: no
- Hotspot files touched during rehearsal: `api/routes.py`, `static/boot.js`, `static/index.html`, `static/messages.js` only
- Hotspot budget result during rehearsal: within budget

## Minimal upstream-owned edits in Phase 8

- None.
  Phase 8 kept launch-default persistence, profile resolution, project git status, and `/ops` UI status rendering in fork-owned modules. No additional upstream-owned files were touched beyond the hotspot surface established in earlier phases.

## Phase 9 deliverables

- [x] Compare the old fork feature catalog in `docs/migration/hermes-cloud-terminal-user-guide.md` and `docs/migration/hermes-ops-module-boundary-guide.md` against the clean restart branch inventory
- [x] Map each legacy workflow surface to `ported`, `reused upstream`, `deferred`, or `dropped`
- [x] Build a completion checklist that maps the execution plan's explicit requirements to concrete branch artifacts, tests, guardrails, and merge evidence
- [ ] Run the final restart verification suite and supporting evidence checks
- [ ] Run the final merge rehearsal for the Phase 9 snapshot
- [ ] Decide whether the execution plan is actually complete

## Phase 9 parity audit

| Legacy surface | Legacy evidence | Clean restart evidence | Decision |
| --- | --- | --- | --- |
| `/ops` shell plus project/task CRUD | `docs/migration/hermes-cloud-terminal-user-guide.md` daily workflow; legacy `api/ops_projects.py`, `static/ops-projects.js` | `api/ops_projects.py`, `api/routes_ops_projects.py`, `static/ops-projects.js`, `tests/test_upstream_restart_phase2_projects.py`, `tests/test_upstream_restart_phase2_ui.py` | Ported |
| Task-linked execution sessions and task resume | legacy user guide “Quick task runner” / project detail workflow; legacy `api/ops_sessions.py` | `api/ops_sessions.py`, `api/session_sidecars.py`, `tests/test_upstream_restart_phase3_sidecars.py`, `tests/test_upstream_restart_phase4_sessions.py` | Ported as explicit task launch and resume from project detail |
| Readable output for active work | legacy user guide “Runs, Requests, And Readable Output”; legacy `api/ops_artifacts.py`, `api/routes_ops_runs.py` | `api/session_readable_output.py`, `api/routes_ops_sessions.py`, `static/readable-output-ui.js`, `static/readable-output-ui.css`, `tests/test_upstream_restart_phase5_readable_output.py` | Ported for task-linked Hermes sessions |
| User-facing approval and clarify workflow | legacy runs/request UI and notification docs | `api/ops_notifications.py`, `api/routes_ops_notifications.py`, `static/ops-notifications.js`, `tests/test_upstream_restart_phase6_notifications.py` | Ported |
| Runtime gather/review, Play, and inspect | legacy user guide “Runtime And Play”; legacy `api/ops_guides.py`, `api/ops_runtime_tools.py`, `api/play_pipeline.py`, `static/ops-play.js`, `static/play-inspect-shell.js` | `api/ops_guides.py`, `api/ops_runtime_tools.py`, `api/ops_runtime_inspect.py`, `api/play_pipeline.py`, `api/routes_ops_runtime.py`, `api/routes_ops_play.py`, `static/ops-runtime.js`, `static/play-proxy-compat.js`, `tests/test_upstream_restart_phase7_runtime_guides.py`, `tests/test_upstream_restart_phase7_play.py`, `tests/test_upstream_restart_phase7_runtime_inspect.py` | Ported |
| Profile/model conveniences | legacy agent/profile bridge modules and upstream-sync launcher inputs | Upstream Hermes profile/model APIs reused directly; project-level defaults layered in `api/ops_projects.py`, `api/ops_sessions.py`, `static/ops-projects.js`, `tests/test_upstream_restart_phase8_project_defaults.py` | Reused upstream plus thin fork integration |
| Project git and upstream/core-branch visibility | legacy `api/ops_git.py`, `static/ops-git.js` | `api/ops_git.py`, `api/routes_ops_git.py`, `static/ops-git.js`, `tests/test_upstream_restart_phase8_git_status.py` | Ported as read-only visibility; direct maintenance-session sync flow not reintroduced |
| Durable run registry, run activity, artifact health, and run detail | legacy `api/routes_ops_runs.py`, `static/ops-runs.js`, `docs/migration/hermes-cloud-terminal-user-guide.md` | No `ops_runs` surface exists in the clean branch; current branch instead links tasks directly to Hermes sessions and session readable output | Deferred. Not part of the restart phase plan, and the clean branch does not claim run-system parity |
| Migration health, deployment, database, and GitHub admin panels | legacy guide “Migration health”, “Deployment And Push Scope”; legacy `api/ops_migration.py`, `api/ops_deployments.py`, `api/ops_database.py`, `api/ops_github.py` | No equivalent clean-branch modules or routes were added; these surfaces were not in Phases 0-8 | Deferred. Broader retirement/admin scope, not part of the restart plan |
| Upstream-sync maintenance session and apply flow | legacy `api/routes_upstream_sync.py`, `api/upstream_sync.py`, `static/upstream-sync-ui.js` | No clean-branch maintenance-session sync surface; Phase 8 retained only project git visibility and profile/model conveniences | Dropped for restart scope. Lower value than mergeability and would widen the fork surface beyond the documented phases |

## Phase 9 completion checklist

| Execution-plan requirement | Evidence in the clean restart branch | Status |
| --- | --- | --- |
| Start from latest `upstream/master` | Current branch snapshot at top of this file lists base commit `9e31a2ac65c3fa7c26a733e213a308aa4a04f992`; guardrail output still reports `base=upstream/master` and the same merge-base | Met |
| Re-port features in small vertical slices | Phases 1-8 in this tracker each have scoped deliverables, focused verification, and merge rehearsals | Met |
| Keep product behavior in fork-owned modules | `git diff --name-status upstream/master..HEAD` shows new behavior in fork-owned `api/ops_*.py`, `api/routes_ops_*.py`, `static/ops-*.js`, `static/cloud-terminal.css`, `static/cloud-terminal-entry.js`, `static/readable-output-ui.*`, `static/play-proxy-compat.js` | Met |
| Avoid broad edits to Hermes-owned hotspots | Guardrail output stays `ready`; `git diff --name-only upstream/master..HEAD -- api/models.py api/streaming.py api/config.py api/profiles.py static/ui.js static/sessions.js static/panels.js static/style.css` returns nothing; hotspot churn is still only `api/routes.py`, `static/boot.js`, `static/index.html`, `static/messages.js` within budget | Met |
| Sidecars own fork workflow metadata | `api/session_sidecars.py` stores project/task linkage outside Hermes session JSON; covered by `tests/test_upstream_restart_phase3_sidecars.py` | Met |
| Prefer behavior tests over source-shape tests | All restart coverage is phase behavior coverage in `tests/test_upstream_restart_phase1_shell.py` through `tests/test_upstream_restart_phase8_git_status.py` plus `tests/test_upstream_restart_guardrails.py` | Met |
| Upstream tests remain intact unless explicitly documented | `git diff --name-status upstream/master..HEAD -- tests` shows only added restart tests; `git diff --diff-filter=D --name-only upstream/master..HEAD` returns nothing | Met |
| High-value fork workflows are rebuilt on latest upstream | Ported/reused rows in the Phase 9 parity audit cover project/task CRUD, task-linked sessions, readable output, requests, runtime gather/review, Play, inspect, profile/model defaults, and project git visibility | Met |
| Old branch no longer needed except as historical reference | Remaining legacy-only surfaces are explicitly classified above as `Deferred` or `Dropped`; no plan-scoped workflow remains unmapped | Pending final verification |
| Final merge should be cheap and mostly mechanical | Pending final Phase 9 merge rehearsal | Pending |

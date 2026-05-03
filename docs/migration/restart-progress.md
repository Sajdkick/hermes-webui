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
- Phase 7: Next
- Phase 8 and later: Not started

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
- Current slice: Phase 6 workflow inbox notifications
- Current guardrail result: `ready`
- Current hotspot churn: `0` committed hotspot files, `4` working-tree hotspot files
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

## Next concrete step

Start Phase 7 on this clean branch: port runtime inspect, gather/review, and Play surfaces as fork-owned product features.

# Ops duplicate task sessions fixed

## What changed

- Made Ops task session launch reuse an existing current, non-archived linked Ops task session instead of creating another session for the same task.
- Added active-session de-duplication for Ops task sessions so historic duplicate links for the same project/task collapse to the best current visible session.
- Preserved task/session cleanup behavior so closing/completing a task clears the task’s session linkage fields and archived sessions are not reused.
- Added regression coverage for repeated launch idempotency and historic duplicate active-session rendering.
- Updated `project_tasks/master.json` for the executed task to `qaStatus: "ready-for-test"`.

## Verification

- `python3 -m pytest tests/test_upstream_restart_phase4_sessions.py -k 'launch_task_session_creates_persisted_linked_session or dedupes_historic_duplicate_task_sessions or close_task_session_archives_linked_session_and_stops_run or complete_task_route_marks_task_done_and_run_succeeded'` — passed (`4 passed`).
- `python3 -m pytest tests/test_upstream_restart_phase4_sessions.py` — passed (`11 passed`).
- `git diff --check -- api/ops_sessions.py tests/test_upstream_restart_phase4_sessions.py CHANGELOG.md project_tasks/master.json` — passed.

## Notes

- `docs/VISION.md` was referenced by repo instructions but does not exist in this checkout; I used the available project docs and existing Ops session tests instead.
- The worktree already contains unrelated modified files; I only intentionally touched the Ops session implementation, its targeted test file, the changelog entry, and the active task JSON status.

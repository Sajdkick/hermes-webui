# Active Sessions Fix

## Root cause

- The Ops home panel reads `/api/sessions/activity`, not `/api/ops/sessions`.
- The live Hermes server was correctly returning your task session from `/api/ops/sessions`, but `/api/sessions/activity` filtered it out once the linked run became quiet or `succeeded` and the session no longer had a live stream.
- That made the dashboard show `No active sessions.` even though the task session still existed and was still part of the open task flow.

## What changed

- In [api/session_activity.py](/home/ubuntu/cloud-terminal-data/projects/hermes-webui/api/session_activity.py), task-linked sessions now stay in the Ops activity list while the linked task is still open, even if the current run is quiet or already `succeeded`.
- The same activity payload now keeps `readableOutputPending` true for completed task sessions when readable output exists, which matches the Cloud Terminal activity model instead of hiding unread output on `done` sessions.
- I added a regression in [tests/test_upstream_restart_phase11_activity.py](/home/ubuntu/cloud-terminal-data/projects/hermes-webui/tests/test_upstream_restart_phase11_activity.py) for the exact failing lifecycle: task session, no live stream, terminal run status, still visible in the activity feed.

## Verification

- Live diagnosis before the patch:
  - `http://127.0.0.1:5003/api/ops/sessions` included your Hermes task session.
  - `http://127.0.0.1:5003/api/sessions/activity` returned `sessionCount: 0`.
- Code verification after the patch:
  - `python -m py_compile api/session_activity.py api/ops_sessions.py api/routes_session_activity.py`
  - `python -m pytest tests/test_upstream_restart_phase11_activity.py tests/test_upstream_restart_phase4_sessions.py`
    - Result: `14 passed`
  - `git diff --check`

## Next step

- Restart Hermes once so the running server picks up the patched activity classifier, then reload `/ops`.
- I could not trigger the managed restart from the terminal because the local Cloud Terminal control plane requires the same authenticated session token as the UI recovery page.

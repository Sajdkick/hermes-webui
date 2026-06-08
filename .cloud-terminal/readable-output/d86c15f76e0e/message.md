# Profile-switch bug fixed

## What changed

- Fixed the active-session sidebar fallback in `static/sessions.js` so project-owned empty sessions use `currentSessionProfileForTurn(S.session)` instead of `S.session.profile || S.activeProfile || 'default'`.
- This keeps a project-linked session, such as a `modelkit` session, locked to its project/session profile when the browser's active profile is `default` or another profile.
- Preserved the intended behavior for plain empty placeholder chats: they can still adopt the currently selected profile before the first turn.

## Regression coverage

- Updated `tests/test_profile_session_isolation_frontend.py` to cover a `modelkit`-style project-owned empty session row and verify it keeps the project profile.
- Tightened the frontend profile-payload assertions to match the current session-aware helper calls.

## Verification

- `python3 -m pytest tests/test_profile_switch_1200.py tests/test_profile_session_isolation_frontend.py tests/test_goal_command_webui.py -q` → `32 passed`
- `python3 -m pytest tests/test_profile_env_isolation.py tests/test_ops_sessions_dedupe.py tests/test_issue803.py tests/test_issue1614_project_profile_filtering.py tests/test_issue1955_worktree_sessions.py -q` → `53 passed`

## Notes

- I did not find inspectable `modelkit` session metadata in the searched local Hermes/profile state, so this fixes and verifies the reproducible class of bug rather than editing that specific live session record.
- The repo already had unrelated uncommitted changes in files such as `api/routes.py`, `CHANGELOG.md`, `project_tasks/master.json`, and CSRF tests; I left those unrelated diffs intact.

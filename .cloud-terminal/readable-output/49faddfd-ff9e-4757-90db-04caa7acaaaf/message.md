# Project Push Parity Fix

## What changed

- The Hermes `/ops` project-page push flow now matches Cloud Terminal more closely.
- `Push changes` now auto-commits dirty worktrees instead of failing on uncommitted changes.
- Push now targets the project core branch on `origin`, and if you start from a non-core branch it merges that branch into the core branch before pushing, the same way Cloud Terminal does.
- `.cloud-terminal` runtime artifacts are now excluded from project git status and staging, so the project page no longer treats readable-output/session metadata as repo changes.
- Successful pushes now also promote `not-synced` tasks to `ready-for-test`, matching Cloud Terminal’s post-push task behavior.
- The Ops UI now reloads project state after push and refreshes the current project detail when task promotion happened, so the page reflects the updated task state immediately.
- I also hardened the project helpers to accept serialized project objects that only carry `resolvedPath`, which removed a brittle mismatch between the git helpers and the shared project/task helpers.

## Files

- [api/ops_git.py](/home/ubuntu/cloud-terminal-data/projects/hermes-webui/api/ops_git.py)
- [api/ops_projects.py](/home/ubuntu/cloud-terminal-data/projects/hermes-webui/api/ops_projects.py)
- [static/ops-legacy-git.js](/home/ubuntu/cloud-terminal-data/projects/hermes-webui/static/ops-legacy-git.js)
- [tests/test_upstream_restart_phase8_git_status.py](/home/ubuntu/cloud-terminal-data/projects/hermes-webui/tests/test_upstream_restart_phase8_git_status.py)
- [tests/test_ops_git_push.py](/home/ubuntu/cloud-terminal-data/projects/hermes-webui/tests/test_ops_git_push.py)

## Verification

- `python -m py_compile api/ops_git.py api/ops_projects.py api/routes_ops_git.py`
- `node --check static/ops-legacy-git.js`
- `python -m pytest tests/test_ops_git_push.py tests/test_upstream_restart_phase8_git_status.py`
  - Result: `9 passed`
- `git diff --check`

## Scope

This pass fixed the project-page git/push behavior and the adjacent UI refresh/task-promotion discrepancies around that same flow. I did not claim parity for unrelated parts of `/ops` in this slice.

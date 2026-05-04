# Ops path fix

`/ops` was failing because the ops entry points were still assuming the app lived at domain root. In your current setup, Hermes is being served from an app base path, so the correct ops URL is derived from that base, not always from `/`.

## What changed

- Main-shell `Ops` buttons now resolve through `document.baseURI` instead of hardcoding `ops` against the raw browser location.
- The ops shell now uses the same base-href bootstrap as the main Hermes UI.
- Ops shell assets, bootstrap fetches, and cross-links now resolve relative to the app base.
- I updated the stale shell tests to keep this additive and merge-friendly rather than rewriting the backend route contract.

## What to test

- Reload Hermes and use the `Ops` button from the main UI.
- If your current page URL looks like `https://host/prefix/session/<id>`, the correct manual ops URL is `https://host/prefix/ops`.
- Literal root `/ops` only works when Hermes is mounted at the site root.

## Verification

- `node --check static/panels.js static/cloud-terminal-entry.js static/ops-projects.js static/ops-notifications.js static/ops-runs.js static/ops-upstream-sync.js`
- `python -m pytest tests/test_upstream_restart_phase1_shell.py tests/test_upstream_restart_phase10_admin_ui.py`
- `python -m pytest tests/test_upstream_restart_phase2_projects.py tests/test_upstream_restart_phase6_notifications.py tests/test_upstream_restart_phase7_runtime_inspect.py tests/test_upstream_restart_phase8_project_defaults.py tests/test_upstream_restart_phase10_upstream_sync.py`
- `git diff --check`

# Settings Integration

Added the missing main-shell entry points for the Cloud Terminal features you called out, without spreading the implementation across unrelated Hermes files.

- `Codex` is now its own settings section in [static/index.html](/home/ubuntu/cloud-terminal-data/projects/hermes-webui/static/index.html) with:
  - shared `~/.codex/config.toml` editing
  - inline ChatGPT/Codex OAuth using the existing `/api/oauth/codex/*` flow
  - a low-conflict backend helper in [api/codex_settings.py](/home/ubuntu/cloud-terminal-data/projects/hermes-webui/api/codex_settings.py) plus `/api/codex-config` routes in [api/routes.py](/home/ubuntu/cloud-terminal-data/projects/hermes-webui/api/routes.py)
- `Maintenance` is now its own settings section in [static/index.html](/home/ubuntu/cloud-terminal-data/projects/hermes-webui/static/index.html) and [static/panels.js](/home/ubuntu/cloud-terminal-data/projects/hermes-webui/static/panels.js), reusing the existing `/api/ops/projects/.../upstream-sync` APIs instead of copying `/ops` internals into the main shell.
- The provider card for `openai-codex` now has an `Open Codex settings` action instead of dead-ending at “use the terminal”.

This was kept merge-friendly on purpose:

- new UI is additive (`Codex` and `Maintenance` sections) instead of reshaping existing settings panes
- upstream merge flow still lives in the existing ops APIs
- Codex file handling is isolated in one new backend helper

Verification:

- `python -m py_compile api/codex_settings.py api/routes.py`
- `node --check static/panels.js`
- `python -m pytest tests/test_codex_settings_panel.py tests/test_upstream_restart_phase10_admin_ui.py`
- `git diff --check`

Focused tests passed: `7 passed`.

I did not run a live browser check here, so the remaining gap is visual runtime confirmation in the app itself.

# Core UI Mode live-preview boundary pattern

Session-derived notes from implementing an MVP Hermes WebUI UI Mode for fast UI iteration.

## Architecture shape

- Treat UI Mode as a Core API/runtime domain sibling to Play, not as direct Hermes-agent integration and not as a replacement for the Play build pipeline.
- Source files remain the source of truth. Do not mutate the rendered DOM as the primary edit path.
- Start/attach to a project dev server once, then let the app's own HMR/live reload update the preview; avoid rebuilding/deploying after every chat turn.
- Keep dev servers bound to loopback and expose them to the browser only through a WebUI-owned same-origin proxy path such as `/ui-project/{projectId}/...`.
- Keep the chat sidecar as a normal WebUI session iframe, e.g. create/open via `/api/session/new` and `/session/<sid>?inspect=simplified`, instead of inventing a separate chat backend.

## Backend seam

A minimal in-process Core UI boundary should include:

- config discovery: `.hermes/ui.json`, `.cloud-terminal/ui.json`, `project_ui.json`, then conservative package-script auto-detection;
- lifecycle endpoints: `ui/status`, `ui/logs`, `ui/start`, `ui/restart`, `ui/stop`;
- process registry with allocated loopback port, stdout/stderr log capture, ready detection, and cleanup;
- preview proxy route outside `/api/core`, e.g. `/ui-project/{projectId}/...`, for browser iframe traffic;
- Core capability/route-map docs so shell clients discover the `ui` domain the same way they discover Play/deployments.

## Frontend seam

A useful MVP surface can be a standalone `/ui-mode?projectId=...` shell with:

- live preview iframe on the left;
- project chat iframe on the right;
- start/restart/stop/reload/refresh controls;
- status and log panel;
- an Ops project-detail launcher near existing Play controls.

When auth/CSRF is enabled, serve the shell through a Python helper that injects the CSRF token placeholder, mirroring the normal chat shell pattern.

## Proxy compatibility

For proxied dev apps, HTML responses usually need a small injected script that rewrites root-relative browser APIs back under the preview proxy:

- `fetch`
- `XMLHttpRequest`
- `EventSource`
- `WebSocket`

Also rewrite HTML root-relative asset URLs and `Location` headers so HMR assets and redirects stay same-origin under `/ui-project/{projectId}/...`.

## Verification recipe

Use a tiny temporary Python HTTP server project as the integration fixture rather than a real frontend stack:

1. write a temp project registry row;
2. write `.hermes/ui.json` with `command: "python3 -u server.py"`, auto port env, and loopback host;
3. start through `core_ui.start_project_ui_runtime()`;
4. poll `build_project_ui_status()` until ready;
5. proxy the preview HTML through `handle_ui_proxy_request()`;
6. assert HTML includes the app body, rewritten `/ui-project/...` asset paths, and injected proxy-compat script;
7. assert logs include the ready marker;
8. stop with purge/cleanup.

Run targeted tests and static checks before claiming completion:

```bash
python3 -m py_compile api/core_ui.py api/routes_core.py api/core_contracts.py api/routes.py
node --check static/ui-mode.js static/ui-proxy-compat.js static/ops-legacy-project-detail.js
python3 -m pytest tests/test_core_ui_mode.py tests/test_core_api_contract.py tests/test_core_play_boundary.py tests/test_session_static_assets.py tests/test_subpath_frontend_routes.py tests/test_static_js_runtime_lint.py tests/test_ops_project_detail_focus.py tests/test_ops_deployments_route.py tests/test_home_route_html_error.py tests/test_run_journal_routes.py -q
```

If the full repository suite has unrelated static-contract failures, report that separately from the green targeted/relevant UI Mode verification.

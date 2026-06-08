# Play project/runtime binding mismatch

Use this when a WebUI-launched agent or browser report shows a route for one project/app but Play/runtime diagnostics show another project path, profile, branch, or `project_play.json`.

## Symptoms

- Browser console shows app-specific tRPC 404s, e.g. `/api/trpc/<app>.profile.getHomeState` returns `404 {"error":"not found"}`.
- Browser loads a path like `/summons` or an old `/play-project/<other-project-id>/...` while the workspace is a different project checkout.
- Static Play helper scripts may also 404 or be served as HTML if the page is not loaded through the proper Play proxy URL.
- Source inspection shows the app router/capability exists, but the live server says the route is not found.

## Diagnostic sequence

1. Run runtime doctor/status from the current session:
   - `hermes-runtime doctor --json`
   - `hermes-runtime play status --json`
2. Compare these fields against the actual workspace and intended app:
   - `projectId`
   - `configPath`
   - `configBranch`
   - logs mentioning the build cwd or detected services
3. Check for a mixed WebUI agent environment before blaming the app build. Print only non-secret runtime/session routing fields, redacting request tokens:
   - `HERMES_SESSION_ID`
   - `HERMES_SESSION_KEY`
   - `HERMES_WEBUI_RUNTIME_API_BASE_URL`
   - `HERMES_WEBUI_RUNTIME_PROJECT_ID`
   - `TERMINAL_CWD`
   - `HERMES_HOME`
   A mismatch where `HERMES_SESSION_ID` belongs to the current project but `HERMES_SESSION_KEY`, runtime project id, or `TERMINAL_CWD` belong to an unrelated Ops task is evidence of WebUI runtime context/session isolation leakage, not a project build failure.
4. Query the WebUI project record if needed:
   - `HERMES_WEBUI_RUNTIME_API_BASE_URL` usually contains `/api/ops/projects/<project-id>/runtime`.
   - Request `/api/ops/projects/<project-id>` with `HERMES_WEBUI_REQUEST_INPUT_TOKEN` to confirm `slug`, `path`, `coreBranch`, and `profile`.
5. If needed, list projects via `/api/ops/projects` and find the project whose `path` matches the workspace.
6. If investigating root cause rather than fixing, compare the persisted WebUI session metadata (`session_id`, `workspace`, `project_id`, `profile`, `parent_session_id`) against the live process env. A clean persisted session row plus stale live env points to runtime/process env reuse or restoration leakage.
7. Start Play for the correct project explicitly by overriding only the runtime API base URL for the command:
   ```bash
   HERMES_WEBUI_RUNTIME_API_BASE_URL='http://127.0.0.1:5003/api/ops/projects/<correct-project-id>/runtime' \
     /path/to/hermes-runtime play start --wait --json
   ```
8. If a wrong project build is occupying the global Play queue, stop it through that wrong project id first:
   ```bash
   HERMES_WEBUI_RUNTIME_API_BASE_URL='http://127.0.0.1:5003/api/ops/projects/<wrong-project-id>/runtime' \
     /path/to/hermes-runtime play stop --json
   ```
9. Verify readiness and inspect URL on the correct project:
   - `hermes-runtime play status --json`
   - `hermes-runtime inspect url --json`
   - Correct URLs should look like `/play-project/<correct-project-id>/app/...` and the injected `play-proxy-compat.js` should have `data-hermes-play-proxy-prefix="/play-project/<correct-project-id>"`.
10. Hit the same tRPC route on the correct local allocated port if useful. A protected route returning `401 Unauthorized` proves the namespace exists; `404 not found` indicates the active server still lacks that router/app.
11. Open the correct public inspect URL, log in if needed, and check the browser console.

## Interpretation

- `404 not found` from the wrong project is not proof the app router is missing in source; first prove the runtime is serving the intended project.
- Bare app routes such as `/summons` are not equivalent to the managed Play URL. Use `/play-project/<project-id>/app/<route>` unless the deployment explicitly provides a separate public app route.
- Do not save the mismatch as a durable environment failure. The durable lesson is the comparison-and-retarget pattern above.

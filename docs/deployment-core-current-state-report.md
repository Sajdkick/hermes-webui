# Deployment/Core current-state report

This report summarizes the current Hermes WebUI Core deployment and Ops session-close state for the reported symptoms:

- Ops dashboard session close sometimes showed confusing HTML-looking errors.
- The deployed Alternative Data app could load a login page, but debug empty login/signup could fail with `not found` or `Unable to transform response from server`.
- Cookie/context changes around deployment proxying made Core deployment behavior look unreliable.

## Executive summary

The current implementation has targeted guards for both classes of failures:

1. **Ops session close is now JSON/API driven and lineage-aware.** The backend closes the requested visible session plus linked/root/tip/sibling aliases in the same Ops task/project scope and returns `closedSessionIds`. The frontend optimistically removes the clicked row, consumes `closedSessionIds`, refreshes Ops sessions, and rolls back UI state on API failure.
2. **Deployment compatibility proxying now claims deployment-owned root-relative app paths before WebUI CSRF/body parsing.** Root-relative deployed-app paths such as `/api/trpc/*`, `/api/blob/*`, `/assets/*`, and auth/login paths are treated as deployment traffic only when a `/deploy/<slug>` referer or deployment cookie supplies context. tRPC auth POST bodies are forwarded raw to the deployment runtime.
3. **Core deployment compatibility remains intentionally narrow.** Hermes still owns most root `/api/*` routes. Deployment compatibility only claims known app API/static/auth paths; arbitrary deployment APIs should go through explicit `/deploy/<slug>/...` URLs.

The current evidence points to earlier failures being caused by boundary misclassification rather than the deployed app itself: deployment API calls were previously able to fall through to WebUI routes, CSRF/body parsing, or SPA/HTML fallback responses, which then surfaced as tRPC transform errors or `not found`.

## Ops dashboard session-close state

### Current behavior

`api/ops_sessions.py` resolves close targets from the explicit clicked session id first, then adds known aliases and lineage references. It considers:

- the requested row/session id;
- `session_sidecars.resolve_session_id(...)` aliases;
- task `linkedSessions` aliases;
- unarchived Ops task sessions in the same project whose lineage aliases overlap the target.

It archives all resolved targets, clears active stream state when needed, updates task `inProgress/sessionId/lastSessionAt`, and returns a JSON payload including:

- `ok`;
- `sessionId`;
- `closedSessionIds`;
- `sessionUrl`;
- `cancelledStream`;
- updated `task` and optional `run`.

The frontend close handler in `static/ops-legacy-task-actions.js` removes the clicked row immediately, calls `AgentBridgeRef.sessions.closeTask(...)`, then removes every returned `closedSessionIds` alias and refreshes Ops sessions. On failure it restores the previous `OPS.sessions`, `OPS.sessionActivity`, and task linkage state.

### Why this addresses HTML-looking close errors

HTML-looking errors usually indicate the browser received an HTML fallback page or non-JSON response where the Ops bridge expected JSON. The current close route is routed through the Ops project API and the backend returns JSON via the route wrapper when `close_task_session(...)` succeeds. The frontend also preserves recoverability by rolling back optimistic UI mutations when the API call fails.

### Remaining caveats

- If a reverse proxy or stale frontend bundle routes the close request to the wrong server/path, it can still receive HTML. That should be diagnosed by capturing the exact close request URL, status, content type, and first response bytes.
- The close operation intentionally archives sessions in the same project/task lineage scope; it should not archive unrelated sessions outside that alias group.

## Deployment/Core proxy state

### Current behavior

`api/core_deployments.py` has three deployment proxy entry points:

1. Explicit `/deploy/<slug>/...` requests are deployment proxy traffic.
2. Legacy `/play-proxy/<run>/deploy/<slug>/...` requests are stripped to `/deploy/<slug>/...` and proxied by Core.
3. Root-relative compatibility paths are proxied only when deployment context exists in the referer or deployment cookie.

The compatibility path set is intentionally limited to deployed-app paths including:

- `/api/trpc` and `/api/trpc/*`;
- `/api/blob` and `/api/blob/*`;
- `/api/nakama` and `/api/nakama/*`;
- `/assets/*`, `/auth/*`, `/app/*`, `/stream/*`, `/_stcore/*`;
- exact login/logout/signin/signout/manifest/favicon/health paths.

`api/routes.py` handles deployment proxy POSTs before WebUI CSRF and before generic body parsing. This is critical for tRPC auth endpoints because the deployment runtime must receive the original raw body. The auth layer also treats deployment public requests as public only when the path is an explicit deployment path, a legacy play-proxy deployment path, or a known compatibility path with deployment context.

### Why this addresses Alternative Data login/signup failures

Alternative Data debug login/signup sends tRPC auth requests such as `/api/trpc/auth.login` or `/api/trpc/auth.signup` from a page served under `/deploy/<slug>/...`. If those root-relative POSTs are handled by WebUI instead of the deployment proxy, the app sees `not found`, HTML fallback, CSRF rejection, or a transformed/non-raw body. Any of those can surface in the client as `Unable to transform response from server`.

The current Core path fixes that by:

- recognizing `/api/trpc/*` as deployment-owned only with `/deploy/<slug>` referer/cookie context;
- routing the request before CSRF/body parsing;
- forwarding the raw POST body to the runtime;
- preserving the deployment context cookie so later root-relative app calls have context.

### Current lifecycle state

Hermes Core now reads Cloud Terminal deployment records, including slug, provider, database mode, snapshot path, and public URL, without rewriting or recreating deployment databases. Existing `local-legacy` deployments advertise redeploy support and preserve database mode. The current safe lifecycle guidance remains:

- use update/redeploy on the existing record;
- preserve `persistent`/`shared` database modes;
- do not stop/delete/publish-new unless intentionally starting a new deployment lifecycle.

## Verification evidence

The following focused tests cover the reported failure boundaries:

- `tests/test_ops_sessions_dedupe.py::test_close_task_session_archives_requested_visible_root_when_resolver_prefers_archived_tip`
- `tests/test_ops_sessions_dedupe.py::test_close_task_session_archives_stale_visible_siblings_for_same_task`
- `tests/test_core_deployments.py::test_deployment_compatibility_post_routes_before_csrf`
- `tests/test_core_deployments.py::test_deployment_compatibility_auth_bypass_uses_referer_or_cookie_context`
- `tests/test_core_deployments.py::test_deployment_compatibility_claims_only_known_app_api_paths`
- `tests/test_core_deployments.py::test_deployment_compatibility_proxy_forwards_raw_auth_body`
- `tests/test_upstream_restart_phase7_play.py::test_phase7_play_proxy_forwards_body_already_consumed_by_main_post_route`

## Recommended diagnostics if the issue recurs

1. Capture the failing request from browser devtools or gather instrumentation: URL, method, status, content type, referer, and first 200 response bytes.
2. For tRPC failures, verify the response is JSON from the deployment runtime, not `text/html` from WebUI/SPA fallback.
3. For session close failures, verify the request path is the Ops task close endpoint and that the response includes JSON `closedSessionIds`.
4. Confirm whether the page was loaded through `/deploy/<slug>/...`, `/play-proxy/<run>/deploy/<slug>/...`, or a direct runtime URL; different surfaces exercise different proxy context rules.
5. Confirm the deployed app is not using root-relative API paths outside the current compatibility allowlist. If it is, route those calls under `/deploy/<slug>/...` or extend the allowlist with focused tests.

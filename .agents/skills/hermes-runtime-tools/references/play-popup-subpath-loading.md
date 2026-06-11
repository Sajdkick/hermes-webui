# Play popup/session overlay subpath loading failures

Use this when a Hermes WebUI Play popup opens but the chat/session overlay inside the playing view fails to load, especially when WebUI is mounted under a prefix such as `/hermes`.

## Durable lesson

Do not stop after fixing the visible popup iframe URL. A Play popup that fails to show the chat/session can have several independent root-path assumptions:

1. The notification/open URL may drop the WebUI mount prefix and open `/play-project/...` instead of `/<mount>/play-project/...`.
2. Injected helper scripts may use root `/static/...` URLs, so `play-session-overlay.js` or `play-proxy-compat.js` fail to load when the WebUI is mounted below a subpath.
3. Proxy-compat code may rewrite app fetch/WebSocket calls to root `/play-project/...`, breaking app traffic even after the popup itself opens.
4. The backend proxy may need a project-scoped static helper route, e.g. `/play-project/{projectId}/.hermes-webui/static/{asset}`, so injected helpers resolve relative to the proxied Play page rather than the deployment root.

## Debugging path

1. Reproduce or inspect the popup URL and preserve the full path prefix.
2. Audit the frontend open/link builder, the backend Play HTML/script injection, and any proxy-compat URL rewriting together; these are separate failure points.
3. Prefer relative or proxy-local helper URLs for injected scripts instead of root `/static/...` paths.
4. Add regression coverage for all mounted-prefix cases:
   - notification/open URL preserves the mount prefix;
   - injected helper script paths are proxy-local/relative;
   - app API and WebSocket rewrite helpers preserve the mount prefix;
   - the backend can serve helper scripts through the Play proxy route.
5. After code changes, report that backend route changes require WebUI backend restart/reload, and recommend a hard browser refresh to clear stale Play helper JS.

## What not to save as a conclusion

Missing local E2E scripts or missing Playwright packages in a checkout are setup state, not a durable rule. Capture the fallback verification you actually ran, but do not encode “E2E is unavailable” as a skill invariant.

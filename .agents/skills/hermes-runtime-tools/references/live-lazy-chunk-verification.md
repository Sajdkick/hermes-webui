# Live lazy-chunk verification after Play restart

Use this when `hermes-runtime play status --json` reports ready but screenshot capture is unavailable, slow, or times out, and the task only needs proof that the running Play server is serving a specific UI/source change.

## Pattern

1. Get the allocated server from `hermes-runtime play status --json`:
   - `allocatedPortHost`
   - `allocatedPort`
   - `inspectUrl`
2. Fetch the direct app route, usually `http://<host>:<port>/app`, and require HTTP 200 HTML.
3. Parse the returned HTML for the built `index-*.js` script.
4. Fetch the index chunk and find the relevant lazy route chunk name, for example `PlayableMapDemoHome-*.js`.
5. Fetch the lazy chunk directly from `/assets/<chunk>.js`.
6. Assert the expected strings/markers are present in that live chunk.

## Why this matters

Hermes runtime screenshots are useful but not the only valid runtime proof. A screenshot timeout can be an inspect/browser issue even when Play is healthy and serving the new build. Direct chunk verification proves the running server has the intended hashed bundle without requiring browser automation.

## Reporting

Separate these facts in the final response:

- Play readiness status and route.
- Screenshot/inspect limitation, if any.
- Direct HTTP/chunk proof that the live server is serving the updated code.

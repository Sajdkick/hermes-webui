# UI Mode gather report readiness

Use this reference when preparing a Hermes WebUI gather report for a user-reproduced UI Mode bug, especially when the app is served from Play/static build assets.

## Canonical flow

1. Create a fresh Hermes gather report with the Hermes WebUI gather script and capture `report.id`, `ingest.path`, `ingest.tokenHeader`, and `ingest.token`.
2. Smoke-test ingestion before changing app code by POSTing a terminal event to the WebUI host plus `ingest.path`; verify `show REPORT_ID --json` reports the smoke-test label as latest or increments `eventCount`.
3. Patch only the temporary investigation helper/constants needed for the report. Avoid broad rewrites while preparing evidence capture.
4. Verify source without printing secrets: report whether the fresh report id, token header, helper name, and expected event labels are present; do not echo the token in user-facing output.
5. Run focused tests for the touched surface and `git diff --check` before the canonical app build.
6. Run the canonical app build from the project docs. For Summons in this monorepo, that is `bash ./scripts/deploy-build.sh summons` from the repository root.
7. Verify the live UI Mode route, not just local files:
   - fetch the active preview route with no-cache headers;
   - fetch its module script/index chunk;
   - parse the dynamic import map for the page chunk;
   - fetch the page chunk and any lazy runtime/editor chunk it imports;
   - assert the fresh report id and key event labels are present and old report ids are absent.
8. Only then give the user concise reproduction steps and a short completion phrase such as `done`.
9. After the user reproduces, inspect the report with the Hermes gather script and summarize the event sequence before deciding on a fix.

## Pitfalls

- Do not trust source edits alone in UI Mode. Static preview can still be serving an older hashed chunk.
- Do not rely on a simplistic `assets/<name>.js` regex only. Vite import maps often store sibling chunks as `./ChunkName-hash.js` inside the index/page chunk.
- Do not print gather tokens in the final report. It is okay to confirm the token field exists and that the token header is `X-Hermes-Gather-Token`.
- Do not mark the report ready until ingestion is smoke-tested and the live route/chunk graph proves the fresh report id is served.
- Keep the readiness work separate from the actual bug fix. Leave a pending follow-up/wait task until the user says they reproduced the bug.

## Useful event labels for canvas/WebGL lasso investigations

Capture both wrapper and renderer layers. Representative labels include:

- `viewport.mount-effect-start`
- `viewport.update-options-effect`
- `viewport.onViewStateChange.update-controller`
- `3d.mount-start`
- `3d.updateOptions`
- `3d.pointerDown.kits`
- `3d.pointerUp.kits`
- `3d.pointerUp.kits.drag-ignored`
- `3d.pointerUp.kits.route-cut-handler`
- `3d.kitSourceRaycast.hit`
- `3d.kitSourceRaycast.miss`
- `3d.handleKitCutPointerUp.start`
- `3d.handleKitCutPointerUp.candidate-decision`
- `3d.handleKitCutPointerUp.append-anchor-success`
- `3d.handleKitCutPointerUp.closed-loop-success`
- `3d.resetDraftCutLoop.start`
- `3d.dispose`

These labels distinguish: handler not reached, tap classified as drag, raycast missed, state mutated then reset, and state present but not rendered.
# Mobile browser hard-reload gather pattern

Use this when a user reports that a mobile browser tab reloads or disappears immediately after an interaction (camera capture, file picker, WebGL/model load, WASM inference), especially when normal error boundaries and promise catches do not fire.

## Why this is different

A hard reload/OOM/suspend kill can prevent ordinary `catch` handlers and post-failure logs from running. The useful evidence is often the **last event before the risky boundary** plus a marker discovered on the next page load.

## Pattern

1. Create a fresh Hermes gather report and smoke-test ingestion from terminal.
2. Add a small local helper that posts to the same-origin `ingest.path` with the returned token header.
3. Before the risky user action starts expensive work, write a compact marker to both `sessionStorage` and `localStorage`:
   - report id / investigation slug
   - attempt id
   - route
   - selected module/mode
   - file metadata only: size, MIME type, last-modified age
   - viewport, hardwareConcurrency, deviceMemory when available
   - `performance.memory` when available
4. On component/page mount, read that marker and immediately emit a `*.page-mounted` event with `hadPreviousMarker` and the marker payload. If the previous attempt crashed/reloaded before cleanup, this proves the crash boundary even when no error event fired.
5. Add `pagehide`, `visibilitychange`, `window.error`, and `unhandledrejection` gather hooks, but do not rely on them as the only evidence; OOM/tab reloads may skip them.
6. Add boundary events around each expensive step:
   - input selected
   - pipeline/module selected
   - resize/decode start
   - resize/decode complete, including output data URL/blob size only
   - local model/WASM inference start
   - local model/WASM inference complete
   - server/API upload start/complete if applicable
   - normal handler error
   - full flow complete
7. Clear the marker only on normal handler error or full successful completion. Do not clear it at step start.
8. Build/sync and verify the **proxied/live route** serves a chunk containing both the report id and key event labels before asking the user to reproduce.
9. Ask the user to reproduce once and reply with a short completion phrase. Do not ask them to copy console logs or send photos/files unless the gather data shows ingestion did not occur.
10. After evidence is collected or replaced by the fix, remove temporary tokens/instrumentation.

## Privacy/safety

- Never send the captured photo, file contents, request bodies, cookies, credentials, API keys, or raw tokens in final summaries.
- File metadata is usually enough: byte size, MIME type, approximate resized output size.
- If you mention a gather token in code during the session, remove it before finishing the actual fix.

## Useful interpretation

- `input-selected` exists, then next `page-mounted` has a previous marker and no resize-start: crash/reload happened before your resize/decode boundary or during camera/file handoff.
- `resize-start` exists, no `resize-complete`, then marker on next mount: decode/canvas/image-bitmap path is suspect.
- `embedding-start` exists, no `embedding-complete`, then marker on next mount: local model/WASM/runtime memory or worker lifecycle is suspect.
- `embedding-complete` and full-flow-complete both exist before the next unexpected mount/reload: deprioritize decode/inference as direct causes and inspect post-success memory pressure, retained result state, model-session cleanup, and repeated-load behavior.
- If the first photo succeeds but the second photo crashes after adding model cleanup, consider whether immediate per-photo disposal is forcing a second full WASM/ONNX model allocation before the browser has actually reclaimed memory. A short idle cleanup plus explicit reset/page cleanup may be safer than disposing after every photo.
- Normal `photo-handler-error` with marker cleanup is not a hard reload; debug it as an ordinary thrown error.

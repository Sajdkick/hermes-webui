# Browser `Failed to fetch` gather pattern

Use this reference when a user can reproduce a browser-side `Failed to fetch` but terminal builds, static asset checks, or source inspection look correct.

## Durable lesson

A successful build and direct terminal fetch of assets does not prove the user's browser is executing the instrumented artifact or that the failing fetch is the asset you expect. Create a gather report, insert a narrow browser-side fetch probe, verify the live route/chunk contains the report id and event labels, then ask the user to reproduce once.

## Recommended instrumentation

1. Create a Hermes gather report and capture `report.id`, `ingest.path`, `ingest.tokenHeader`, and `ingest.token`.
2. Add a small temporary helper near the feature under investigation, not a permanent logging framework.
3. Install a one-time browser `fetch` wrapper that records only suspicious requests:
   - failed fetches/rejected promises;
   - non-2xx responses for relevant runtime dependencies;
   - API calls such as `/api/trpc`;
   - same-origin model/WASM assets;
   - unexpected external model/CDN providers.
4. If the feature uses browser ML, WebAssembly, or workers, also install a temporary `Worker` constructor probe. Some failures never pass through `fetch()` because ONNX Runtime/Emscripten creates worker sidecars directly (for example `ort-wasm-threaded.worker.js`, `ort-wasm-threaded.js`, or blob worker URLs). Capture worker URL/type/name, constructor errors, and worker `error` events.
5. Log flow boundaries around the UI handler:
   - handler entered/clicked;
   - early-return reasons;
   - file/input selected;
   - image/file normalization start/success;
   - client-side model import/load start/success/error;
   - server mutation start/success/error;
   - final catch block with both formatted user-facing message and raw error summary.
5. Add an obvious temporary visible marker that includes the report id when safe. This prevents stale-build confusion and gives the user a quick way to confirm the instrumented code loaded.
6. Build and verify the live artifact, not just source:
   - run the canonical app build for the environment;
   - fetch the live route with no-cache headers;
   - recursively fetch imported JS chunks if needed;
   - assert the report id and key event labels appear in the served chunk.
7. Smoke-test ingestion before asking the user to reproduce. Prefer the public gather endpoint when possible. If running inside the WebUI repo/process context, `api.gather.append_gather_event(...)` can be used as a fallback to prove the report can be appended and read.
8. Ask the user to reproduce exactly once and reply with a short completion phrase such as `done`; ask for `no banner` if the visible marker is absent.
9. After capture, inspect the report and remove the temporary helper/visible marker unless the user asks to keep diagnostics.

## Good event labels

Use short namespaced labels that identify boundaries and failure locations:

- `photo.fetch-probe.installed`
- `photo.fetch.error`
- `photo.fetch.response-error`
- `photo.input.change`
- `photo.input.catch`
- `localClip.transformers.import.start`
- `localClip.processor.load.error`
- `localClip.embedPhoto.error`
- `serverMutation.embedding.start`
- `serverMutation.embedding.error`

## Error payload shape

Keep payloads compact and safe:

```ts
function getGatherErrorData(error: unknown) {
  if (error instanceof Error) {
    return {
      name: error.name,
      message: error.message,
      stack: error.stack?.split('\n').slice(0, 8).join('\n'),
      cause: error.cause instanceof Error
        ? { name: error.cause.name, message: error.cause.message }
        : typeof error.cause === 'string'
          ? error.cause
          : undefined,
    };
  }
  return { value: String(error) };
}
```

Do not log tokens, cookies, passcodes, full request bodies, or full image/data URLs. For images, log size and a short prefix only.

## Pitfalls

- Do not keep asking the user to reproduce if only terminal smoke events appear. Treat that as stale deployment, wrong route, blocked ingestion, or missing visible marker.
- Do not conclude that a runtime dependency is fixed just because `curl`/`urllib` can fetch it from the server. Browser code may resolve a different module-relative URL or still run an old hashed chunk.
- When a live chunk scan finds missing worker/sidecar candidates (for example `ort-wasm-threaded.worker.js`, `ort-wasm-threaded.js`, `.worker.js`, or module-relative `/assets/ort-*` URLs), treat that as a first-class hypothesis even if all explicitly copied `.wasm` files return `200`. ONNX Runtime can need both WASM binaries and JS worker sidecars, and sidecar construction can fail as a generic `Failed to fetch` or worker error.
- Do not persist the debug token or report id beyond the temporary investigation. Remove debug helpers after use.
- If the expected model/WASM/API asset requests all succeed but the browser still reports `Failed to fetch`, inspect the failed request URL and stack instead of assuming the asset path is still wrong. Some browser libraries route non-network inputs through `fetch()`: for example, Xenova/Transformers.js `RawImage.read(data:image/...)` can call `fetch(data:image...)` and fail under a proxy/CSP browser runtime even though every same-origin model asset returns `200`. Capture a short URL prefix plus stack frames, not the full data URL, and prefer a Blob/native input path such as `RawImage.fromBlob(dataUrlToBlob(photoDataUrl))` when available.

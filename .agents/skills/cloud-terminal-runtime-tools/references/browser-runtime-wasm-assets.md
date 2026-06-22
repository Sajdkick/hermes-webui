# Browser runtime WASM/worker asset checks

Use this reference when a browser-only dependency works in build/typecheck but fails at runtime with a generic fetch/backend error, especially ONNX Runtime / Transformers.js errors such as:

```text
no available backend found
WebAssembly.instantiate(): expected magic word 00 61 73 6d, found 3c 21 64 6f @+0
```

`00 61 73 6d` is the WASM magic header. `3c 21 64 6f` is `<!do`, meaning the browser fetched an HTML fallback page instead of the `.wasm` file.

## Diagnostic pattern

1. Identify the exact runtime asset URL the browser will request. For dependencies that compute URLs from a module/chunk, prefer reproducing the module-relative URL, not just a guessed root URL.
2. Probe both status and first bytes:

```bash
python3 - <<'PY'
from urllib.request import Request, urlopen
for url in [
  'http://127.0.0.1:PORT/app',
  'http://127.0.0.1:PORT/assets/ort/ort-wasm-simd-threaded.wasm',
  'http://127.0.0.1:PORT/apps/playable-map-demo/client/lib/ort/ort-wasm-simd-threaded.wasm',
]:
    with urlopen(Request(url, method='GET'), timeout=10) as response:
        print(url, response.status, response.headers.get('content-type'), response.read(4).hex(' '))
PY
```

Expected for a WASM asset:

```text
200 application/wasm 00 61 73 6d
```

HTML fallback shows:

```text
200 text/html 3c 21 64 6f
```

3. Verify dev and built/Play paths separately. A direct production server check can pass while the actual Play/WebUI proxied dev path still falls through to HTML.

## Durable fix pattern

- Do not rely only on absolute `/assets/...` URLs in proxied Play/WebUI runtimes; they can resolve against the proxy/root app and return HTML.
- Prefer dependency asset URLs derived from the executing module/chunk, e.g. `new URL('./ort/<file>', import.meta.url).href`.
- When a runtime needs a filename-to-URL map, use static literal `new URL('./ort/exact-file.wasm', import.meta.url)` entries for each known sidecar and inspect the emitted JS. Avoid unchecked dynamic templates such as ``new URL(`./ort/${filename}`, import.meta.url)``; Vite can leave or transform opaque dynamic asset URLs into invalid lookups that fall through to HTML.
- In Vite dev, add middleware that serves any matching module-relative asset request (for example any basename matching `ort-wasm*.(wasm|js)`), not just a single absolute route like `/assets/ort/`.
- In production builds, copy the same runtime assets next to the emitted chunk path used by `new URL(...)`, and ensure deploy/build scripts sync those copied files into the server-served static bundle.
- After rebuild, restart the running Play/server process and hard-refresh or clear site data if stale chunks are still loaded.

## Verification checklist

- Format and typecheck changed client/runtime config files.
- Build the client and app deploy artifact.
- Confirm all copied runtime assets exist in both client `dist` and the server-served static bundle.
- Start the built server manually if `ct-runtime` is unavailable and verify:
  - `/app` returns HTML (`3c 21 64 6f` is fine for `/app`).
  - The exact `.wasm` URL returns `application/wasm` and first bytes `00 61 73 6d`.
- Stop any manual background server before finishing.

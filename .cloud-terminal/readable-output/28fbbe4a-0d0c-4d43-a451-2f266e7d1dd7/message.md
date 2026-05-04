# `/ops` diagnosis

`/session/ops` was the wrong workaround. The clean URL should still be plain `/ops`.

## Clarification

You said you do switch the public proxy to `hermes` when testing. That is compatible with what I found.

The stronger failure is not the proxy target snapshot. It is the Hermes process itself.

## What I verified

At `2026-05-04 07:17 UTC`, direct local requests to the Hermes server returned:

- `http://127.0.0.1:5003/ops` → `404`
- `http://127.0.0.1:5003/session/ops` → `404`

The response header from that process was:

- `HermesWebUI/0.50.125-39-g4567163-dirty`

So even if the public proxy is switched to `hermes` during your test, the Hermes target behind it is still serving an older/stale runtime that does not know about the new `/ops` route.

## Conclusion

This is not a URL-shape problem anymore.

It is a runtime problem:

- the actual Hermes process on `5003` did not pick up the new code

## Clean fix

- keep the intended URL as plain `/ops`
- stop trying to use `/session/ops`
- restart the actual Hermes target on `5003`
- then test `/ops` again while the public proxy is switched to `hermes`

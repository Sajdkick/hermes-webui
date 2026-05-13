---
name: cloud-terminal-gather-information
description: Collect structured, user-driven runtime evidence from Cloud Terminal or Hermes WebUI project sessions. Use when Codex needs the user to reproduce a flow, click through the app, or trigger code paths that are hard to inspect from the terminal alone, and temporary instrumentation in the project code is acceptable. Prefer this skill when you want to read the resulting report directly instead of asking the user to copy and paste findings.
---

# Cloud Terminal Gather Information

Use the session's native gather bridge to create a session-scoped report, add a temporary logging hook that posts into it, ask the user to reproduce the flow, then inspect the captured events directly from the terminal.

## First choose the gather bridge

- Cloud Terminal project session: use `ct-runtime gather ...`.
- Hermes WebUI project/session: use `hermes-runtime` first.
  1. Run `hermes-runtime doctor --json`.
  2. If the doctor reports usable `HERMES_WEBUI_*` runtime/request-input context, create/read reports with:
     - `hermes-runtime gather create --title "Save flow repro" --json`
     - `hermes-runtime gather show REPORT_ID --json`
  3. If the doctor reports missing `HERMES_WEBUI_RUNTIME_API_BASE_URL`, `HERMES_WEBUI_REQUEST_INPUT_URL`, or `HERMES_WEBUI_REQUEST_INPUT_TOKEN`, do **not** try `ct-runtime` or add a compatibility shim. Treat this as native WebUI runtime context unavailable and use the fallback section below.

## Cloud Terminal workflow

1. Create a report:
   - `ct-runtime gather create --title "Save flow repro" --json`
   - Capture `report.id`, `report.path`, `ingest.path`, `ingest.url`, `ingest.tokenHeader`, and `ingest.token`.
2. Add the narrowest possible temporary instrumentation near the failing or uncertain code path.
3. Ask the user to reproduce the exact flow.
4. Read the result:
   - `ct-runtime gather show REPORT_ID --json`
   - Or read `report.path` directly when inspecting the file is simpler.
5. Remove the temporary hooks after you have the evidence unless the user explicitly wants them kept.

## Hermes WebUI workflow

1. Create a report:
   - `hermes-runtime gather create --title "Save flow repro" --json`
   - Capture `report.id`, `report.path`, `ingest.path`, `ingest.url`, `ingest.tokenHeader`, and `ingest.token`.
2. Add the narrowest possible temporary instrumentation near the failing or uncertain code path.
3. Ask the user to reproduce the exact flow.
4. Read the result:
   - `hermes-runtime gather show REPORT_ID --json`
   - Or read `report.path` directly when inspecting the file is simpler.
5. Remove the temporary hooks after you have the evidence unless the user explicitly wants them kept.

## Hermes WebUI / runtime-unavailable fallback

If `hermes-runtime doctor --json` reports missing WebUI runtime/request-input context, use the narrowest app-local temporary instrumentation available instead of `ct-runtime`:

- structured browser `console.info` / `console.warn` entries with a distinctive prefix,
- an existing in-page diagnostic buffer if the app has one,
- a localStorage key for persistence across the immediate repro,
- a local project file written by backend code under an existing test/debug state directory,
- readable-output instructions that tell the user exactly how to reproduce and retrieve the buffered diagnostics.

In the final report, explicitly separate official gather-report unavailability from successful app-local instrumentation and verification.

## Instrumentation Rules

- Prefer structured fields over prose. Log compact objects like `{ selectedId, pendingCount, route }`.
- Log boundaries and branch decisions: entering handler, fetched response, derived state, render condition, thrown error.
- Keep the hook local to the investigation. Do not introduce a permanent generic logging framework for one-off debugging.
- Avoid secrets, passcodes, tokens, or large blobs. Redact or omit sensitive values.
- For noisy code paths, log only when values change or when a predicate matches.

## Browser Pattern

Prefer a same-origin relative path from `ingest.path` for browser code:

```js
const gatherReport = {
  path: "__INGEST_PATH__",
  tokenHeader: "__TOKEN_HEADER__",
  token: "__TOKEN__",
};

async function sendGatherEvent(label, data = {}, extras = {}) {
  try {
    await fetch(gatherReport.path, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        [gatherReport.tokenHeader]: gatherReport.token,
      },
      body: JSON.stringify({
        type: extras.type || "log",
        level: extras.level || "info",
        label,
        message: extras.message || "",
        route: typeof window !== "undefined" ? window.location.pathname : "",
        url: typeof window !== "undefined" ? window.location.href : "",
        data,
        meta: extras.meta || null,
      }),
    });
  } catch (error) {
    console.warn("sendGatherEvent failed", error);
  }
}
```

## Server Pattern

- Use `ingest.url` when the code runs outside the browser and cannot rely on same-origin routing.
- Reuse the same JSON shape as the browser example.
- Keep the token scoped to the temporary helper you are adding for this investigation.

## Review

- Start by checking `report.latestEvent` and the last few events before reading everything.
- If the report is missing expected data, tighten the hooks and run another reproduction instead of asking the user for a manual report.
- Once you understand the behavior, replace the debug hook with the actual fix or remove it entirely.

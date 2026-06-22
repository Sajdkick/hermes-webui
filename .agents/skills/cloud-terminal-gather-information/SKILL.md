---
name: cloud-terminal-gather-information
description: Collect structured, user-driven runtime evidence from a Cloud Terminal project session. Use when Codex needs the user to reproduce a flow, click through the app, or trigger code paths that are hard to inspect from the terminal alone, and temporary instrumentation in the project code is acceptable. Prefer this skill when you want to read the resulting report directly instead of asking the user to copy and paste findings.
---

# Cloud Terminal Gather Information

Use `ct-runtime gather` to create a session-scoped report, add a temporary logging hook that posts into it, ask the user to reproduce the flow, then inspect the captured events directly from the terminal.

If `ct-runtime gather create` returns `ct-runtime only works inside a Cloud Terminal project session`, do not stop or ask the user to collect console logs manually. Switch to the Hermes WebUI gather workflow (`hermes-gather-information`) and create the report with `/home/ubuntu/cloud-terminal-data/projects/hermes-webui/scripts/hermes-gather.py` from the current workspace.

For mobile browser hard reloads/crashes where the page reloads before a normal exception can be caught, use the Hermes WebUI gather reference `mobile-browser-hard-reload-gather.md` when available. The important pattern is to write a compact pre-action marker to `sessionStorage`/`localStorage`, emit it on the next page mount, log boundaries around decode/resize/model/API work, and clear the marker only on normal error or successful completion.

## Workflow

1. Create a report:
   - `ct-runtime gather create --title "Save flow repro" --json`
   - Capture `report.id`, `report.path`, `ingest.path`, `ingest.url`, `ingest.tokenHeader`, and `ingest.token`.
2. Add the narrowest possible temporary instrumentation near the failing or uncertain code path.
3. Ask the user to reproduce the exact flow.
4. Read the result:
   - `ct-runtime gather show REPORT_ID --json`
   - Or read `report.path` directly when inspecting the file is simpler.
5. Remove the temporary hooks after you have the evidence unless the user explicitly wants them kept.

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

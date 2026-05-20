---
name: hermes-gather-information
description: Collect structured, user-driven runtime evidence with Hermes WebUI gather reports. Use when the user can reproduce a browser/server flow, a screenshot contradicts source or tests, or a runtime branch is hard to inspect from terminal output alone. Prefer this before asking the user to copy console logs manually.
---

# Hermes Gather Information

Hermes WebUI has a native gather-report system. Use this skill when you need temporary instrumentation and user-reproduced evidence; use `hermes-runtime gather ...` only when managed runtime access is available and a plain report create/show is enough.

Use the Hermes WebUI CLI script to create a session-scoped report, add temporary instrumentation that POSTs structured events to the returned `/api/gather/.../events` endpoint, ask the user to reproduce the flow, then inspect the saved report directly.

## Commands

Run the CLI from the Hermes WebUI repository root:

```bash
cd /home/ubuntu/cloud-terminal-data/projects/hermes-webui
python3 scripts/hermes-gather.py create --title "Save flow repro" --json
python3 scripts/hermes-gather.py show REPORT_ID --json
python3 scripts/hermes-gather.py list --json
```

If working from another workspace, either `cd` to the WebUI repo first or call the script by absolute path:

```bash
python3 /home/ubuntu/cloud-terminal-data/projects/hermes-webui/scripts/hermes-gather.py create --title "Runtime repro" --workspace "$PWD" --json
```

The `create` command returns:

- `report.id`
- `report.path`
- `ingest.path` / `ingest.url` like `/api/gather/<report-id>/events`
- `ingest.tokenHeader` (`X-Hermes-Gather-Token`)
- `ingest.token`

The report is stored under the active Hermes WebUI state directory (`HERMES_WEBUI_STATE_DIR` or `~/.hermes/webui/gather`).

## Workflow

1. Create a report:
   - `python3 scripts/hermes-gather.py create --title "Summons flick-arrow repro" --workspace "$PWD" --json`
   - Capture `report.id`, `report.path`, `ingest.path`, `ingest.tokenHeader`, and `ingest.token`.
2. Add the narrowest possible temporary instrumentation near the uncertain runtime path.
3. Ask the user to reproduce the exact flow.
4. Inspect the report:
   - `python3 scripts/hermes-gather.py show REPORT_ID --json`
   - Or read `report.path` directly when that is easier.
5. Remove the temporary hooks after the evidence is captured unless the user explicitly asks to keep them.

## When to use

Use this before continuing to infer from code alone when:

- a screenshot or live user observation contradicts tests/source expectations;
- the bug depends on browser state, playback timing, route state, or user interaction;
- a server/browser handoff is suspected but not visible from unit tests;
- you would otherwise ask the user to copy console output or describe internal state.

## Instrumentation rules

- Prefer structured fields over prose, e.g. `{ selectedId, pendingCount, route }`.
- Log boundaries and branch decisions: handler entered, fetched response, derived state, render condition, thrown error.
- Keep hooks local to the investigation. Do not introduce a permanent generic logging framework for a one-off repro.
- Avoid secrets, passcodes, tokens, cookies, full request bodies, or large blobs. Redact or omit sensitive values.
- For noisy code paths, log only when values change or when a predicate matches.

## Browser pattern

Use the same-origin `ingest.path` returned by `create` for browser code:

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

## Server pattern

- Use `ingest.path` for same-origin WebUI requests.
- Use an absolute WebUI base URL plus `ingest.path` only when code runs outside the browser and cannot rely on same-origin routing.
- Reuse the same JSON shape as the browser example.
- Keep the token scoped to the temporary helper you are adding for this investigation.

## Review

- Start with `report.latestEvent` and the last few events before reading everything.
- If the report is missing expected data, tighten the hooks and run another reproduction instead of asking the user for a manual report.
- Once you understand the behavior, replace the debug hook with the actual fix or remove it entirely.

## Implementation reference

- CLI: `/home/ubuntu/cloud-terminal-data/projects/hermes-webui/scripts/hermes-gather.py`
- API helpers: `/home/ubuntu/cloud-terminal-data/projects/hermes-webui/api/gather.py`
- POST route: `/api/gather/<report-id>/events`
- Tests: `/home/ubuntu/cloud-terminal-data/projects/hermes-webui/tests/test_gather_information.py`

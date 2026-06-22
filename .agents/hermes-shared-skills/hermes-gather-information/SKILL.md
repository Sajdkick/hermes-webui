---
name: hermes-gather-information
description: Collect structured, user-driven runtime evidence with Hermes WebUI gather reports. Use when the user can reproduce a browser/server flow, a screenshot contradicts source or tests, or a runtime branch is hard to inspect from terminal output alone. Prefer this before asking the user to copy console logs manually.
---

# Hermes Gather Information

Hermes WebUI has a native gather-report system. Use this skill when you need temporary instrumentation and user-reproduced evidence. In this environment, Hermes WebUI gather is the only gather workflow.

Use the Hermes WebUI CLI script to create a session-scoped report, add temporary instrumentation that POSTs structured events to the returned `/api/gather/.../events` endpoint, ask the user to reproduce the flow, then inspect the saved report directly.

## Canonical rule

Always create and inspect reports with the Hermes WebUI gather script:

```bash
python3 /home/ubuntu/cloud-terminal-data/projects/hermes-webui/scripts/hermes-gather.py create --title "..." --workspace "$PWD" --json
python3 /home/ubuntu/cloud-terminal-data/projects/hermes-webui/scripts/hermes-gather.py show REPORT_ID --json
```

For cleanup/audit tasks where stale runtime/gather terminology may exist, use `references/hermes-runtime-gather-naming-cleanup.md` before editing. It captures the canonical Hermes runtime vs Hermes gather separation, search patterns, token header, and generated-artifact pitfalls.

For UI Mode report readiness work, use `references/ui-mode-gather-report-readiness.md`. It captures the fresh-report → smoke-test → patch constants → focused tests → canonical build → live route/chunk proof → concise repro handoff sequence.

For browser-side `Failed to fetch` reports where builds and direct asset fetches look correct, use `references/browser-fetch-failure-gather.md`. It captures the temporary fetch-probe + UI boundary logging pattern, visible report-id marker, live route/chunk verification, and the “reply done/no banner” repro handoff.

For mobile browser hard reloads/crashes where the tab reloads before normal errors can be caught, use `references/mobile-browser-hard-reload-gather.md`. It captures the persistent pre-action marker, page-mount recovery event, pagehide/visibility/error hooks, last-boundary interpretation, live route/chunk proof, privacy constraints, and cleanup of temporary gather tokens.

For canvas/WebGL cut-loop or lasso selection bugs where tests pass but the live model selects too much/too little, use `references/cut-loop-gather-debugging.md`. It captures the phase-by-phase fragment/bounds logging pattern and the reinclusion pitfall where fixes can swing from whole-face/body selection to only the tiny seeded island. Also use `references/cut-loop-gather-evidence-before-fixes.md` when the user reports oscillating visual geometry behavior or asks for report-backed debugging before more fixes; it covers automatic gather collection, pre/post-fragment diagnostics, and how to distinguish split, classification, pruning, and projection-frame failures. Use `references/cut-loop-visual-success-metrics.md` when a screenshot contradicts a supposedly successful gather report; it captures why seam-only metrics can miss raised/detached gray islands inside a lasso and the component-level diagnostic shape to add.

Capture the returned `report.id`, `report.path`, `ingest.path`, `ingest.tokenHeader`, and `ingest.token` before editing code. If the app is served from built/static assets, treat source instrumentation as incomplete until the canonical app build has run and the live route/chunk graph is verified to contain the report id and event labels.

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
   - Put one small `sendGatherEvent()` helper close to the code under investigation, or import a local temporary helper if several files need it.
   - Log boundaries first, then branch decisions and compact state snapshots.
3. Smoke-test ingestion before asking the user to reproduce:
   - POST one terminal-generated event to `ingest.url` or the WebUI base URL plus `ingest.path` with the returned token header.
   - Confirm `eventCount` increments or `latestEvent.label` matches the smoke-test label.
4. Build and prove the instrumented code is actually what the user will run.
   - For hot-reload dev servers, verify the running page sees the helper/labels.
   - For Play/static build workflows, run the canonical build and fetch the live route plus imported assets. Confirm the route's `index-*.js` imports the page chunk, the page chunk imports the instrumented chunk, and the chunk contains both the `report.id` and key event labels.
5. Ask the user to reproduce the exact flow once. Give numbered steps and ask them to reply with a short completion phrase such as `done`.
6. Inspect the report:
   - `python3 scripts/hermes-gather.py show REPORT_ID --json`
   - Or read `report.path` directly when that is easier.
   - Start with `latestEvent` and the final 20–50 events, then scroll backward to the first unexpected reset/error/missing branch.
   - If the user says they reproduced but the report still contains only the terminal smoke-test event, do not keep asking them to repeat indefinitely. Treat it as a deployment/ingestion mismatch: re-verify the live route/chunk graph contains the report id and labels, verify the browser code posts to same-origin `ingest.path`, then either tighten instrumentation with an obvious visible marker or continue from source/test evidence while clearly reporting that no browser events arrived.
7. Remove the temporary hooks after the evidence is captured unless the user explicitly asks to keep them.

## When to use

Use this before continuing to infer from code alone when:

- a screenshot or live user observation contradicts tests/source expectations;
- the bug depends on browser state, playback timing, route state, or user interaction;
- a server/browser handoff is suspected but not visible from unit tests;
- you would otherwise ask the user to copy console output or describe internal state.

## Instrumentation rules

- Prefer structured fields over prose, e.g. `{ selectedId, pendingCount, route }`.
- Log boundaries and branch decisions: handler entered, fetched response, derived state, render condition, thrown error.
- Include stable correlation fields in every event when available: component/debug id, route, mode/tool, command id/action, selected ids, counts before/after, and whether a branch returned early.
- Keep hooks local to the investigation. Do not introduce a permanent generic logging framework for a one-off repro.
- Avoid secrets, passcodes, tokens, cookies, full request bodies, or large blobs. Redact or omit sensitive values.
- For noisy code paths, log only when values change or when a predicate matches.
- For interactive canvas/WebGL/Three.js bugs, instrument both wrapper and renderer layers: wrapper mount/update/dispose/state emissions, plus renderer pointer classification, raycast hit/miss, state mutation counts, redraw child counts, and reset/command branches. This separates “state was cleared” from “rendering stopped showing state.”
- For app flows where the user reports “it still behaves the same,” include an obvious visible marker in the same deployed change when safe, then verify that the live route serves the marker. This distinguishes stale-build problems from real logic bugs.

## Reusable event shape

Use short, namespaced labels such as `viewport.update-options-effect` or `3d.pointerUp.kits.route-cut-handler`. A good gather event usually includes:

```json
{
  "type": "log",
  "level": "info",
  "label": "namespace.boundary-or-branch",
  "message": "optional short human note",
  "route": "/current/path",
  "url": "https://...",
  "data": {
    "debugId": "stable-per-instance-id",
    "mode": "kits",
    "tool": "cut",
    "beforeCount": 1,
    "afterCount": 2,
    "branch": "append-success",
    "earlyReturn": false
  },
  "meta": {
    "source": "temporary gather instrumentation",
    "investigation": "short-slug"
  }
}
```

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

## Endpoint smoke test

Before sending the user to reproduce, prove ingestion works from the current environment. Use the report's absolute ingest URL when available, or combine the WebUI base URL with `ingest.path`:

```bash
python3 - <<'PY'
from urllib.request import Request, urlopen
import json
url = 'https://<webui-host>/api/gather/<report-id>/events'
token_header = 'X-Hermes-Gather-Token'
token = '<token>'
payload = json.dumps({
    'type': 'log',
    'level': 'info',
    'label': 'hermes.instrumentation-smoke-test',
    'message': 'Gather endpoint reachable before browser repro.',
    'route': '/terminal-smoke-test',
    'url': url,
    'data': {'source': 'terminal', 'ok': True},
    'meta': {'source': 'Hermes terminal'},
}).encode()
req = Request(url, data=payload, headers={'content-type': 'application/json', token_header: token}, method='POST')
with urlopen(req, timeout=30) as res:
    print(res.status)
    print(res.read().decode('utf-8', 'ignore'))
PY
```

If the smoke test fails, fix the report URL/token/base-path problem before adding more instrumentation.

## Static route/chunk verification

When a UI is served from built assets (for example UI Mode `play-config`), do not trust source edits or a local asset existing on disk. Fetch the live route and imported assets with no-cache headers, then assert the graph contains the new report id and event labels:

```bash
python3 - <<'PY'
from urllib.request import Request, urlopen
base = 'https://<host>/ui-project/<project-id>/app/'
route = base + '<app-route>'
headers = {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'User-Agent': 'HermesGatherVerify/1.0'}
html = urlopen(Request(route, headers=headers), timeout=30).read().decode('utf-8', 'ignore')
print('route bytes', len(html))
# Then fetch the index/page/dynamic chunks found in the route graph and check:
# - page chunk name appears in index
# - instrumented dynamic chunk name appears in page chunk
# - report id and labels appear in the instrumented chunk
PY
```

Record the verified chunk names in the final user update so later debugging can separate stale-runtime issues from captured runtime behavior.

## Review

- Start with `report.latestEvent` and the last few events before reading everything.
- If the report is missing expected data, tighten the hooks and run another reproduction instead of asking the user for a manual report.
- When a screenshot contradicts a supposedly successful gather report, treat the report as having an insufficient metric rather than treating the screenshot as anecdotal. Add the missing discriminator and collect a new repro before coding.
- For canvas/WebGL geometry bugs, avoid seam-only or branch-only success metrics. If the visible failure is “gray island/protrusion remains inside selected lasso,” add component-level diagnostics as well as fragment-level diagnostics: rejected host components, selected donor components, bounds/centroid, detached-original-surface status, near-plane sample counts, inside ratios, donor counts, and top fragments. A metric like `seamHostInsideFragments === 0` proves only the seam-fragment class, not full visual correctness.
- Once you understand the behavior, replace the debug hook with the actual fix or remove it entirely.

## Implementation reference

- CLI: `/home/ubuntu/cloud-terminal-data/projects/hermes-webui/scripts/hermes-gather.py`
- API helpers: `/home/ubuntu/cloud-terminal-data/projects/hermes-webui/api/gather.py`
- POST route: `/api/gather/<report-id>/events`
- Tests: `/home/ubuntu/cloud-terminal-data/projects/hermes-webui/tests/test_gather_information.py`

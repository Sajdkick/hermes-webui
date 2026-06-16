# Cut-loop gather diagnostics: evidence before fixes

Use this reference for browser/WebGL cut-loop bugs where screenshots show oscillation between too much selected, too little selected, missing protruding islands, or boundary slivers.

## Required sequence

1. Treat screenshots as visible evidence only.
2. Update the investigation report before implementation:
   - what the screenshot proves;
   - what it does not prove;
   - plausible mechanisms that would require different fixes.
3. Add diagnostic-only gather events. Do not change geometry ownership, splitter, pruning, projection, or thresholds in the same step.
4. Smoke-test gather ingestion before asking for a repro.
5. Ask the user to reproduce once and reply `done`.
6. Inspect the saved gather report directly.
7. Update the investigation report from the gathered evidence.
8. Only then implement the fix that matches the evidence.

## Avoid manual copying

If a browser diagnostic object is useful, expose it for convenience, but also POST the same data to Hermes gather:

```js
window.__MODEL_BUILDER_LAST_CUT_LOOP_DIAGNOSTIC__ = report;
sendGatherEvent('model-builder.cut-loop.final-fragment-diagnostic', report);
```

Do not ask the user to copy console output or `window.*` JSON when gather can collect it automatically.

## Diagnostic payload for boundary/sliver failures

Include enough fields to distinguish opposite root causes:

- seed fragment id and seed position;
- loop centroid, radius, frame/tolerances;
- component counts: total, candidate, donor;
- fragment counts: total, pre-prune donor, final donor, pruned;
- seam faces: face index, polyline/chord count, fragment count;
- per relevant fragment:
  - face index;
  - component index;
  - pre-prune donor;
  - final donor;
  - pruned;
  - centroid-inside;
  - inside votes;
  - sample count;
  - near-plane count;
  - inside ratio;
  - centroid;
  - bounds;
- top host fragments with inside evidence, including non-seam fragments.

## Reading the evidence

- Missing seam faces/fragments imply split/chord generation issues.
- Host fragments with strong inside evidence imply ownership/classification issues.
- Pre-prune donor fragments that become final host imply pruning issues.
- Visually interior fragments with low/zero inside evidence imply projection-frame/sample-definition issues.

## Hermes WebUI state pitfall

When inspecting reports from terminal, match the WebUI state directory used to create the report:

```bash
HERMES_WEBUI_STATE_DIR=/home/ubuntu/cloud-terminal-data/projects/.cloud-terminal/hermes-webui-state \
python3 /home/ubuntu/cloud-terminal-data/projects/hermes-webui/scripts/hermes-gather.py show REPORT_ID --json
```

Some profiles emit plugin warnings before JSON. If JSON parsing matters, read the returned `report.path` directly.

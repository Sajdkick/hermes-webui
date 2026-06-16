# Canvas/WebGL/Three.js gather checklist

Use this when a browser interaction changes visible canvas state and source/test reasoning is not enough.

## Wrapper layer

Log these at the React/Vue/Svelte/component shell boundary:

- component mount and cleanup/dispose
- dynamic import start/success/failure
- controller creation and disposal
- option/prop updates passed into the renderer
- state callbacks emitted from the renderer back to the wrapper
- user-visible tool/mode selection changes
- command ids/actions such as undo/reset/save

## Renderer layer

Log these inside the canvas/WebGL/Three.js runtime:

- runtime instance id and initial mode/tool
- asset/geometry/topology load start/success/error
- source mesh/topology reset or rebuild
- pointer down/up/move for the active tool
- tap-vs-drag classification and movement threshold
- handler routing, especially early returns
- raycast hit/miss, face/index/object id, and compact hit coordinates
- state mutation counts before/after, such as anchor count and draft point count
- close/append/select branch decisions
- redraw child counts and object/group visibility
- dispose/remount boundaries

## Report interpretation

The useful split is:

1. Input never reached the handler → inspect pointer capture, overlay, mode/tool state, tap-vs-drag threshold.
2. Handler reached but raycast missed → inspect canvas coordinates, mesh visibility, raycaster targets, camera/layer state.
3. State mutation succeeded but redraw lacks objects → inspect overlay group clearing, object disposal, material visibility/depth, render order.
4. State mutation succeeded and redraw succeeded, then state resets → inspect wrapper prop updates, controller remount/dispose, command dispatch, asset reload/reset.
5. State never increments → inspect append/close decision, errors, service helper assumptions.

Always include before/after counts and one compact sample of relevant ids/anchors so a single report can identify which split applies.

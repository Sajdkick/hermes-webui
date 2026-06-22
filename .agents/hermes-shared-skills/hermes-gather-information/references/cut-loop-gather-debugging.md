# Cut-loop gather debugging pattern

Use this reference when a canvas/WebGL lasso/cut-loop bug passes focused tests but a user screenshot or reproduction shows the live model selecting too much or too little.

## Instrument the phase that can change selection size

For mesh splitters, log each phase separately instead of only final geometry:

1. Split start: topology size, path/segment counts, side-marker face/point, guide counts.
2. Seed resolution: seed fragment id/face and total fragment/split-face counts.
3. Initial flood-fill: donor/host counts and bounds.
4. Local leak pruning: removed ids, bounds, loop centroid, seed position, donor axis, radii/limits.
5. Detached/local reinclusion: added ids, donor-axis metrics, lasso footprint metrics, donor/host bounds.
6. Final result: donor/host triangle counts, bounds, component count.

This lets you identify whether the bug is seed selection, flood-fill, pruning, detached-component reinclusion, or stale deployment.

## Two-sided failure signal

A real model-builder wolf-ear repro produced both sides of the same class of bug:

- **Too large:** the initial ear-side flood was small, but a later reinclusion step added hundreds of nearby head/face/body fragments. Fix the reinclusion constraints; do not move the seed.
- **Too small:** making reinclusion accept only truly detached original mesh islands preserved tests but extracted only the tiny seeded ear component. For lasso tools, also consider local fragments inside/near the lasso footprint, with lateral/proximal/distal limits so the patch expands locally without jumping to the body.

## Workflow lesson

After patching this class of bug, ask the user to reproduce the exact interaction again while gather hooks remain active. Do not declare completion from synthetic tests alone; the next report should show whether donor counts are balanced, still tiny, or jumping after a specific phase.

## Test guard

Browser gather helpers in app code should no-op under Jest/jsdom, e.g. `NODE_ENV === 'test'`, missing `window`, or missing `fetch`, so instrumentation does not affect focused unit tests.
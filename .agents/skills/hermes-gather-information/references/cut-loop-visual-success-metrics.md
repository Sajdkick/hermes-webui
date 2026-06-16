# Cut-loop visual success metrics and gather blind spots

Use this reference when a canvas/WebGL lasso/cut report appears successful but the user points to a screenshot showing remaining gray/host geometry inside the lasso.

## Lesson

A gather metric can be true and still insufficient. In the wolf-ear/model-builder session, `seamHostInsideFragments === 0` correctly proved that centroid-inside seam fragments had been recovered, but it did not prove the full visible donor region was selected. The screenshot still showed a raised/protruding island inside the lasso remaining gray while the surrounding patch was orange.

## Failure mode

Do not equate a seam-fragment metric with whole-cut correctness:

```text
seamHostInsideFragments: 0  // only seam-face fragment class cleared
```

This does not cover:

- detached or raised original-surface components;
- non-seam components inside the visual lasso;
- components that fail a loop-plane/near-plane gate;
- candidates below the projected inside-ratio threshold;
- render/overlay mismatches where ownership and visible fill diverge.

## Diagnostic shape to add before coding

Alongside fragment diagnostics, emit component-level tables:

```text
componentDiagnostics.rejectedHostComponents
componentDiagnostics.selectedDonorComponents
```

For each component include:

- component index;
- fragment count;
- pre-prune donor count;
- final donor count;
- seam fragment count;
- detached-original-surface status;
- inside votes;
- sample count;
- near-plane count;
- inside ratio;
- centroid-inside fragment count;
- bounds;
- centroid;
- top fragment summaries.

## Review discipline

When the user says “not fixed, look at the screenshot,” first document how the prior report could miss the visible failure. Then add the missing diagnostic-only discriminator and collect one new repro. Do not jump directly from the screenshot to another ownership heuristic.

# Cloud Terminal Runtime to Hermes Runtime Skill Migration

## When this applies

Use this reference when cleaning up old Cloud Terminal-era runtime guidance or deciding whether a Hermes runtime skill should be kept.

## Session lesson

A Summons UI/runtime bug was solved with `hermes-gather-information`, manual build/start commands, browser inspection, and targeted tests. That proved managed Hermes runtime is useful but not mandatory for every runtime/UI investigation.

The durable policy is:

1. Keep the runtime skill as a class-level umbrella for managed Play/inspect/review workflows.
2. Rename Cloud Terminal-era runtime guidance to Hermes runtime guidance.
3. Start runtime use with `hermes-runtime doctor --json`.
4. In a Hermes WebUI-launched project session, missing runtime bridge env is a WebUI runtime-context injection gap that should be reported and fixed.
5. Until the bridge is available, fall back to project docs, terminal/browser tools, and `hermes-gather-information`.
6. Do not claim managed runtime verification unless a runtime command actually succeeded.

## Cleanup checklist

- Search active skill roots for legacy Cloud Terminal runtime command/name references.
- Replace command examples with `hermes-runtime ... --json` where managed runtime is still the intended path.
- Reframe missing runtime context as a WebUI integration gap for WebUI-launched agents, not as normal optional behavior.
- Prefer `hermes-gather-information` for temporary instrumentation and user-driven repro evidence.
- Keep historical notes only when they explain migration context and do not instruct future agents to run legacy commands.
- Verify the Hermes runtime skill resolves and the old runtime skill name no longer does.

## Why keep Hermes runtime

Keep it for capabilities that ordinary terminal/browser/gather workflows do not fully replace:

- managed Play lifecycle/status/logs;
- project-aware inspect URLs;
- authenticated or persistent inspect browser sessions;
- scripted inspect action bundles;
- screenshot/media/canvas capture through the managed bridge;
- inspect guides/scenarios/adapters;
- user image/live review request flows.

Use direct terminal/browser/gather instead when those managed capabilities are unnecessary or unavailable.

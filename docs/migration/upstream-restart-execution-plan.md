# Upstream Restart Execution Plan

Last updated: 2026-05-03

## Purpose

This document is the handoff plan for restarting the Cloud Terminal to Hermes Web UI migration from a clean branch based on the latest upstream Hermes Web UI.

The previous fork proved that many of the desired Cloud Terminal features can work inside Hermes Web UI. It did not prove that the code shape keeps future upstream updates cheap. The restart goal is different:

> Rebuild the highest-value Cloud Terminal features on top of latest upstream Hermes Web UI while keeping future upstream merges cheap, predictable, and mostly mechanical.

The current legacy fork is a reference implementation and behavior catalog. It is not the code shape to copy wholesale.

## Executive Summary

Start from latest `upstream/master`.

Re-port features in small vertical slices.

Keep product behavior in fork-owned modules.

Touch Hermes-owned core files only for stable hooks, route registration, script/style includes, and lifecycle callbacks.

Reject any approach that requires broad edits to Hermes-owned hotspots such as:

- `api/routes.py`
- `api/models.py`
- `api/streaming.py`
- `api/config.py`
- `api/profiles.py`
- `static/ui.js`
- `static/messages.js`
- `static/sessions.js`
- `static/panels.js`
- `static/boot.js`
- `static/index.html`
- `static/style.css`

If a feature needs large edits there, stop and design a smaller extension point first.

## Primary Goal

Make future upstream Hermes Web UI updates cheap enough that taking them remains worth it.

Success means:

- upstream changes can be merged regularly,
- most merge conflicts are in fork-owned files,
- conflicts in Hermes-owned files are rare, small, and mechanical,
- new upstream features can usually be adopted instead of reimplemented,
- fork features do not require reshaping upstream core files.

## Non-Goals

- Do not build a generic multi-agent abstraction layer unless it directly reduces upstream merge pain.
- Do not port every previous feature at once.
- Do not copy old fork files wholesale into latest upstream.
- Do not replace upstream tests with source-shape assertions tied to the legacy fork.
- Do not fork large upstream files just because the previous branch already did.

## Definitions

- `Upstream-owned file`: a Hermes Web UI file that upstream maintainers are likely to change.
- `Fork-owned file`: a file created for this product layer and not expected to exist upstream.
- `Hook`: a tiny, stable call from upstream-owned code into fork-owned code.
- `Registration`: adding a route module, script, style, menu item, or callback without moving product behavior into the upstream-owned file.
- `Sidecar`: fork-owned persistence linked to Hermes sessions but not stored inside core Hermes session JSON.
- `Resolver-ready`: a future merge resolver can follow documented local rules without rediscovering product architecture.

## Hard Rules

### Rule 1: Upstream Files Stay Upstream-Shaped

Allowed examples:

- import and register a fork route module from `api/routes.py`,
- include a fork entrypoint script from `static/index.html`,
- call one narrow stream hook from a stable completion point,
- expose one `data-*` mount point for a fork dashboard.

Rejected examples:

- moving route bodies into `api/routes.py`,
- replacing the upstream stream runner,
- storing fork workflow fields directly in `api/models.py`,
- rebuilding upstream session list behavior inside `static/sessions.js`,
- replacing upstream message rendering in `static/messages.js`.

### Rule 2: Product Behavior Lives In Fork-Owned Modules

Preferred backend locations:

- `api/ops_*.py`
- `api/routes_ops_*.py`
- `api/fork_*.py`
- `api/session_sidecars.py`
- `api/stream_hooks.py`

Preferred frontend locations:

- `static/ops-*.js`
- `static/cloud-terminal-*.js`
- `static/readable-output-ui.js`
- `static/play-*.js`

### Rule 3: The Seam Is Not A Giant Bridge

Do not recreate the previous broad bridge layer.

A seam is acceptable only when both are true:

- upstream-owned code needs a stable hook into fork behavior,
- the seam is smaller than directly editing the upstream-owned file.

Prefer explicit modules and narrow hooks over a universal interface.

### Rule 4: Sidecars Own Fork Metadata

Do not store fork workflow identity in core Hermes session JSON.

Fork-owned linkage belongs in sidecars:

- project id,
- task id,
- run id,
- upstream-sync record key,
- readable-output references,
- Play linkage,
- Cloud Terminal compatibility ids.

### Rule 5: Behavior Tests Beat Source-Shape Tests

Favor route behavior, UI behavior, persistence behavior, and merge-surface budgets over tests that assert exact line placement in core files.

## Architecture Target

### Backend Shape

Preferred shape:

```text
api/
  routes.py
  routes_ops_projects.py
  routes_ops_runs.py
  routes_ops_runtime.py
  routes_ops_play.py
  routes_readable_output.py
  ops_projects.py
  ops_runs.py
  ops_runtime_tools.py
  play_pipeline.py
  session_sidecars.py
  stream_hooks.py
```

### Frontend Shape

Preferred shape:

```text
static/
  index.html
  cloud-terminal-entry.js
  ops-dashboard-shell.js
  ops-projects.js
  ops-tasks.js
  ops-runs.js
  ops-notifications.js
  readable-output-ui.js
  play-inspect-shell.js
  cloud-terminal.css
```

### Persistence Shape

Preferred persistence:

```text
<state-dir>/
  ops/
    projects.json
    runs.json
    notifications.json
    artifacts/
    readable-output/
    session-links/
```

## Phase Plan

### Phase 0: Baseline And Guardrails

Goal: create the clean branch and add only guardrails.

Tasks:

- create restart branch from latest upstream,
- add this document,
- add a short `docs/migration/restart-progress.md`,
- add a guardrail test or script that reports edits to upstream-owned hotspots,
- run upstream baseline tests that are practical in the environment.

Acceptance criteria:

- branch is based on latest upstream,
- no product feature has been ported yet,
- guardrails can report hotspot churn.

### Phase 1: Extension Skeleton

Goal: prove fork code can mount without reshaping Hermes.

Tasks:

- add backend fork route registration with a tiny hook,
- add frontend fork entrypoint with a tiny script/style include,
- add empty dashboard shell route/page,
- add fork CSS file,
- add smoke tests for route and UI asset presence.

### Phase 2: Projects And Tasks

Goal: port project/task CRUD and dashboard display without agent/session coupling.

Do not port yet:

- session launch,
- task execution,
- Play,
- runtime tools,
- notifications.

### Phase 3: Sidecar Session Linkage

Goal: link Hermes sessions to fork tasks without changing Hermes session semantics.

### Phase 4: Session Launch And Resume

Goal: start and resume Hermes sessions from tasks through small hooks.

### Phase 5: Readable Output

Goal: port readable-output support with minimal stream/session hooks.

### Phase 6: Notifications, Approval, And Clarify

Goal: port user-facing workflow notifications without taking over upstream streaming.

### Phase 7: Runtime Tools And Play

Goal: port runtime inspect/gather/review and Play as fork-owned product features.

### Phase 8: Profiles, Models, And Upstream Sync

Goal: port only the profile/model conveniences that are still valuable after reviewing latest upstream.

### Phase 9: Parity Audit

Goal: compare old fork, new fork, and upstream and decide what remains ported, replaced, deferred, or dropped.

## Merge Rehearsal Protocol

After each phase:

```bash
git fetch upstream
git switch -c tmp/rehearse-upstream-merge HEAD
git merge --no-edit upstream/master
```

Then record:

- conflict files,
- conflict count,
- time to resolve,
- whether conflicts were mechanical,
- which upstream-owned files changed,
- verification run.

If a phase creates large conflicts in upstream-owned files, stop and fix the architecture first.

## Verification Strategy

Each phase needs focused verification.

Minimum checks:

- syntax checks for touched Python and JavaScript files,
- focused backend route tests,
- focused frontend behavior tests,
- sidecar persistence tests where applicable,
- merge rehearsal,
- `git diff --check`.

Avoid treating a huge unrelated suite as a blocker. If something practical is skipped, document it explicitly.

## Hotspot Budget

Use this as a review gate for every phase.

For each phase, report line churn in:

- `api/routes.py`
- `api/models.py`
- `api/streaming.py`
- `api/config.py`
- `api/profiles.py`
- `static/ui.js`
- `static/messages.js`
- `static/sessions.js`
- `static/panels.js`
- `static/boot.js`
- `static/index.html`
- `static/style.css`

Preferred budget:

- zero changes for most hotspots,
- under `20` lines for hooks and includes,
- under `50` lines only with written justification,
- anything larger requires architectural review before continuing.

## AI Execution Protocol

If you are an AI executing this plan:

1. Read `AGENTS.md` when available in the active workspace.
2. Read this document.
3. Read the old fork only as reference.
4. Do not copy entire old files into the new branch.
5. Work one phase at a time.
6. Before editing a hotspot file, explain why no smaller hook works.
7. After each phase, update `docs/migration/restart-progress.md`.
8. After each phase, run focused verification and merge rehearsal.
9. Stop if a feature forces broad edits to upstream-owned files.
10. Prefer dropping or deferring a feature over damaging mergeability.

## Feature Decision Matrix

| Question | If yes | If no |
| --- | --- | --- |
| Does latest upstream already provide this? | Reuse upstream and add thin integration only | Continue |
| Can it live entirely in fork-owned files? | Port it | Design a hook |
| Does it require changing core session JSON? | Use sidecar instead | Continue |
| Does it require replacing the upstream stream runner? | Design lifecycle hooks or defer | Continue |
| Does it require large edits to `api/routes.py`? | Add route-module registration instead | Continue |
| Does it require large edits to core frontend files? | Add a separate fork entrypoint/page/component | Continue |
| Is it lower value than mergeability? | Defer it | Port carefully |

## Definition Of Done

The restart effort is successful when:

- high-value fork workflows are rebuilt on latest upstream,
- upstream-owned files remain close to upstream shape,
- fork-owned features live in fork-owned modules,
- core session JSON does not own fork workflow state,
- upstream tests remain intact unless explicitly documented,
- merge rehearsal after the final phase is cheap and mostly mechanical,
- the old branch is no longer needed except as historical reference.

## Final Warning

The previous fork’s mistake was not too little abstraction. It was that abstraction came after a large direct port and then aimed at the wrong target.

This restart must optimize for upstream-merge isolation first.

If a future AI starts rebuilding a giant bridge, copying old core files, or rewriting upstream-owned files, stop and return to this document.

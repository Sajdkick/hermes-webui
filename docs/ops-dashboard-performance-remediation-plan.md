# Ops Dashboard Performance and Architecture Remediation Plan

## Purpose

This document is the implementation plan for cleaning up the Hermes WebUI Ops dashboard features that were ported from Cloud Terminal:

- main menu / Ops dashboard home;
- Active Sessions / session activity;
- notifications and approval monitoring;
- Quick Task creation and execution;
- project task session launch/resume;
- Ops runs and run enrichment;
- session sidecar/task linkage resolution;
- the boundary between Ops UI, Core API, and the Hermes runtime.

The current implementation works, but it is not cleanly layered. It uses legacy Ops compatibility surfaces, heavy polling routes, repeated global scans, and normal chat UI state as the task-runner transport. The goal is to keep the Cloud Terminal-style UX while making the implementation fast, predictable, and maintainable.

## Current diagnosis

### User-visible symptoms

- Opening the Ops dashboard/menu can feel slow.
- Active Sessions can take many seconds to load.
- Notifications can take many seconds to load and can keep polling expensive backend routes.
- Quick Task creation and `Create & run` can feel slow before Hermes has actually started useful model work.
- The UI has several places where unrelated polling can cause broad re-renders or background work.

### Measured baseline from current local state

The following timings were measured directly against the current workspace/state during the analysis pass. They are not hard pass/fail thresholds, but they show where the worst paths are.

| Operation | Observed cost |
|---|---:|
| `ops_projects.list_ops_projects()` | ~123 ms |
| `models.all_sessions()` | ~9 ms |
| `ops_runs.list_ops_runs({})` | ~9,008 ms |
| `ops_notifications.list_pending_notifications()` | ~8,856 ms |
| `session_activity.list_session_activity()` | ~10,978 ms |
| `ops_sessions.list_ops_sessions()` | ~11,087 ms |

Relevant state size at the time:

| State | Count / size |
|---|---:|
| visible sessions | 191 |
| session files | 372 |
| Ops runs | 99 |
| Ops sidecar files | 161 |
| Ops projects | 36 |
| `runs.json` | ~148 KiB |
| largest task JSON | ~289 KiB |

This state is not large enough to justify 9-16 second list/poll operations. The main issue is repeated enrichment and repeated disk/session/sidecar scans.

### Primary code paths involved

Frontend:

- `static/ops-legacy-home.js`
- `static/ops-legacy-notifications.js`
- `static/ops-legacy-projects.js`
- `static/ops-legacy-task-actions.js`
- `static/ops-legacy-runs.js`
- `static/ops-legacy-agent-bridge.js`
- normal chat/session helpers used by Quick Task:
  - `static/messages.js`
  - session loading/sidebar functions

Backend:

- `api/session_activity.py`
- `api/ops_sessions.py`
- `api/ops_notifications.py`
- `api/ops_runs.py`
- `api/ops_projects.py`
- `api/session_sidecars.py`
- `api/routes.py` (`/api/chat/start` and runtime adapter bridge)
- `api/routes_ops_sessions.py`
- existing Core API modules under `api/core_*.py`

## Target architecture

### Desired layering

```text
Ops Dashboard UI
  -> cheap dashboard summary endpoints
  -> Core/Ops project-task/session/run APIs
  -> Hermes runtime adapter
  -> persisted session/run/task state
```

The current shape is closer to:

```text
Ops Dashboard UI
  -> legacy Ops compatibility endpoints
  -> repeated full-state scans and enrichment
  -> normal chat UI state and composer injection
  -> /api/chat/start
  -> Hermes runtime
```

The remediation should move toward the first model without breaking existing compatibility routes.

### Guiding principles

1. **Read routes should read.** Poll/list endpoints must not trigger lifecycle side effects such as Play handoff or hidden run reconciliation.
2. **List routes should be cheap.** Summary endpoints must not perform detail-level enrichment for every row.
3. **Build indexes once per request.** Do not call `all_sessions()`, sidecar scans, task JSON reads, or run enrichment hundreds of times in a single request.
4. **Quick Task should be server-owned.** Creating a task and starting Hermes should be one structured backend operation, not a frontend sequence that mutates normal chat UI state.
5. **Goal mode should be structured.** Do not start goal tasks by prefixing `/goal` into composer text.
6. **Keep compatibility while migrating.** Existing `/api/ops/...` routes can wrap new cheap/core paths while frontend consumers migrate gradually.
7. **Make performance testable.** Add focused regression tests for call counts, no-fallback behavior, dedupe behavior, and no-overlap polling.

## Phase 0 — Establish safety rails and repeatable benchmarks

### Goals

- Create repeatable measurements before changing behavior.
- Add tests around current expected semantics so performance work does not break task/session lifecycle behavior.

### Tasks

- [ ] Add a lightweight benchmark/debug script under `scripts/` or `tools/` that times:
  - `ops_projects.list_ops_projects()`;
  - `ops_runs.list_ops_runs({})`;
  - `ops_notifications.list_pending_notifications()`;
  - `session_activity.list_session_activity()`;
  - `ops_sessions.list_ops_sessions()`.
- [ ] Include counts in the benchmark output:
  - project count;
  - run count;
  - visible session count;
  - sidecar count;
  - task-file count and total task-file bytes.
- [ ] Add or extend unit tests that lock down existing semantics:
  - existing task launch can resume/dedupe when no force-new flag is supplied;
  - create-and-run Quick Task can request a fresh session;
  - Ops run creation remains idempotent by `sessionId`;
  - linked task/session metadata remains visible in the project detail view.
- [ ] Add test fixtures for a medium-sized Ops state:
  - multiple projects;
  - dozens of runs;
  - multiple sidecars per task;
  - archived and active sessions;
  - at least one pending approval/clarify request.

### Acceptance criteria

- A developer can run one command to print before/after timings.
- Existing task/session dedupe behavior is covered before optimizing it.
- No production behavior changes in this phase except optional debug tooling.

## Phase 1 — Stop expensive polling and menu-open work

This is the highest-impact phase. It should make the dashboard feel substantially faster before deeper refactors.

### 1. Make session activity truly lean

Current issue:

`api/session_activity.py` can use a lean source, but if the lean source returns no sessions it falls back to `ops_sessions.list_ops_sessions()`, which can cost 10+ seconds.

Plan:

- [ ] Change `session_activity.list_session_activity()` so an empty lean result is considered a valid response.
- [ ] Only fall back to `ops_sessions.list_ops_sessions()` when:
  - the lean source raises an exception; or
  - an explicit compatibility/debug flag is supplied.
- [ ] Add a regression test where the lean source returns zero sessions and `ops_sessions.list_ops_sessions()` must not be called.
- [ ] Add a regression test where the lean source fails and fallback behavior still works.

Acceptance criteria:

- `/api/sessions/activity` returns quickly when there are no active sessions.
- Active Sessions polling never pays full Ops session enrichment just to show an empty list.

### 2. Add notification polling in-flight protection

Current issue:

Notification polling runs every 5 seconds, while the route can take ~9 seconds. Requests can overlap.

Plan:

- [ ] Add `OPS.notificationPollBusy` or equivalent in `static/ops-legacy-notifications.js`.
- [ ] Make the interval callback skip polling if a previous poll is still running.
- [ ] Add stale/error handling so a rejected request clears the busy flag.
- [ ] Add frontend tests proving overlapping polls are skipped.

Acceptance criteria:

- No more than one notification poll can be in flight per dashboard instance.
- A slow failed poll does not permanently disable polling.

### 3. Stop duplicate home-load calls

Current issue:

`loadDashboardHome()` runs `loadNotifications()`, `loadOpsRuns()`, and `loadNotificationDiagnostics()` together, but those paths can call overlapping backend routes.

Plan:

- [ ] Change dashboard home load to hydrate only the minimum critical controls first:
  - render static shell immediately;
  - load projects for the Quick Task selector;
  - render again;
  - load session activity and notifications independently in the background.
- [ ] Do not call `loadOpsRuns()` on menu home unless the visible home UI actually needs full run rows.
- [ ] Make diagnostics refresh explicit or use a cheap summary field from the notification endpoint.
- [ ] Add tests proving opening the home dashboard does not call `/api/ops/runs` more than once.

Acceptance criteria:

- Quick Task project dropdown is not blocked by session activity.
- Dashboard home can render useful controls before notifications/session activity finish.
- Opening the menu does not trigger duplicate `/api/ops/runs` scans.

## Phase 2 — Split cheap summaries from rich detail enrichment

### 1. Add cheap run summary API

Current issue:

`ops_runs.list_ops_runs()` enriches every run as though the caller opened a detail view. This includes session summaries, pending requests, readable output state, task context, and Play handoff metadata.

Plan:

- [ ] Add a cheap summary function, for example:
  - `ops_runs.list_ops_run_summaries(filters=None, limit=None)`; and/or
  - `GET /api/ops/runs/summary`;
  - optionally expose via `/api/core/runs/summary` when the Core boundary is ready for it.
- [ ] Summary rows should include only list/menu fields:
  - `id`;
  - `projectId`;
  - `taskId`;
  - `sessionId`;
  - `status`;
  - `title`;
  - `createdAt`;
  - `updatedAt`;
  - `completedAt`;
  - minimal `metadata` needed for badges.
- [ ] Summary rows must not:
  - resolve readable output;
  - inspect full task context;
  - scan all sidecars per row;
  - trigger Play handoff;
  - call rich pending request detection per row.
- [ ] Keep existing `ops_runs.list_ops_runs()` for compatibility, but migrate list/poll callers to the summary path.
- [ ] Add regression tests that summary listing does not call `_enrich_run()`.

Acceptance criteria:

- Run summary listing is proportional to raw run count and raw `runs.json` size.
- Home/menu/notification polling do not call rich run enrichment.

### 2. Move rich enrichment to detail routes

Plan:

- [ ] Keep rich `_enrich_run()` for:
  - run detail panel;
  - explicit inspect mode;
  - user-triggered refresh of a selected run.
- [ ] Add or confirm a detail endpoint:
  - `GET /api/ops/runs/{runId}`;
  - optionally `GET /api/core/runs/{runId}`.
- [ ] Make detail endpoint accept optional sections if useful:
  - `?include=readable_output,requests,task,play`.

Acceptance criteria:

- Opening a run detail still shows the rich data users expect.
- List views stay fast and detail views pay detail cost only for one run.

### 3. Make notifications cheap

Current issue:

`ops_notifications.list_pending_notifications()` calls run enrichment and project status logic. Notification listing is therefore close to as expensive as full run listing.

Plan:

- [ ] Split notification collection into cheap readers:
  - pending approval/clarify requests;
  - raw run terminal states that need user attention;
  - Play status from a cached status source;
  - dismissed notification IDs.
- [ ] Stop using `ops_runs.list_ops_runs()` from notification polling.
- [ ] Use raw runs or run summaries only.
- [ ] Add regression tests proving notification list does not call rich run enrichment.

Acceptance criteria:

- Notification list is suitable for 5-second polling.
- Notification list remains read-only.

## Phase 3 — Remove side effects from read/poll routes

Current issue:

Run enrichment and notification polling can detect completed linked task sessions and start Play pipelines. This makes read routes expensive and side-effectful.

Plan:

- [ ] Identify all side effects currently triggered by:
  - `ops_runs._enrich_run()`;
  - `ops_runs.list_ops_runs()`;
  - `ops_notifications.list_pending_notifications()`;
  - session activity polling.
- [ ] Extract side effects into an explicit reconciler, for example:
  - `ops_run_reconciler.reconcile_runs()`;
  - `ops_play_reconciler.reconcile_project(project_id)`;
  - or a background scheduled/timer path.
- [ ] Trigger reconciliation from lifecycle events where possible:
  - stream finishes;
  - run status transitions terminal;
  - task session closes;
  - explicit user refresh.
- [ ] Add idempotency guards so the same terminal run cannot start Play repeatedly.
- [ ] Add tests proving GET/list routes do not mutate run/Play state.

Acceptance criteria:

- Polling routes do not start Play, mutate runs, or write sidecar/task state.
- Play handoff still happens through an explicit event/reconcile path.
- Reconciliation remains idempotent.

## Phase 4 — Add request-scoped indexes and sidecar caches

### 1. Build request-scoped dashboard indexes

Current issue:

The same request repeatedly calls `all_sessions()`, scans sidecar JSON files, reads task files, and enriches runs.

Plan:

- [ ] Add an internal request context object, for example `OpsDashboardIndex`, containing:
  - `sessions_by_id`;
  - `session_alias_to_current_id`;
  - `sidecars_by_session_id`;
  - `sidecars_by_project_id`;
  - `sidecars_by_project_task`;
  - `raw_runs_by_id`;
  - `raw_runs_by_session_id`;
  - `projects_by_id`;
  - `task_data_by_project_id` when required.
- [ ] Build the index once per backend request where rich data is needed.
- [ ] Thread the index through:
  - run enrichment;
  - rich session listing;
  - notification diagnostics;
  - project detail enrichment.
- [ ] Add tests with monkeypatched counters proving repeated calls are eliminated.

Acceptance criteria:

- A rich request calls `all_sessions()` at most once.
- A rich request scans sidecars at most once.
- Task data is read once per project per request, not once per run/session row.

### 2. Persist or cache sidecar indexes

Current issue:

`list_project_linkage_records(project_id)` scans every sidecar file, and `get_session_linkage()` can recursively resolve summaries.

Plan:

- [ ] Add an mtime-invalidated in-memory sidecar index, or persist an index file such as:
  - `ops/session-links-index.json`.
- [ ] Index dimensions:
  - by direct session ID;
  - by canonical/current session ID;
  - by project ID;
  - by `(projectId, taskId)`;
  - by run ID if useful.
- [ ] Update the index whenever sidecars are created, updated, archived, or removed.
- [ ] Fall back to a full rebuild if the index is missing or stale.
- [ ] Add corruption recovery tests.

Acceptance criteria:

- Project linkage lookup is O(linkages for project), not O(all sidecars).
- Task linkage lookup is O(linkages for task), not O(all sidecars x session resolution).

### 3. Cache project/task summary data

Plan:

- [ ] Cache task counts and branch metadata used by `list_ops_projects()`.
- [ ] Avoid repeated git calls for current branch/task branch in a single request.
- [ ] Add a cheap project-list mode for menu dropdowns:
  - `id`;
  - name;
  - path/workspace;
  - profile;
  - archived flag.
- [ ] Load heavy task counts only in Projects or project-detail views.

Acceptance criteria:

- Quick Task project dropdown does not require every task file and git state to be fully inspected.
- Project detail still gets accurate full task data.

## Phase 5 — Replace frontend Quick Task orchestration with a backend operation

### Current issue

Quick Task create-and-run currently performs a long frontend sequence:

1. ensure/create Quick tasks epic;
2. create task;
3. launch task session;
4. refresh active sessions through `/api/ops/sessions`;
5. create/update Ops run records;
6. load the session into normal chat UI state;
7. inject prompt text into the composer;
8. call `sendTurn()`;
9. create/update run records again;
10. re-render session list and dashboard panels.

This is fragile and slow.

### Target endpoint

Add a structured endpoint such as:

```text
POST /api/ops/projects/{projectId}/quick-task/run
```

or, after Core boundary review:

```text
POST /api/core/projects/{projectId}/quick-task/run
```

Example request:

```json
{
  "text": "Implement the deployment status card",
  "goalMode": false,
  "attachments": [],
  "profile": "hermes",
  "model": "...",
  "model_provider": "...",
  "forceNewSession": true
}
```

Example response:

```json
{
  "ok": true,
  "project": {},
  "epic": {},
  "task": {},
  "session": {
    "sessionId": "...",
    "sessionKey": "...",
    "workspace": "..."
  },
  "run": {
    "id": "...",
    "status": "running"
  },
  "streamId": "...",
  "sessionUrl": "/session/..."
}
```

### Backend behavior

- [ ] Validate project ID and profile ownership.
- [ ] Ensure/create the `Quick tasks` epic using a narrow path.
- [ ] Create the task and return the new task payload.
- [ ] Create a fresh task session when `forceNewSession` is true.
- [ ] Create or reuse an Ops run exactly once.
- [ ] Build the task prompt server-side.
- [ ] Start Hermes through a runtime adapter or `_start_chat_stream_for_session()` delegate.
- [ ] Treat `goalMode` as a structured option, not as `/goal` text injection.
- [ ] Return enough information for the frontend to update local state without global refresh.

### Frontend behavior

- [ ] Replace `createQuickTask()` + `executeTaskMatch()` composer path for new Quick Tasks with the new endpoint.
- [ ] Optimistically insert returned project/task/session/run data into `OPS` state.
- [ ] Do not call full `refreshOpsSessions()` before starting the run.
- [ ] Open inspect mode using the returned session/run if requested.
- [ ] Keep old execute/resume path for existing tasks until a separate endpoint covers it.

### Tests

- [ ] Quick Task `Create` creates a task without starting Hermes.
- [ ] Quick Task `Create & run` calls the new endpoint once.
- [ ] `Create & run` does not mutate the chat composer.
- [ ] `Create & run` does not call `/api/ops/sessions` before startup.
- [ ] `goalMode=true` is sent as structured metadata.
- [ ] Existing task execution still dedupes/resumes unless `forceNewSession` is true.

Acceptance criteria:

- Quick Task startup is one backend operation from the UI perspective.
- The normal chat composer is no longer part of the task runner transport.
- Run creation is not duplicated by frontend/backend races.

## Phase 6 — Introduce a Hermes runtime adapter for Ops/Core task starts

Current issue:

Ops starts Hermes by going through normal `/api/chat/start` semantics and chat UI state. The backend route already has a `LegacyJournalRuntimeAdapter`, but Ops does not yet have a clean task-runner-facing runtime abstraction.

Plan:

- [ ] Define a runtime start contract, for example:

```py
@dataclass
class OpsTaskRunRequest:
    session_id: str
    project_id: str
    task_id: str
    message: str
    workspace: str
    profile: str | None
    model: str | None
    model_provider: str | None
    attachments: list[dict]
    goal_mode: bool = False
    source: str = "ops-quick-task"
```

- [ ] Implement a server-side adapter that can:
  - validate session/profile/workspace;
  - persist pending message state;
  - create stream channel;
  - start `_run_agent_streaming` or the newer runtime adapter path;
  - attach Ops run metadata.
- [ ] Keep `/api/chat/start` as the normal chat route.
- [ ] Use the adapter from Quick Task and future project task execution endpoints.
- [ ] Add tests for profile preservation and project-owned session semantics.

Acceptance criteria:

- Ops task execution does not depend on DOM/global chat state.
- Chat and Ops can share lower-level runtime code without sharing UI orchestration.

## Phase 7 — Align with the Core API boundary

Current issue:

The repository now has a documented Core API boundary, but the Ops dashboard still relies heavily on `ops-legacy-*` frontend modules and `/api/ops/...` compatibility routes.

Plan:

- [ ] Classify each new/updated endpoint as one of:
  - Core API;
  - Ops compatibility wrapper;
  - shell/UI-only route.
- [ ] Prefer Core for shell-neutral operations:
  - project registry summary;
  - task create/update;
  - run summary/detail;
  - session activity summary;
  - deployment/provider capability metadata.
- [ ] Keep Ops wrappers where they preserve legacy route shape or UI-specific presentation.
- [ ] Document any route movement in:
  - `docs/core-api-contract.md` if Core-facing;
  - this plan or a follow-up migration note if Ops-only.
- [ ] Add tests verifying old `/api/ops/...` routes still work while the frontend migrates.

Acceptance criteria:

- New performance-sensitive flows are not added only to legacy compatibility layers.
- The Core boundary remains shell-neutral and does not absorb chat UI behavior.

## Phase 8 — Frontend component and render cleanup

Current issue:

`renderHome()` owns notifications, Quick Task, session overview, diagnostics, and navigation, and many background refreshes can rerender the whole panel.

Plan:

- [ ] Split home rendering into independent panel renderers:
  - menu shell/navigation;
  - notifications panel;
  - Quick Task panel;
  - session activity panel.
- [ ] Keep Quick Task textarea/select stable during notification/session refresh.
- [ ] Update only the panel whose data changed.
- [ ] Preserve focus/selection without needing broad re-render recovery.
- [ ] Use stale-while-revalidate behavior:
  - render cached panel data immediately;
  - show subtle loading state per panel;
  - update panel when background data arrives.
- [ ] Add frontend tests for focus preservation while polling updates arrive.

Acceptance criteria:

- Notification polling does not rewrite the Quick Task form.
- Session activity polling does not rewrite the notification panel.
- Main menu remains interactive while background panels load.

## Phase 9 — Cleanup and deprecation

Plan:

- [ ] Remove no-longer-used duplicate frontend run creation calls after backend Quick Task start owns run lifecycle.
- [ ] Retire or narrow `refreshOpsSessions()` calls that use the rich `/api/ops/sessions` route.
- [ ] Rename or reorganize `ops-legacy-*` modules only after behavior is stable and tested.
- [ ] Add code comments marking compatibility wrappers and Core-owned paths.
- [ ] Update docs to describe the new task/session/run architecture.

Acceptance criteria:

- The dashboard no longer depends on compatibility-only incidental behavior.
- The remaining legacy routes are documented and covered by compatibility tests.

## Suggested implementation order

1. Phase 0: benchmark and safety tests.
2. Phase 1.1: make session activity lean/no-empty-fallback.
3. Phase 1.2: add notification polling in-flight guard.
4. Phase 1.3: remove duplicate home-load calls.
5. Phase 2.1-2.3: add run summaries and cheap notifications.
6. Phase 3: move read-route side effects into reconciler.
7. Phase 4.1: request-scoped indexes.
8. Phase 4.2: sidecar index/cache.
9. Phase 5: dedicated Quick Task run endpoint.
10. Phase 6: Ops/Hermes runtime adapter cleanup.
11. Phase 7-9: Core alignment, frontend render cleanup, legacy deprecation.

The first three implementation steps should produce the fastest visible improvement with the lowest architectural risk.

## Performance targets

These targets are intentionally conservative and should be refined after Phase 0 benchmarks exist.

| Operation | Target |
|---|---:|
| dashboard shell initial render | immediate / no backend gate |
| project dropdown hydration | < 300 ms typical |
| session activity poll, no active sessions | < 100 ms typical |
| notification poll, no pending work | < 250 ms typical |
| run summary list, ~100 runs | < 250 ms typical |
| rich run detail | < 750 ms typical |
| Quick Task `Create` | < 500 ms before model work |
| Quick Task `Create & run` API response | < 1,000 ms before model work/stream startup |

## Regression test matrix

### Backend tests

- `session_activity`:
  - lean empty result does not fall back to rich Ops sessions;
  - lean failure can fall back;
  - active sessions are grouped correctly.
- `ops_runs`:
  - summary route skips `_enrich_run()`;
  - detail route still enriches requested run;
  - idempotent run creation by `sessionId` still works.
- `ops_notifications`:
  - pending notifications do not call rich run list;
  - dismissed notifications are respected;
  - important/manual requests still appear.
- `session_sidecars`:
  - sidecar index rebuilds from files;
  - index invalidates after sidecar write/remove;
  - corrupt sidecar/index recovery works.
- Quick Task endpoint:
  - creates task only;
  - creates and starts run;
  - handles `goalMode` structurally;
  - preserves profile/workspace ownership;
  - returns session/run/task payloads;
  - handles duplicate submissions safely.

### Frontend tests

- Opening Ops home:
  - renders shell immediately;
  - loads project dropdown independently;
  - does not call duplicate run/notification scans.
- Polling:
  - notification polls do not overlap;
  - failed poll clears busy flag;
  - session activity poll skips while busy.
- Quick Task:
  - `Create & run` uses new endpoint;
  - does not inject prompt into normal composer;
  - does not call full active-session refresh before start;
  - updates local state from returned payload.
- Rendering:
  - notification refresh does not steal Quick Task textarea focus;
  - session activity refresh does not reset Quick Task input/attachments.

### Integration/manual smoke tests

- Open Ops dashboard home with existing projects/runs/sessions.
- Verify Quick Task project dropdown appears quickly.
- Create a Quick Task without running it.
- Create and run a Quick Task.
- Open the returned session/inspect view.
- Verify notifications still show pending approvals/clarifications.
- Verify completed linked runs can still trigger Play through reconciler/event path.
- Verify legacy `/api/ops/...` consumers still behave.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Breaking existing task resume/dedupe behavior | Preserve old launch path for existing tasks; add explicit `forceNewSession` only for fresh Quick Tasks. |
| Notifications stop showing terminal run/Play events | Move lifecycle work to reconciler before removing enrichment side effects; test terminal run scenarios. |
| Core boundary becomes polluted with UI-specific behavior | Keep chat composer/session UI behavior outside Core; expose shell-neutral task/run/session primitives only. |
| Caches/indexes become stale | Use mtime invalidation and write-through updates; add rebuild-on-corruption fallback. |
| Performance fixes hide data inconsistencies | Keep rich detail endpoints and explicit diagnostics; add debug endpoint or script for index consistency checks. |
| Frontend migration becomes too large | Migrate one panel/path at a time behind existing bridge methods. |

## Rollout strategy

1. Land low-risk polling fixes first.
2. Land summary endpoints while keeping rich endpoints unchanged.
3. Migrate frontend consumers one at a time.
4. Add indexes behind existing function signatures where possible.
5. Introduce the new Quick Task endpoint and gate the UI path behind a small compatibility wrapper.
6. Remove old composer-based Quick Task path only after tests and manual smoke pass.
7. Keep old Ops routes as wrappers until consumers are fully migrated.

## Definition of done

This remediation is complete when:

- Ops dashboard home renders useful controls without waiting on expensive global scans.
- Active Sessions/session activity uses a lean path and no longer falls back to rich session listing on empty results.
- Notification polling is cheap, non-overlapping, and read-only.
- Run list views use summary data; rich enrichment happens only for selected/detail routes.
- Sidecar/session/task/run lookups use request-scoped or persisted indexes instead of repeated global scans.
- Quick Task `Create & run` is a single structured backend operation and no longer depends on chat composer injection.
- Goal mode is passed as structured metadata.
- Read routes have no hidden Play/run lifecycle side effects.
- Legacy compatibility routes still pass regression tests.
- Focused tests and at least one manual smoke test cover the main Cloud Terminal-style Ops workflow.

# Cloud Terminal capabilities to extract into a shared Core API

## Purpose

This document inventories the Cloud Terminal capabilities that are reusable beyond the legacy Cloud Terminal/Codex shell and should be considered for a new Hermes Core API. The goal is to separate durable runtime/product infrastructure from shell-specific UI and agent-session behavior so Cloud Terminal and Hermes can share the same project, Play, deployment, database, proxy, and inspection foundations without coupling the Hermes Python WebUI directly to the Cloud Terminal Node/Express implementation.

## Scope and source material

Reference implementation inspected from `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal`:

- `server.js` — primary Express route surface for projects, Play, deployments, database, runtime tools, sessions, and task flows.
- `proxy.js` — root proxy, target switching, managed backend lifecycle, deployment public proxy, health, and self-heal control plane.
- `src/backend/projects.js` — project registry, task JSON, Play config discovery, Git operations, activity/inode cleanup, project file helpers.
- `src/backend/deployments.js` — deployment metadata, snapshots, public paths, revisions, rollback, provider/database-mode validation.
- `src/backend/deployments/provider-registry.js` — provider lookup/capability abstraction.
- `src/backend/deployments/artifacts.js` — deployment artifact detection, portable container config, Dockerfile/.dockerignore scaffolding, env/health-check detection.
- `src/backend/deployments/providers/local-legacy.js` — compatibility provider for Cloud Terminal host/proxy deployment flow.
- `src/backend/deployments/providers/container-local.js` — portable local container provider.
- `src/backend/deployments/providers/google-cloud-run.js` — Google Cloud Run provider.
- `src/backend/database.js` — managed Postgres settings/runtime, project/deployment DB preparation, query/inspection helpers.
- `src/backend/git-utils.js` and `src/backend/github.js` — safe Git/GitHub transport helpers.
- `public/index.html` and `public/app.js` — concrete UI consumers, especially the first-class Deployments page and project/database/Play controls.

Hermes-side context inspected in `/home/ubuntu/cloud-terminal-data/projects/hermes-webui`:

- `docs/core-play-contract.md` — current Core Play extraction direction.
- `docs/CONTRACTS.md`, `ARCHITECTURE.md`, `DESIGN.md`, `docs/UIUX-GUIDE.md` — route/API and UI constraints.
- `api/core_play.py`, `api/play_pipeline.py`, `api/routes_ops_play.py`, `api/ops_runtime_tools.py` — current Python-side Play/runtime boundary.

## Executive findings

1. **The strongest Core API candidates are already service-shaped in Cloud Terminal.** Deployments, Play runtime, managed databases, project registry, Git helpers, and proxy/host control all have explicit module boundaries and HTTP route consumers.
2. **The new Core API should be a service/API boundary, not a directly shared library.** Cloud Terminal is Node/Express; Hermes WebUI is Python. Extracting contracts over HTTP/process boundaries is safer than trying to share implementation modules across runtimes.
3. **Deployments should be a first-class Core domain, not a project-page subfeature.** Cloud Terminal has a dedicated Deployments page, provider discovery, artifact/config detection, publish/update/rollback/delete operations, logs, and public proxy status. Hermes should consume the same deployment domain rather than routing a Deployments action to project detail.
4. **Play is the right first extraction slice, but it is not enough.** `api/core_play.py` currently wraps Hermes `play_pipeline`; Cloud Terminal shows adjacent concerns that need the same treatment: project config discovery, managed DB injection, logs, proxy URLs, inspect targets, failure repair hooks, and deployment reuse of build/runtime primitives.
5. **Some Cloud Terminal behavior belongs in core adapters, not core itself.** Codex native commands, Cloud Terminal-specific menu/navigation, passcode login UI, notification copy, and task-session launching should remain shell-owned while core owns neutral state/lifecycle contracts.
6. **Core must be provider-capability-driven.** Deployment providers vary materially: local legacy, local container, and Google Cloud Run support different slug, database, local port, artifact, rollback, health-check, and config capabilities. The UI should render from provider metadata, not hard-coded route assumptions.
7. **Secrets/redaction must be part of the API contract.** Database URLs, deployment env, GitHub credentials, auth files, cookies, and logs can contain sensitive values. Core responses should return redacted previews by default and require explicit privileged calls for raw material.

## Inclusion criteria for the new Core API

A Cloud Terminal capability should move into core when it is:

- **Shell-neutral:** useful to both Cloud Terminal/Codex and Hermes, and not tied to one UI page or agent provider.
- **Runtime-owned:** controls project filesystem/runtime/process/proxy/deployment/database state that should not be duplicated by each shell.
- **Contractable:** can be represented as stable request/response schemas with clear error/status semantics.
- **Observable:** exposes logs, status, progress, and recoverable failure information in a way UIs and agents can consume.
- **Safe by default:** applies path containment, credential redaction, lifecycle locks, timeout limits, and explicit destructive operations.
- **Provider/extensible:** supports adapters for local, container, cloud, and future runtimes without forcing every caller to know provider internals.

A capability should stay shell-specific when it is mostly presentation, user-notification copy, Codex/Hermes session orchestration, or product-specific UI behavior.

## Recommended Core API domains

### 1. Project registry, project metadata, and workspace identity

**Priority:** P0

**Cloud Terminal evidence**

- `src/backend/projects.js` exports `createProjectFromRepo`, `getProjectById`, `listProjects`, `serializeProject`, `serializeProjects`, `setProjectActivity`, `deleteProject`, `cleanupStaleInodes`, `getInodeSummary`, and project Play/task/file helpers.
- `server.js` routes:
  - `GET /api/projects` (`server.js:30353`)
  - `POST /api/projects` (`server.js:30879`)
  - `PATCH /api/projects/:id/activity` (`server.js:30783`)
  - `DELETE /api/projects/:id` (`server.js:30694`)
  - `POST /api/projects/inodes/cleanup` (`server.js:30663`)
  - `GET /api/projects/:id/files` (`server.js:31102`)
  - `GET /api/projects/:id/files/content` (`server.js:31153`)
  - `POST /api/projects/:id/files/content` (`server.js:31198`)
- `public/app.js` consumes `/api/projects`, `/api/projects?fast=1`, `/api/projects?includeInodes=1`, project file routes, and project activity streams.

**Why it belongs in core**

Every higher-level runtime operation starts with a project identity: filesystem path, display name, branch, repository metadata, active/inactive state, app selections, task file location, Play config path, inode/node_modules state, and cleanup semantics. Hermes and Cloud Terminal should not maintain divergent project registries.

**Recommended Core contract**

- `GET /core/projects`
- `POST /core/projects`
- `GET /core/projects/{projectId}`
- `PATCH /core/projects/{projectId}/activity`
- `DELETE /core/projects/{projectId}` with explicit cleanup/promote/detach options.
- `POST /core/projects/inodes/cleanup`
- `GET /core/projects/{projectId}/files`
- `GET/PUT /core/projects/{projectId}/files/content`

**Core-owned responsibilities**

- Project ID/path normalization.
- Workspace/project root containment.
- Active/inactive state and dependency cleanup.
- Inode/node_modules summaries.
- Project serialization schema shared by all shells.
- Safe file listing/read/write under the project root.

**Shell-owned exclusions**

- Which dashboard tab renders projects.
- Agent-session shutdown copy and notification delivery.
- Shell-specific project cards, menus, and breadcrumbs.

### 2. Git and GitHub controls

**Priority:** P0/P1

**Cloud Terminal evidence**

- `src/backend/git-utils.js` exports safe Git helpers such as authenticated clone URL handling, safe-directory retry, sanitized remote URL handling, and `runGitCommand`.
- `src/backend/github.js` exports `performGitHubRequest`.
- `src/backend/projects.js` exports `pushProjectChanges`, `syncProjectWithMain`, `getProjectGitStatus`, and GitHub remote normalization helpers.
- `server.js` routes:
  - `GET /api/github/user` (`server.js:30240`)
  - `GET /api/github/repos` (`server.js:30263`)
  - `GET /api/github/repos/:owner/:repo/branches` (`server.js:30283`)
  - `POST /api/projects/:id/push` (`server.js:31001`)
  - `POST /api/projects/:id/sync` (`server.js:31019`)
  - `GET /api/projects/:id/git-status` (`server.js:31049`)
- `public/app.js` consumes project git-status, push, and sync routes from project cards and Git controls.

**Why it belongs in core**

Repository state is not Codex-specific. Both Hermes and Cloud Terminal need safe status, sync, branch, push, and remote normalization to reason about project readiness, deployment provenance, and task branches.

**Recommended Core contract**

- `GET /core/git/github/user`
- `GET /core/git/github/repos`
- `GET /core/git/github/repos/{owner}/{repo}/branches`
- `GET /core/projects/{projectId}/git/status`
- `POST /core/projects/{projectId}/git/sync`
- `POST /core/projects/{projectId}/git/push`

**Core-owned responsibilities**

- Safe Git command execution and cwd containment.
- Sanitized remote URLs in responses.
- Explicit branch/upstream status shape.
- Authenticated GitHub request helper that never leaks tokens.
- Error taxonomy for dirty worktrees, detached HEAD, missing upstreams, auth failure, and protected branch conditions.

**Shell-owned exclusions**

- GitHub login UX.
- Prompt wording for push confirmations.
- How a shell displays dirty file summaries.

### 3. Play/build runtime lifecycle

**Priority:** P0, already started in Hermes via `api/core_play.py`

**Cloud Terminal evidence**

- `src/backend/projects.js` exports `getProjectPlayConfigFileInfo`, `getProjectPlayConfig`, `parseProjectPlayConfig`, and `resolveProjectPlayConfigPath`.
- `server.js` project routes:
  - `GET /api/projects/:id/play-config-file` (`server.js:31236`)
  - `GET /api/projects/:id/play/status` (`server.js:31248`)
  - `POST /api/projects/:id/play/start` (`server.js:31265`)
  - `POST /api/projects/:id/play/stop` (`server.js:31295`)
  - `GET /api/projects/:id/play/logs` (`server.js:31321`)
- `server.js` agent runtime routes:
  - `GET /agent/sessions/:id/runtime/play/status` (`server.js:27468`)
  - `POST /agent/sessions/:id/runtime/play/start` (`server.js:27485`)
  - `POST /agent/sessions/:id/runtime/play/stop` (`server.js:27518`)
  - `GET /agent/sessions/:id/runtime/play/logs` (`server.js:27547`)
- Hermes has `api/core_play.py`, which intentionally delegates to `api.play_pipeline` while creating a stable facade for future shared runtime extraction.

**Why it belongs in core**

Play is a runtime capability, not a UI capability. Starting a build, allocating ports, waiting for readiness, streaming logs, exposing inspect/proxy URLs, and stopping processes must be consistent across Hermes and Cloud Terminal.

**Recommended Core contract**

- `GET /core/projects/{projectId}/play/config-file`
- `GET /core/projects/{projectId}/play/config`
- `GET /core/projects/{projectId}/play/status`
- `POST /core/projects/{projectId}/play/start`
- `POST /core/projects/{projectId}/play/restart`
- `POST /core/projects/{projectId}/play/stop`
- `GET /core/projects/{projectId}/play/logs`
- `ANY /core/projects/{projectId}/play/proxy/{path}` or a proxy target descriptor consumed by a host proxy.

**Core-owned responsibilities**

- Config discovery and validation across legacy and modern locations.
- Build/start command execution.
- Process group lifecycle and cleanup.
- Port allocation/reservation and readiness checks.
- Bounded structured logs plus text rendering.
- Status schema: `idle`, `queued`, `building`, `starting`, `ready`, `failed`, `stopped`.
- Inspect URL and proxy target metadata.
- Idempotent start/restart/stop semantics.

**Shell-owned exclusions**

- Session repair handoff after build failure. Core should expose failure logs/metadata and allow a registered callback, but Hermes/Cloud Terminal should decide which session receives the repair prompt.
- UI notification keys and copy.
- Provider-specific agent session ownership.

### 4. Deployments, providers, artifacts, logs, and public proxy status

**Priority:** P0

**Cloud Terminal evidence**

- `src/backend/deployments.js` exports deployment metadata/snapshot/revision helpers: `createDeploymentRecord`, `updateDeploymentRecord`, `deleteDeploymentRecord`, `readDeployments`, `stageDeploymentSnapshot`, `promoteDeploymentSnapshot`, `storeDeploymentRevision`, `activateDeploymentRevision`, `rollbackDeploymentSnapshot`, `normalizeDeploymentProvider`, `validateDeploymentProvider`, `normalizeDeploymentDatabaseMode`, and public path helpers.
- `src/backend/deployments/provider-registry.js` exports `createDeploymentProviderRegistry` with provider lookup/list/resolve behavior.
- `src/backend/deployments/artifacts.js` exports artifact/config detection and scaffolding: `detectProjectDeploymentArtifacts`, `resolveProjectDeploymentArtifactScaffold`, `scaffoldProjectDeploymentArtifacts`, `saveProjectContainerDeploymentConfig`, `readProjectContainerDeploymentConfig`, Dockerfile health/port detection, and container config generation.
- Providers:
  - `local-legacy.js` exposes Cloud Terminal host/proxy compatibility deployment.
  - `container-local.js` exposes local portable container deployment.
  - `google-cloud-run.js` exposes Cloud Run build/deploy/update/rollback flow.
- `server.js` routes:
  - `GET /api/deployments` (`server.js:30367`)
  - `GET /api/deployments/providers` (`server.js:30380`)
  - `GET /api/deployments/public/:slug/proxy-status` (`server.js:27183`)
  - `GET /api/projects/:id/deployment/artifacts` (`server.js:30391`)
  - `POST /api/projects/:id/deployment/artifacts/scaffold` (`server.js:30411`)
  - `POST /api/projects/:id/deployment/config` (`server.js:30438`)
  - `GET /api/projects/:id/deployment/logs` (`server.js:30466`)
  - `POST /api/projects/:id/deployment` (`server.js:30511`)
  - `POST /api/projects/:id/deployment/update` (`server.js:30561`)
  - `POST /api/projects/:id/deployment/rollback` (`server.js:30604`)
  - `DELETE /api/projects/:id/deployment` (`server.js:30638`)
- `public/index.html` has a dedicated `deploymentsPage` with provider selection, artifact summary/actions, scaffold/save config buttons, slug/database mode fields, Cloud Run fields, port/range/health/env fields, preview, and publish controls.
- `public/app.js` consumes:
  - `/api/deployments/providers`
  - `/api/deployments`
  - `/api/projects/{id}/deployment/artifacts`
  - `/api/projects/{id}/deployment/artifacts/scaffold`
  - `/api/projects/{id}/deployment/config`
  - `/api/projects/{id}/deployment/logs`
  - `/api/projects/{id}/deployment`
  - `/api/projects/{id}/deployment/update`
  - `/api/projects/{id}/deployment/rollback`

**Why it belongs in core**

Deployments are project/runtime infrastructure. They require provider discovery, lifecycle state, public entry URLs, logs, build artifacts, database mode, snapshots, revisions, rollback, and proxy compatibility. None of this is inherently Codex-specific or Hermes-specific.

This is also the strongest evidence against treating Deployments as a project-detail navigation shortcut. Cloud Terminal’s working UI treats Deployments as a top-level page backed by a complete domain API.

**Recommended Core contract**

- `GET /core/deployments`
- `GET /core/deployments/providers`
- `GET /core/deployments/public/{identifier}/proxy-status`
- `GET /core/projects/{projectId}/deployment`
- `GET /core/projects/{projectId}/deployment/artifacts`
- `POST /core/projects/{projectId}/deployment/artifacts/scaffold`
- `GET /core/projects/{projectId}/deployment/config`
- `PUT /core/projects/{projectId}/deployment/config`
- `GET /core/projects/{projectId}/deployment/logs`
- `POST /core/projects/{projectId}/deployment/publish`
- `POST /core/projects/{projectId}/deployment/update`
- `POST /core/projects/{projectId}/deployment/rollback`
- `DELETE /core/projects/{projectId}/deployment`

**Core-owned responsibilities**

- Provider registry and provider capabilities.
- Deployment status/log schemas.
- Artifact and portable container config detection.
- Dockerfile/.dockerignore/container config scaffolding.
- Env file and env override normalization.
- Health-check path/timeout normalization.
- Slug/public path validation.
- Publish/update/delete/rollback lifecycle locking.
- Snapshot/revision retention.
- Deployment database-mode integration.
- Public proxy target descriptors.

**Provider capability fields that should be preserved**

Cloud Terminal’s frontend and backend already model provider differences. Core provider definitions should include at least:

- `id`, `label`, `description`
- `default`
- `requiresSlug`
- `supportsDatabaseMode`
- `usesProjectArtifacts`
- `usesPortableContainerConfig`
- `supportsLocalPortConfig`
- `supportsGoogleCloudRunConfig`
- `supportsRollback`

**Shell-owned exclusions**

- Deployment page layout and form rendering.
- Cloud Terminal-only `local-legacy` provider internals, except as a compatibility adapter during migration.
- Menu/navigation decisions.

### 5. Managed database runtime

**Priority:** P1, but needed by Play/deployment sooner if projects depend on Postgres

**Cloud Terminal evidence**

- `src/backend/database.js` exports `readSettings`, `updateSettings`, `getSettingsPayload`, `ensureDatabaseForProject`, `prepareDeploymentDatabase`, `releaseDatabaseForProject`, `testConnection`, `listTables`, `runQuery`, and `buildEnvPreview`.
- `server.js` routes:
  - `GET /api/database/settings` (`server.js:30179`)
  - `POST /api/database/settings` (`server.js:30192`)
  - `POST /api/database/test` (`server.js:30201`)
  - `GET /api/database/inspect/tables` (`server.js:30211`)
  - `POST /api/database/inspect/query` (`server.js:30225`)
- `public/app.js` consumes database settings/test/inspect routes and uses project query parameters.
- Deployment providers use database modes (`persistent`, `shared`, `empty`, `copy`) and project/deployment DB environment injection.

**Why it belongs in core**

Database lifecycle is a runtime dependency for both Play and deployments. If each shell invents its own database env injection, local Postgres lifecycle, and deployment-copy semantics, Play and deployment behavior will drift quickly.

**Recommended Core contract**

- `GET /core/database/settings`
- `PUT /core/database/settings`
- `POST /core/database/test`
- `POST /core/projects/{projectId}/database/ensure`
- `POST /core/projects/{projectId}/database/release`
- `POST /core/projects/{projectId}/deployment/database/prepare`
- `GET /core/projects/{projectId}/database/tables`
- `POST /core/projects/{projectId}/database/query` for explicitly authorized inspect/debug use only.

**Core-owned responsibilities**

- Local vs external Postgres settings.
- Managed database naming and project/deployment namespaces.
- Local Postgres process lifecycle and readiness checks.
- Connection env map generation for Play/deployment processes.
- Database-mode semantics for deployments.
- Redacted env previews.
- Optional table/query inspection with strict authorization.

**Security requirements**

- Never include raw database passwords or full connection URLs in ordinary status/list responses.
- Use redacted previews by default.
- Gate raw env/connection material behind explicit process-launch internals or privileged APIs.
- Do not write credentials into logs.

### 6. Runtime inspect, screenshots, gather reports, and guide recordings

**Priority:** P1/P2 as a separate Runtime Tools API, not the first Core Play slice

**Cloud Terminal evidence**

- `server.js` agent runtime routes include:
  - `GET /agent/sessions/:id/runtime/status` (`server.js:27460`)
  - Gather reports: create/list/latest/read/append events (`server.js:27569` through `27634`)
  - Inspect reset/request-review/request-image-review (`server.js:27676`, `27787`, `27860`)
  - Inspect guide request/list/read/update/delete (`server.js:27911` through `28068`)
  - Inspect action/script/scenario/screenshot/session routes (`server.js:28093`, `28370`, `28622`, `28645`, `28918`, `28940`)
- Hermes has `api/ops_runtime_tools.py`, which points in a similar direction for project/session runtime tool access.

**Why it belongs near core**

Visual QA, screenshots, inspect actions, reset hooks, and gather reports are valuable across shells. However, Cloud Terminal’s implementation is currently coupled to agent sessions, request-input notifications, and shell-specific review workflows. The portable part is the runtime tool substrate, not the notification flow.

**Recommended Core contract**

Split this from Play/Deployments into `core-runtime-tools`:

- `GET /core/runtime/projects/{projectId}/inspect/target`
- `POST /core/runtime/projects/{projectId}/inspect/reset`
- `POST /core/runtime/projects/{projectId}/inspect/screenshot`
- `POST /core/runtime/projects/{projectId}/inspect/action`
- `GET /core/runtime/projects/{projectId}/inspect/guides`
- `GET/PATCH/DELETE /core/runtime/projects/{projectId}/inspect/guides/{recordingId}`
- `POST /core/runtime/gather/reports`
- `GET /core/runtime/gather/reports/{reportId}`
- `POST /core/runtime/gather/reports/{reportId}/events`

**Core-owned responsibilities**

- Browser target resolution from Play/deployment status.
- Screenshot/action execution with deterministic output.
- Guide recording storage and learned-guide updates.
- Gather report file/event schema and ingest token validation.
- Redacted runtime evidence capture.

**Shell-owned exclusions**

- `request-input` notification delivery.
- Review prompt copy.
- Choosing which session receives a human review request.
- Messaging app push integration.

### 7. Proxy, host target switching, runtime health, and public routing

**Priority:** P1, high leverage but high risk

**Cloud Terminal evidence**

- `proxy.js` exposes health/control routes:
  - `GET /health`
  - `GET /health/live`
  - `GET /health/runtime`
  - `GET /control/status`
  - `POST /control/proxy/restart-force`
- `proxy.js` contains operational functions for:
  - active target state and switching (`switchTarget`, `readActiveTarget`, `writeActiveTarget`)
  - Cloud Terminal/Hermes target discovery (`dev`, `prod`, `hermes`)
  - service worker cleanup during shell switching
  - managed backend lifecycle/restart/readiness
  - deployment proxy identifier parsing and status routing
  - backend self-heal and runtime health snapshots
  - port/process diagnostics and cleanup
- `server.js` exposes `GET /api/deployments/public/:slug/proxy-status` for deployment proxy status.

**Why it belongs in core**

If Cloud Terminal and Hermes share a host, proxy routing and runtime health should not be duplicated. Deployments and Play need public URL generation and proxy target descriptors. The shell switcher also already knows about Hermes as a first-class proxy target.

**Recommended Core contract**

This should probably be a `core-host` or `host-runtime` API, not mixed into project core:

- `GET /core/host/health`
- `GET /core/host/runtime`
- `GET /core/host/targets`
- `GET /core/host/target/active`
- `POST /core/host/target/switch`
- `POST /core/host/proxy/restart`
- `GET /core/host/deployments/{identifier}/proxy-status`
- `GET /core/host/diagnostics/processes?port=...`

**Core-owned responsibilities**

- Host health and readiness snapshots.
- Active target persistence.
- Safe target switching.
- Backend startup/readiness/self-heal policy.
- Deployment and Play proxy target resolution.
- Port/process diagnostics.

**Shell-owned exclusions**

- Which shell is presented as the default home page.
- UI switcher copy.
- Shell-specific service worker cache details, unless represented as generic pre-switch cleanup hooks.

### 8. Project task files, epics, task lifecycle, and task images

**Priority:** P1/P2 depending on whether Ops tasks are part of the new shared product surface

**Cloud Terminal evidence**

- `src/backend/projects.js` exports project task operations: `listProjectTasks`, `getProjectTasksFileInfo`, `addProjectEpic`, `deleteProjectEpic`, `addProjectTask`, `updateProjectTask`, `setProjectTaskInProgress`, `setProjectTaskSession`, `setProjectTaskGrade`, `completeProjectTask`, `archiveCompletedProjectTasks`, `deleteProjectTask`, and sync-status helpers.
- `server.js` routes:
  - `GET /api/projects/:id/tasks` (`server.js:31062`)
  - `GET /api/projects/:id/tasks-file` (`server.js:31090`)
  - `POST /api/projects/:id/task-images` (`server.js:31344`)
  - `POST /api/projects/:id/epics` (`server.js:31403`)
  - `DELETE /api/projects/:id/epics/:epicId` (`server.js:31423`)
  - `POST /api/projects/:id/tasks` (`server.js:31442`)
  - `POST /api/projects/:id/tasks/:taskId/session` (`server.js:31481`)
  - `POST /api/projects/:id/tasks/:taskId/start` (`server.js:31547`)
  - `POST /api/projects/:id/tasks/:taskId/grade` (`server.js:31628`)
  - `PATCH /api/projects/:id/tasks/:taskId` (`server.js:31648`)
  - `POST /api/projects/:id/tasks/:taskId/complete` (`server.js:31714`)
  - `POST /api/projects/:id/tasks/archive-completed` (`server.js:31759`)
  - `DELETE /api/projects/:id/tasks/:taskId` (`server.js:31774`)

**Why it may belong in core**

Ops/dashboard tasks are project metadata, not necessarily Codex-specific. The task JSON source of truth, epics, task images, status transitions, and sync status should be consistent if both Cloud Terminal and Hermes edit the same projects.

**Recommended split**

Core should own task document persistence and neutral status transitions:

- `GET /core/projects/{projectId}/tasks`
- `GET /core/projects/{projectId}/tasks-file`
- `POST/PATCH/DELETE /core/projects/{projectId}/tasks/{taskId}`
- `POST/DELETE /core/projects/{projectId}/epics/{epicId}`
- `POST /core/projects/{projectId}/task-images`
- `POST /core/projects/{projectId}/tasks/archive-completed`

Shells should own agent-session launching and grading adapters:

- `POST /api/projects/:id/tasks/:taskId/session`
- `POST /api/projects/:id/tasks/:taskId/start`
- `POST /api/projects/:id/tasks/:taskId/grade`

Those may call core for task state updates, but the actual agent provider/runtime choice should stay shell-specific.

### 9. Session activity, readable output, screenshots, and audit assets

**Priority:** P2, shared contract only

**Cloud Terminal evidence**

- `server.js` routes include:
  - `GET /api/sessions` (`server.js:33495`)
  - `GET /api/sessions/activity` (`server.js:33501`)
  - activity grouping routes (`server.js:33530` through `33599`)
  - session input/refresh/file-input/native-command/takeover/audit/delete routes (`server.js:36031` through `36756`)
  - readable-output and screenshot asset routes (`server.js:36428` through `36527`)

**Why only part belongs in core**

A shared dashboard benefits from a normalized run/session activity feed and stable readable-output/screenshot asset handling. But Cloud Terminal’s sessions are Codex-oriented, while Hermes has its own session/run model and profiles. Core should not become a Codex session manager.

**Recommended Core contract**

- Shared run activity/event schema.
- Asset store contract for readable outputs and screenshots.
- Audit/event envelope fields.

**Shell-owned exclusions**

- Codex native commands.
- Session stdin/input-via-file mechanics.
- Takeover behavior.
- Provider-specific terminal/tmux process control.

### 10. Runtime timers and small host utilities

**Priority:** P2/P3

**Cloud Terminal evidence**

- `src/backend/runtime-timers.js` exists and `server.js` exposes:
  - `GET /api/runtime/timers` (`server.js:30148`)
  - `POST /api/runtime/timers` (`server.js:30159`)
- `public/app.js` consumes `/api/runtime/timers`.

**Recommendation**

Keep this as a small `core-host` supporting utility if timers are required by runtime diagnostics or UI scheduling. Do not prioritize it ahead of projects, Play, deployments, database, or proxy health.

## Capabilities that should not move into the new core API

### Cloud Terminal UI pages and navigation

Keep these shell-owned:

- `public/index.html` page structure.
- `public/app.js` rendering, event handlers, CSS class toggles, history state, and menu/dashboard decisions.
- Deployments page layout, even though its backing deployment domain should be core.

### Codex/native session mechanics

Keep shell-owned:

- `POST /api/sessions/:id/codex/native-command`.
- Terminal/tmux attachment details.
- Codex-specific command invocation and refresh behavior.
- Any prompt/copy that assumes Codex rather than Hermes.

### Authentication/login UI and passcode management

Keep outside core or isolate in a host/auth layer:

- Passcode login UI.
- Session-token cookie mechanics.
- Provider-specific credential UI.

Core can define authorization requirements and token validation hooks, but should not force one shell’s login model on all consumers.

### Personal/product features unrelated to runtime core

Keep product-specific unless explicitly adopted by Hermes:

- Todo scheduler UI.
- Workout/exercise features.
- Menu-specific quick task widgets.
- Miscellaneous Cloud Terminal-only dashboard groupings.

### Shell-specific notification and human-review flows

Keep shell-owned:

- Request-input notification copy.
- Push delivery targets.
- “Ask user to inspect” orchestration.
- Which session receives build-failure repair prompts.

Core should expose status/evidence and allow callbacks, not decide user messaging.

## Proposed extraction order

### Phase 0 — stabilize the existing Hermes Core Play facade

- Keep `api/core_play.py` as the stable Hermes call boundary.
- Stop importing `api.play_pipeline` directly from new Ops routes.
- Document exact Play status/log/config schemas in `docs/core-play-contract.md`.
- Add contract tests that assert route payloads match the facade, not implementation internals.

### Phase 1 — define a versioned Core API contract

Create a new contract document, for example `docs/core-api-contract.md`, before moving implementation:

- Shared error envelope.
- Shared status enums.
- Long-running operation shape.
- Log entry shape.
- Provider definition shape.
- Project identity shape.
- Redaction rules.
- Capability discovery endpoint.

Suggested capability discovery:

```http
GET /core/capabilities
```

Example response shape:

```json
{
  "version": 1,
  "domains": {
    "projects": { "available": true },
    "play": { "available": true },
    "deployments": { "available": true, "providers": ["container-local", "google-cloud-run"] },
    "database": { "available": true, "modes": ["local", "external"] },
    "runtimeTools": { "available": true },
    "host": { "available": true }
  }
}
```

### Phase 2 — extract project registry and safe file APIs

This is the foundation for every later domain. Migrate or wrap:

- Project list/get/create/delete/activity.
- Safe project file list/read/write.
- Inode/node_modules summaries and cleanup.
- Project serialization schema.

### Phase 3 — extract deployments read-only and artifact APIs

Start with low-risk, high-value endpoints:

- List deployments.
- List providers.
- Read deployment status.
- Detect artifacts.
- Save/read portable config.
- Scaffold artifacts.

This enables the Hermes Deployments UI to be first-class before implementing all provider lifecycle operations.

### Phase 4 — extract deployment lifecycle operations

Add publish/update/delete/rollback, provider adapters, logs, public proxy target descriptors, and revision storage. Preserve Cloud Terminal’s provider-capability model.

### Phase 5 — extract managed database runtime

Move database settings/test/ensure/release/prepare into core so Play and Deployments share env injection and database-mode semantics.

### Phase 6 — extract Git controls

Move Git/GitHub status/sync/push/branch helpers into core with strict token redaction and safe-directory handling.

### Phase 7 — extract runtime tools and host/proxy APIs

Move inspect/screenshot/gather/guide and host/proxy health/switching after project, Play, deployment, and database contracts are stable. These are more coupled to user/session flows and should be extracted behind adapters.

## Cross-cutting contract requirements

### Error envelope

Use one envelope across domains:

```json
{
  "error": "Human-readable message.",
  "code": "STABLE_MACHINE_CODE",
  "details": {},
  "retryable": false
}
```

Cloud Terminal already has useful codes such as `DEPLOYMENT_NOT_FOUND`, `DEPLOYMENT_PROVIDER_INVALID`, `DEPLOYMENT_PROVIDER_UNKNOWN`, `DEPLOYMENT_PROVIDER_CONFIG_INVALID`, `DEPLOYMENT_REVISION_NOT_FOUND`, project inode/path/dependency codes, and worktree conflict codes. Preserve and document these instead of collapsing failures into generic 500s.

### Long-running operations

Builds, deployments, project activation, database startup, and proxy restarts need a consistent operation shape:

```json
{
  "operationId": "...",
  "projectId": "...",
  "kind": "deployment.publish",
  "status": "running",
  "startedAt": "...",
  "updatedAt": "...",
  "progress": { "step": "building", "percent": 45, "message": "Building image..." },
  "result": null,
  "error": null
}
```

Support both polling and streaming (`application/x-ndjson`) for long operations. Cloud Terminal already streams project activity updates and returns structured Play/deployment logs.

### Logs

Use a shared log entry shape:

```json
{
  "at": "2026-05-26T00:00:00.000Z",
  "stage": "build",
  "stream": "stdout",
  "message": "..."
}
```

Provide both structured entries and bounded text rendering. Enforce server-side line limits.

### Redaction

Core must redact by default:

- Authorization headers.
- Cookies.
- GitHub tokens.
- Database URLs/passwords.
- Deployment env values.
- `.env` contents.
- Provider credentials.
- Log lines containing token/password/secret patterns.

### Path containment

Core file/artifact/config APIs must safe-resolve paths under the project root or core state directory. This applies to:

- Project file browser routes.
- Deployment artifact detection and scaffolding.
- Config save/load.
- Task images.
- Screenshots and readable-output assets.
- Inspect guide files.

### Provider capability negotiation

Do not let frontends infer behavior from provider names alone. Use `GET /core/deployments/providers` and capability flags to decide which fields/actions to show.

### Concurrency and idempotency

Core must serialize lifecycle operations per project where needed:

- Play start/restart/stop.
- Deployment publish/update/rollback/delete.
- Database prepare/release.
- Project delete/activity cleanup.
- Proxy target switch/restart.

Repeated stop/delete calls should be safe. Repeated publish/update should return a clear conflict or attach to the existing operation.

### Public URL/proxy contract

Play and Deployments should return proxy descriptors, not just raw URLs:

```json
{
  "publicUrl": "https://example/deploy/my-app/",
  "proxyPath": "/deploy/my-app/",
  "targetUrl": "http://127.0.0.1:12345/",
  "ready": true,
  "health": { "status": "ok", "checkedAt": "..." }
}
```

The host proxy can then route consistently for Cloud Terminal and Hermes.

## Suggested Core API domain map

| Domain | Priority | Cloud Terminal source | Core inclusion | Notes |
|---|---:|---|---|---|
| Projects/workspaces | P0 | `src/backend/projects.js`, `/api/projects` | Yes | Foundation for every other domain. |
| Safe project files | P0/P1 | `server.js` project file routes | Yes | Must enforce path containment. |
| Play/build runtime | P0 | project Play routes, Hermes `api/core_play.py` | Yes | First extraction slice already started. |
| Deployments | P0 | `src/backend/deployments*`, deployment routes, dedicated UI | Yes | Should become first-class Hermes Deployments API/UI. |
| Deployment artifacts/config | P0 | `deployments/artifacts.js` | Yes | Enables provider-neutral UI before lifecycle migration. |
| Managed database | P1 | `src/backend/database.js`, `/api/database/*` | Yes | Needed for Play/deployment parity. |
| Git/GitHub controls | P0/P1 | `git-utils.js`, `github.js`, project git routes | Yes | Core should own safe Git operations. |
| Runtime inspect/tools | P1/P2 | `/agent/sessions/:id/runtime/*` | Partial | Extract substrate; keep notifications shell-owned. |
| Host/proxy health/switching | P1 | `proxy.js` | Partial/Yes | High-risk; best as `core-host`. |
| Task files/epics | P1/P2 | project task routes | Partial | Core owns documents; shells own agent launches/grading. |
| Session activity/assets | P2 | session/readable-output routes | Partial | Shared schema/assets only. |
| Runtime timers | P2/P3 | `runtime-timers.js` | Maybe | Supporting utility, not a first slice. |
| Codex native command | Exclude | session native command route | No | Provider-specific shell behavior. |
| UI pages/navigation | Exclude | `public/*` | No | Core should expose data/actions, not layout. |
| Todo/workout/product widgets | Exclude | `server.js`, `public/app.js` | No | Product-specific unless explicitly adopted. |

## Deployments UI implication for Hermes Ops

Cloud Terminal’s Deployments implementation is not a project-detail shortcut. It has:

- top-level page identity (`deploymentsPage`),
- page-entry data loading (`showPage('deployments')` loads providers and deployments),
- provider capability discovery,
- artifact detection/scaffolding,
- portable config save,
- publish/update/rollback/delete lifecycle calls,
- log viewing,
- public URL/proxy status handling.

Hermes Ops should therefore route Deployments to a deployments view backed by the deployment domain. If the current Hermes Ops dashboard sends Deployments to project detail, that should be treated as a routing bug and not as an intended design.

## Risks

1. **Runtime mismatch risk:** Node implementation and Python Hermes runtime make shared libraries brittle. Prefer HTTP/process contracts.
2. **State migration risk:** Deployments, project metadata, database settings, and proxy active-target files already persist under Cloud Terminal state paths. Migration needs versioned readers/writers and backup paths.
3. **Secret leakage risk:** Database/env/provider/GitHub data must be redacted consistently.
4. **Proxy blast radius:** Target switching and backend self-heal can affect live sessions. Extract only after strong health/rollback tests exist.
5. **Provider drift:** If Hermes hard-codes deployment provider behavior, it will drift from Cloud Terminal. Provider metadata must be authoritative.
6. **Session ownership ambiguity:** Runtime tools currently key off Cloud Terminal sessions. Core must accept project/runtime IDs and let shells map their own sessions.
7. **Long-operation UX:** Publish/build/database/proxy operations need clear progress contracts; synchronous request/response alone will produce poor UI behavior.

## Minimum test strategy

### Contract tests

- Project serialization is stable and shell-neutral.
- Play status/log/config payloads match the documented schema.
- Deployment provider definitions include required capability flags.
- Deployment status/log/revision payloads validate across providers.
- Database settings/status payloads never expose raw secrets by default.
- Error envelopes include stable `code` where applicable.

### Route-level tests

- Project file routes reject traversal and absolute paths outside project root.
- Deployment artifact scaffold writes only expected files under project root.
- Deployment config validation rejects invalid ports, env names, and health checks.
- Deployment publish/update/rollback/delete are serialized per project.
- Database inspect/query requires authorization and project scoping.
- Proxy public deployment status works for each provider descriptor shape.

### Migration tests

- Existing Cloud Terminal deployment records can be read by the new core service.
- Existing project records preserve IDs, paths, branches, task files, and active state.
- Existing database settings load with secrets redacted in ordinary responses.
- Existing Play configs in legacy and modern locations resolve consistently.

### UI integration tests

- Deployments dashboard entry opens the deployments view, not project detail.
- Deployments view loads providers and deployments on entry.
- Provider capability flags hide/show slug, DB mode, local port, Cloud Run, rollback, and artifact fields correctly.
- Play and deployment log panels render shared log entries.

## Conclusion

Cloud Terminal already contains most of the operational substrate a Hermes Core API needs. The immediate extraction path should be:

1. stabilize Core Play,
2. define shared project and deployment contracts,
3. move deployment provider/artifact/status APIs behind core,
4. add lifecycle operations and managed database integration,
5. migrate Git/runtime-tools/proxy capabilities behind adapters.

The new core should own neutral runtime state and lifecycle operations. Cloud Terminal and Hermes should own presentation, agent-provider orchestration, user notifications, and shell-specific session behavior. This split preserves the working Cloud Terminal capabilities while making them reusable by Hermes without forcing Hermes to inherit Cloud Terminal’s legacy UI or Codex-specific session model.

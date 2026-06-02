# AI-agent implementation plan: Cloud Terminal capabilities as Hermes Core API

## How to use this document

Pass this entire document to the implementing AI agent. It is intentionally written as a task prompt, execution plan, and checklist. The agent should implement the work in small verified phases, not as a single unreviewable rewrite.

This plan is based on:

- `docs/cloud-terminal-core-api-capability-analysis.md`
- `docs/core-play-contract.md`
- `docs/CONTRACTS.md`
- `ARCHITECTURE.md`
- `CONTRIBUTING.md`
- `TESTING.md`
- `DESIGN.md`
- `README.md`
- Cloud Terminal reference repo at `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal`

Important repository note: `AGENTS.md` mentions `docs/VISION.md` and `docs/BUILDING.md`, but those files were not present in this checkout when this plan was written. If they exist when the implementing agent runs, read them before changing code. If they are still absent, do not block; record that absence in the final verification notes.

---

## Agent assignment

You are implementing the new Hermes Core API capabilities identified from Cloud Terminal. Your job is to create a durable, tested, shell-neutral core boundary in Hermes WebUI for project/runtime/deployment/database/git/proxy/inspection capabilities, using Cloud Terminal as a reference implementation only.

### Primary goals

1. Build a versioned Hermes Core API contract and implementation surface.
2. Preserve the existing Hermes WebUI architecture: Python backend, vanilla JS frontend, no build step, no framework, no bundler.
3. Make Deployments a first-class Ops dashboard destination backed by the Core API, not a shortcut to project detail.
4. Keep Cloud Terminal/Codex-specific behavior out of core.
5. Add tests and docs so future agents cannot accidentally bypass or regress the core boundary.

### Non-goals

Do not do these unless explicitly asked by the human operator:

- Do not modify the Cloud Terminal repo. Treat it as read-only reference material.
- Do not add a frontend framework, bundler, TypeScript build step, or new app shell.
- Do not move Hermes WebUI to a new web framework.
- Do not create a separate daemon in the first pass unless the human explicitly authorizes a service split.
- Do not copy Cloud Terminal JavaScript into Hermes Python verbatim.
- Do not preserve Cloud Terminal/Codex native session behavior in core.
- Do not expose raw secrets, database URLs, GitHub tokens, cookies, provider credentials, `.env` values, or unredacted logs.
- Do not change existing public route shapes unless the task explicitly calls for a migration.

---

## Overall done condition

This implementation is complete only when all of the following are true:

1. **Contract:** `docs/core-api-contract.md` exists and documents the versioned Core API domains, schemas, errors, redaction rules, operation model, and route map.
2. **Core modules:** Hermes has shell-neutral core implementation modules for these domains:
   - projects/workspaces and safe project files;
   - Play/build runtime facade;
   - deployments/providers/artifacts/config/logs/lifecycle;
   - managed database settings/runtime;
   - Git/GitHub controls;
   - runtime inspect/gather tool substrate;
   - host/proxy health descriptors;
   - task document persistence where shared;
   - session asset/activity contract where shared.
3. **Routes:** HTTP routes expose the core domains under a stable namespace, preferably `/api/core/...`, while existing Ops routes either call core or are explicitly documented as legacy wrappers.
4. **Deployments UI:** The Ops dashboard Deployments entry opens a dedicated Deployments view that loads providers and deployments. It must not route to project detail as its primary behavior.
5. **Provider model:** Deployment UI and backend behavior are driven by provider capability metadata, not hard-coded provider-name assumptions.
6. **Security:** All file APIs enforce project-root containment; all status/list/log/env responses redact secrets by default.
7. **Concurrency:** Long-running lifecycle actions are serialized or conflict-safe per project/provider where needed.
8. **Tests:** Focused unit/route/UI tests cover every implemented domain and the final full relevant suite passes.
9. **Docs:** `CHANGELOG.md`, `docs/CONTRACTS.md`, and architecture/runtime docs are updated for behavior and contract changes.
10. **Verification evidence:** The final report lists commands run, browser/runtime checks performed, any skipped checks with reasons, and remaining follow-ups.

If any item above is not true, the implementation is not done. Do not claim done early.

---

## Work style requirements

### Before editing

1. Read these files in the Hermes repo:
   - `AGENTS.md`
   - `docs/CONTRACTS.md`
   - `docs/core-play-contract.md`
   - `docs/cloud-terminal-core-api-capability-analysis.md`
   - `ARCHITECTURE.md`
   - `CONTRIBUTING.md`
   - `TESTING.md`
   - `DESIGN.md`
   - `README.md`
2. If present, also read:
   - `docs/VISION.md`
   - `docs/BUILDING.md`
3. Inspect current source before changing it:
   - `api/core_play.py`
   - `api/play_pipeline.py`
   - `api/routes_ops_play.py`
   - `api/ops_runtime_tools.py`
   - `api/routes_ops.py`
   - `static/ops-legacy-dashboard*.js`
   - `static/ops-legacy-deployments.js`
   - `static/ops-legacy-home.js`
   - existing tests under `tests/` matching `ops`, `play`, `deployment`, `runtime`, `core`.
4. Inspect Cloud Terminal reference files as needed:
   - `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/server.js`
   - `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/proxy.js`
   - `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/src/backend/projects.js`
   - `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/src/backend/deployments.js`
   - `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/src/backend/deployments/provider-registry.js`
   - `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/src/backend/deployments/artifacts.js`
   - `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/src/backend/deployments/providers/container-local.js`
   - `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/src/backend/deployments/providers/google-cloud-run.js`
   - `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/src/backend/database.js`
   - `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/src/backend/git-utils.js`
   - `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/src/backend/github.js`
   - `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/public/app.js`
   - `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/public/index.html`

### While editing

- Keep `server.py` thin. Business logic belongs in `api/` modules.
- Keep frontend changes in existing `static/*.js` modules.
- Prefer small core facades and route wrappers over rewrites.
- Preserve existing route behavior unless there is an explicit contract migration.
- Add or update tests alongside each domain implementation.
- Update docs and changelog in the same logical phase as the behavior change.
- Stop and ask the human before destructive migrations, data deletion, or credential-sensitive changes.
- If unrelated bugs are discovered, add follow-up tasks according to `AGENTS.md`; do not mix unrelated fixes into this implementation.

### Verification discipline

After every phase:

```bash
git diff --check
python3 -m py_compile <touched python files>
node --check <touched js files>
pytest -q <focused tests for the phase>
```

Before final completion:

```bash
pytest tests/ -v --timeout=60
git diff --check
```

For UI behavior, also perform a runtime/browser check. Prefer Hermes runtime bridge if available:

```bash
hermes-runtime doctor --json
hermes-runtime play start --wait --json
hermes-runtime inspect screenshot --file-name core-api-deployments-check --json
```

If `hermes-runtime doctor --json` reports missing WebUI runtime context, state that as a runtime-context injection limitation and use manual browser/browser-tool checks instead. Do not claim managed runtime verification if the bridge is unavailable.

---

## Target architecture

### Boundary pattern

Use this initial architecture:

```text
static Ops UI
  -> existing /api/ops/... routes and new /api/core/... routes
    -> api/routes_core_*.py route wrappers
      -> api/core_*.py shell-neutral facades
        -> current Hermes implementation modules and new core-owned implementation helpers
```

Do not start with a separate daemon. First make the in-process core boundary stable, tested, and documented. A future service split can move implementation behind the same contract.

### Naming convention

Prefer these module names unless the existing code strongly suggests a better local pattern:

- `api/core_contracts.py` — shared schema helpers, error envelope, redaction helpers, operation helpers.
- `api/core_projects.py` — project/workspace registry and safe project file contract.
- `api/core_play.py` — existing Play facade; extend only through stable functions.
- `api/core_deployments.py` — deployment records/status/lifecycle facade.
- `api/core_deployment_artifacts.py` — artifact/config detection and scaffolding.
- `api/core_database.py` — database settings/runtime facade.
- `api/core_git.py` — Git/GitHub facade.
- `api/core_runtime_tools.py` — inspect/gather/screenshot substrate.
- `api/core_host.py` — host/proxy health descriptors and target descriptors.
- `api/routes_core.py` — aggregate route registration if current routing patterns allow it.
- `api/routes_core_<domain>.py` — domain route wrappers if aggregate files would become too large.

### Response shape

Use a consistent error envelope for new core routes:

```json
{
  "error": "Human-readable message.",
  "code": "STABLE_MACHINE_CODE",
  "details": {},
  "retryable": false
}
```

Use direct payloads for successful reads where that matches local route style, but document exact shapes in `docs/core-api-contract.md`.

### Long-running operation shape

Use a shared shape for build/deploy/database/proxy operations:

```json
{
  "operationId": "...",
  "kind": "deployment.publish",
  "projectId": "...",
  "status": "queued|running|succeeded|failed|cancelled",
  "startedAt": "...",
  "updatedAt": "...",
  "progress": {
    "step": "building",
    "percent": null,
    "message": "..."
  },
  "result": null,
  "error": null
}
```

If a phase cannot implement persistent operations yet, return synchronous status while preserving the documented shape for future migration.

---

## Phase 0 — Baseline, inventory, and contract skeleton

### Goal

Create the implementation runway without changing behavior.

### Steps

1. Record current git state and identify pre-existing modifications. Do not overwrite unrelated changes.
2. Read all required docs and source files listed above.
3. Create `docs/core-api-contract.md` with:
   - version number;
   - domain list;
   - route namespace;
   - shared error envelope;
   - redaction rules;
   - path-containment rules;
   - operation schema;
   - log entry schema;
   - provider capability schema;
   - route map table;
   - migration notes for existing Ops routes.
4. Create `api/core_contracts.py` with minimal shared helpers:
   - `CoreAPIError` carrying `status`, `code`, `details`, `retryable`;
   - `error_payload(error)`;
   - `redact_secret_text(text)`;
   - `redact_mapping(mapping)`;
   - timestamp helper;
   - optional operation payload helper.
5. Add tests for the helper behavior.
6. Wire no broad routes yet unless a minimal `/api/core/capabilities` route is easy and low-risk.

### Done condition

- Contract document exists and matches planned domains.
- Shared helper module exists with tests.
- Existing behavior is unchanged.
- `python3 -m py_compile api/core_contracts.py` passes.
- Focused helper tests pass.

### Checklist

- [ ] Read required docs.
- [ ] Confirm `docs/VISION.md` / `docs/BUILDING.md` present or absent.
- [ ] Record git status.
- [ ] Write `docs/core-api-contract.md`.
- [ ] Add `api/core_contracts.py`.
- [ ] Add tests for errors/redaction/operation helpers.
- [ ] Run focused tests and syntax checks.

---

## Phase 1 — Core route registration and capabilities endpoint

### Goal

Add a stable route namespace for core without changing existing Ops behavior.

### Steps

1. Inspect how `api/routes.py` and `api/routes_ops.py` register current routes.
2. Add route wrappers for:
   - `GET /api/core/capabilities`
   - optionally `GET /api/core/health`
3. Response should state available domains and implementation status:

```json
{
  "version": 1,
  "domains": {
    "projects": { "available": false, "status": "planned" },
    "play": { "available": true, "status": "implemented" },
    "deployments": { "available": false, "status": "planned" },
    "database": { "available": false, "status": "planned" },
    "git": { "available": false, "status": "planned" },
    "runtimeTools": { "available": false, "status": "planned" },
    "host": { "available": false, "status": "planned" }
  }
}
```

4. Add route tests.
5. Update `docs/CONTRACTS.md` to link `docs/core-api-contract.md`.

### Done condition

- `/api/core/capabilities` returns documented JSON.
- No existing Ops route behavior changes.
- Route tests pass.

### Checklist

- [ ] Add route wrapper module or aggregate route registration.
- [ ] Add `/api/core/capabilities`.
- [ ] Add tests.
- [ ] Update docs index.
- [ ] Run syntax and focused tests.

---

## Phase 2 — Projects/workspaces and safe project files

### Goal

Move shell-neutral project identity and safe file access behind core.

### Reference evidence

Cloud Terminal:

- `src/backend/projects.js`
- `GET /api/projects`
- `POST /api/projects`
- `PATCH /api/projects/:id/activity`
- `DELETE /api/projects/:id`
- `POST /api/projects/inodes/cleanup`
- `GET /api/projects/:id/files`
- `GET/POST /api/projects/:id/files/content`

### Steps

1. Inventory current Hermes project/Ops project data structures and routes.
2. Create `api/core_projects.py` with functions such as:
   - `list_projects()`
   - `get_project(project_id)`
   - `serialize_project(project)`
   - `set_project_activity(project_id, active)`
   - `list_project_files(project_id, path="")`
   - `read_project_file(project_id, path)`
   - `write_project_file(project_id, path, content)`
3. Use existing Hermes workspace/project helpers wherever possible; do not duplicate state stores unnecessarily.
4. Enforce path containment with existing safe-resolve helpers.
5. Add routes:
   - `GET /api/core/projects`
   - `GET /api/core/projects/{projectId}`
   - `PATCH /api/core/projects/{projectId}/activity`
   - `GET /api/core/projects/{projectId}/files`
   - `GET /api/core/projects/{projectId}/files/content`
   - `PUT /api/core/projects/{projectId}/files/content`
6. If create/delete project behavior is not already well-defined in Hermes, document it as pending rather than inventing a risky migration.
7. Add tests for serialization, missing projects, path traversal rejection, read/write containment, and activity updates.

### Done condition

- Core project routes can list/get projects and safely list/read/write project files.
- Path traversal tests fail before fix and pass after fix.
- Existing workspace/project UI behavior is unchanged unless explicitly migrated.

### Checklist

- [ ] Inventory Hermes project model.
- [ ] Implement `api/core_projects.py`.
- [ ] Add routes.
- [ ] Add route/unit tests.
- [ ] Add docs route table entries.
- [ ] Run syntax and focused tests.

---

## Phase 3 — Stabilize and extend Core Play

### Goal

Ensure all Play callers route through the existing `api.core_play` boundary and align it with the broader core contract.

### Reference evidence

Hermes:

- `api/core_play.py`
- `api/play_pipeline.py`
- `api/routes_ops_play.py`
- `docs/core-play-contract.md`

Cloud Terminal:

- project Play routes under `/api/projects/:id/play/*`
- agent runtime Play routes under `/agent/sessions/:id/runtime/play/*`

### Steps

1. Search for direct imports of `api.play_pipeline` from Ops-facing modules.
2. Replace Ops-facing direct calls with `api.core_play` calls unless a test intentionally targets implementation internals.
3. Align Core Play error conversion with `api/core_contracts.py` for new `/api/core/...` routes while preserving existing Ops route error shapes.
4. Add `/api/core/projects/{projectId}/play/...` wrappers:
   - config-file;
   - config;
   - status;
   - logs;
   - start;
   - restart;
   - stop.
5. Preserve existing `/api/ops/projects/{projectId}/play/...` routes as wrappers.
6. Add tests that prove existing Ops route payloads are unchanged and new Core route payloads match contract.

### Done condition

- Ops callers use `api.core_play`.
- New Core Play routes exist and pass tests.
- Existing Ops Play tests still pass.

### Checklist

- [ ] Search direct `play_pipeline` imports.
- [ ] Route Ops callers through `core_play`.
- [ ] Add Core Play route wrappers.
- [ ] Add/extend tests.
- [ ] Update `docs/core-play-contract.md` and `docs/core-api-contract.md` if shapes changed.
- [ ] Run documented Core Play verification gate.

Suggested focused command:

```bash
python3 -m py_compile api/core_play.py api/routes_ops_play.py api/ops_runs.py api/ops_runtime_tools.py api/ops_notifications.py
pytest -q tests/test_core_play_boundary.py tests/test_ops_play_pipeline_handoff.py tests/test_upstream_restart_phase7_play.py tests/test_runtime_adapter_seam.py
```

---

## Phase 4 — Deployment provider and artifact read APIs

### Goal

Implement low-risk deployment read/config/artifact surfaces before lifecycle mutations.

### Reference evidence

Cloud Terminal:

- `src/backend/deployments.js`
- `src/backend/deployments/provider-registry.js`
- `src/backend/deployments/artifacts.js`
- `GET /api/deployments`
- `GET /api/deployments/providers`
- `GET /api/projects/:id/deployment/artifacts`
- `POST /api/projects/:id/deployment/artifacts/scaffold`
- `POST /api/projects/:id/deployment/config`

Hermes:

- `static/ops-legacy-deployments.js`
- `tests/test_ops_deployments_route.py`

### Steps

1. Create `api/core_deployments.py` for record/status/provider read operations.
2. Create `api/core_deployment_artifacts.py` for artifact/config detection and scaffolding.
3. Define provider metadata in Python with capability flags:
   - `id`
   - `label`
   - `description`
   - `default`
   - `requiresSlug`
   - `supportsDatabaseMode`
   - `usesProjectArtifacts`
   - `usesPortableContainerConfig`
   - `supportsLocalPortConfig`
   - `supportsGoogleCloudRunConfig`
   - `supportsRollback`
4. Start with providers that can be represented safely in Hermes:
   - `container-local` as the preferred portable/local provider;
   - `google-cloud-run` as configured/available but not necessarily executable unless credentials exist;
   - `local-legacy` only as a compatibility descriptor if needed.
5. Add routes:
   - `GET /api/core/deployments`
   - `GET /api/core/deployments/providers`
   - `GET /api/core/projects/{projectId}/deployment`
   - `GET /api/core/projects/{projectId}/deployment/artifacts`
   - `POST /api/core/projects/{projectId}/deployment/artifacts/scaffold`
   - `GET /api/core/projects/{projectId}/deployment/config`
   - `PUT /api/core/projects/{projectId}/deployment/config`
6. Implement artifact detection conservatively:
   - detect Dockerfile;
   - detect `.dockerignore`;
   - detect exposed port;
   - detect health check;
   - detect env files without exposing contents;
   - read/write portable deployment config under a documented safe path.
7. Add tests for provider metadata, artifact detection, config read/write, scaffolding, and traversal rejection.

### Done condition

- Core routes list providers and deployment/artifact/config info.
- Artifact scaffold writes only expected files inside the project.
- No lifecycle publish/update/delete yet unless intentionally included in the phase.

### Checklist

- [ ] Implement provider metadata.
- [ ] Implement artifact detection.
- [ ] Implement safe config read/write.
- [ ] Implement scaffold.
- [ ] Add Core routes.
- [ ] Add tests.
- [ ] Update docs.
- [ ] Run syntax and focused tests.

---

## Phase 5 — Dedicated Ops Deployments UI route/view

### Goal

Fix the Ops Deployments UX so it opens a deployments view backed by core deployment APIs.

### Reference evidence

Cloud Terminal working pattern:

- `public/index.html` has `<main class="page" id="deploymentsPage">`.
- `public/app.js` routes `viewDeploymentsBtn` to `showPage('deployments')`.
- `showPage('deployments')` loads providers and deployments.

Hermes issue:

- The current Ops Deployments entry has routed to project detail in prior inspection. Treat that as a bug.

### Steps

1. Locate the current Deployments entry handler in `static/ops-legacy-home.js` and related Ops dashboard modules.
2. Add or restore a dedicated deployments view state in the Ops dashboard shell.
3. Ensure entering the view calls the core deployment provider/list routes.
4. Render:
   - provider list/status;
   - deployment records;
   - project selector or deployment project context;
   - artifact/config summary;
   - publish/update controls only when lifecycle is implemented;
   - clear empty/loading/error states.
5. Use provider capability flags to show/hide controls.
6. Preserve existing project detail navigation for actual project-detail actions.
7. Add frontend tests or route-level/static regression tests proving Deployments no longer calls project-detail routing as its primary action.
8. If UI changes are visible, capture before/after evidence.

### Done condition

- Clicking Ops Deployments opens the deployments view.
- The view loads providers and deployments from core routes.
- It does not navigate to project detail unless the user explicitly selects a project-detail action.
- Tests cover the routing behavior.

### Checklist

- [ ] Locate existing handler.
- [ ] Add deployments view state.
- [ ] Wire provider/deployment loading.
- [ ] Render empty/loading/error states.
- [ ] Gate controls by provider capabilities.
- [ ] Add tests.
- [ ] Capture UI evidence.
- [ ] Run JS checks and focused tests.

---

## Phase 6 — Deployment lifecycle operations

### Goal

Add publish/update/logs/rollback/delete lifecycle operations behind core.

### Reference evidence

Cloud Terminal routes:

- `GET /api/projects/:id/deployment/logs`
- `POST /api/projects/:id/deployment`
- `POST /api/projects/:id/deployment/update`
- `POST /api/projects/:id/deployment/rollback`
- `DELETE /api/projects/:id/deployment`
- `GET /api/deployments/public/:slug/proxy-status`

### Steps

1. Design deployment record storage for Hermes. Use a state directory under Hermes WebUI state, not repo source.
2. Implement record normalization and validation:
   - project id;
   - provider;
   - slug/public identifier;
   - status;
   - revisions;
   - created/updated timestamps;
   - config snapshot;
   - redacted env preview;
   - logs.
3. Implement lifecycle locking per project.
4. Implement `publish` for the first safe provider. Prefer a local/container-compatible path if environment support exists; if not, implement dry-run/recorded operation and clearly mark unsupported execution.
5. Implement `update` using the same validation and lock path.
6. Implement `logs` with bounded output.
7. Implement `rollback` only for providers that advertise `supportsRollback`.
8. Implement `delete` idempotently.
9. Implement public proxy status descriptor route even if actual proxy forwarding remains host-owned.
10. Add route tests for lifecycle success, validation failures, provider unsupported failures, idempotent delete, rollback unsupported, and log bounds.

### Done condition

- Deployment lifecycle routes exist and are tested.
- Unsupported providers fail with stable error codes, not 500s.
- Logs are bounded and redacted.
- Delete/stop operations are safe to repeat.

### Checklist

- [ ] Design state storage.
- [ ] Implement normalization/validation.
- [ ] Implement per-project lifecycle locks.
- [ ] Implement publish/update/logs/delete.
- [ ] Implement rollback where supported.
- [ ] Implement proxy-status descriptor.
- [ ] Add tests for success and failure paths.
- [ ] Update UI controls and docs.

---

## Phase 7 — Managed database runtime

### Goal

Add shared database settings, inspection, and project/deployment database preparation behind core.

### Reference evidence

Cloud Terminal:

- `src/backend/database.js`
- `GET /api/database/settings`
- `POST /api/database/settings`
- `POST /api/database/test`
- `GET /api/database/inspect/tables`
- `POST /api/database/inspect/query`

### Steps

1. Create `api/core_database.py`.
2. Implement redacted settings payloads.
3. Implement settings update with validation.
4. Implement test connection with timeout and redacted errors.
5. Implement project env map generation for Play/deployment process launch internals.
6. Implement `ensure_database_for_project`, `prepare_deployment_database`, and `release_database_for_project` where safe.
7. Add inspect table/query routes only if authorization and project scoping are explicit.
8. Never return raw passwords or unredacted connection URLs in normal responses.
9. Add tests for redaction, validation, env map internals, connection failure, and query authorization.

### Done condition

- Database settings/test/preparation APIs exist and are safe by default.
- Normal responses never expose raw secrets.
- Play/deployment integration can consume database env maps internally.

### Checklist

- [ ] Implement `api/core_database.py`.
- [ ] Add redacted settings routes.
- [ ] Add connection test route.
- [ ] Add internal env map generation.
- [ ] Add project/deployment prepare/release helpers.
- [ ] Add optional inspect routes only with authorization.
- [ ] Add tests.
- [ ] Update docs.

---

## Phase 8 — Git and GitHub controls

### Goal

Expose safe, shell-neutral Git/GitHub operations behind core.

### Reference evidence

Cloud Terminal:

- `src/backend/git-utils.js`
- `src/backend/github.js`
- `GET /api/github/user`
- `GET /api/github/repos`
- `GET /api/github/repos/:owner/:repo/branches`
- `POST /api/projects/:id/push`
- `POST /api/projects/:id/sync`
- `GET /api/projects/:id/git-status`

### Steps

1. Create `api/core_git.py`.
2. Reuse existing Hermes helpers if present. Do not shell out unsafely.
3. Implement:
   - project git status;
   - sync/pull from main/upstream where configured;
   - push with explicit commit/message/ref semantics;
   - GitHub user/repos/branches if credentials are configured.
4. Sanitize remote URLs in every response.
5. Add stable errors for missing Git, missing repo, dirty worktree, auth failure, detached HEAD, no upstream, and push rejection.
6. Add tests using temporary repos and mocked GitHub responses.

### Done condition

- Core Git routes exist and return sanitized output.
- Failure modes use stable error codes.
- Tests cover common repo states.

### Checklist

- [ ] Implement `api/core_git.py`.
- [ ] Add status route.
- [ ] Add sync/push routes.
- [ ] Add GitHub routes if credential path exists.
- [ ] Add sanitization tests.
- [ ] Add temp-repo tests.
- [ ] Update docs.

---

## Phase 9 — Runtime inspect/gather tools substrate

### Goal

Extract shell-neutral runtime inspection and gather-report capabilities without absorbing shell-specific notifications.

### Reference evidence

Cloud Terminal routes under `/agent/sessions/:id/runtime/...`:

- runtime status;
- gather reports;
- inspect reset;
- inspect screenshot;
- inspect action/script/scenarios;
- inspect guide list/read/update/delete/request.

Hermes:

- `api/ops_runtime_tools.py`
- `hermes-runtime` bridge behavior.

### Steps

1. Create or extend `api/core_runtime_tools.py`.
2. Use project/runtime IDs as core identifiers. Do not require Cloud Terminal session IDs.
3. Implement substrate routes:
   - inspect target;
   - screenshot;
   - action/script where supported;
   - guide list/read/update/delete;
   - gather report create/list/read/append events.
4. Keep user-review/request-input notification delivery shell-owned.
5. Add redaction and file containment for screenshots, recordings, and reports.
6. Add tests with mocked runtime bridge where browser execution is not available.

### Done condition

- Core runtime tool routes expose project/runtime inspection primitives.
- Notification/user-review flows remain outside core.
- Tests cover storage, redaction, and route behavior.

### Checklist

- [ ] Implement core runtime identifiers.
- [ ] Add inspect/gather routes.
- [ ] Preserve shell-owned review/notification behavior.
- [ ] Add redaction/containment tests.
- [ ] Update docs.

---

## Phase 10 — Host/proxy health descriptors

### Goal

Expose host/proxy health and target descriptors without destabilizing live routing.

### Reference evidence

Cloud Terminal `proxy.js`:

- `/health`
- `/health/live`
- `/health/runtime`
- `/control/status`
- `/control/proxy/restart-force`
- active target state;
- backend readiness/self-heal;
- deployment proxy target resolution;
- port/process diagnostics.

### Steps

1. Create `api/core_host.py`.
2. Implement read-only descriptors first:
   - health;
   - active target if known;
   - Play/deployment proxy descriptors;
   - runtime process summary if available.
3. Do not implement force restart/target switch until read-only behavior is tested and the human approves mutating host controls.
4. Add route tests with mocked process/proxy state.
5. If mutating controls are later approved, add explicit authorization, confirmation semantics, and idempotent operation status.

### Done condition

- Read-only core host/proxy descriptors exist and are tested.
- No risky proxy restart/switch side effects are introduced without approval.

### Checklist

- [ ] Implement read-only host health descriptors.
- [ ] Implement proxy target descriptors for Play/deployments.
- [ ] Add mocked tests.
- [ ] Document mutating controls as future/approval-required.

---

## Phase 11 — Task documents, epics, and shared task assets

### Goal

Move neutral task document persistence behind core while keeping agent launch/grading shell-owned.

### Reference evidence

Cloud Terminal project task routes:

- tasks list/file;
- epics create/delete;
- tasks create/update/delete/complete/archive;
- task images;
- session/start/grade endpoints.

### Steps

1. Inventory current Hermes task/project task support.
2. Implement core task document functions only for shared persistence:
   - list tasks;
   - read task file info;
   - create/update/delete task;
   - create/delete epic;
   - complete/archive;
   - task images with path containment.
3. Do not move agent session launching, task grading, or execution mode into core.
4. Add tests for JSON parsing, status transitions, AI-suggestion markers when adding follow-ups, and image containment.

### Done condition

- Core can safely read/write task documents and assets.
- Agent launch/grading remains shell-owned.

### Checklist

- [ ] Inventory existing task support.
- [ ] Implement neutral task doc helpers.
- [ ] Add routes.
- [ ] Add tests.
- [ ] Update docs.

---

## Phase 12 — Session activity/readable-output/screenshot asset contract

### Goal

Define shared schemas for activity and assets without turning core into a Codex/Hermes session manager.

### Steps

1. Document shared activity and asset schemas in `docs/core-api-contract.md`.
2. Add helper module functions only if there are multiple existing consumers.
3. Keep Codex native commands, session stdin, takeover, and provider-specific stream controls out of core.
4. Ensure readable-output/screenshot assets enforce file containment and content-type safety.
5. Add tests around asset retrieval path containment and metadata shape.

### Done condition

- Shared schema is documented and, if implemented, tested.
- Provider-specific session controls remain shell-owned.

### Checklist

- [ ] Document schema.
- [ ] Implement only shared asset helpers needed by current consumers.
- [ ] Add tests.
- [ ] Update docs.

---

## Final integration pass

### Steps

1. Search for direct bypasses:

```bash
python3 - <<'PY'
from pathlib import Path
for p in Path('api').glob('*.py'):
    text = p.read_text(errors='replace')
    if 'play_pipeline' in text and p.name not in {'play_pipeline.py', 'core_play.py'}:
        print(p)
PY
```

Expand this search for each core implementation module to ensure Ops-facing code uses core facades where intended.

2. Run focused tests for every phase.
3. Run the full test suite:

```bash
pytest tests/ -v --timeout=60
```

4. Run syntax/static checks:

```bash
git diff --check
python3 -m py_compile $(git diff --name-only -- '*.py')
node --check static/ops-legacy-dashboard.js static/ops-legacy-dashboard-actions.js static/ops-legacy-dashboard-shell.js static/ops-legacy-deployments.js static/ops-legacy-home.js
```

If the shell command with `$(git diff...)` is unreliable, list touched Python files explicitly.

5. Perform UI/runtime verification:
   - Start Hermes WebUI or use the runtime bridge.
   - Open Ops dashboard.
   - Click Deployments.
   - Confirm a dedicated deployments view appears.
   - Confirm providers/deployments load.
   - Confirm project detail does not open unless explicitly requested.
   - Capture screenshot evidence.
6. Update docs:
   - `docs/core-api-contract.md`
   - `docs/core-play-contract.md` if Play changed
   - `docs/CONTRACTS.md`
   - `ARCHITECTURE.md` if module layout/runtime ownership changed
   - `TESTING.md` if verification guidance changed
   - `CHANGELOG.md` for user-visible/API changes
7. Write final implementation notes with:
   - changed files;
   - route map;
   - tests run;
   - UI evidence path;
   - skipped checks and why;
   - follow-up tasks.

### Final checklist

- [ ] No direct Ops caller bypasses core where a core facade exists.
- [ ] `/api/core/capabilities` accurately reflects implemented domains.
- [ ] Project file APIs reject traversal.
- [ ] Core Play routes and existing Ops Play routes pass tests.
- [ ] Deployment provider metadata drives UI controls.
- [ ] Ops Deployments opens the dedicated deployments view.
- [ ] Deployment artifact/config routes pass tests.
- [ ] Deployment lifecycle routes pass success/failure/idempotency tests.
- [ ] Database responses redact secrets.
- [ ] Git responses sanitize remotes and errors.
- [ ] Runtime tools/gather outputs are contained and redacted.
- [ ] Host/proxy descriptors are read-only unless mutating controls were explicitly approved.
- [ ] Docs and changelog are updated.
- [ ] Full relevant tests pass.
- [ ] UI/runtime evidence is captured.

---

## Stable route map target

This table is the target. Implement incrementally, but keep the final shape coherent.

| Domain | Route | Method | Notes |
|---|---|---:|---|
| Capabilities | `/api/core/capabilities` | GET | Version and domain availability. |
| Projects | `/api/core/projects` | GET | List serialized projects. |
| Projects | `/api/core/projects/{projectId}` | GET | Get one project. |
| Projects | `/api/core/projects/{projectId}/activity` | PATCH | Activity/active state. |
| Files | `/api/core/projects/{projectId}/files` | GET | Safe project file listing. |
| Files | `/api/core/projects/{projectId}/files/content` | GET/PUT | Safe read/write by query/body path. |
| Play | `/api/core/projects/{projectId}/play/config-file` | GET | Config metadata. |
| Play | `/api/core/projects/{projectId}/play/config` | GET | Normalized runnable config. |
| Play | `/api/core/projects/{projectId}/play/status` | GET | Current Play status. |
| Play | `/api/core/projects/{projectId}/play/logs` | GET | Bounded logs. |
| Play | `/api/core/projects/{projectId}/play/start` | POST | Start. |
| Play | `/api/core/projects/{projectId}/play/restart` | POST | Restart. |
| Play | `/api/core/projects/{projectId}/play/stop` | POST | Stop. |
| Deployments | `/api/core/deployments` | GET | List deployments. |
| Deployments | `/api/core/deployments/providers` | GET | Provider capabilities. |
| Deployments | `/api/core/deployments/public/{identifier}/proxy-status` | GET | Public proxy status descriptor. |
| Deployments | `/api/core/projects/{projectId}/deployment` | GET | Project deployment record/status. |
| Deployments | `/api/core/projects/{projectId}/deployment/artifacts` | GET | Artifact detection. |
| Deployments | `/api/core/projects/{projectId}/deployment/artifacts/scaffold` | POST | Scaffold Dockerfile/config. |
| Deployments | `/api/core/projects/{projectId}/deployment/config` | GET/PUT | Portable config. |
| Deployments | `/api/core/projects/{projectId}/deployment/logs` | GET | Bounded logs. |
| Deployments | `/api/core/projects/{projectId}/deployment/publish` | POST | Publish/create. |
| Deployments | `/api/core/projects/{projectId}/deployment/update` | POST | Update. |
| Deployments | `/api/core/projects/{projectId}/deployment/rollback` | POST | Rollback if supported. |
| Deployments | `/api/core/projects/{projectId}/deployment` | DELETE | Idempotent delete. |
| Database | `/api/core/database/settings` | GET/PUT | Redacted settings. |
| Database | `/api/core/database/test` | POST | Test connection. |
| Database | `/api/core/projects/{projectId}/database/ensure` | POST | Prepare project DB. |
| Database | `/api/core/projects/{projectId}/database/release` | POST | Release project DB. |
| Database | `/api/core/projects/{projectId}/deployment/database/prepare` | POST | Deployment DB mode prep. |
| Git | `/api/core/git/github/user` | GET | Optional GitHub identity. |
| Git | `/api/core/git/github/repos` | GET | Optional repos. |
| Git | `/api/core/git/github/repos/{owner}/{repo}/branches` | GET | Optional branches. |
| Git | `/api/core/projects/{projectId}/git/status` | GET | Sanitized status. |
| Git | `/api/core/projects/{projectId}/git/sync` | POST | Pull/sync. |
| Git | `/api/core/projects/{projectId}/git/push` | POST | Push. |
| Runtime tools | `/api/core/runtime/projects/{projectId}/inspect/target` | GET | Inspect target descriptor. |
| Runtime tools | `/api/core/runtime/projects/{projectId}/inspect/screenshot` | POST | Screenshot. |
| Runtime tools | `/api/core/runtime/projects/{projectId}/inspect/action` | POST | Scripted action. |
| Runtime tools | `/api/core/runtime/projects/{projectId}/inspect/guides` | GET | Guide list. |
| Runtime tools | `/api/core/runtime/projects/{projectId}/inspect/guides/{recordingId}` | GET/PATCH/DELETE | Guide CRUD. |
| Runtime tools | `/api/core/runtime/gather/reports` | GET/POST | Reports. |
| Runtime tools | `/api/core/runtime/gather/reports/{reportId}` | GET | One report. |
| Runtime tools | `/api/core/runtime/gather/reports/{reportId}/events` | POST | Append event. |
| Host | `/api/core/host/health` | GET | Health descriptor. |
| Host | `/api/core/host/runtime` | GET | Runtime descriptor. |
| Host | `/api/core/host/targets` | GET | Known targets if available. |
| Host | `/api/core/host/target/active` | GET | Active target if available. |

---

## Required tests to add or update

Names can vary, but cover these areas.

### Contract/helper tests

- `tests/test_core_api_contracts.py`
  - error payload;
  - redaction;
  - operation shape;
  - timestamp shape;
  - capabilities payload.

### Project/file tests

- `tests/test_core_projects.py`
  - project list/get;
  - missing project;
  - file list/read/write;
  - traversal rejection;
  - activity updates.

### Play tests

- Keep/extend:
  - `tests/test_core_play_boundary.py`
  - `tests/test_ops_play_pipeline_handoff.py`
  - `tests/test_upstream_restart_phase7_play.py`
  - `tests/test_runtime_adapter_seam.py`

### Deployment tests

- `tests/test_core_deployments.py`
  - provider metadata;
  - deployment list/status;
  - unsupported provider errors;
  - publish/update/delete/rollback routes;
  - lifecycle locking/idempotency;
  - logs bounded/redacted.

- `tests/test_core_deployment_artifacts.py`
  - Dockerfile detection;
  - port/health/env detection;
  - config read/write;
  - scaffold writes expected files only;
  - traversal rejection.

- Keep/extend:
  - `tests/test_ops_deployments_route.py`

### Database tests

- `tests/test_core_database.py`
  - settings redaction;
  - invalid settings rejection;
  - connection test mocked success/failure;
  - env map internals;
  - inspect authorization.

### Git tests

- `tests/test_core_git.py`
  - sanitized status;
  - missing repo;
  - dirty worktree;
  - sync/push mocked;
  - GitHub response/token redaction.

### Runtime tools tests

- `tests/test_core_runtime_tools.py`
  - inspect target;
  - screenshot path containment;
  - gather report lifecycle;
  - guide CRUD;
  - redaction.

### Host/proxy tests

- `tests/test_core_host.py`
  - health descriptor;
  - active target descriptor;
  - deployment/Play proxy descriptor;
  - mutating controls unavailable unless approved.

---

## Error codes to prefer

Use stable, documented codes. Add only when needed.

General:

- `CORE_INVALID_REQUEST`
- `CORE_NOT_FOUND`
- `CORE_UNSUPPORTED`
- `CORE_CONFLICT`
- `CORE_FORBIDDEN`
- `CORE_INTERNAL_ERROR`

Projects/files:

- `PROJECT_NOT_FOUND`
- `PROJECT_PATH_FORBIDDEN`
- `PROJECT_FILE_NOT_FOUND`
- `PROJECT_ACTIVITY_INVALID`

Play:

- preserve existing Play error status behavior;
- add wrapper codes only for new Core routes if needed.

Deployments:

- `DEPLOYMENT_NOT_FOUND`
- `DEPLOYMENT_PROVIDER_INVALID`
- `DEPLOYMENT_PROVIDER_UNKNOWN`
- `DEPLOYMENT_PROVIDER_UNSUPPORTED`
- `DEPLOYMENT_PROVIDER_CONFIG_INVALID`
- `DEPLOYMENT_SLUG_INVALID`
- `DEPLOYMENT_OPERATION_CONFLICT`
- `DEPLOYMENT_REVISION_NOT_FOUND`
- `DEPLOYMENT_ROLLBACK_UNSUPPORTED`

Database:

- `DATABASE_SETTINGS_INVALID`
- `DATABASE_CONNECTION_FAILED`
- `DATABASE_NOT_CONFIGURED`
- `DATABASE_QUERY_FORBIDDEN`

Git:

- `GIT_NOT_REPOSITORY`
- `GIT_COMMAND_FAILED`
- `GIT_AUTH_FAILED`
- `GIT_DIRTY_WORKTREE`
- `GIT_NO_UPSTREAM`
- `GITHUB_NOT_CONFIGURED`

Runtime tools:

- `RUNTIME_CONTEXT_UNAVAILABLE`
- `INSPECT_TARGET_UNAVAILABLE`
- `INSPECT_ACTION_FAILED`
- `GATHER_REPORT_NOT_FOUND`

Host/proxy:

- `HOST_STATUS_UNAVAILABLE`
- `PROXY_TARGET_NOT_FOUND`
- `PROXY_MUTATION_REQUIRES_APPROVAL`

---

## Security checklist

Apply this to every phase.

- [ ] No raw secrets in ordinary JSON responses.
- [ ] No raw secrets in logs, test snapshots, or docs.
- [ ] Database URLs are redacted unless used internally for process launch.
- [ ] GitHub tokens are never returned.
- [ ] Authorization headers and cookies are never returned.
- [ ] `.env` values are not returned; only keys or redacted previews.
- [ ] File paths are safe-resolved under project root or state dir.
- [ ] Uploaded/scaffolded/generated files cannot escape project root.
- [ ] Public proxy descriptors do not leak private env/config.
- [ ] Query/inspect routes require explicit authorization and project scope.
- [ ] Long-running operations redact logs before returning them to UI or agents.

---

## UI/UX checklist for Deployments

- [ ] Deployments has a dedicated Ops view/state.
- [ ] Loading state is visible and calm.
- [ ] Empty state explains no deployments exist yet.
- [ ] Error state gives actionable retry/details without raw stack dumps.
- [ ] Provider controls are capability-driven.
- [ ] Publish/update/delete/rollback buttons are disabled while operations run.
- [ ] Destructive actions require confirmation.
- [ ] Status badges are compact.
- [ ] Logs/details use progressive disclosure.
- [ ] The view works on desktop and narrow/mobile layouts where applicable.
- [ ] Before/after screenshots are captured for review.

---

## PR / final report template

Use this shape when reporting completion:

```markdown
## Thinking Path

- Cloud Terminal already contains service-shaped project, Play, deployment, database, Git, runtime-tools, and proxy capabilities.
- Hermes needs a shell-neutral Core API boundary rather than importing Cloud Terminal Node code.
- This implementation adds the boundary in phases, keeps existing Ops behavior stable, and makes Deployments first-class.

## What Changed

- Added/updated core modules: ...
- Added/updated routes: ...
- Updated Ops Deployments UI: ...
- Updated docs: ...

## Why It Matters

- Deployments no longer fall through to project detail.
- Play/deployment/database/git/runtime capabilities now have a stable shared contract.
- Future Cloud Terminal/Hermes convergence can happen through API contracts instead of duplicated shell logic.

## Verification

Commands run:

- `python3 -m py_compile ...`
- `node --check ...`
- `pytest -q ...`
- `pytest tests/ -v --timeout=60`
- runtime/browser checks: ...

UI evidence:

- screenshot path(s): ...

## Risks / Follow-ups

- ...

## Model Used

- Provider/model: ...
- Notable agent/tool use: ...
```

---

## Stop conditions

Stop and ask the human before proceeding if any of these occur:

- You need to delete or migrate real user state.
- You need to expose or inspect raw credentials.
- You need to modify the Cloud Terminal repo.
- You need to add a new long-lived daemon/service.
- You need to introduce a new framework, bundler, database, or dependency.
- Existing tests reveal broad unrelated failures that make verification ambiguous.
- The intended project/deployment/database state location is unclear.
- A provider requires external cloud credentials not present in the environment.
- A route change would break documented existing Ops behavior.

---

## Implementation priority summary

If time or context is constrained, execute in this order and stop cleanly at phase boundaries:

1. Contract skeleton and capabilities route.
2. Core Play stabilization and route wrappers.
3. Deployment provider/artifact read APIs.
4. Dedicated Ops Deployments view backed by core routes.
5. Deployment lifecycle operations.
6. Managed database integration.
7. Projects/safe files and Git, if not already required by deployments.
8. Runtime tools/gather substrate.
9. Host/proxy descriptors.
10. Task/session asset shared contracts.

Do not skip verification gates to move faster. A smaller fully verified slice is better than a large incomplete migration.

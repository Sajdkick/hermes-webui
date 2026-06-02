# Hermes Core API contract

Status: implemented in-process boundary, version `2026-05-26`.

The Hermes Core API is a shell-neutral HTTP contract for project/runtime capabilities that are useful to both the Hermes Ops dashboard and Cloud Terminal-style shells. The first implementation lives in-process under `api/core_*.py` and is routed through `/api/core/...`; it is intentionally shaped so the implementation can move behind a separate service later without changing frontend or agent clients.

## Goals

- Keep reusable runtime capabilities out of shell-specific UI modules.
- Preserve the no-build-step Python + vanilla-JS Hermes architecture.
- Expose provider/capability metadata so UIs render from contracts instead of hard-coded provider names.
- Redact secrets and enforce project-root containment by default.
- Preserve legacy Ops routes as compatibility wrappers while new shared consumers use `/api/core` directly.

## Namespace and version discovery

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/core` | `GET` | Return the public route map plus capability metadata. |
| `/api/core/capabilities` | `GET` | Return implemented Core domains and route lists. |
| `/api/core/health` | `GET` | Return host/core health using the host health facade. |
| `/api/core/host/health` | `GET` | Alias for host health. |
| `/api/core/host/proxy` | `GET` | Return host/proxy descriptors. |

The version is surfaced by `api.core_contracts.CORE_API_VERSION` and currently equals `2026-05-26`.

## Shared response rules

Successful read routes return direct domain payloads following existing Hermes API style. New Core errors use this envelope:

```json
{
  "error": "Human-readable message.",
  "code": "STABLE_MACHINE_CODE",
  "details": {},
  "retryable": false
}
```

Route wrappers should raise `CoreApiError` for expected failures. Unexpected domain exceptions are coerced into the same envelope at the route boundary.

## Security and redaction

- Core route responses must pass sensitive payloads through `redact_payload()` or a domain facade that does so.
- Text and nested JSON redaction reuse the existing Hermes API redactor.
- File APIs must resolve paths through project-root containment helpers and must reject absolute paths or traversal attempts.
- Binary project-file content is not returned by the Core API.
- Secrets, tokens, connection strings, provider credentials, and raw environment values must not be added to docs, tests, logs, or route responses.

## Operation schema

Long-running or side-effectful operations should return an operation descriptor, even when the current implementation runs synchronously:

```json
{
  "operationId": "deployment-publish-abc123",
  "kind": "deployment.publish",
  "projectId": "project-id",
  "status": "queued|running|succeeded|failed|cancelled",
  "startedAt": "2026-05-26T00:00:00.000Z",
  "updatedAt": "2026-05-26T00:00:00.000Z",
  "progress": { "summary": "human summary" },
  "result": {},
  "error": null
}
```

`api.core_contracts.operation_record()` is the shared helper for this shape.

## Provider capability schema

Deployment providers are returned by `/api/core/deployments/providers`:

```json
{
  "providers": [
    {
      "id": "manual",
      "label": "Manual record",
      "description": "Record externally managed deployments.",
      "capabilities": {
        "record": true,
        "execute": false,
        "scaffold": true,
        "logs": true,
        "rollback": true,
        "delete": true
      }
    }
  ],
  "defaultProvider": "manual"
}
```

UIs must render controls from provider metadata where possible. The Ops Deployments dashboard now loads this route before rendering project deployment panels.

## Domain route map

### Projects, tasks, and safe project files

| Route | Method | Notes |
| --- | --- | --- |
| `/api/core/projects` | `GET` / `POST` | List or create registered Ops/Core projects. |
| `/api/core/projects/{projectId}` | `GET` | Get one project. |
| `/api/core/projects/{projectId}/update` | `POST` | Update project settings. |
| `/api/core/projects/{projectId}/settings` | `POST` | Alias for update semantics. |
| `/api/core/projects/{projectId}/activity` | `POST` | Set active/inactive state. |
| `/api/core/projects/{projectId}/ensure-workspace` | `POST` | Ensure WebUI workspace registration. |
| `/api/core/projects/{projectId}/delete` | `POST` | Delete/detach project per domain rules. |
| `/api/core/projects/{projectId}/files` | `GET` | List files under the project root. |
| `/api/core/projects/{projectId}/files/content` | `GET` | Read redacted UTF-8 text from a contained file. |
| `/api/core/projects/{projectId}/tasks` | `GET` / `POST` | Read or create project tasks. |
| `/api/core/projects/{projectId}/epics` | `POST` | Create project epic. |
| `/api/core/projects/{projectId}/epics/ensure` | `POST` | Create-or-return epic. |
| `/api/core/projects/{projectId}/tasks/{taskId}` | `POST` | Update task. |
| `/api/core/projects/{projectId}/tasks/{taskId}/images` | `POST` | Attach task image. |
| `/api/core/projects/{projectId}/tasks/{taskId}/delete` | `POST` | Delete task. |
| `/api/core/projects/{projectId}/epics/{epicId}/delete` | `POST` | Delete epic. |
| `/api/core/projects/{projectId}/tasks/archive-completed` | `POST` | Archive completed tasks. |

### Play/build runtime

| Route | Method |
| --- | --- |
| `/api/core/projects/{projectId}/play-config-file` | `GET` |
| `/api/core/projects/{projectId}/play/status` | `GET` |
| `/api/core/projects/{projectId}/play/logs` | `GET` |
| `/api/core/projects/{projectId}/play/start` | `POST` |
| `/api/core/projects/{projectId}/play/restart` | `POST` |
| `/api/core/projects/{projectId}/play/stop` | `POST` |

The Core Play facade delegates to the existing Play pipeline implementation. Legacy Ops Play routes are compatibility wrappers around this facade.

### Deployments

| Route | Method | Notes |
| --- | --- | --- |
| `/api/core/deployments/providers` | `GET` | Provider/capability metadata. |
| `/api/core/projects/{projectId}/deployment` | `GET` / `POST` | Read or record a deployment. |
| `/api/core/projects/{projectId}/deployment/logs` | `GET` | Deployment logs. |
| `/api/core/projects/{projectId}/deployment/artifacts` | `GET` | Detect deployment artifacts. |
| `/api/core/projects/{projectId}/deployment/artifacts/scaffold` | `POST` | Create scaffold files when supported. |
| `/api/core/projects/{projectId}/deployment/execute` | `POST` | Execute/record a deployment operation. |
| `/api/core/projects/{projectId}/deployment/redeploy` | `POST` | Redeploy an existing Cloud Terminal deployment with current project code while preserving the existing deployment record and database mode. Requires `confirm: "redeploy"`; rejects database-mode changes. For `local-legacy` deployments, Core owns the redeploy directly: it runs the project deploy build when a build command is available, preserves previous hashed public/browser assets, atomically replaces `.deployments/items/{slug}/source`, and updates deployment lifecycle metadata without requiring a Cloud Terminal session token. Non-local Cloud Terminal providers may still delegate to their provider runtime. |
| `/api/core/projects/{projectId}/deployment/update` | `POST` | Alias for redeploy/update semantics above, kept ahead of the generic lifecycle action route. |
| `/api/core/projects/{projectId}/deployment/{action}` | `POST` | Record lifecycle action such as rollback. `update` is reserved for the first-class redeploy/update operation. |

The Ops dashboard Deployments entry opens a dedicated Deployments view backed by these Core routes. Legacy `/api/ops/.../deployment` routes are retained as wrappers for older clients, including the redeploy/update compatibility aliases.

Published local-legacy deployments are served through the native Core proxy at `/deploy/{slug}/...`. Root deployment requests redirect to the configured public entry path (for example `/deploy/{slug}/app`) and set a deployment-context cookie. Browser requests from that deployed app for root-relative compatibility paths such as `/api/trpc/*`, `/api/blob/*`, `/assets/*`, `/app`, `/login`, and `/auth/*` are treated as public deployment traffic when the request carries a `/deploy/{slug}` referer or deployment cookie. Unsafe deployment proxy requests are routed before WebUI CSRF and JSON body parsing so tRPC login/signup/logout calls keep their raw request body and do not fall through to WebUI `not found` responses.

### Database

| Route | Method |
| --- | --- |
| `/api/core/database/settings` | `GET` / `POST` |
| `/api/core/database/test` | `POST` |
| `/api/core/database/inspect/tables` | `GET` |
| `/api/core/database/inspect/query` | `POST` |
| `/api/core/projects/{projectId}/database/settings` | `GET` / `POST` |
| `/api/core/projects/{projectId}/database/test` | `POST` |
| `/api/core/projects/{projectId}/database/inspect/tables` | `GET` |
| `/api/core/projects/{projectId}/database/inspect/query` | `POST` |

### Git and GitHub

| Route | Method |
| --- | --- |
| `/api/core/projects/{projectId}/git/status` | `GET` |
| `/api/core/projects/{projectId}/git/push` | `POST` |
| `/api/core/projects/{projectId}/git/sync` | `POST` |
| `/api/core/github/status` | `GET` |
| `/api/core/github/repos` | `GET` |
| `/api/core/github/repos/{owner}/{repo}/branches` | `GET` |
| `/api/core/github/import` | `POST` |

### Runtime inspection and gather tools

| Route | Method |
| --- | --- |
| `/api/core/projects/{projectId}/runtime/summary` | `GET` |
| `/api/core/projects/{projectId}/runtime/capabilities` | `GET` |
| `/api/core/projects/{projectId}/runtime/gather/reports` | `GET` / `POST` |
| `/api/core/projects/{projectId}/runtime/gather/reports/latest` | `GET` |
| `/api/core/projects/{projectId}/runtime/gather/reports/{reportId}` | `GET` |
| `/api/core/projects/{projectId}/runtime/gather/reports/{reportId}/events` | `POST` |
| `/api/core/projects/{projectId}/runtime/inspect/reviews` | `GET` / `POST` |
| `/api/core/projects/{projectId}/runtime/inspect/reviews/latest` | `GET` |
| `/api/core/projects/{projectId}/runtime/inspect/reviews/{reviewId}` | `GET` |
| `/api/core/projects/{projectId}/runtime/inspect/reviews/{reviewId}/complete` | `POST` |
| `/api/core/projects/{projectId}/runtime/inspect/snapshot` | `POST` |
| `/api/core/projects/{projectId}/runtime/inspect/snapshot/latest` | `GET` |
| `/api/core/projects/{projectId}/runtime/inspect/screenshot` | `POST` |
| `/api/core/projects/{projectId}/runtime/inspect/screenshot/latest` | `GET` |
| `/api/core/projects/{projectId}/runtime/inspect/action` | `POST` |
| `/api/core/projects/{projectId}/runtime/inspect/action/latest` | `GET` |

### Session activity and readable output

| Route | Method |
| --- | --- |
| `/api/core/session-activity` | `GET` |
| `/api/core/session-activity/groups` | `POST` |
| `/api/core/session-activity/groups/{groupId}/rename` | `POST` |
| `/api/core/session-activity/groups/{groupId}/delete` | `POST` |
| `/api/core/session-activity/group-assignment` | `POST` |
| `/api/core/sessions/{sessionId}/readable-output` | `GET` |

## Migration notes

- `/api/ops/projects/{projectId}/play/...` is a compatibility layer over `api.core_play`.
- `/api/ops/projects/{projectId}/deployment...` is a compatibility layer over `api.core_deployments`.
- New shared UI/runtime consumers should prefer `/api/core/...`.
- Core modules must not import frontend code, Cloud Terminal/Codex UI code, or shell-specific copy. Shells own navigation, presentation, and notifications.

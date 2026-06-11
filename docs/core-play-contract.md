# Core Play Contract

Status: implemented as an in-process Hermes WebUI API boundary.

This document defines the current Hermes **core-play** contract.  The first
slice is intentionally conservative: it creates a stable boundary around the
existing `api.play_pipeline` implementation without changing Play process,
proxy, log, config-discovery, notification, or status behavior.

Cloud Terminal is legacy/reference-only for this contract.  It does not need to
consume this boundary.

## Ownership

- Public in-process boundary: `api.core_play`.
- Current implementation: `api.play_pipeline`.
- HTTP shell routes: `api.routes_ops_play`.
- Ops integration callers: `api.ops_runs`, `api.ops_runtime_tools`, and
  `api.ops_notifications`.

Ops-facing modules should import `api.core_play`, not `api.play_pipeline`.
Tests may still target `api.play_pipeline` directly when they verify the current
implementation internals.

## Non-goals for the first slice

- No new daemon or external service.
- No Cloud Terminal migration.
- No route shape changes.
- No persistence model changes.
- No changes to Play process lifecycle, port allocation, proxy rewriting,
  build-failure repair handoff, or notification semantics.
- No removal of `api.play_pipeline`; it remains the implementation module.

## In-process API

`api.core_play` exposes these stable functions:

| Function | Purpose |
|---|---|
| `get_project_play_config_file_info(project_id)` | Discover and validate Play config metadata for a project. |
| `get_project_play_config(project_id)` | Resolve the normalized runnable config. |
| `get_project_play_status(project_id)` | Return the current status payload for a project. |
| `get_project_play_logs(project_id, limit)` | Return bounded Play logs. |
| `start_project_play(project_id, body=None)` | Start the project's Play workflow and return status. |
| `restart_project_play(project_id, body=None)` | Restart the project's Play workflow and return status. |
| `stop_project_play(project_id, purge=False)` | Stop the project's Play workflow; returns status or `None` when no pipeline exists. |
| `handle_play_proxy_request(handler, project_id, target_path, parsed, method="GET")` | Proxy an HTTP/WebSocket request to the ready Play target. |
| `register_build_failure_repair_handler(handler)` | Register the shell-owned repair handoff callback for failed Play builds. |

Errors raised across this boundary use `core_play.PlayCoreError` /
`core_play.PlayPipelineError`.  The class is currently the same object as
`play_pipeline.PlayPipelineError`, preserving the existing `status` attribute and
HTTP error behavior.

## HTTP route contract

The existing Ops routes are unchanged.  They now call `api.core_play` internally.

| Method | Route | Response notes |
|---|---|---|
| `GET` | `/api/ops/projects/{projectId}/play-config-file` | Direct config-info payload. |
| `GET` | `/api/ops/projects/{projectId}/play/status` | Direct Play status payload. |
| `GET` | `/api/ops/projects/{projectId}/play/logs?limit=N` | Direct log payload. |
| `POST` | `/api/ops/projects/{projectId}/play/start` | `{ ok: true, started: true, status, message }`. |
| `POST` | `/api/ops/projects/{projectId}/play/restart` | `{ ok: true, restarted: true, status, message }`. |
| `POST` | `/api/ops/projects/{projectId}/play/stop` | `{ ok: true, stopped: true, status, message }`. If the core stop returns `None`, the route fetches current status, preserving historical behavior. |
| `GET/POST/...` | `/play-project/{projectId}/{path}` | Proxies to the active ready Play target. |

The injected Play session overlay may render a project-scoped **Feedback** control when the proxy context includes a project id. That control captures the current Play page through `/api/core/projects/{projectId}/runtime/inspect/screenshot` with `includeContent: true`, lets the user skip or annotate the screenshot with a red marker, then saves the wrapped feedback text as a new project task under the `User Feedback` epic and attaches the screenshot through the Core task image route. The screenshot capture URL includes `hermesPlayFeedbackCapture=1` so the overlay does not recursively appear in its own capture.

Error responses retain the existing JSON helper shape:

```json
{ "error": "message" }
```

The HTTP status comes from the raised core error's `status` attribute.

## Status payload expectations

The status payload is intentionally inherited from the existing implementation.
Known stable fields include:

- `projectId`
- `status`
- `running`
- `ready`
- `statusLabel`
- `statusSummary`
- `buildAvailable`
- `workflowSource`
- `config`
- `configPath`
- `configBranch`
- `pipelineId`
- `runId`
- `taskId`
- `sessionId`
- `inspectUrl`
- `inspectMode`
- `startedAt`
- `readyAt`
- `finishedAt`
- `updatedAt`
- `error`
- `failureSummary`
- `repairRequestedAt`
- `repairStreamId`
- `repairError`

Callers must treat unknown fields as forward-compatible additions.

## Extraction rule

Future extraction should move implementation behind `api.core_play` while keeping
this boundary stable.  Acceptable next steps include:

1. Split config discovery, process lifecycle, proxying, and log storage into
   smaller implementation modules.
2. Keep Ops callers pinned to `api.core_play` during those splits.
3. Add contract tests for each HTTP route and each in-process boundary function
   before replacing any underlying implementation.
4. Only introduce a service/HTTP boundary after the in-process contract is stable
   and covered.

## Verification gate

A behavior-preserving change to core-play should run at minimum:

```bash
python3 -m py_compile api/core_play.py api/routes_ops_play.py api/ops_runs.py api/ops_runtime_tools.py api/ops_notifications.py
pytest -q tests/test_core_play_boundary.py tests/test_ops_play_pipeline_handoff.py tests/test_upstream_restart_phase7_play.py tests/test_runtime_adapter_seam.py
```

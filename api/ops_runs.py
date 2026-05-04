"""Fork-owned run activity records for the clean restart branch."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from api.config import STATE_DIR
from api import ops_projects, session_readable_output
from api.models import get_session


OPS_RUNS_FILE = STATE_DIR / "ops" / "runs.json"
RUN_STATUS_VALUES = {
    "queued",
    "starting",
    "running",
    "waiting-input",
    "waiting-approval",
    "succeeded",
    "failed",
    "stopped",
    "stale",
}
RUN_TERMINAL_STATUSES = {"succeeded", "failed", "stopped", "stale"}
_LOCK = threading.RLock()


class OpsRunError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _text(value: Any, *, limit: int = 512) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _json_safe(val) for key, val in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(item) for item in value]
        return str(value)


def _run_id(value: Any = "") -> str:
    existing = _text(value, limit=128)
    if existing:
        return existing
    return f"run_{uuid.uuid4().hex}"


def _to_iso(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return ""


def _status(value: Any, *, default: str = "running") -> str:
    normalized = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    if not normalized:
        return default
    if normalized not in RUN_STATUS_VALUES:
        raise OpsRunError("Run status is invalid.")
    return normalized


def _read_runs() -> list[dict]:
    try:
        parsed = json.loads(OPS_RUNS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [_normalize_run(item) for item in parsed if isinstance(item, dict)]


def _write_runs(items: list[dict]) -> None:
    OPS_RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OPS_RUNS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OPS_RUNS_FILE)


def _normalize_run(entry: dict) -> dict:
    run = dict(entry)
    now = _now_iso()
    run["id"] = _run_id(run.get("id"))
    run["projectId"] = _text(run.get("projectId") or run.get("project_id"), limit=128)
    run["taskId"] = _text(run.get("taskId") or run.get("task_id"), limit=128)
    run["sessionId"] = _text(run.get("sessionId") or run.get("session_id"), limit=128)
    run["title"] = _text(run.get("title"), limit=256) or "Task run"
    run["summary"] = _text(run.get("summary"), limit=4000)
    run["status"] = _status(run.get("status"), default="running")
    run["createdAt"] = _text(run.get("createdAt") or run.get("created_at"), limit=64) or now
    run["updatedAt"] = _text(run.get("updatedAt") or run.get("updated_at"), limit=64) or run["createdAt"]
    completed_at = _text(run.get("completedAt") or run.get("completed_at"), limit=64)
    if completed_at:
        run["completedAt"] = completed_at
    else:
        run.pop("completedAt", None)
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    run["metadata"] = _json_safe(metadata)
    return run


def _load_run(run_id: str) -> tuple[int, list[dict], dict]:
    key = _text(run_id, limit=128)
    if not key:
        raise OpsRunError("Run id is required.")
    with _LOCK:
        runs = _read_runs()
    for index, run in enumerate(runs):
        if run.get("id") == key:
            return index, runs, run
    raise OpsRunError("Run not found.", 404)


def run_url(run_id: str) -> str:
    key = _text(run_id, limit=128)
    if not key:
        raise OpsRunError("Run id is required.")
    return f"/api/ops/runs/{quote(key, safe='')}"


def _session_url(session_id: str) -> str:
    from api import ops_sessions

    return ops_sessions.session_url(session_id)


def _session_summary(session_id: str) -> dict | None:
    key = _text(session_id, limit=128)
    if not key:
        return None
    try:
        session = get_session(key, metadata_only=True)
    except KeyError:
        return None
    except Exception:
        return None
    return session.compact()


def _project_context(project_id: str) -> dict | None:
    key = _text(project_id, limit=128)
    if not key:
        return None
    try:
        project = ops_projects.get_ops_project(key)
    except ops_projects.OpsProjectError:
        return None
    return {
        "id": project["id"],
        "name": project.get("name"),
        "path": project.get("path"),
        "coreBranch": project.get("coreBranch"),
    }


def _task_context(project_id: str, task_id: str) -> dict | None:
    project_key = _text(project_id, limit=128)
    task_key = _text(task_id, limit=128)
    if not project_key or not task_key:
        return None
    try:
        resolved = ops_projects.get_ops_project_task(project_key, task_key)
    except ops_projects.OpsProjectError:
        return None
    return {
        "id": resolved["task"].get("id"),
        "text": resolved["task"].get("text"),
        "grade": resolved["task"].get("grade"),
        "done": resolved["task"].get("done"),
        "epicId": resolved.get("epicId"),
    }


def _readable_output_state(session_id: str) -> dict:
    key = _text(session_id, limit=128)
    if not key:
        return {"available": False}
    try:
        payload = session_readable_output.get_session_readable_output(key)
    except session_readable_output.SessionReadableOutputError:
        return {"available": False}
    artifact = payload.get("readableOutput") if isinstance(payload, dict) else None
    if not isinstance(artifact, dict) or not artifact.get("exists"):
        return {"available": False}
    return {
        "available": True,
        "title": artifact.get("title"),
        "updatedAt": artifact.get("updated_at"),
    }


def _run_requests_for_session(session_id: str) -> list[dict]:
    key = _text(session_id, limit=128)
    if not key:
        return []
    from api import ops_notifications

    requests: list[dict] = []
    approval = ops_notifications._pending_approval(key)
    pending_approval = approval.get("pending")
    if isinstance(pending_approval, dict):
        requests.append(
            {
                "id": _text(pending_approval.get("approval_id"), limit=128) or f"approval:{key}",
                "kind": "approval",
                "status": "pending",
                "message": _text(
                    pending_approval.get("description") or pending_approval.get("command"),
                    limit=4000,
                ),
                "createdAt": None,
                "metadata": _json_safe(pending_approval),
            }
        )
    clarify = ops_notifications._pending_clarify(key)
    pending_clarify = clarify.get("pending")
    if isinstance(pending_clarify, dict):
        requests.append(
            {
                "id": _text(pending_clarify.get("requested_at"), limit=128) or f"clarify:{key}",
                "kind": "clarification",
                "status": "pending",
                "message": _text(
                    pending_clarify.get("question") or pending_clarify.get("description"),
                    limit=4000,
                ),
                "createdAt": pending_clarify.get("requested_at"),
                "metadata": _json_safe(pending_clarify),
            }
        )
    return requests


def _derive_status(run: dict, session: dict | None, requests: list[dict], readable_output: dict) -> str:
    stored = _status(run.get("status"), default="running")
    if stored in RUN_TERMINAL_STATUSES:
        return stored
    if not session:
        return "stale"
    if any(request.get("kind") == "approval" for request in requests):
        return "waiting-approval"
    if requests:
        return "waiting-input"
    if session.get("active_stream_id") or session.get("pending_user_message"):
        return "running"
    if readable_output.get("available"):
        return "succeeded"
    return stored


def _enrich_run(run: dict) -> dict:
    session_id = _text(run.get("sessionId"), limit=128)
    session = _session_summary(session_id)
    requests = _run_requests_for_session(session_id)
    readable_output = _readable_output_state(session_id)
    status = _derive_status(run, session, requests, readable_output)
    updated_at = run.get("updatedAt")
    if isinstance(session, dict):
        updated_at = _to_iso(session.get("updated_at")) or updated_at
    if readable_output.get("available") and readable_output.get("updatedAt"):
        updated_at = _to_iso(readable_output.get("updatedAt")) or updated_at
    return {
        **run,
        "status": status,
        "updatedAt": updated_at or run.get("updatedAt"),
        "project": _project_context(_text(run.get("projectId"), limit=128)),
        "task": _task_context(_text(run.get("projectId"), limit=128), _text(run.get("taskId"), limit=128)),
        "session": session,
        "sessionUrl": _session_url(session_id) if session_id else "",
        "pendingRequestCount": len(requests),
        "requests": requests,
        "readableOutput": {
            **readable_output,
            **(
                {"url": f"/api/ops/runs/{quote(str(run.get('id') or ''), safe='')}/readable-output"}
                if readable_output.get("available")
                else {}
            ),
        },
        "runUrl": run_url(str(run.get("id") or "")),
    }


def create_task_run(project_id: str, task_id: str, session_id: str, *, title: str = "", summary: str = "") -> dict:
    project = ops_projects.get_ops_project(project_id)
    resolved = ops_projects.get_ops_project_task(project["id"], task_id)
    session_key = _text(session_id, limit=128)
    if not session_key:
        raise OpsRunError("Session id is required.")
    existing = None
    with _LOCK:
        runs = _read_runs()
        for run in runs:
            if run.get("sessionId") == session_key:
                existing = run
                break
        if existing:
            return _enrich_run(existing)
        run = _normalize_run(
            {
                "id": _run_id(),
                "projectId": project["id"],
                "taskId": resolved["task"].get("id"),
                "sessionId": session_key,
                "title": _text(title, limit=256) or _text(resolved["task"].get("text"), limit=256) or "Task run",
                "summary": summary,
                "status": "running",
                "createdAt": _now_iso(),
                "updatedAt": _now_iso(),
                "metadata": {
                    "taskText": resolved["task"].get("text"),
                    "projectName": project.get("name"),
                },
            }
        )
        runs.insert(0, run)
        _write_runs(runs)
    return _enrich_run(run)


def list_ops_runs(filters: dict | None = None) -> dict:
    filters = filters or {}
    project_id = _text(filters.get("projectId") or filters.get("project_id"), limit=128)
    task_id = _text(filters.get("taskId") or filters.get("task_id"), limit=128)
    session_id = _text(filters.get("sessionId") or filters.get("session_id"), limit=128)
    status = _text(filters.get("status"), limit=64).lower().replace("_", "-").replace(" ", "-")
    if status and status not in RUN_STATUS_VALUES:
        raise OpsRunError("Run status is invalid.")

    with _LOCK:
        runs = list(_read_runs())
    enriched = [_enrich_run(run) for run in runs]
    if project_id:
        enriched = [run for run in enriched if _text(run.get("projectId"), limit=128) == project_id]
    if task_id:
        enriched = [run for run in enriched if _text(run.get("taskId"), limit=128) == task_id]
    if session_id:
        enriched = [run for run in enriched if _text(run.get("sessionId"), limit=128) == session_id]
    if status:
        enriched = [run for run in enriched if run.get("status") == status]
    enriched.sort(key=lambda item: str(item.get("updatedAt") or item.get("createdAt") or ""), reverse=True)
    return {"runs": enriched, "count": len(enriched)}


def get_ops_run(run_id: str) -> dict:
    _index, _runs, run = _load_run(run_id)
    return _enrich_run(run)


def update_ops_run(run_id: str, updates: dict | None = None) -> dict:
    payload = updates if isinstance(updates, dict) else {}
    index, runs, current = _load_run(run_id)
    updated = dict(current)
    if "title" in payload:
        title = _text(payload.get("title"), limit=256)
        if not title:
            raise OpsRunError("Run title is required.")
        updated["title"] = title
    if "summary" in payload:
        updated["summary"] = _text(payload.get("summary"), limit=4000)
    if "status" in payload:
        updated["status"] = _status(payload.get("status"), default=updated.get("status") or "running")
    updated["updatedAt"] = _now_iso()
    if updated.get("status") in RUN_TERMINAL_STATUSES and not updated.get("completedAt"):
        updated["completedAt"] = updated["updatedAt"]
    runs[index] = _normalize_run(updated)
    with _LOCK:
        _write_runs(runs)
    return _enrich_run(runs[index])


def complete_ops_run(run_id: str, body: dict | None = None) -> dict:
    payload = dict(body or {})
    status = _status(payload.get("status"), default="succeeded")
    if status not in RUN_TERMINAL_STATUSES:
        raise OpsRunError("Completed run status must be terminal.")
    payload["status"] = status
    payload["completedAt"] = _now_iso()
    return update_ops_run(run_id, payload)


def mark_stale_ops_runs(body: dict | None = None) -> dict:
    updated = 0
    with _LOCK:
        runs = _read_runs()
        next_runs = list(runs)
        for index, run in enumerate(runs):
            if _status(run.get("status"), default="running") in RUN_TERMINAL_STATUSES:
                continue
            if _session_summary(_text(run.get("sessionId"), limit=128)):
                continue
            next_run = dict(run)
            next_run["status"] = "stale"
            next_run["updatedAt"] = _now_iso()
            if not next_run.get("completedAt"):
                next_run["completedAt"] = next_run["updatedAt"]
            next_runs[index] = _normalize_run(next_run)
            updated += 1
        if updated:
            _write_runs(next_runs)
            runs = next_runs
    return {"updated": updated, "count": updated}


def list_ops_run_requests(run_id: str) -> dict:
    run = get_ops_run(run_id)
    requests = run.get("requests") if isinstance(run, dict) else []
    requests = requests if isinstance(requests, list) else []
    return {"runId": run.get("id"), "requests": requests, "count": len(requests)}


def get_ops_run_runtime_status(run_id: str) -> dict:
    run = get_ops_run(run_id)
    return {
        "runId": run.get("id"),
        "status": run.get("status"),
        "sessionId": run.get("sessionId"),
        "pendingRequestCount": run.get("pendingRequestCount"),
        "readableOutputAvailable": bool((run.get("readableOutput") or {}).get("available")),
        "session": run.get("session"),
    }


def get_ops_run_readable_output(run_id: str) -> dict:
    run = get_ops_run(run_id)
    session_id = _text(run.get("sessionId"), limit=128)
    if not session_id:
        raise OpsRunError("Run has no linked session.", 404)
    try:
        return session_readable_output.get_session_readable_output(session_id)
    except session_readable_output.SessionReadableOutputError as exc:
        raise OpsRunError(str(exc), exc.status) from exc


def resolve_ops_run_readable_asset(run_id: str, asset_path: str) -> Path:
    run = get_ops_run(run_id)
    session_id = _text(run.get("sessionId"), limit=128)
    if not session_id:
        raise OpsRunError("Run has no linked session.", 404)
    try:
        return session_readable_output.resolve_session_readable_asset(session_id, asset_path)
    except session_readable_output.SessionReadableOutputError as exc:
        raise OpsRunError(str(exc), exc.status) from exc

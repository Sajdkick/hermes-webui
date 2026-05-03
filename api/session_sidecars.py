"""Fork-owned session linkage sidecars for the clean restart branch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from api.config import STATE_DIR
from api.models import Session


class SessionSidecarError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _sidecar_dir() -> Path:
    return STATE_DIR / "ops" / "session-links"


def _validate_session_id(session_id: str) -> str:
    value = str(session_id or "").strip()
    if not value or not all(char in "0123456789abcdefghijklmnopqrstuvwxyz_" for char in value):
        raise SessionSidecarError("Session id is invalid.")
    return value


def _sidecar_path(session_id: str) -> Path:
    return _sidecar_dir() / f"{_validate_session_id(session_id)}.json"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise SessionSidecarError(f"{path.name} contains invalid JSON.", 500) from exc
    except OSError as exc:
        raise SessionSidecarError(f"Could not read {path.name}.", 500) from exc


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _session_summary(session_id: str) -> dict[str, Any] | None:
    session = Session.load_metadata_only(session_id)
    if not session:
        return None
    return session.compact()


def _session_url(session_id: str) -> str:
    return f"/session/{quote(session_id, safe='')}"


def get_session_linkage(session_id: str) -> dict[str, Any] | None:
    key = _validate_session_id(session_id)
    payload = _read_json(_sidecar_path(key))
    if not payload:
        return None
    summary = _session_summary(key)
    return {
        **payload,
        "session": summary,
        "sessionUrl": _session_url(key),
        "available": summary is not None,
    }


def get_project_task_link(project_id: str, task_id: str) -> dict[str, Any] | None:
    from api import ops_projects

    project_key = str(project_id or "").strip()
    task_key = str(task_id or "").strip()
    if not project_key or not task_key:
        raise SessionSidecarError("Project id and task id are required.")
    ops_projects.get_ops_project_task(project_key, task_key)
    return {"projectId": project_key, "taskId": task_key}


def set_session_linkage(session_id: str, project_id: str, task_id: str | None = None, run_id: str | None = None) -> dict[str, Any]:
    from api import ops_projects

    key = _validate_session_id(session_id)
    if not _session_summary(key):
        raise SessionSidecarError("Session not found.", 404)

    project = ops_projects.get_ops_project(project_id)
    task_key = str(task_id or "").strip() or None
    if task_key:
        ops_projects.get_ops_project_task(project["id"], task_key)

    existing = _read_json(_sidecar_path(key)) or {}
    payload = {
        "sessionId": key,
        "projectId": project["id"],
        "taskId": task_key,
        "runId": str(run_id or "").strip() or None,
        "linkedAt": existing.get("linkedAt") or ops_projects._now_iso(),
        "updatedAt": ops_projects._now_iso(),
    }
    _write_json(_sidecar_path(key), payload)
    return get_session_linkage(key)


def list_project_linkages(project_id: str) -> list[dict[str, Any]]:
    project_key = str(project_id or "").strip()
    if not project_key:
        raise SessionSidecarError("Project id is required.")
    result = []
    for path in sorted(_sidecar_dir().glob("*.json")):
        try:
            payload = _read_json(path)
        except SessionSidecarError:
            continue
        if not payload or payload.get("projectId") != project_key:
            continue
        try:
            linkage = get_session_linkage(str(payload.get("sessionId") or ""))
        except SessionSidecarError:
            continue
        if linkage:
            result.append(linkage)
    result.sort(
        key=lambda linkage: (
            str(linkage.get("updatedAt") or linkage.get("linkedAt") or ""),
            str(linkage.get("sessionId") or ""),
        ),
        reverse=True,
    )
    return result


def task_linkage_map(project_id: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for linkage in list_project_linkages(project_id):
        task_id = str(linkage.get("taskId") or "").strip()
        if not task_id:
            continue
        grouped.setdefault(task_id, []).append(linkage)
    return grouped

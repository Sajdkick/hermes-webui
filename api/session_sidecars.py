"""Fork-owned session linkage sidecars for the clean restart branch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from api.config import STATE_DIR
from api.models import Session, all_sessions


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


def _session_sort_key(summary: dict[str, Any] | None) -> float:
    if not isinstance(summary, dict):
        return 0.0
    for field in ("last_message_at", "updated_at", "created_at"):
        try:
            value = float(summary.get(field) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _canonical_session_rank(summary: dict[str, Any] | None) -> tuple[int, int, float, float, str]:
    """Rank lineage candidates by transcript currency, not sidebar visibility.

    Ops task links are durable references to a conversation lineage. A completed
    or closed task can archive the current tip to hide it from the normal sidebar,
    while older sibling continuations remain unarchived. If sidecar resolution
    prefers non-archived rows first, task resume/open actions can jump back to an
    older root/sibling and make the conversation look like it lost messages.
    """
    if not isinstance(summary, dict):
        return (0, 0, 0.0, 0.0, "")
    session_id = str(summary.get("session_id") or "").strip()
    lineage_tip_id = str(summary.get("_lineage_tip_id") or "").strip()
    continuation_tip = bool(
        summary.get("parent_session_id")
        or (lineage_tip_id and lineage_tip_id == session_id)
    )
    return (
        1 if continuation_tip else 0,
        _safe_int(summary.get("message_count")),
        _session_sort_key(summary),
        float(summary.get("updated_at") or 0.0),
        session_id,
    )


def _session_aliases(summary: dict[str, Any] | None) -> set[str]:
    aliases: set[str] = set()
    if not isinstance(summary, dict):
        return aliases
    for field in ("session_id", "_lineage_root_id", "_lineage_tip_id", "parent_session_id"):
        value = str(summary.get(field) or "").strip()
        if value:
            aliases.add(value)
    return aliases


def resolve_session_summary(session_id: str) -> dict[str, Any] | None:
    key = _validate_session_id(session_id)
    candidates: dict[str, dict[str, Any]] = {}

    direct = _session_summary(key)
    if direct:
        candidates[str(direct.get("session_id") or key)] = direct

    try:
        for session in all_sessions():
            if not isinstance(session, dict):
                continue
            if key not in _session_aliases(session):
                continue
            session_key = str(session.get("session_id") or "").strip()
            if session_key:
                candidates[session_key] = dict(session)
    except Exception:
        pass

    if not candidates:
        return None
    return max(candidates.values(), key=_canonical_session_rank)


def resolve_session_id(session_id: str) -> str | None:
    summary = resolve_session_summary(session_id)
    if not summary:
        return None
    value = str(summary.get("session_id") or "").strip()
    return value or None


def _session_url(session_id: str) -> str:
    return f"/session/{quote(session_id, safe='')}"


def get_session_linkage(session_id: str) -> dict[str, Any] | None:
    key = _validate_session_id(session_id)
    payload = _read_json(_sidecar_path(key))
    if not payload:
        return None
    summary = resolve_session_summary(key)
    resolved_id = str(summary.get("session_id") or key).strip() if summary else key
    lineage_root_id = str(summary.get("_lineage_root_id") or key).strip() if summary else key
    lineage_tip_id = str(summary.get("_lineage_tip_id") or resolved_id).strip() if summary else resolved_id
    return {
        **payload,
        "linkedSessionId": key,
        "sessionId": resolved_id,
        "lineageRootId": lineage_root_id,
        "lineageTipId": lineage_tip_id,
        "session": summary,
        "sessionUrl": _session_url(resolved_id),
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


def inherit_session_linkage(source_session_id: str, target_session_id: str) -> dict[str, Any] | None:
    """Copy an Ops/task sidecar from a rotated parent segment to its continuation.

    Context compression changes the WebUI session id. Without a sidecar for the
    new id, every Ops resume/open path keeps resolving from the original root and
    can later choose a stale sibling. Stamping the continuation gives future
    task linkage an explicit handle for the current segment while preserving the
    original root sidecar as an alias.
    """
    from api import ops_projects

    source_key = _validate_session_id(source_session_id)
    target_key = _validate_session_id(target_session_id)
    if source_key == target_key:
        return get_session_linkage(target_key)
    if not _session_summary(target_key):
        return None
    source = _read_json(_sidecar_path(source_key))
    if not source:
        return None
    existing = _read_json(_sidecar_path(target_key)) or {}
    payload = {
        "sessionId": target_key,
        "projectId": source.get("projectId"),
        "taskId": source.get("taskId"),
        "runId": source.get("runId"),
        "linkedAt": existing.get("linkedAt") or source.get("linkedAt") or ops_projects._now_iso(),
        "updatedAt": ops_projects._now_iso(),
        "inheritedFromSessionId": source_key,
    }
    _write_json(_sidecar_path(target_key), payload)
    return get_session_linkage(target_key)


def list_project_linkage_records(project_id: str) -> list[dict[str, Any]]:
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
        result.append(dict(payload))
    result.sort(
        key=lambda linkage: (
            str(linkage.get("updatedAt") or linkage.get("linkedAt") or ""),
            str(linkage.get("sessionId") or ""),
        ),
        reverse=True,
    )
    return result


def list_project_linkages(project_id: str) -> list[dict[str, Any]]:
    result = []
    for payload in list_project_linkage_records(project_id):
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

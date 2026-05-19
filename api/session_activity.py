"""Cloud Terminal-style session activity helpers for the standalone ops UI."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from api import ops_sessions
from api.models import all_sessions


SESSION_ACTIVITY_GROUP_LABEL_MAX_LENGTH = int(
    os.getenv("SESSION_ACTIVITY_GROUP_LABEL_MAX_LENGTH") or "80"
)
SESSION_ACTIVITY_GROUP_LIMIT = int(
    os.getenv("SESSION_ACTIVITY_GROUP_LIMIT_PER_USER") or "40"
)
SESSION_ACTIVITY_GROUP_ASSIGNMENT_LIMIT = int(
    os.getenv("SESSION_ACTIVITY_GROUP_ASSIGNMENT_LIMIT_PER_USER") or "400"
)
SESSION_ACTIVITY_REFRESH_INTERVAL_MS = 5000
_ACTIVE_RUN_STATUSES = {
    "queued",
    "starting",
    "running",
    "waiting-input",
    "waiting-approval",
}


class SessionActivityError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _epoch_seconds(value) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _profile_state_dir() -> Path:
    try:
        from api.profiles import get_active_hermes_home

        state_dir = get_active_hermes_home() / "webui_state"
    except Exception:
        state_dir = Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser() / "webui_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def _state_path() -> Path:
    return _profile_state_dir() / "session_activity_groups.json"


def _normalize_group_label(value) -> str:
    if not isinstance(value, str):
        return ""
    normalized = " ".join(value.split()).strip()
    if not normalized:
        return ""
    return normalized[:SESSION_ACTIVITY_GROUP_LABEL_MAX_LENGTH].strip()


def _normalize_group(entry: dict | None, fallback_position: int = 0) -> dict | None:
    if not isinstance(entry, dict):
        return None
    group_id = str(entry.get("id") or "").strip()
    label = _normalize_group_label(entry.get("label"))
    if not group_id or not label:
        return None
    parsed_position = int(entry.get("position") or fallback_position or 0)
    created_at = str(entry.get("createdAt") or "").strip() or _now_iso()
    updated_at = str(entry.get("updatedAt") or "").strip() or created_at
    return {
        "id": group_id,
        "label": label,
        "position": max(0, parsed_position),
        "createdAt": created_at,
        "updatedAt": updated_at,
    }


def _normalize_assignment(entry: dict | None, valid_group_ids: set[str]) -> dict | None:
    if not isinstance(entry, dict):
        return None
    session_id = str(entry.get("sessionId") or "").strip()
    group_id = str(entry.get("groupId") or "").strip()
    if not session_id or not group_id or group_id not in valid_group_ids:
        return None
    return {
        "sessionId": session_id,
        "groupId": group_id,
        "updatedAt": str(entry.get("updatedAt") or "").strip() or _now_iso(),
    }


def _read_state() -> dict:
    path = _state_path()
    if not path.exists():
        return {"groups": [], "assignments": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"groups": [], "assignments": []}
    groups: list[dict] = []
    seen_group_ids: set[str] = set()
    for index, entry in enumerate(payload.get("groups") or []):
        normalized = _normalize_group(entry, index)
        if not normalized or normalized["id"] in seen_group_ids:
            continue
        seen_group_ids.add(normalized["id"])
        groups.append(normalized)
    groups.sort(key=lambda item: (int(item.get("position") or 0), str(item.get("label") or "")))
    groups = [
        {**group, "position": index}
        for index, group in enumerate(groups[:SESSION_ACTIVITY_GROUP_LIMIT])
    ]
    valid_group_ids = {group["id"] for group in groups}
    assignment_by_session_id: dict[str, dict] = {}
    for entry in payload.get("assignments") or []:
        normalized = _normalize_assignment(entry, valid_group_ids)
        if not normalized:
            continue
        assignment_by_session_id[normalized["sessionId"]] = normalized
    assignments = list(assignment_by_session_id.values())[:SESSION_ACTIVITY_GROUP_ASSIGNMENT_LIMIT]
    return {"groups": groups, "assignments": assignments}


def _write_state(state: dict, reason: str) -> None:
    path = _state_path()
    groups = list(state.get("groups") or [])
    assignments = list(state.get("assignments") or [])
    if not groups and not assignments:
        if path.exists():
            path.unlink()
        return
    payload = {
        "version": 1,
        "savedAt": _now_iso(),
        "reason": reason,
        "groups": groups,
        "assignments": assignments,
    }
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _session_aliases(session: dict | None) -> set[str]:
    aliases: set[str] = set()
    if not isinstance(session, dict):
        return aliases
    for field in ("session_id", "_lineage_root_id", "_lineage_tip_id", "parent_session_id"):
        value = str(session.get(field) or "").strip()
        if value:
            aliases.add(value)
    return aliases


def _canonical_assignment_session_id(session_id: str) -> str:
    requested = str(session_id or "").strip()
    if not requested:
        return ""
    for session in all_sessions():
        if requested not in _session_aliases(session):
            continue
        return str(session.get("_lineage_root_id") or session.get("session_id") or requested).strip() or requested
    return requested


def _session_has_live_stream(session: dict) -> bool:
    # active_stream_id is durable sidecar state and can survive a crashed or
    # restarted WebUI process. all_sessions() overlays is_streaming from the
    # in-process STREAMS registry, so only that runtime flag proves a stream is
    # currently alive. This keeps stale first-turn sidecars out of the ops
    # dashboard activity list while preserving durable ops run state.
    return bool(session.get("is_streaming"))


def _activity_status(session: dict) -> dict | None:
    run = session.get("ops_run") if isinstance(session.get("ops_run"), dict) else {}
    run_status = str(run.get("status") or "").strip().lower()
    has_live_stream = _session_has_live_stream(session)
    if session.get("waitingForApproval") or run_status == "waiting-approval":
        return {
            "key": "approval",
            "toneClass": "approval",
            "labelText": "Codex needs approval",
            "title": "Codex is waiting for approval in this session.",
        }
    if session.get("waitingForInput") or run_status == "waiting-input":
        return {
            "key": "waiting",
            "toneClass": "waiting",
            "labelText": "Codex needs input",
            "title": "Codex is waiting for input in this session.",
        }
    if has_live_stream:
        return {
            "key": "active",
            "toneClass": "active",
            "labelText": "Codex is working",
            "title": "Codex is actively processing this session.",
        }
    if session.get("pending_user_message") or run_status in {"queued", "starting"}:
        return {
            "key": "connecting",
            "toneClass": "connecting",
            "labelText": "Connecting to Codex",
            "title": "Connecting to Codex for live session state.",
        }
    if run_status == "running":
        return {
            "key": "active",
            "toneClass": "active",
            "labelText": "Codex is working",
            "title": "Codex is actively processing this session.",
        }
    if run_status == "failed":
        return {
            "key": "degraded",
            "toneClass": "degraded",
            "labelText": "Codex degraded",
            "title": "Codex app-server is degraded for this session.",
        }
    if run_status in {"stopped", "succeeded"}:
        return {
            "key": "done",
            "toneClass": "done",
            "labelText": "Codex completed",
            "title": "Completion has been detected for this session.",
        }
    return None


def _is_activity_session(session: dict) -> bool:
    if not isinstance(session, dict) or session.get("archived"):
        return False
    run = session.get("ops_run") if isinstance(session.get("ops_run"), dict) else {}
    run_status = str(run.get("status") or "").strip().lower()
    task = session.get("ops_task") if isinstance(session.get("ops_task"), dict) else {}
    if session.get("waitingForApproval") or session.get("waitingForInput"):
        return True
    if _session_has_live_stream(session):
        return True
    if str(task.get("id") or "").strip() and task.get("done") is not True:
        return True
    return run_status in _ACTIVE_RUN_STATUSES


def _activity_title(session: dict) -> str:
    for candidate in (
        session.get("label"),
        ((session.get("ops_task") or {}).get("text") if isinstance(session.get("ops_task"), dict) else ""),
        session.get("title"),
        session.get("branchLabel"),
        session.get("repositoryLabel"),
    ):
        value = str(candidate or "").strip()
        if value:
            return value
    return "Untitled"


def _activity_project_name(session: dict) -> str:
    return str(
        session.get("projectName")
        or session.get("repositoryLabel")
        or session.get("branchLabel")
        or "Default workspace"
    ).strip() or "Default workspace"


def _activity_repo_label(session: dict) -> str:
    return str(session.get("repositoryLabel") or _activity_project_name(session)).strip()


def _activity_last_output_at(session: dict, run: dict) -> float | None:
    for candidate in (
        ((run.get("readableOutput") or {}).get("updatedAt") if isinstance(run, dict) else None),
        session.get("lastOutputAt"),
        session.get("lastActivityAt"),
        session.get("updated_at"),
        session.get("last_message_at"),
        session.get("created_at"),
    ):
        stamp = _epoch_seconds(candidate)
        if stamp > 0:
            return stamp
    return None


def _serialize_activity_session(session: dict, assignment_map: dict[str, str]) -> dict:
    run = session.get("ops_run") if isinstance(session.get("ops_run"), dict) else {}
    group_id = None
    for alias in _session_aliases(session):
        if alias in assignment_map:
            group_id = assignment_map[alias]
            break
    status = _activity_status(session) or {
        "key": "idle",
        "toneClass": "idle",
        "labelText": "Quiet",
        "title": "No recent Codex activity detected for this session.",
    }
    last_output_at = _activity_last_output_at(session, run)
    readable_output = run.get("readableOutput") if isinstance(run.get("readableOutput"), dict) else {}
    task = session.get("ops_task") if isinstance(session.get("ops_task"), dict) else {}
    return {
        "id": str(session.get("session_id") or "").strip(),
        "projectId": str(session.get("ops_project_id") or session.get("projectId") or "").strip() or None,
        "projectName": _activity_project_name(session),
        "repoLabel": _activity_repo_label(session),
        "branchLabel": str(session.get("branchLabel") or "").strip() or None,
        "label": _activity_title(session),
        "taskId": str(task.get("id") or "").strip() or None,
        "taskText": str(task.get("text") or "").strip() or None,
        "lastActive": session.get("updated_at"),
        "lastOutputAt": last_output_at,
        "outputSequence": max(0, int(session.get("message_count") or 0)),
        "notificationFlowState": "running",
        "approvalPromptVisible": False,
        "promptVisible": False,
        "promptLine": None,
        "waitingForInput": bool(session.get("waitingForInput")),
        "waitingForInputSince": session.get("waitingSince"),
        "readableOutputPending": bool(readable_output.get("available")),
        "readableOutputUpdatedAt": readable_output.get("updatedAt"),
        "groupId": group_id,
        "running": True,
        "activityStatus": status,
    }


def _list_ops_activity_source() -> dict:
    try:
        return ops_sessions.list_ops_sessions(activity_only=True)
    except TypeError:
        # Tests and older compatibility shims may monkeypatch list_ops_sessions
        # with the historical no-argument callable. Fall back without losing the
        # endpoint entirely.
        return ops_sessions.list_ops_sessions()


def list_session_activity() -> dict:
    state = _read_state()
    assignment_map = {
        str(entry.get("sessionId") or "").strip(): str(entry.get("groupId") or "").strip()
        for entry in state.get("assignments") or []
        if str(entry.get("sessionId") or "").strip() and str(entry.get("groupId") or "").strip()
    }
    try:
        source = _list_ops_activity_source()
    except Exception:
        source = {"sessions": []}
    sessions = [
        _serialize_activity_session(session, assignment_map)
        for session in source.get("sessions") or []
        if _is_activity_session(session)
    ]
    sessions.sort(
        key=lambda item: (
            float(item.get("lastOutputAt") or 0.0),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    return {
        "generatedAt": _now_iso(),
        "detectionMode": "ops_run_state",
        "refreshIntervalMs": SESSION_ACTIVITY_REFRESH_INTERVAL_MS,
        "groupCount": len(state.get("groups") or []),
        "groups": state.get("groups") or [],
        "sessionCount": len(sessions),
        "sessions": sessions,
    }


def create_session_activity_group(label: str) -> dict:
    state = _read_state()
    if len(state["groups"]) >= SESSION_ACTIVITY_GROUP_LIMIT:
        raise SessionActivityError(f"Group limit reached ({SESSION_ACTIVITY_GROUP_LIMIT}).")
    normalized_label = _normalize_group_label(label)
    if not normalized_label:
        raise SessionActivityError("Group label is required.")
    now_iso = _now_iso()
    group = {
        "id": uuid.uuid4().hex,
        "label": normalized_label,
        "position": len(state["groups"]),
        "createdAt": now_iso,
        "updatedAt": now_iso,
    }
    state["groups"].append(group)
    _write_state(state, "session_activity_group_created")
    return group


def rename_session_activity_group(group_id: str, label: str) -> dict:
    state = _read_state()
    normalized_group_id = str(group_id or "").strip()
    normalized_label = _normalize_group_label(label)
    if not normalized_group_id:
        raise SessionActivityError("Group id is required.")
    if not normalized_label:
        raise SessionActivityError("Group label is required.")
    target = next((group for group in state["groups"] if group["id"] == normalized_group_id), None)
    if not target:
        raise SessionActivityError("Group not found.", 404)
    target["label"] = normalized_label
    target["updatedAt"] = _now_iso()
    _write_state(state, "session_activity_group_updated")
    return target


def delete_session_activity_group(group_id: str) -> dict:
    state = _read_state()
    normalized_group_id = str(group_id or "").strip()
    if not normalized_group_id:
        raise SessionActivityError("Group id is required.")
    groups = [group for group in state["groups"] if group["id"] != normalized_group_id]
    if len(groups) == len(state["groups"]):
        raise SessionActivityError("Group not found.", 404)
    removed_assignment_count = sum(
        1 for entry in state["assignments"] if entry.get("groupId") == normalized_group_id
    )
    state["groups"] = [
        {**group, "position": index}
        for index, group in enumerate(groups)
    ]
    state["assignments"] = [
        entry for entry in state["assignments"] if entry.get("groupId") != normalized_group_id
    ]
    _write_state(state, "session_activity_group_deleted")
    return {
        "groupId": normalized_group_id,
        "removedAssignmentCount": removed_assignment_count,
    }


def set_session_activity_group_assignment(session_id: str, group_id: str | None) -> dict:
    state = _read_state()
    canonical_session_id = _canonical_assignment_session_id(session_id)
    if not canonical_session_id:
        raise SessionActivityError("Session id is required.")
    normalized_group_id = str(group_id or "").strip() or None
    if normalized_group_id and not any(group["id"] == normalized_group_id for group in state["groups"]):
        raise SessionActivityError("Group not found.", 404)
    existing_index = next(
        (
            index
            for index, entry in enumerate(state["assignments"])
            if str(entry.get("sessionId") or "").strip() == canonical_session_id
        ),
        -1,
    )
    if normalized_group_id is None:
        if existing_index < 0:
            return {"sessionId": canonical_session_id, "groupId": None, "changed": False}
        state["assignments"].pop(existing_index)
        _write_state(state, "session_activity_group_assignment_cleared")
        return {"sessionId": canonical_session_id, "groupId": None, "changed": True}
    if existing_index < 0 and len(state["assignments"]) >= SESSION_ACTIVITY_GROUP_ASSIGNMENT_LIMIT:
        raise SessionActivityError(
            f"Session group assignment limit reached ({SESSION_ACTIVITY_GROUP_ASSIGNMENT_LIMIT})."
        )
    assignment = {
        "sessionId": canonical_session_id,
        "groupId": normalized_group_id,
        "updatedAt": _now_iso(),
    }
    if existing_index >= 0:
        state["assignments"][existing_index] = assignment
    else:
        state["assignments"].append(assignment)
    _write_state(state, "session_activity_group_assignment_updated")
    return {"sessionId": canonical_session_id, "groupId": normalized_group_id, "changed": True}

"""Fork-owned workflow notification helpers for the clean restart branch."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from api.config import STATE_DIR
from api import ops_projects, ops_sessions, session_sidecars

try:
    from api.clarify import get_pending as get_pending_clarify, resolve_clarify
except ImportError:
    get_pending_clarify = lambda *a, **k: None
    resolve_clarify = lambda *a, **k: 0


class OpsNotificationError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


_APPROVAL_FALLBACK_PENDING: dict[str, object] = {}
_APPROVAL_FALLBACK_LOCK = threading.Lock()
_APPROVAL_FALLBACK_PERMANENT_APPROVED: set[str] = set()
OPS_NOTIFICATION_DISMISSALS_FILE = STATE_DIR / "ops" / "notification_dismissals.json"
_DISMISSAL_LOCK = threading.RLock()
_MAX_STORED_DISMISSALS = 1000


def _text(value: Any, *, limit: int = 512) -> str:
    if not isinstance(value, str):
        value = "" if value is None else str(value)
    return value.strip()[:limit]


def _normalize_dismissal(entry: Any) -> dict | None:
    if isinstance(entry, str):
        notification_id = _text(entry, limit=256)
        dismissed_at = 0.0
    elif isinstance(entry, dict):
        notification_id = _text(entry.get("id") or entry.get("notificationId"), limit=256)
        try:
            dismissed_at = float(entry.get("dismissedAt") or entry.get("dismissed_at") or 0)
        except (TypeError, ValueError):
            dismissed_at = 0.0
    else:
        return None
    if not notification_id:
        return None
    return {"id": notification_id, "dismissedAt": dismissed_at}


def _read_dismissals() -> list[dict]:
    try:
        parsed = json.loads(OPS_NOTIFICATION_DISMISSALS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []
    source = parsed.get("dismissals") if isinstance(parsed, dict) else parsed
    if not isinstance(source, list):
        return []
    seen: set[str] = set()
    items: list[dict] = []
    for entry in source:
        normalized = _normalize_dismissal(entry)
        if not normalized or normalized["id"] in seen:
            continue
        seen.add(normalized["id"])
        items.append(normalized)
    items.sort(key=lambda item: float(item.get("dismissedAt") or 0), reverse=True)
    return items[:_MAX_STORED_DISMISSALS]


def _write_dismissals(items: list[dict]) -> None:
    OPS_NOTIFICATION_DISMISSALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OPS_NOTIFICATION_DISMISSALS_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"dismissals": items[:_MAX_STORED_DISMISSALS]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(OPS_NOTIFICATION_DISMISSALS_FILE)


def list_dismissed_notifications() -> dict:
    with _DISMISSAL_LOCK:
        dismissals = _read_dismissals()
    return {
        "dismissed": [item["id"] for item in dismissals],
        "dismissals": dismissals,
        "count": len(dismissals),
    }


def dismiss_notification(body: dict | None = None) -> dict:
    payload = body if isinstance(body, dict) else {}
    notification_id = _text(payload.get("notificationId") or payload.get("id"), limit=256)
    if not notification_id:
        raise OpsNotificationError("notificationId is required.")
    with _DISMISSAL_LOCK:
        dismissals = [item for item in _read_dismissals() if item.get("id") != notification_id]
        dismissal = {"id": notification_id, "dismissedAt": time.time()}
        dismissals.insert(0, dismissal)
        dismissals = dismissals[:_MAX_STORED_DISMISSALS]
        _write_dismissals(dismissals)
    return {"ok": True, "notificationId": notification_id, "dismissed": True}


def _approval_runtime() -> dict[str, object]:
    try:
        from api import routes as api_routes

        return {
            "approve_permanent": api_routes.approve_permanent,
            "approve_session": api_routes.approve_session,
            "lock": api_routes._lock,
            "notify_locked": getattr(api_routes, "_approval_sse_notify_locked", None),
            "pending": api_routes._pending,
            "permanent_approved": api_routes._permanent_approved,
            "resolve_gateway_approval": api_routes.resolve_gateway_approval,
            "save_permanent_allowlist": api_routes.save_permanent_allowlist,
        }
    except Exception:
        return {
            "approve_permanent": lambda *a, **k: None,
            "approve_session": lambda *a, **k: None,
            "lock": _APPROVAL_FALLBACK_LOCK,
            "notify_locked": None,
            "pending": _APPROVAL_FALLBACK_PENDING,
            "permanent_approved": _APPROVAL_FALLBACK_PERMANENT_APPROVED,
            "resolve_gateway_approval": lambda *a, **k: 0,
            "save_permanent_allowlist": lambda *a, **k: None,
        }


def _pending_approval(session_id: str) -> dict:
    sid = str(session_id or "").strip()
    runtime = _approval_runtime()
    with runtime["lock"]:
        queue = runtime["pending"].get(sid)
        if isinstance(queue, list):
            pending = dict(queue[0]) if queue else None
            total = len(queue)
        elif queue:
            pending = dict(queue)
            total = 1
        else:
            pending = None
            total = 0
    if isinstance(pending, dict):
        pending = {**pending, "sessionId": sid}
    return {"pending": pending, "pending_count": total}


def _pending_clarify(session_id: str) -> dict:
    sid = str(session_id or "").strip()
    pending = get_pending_clarify(sid)
    if isinstance(pending, dict):
        pending = {**pending, "sessionId": sid}
    return {"pending": pending or None, "pending_count": 1 if pending else 0}


def _task_context(project_id: str, task_id: str) -> dict:
    try:
        resolved = ops_projects.get_ops_project_task(project_id, task_id)
        return {
            "project": resolved["project"],
            "task": resolved["task"],
            "epicId": resolved["epicId"],
        }
    except ops_projects.OpsProjectError:
        project = ops_projects.get_ops_project(project_id)
        return {
            "project": project,
            "task": {"id": task_id, "text": "Task unavailable", "grade": "green", "done": False},
            "epicId": "",
        }


def _approval_notification(linkage: dict, task_context: dict, pending: dict, pending_count: int) -> dict:
    pattern_keys = pending.get("pattern_keys") or [pending.get("pattern_key", "")]
    return {
        "notificationKey": "approval:" + str(linkage.get("sessionId") or "") + ":" + str(pending.get("approval_id") or ""),
        "kind": "approval",
        "sessionId": linkage.get("sessionId"),
        "sessionUrl": linkage.get("sessionUrl") or ops_sessions.session_url(str(linkage.get("sessionId") or "")),
        "session": linkage.get("session"),
        "available": linkage.get("available", True),
        "project": {
            "id": task_context["project"]["id"],
            "name": task_context["project"].get("name"),
        },
        "task": {
            "id": task_context["task"].get("id"),
            "text": task_context["task"].get("text"),
            "grade": task_context["task"].get("grade"),
            "done": task_context["task"].get("done"),
        },
        "approvalId": pending.get("approval_id"),
        "description": str(pending.get("description") or "").strip(),
        "command": str(pending.get("command") or "").strip(),
        "patternKeys": [str(value).strip() for value in pattern_keys if str(value).strip()],
        "pendingCount": pending_count,
    }


def _clarify_notification(linkage: dict, task_context: dict, pending: dict, pending_count: int) -> dict:
    choices = pending.get("choices_offered")
    if not isinstance(choices, list):
        choices = pending.get("choices") if isinstance(pending.get("choices"), list) else []
    return {
        "notificationKey": "clarify:" + str(linkage.get("sessionId") or "") + ":" + str(pending.get("requested_at") or ""),
        "kind": "clarify",
        "sessionId": linkage.get("sessionId"),
        "sessionUrl": linkage.get("sessionUrl") or ops_sessions.session_url(str(linkage.get("sessionId") or "")),
        "session": linkage.get("session"),
        "available": linkage.get("available", True),
        "project": {
            "id": task_context["project"]["id"],
            "name": task_context["project"].get("name"),
        },
        "task": {
            "id": task_context["task"].get("id"),
            "text": task_context["task"].get("text"),
            "grade": task_context["task"].get("grade"),
            "done": task_context["task"].get("done"),
        },
        "question": str(pending.get("question") or pending.get("description") or "").strip(),
        "choices": [str(value).strip() for value in choices if str(value).strip()],
        "pendingCount": pending_count,
        "requestedAt": pending.get("requested_at"),
        "timeoutSeconds": pending.get("timeout_seconds"),
        "expiresAt": pending.get("expires_at"),
    }


def list_pending_notifications(project_id: str | None = None) -> dict:
    if project_id:
        projects = [ops_projects.get_ops_project(project_id)]
    else:
        projects = list(ops_projects.list_ops_projects().get("projects") or [])

    notifications = []
    for project in projects:
        for linkage in session_sidecars.list_project_linkages(project["id"]):
            session_id = str(linkage.get("sessionId") or "").strip()
            task_id = str(linkage.get("taskId") or "").strip()
            if not session_id or not task_id:
                continue
            task_context = _task_context(project["id"], task_id)
            approval = _pending_approval(session_id)
            if approval.get("pending"):
                notifications.append(
                    _approval_notification(linkage, task_context, approval["pending"], int(approval.get("pending_count") or 0))
                )
            clarify = _pending_clarify(session_id)
            if clarify.get("pending"):
                notifications.append(
                    _clarify_notification(linkage, task_context, clarify["pending"], int(clarify.get("pending_count") or 0))
                )

    notifications.sort(
        key=lambda item: (
            str(item.get("kind") or ""),
            float(item.get("expiresAt") or item.get("requestedAt") or 0),
            str(item.get("sessionId") or ""),
        ),
        reverse=True,
    )
    return {"notifications": notifications, "count": len(notifications)}


def _respond_approval(body: dict) -> dict:
    sid = str(body.get("sessionId") or body.get("session_id") or "").strip()
    if not sid:
        raise OpsNotificationError("sessionId is required.")
    choice = str(body.get("choice") or "deny").strip()
    if choice not in ("once", "session", "always", "deny"):
        raise OpsNotificationError(f"Invalid choice: {choice}")
    approval_id = str(body.get("approvalId") or body.get("approval_id") or "").strip()

    runtime = _approval_runtime()
    pending = None
    with runtime["lock"]:
        queue = runtime["pending"].get(sid)
        if isinstance(queue, list):
            if approval_id:
                for index, entry in enumerate(queue):
                    if entry.get("approval_id") == approval_id:
                        pending = queue.pop(index)
                        break
                else:
                    pending = queue.pop(0) if queue else None
            else:
                pending = queue.pop(0) if queue else None
            if not queue:
                runtime["pending"].pop(sid, None)
        elif queue:
            pending = runtime["pending"].pop(sid, None)

        notify_locked = runtime["notify_locked"]
        remaining = runtime["pending"].get(sid)
        if notify_locked:
            if isinstance(remaining, list) and remaining:
                notify_locked(sid, remaining[0], len(remaining))
            else:
                notify_locked(sid, None, 0)

    if pending:
        keys = pending.get("pattern_keys") or [pending.get("pattern_key", "")]
        if choice in ("once", "session"):
            for key in keys:
                runtime["approve_session"](sid, key)
        elif choice == "always":
            for key in keys:
                runtime["approve_session"](sid, key)
                runtime["approve_permanent"](key)
            runtime["save_permanent_allowlist"](runtime["permanent_approved"])

    runtime["resolve_gateway_approval"](sid, choice, resolve_all=False)
    return {"ok": True, "kind": "approval", "choice": choice, "sessionId": sid}


def _respond_clarify(body: dict) -> dict:
    sid = str(body.get("sessionId") or body.get("session_id") or "").strip()
    if not sid:
        raise OpsNotificationError("sessionId is required.")
    response = body.get("response")
    if response is None:
        response = body.get("answer")
    if response is None:
        response = body.get("choice")
    response = str(response or "").strip()
    if not response:
        raise OpsNotificationError("response is required.")
    resolve_clarify(sid, response, resolve_all=False)
    return {"ok": True, "kind": "clarify", "response": response, "sessionId": sid}


def respond_pending_notification(body: dict | None = None) -> dict:
    payload = body if isinstance(body, dict) else {}
    kind = str(payload.get("kind") or "").strip().lower()
    if kind == "approval":
        return _respond_approval(payload)
    if kind == "clarify":
        return _respond_clarify(payload)
    raise OpsNotificationError("kind must be approval or clarify.")

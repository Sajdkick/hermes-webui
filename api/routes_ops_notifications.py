"""Fork-owned workflow notification routes for the clean restart branch."""

from __future__ import annotations

from api.helpers import j
from api import ops_notifications, ops_projects


def handle_get(handler, parsed) -> bool:
    try:
        if parsed.path == "/api/ops/notifications/pending":
            j(handler, ops_notifications.list_pending_notifications())
            return True
        if parsed.path == "/api/ops/notifications/dismissed":
            j(handler, ops_notifications.list_dismissed_notifications())
            return True
        return False
    except (ops_notifications.OpsNotificationError, ops_projects.OpsProjectError) as exc:  # type: ignore[name-defined]
        j(handler, {"error": str(exc)}, status=exc.status)
        return True


def handle_post(handler, parsed, body: dict) -> bool:
    try:
        if parsed.path == "/api/ops/notifications/respond":
            j(handler, ops_notifications.respond_pending_notification(body))
            return True
        if parsed.path == "/api/ops/notifications/dismiss":
            j(handler, ops_notifications.dismiss_notification(body))
            return True
        return False
    except (ops_notifications.OpsNotificationError, ops_projects.OpsProjectError) as exc:  # type: ignore[name-defined]
        j(handler, {"error": str(exc)}, status=exc.status)
        return True

"""Routes for Cloud Terminal-style session activity compatibility."""

from __future__ import annotations

import re
from urllib.parse import unquote

from api.helpers import bad, j
from api import session_activity


_SESSION_ACTIVITY_RE = re.compile(r"^/api/sessions/activity/?$")
_SESSION_ACTIVITY_GROUPS_RE = re.compile(r"^/api/sessions/activity/groups/?$")
_SESSION_ACTIVITY_GROUP_RENAME_RE = re.compile(r"^/api/sessions/activity/groups/([^/]+)/rename/?$")
_SESSION_ACTIVITY_GROUP_DELETE_RE = re.compile(r"^/api/sessions/activity/groups/([^/]+)/delete/?$")
_SESSION_ACTIVITY_ASSIGNMENT_RE = re.compile(r"^/api/sessions/activity/group-assignment/?$")


def handle_get(handler, parsed) -> bool:
    if not _SESSION_ACTIVITY_RE.match(parsed.path):
        return False
    try:
        j(handler, session_activity.list_session_activity())
    except session_activity.SessionActivityError as exc:
        bad(handler, str(exc), exc.status)
        return True
    return True


def handle_post(handler, parsed, body: dict) -> bool:
    if _SESSION_ACTIVITY_GROUPS_RE.match(parsed.path):
        try:
            group = session_activity.create_session_activity_group(body.get("label"))
        except session_activity.SessionActivityError as exc:
            bad(handler, str(exc), exc.status)
            return True
        j(handler, {"success": True, "group": group}, status=201)
        return True

    match = _SESSION_ACTIVITY_GROUP_RENAME_RE.match(parsed.path)
    if match:
        try:
            group = session_activity.rename_session_activity_group(
                unquote(match.group(1)),
                body.get("label"),
            )
        except session_activity.SessionActivityError as exc:
            bad(handler, str(exc), exc.status)
            return True
        j(handler, {"success": True, "group": group})
        return True

    match = _SESSION_ACTIVITY_GROUP_DELETE_RE.match(parsed.path)
    if match:
        try:
            result = session_activity.delete_session_activity_group(unquote(match.group(1)))
        except session_activity.SessionActivityError as exc:
            bad(handler, str(exc), exc.status)
            return True
        j(handler, {"success": True, **result})
        return True

    if _SESSION_ACTIVITY_ASSIGNMENT_RE.match(parsed.path):
        try:
            result = session_activity.set_session_activity_group_assignment(
                body.get("sessionId") or body.get("session_id"),
                body.get("groupId"),
            )
        except session_activity.SessionActivityError as exc:
            bad(handler, str(exc), exc.status)
            return True
        j(handler, {"success": True, **result})
        return True

    return False

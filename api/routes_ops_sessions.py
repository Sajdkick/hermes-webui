"""Fork-owned ops session routes for the clean restart branch."""

from __future__ import annotations

import re
from urllib.parse import parse_qs

from api.helpers import bad, j
from api import ops_sessions


_OPS_SESSIONS_RE = re.compile(r"^/api/ops/sessions/?$")


def handle_get(handler, parsed) -> bool:
    if _OPS_SESSIONS_RE.match(parsed.path):
        try:
            project_id = parse_qs(parsed.query).get("projectId", [""])[0] or None
            j(handler, ops_sessions.list_ops_sessions(project_id))
        except ops_sessions.OpsSessionError as exc:
            return bad(handler, str(exc), exc.status)
        return True

    return False

"""Fork-owned project-scoped upstream-sync routes for the clean restart branch."""

from __future__ import annotations

import re

from api.helpers import j
from api import ops_upstream_sync


_PROJECT_UPSTREAM_SYNC_RE = re.compile(r"^/api/ops/projects/([^/]+)/upstream-sync/?$")
_PROJECT_UPSTREAM_SYNC_START_RE = re.compile(r"^/api/ops/projects/([^/]+)/upstream-sync/start/?$")
_PROJECT_UPSTREAM_SYNC_APPLY_RE = re.compile(r"^/api/ops/projects/([^/]+)/upstream-sync/apply/?$")


def handle_get(handler, parsed) -> bool:
    try:
        match = _PROJECT_UPSTREAM_SYNC_RE.match(parsed.path)
        if match:
            j(handler, ops_upstream_sync.list_project_upstream_sync(match.group(1)))
            return True
        return False
    except ops_upstream_sync.OpsUpstreamSyncError as exc:
        j(handler, {"error": str(exc)}, status=exc.status)
        return True


def handle_post(handler, parsed, body: dict) -> bool:
    try:
        match = _PROJECT_UPSTREAM_SYNC_START_RE.match(parsed.path)
        if match:
            j(handler, ops_upstream_sync.start_project_upstream_sync(match.group(1), body), status=201)
            return True
        match = _PROJECT_UPSTREAM_SYNC_APPLY_RE.match(parsed.path)
        if match:
            j(handler, ops_upstream_sync.apply_project_upstream_sync(match.group(1), body))
            return True
        return False
    except ops_upstream_sync.OpsUpstreamSyncError as exc:
        j(handler, {"error": str(exc)}, status=exc.status)
        return True

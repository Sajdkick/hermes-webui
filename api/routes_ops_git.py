"""Fork-owned project git status and operation routes for the clean restart branch."""

from __future__ import annotations

import re
from urllib.parse import unquote

from api.helpers import j
from api import ops_git


_PROJECT_GIT_STATUS_RE = re.compile(r"^/api/ops/projects/([^/]+)/git/status/?$")
_PROJECT_GIT_OPERATION_RE = re.compile(r"^/api/ops/projects/([^/]+)/git/(push|sync)/?$")


def handle_get(handler, parsed) -> bool:
    match = _PROJECT_GIT_STATUS_RE.match(parsed.path)
    if not match:
        return False
    try:
        j(handler, {"git": ops_git.get_project_git_status(unquote(match.group(1)))})
    except ops_git.OpsGitError as exc:
        j(handler, {"error": str(exc)}, status=exc.status)
    return True


def handle_post(handler, parsed, body: dict) -> bool:
    match = _PROJECT_GIT_OPERATION_RE.match(parsed.path)
    if not match:
        return False
    try:
        project_id = unquote(match.group(1))
        operation = unquote(match.group(2))
        j(handler, {"operation": ops_git.execute_project_git_operation(project_id, operation, body)})
    except ops_git.OpsGitError as exc:
        j(handler, {"error": str(exc)}, status=exc.status)
    return True

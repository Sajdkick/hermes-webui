"""Fork-owned GitHub admin routes for the clean restart branch."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote

from api.helpers import j
from api import ops_github


_GITHUB_STATUS_RE = re.compile(r"^/api/ops/github/status/?$")
_GITHUB_REPOS_RE = re.compile(r"^/api/ops/github/repos/?$")
_GITHUB_BRANCHES_RE = re.compile(r"^/api/ops/github/repos/([^/]+)/([^/]+)/branches/?$")
_GITHUB_IMPORT_RE = re.compile(r"^/api/ops/github/import/?$")


def handle_get(handler, parsed) -> bool:
    try:
        if _GITHUB_STATUS_RE.match(parsed.path):
            j(handler, ops_github.github_status())
            return True
        if _GITHUB_REPOS_RE.match(parsed.path):
            filters = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
            j(handler, ops_github.list_repositories(filters))
            return True
        match = _GITHUB_BRANCHES_RE.match(parsed.path)
        if match:
            filters = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
            j(handler, ops_github.list_branches(unquote(match.group(1)), unquote(match.group(2)), filters))
            return True
        return False
    except ops_github.OpsGitHubError as exc:
        j(handler, {"error": str(exc)}, status=exc.status)
        return True


def handle_post(handler, parsed, body: dict) -> bool:
    try:
        if _GITHUB_IMPORT_RE.match(parsed.path):
            j(handler, {"ok": True, **ops_github.import_repository(body)}, status=201)
            return True
        return False
    except ops_github.OpsGitHubError as exc:
        j(handler, {"error": str(exc)}, status=exc.status)
        return True

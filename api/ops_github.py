"""Fork-owned GitHub discovery and import helpers."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from api import ops_projects


GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
TOKEN_ENV_NAMES = ("HERMES_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_CLONE_TIMEOUT_SECONDS = 600
DEFAULT_REPO_LIMIT = 30
MAX_REPO_LIMIT = 100
_GITHUB_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class OpsGitHubError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _text(value: Any, *, limit: int = 512) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _limit(value: Any, *, default: int = DEFAULT_REPO_LIMIT, maximum: int = MAX_REPO_LIMIT) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(maximum, parsed))


def _token_info() -> dict:
    for name in TOKEN_ENV_NAMES:
        value = os.getenv(name, "").strip()
        if value:
            return {"token": value, "envName": name}
    return {"token": "", "envName": ""}


def _headers(token: str = "") -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "hermes-webui-ops-shell",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_url(path: str, params: dict[str, Any] | None = None) -> str:
    base = GITHUB_API_BASE.rstrip("/")
    clean_path = "/" + path.lstrip("/")
    query = urlparse.urlencode({key: str(value) for key, value in (params or {}).items() if value not in (None, "")})
    return f"{base}{clean_path}{'?' + query if query else ''}"


def _error_message(exc: urlerror.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="replace")
        parsed = json.loads(raw) if raw else {}
    except Exception:
        parsed = {}
    message = _text(parsed.get("message") if isinstance(parsed, dict) else "", limit=1000)
    if message:
        return message
    reason = _text(getattr(exc, "reason", ""), limit=200)
    return reason or f"GitHub request failed with HTTP {exc.code}."


def _api_get(path: str, params: dict[str, Any] | None = None, *, token: str = "") -> Any:
    request = urlrequest.Request(_github_url(path, params), headers=_headers(token))
    try:
        with urlrequest.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except urlerror.HTTPError as exc:
        raise OpsGitHubError(_error_message(exc), exc.code) from exc
    except urlerror.URLError as exc:
        reason = _text(getattr(exc, "reason", ""), limit=300)
        raise OpsGitHubError(reason or "Unable to reach GitHub.", 502) from exc
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError as exc:
        raise OpsGitHubError("GitHub returned invalid JSON.", 502) from exc


def _require_token() -> dict:
    info = _token_info()
    if not info["token"]:
        raise OpsGitHubError("Set HERMES_GITHUB_TOKEN, GITHUB_TOKEN, or GH_TOKEN to list GitHub repositories.", 401)
    return info


def _repo_owner(repo: dict) -> str:
    owner = repo.get("owner")
    if isinstance(owner, dict):
        return _text(owner.get("login"), limit=128)
    return ""


def _repo_from_api(repo: dict) -> dict:
    owner = _repo_owner(repo)
    name = _text(repo.get("name"), limit=256)
    full_name = _text(repo.get("full_name"), limit=512) or f"{owner}/{name}".strip("/")
    return {
        "id": repo.get("id"),
        "owner": owner,
        "name": name,
        "fullName": full_name,
        "description": _text(repo.get("description"), limit=1000),
        "private": bool(repo.get("private")),
        "fork": bool(repo.get("fork")),
        "archived": bool(repo.get("archived")),
        "disabled": bool(repo.get("disabled")),
        "defaultBranch": _text(repo.get("default_branch"), limit=256) or "main",
        "language": _text(repo.get("language"), limit=128),
        "htmlUrl": _text(repo.get("html_url"), limit=2048),
        "cloneUrl": _text(repo.get("clone_url"), limit=2048),
        "sshUrl": _text(repo.get("ssh_url"), limit=2048),
        "updatedAt": _text(repo.get("updated_at"), limit=64),
        "pushedAt": _text(repo.get("pushed_at"), limit=64),
    }


def _branch_from_api(branch: dict) -> dict:
    commit = branch.get("commit") if isinstance(branch.get("commit"), dict) else {}
    return {
        "name": _text(branch.get("name"), limit=256),
        "protected": bool(branch.get("protected")),
        "commitSha": _text(commit.get("sha"), limit=128),
        "commitUrl": _text(commit.get("url"), limit=2048),
    }


def _github_name(value: Any, label: str, *, limit: int = 128) -> str:
    name = _text(value, limit=limit)
    if not name:
        raise OpsGitHubError(f"GitHub {label} is required.")
    if not _GITHUB_NAME_RE.match(name):
        raise OpsGitHubError(f"GitHub {label} contains unsupported characters.")
    return name


def _branch_name(value: Any) -> str:
    branch = _text(value, limit=256)
    if not branch:
        return ""
    if branch.startswith("-") or branch.endswith("/") or ".." in branch or "@{" in branch or "\\" in branch:
        raise OpsGitHubError("Git branch name is invalid.")
    if any(ord(char) < 32 or char in " ~^:?*[" for char in branch):
        raise OpsGitHubError("Git branch name is invalid.")
    return branch


def _directory_name(value: Any, fallback: str) -> str:
    raw = _text(value, limit=128) or fallback
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip(".-")
    if name in {"", ".", ".."}:
        name = fallback
    return name[:128] or "repository"


def _default_import_parent() -> Path:
    return ops_projects.ops_projects_metadata_path().parent.resolve()


def _validate_target_path(path: Path) -> None:
    projects_parent = _default_import_parent()
    try:
        path.relative_to(projects_parent)
        return
    except ValueError:
        pass
    try:
        path.relative_to(Path.home().resolve())
        return
    except ValueError:
        pass
    raise OpsGitHubError("GitHub import target must be under the projects directory or the server user's home directory.")


def _target_path(body: dict, repo_name: str) -> Path:
    raw_path = _text(body.get("path"), limit=4096)
    if raw_path:
        target = Path(raw_path).expanduser().resolve()
        _validate_target_path(target)
        return target
    parent = Path(_text(body.get("parentPath"), limit=4096) or _default_import_parent()).expanduser().resolve()
    if parent.exists() and not parent.is_dir():
        raise OpsGitHubError("GitHub import parent path is not a directory.")
    target = (parent / _directory_name(body.get("directoryName"), repo_name)).resolve()
    _validate_target_path(target)
    return target


def _target_is_empty(path: Path) -> bool:
    return not path.exists() or (path.is_dir() and not any(path.iterdir()))


def _clone_url(owner: str, repo: str, protocol: str) -> str:
    normalized = _text(protocol, limit=32).lower()
    if normalized == "ssh":
        return f"git@github.com:{owner}/{repo}.git"
    return f"https://github.com/{owner}/{repo}.git"


def _clone_repository(clone_url: str, target_path: Path, branch: str) -> dict:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["git", "clone"]
    if branch:
        args.extend(["--branch", branch, "--single-branch"])
    args.extend([clone_url, str(target_path)])
    try:
        completed = subprocess.run(
            args,
            check=True,
            capture_output=True,
            text=True,
            timeout=DEFAULT_CLONE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise OpsGitHubError("git is not available on the Hermes server.", 500) from exc
    except subprocess.TimeoutExpired as exc:
        raise OpsGitHubError("GitHub clone timed out.", 504) from exc
    except subprocess.CalledProcessError as exc:
        detail = _text((exc.stderr or exc.stdout or "").strip(), limit=1200)
        raise OpsGitHubError(detail or "GitHub clone failed.", 502) from exc
    return {
        "command": args[:3] + ["..."] if len(args) > 3 else args,
        "stdout": _text(completed.stdout, limit=1200),
        "stderr": _text(completed.stderr, limit=1200),
    }


def _source_repo_path(value: Any) -> Path:
    source = Path(_text(value, limit=4096)).expanduser().resolve()
    if not source.exists() or not source.is_dir():
        raise OpsGitHubError("GitHub worktree source path must be an existing Git checkout.")
    _validate_target_path(source)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(source),
            capture_output=True,
            text=True,
            check=False,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise OpsGitHubError("git is not available on the Hermes server.", 500) from exc
    except subprocess.TimeoutExpired as exc:
        raise OpsGitHubError("GitHub worktree source validation timed out.", 504) from exc
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise OpsGitHubError("GitHub worktree source path is not a Git checkout.")
    return source


def _add_worktree(source_path: Path, target_path: Path, branch: str) -> dict:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["git", "worktree", "add", str(target_path)]
    if branch:
        args.append(branch)
    try:
        completed = subprocess.run(
            args,
            cwd=str(source_path),
            check=True,
            capture_output=True,
            text=True,
            timeout=DEFAULT_CLONE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise OpsGitHubError("git is not available on the Hermes server.", 500) from exc
    except subprocess.TimeoutExpired as exc:
        raise OpsGitHubError("GitHub worktree creation timed out.", 504) from exc
    except subprocess.CalledProcessError as exc:
        detail = _text((exc.stderr or exc.stdout or "").strip(), limit=1200)
        raise OpsGitHubError(detail or "GitHub worktree creation failed.", 502) from exc
    return {
        "command": ["git", "worktree", "add", "..."],
        "stdout": _text(completed.stdout, limit=1200),
        "stderr": _text(completed.stderr, limit=1200),
        "sourcePath": str(source_path),
    }


def github_status() -> dict:
    info = _token_info()
    if not info["token"]:
        return {
            "tokenPresent": False,
            "authenticated": False,
            "tokenSource": "",
            "user": None,
            "message": "No GitHub token is configured.",
        }
    user = _api_get("/user", token=info["token"])
    if not isinstance(user, dict):
        raise OpsGitHubError("GitHub returned an unexpected user response.", 502)
    return {
        "tokenPresent": True,
        "authenticated": True,
        "tokenSource": info["envName"],
        "user": {
            "login": _text(user.get("login"), limit=128),
            "name": _text(user.get("name"), limit=256),
            "avatarUrl": _text(user.get("avatar_url"), limit=2048),
            "htmlUrl": _text(user.get("html_url"), limit=2048),
        },
    }


def list_repositories(filters: dict[str, Any] | None = None) -> dict:
    filters = filters if isinstance(filters, dict) else {}
    info = _require_token()
    limit = _limit(filters.get("limit"))
    query = _text(filters.get("q") or filters.get("query"), limit=256)
    if query:
        payload = _api_get(
            "/search/repositories",
            {"q": query, "sort": "updated", "order": "desc", "per_page": limit},
            token=info["token"],
        )
        items = payload.get("items") if isinstance(payload, dict) else []
        source = "search"
    else:
        payload = _api_get(
            "/user/repos",
            {
                "affiliation": _text(filters.get("affiliation"), limit=128) or "owner,collaborator,organization_member",
                "visibility": _text(filters.get("visibility"), limit=64) or "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": limit,
            },
            token=info["token"],
        )
        items = payload if isinstance(payload, list) else []
        source = "user"
    repositories = [_repo_from_api(repo) for repo in items if isinstance(repo, dict)]
    return {
        "authenticated": True,
        "tokenSource": info["envName"],
        "query": query,
        "limit": limit,
        "source": source,
        "repositories": repositories,
    }


def list_branches(owner: str, repo: str, filters: dict[str, Any] | None = None) -> dict:
    owner = _text(owner, limit=128)
    repo = _text(repo, limit=256)
    if not owner or not repo:
        raise OpsGitHubError("GitHub owner and repository name are required.")
    if "/" in owner or "/" in repo:
        raise OpsGitHubError("GitHub owner and repository name must not contain slashes.")
    info = _token_info()
    limit = _limit((filters or {}).get("limit"), default=100)
    payload = _api_get(
        f"/repos/{urlparse.quote(owner, safe='')}/{urlparse.quote(repo, safe='')}/branches",
        {"per_page": limit},
        token=info["token"],
    )
    branches = [_branch_from_api(branch) for branch in payload if isinstance(branch, dict)] if isinstance(payload, list) else []
    return {
        "authenticated": bool(info["token"]),
        "tokenSource": info["envName"],
        "owner": owner,
        "repo": repo,
        "limit": limit,
        "branches": branches,
    }


def import_repository(body: dict | None = None) -> dict:
    body = body if isinstance(body, dict) else {}
    owner = _github_name(body.get("owner"), "owner")
    repo = _github_name(body.get("repo") or body.get("name"), "repository", limit=256)
    branch = _branch_name(body.get("branch") or body.get("defaultBranch"))
    protocol = _text(body.get("protocol"), limit=32).lower()
    clone_url = _clone_url(owner, repo, protocol)
    target_path = _target_path(body, repo)
    reuse_existing = bool(body.get("reuseExisting"))
    mode = _text(body.get("mode"), limit=32).lower()
    use_worktree = mode == "worktree" or body.get("worktree") is True
    if target_path.exists() and not target_path.is_dir():
        raise OpsGitHubError("GitHub import target exists and is not a directory.", 409)
    if target_path.exists() and not reuse_existing and not _target_is_empty(target_path):
        raise OpsGitHubError("GitHub import target already exists. Choose an empty directory or enable reuseExisting.", 409)

    cloned = False
    worktree = False
    clone_result: dict[str, Any] = {}
    if use_worktree and not reuse_existing:
        source_path = _source_repo_path(body.get("sourcePath") or body.get("source_path"))
        clone_result = _add_worktree(source_path, target_path, branch)
        worktree = True
    elif _target_is_empty(target_path):
        clone_result = _clone_repository(clone_url, target_path, branch)
        cloned = True

    project_name = _text(body.get("projectName") or body.get("name"), limit=128) or repo
    core_branch = branch or _text(body.get("defaultBranch"), limit=256) or "main"
    try:
        project = ops_projects.create_ops_project(
            {
                "name": project_name,
                "fullName": f"{owner}/{repo}",
                "slug": _directory_name(body.get("slug"), repo),
                "path": str(target_path),
                "coreBranch": core_branch,
                "cloneUrl": clone_url,
            }
        )
    except ops_projects.OpsProjectError as exc:
        raise OpsGitHubError(str(exc), exc.status) from exc

    return {
        "imported": True,
        "cloned": cloned,
        "worktree": worktree,
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "cloneUrl": clone_url,
        "targetPath": str(target_path),
        "project": project,
        "clone": clone_result,
    }

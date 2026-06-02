"""Core API Git/GitHub facade."""

from __future__ import annotations

from api import ops_git, ops_github
from api.core_contracts import coerce_core_error, redact_payload

GitCoreError = ops_git.OpsGitError
GitHubCoreError = ops_github.OpsGitHubError


def get_project_git_status(project_id: str) -> dict:
    try:
        return redact_payload(ops_git.get_project_git_status(project_id))
    except ops_git.OpsGitError as exc:
        raise coerce_core_error(exc, code="GIT_ERROR") from exc


def execute_project_git_operation(project_id: str, operation: str, body: dict | None = None) -> dict:
    try:
        return redact_payload(ops_git.execute_project_git_operation(project_id, operation, body or {}))
    except ops_git.OpsGitError as exc:
        raise coerce_core_error(exc, code="GIT_ERROR") from exc


def github_status() -> dict:
    try:
        return redact_payload(ops_github.github_status())
    except ops_github.OpsGitHubError as exc:
        raise coerce_core_error(exc, code="GITHUB_ERROR") from exc


def list_repositories(filters: dict | None = None) -> dict:
    try:
        return redact_payload(ops_github.list_repositories(filters or {}))
    except ops_github.OpsGitHubError as exc:
        raise coerce_core_error(exc, code="GITHUB_ERROR") from exc


def list_branches(owner: str, repo: str, filters: dict | None = None) -> dict:
    try:
        return redact_payload(ops_github.list_branches(owner, repo, filters or {}))
    except ops_github.OpsGitHubError as exc:
        raise coerce_core_error(exc, code="GITHUB_ERROR") from exc


def import_repository(body: dict | None = None) -> dict:
    try:
        return redact_payload(ops_github.import_repository(body or {}))
    except ops_github.OpsGitHubError as exc:
        raise coerce_core_error(exc, code="GITHUB_ERROR") from exc

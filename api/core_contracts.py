"""Shared helpers for the Hermes Core API boundary.

The Core API is intentionally an in-process boundary for now.  Route wrappers
should use this module for stable error envelopes, operation descriptors,
redaction, and path-containment helpers so future service extraction can preserve
one contract.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.helpers import _redact_value, _redact_text

CORE_API_VERSION = "2026-05-26"


class CoreApiError(Exception):
    """Stable Core API exception shape."""

    def __init__(
        self,
        message: str,
        status: int = 400,
        *,
        code: str = "CORE_API_ERROR",
        details: dict | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status = int(status or 400)
        self.code = str(code or "CORE_API_ERROR")
        self.details = details if isinstance(details, dict) else {}
        self.retryable = bool(retryable)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def operation_id(kind: str) -> str:
    prefix = "".join(char if char.isalnum() else "-" for char in str(kind or "operation").lower()).strip("-")
    return f"{prefix or 'operation'}-{uuid.uuid4().hex[:12]}"


def error_payload(exc: Exception) -> dict:
    if isinstance(exc, CoreApiError):
        return {
            "error": _redact_text(str(exc)),
            "code": exc.code,
            "details": redact_payload(exc.details),
            "retryable": exc.retryable,
        }
    return {
        "error": _redact_text(str(exc) or "Core API request failed."),
        "code": "CORE_API_ERROR",
        "details": {},
        "retryable": False,
    }


def coerce_core_error(exc: Exception, *, code: str = "UPSTREAM_DOMAIN_ERROR") -> CoreApiError:
    if isinstance(exc, CoreApiError):
        return exc
    status = int(getattr(exc, "status", 400) or 400)
    return CoreApiError(str(exc), status=status, code=code)


def redact_payload(payload: Any) -> Any:
    return _redact_value(payload)


def public_route_map() -> dict:
    return {
        "version": CORE_API_VERSION,
        "namespace": "/api/core",
        "domains": {
            "projects": ["GET /projects", "GET /projects/{projectId}", "GET /projects/{projectId}/files"],
            "tasks": ["GET /projects/{projectId}/tasks", "POST /projects/{projectId}/tasks"],
            "play": ["GET /projects/{projectId}/play/status", "POST /projects/{projectId}/play/start"],
            "ui": [
                "GET /projects/{projectId}/ui-config-file",
                "GET /projects/{projectId}/ui/status",
                "GET /projects/{projectId}/ui/logs",
                "GET /projects/{projectId}/ui/session",
                "POST /projects/{projectId}/ui/session/reset",
                "POST /projects/{projectId}/ui/session/prune",
                "POST /projects/{projectId}/ui/start",
                "POST /projects/{projectId}/ui/restart",
                "POST /projects/{projectId}/ui/stop",
                "GET /ui-project/{projectId}/...",
            ],
            "deployments": ["GET /deployments/providers", "GET /projects/{projectId}/deployment", "POST /projects/{projectId}/deployment/redeploy"],
            "database": ["GET /database/settings", "POST /projects/{projectId}/database/inspect/query"],
            "git": ["GET /projects/{projectId}/git/status", "POST /projects/{projectId}/git/{operation}"],
            "github": ["GET /github/status", "GET /github/repos"],
            "runtime": ["GET /projects/{projectId}/runtime/summary", "POST /projects/{projectId}/runtime/inspect/snapshot"],
            "host": ["GET /host/health", "GET /host/proxy"],
            "sessionActivity": ["GET /session-activity", "POST /session-activity/groups"],
        },
    }


def capabilities() -> dict:
    route_map = public_route_map()
    return {
        "coreApi": {
            "available": True,
            "version": CORE_API_VERSION,
            "namespace": route_map["namespace"],
        },
        "domains": {
            name: {"available": True, "routes": routes}
            for name, routes in route_map["domains"].items()
        },
        "security": {
            "redactionDefault": True,
            "projectPathContainment": True,
            "longRunningOperationShape": True,
        },
    }


def project_root(project: dict) -> Path:
    raw = str(project.get("resolvedPath") or project.get("path") or "").strip()
    if not raw:
        raise CoreApiError("Project path is unavailable.", 404, code="PROJECT_PATH_UNAVAILABLE")
    root = Path(raw).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise CoreApiError("Project directory is missing on the server.", 404, code="PROJECT_PATH_MISSING")
    return root


def safe_project_child(project: dict, relative_path: str | None = "") -> Path:
    root = project_root(project)
    requested = str(relative_path or "").strip().replace("\\", "/")
    if requested.startswith("/"):
        raise CoreApiError("Project file paths must be relative.", 400, code="PROJECT_PATH_TRAVERSAL")
    target = (root / requested).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise CoreApiError("Project file path escapes the project root.", 403, code="PROJECT_PATH_TRAVERSAL") from exc
    return target


def relative_to_project(project: dict, path: Path) -> str:
    root = project_root(project)
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        raise CoreApiError("Path escapes the project root.", 403, code="PROJECT_PATH_TRAVERSAL")


def operation_record(kind: str, project_id: str = "", *, status: str = "succeeded", summary: str = "", details: dict | None = None) -> dict:
    timestamp = now_iso()
    return redact_payload({
        "operationId": operation_id(kind),
        "kind": kind,
        "projectId": project_id,
        "status": status,
        "startedAt": timestamp,
        "updatedAt": timestamp,
        "progress": {"summary": summary or status},
        "result": details if isinstance(details, dict) else {},
    })


def getenv_descriptor(name: str) -> dict:
    value = os.getenv(name, "")
    return {"name": name, "configured": bool(value), "value": "[REDACTED]" if value else ""}

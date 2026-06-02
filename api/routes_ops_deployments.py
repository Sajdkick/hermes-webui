"""Ops compatibility routes for the Core deployments domain."""

from __future__ import annotations

import re
from urllib.parse import unquote

from api.helpers import j
from api.core_contracts import CoreApiError, error_payload
from api import core_deployments

_DEPLOYMENT_PROVIDERS_RE = re.compile(r"^/api/ops/deployments/providers/?$")
_PROJECT_DEPLOYMENT_RE = re.compile(r"^/api/ops/projects/([^/]+)/deployment/?$")
_PROJECT_DEPLOYMENT_LOGS_RE = re.compile(r"^/api/ops/projects/([^/]+)/deployment/logs/?$")
_PROJECT_DEPLOYMENT_ARTIFACTS_RE = re.compile(r"^/api/ops/projects/([^/]+)/deployment/artifacts/?$")
_PROJECT_DEPLOYMENT_SCAFFOLD_RE = re.compile(r"^/api/ops/projects/([^/]+)/deployment/artifacts/scaffold/?$")
_PROJECT_DEPLOYMENT_EXECUTE_RE = re.compile(r"^/api/ops/projects/([^/]+)/deployment/execute/?$")
_PROJECT_DEPLOYMENT_REDEPLOY_RE = re.compile(r"^/api/ops/projects/([^/]+)/deployment/(?:redeploy|update)/?$")
_PROJECT_DEPLOYMENT_ACTION_RE = re.compile(r"^/api/ops/projects/([^/]+)/deployment/([^/]+)/?$")


def _send_error(handler, exc: Exception) -> None:
    if not isinstance(exc, CoreApiError):
        exc = CoreApiError(str(exc), status=int(getattr(exc, "status", 500) or 500), code="DEPLOYMENT_ROUTE_ERROR")
    j(handler, error_payload(exc), status=exc.status)


def handle_get(handler, parsed) -> bool:
    try:
        if _DEPLOYMENT_PROVIDERS_RE.match(parsed.path):
            j(handler, core_deployments.provider_registry())
            return True
        match = _PROJECT_DEPLOYMENT_RE.match(parsed.path)
        if match:
            j(handler, core_deployments.get_project_deployment(unquote(match.group(1))))
            return True
        match = _PROJECT_DEPLOYMENT_LOGS_RE.match(parsed.path)
        if match:
            payload = core_deployments.get_project_deployment(unquote(match.group(1)))
            j(handler, {"projectId": unquote(match.group(1)), "logs": payload.get("logs", [])})
            return True
        match = _PROJECT_DEPLOYMENT_ARTIFACTS_RE.match(parsed.path)
        if match:
            j(handler, core_deployments.detect_project_artifacts(unquote(match.group(1))))
            return True
        return False
    except Exception as exc:
        _send_error(handler, exc)
        return True


def handle_post(handler, parsed, body: dict) -> bool:
    try:
        match = _PROJECT_DEPLOYMENT_RE.match(parsed.path)
        if match:
            j(handler, core_deployments.record_project_deployment(unquote(match.group(1)), body), status=201)
            return True
        match = _PROJECT_DEPLOYMENT_SCAFFOLD_RE.match(parsed.path)
        if match:
            j(handler, core_deployments.scaffold_project_deployment(unquote(match.group(1)), body), status=201)
            return True
        match = _PROJECT_DEPLOYMENT_EXECUTE_RE.match(parsed.path)
        if match:
            j(handler, core_deployments.execute_project_deployment(unquote(match.group(1)), body), status=202)
            return True
        match = _PROJECT_DEPLOYMENT_REDEPLOY_RE.match(parsed.path)
        if match:
            j(handler, core_deployments.redeploy_project_deployment(unquote(match.group(1)), body, request_headers=handler.headers), status=202)
            return True
        match = _PROJECT_DEPLOYMENT_ACTION_RE.match(parsed.path)
        if match:
            j(handler, core_deployments.record_project_deployment(unquote(match.group(1)), body, action=unquote(match.group(2))), status=201)
            return True
        return False
    except Exception as exc:
        _send_error(handler, exc)
        return True

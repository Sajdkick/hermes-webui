from __future__ import annotations

import io
import json
from urllib.parse import urlparse

import pytest

from api import core_contracts, core_deployments, core_host, core_projects, routes_core


class DummyHandler:
    def __init__(self, command: str = "GET") -> None:
        self.command = command
        self.headers = {}
        self.wfile = io.BytesIO()
        self.status = None
        self.response_headers = []
        self.ended = False

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.response_headers.append((key, value))

    def end_headers(self) -> None:
        self.ended = True

    def json_payload(self) -> dict:
        return json.loads(self.wfile.getvalue().decode("utf-8"))


def _get(path: str) -> DummyHandler:
    handler = DummyHandler("GET")
    assert routes_core.handle_get(handler, urlparse(path)) is True
    return handler


def _post(path: str, body: dict | None = None) -> DummyHandler:
    handler = DummyHandler("POST")
    assert routes_core.handle_post(handler, urlparse(path), body or {}) is True
    return handler


def test_core_contract_helpers_expose_version_redaction_and_safe_paths(tmp_path):
    assert core_contracts.CORE_API_VERSION
    route_map = core_contracts.public_route_map()
    assert route_map["namespace"] == "/api/core"
    assert "deployments" in route_map["domains"]
    assert core_contracts.capabilities()["security"]["redactionDefault"] is True

    payload = core_contracts.error_payload(
        core_contracts.CoreApiError(
            "Connection failed for postgres://user:secret@example.invalid/db",
            code="DATABASE_SECRET_TEST",
            details={"message": "Authorization: Bearer sk-testsecret1234567890"},
        )
    )
    assert payload["code"] == "DATABASE_SECRET_TEST"
    rendered = json.dumps(payload)
    assert "secret@example" not in rendered
    assert "sk-testsecret" not in rendered

    project = {"id": "project-1", "path": str(tmp_path)}
    child = tmp_path / "nested" / "file.txt"
    child.parent.mkdir()
    child.write_text("ok", encoding="utf-8")
    assert core_contracts.safe_project_child(project, "nested/file.txt") == child.resolve()
    with pytest.raises(core_contracts.CoreApiError) as excinfo:
        core_contracts.safe_project_child(project, "../outside.txt")
    assert excinfo.value.code == "PROJECT_PATH_TRAVERSAL"


def test_core_routes_expose_capabilities_health_and_domain_delegates(monkeypatch):
    capabilities_handler = _get("/api/core/capabilities")
    assert capabilities_handler.status == 200
    capabilities_payload = capabilities_handler.json_payload()
    assert capabilities_payload["coreApi"]["namespace"] == "/api/core"
    assert capabilities_payload["domains"]["deployments"]["available"] is True
    assert capabilities_payload["domains"]["runtime"]["available"] is True

    root_handler = _get("/api/core")
    assert root_handler.status == 200
    assert root_handler.json_payload()["coreApi"]["namespace"] == "/api/core"

    monkeypatch.setattr(core_host, "host_health", lambda: {"ok": True, "status": "healthy"})
    health_handler = _get("/api/core/health")
    assert health_handler.status == 200
    assert health_handler.json_payload() == {"ok": True, "status": "healthy"}

    monkeypatch.setattr(core_deployments, "provider_registry", lambda: {"providers": [{"id": "manual", "label": "Manual record"}], "defaultProvider": "manual"})
    providers_handler = _get("/api/core/deployments/providers")
    assert providers_handler.status == 200
    assert providers_handler.json_payload()["providers"][0]["id"] == "manual"

    monkeypatch.setattr(core_projects, "list_projects", lambda: {"projects": [{"id": "project-1"}]})
    projects_handler = _get("/api/core/projects")
    assert projects_handler.status == 200
    assert projects_handler.json_payload() == {"projects": [{"id": "project-1"}]}

    monkeypatch.setattr(core_deployments, "get_project_deployment", lambda project_id: {"projectId": project_id, "deployment": {"status": "ready"}})
    deployment_handler = _get("/api/core/projects/project%201/deployment")
    assert deployment_handler.status == 200
    assert deployment_handler.json_payload() == {"projectId": "project 1", "deployment": {"status": "ready"}}


def test_core_routes_post_deployment_execute_uses_core_facade(monkeypatch):
    calls = []

    def execute(project_id: str, body: dict) -> dict:
        calls.append((project_id, body))
        return {
            "operation": core_contracts.operation_record(
                "deployment.execute",
                project_id,
                summary="executed",
                details={"provider": body.get("provider")},
            )
        }

    monkeypatch.setattr(core_deployments, "execute_project_deployment", execute)
    handler = _post("/api/core/projects/project%201/deployment/execute", {"provider": "manual"})
    assert handler.status == 202
    payload = handler.json_payload()
    assert payload["operation"]["kind"] == "deployment.execute"
    assert payload["operation"]["projectId"] == "project 1"
    assert payload["operation"]["result"] == {"provider": "manual"}
    assert calls == [("project 1", {"provider": "manual"})]


def test_core_route_errors_use_stable_envelope(monkeypatch):
    def fail() -> dict:
        raise core_contracts.CoreApiError("Nope", status=418, code="TEAPOT", details={"safe": True})

    monkeypatch.setattr(core_projects, "list_projects", fail)
    handler = _get("/api/core/projects")
    assert handler.status == 418
    assert handler.json_payload() == {"error": "Nope", "code": "TEAPOT", "details": {"safe": True}, "retryable": False}

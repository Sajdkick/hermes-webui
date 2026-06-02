from __future__ import annotations

import io
import json
from urllib.parse import urlparse

from api import core_play, play_pipeline, routes_ops_play


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


def test_core_play_facade_delegates_to_play_pipeline_at_call_time(monkeypatch):
    calls = []

    def status(project_id: str) -> dict:
        calls.append(("status", project_id))
        return {"projectId": project_id, "status": "ready"}

    def logs(project_id: str, limit) -> dict:
        calls.append(("logs", project_id, limit))
        return {"projectId": project_id, "logs": []}

    def start(project_id: str, body: dict | None = None) -> dict:
        calls.append(("start", project_id, body))
        return {"projectId": project_id, "status": "building"}

    def stop(project_id: str, *, purge: bool = False) -> dict:
        calls.append(("stop", project_id, purge))
        return {"projectId": project_id, "status": "stopped"}

    monkeypatch.setattr(play_pipeline, "build_project_play_status", status)
    monkeypatch.setattr(play_pipeline, "build_project_play_logs", logs)
    monkeypatch.setattr(play_pipeline, "start_project_play_pipeline", start)
    monkeypatch.setattr(play_pipeline, "stop_project_play_pipeline", stop)

    assert core_play.get_project_play_status("project-1") == {"projectId": "project-1", "status": "ready"}
    assert core_play.get_project_play_logs("project-1", "25") == {"projectId": "project-1", "logs": []}
    assert core_play.start_project_play("project-1", {"runId": "run-1"}) == {"projectId": "project-1", "status": "building"}
    assert core_play.stop_project_play("project-1", purge=True) == {"projectId": "project-1", "status": "stopped"}
    assert calls == [
        ("status", "project-1"),
        ("logs", "project-1", "25"),
        ("start", "project-1", {"runId": "run-1"}),
        ("stop", "project-1", True),
    ]


def test_ops_play_routes_delegate_to_core_play(monkeypatch):
    calls = []

    monkeypatch.setattr(
        core_play,
        "get_project_play_status",
        lambda project_id: calls.append(("status", project_id)) or {"projectId": project_id, "status": "ready"},
    )
    monkeypatch.setattr(
        core_play,
        "get_project_play_logs",
        lambda project_id, limit: calls.append(("logs", project_id, limit)) or {"projectId": project_id, "logs": []},
    )
    monkeypatch.setattr(
        core_play,
        "start_project_play",
        lambda project_id, body: calls.append(("start", project_id, body)) or {"projectId": project_id, "status": "building"},
    )

    status_handler = DummyHandler("GET")
    assert routes_ops_play.handle_get(status_handler, urlparse("/api/ops/projects/project%201/play/status")) is True
    assert status_handler.status == 200
    assert status_handler.json_payload() == {"projectId": "project 1", "status": "ready"}

    logs_handler = DummyHandler("GET")
    assert routes_ops_play.handle_get(logs_handler, urlparse("/api/ops/projects/project%201/play/logs?limit=25")) is True
    assert logs_handler.status == 200
    assert logs_handler.json_payload() == {"projectId": "project 1", "logs": []}

    start_handler = DummyHandler("POST")
    body = {"runId": "run-1"}
    assert routes_ops_play.handle_post(start_handler, urlparse("/api/ops/projects/project%201/play/start"), body) is True
    assert start_handler.status == 200
    assert start_handler.json_payload() == {
        "ok": True,
        "started": True,
        "status": {"projectId": "project 1", "status": "building"},
        "message": "Play pipeline started.",
    }

    assert calls == [
        ("status", "project 1"),
        ("logs", "project 1", "25"),
        ("start", "project 1", body),
    ]


def test_ops_play_stop_route_preserves_status_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(core_play, "stop_project_play", lambda project_id: calls.append(("stop", project_id)) or None)
    monkeypatch.setattr(
        core_play,
        "get_project_play_status",
        lambda project_id: calls.append(("status", project_id)) or {"projectId": project_id, "status": "idle"},
    )

    handler = DummyHandler("POST")
    assert routes_ops_play.handle_post(handler, urlparse("/api/ops/projects/project%201/play/stop"), {}) is True
    assert handler.status == 200
    assert handler.json_payload() == {
        "ok": True,
        "stopped": True,
        "status": {"projectId": "project 1", "status": "idle"},
        "message": "Play pipeline stopped.",
    }
    assert calls == [("stop", "project 1"), ("status", "project 1")]


def test_ops_play_proxy_route_delegates_to_core_play(monkeypatch):
    calls = []

    def proxy(handler, project_id: str, target_path: str, parsed, *, method: str = "GET") -> None:
        calls.append((handler.command, project_id, target_path, parsed.query, method))

    monkeypatch.setattr(core_play, "handle_play_proxy_request", proxy)

    handler = DummyHandler("GET")
    assert routes_ops_play.handle_get(handler, urlparse("/play-project/project%201/dashboard?tab=preview")) is True
    assert calls == [("GET", "project 1", "/dashboard", "tab=preview", "GET")]

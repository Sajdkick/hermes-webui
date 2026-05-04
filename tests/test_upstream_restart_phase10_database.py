import io
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

import api.routes as routes
from api import ops_database, routes_ops_database


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def create_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("create table users (id integer primary key, name text not null)")
        connection.execute("insert into users (name) values ('Ada'), ('Grace')")


class _FakeHandler:
    def __init__(self, body=None):
        raw = json.dumps(body or {}).encode("utf-8")
        self.status = None
        self.sent_headers = []
        self.body = bytearray()
        self.wfile = self
        self.rfile = io.BytesIO(raw)
        self.headers = {"Content-Length": str(len(raw))}

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent_headers.append((name, value))

    def end_headers(self):
        pass

    def write(self, data):
        self.body.extend(data)


def _response_json(handler: _FakeHandler) -> dict:
    return json.loads(bytes(handler.body).decode("utf-8"))


def test_phase10_database_settings_connection_tables_and_query(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    create_db(db_path)
    monkeypatch.setattr(ops_database, "OPS_DATABASE_SETTINGS_FILE", tmp_path / "ops-database" / "settings.json")

    saved = ops_database.save_database_settings({"path": str(db_path), "label": "App DB"})
    tested = ops_database.test_database_connection()
    inspected = ops_database.inspect_database_tables()
    queried = ops_database.execute_readonly_query({"query": "select name from users order by id", "limit": 10})

    assert saved["configured"] is True
    assert tested["ok"] is True
    assert inspected["tables"][0]["name"] == "users"
    assert [column["name"] for column in inspected["tables"][0]["columns"]] == ["id", "name"]
    assert queried["columns"] == ["name"]
    assert queried["rows"] == [["Ada"], ["Grace"]]


def test_phase10_database_query_rejects_mutation(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    create_db(db_path)
    monkeypatch.setattr(ops_database, "OPS_DATABASE_SETTINGS_FILE", tmp_path / "ops-database" / "settings.json")
    ops_database.save_database_settings({"path": str(db_path)})

    with pytest.raises(ops_database.OpsDatabaseError, match="Only SELECT"):
        ops_database.execute_readonly_query({"query": "delete from users"})
    with pytest.raises(ops_database.OpsDatabaseError, match="Only one"):
        ops_database.execute_readonly_query({"query": "select * from users; select 1"})


def test_phase10_project_database_settings_tables_and_query(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = repo / "app.db"
    create_db(db_path)
    write_json(
        projects_dir / "projects.json",
        [{"id": "project-1", "name": "Repo", "slug": "repo", "path": str(repo), "coreBranch": "main"}],
    )
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(projects_dir))
    monkeypatch.setattr(ops_database, "OPS_DATABASE_SETTINGS_FILE", tmp_path / "ops-database" / "settings.json")

    saved = ops_database.save_project_database_settings(
        "project-1",
        {"path": "app.db", "label": "Project DB", "mode": "copy"},
    )
    settings = ops_database.get_project_database_settings("project-1")
    tested = ops_database.test_project_database_connection("project-1")
    tables = ops_database.inspect_project_database_tables("project-1")
    queried = ops_database.execute_project_readonly_query("project-1", {"query": "select count(*) as c from users"})

    assert saved["settings"]["path"] == str(db_path.resolve())
    assert saved["settings"]["mode"] == "copy"
    assert settings["configured"] is True
    assert settings["inherited"] is False
    assert tested["ok"] is True
    assert tables["projectId"] == "project-1"
    assert tables["tables"][0]["name"] == "users"
    assert queried["rows"] == [[2]]


def test_phase10_database_routes_dispatch_through_ops_modules(monkeypatch):
    dispatch_calls = []
    handler = SimpleNamespace(command="POST", headers={}, host="127.0.0.1")

    def fake_get(_handler, parsed):
        dispatch_calls.append(("get", parsed.path))
        return parsed.path == "/api/ops/database/settings"

    def fake_post(_handler, parsed, body):
        dispatch_calls.append(("post", parsed.path, body))
        return parsed.path in {
            "/api/ops/database/test",
            "/api/ops/projects/project-1/database/inspect/query",
        }

    monkeypatch.setattr(routes_ops_database, "handle_get", fake_get)
    monkeypatch.setattr(routes_ops_database, "handle_post", fake_post)
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    monkeypatch.setattr(routes, "read_body", lambda _handler: {"query": "select 1"})

    assert routes.handle_get(handler, SimpleNamespace(path="/api/ops/database/settings", query="")) is True
    assert routes.handle_post(handler, SimpleNamespace(path="/api/ops/database/test", query="")) is True
    assert routes.handle_post(handler, SimpleNamespace(path="/api/ops/projects/project-1/database/inspect/query", query="")) is True
    assert dispatch_calls == [
        ("get", "/api/ops/database/settings"),
        ("post", "/api/ops/database/test", {"query": "select 1"}),
        ("post", "/api/ops/projects/project-1/database/inspect/query", {"query": "select 1"}),
    ]


def test_phase10_database_route_module_handles_direct_endpoints(monkeypatch):
    responses = []

    def fake_j(_handler, payload, status=200):
        responses.append((payload, status))
        return True

    monkeypatch.setattr(routes_ops_database, "j", fake_j)
    monkeypatch.setattr(ops_database, "get_database_settings", lambda: {"configured": True})
    monkeypatch.setattr(ops_database, "inspect_database_tables", lambda: {"tables": [{"name": "users"}]})
    monkeypatch.setattr(ops_database, "save_database_settings", lambda body: {"configured": True, "saved": body})
    monkeypatch.setattr(ops_database, "test_database_connection", lambda body=None: {"ok": True, "body": body})
    monkeypatch.setattr(ops_database, "execute_readonly_query", lambda body: {"columns": ["name"], "rows": [["Ada"]], "body": body})
    monkeypatch.setattr(
        ops_database,
        "get_project_database_settings",
        lambda project_id: {"projectId": project_id, "configured": True},
    )
    monkeypatch.setattr(
        ops_database,
        "inspect_project_database_tables",
        lambda project_id: {"projectId": project_id, "tables": [{"name": "users"}]},
    )
    monkeypatch.setattr(
        ops_database,
        "save_project_database_settings",
        lambda project_id, body: {"projectId": project_id, "saved": body},
    )
    monkeypatch.setattr(
        ops_database,
        "test_project_database_connection",
        lambda project_id, body=None: {"projectId": project_id, "ok": True, "body": body},
    )
    monkeypatch.setattr(
        ops_database,
        "execute_project_readonly_query",
        lambda project_id, body: {"projectId": project_id, "rows": [[2]], "body": body},
    )

    handler = SimpleNamespace()
    assert routes_ops_database.handle_get(handler, SimpleNamespace(path="/api/ops/database/settings", query="")) is True
    assert routes_ops_database.handle_get(handler, SimpleNamespace(path="/api/ops/database/inspect/tables", query="")) is True
    assert routes_ops_database.handle_post(handler, SimpleNamespace(path="/api/ops/database/settings", query=""), {"path": "/tmp/app.db"}) is True
    assert routes_ops_database.handle_post(handler, SimpleNamespace(path="/api/ops/database/test", query=""), {"path": "/tmp/app.db"}) is True
    assert routes_ops_database.handle_post(handler, SimpleNamespace(path="/api/ops/database/inspect/query", query=""), {"query": "select name from users"}) is True
    assert routes_ops_database.handle_get(handler, SimpleNamespace(path="/api/ops/projects/project-1/database/settings", query="")) is True
    assert routes_ops_database.handle_get(handler, SimpleNamespace(path="/api/ops/projects/project-1/database/inspect/tables", query="")) is True
    assert routes_ops_database.handle_post(handler, SimpleNamespace(path="/api/ops/projects/project-1/database/settings", query=""), {"path": "app.db"}) is True
    assert routes_ops_database.handle_post(handler, SimpleNamespace(path="/api/ops/projects/project-1/database/test", query=""), {"path": "app.db"}) is True
    assert routes_ops_database.handle_post(handler, SimpleNamespace(path="/api/ops/projects/project-1/database/inspect/query", query=""), {"query": "select count(*) from users"}) is True

    assert responses == [
        ({"configured": True}, 200),
        ({"tables": [{"name": "users"}]}, 200),
        ({"ok": True, "configured": True, "saved": {"path": "/tmp/app.db"}}, 200),
        ({"ok": True, "body": {"path": "/tmp/app.db"}}, 200),
        ({"columns": ["name"], "rows": [["Ada"]], "body": {"query": "select name from users"}}, 200),
        ({"projectId": "project-1", "configured": True}, 200),
        ({"projectId": "project-1", "tables": [{"name": "users"}]}, 200),
        ({"ok": True, "projectId": "project-1", "saved": {"path": "app.db"}}, 200),
        ({"projectId": "project-1", "ok": True, "body": {"path": "app.db"}}, 200),
        ({"projectId": "project-1", "rows": [[2]], "body": {"query": "select count(*) from users"}}, 200),
    ]

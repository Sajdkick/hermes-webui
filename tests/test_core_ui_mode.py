from __future__ import annotations

import io
import json
import time
from pathlib import Path
from urllib.parse import urlparse

from api import config, core_contracts, core_ui, models, routes, routes_core
from api.models import Session, _normalize_session_mode


class DummyHandler:
    def __init__(self, command: str = "GET") -> None:
        self.command = command
        self.headers = {}
        self.wfile = io.BytesIO()
        self.rfile = io.BytesIO()
        self.status = None
        self.response_headers = []
        self.ended = False

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.response_headers.append((key, value))

    def end_headers(self) -> None:
        self.ended = True

    def header(self, key: str) -> str | None:
        for name, value in self.response_headers:
            if name.lower() == key.lower():
                return value
        return None

    def json_payload(self) -> dict:
        return json.loads(self.wfile.getvalue().decode("utf-8"))


def _write_project_registry(registry_dir: Path, project_id: str, project_path: Path) -> None:
    registry_dir.mkdir(parents=True, exist_ok=True)
    (registry_dir / "projects.json").write_text(
        json.dumps([
            {
                "id": project_id,
                "name": "Tiny UI",
                "fullName": "Tiny UI Project",
                "slug": "tiny-ui",
                "path": str(project_path),
                "coreBranch": "main",
                "active": True,
            }
        ]),
        encoding="utf-8",
    )


def _write_tiny_ui_project(project_path: Path) -> None:
    (project_path / ".hermes").mkdir(parents=True, exist_ok=True)
    (project_path / ".hermes" / "ui.json").write_text(
        json.dumps(
            {
                "version": 1,
                "dev": {
                    "command": "python3 -u server.py",
                    "cwd": ".",
                    "port": {"mode": "auto", "host": "127.0.0.1", "envVar": "PORT", "range": {"min": 41000, "max": 41999}},
                },
                "inspect": {"mode": "proxy", "url": "/", "readyTimeoutMs": 10000, "readyPattern": "READY"},
            }
        ),
        encoding="utf-8",
    )
    (project_path / "server.py").write_text(
        """
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/asset.js':
            body = b"window.__tinyAsset=1;"
            self.send_response(200)
            self.send_header('Content-Type','application/javascript')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b"<!doctype html><html><head><script src='/asset.js'></script></head><body>Tiny UI</body></html>"
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, format, *args):
        pass

port = int(os.environ['PORT'])
server = HTTPServer(('127.0.0.1', port), Handler)
print('READY', port, flush=True)
server.serve_forever()
""".strip(),
        encoding="utf-8",
    )


def _write_tiny_play_sourced_ui_project(project_path: Path) -> None:
    _write_tiny_ui_project(project_path)
    (project_path / ".hermes" / "ui.json").write_text(json.dumps({"version": 1, "source": "project_play.json"}), encoding="utf-8")
    (project_path / "project_play.json").write_text(
        json.dumps(
            {
                "version": 1,
                "build": {
                    "command": "python3 -c \"from pathlib import Path; Path('built.txt').write_text('ok', encoding='utf-8')\"",
                    "cwd": ".",
                    "env": {"CI": "true"},
                    "timeoutMs": 10000,
                },
                "start": {
                    "command": "python3 -u server.py",
                    "cwd": ".",
                    "env": {"AUTH_DEBUG_LOGIN": "true", "SERVE_CLIENT_BUILD": "true"},
                    "port": {"mode": "auto", "host": "127.0.0.1", "envVar": "PORT", "range": {"min": 42000, "max": 42999}},
                },
                "inspect": {"mode": "proxy", "url": "/app", "readyTimeoutMs": 10000, "readyPattern": "READY"},
            }
        ),
        encoding="utf-8",
    )


def _write_monorepo_template_project(project_path: Path) -> None:
    (project_path / "packages" / "client").mkdir(parents=True, exist_ok=True)
    (project_path / "packages" / "apps").mkdir(parents=True, exist_ok=True)
    (project_path / "packages" / "server").mkdir(parents=True, exist_ok=True)
    (project_path / "packages" / "schemas").mkdir(parents=True, exist_ok=True)
    (project_path / "scripts").mkdir(parents=True, exist_ok=True)
    (project_path / "scripts" / "active-app.sh").write_text("# template active app helper\n", encoding="utf-8")
    (project_path / "package.json").write_text(
        json.dumps({"packageManager": "pnpm@10.12.4", "scripts": {"test": "jest"}}),
        encoding="utf-8",
    )
    (project_path / "packages" / "client" / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "predev": "node ./scripts/generate-app-modules.cjs && pnpm --filter @monorepo/schemas run build",
                    "dev": "vite",
                    "build": "node ./scripts/generate-app-modules.cjs && vite build",
                }
            }
        ),
        encoding="utf-8",
    )
    for rel in ("packages/apps/package.json", "packages/server/package.json", "packages/schemas/package.json"):
        (project_path / rel).write_text(json.dumps({"name": rel.split("/")[1]}), encoding="utf-8")
    (project_path / "project_play.json").write_text(
        json.dumps(
            {
                "version": 2,
                "build": {
                    "command": "bash ./scripts/deploy-build.sh model-builder",
                    "cwd": ".",
                    "env": {"CI": "true", "MONOREPO_ACTIVE_APP": "model-builder"},
                },
                "start": {
                    "command": "node -r ./scripts/register-runtime-paths.cjs packages/server/dist/packages/server/index.js",
                    "cwd": ".",
                    "env": {
                        "AUTH_DEBUG_LOGIN": "true",
                        "MONOREPO_ACTIVE_APP": "model-builder",
                        "SERVE_CLIENT_BUILD": "true",
                        "NO_PROXY": "localhost,127.0.0.1",
                    },
                    "port": {"mode": "auto", "host": "127.0.0.1", "envVar": "PORT", "range": {"min": 20000, "max": 29999}},
                },
                "inspect": {"mode": "proxy", "url": "/app", "readyPattern": "Server listening", "readyTimeoutMs": 120000},
            }
        ),
        encoding="utf-8",
    )


def _add_monorepo_template_ui_dev_contract(project_path: Path) -> None:
    root_payload = json.loads((project_path / "package.json").read_text(encoding="utf-8"))
    scripts = root_payload.setdefault("scripts", {})
    scripts["ui:dev"] = "bash ./scripts/ui-dev.sh"
    (project_path / "package.json").write_text(json.dumps(root_payload), encoding="utf-8")
    (project_path / "scripts" / "ui-dev.sh").write_text("#!/usr/bin/env bash\npnpm --filter ./packages/client run dev\n", encoding="utf-8")


def _write_monorepo_template_ui_config(project_path: Path) -> None:
    (project_path / "project_ui.json").write_text(
        json.dumps(
            {
                "version": 1,
                "workflowSource": "monorepo-template:ui-dev",
                "dev": {
                    "command": "pnpm run ui:dev",
                    "cwd": ".",
                    "env": {
                        "HOST": "127.0.0.1",
                        "NO_PROXY": "localhost,127.0.0.1",
                        "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
                        "NPM_CONFIG_STORE_DIR": ".cache/pnpm-store",
                        "npm_config_store_dir": ".cache/pnpm-store",
                    },
                    "port": {"mode": "auto", "host": "127.0.0.1", "envVar": "PORT", "range": {"min": 30000, "max": 39999}},
                },
                "inspect": {"mode": "proxy", "url": "/", "readyPattern": "Local:", "readyTimeoutMs": 60000},
            }
        ),
        encoding="utf-8",
    )


def test_core_contract_exposes_ui_domain():
    route_map = core_contracts.public_route_map()
    assert "ui" in route_map["domains"]
    assert "GET /projects/{projectId}/ui/status" in route_map["domains"]["ui"]
    assert "GET /projects/{projectId}/ui/session" in route_map["domains"]["ui"]
    assert "POST /projects/{projectId}/ui/session/reset" in route_map["domains"]["ui"]
    assert "POST /projects/{projectId}/ui/session/prune" in route_map["domains"]["ui"]
    assert "POST /projects/{projectId}/ui/start" in route_map["domains"]["ui"]
    caps = core_contracts.capabilities()
    assert caps["domains"]["ui"]["available"] is True



def test_session_mode_normalizes_persists_and_compacts(tmp_path, monkeypatch):
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    monkeypatch.setattr(models, "SESSION_DIR", session_dir)
    monkeypatch.setattr(models, "SESSION_INDEX_FILE", session_dir / "_index.json")

    assert _normalize_session_mode("ui") == "ui_mode"
    assert _normalize_session_mode("ui-mode") == "ui_mode"
    assert _normalize_session_mode("normal") is None

    session = Session(
        session_id="ui-mode-session",
        workspace=str(tmp_path),
        session_mode="ui",
        ui_project_id="summons-project",
        ui_project_label="Summons",
        ui_preview_path="/app",
        ui_preview_title="Summons Arena",
        ui_workflow_source="play-config",
        ui_iteration_mode="play-parity",
        ui_status_summary="UI runtime is ready at /ui-project/summons/app.",
        ui_build_command="bash ./scripts/deploy-build.sh summons",
        ui_runtime_command="node packages/server/dist/index.js",
        ui_build_policy="explicit-user-approval",
        ui_parity_available="true",
        ui_parity_workflow_source="play-config",
        ui_parity_config_path="/tmp/project_play.json",
    )

    assert session.session_mode == "ui_mode"
    compact = session.compact()
    assert compact["session_mode"] == "ui_mode"
    assert compact["ui_project_id"] == "summons-project"
    assert compact["ui_project_label"] == "Summons"
    assert compact["ui_preview_path"] == "/app"
    assert compact["ui_preview_title"] == "Summons Arena"
    assert compact["ui_workflow_source"] == "play-config"
    assert compact["ui_iteration_mode"] == "play-parity"
    assert compact["ui_status_summary"] == "UI runtime is ready at /ui-project/summons/app."
    assert compact["ui_build_command"] == "bash ./scripts/deploy-build.sh summons"
    assert compact["ui_runtime_command"] == "node packages/server/dist/index.js"
    assert compact["ui_build_policy"] == "explicit-user-approval"
    assert compact["ui_parity_available"] == "true"
    assert compact["ui_parity_workflow_source"] == "play-config"
    assert compact["ui_parity_config_path"] == "/tmp/project_play.json"
    assert compact["reasoning_effort"] is None

    session.save(skip_index=True)
    loaded = Session.load("ui-mode-session")

    assert loaded is not None
    assert loaded.session_mode == "ui_mode"
    assert loaded.ui_project_id == "summons-project"
    assert loaded.ui_project_label == "Summons"
    assert loaded.ui_preview_path == "/app"
    assert loaded.ui_preview_title == "Summons Arena"
    assert loaded.ui_workflow_source == "play-config"
    assert loaded.ui_iteration_mode == "play-parity"
    assert loaded.ui_status_summary == "UI runtime is ready at /ui-project/summons/app."
    assert loaded.ui_build_command == "bash ./scripts/deploy-build.sh summons"
    assert loaded.ui_runtime_command == "node packages/server/dist/index.js"
    assert loaded.ui_build_policy == "explicit-user-approval"
    assert loaded.ui_parity_available == "true"
    assert loaded.ui_parity_workflow_source == "play-config"
    assert loaded.ui_parity_config_path == "/tmp/project_play.json"
    assert loaded.compact()["session_mode"] == "ui_mode"


def test_new_ui_mode_sessions_default_to_medium_reasoning(tmp_path, monkeypatch):
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    monkeypatch.setattr(models, "SESSION_DIR", session_dir)
    monkeypatch.setattr(models, "SESSION_INDEX_FILE", session_dir / "_index.json")

    regular = models.new_session(workspace=str(tmp_path / "regular"))
    ui_mode = models.new_session(workspace=str(tmp_path / "ui"), session_mode="ui_mode")
    explicit = models.new_session(workspace=str(tmp_path / "explicit"), session_mode="ui_mode", reasoning_effort="low")
    inherited = models.new_session(workspace=str(tmp_path / "inherit"), session_mode="ui_mode", reasoning_effort="default")

    assert regular.reasoning_effort is None
    assert ui_mode.session_mode == "ui_mode"
    assert ui_mode.reasoning_effort == models.UI_MODE_DEFAULT_REASONING_EFFORT == "medium"
    assert ui_mode.compact()["reasoning_effort"] == "medium"
    assert explicit.reasoning_effort == "low"
    assert inherited.reasoning_effort == "medium"


def test_core_ui_routes_delegate_to_core_ui(monkeypatch):
    calls = []
    monkeypatch.setattr(core_ui, "get_project_ui_config_file_info", lambda project_id: calls.append(("config", project_id)) or {"projectId": project_id, "valid": True})
    monkeypatch.setattr(core_ui, "build_project_ui_status", lambda project_id: calls.append(("status", project_id)) or {"projectId": project_id, "status": "ready"})
    monkeypatch.setattr(core_ui, "build_project_ui_logs", lambda project_id, limit: calls.append(("logs", project_id, limit)) or {"projectId": project_id, "logs": []})
    monkeypatch.setattr(core_ui, "get_project_ui_session", lambda project_id: calls.append(("session", project_id)) or {"projectId": project_id, "sessionId": "ui-session"})
    monkeypatch.setattr(core_ui, "reset_project_ui_session", lambda project_id, body: calls.append(("reset-session", project_id, body)) or {"projectId": project_id, "sessionId": "ui-session-2", "reset": True})
    monkeypatch.setattr(core_ui, "prune_project_ui_sessions", lambda project_id, body: calls.append(("prune-session", project_id, body)) or {"projectId": project_id, "removedWorkspaces": 1})
    monkeypatch.setattr(core_ui, "start_project_ui_runtime", lambda project_id, body: calls.append(("start", project_id, body)) or {"projectId": project_id, "status": "starting"})
    monkeypatch.setattr(core_ui, "restart_project_ui_runtime", lambda project_id, body: calls.append(("restart", project_id, body)) or {"projectId": project_id, "status": "starting"})
    monkeypatch.setattr(core_ui, "stop_project_ui_runtime", lambda project_id: calls.append(("stop", project_id)) or {"projectId": project_id, "status": "stopped"})

    handler = DummyHandler("GET")
    assert routes_core.handle_get(handler, urlparse("/api/core/projects/project%201/ui/status")) is True
    assert handler.json_payload() == {"projectId": "project 1", "status": "ready"}

    handler = DummyHandler("GET")
    assert routes_core.handle_get(handler, urlparse("/api/core/projects/project%201/ui/logs?limit=25")) is True
    assert handler.json_payload() == {"projectId": "project 1", "logs": []}

    handler = DummyHandler("GET")
    assert routes_core.handle_get(handler, urlparse("/api/core/projects/project%201/ui-config-file")) is True
    assert handler.json_payload() == {"projectId": "project 1", "valid": True}

    handler = DummyHandler("GET")
    assert routes_core.handle_get(handler, urlparse("/api/core/projects/project%201/ui/session")) is True
    assert handler.json_payload()["sessionId"] == "ui-session"

    body = {"sessionId": "abc123"}
    handler = DummyHandler("POST")
    assert routes_core.handle_post(handler, urlparse("/api/core/projects/project%201/ui/session/reset"), body) is True
    assert handler.json_payload()["reset"] is True

    handler = DummyHandler("POST")
    assert routes_core.handle_post(handler, urlparse("/api/core/projects/project%201/ui/session/prune"), {"keepCurrent": True}) is True
    assert handler.json_payload()["removedWorkspaces"] == 1

    handler = DummyHandler("POST")
    assert routes_core.handle_post(handler, urlparse("/api/core/projects/project%201/ui/start"), body) is True
    assert handler.json_payload()["status"] == {"projectId": "project 1", "status": "starting"}

    handler = DummyHandler("POST")
    assert routes_core.handle_post(handler, urlparse("/api/core/projects/project%201/ui/restart"), body) is True
    assert handler.json_payload()["restarted"] is True

    handler = DummyHandler("POST")
    assert routes_core.handle_post(handler, urlparse("/api/core/projects/project%201/ui/stop"), {}) is True
    assert handler.json_payload()["stopped"] is True

    assert calls == [
        ("status", "project 1"),
        ("logs", "project 1", "25"),
        ("config", "project 1"),
        ("session", "project 1"),
        ("reset-session", "project 1", body),
        ("prune-session", "project 1", {"keepCurrent": True}),
        ("start", "project 1", body),
        ("restart", "project 1", body),
        ("stop", "project 1"),
    ]


def test_core_ui_project_session_reuses_resets_and_prunes_fast_workspace(tmp_path, monkeypatch):
    project_id = "ui-fast-project"
    project_path = tmp_path / "source-project"
    project_path.mkdir()
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    state_dir = tmp_path / "state"

    monkeypatch.setattr(config, "STATE_DIR", state_dir)
    monkeypatch.setattr(models, "SESSION_DIR", session_dir)
    monkeypatch.setattr(models, "SESSION_INDEX_FILE", session_dir / "_index.json")
    monkeypatch.setattr(core_ui, "_publish_session_change", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        core_ui,
        "_get_project",
        lambda requested_id: {
            "id": requested_id,
            "name": "Tiny UI",
            "fullName": "Tiny UI Project",
            "path": str(project_path),
            "coreBranch": "main",
        },
    )
    monkeypatch.setattr(
        core_ui,
        "build_project_ui_status",
        lambda requested_id: {
            "projectId": requested_id,
            "previewUrl": f"/ui-project/{requested_id}/app",
            "previewPath": "/app",
            "workflowSource": "dev-config",
            "statusSummary": "Ready for HMR",
            "buildCommand": "npm run build",
            "command": "npm run dev",
        },
    )

    first = core_ui.get_project_ui_session(project_id)
    assert first["created"] is True
    first_session_id = first["sessionId"]
    first_workspace = Path(first["fastWorkspace"])
    assert first_workspace.exists()
    agents_text = (first_workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert agents_text.startswith("# UI Mode Fast Workspace")
    assert "fast verification budget" in agents_text
    assert "Do not run" in agents_text and "deploy/build scripts as the default" in agents_text
    assert "Build policy: `explicit-user-approval`" in agents_text
    assert "full" in agents_text and "build is opt-in" in agents_text
    assert "Only run" in agents_text and "explicitly asks" in agents_text
    assert "live-preview visibility still needs" in agents_text and "explicit rebuild" in agents_text
    context = json.loads((first_workspace / "ui-context.json").read_text(encoding="utf-8"))
    assert context["sourceWorkspace"] == str(project_path.resolve())
    assert context["fastWorkspace"] == str(first_workspace.resolve())
    assert context["buildPolicy"] == "explicit-user-approval"
    assert "explicit user-approval" in context["buildPolicySummary"]
    assert (first_workspace / "preview-patches").is_dir()
    assert (first_workspace / "source").exists() or (first_workspace / "source.txt").read_text(encoding="utf-8").strip() == str(project_path.resolve())

    saved = Session.load(first_session_id)
    assert saved is not None
    assert saved.session_mode == "ui_mode"
    assert saved.workspace == str(first_workspace.resolve())
    assert saved.ui_project_workspace == str(project_path.resolve())
    assert saved.ui_build_policy == "explicit-user-approval"

    reused = core_ui.get_project_ui_session(project_id)
    assert reused["created"] is False
    assert reused["sessionId"] == first_session_id

    stale_workspace = first_workspace.parent / "stale-ui-session"
    stale_workspace.mkdir(parents=True)
    reset = core_ui.reset_project_ui_session(project_id, {"sessionId": first_session_id})
    assert reset["reset"] is True
    assert reset["previousSessionId"] == first_session_id
    assert reset["sessionId"] != first_session_id
    retired = Session.load(first_session_id)
    assert retired is not None
    assert retired.archived is True

    pruned = core_ui.prune_project_ui_sessions(project_id, {"keepCurrent": True})
    assert pruned["removedWorkspaces"] >= 1
    assert not stale_workspace.exists()
    assert Path(reset["fastWorkspace"]).exists()


def test_ui_mode_chat_start_uses_fast_workspace_without_overwriting_source_metadata(tmp_path, monkeypatch):
    project_id = "ui-fast-chat"
    source_workspace = tmp_path / "source-project"
    fast_workspace = tmp_path / "state" / "ui-mode" / "workspaces" / "project" / "session"
    source_workspace.mkdir(parents=True)
    fast_workspace.mkdir(parents=True)
    (fast_workspace / "AGENTS.md").write_text("# UI Mode Fast Workspace\n", encoding="utf-8")
    (fast_workspace / "ui-context.json").write_text(json.dumps({"sourceWorkspace": str(source_workspace)}), encoding="utf-8")

    monkeypatch.setattr(routes, "resolve_trusted_workspace", lambda path=None: Path(path or source_workspace).expanduser().resolve())
    monkeypatch.setattr(routes, "set_last_workspace", lambda workspace: None)
    monkeypatch.setattr(routes, "_resolve_compatible_session_model_state", lambda model, provider: (model or "test/model", provider, False))
    monkeypatch.setattr(core_ui, "is_ui_mode_fast_workspace", lambda path, project_id=None: Path(path).resolve() == fast_workspace.resolve())

    session = Session(
        session_id="ui-mode-fast",
        workspace=str(fast_workspace),
        model="test/model",
        session_mode="ui_mode",
        project_id=project_id,
        ui_project_id=project_id,
        ui_project_workspace=str(source_workspace),
    )
    monkeypatch.setattr(routes, "get_session", lambda session_id: session if session_id == session.session_id else (_ for _ in ()).throw(KeyError(session_id)))
    captured = {}

    def fake_start_chat_stream(s, **kwargs):
        captured.update(kwargs)
        s.workspace = kwargs["workspace"]
        return {"stream_id": "stream-1", "pending_started_at": 1.0}

    monkeypatch.setattr(routes, "_start_chat_stream_for_session", fake_start_chat_stream)

    handler = DummyHandler("POST")
    result = routes._handle_chat_start(
        handler,
        {
            "session_id": session.session_id,
            "message": "Tighten the selected button spacing",
            "workspace": str(fast_workspace),
            "session_mode": "ui_mode",
            "ui_project_id": project_id,
            "ui_project_workspace": str(source_workspace),
            "ui_fast_workspace": str(fast_workspace),
            "ui_build_policy": "explicit-user-approval",
        },
    )

    assert result in (True, None)
    assert handler.status == 200
    assert captured["workspace"] == str(fast_workspace.resolve())
    assert session.workspace == str(fast_workspace.resolve())
    assert session.ui_project_workspace == str(source_workspace)
    assert session.ui_build_policy == "explicit-user-approval"


def test_ui_mode_shell_and_static_sources_are_present():
    root = Path(__file__).resolve().parents[1]
    html = (root / "static" / "ui-mode.html").read_text(encoding="utf-8")
    js = (root / "static" / "ui-mode.js").read_text(encoding="utf-8")
    compat = (root / "static" / "ui-proxy-compat.js").read_text(encoding="utf-8")
    messages = (root / "static" / "messages.js").read_text(encoding="utf-8")
    ui_src = (root / "static" / "ui.js").read_text(encoding="utf-8")
    ops_detail = (root / "static" / "ops-legacy-project-detail.js").read_text(encoding="utf-8")
    ops_home = (root / "static" / "ops-legacy-home.js").read_text(encoding="utf-8")
    ops_css = (root / "static" / "ops-legacy.css").read_text(encoding="utf-8")

    assert "data-preview-frame" in html
    assert "data-chat-frame" in html
    assert "data-chrome-toggle" in html
    assert "data-chat-toggle" in html
    assert "data-action=\"focus-preview\"" in html
    assert "data-action=\"show-controls\"" in html
    assert "data-action=\"show-chat\"" in html
    assert "data-current-page" not in html
    assert "data-selected-element" not in html
    assert "data-preview-meta" not in html
    assert "data-chat-meta" not in html
    assert "data-inspect-toggle" in html
    assert "data-action=\"send-context-to-chat\"" not in html
    assert "Paste visible context" not in html
    assert "Auto-sent to chat" not in html
    assert "preview-pane{grid-template-rows:minmax(0,1fr) auto}" in html
    assert "preview-context" not in html
    assert "context-page" not in html
    assert "context-selection" not in html
    assert "context-sync" not in html
    assert "chat-preview-actions" in html
    assert html.count('data-action="toggle-inspect"') == 1
    assert html.count('data-action="clear-highlights"') == 1
    assert "data-highlight-clear" in html
    assert "Clear highlights" in html
    assert html.count('data-action="reload-preview"') == 1
    assert html.count('data-action="apply-preview-patches"') == 1
    assert html.count('data-action="discard-preview-patches"') == 1
    assert "data-preview-patch-status" in html
    assert "Apply to source" in html
    assert "Discard" in html
    assert html.count('data-action="focus-preview"') == 1
    assert "Refresh status" in html
    assert "__CSRF_TOKEN_JSON__" in html
    assert "api/core/projects/" in js
    assert "ui/session" in js
    assert "api/session/new" not in js
    assert "api/session?session_id=" not in js
    assert "data-action=\"reset-chat\"" in html
    assert "resetChatSession" in js
    assert "Opening project UI chat…" in js
    assert "uiFastWorkspace" in js
    assert "uiContextPath" in js
    assert "UI Mode fast workspace" in js
    assert "UI Mode context file" in js
    assert "chatUrl.searchParams.set('sessionMode','ui_mode')" in js
    assert "sessionVerified:false" in js
    assert "uiProjectLabel" in js
    assert "uiProjectWorkspace" in js
    assert "projectSourceWorkspace" in js
    assert "Project source workspace" in js
    assert "currentPreviewContextMetadata" in js
    assert "Mode: UI Mode live preview" in js
    assert "Highlighted/selected elements" in js
    assert "selectedElements:[]" in js
    assert "selectedElementsList" in js
    assert "normalizeSelectedElements" in js
    assert "selections:selectedElementsList()" in js
    assert "Highlight ('+count+')" in js
    assert "layoutStorageKey:'hermes-ui-mode-layout-v1'" in js
    assert "setControlsCollapsed" in js
    assert "setChatCollapsed" in js
    assert "focusPreview" in js
    assert "setInspectEnabled" in js
    assert "clearHighlights" in js
    assert "hermes-ui-clear-highlights" in js
    assert "[data-highlight-clear]" in js
    assert "previewPatches:[]" in js
    assert "handlePreviewPatchRequest" in js
    assert "postPreviewPatches" in js
    assert "previewPatchJournalPrompt" in js
    assert "hermes-ui-preview-patch-request" in js
    assert "hermes-ui-preview-apply-patches" in js
    assert "hermes-ui-preview-clear-patches" in js
    assert "hermes-ui-mode-send-text" in js
    assert "hermes-ui-preview-context" in js
    assert "hermes-ui-mode-context-update" in js
    assert "sendContextToChat" not in js
    assert "hermes-ui-mode-compose-context" not in js
    assert "Auto-sent to chat" in js
    assert "Click preview element to highlight" in js
    assert "schedulePoll(status)" in js
    assert "value==='starting'||value==='building'" in js
    assert "lastPreviewAppPath:''" in js
    assert "lastUsefulPreviewAppPath:''" in js
    assert "lastPreviewContextAt:0" in js
    assert "previewRuntimeReady:false" in js
    assert "hermes-ui-mode-preview-route-v1:" in js
    assert "hermes-ui-mode-preview-useful-route-v1:" in js
    assert "isPreviewAuthAppPath" in js
    assert "isPreviewRootAppPath" in js
    assert "rememberPreviewRoute(state.pageContext.appPath)" in js
    assert "currentPreviewReloadUrl" in js
    assert "schedulePreviewReattach" in js
    assert "hermes-ui-mode-chat-settled" in js
    assert "attachPreviewForStatus(status)" in js
    assert "!state.previewRuntimeReady" in js
    assert "setFrameSource(els.previewFrame,target,state.cacheToken)" in js
    assert "params.delete('__hermesUiModeTs')" in js
    assert "previewProxyPrefixFromPath" in js
    assert "data-hermes-ui-proxy-prefix" in compat
    assert "rewriteNavigationUrl" in compat
    assert "history.pushState" in compat
    assert "history.replaceState" in compat
    assert "hermes-ui-preview-context" in compat
    assert "hermes-ui-element-selected" in compat
    assert "inspectorSelectedTargets=[]" in compat
    assert "clearInspectorSelections" in compat
    assert "hermes-ui-clear-highlights" in compat
    assert "drawSelectedOverlays" in compat
    assert "selectedElementDescriptors" in compat
    assert "selectionCount:elements.length" in compat
    assert "data-hermes-ui-inspector-overlay^=\"selected\"" in compat
    assert "data-hermes-ui-inspector-overlay" in compat
    assert "createSelector" in compat
    assert "hermes-ui-preview-apply-patches" in compat
    assert "data-hermes-ui-preview-patch" in compat
    assert "applyPreviewPatches" in compat
    assert "hermes-ui-preview-patches-applied" in compat
    assert "hermes-ui-mode-context-update" in messages
    assert "_uiModeNotifyParentChatSettled" in messages
    assert "hermes-ui-mode-chat-settled" in messages
    assert "hermes-ui-preview-patch" in messages
    assert "_uiModeDispatchPreviewPatchDirectives" in messages
    assert "hermes-ui-preview-patch-request" in messages
    assert "_uiModeSendShellText" in messages
    assert "hermes-ui-mode-send-text" in messages
    assert "_appendUiModeContextToOutgoingText" in messages
    assert "_uiModeFallbackContextText" in messages
    assert "_uiModeContextForOutgoingText" in messages
    assert "_stripUiModePreviewPatchDirectives" in ui_src
    assert "hermes-ui-preview-patch" in ui_src
    assert "Highlighted/selected elements: none" in messages
    assert "_isUiModeChatSession" in messages
    assert "session_mode:_isUiModeChatSession()?'ui_mode':undefined" in messages
    assert "surface:_isUiModeChatSession()?'ui_mode':undefined" in messages
    assert "ui_project_label:_uiModeMetadata.projectLabel||undefined" in messages
    assert "ui_project_workspace:_uiModeMetadata.projectWorkspace||undefined" in messages
    assert "ui_fast_workspace:_uiModeMetadata.fastWorkspace||undefined" in messages
    assert "ui_context_path:_uiModeMetadata.contextPath||undefined" in messages
    assert "workspace:_uiModeMetadata.fastWorkspace||_uiModeMetadata.projectWorkspace||S.session.workspace" in messages
    assert "Project source workspace" in messages
    assert "Runtime workflow source" in js
    assert "Runtime iteration mode" in js
    assert "Play parity available" in js
    assert "Runtime build command" in js
    assert "Runtime start command" in js
    assert "Runtime build policy" in js
    assert "explicit-user-approval" in js
    assert "uiBuildPolicy" in js
    assert "workflowSource:meta.workflowSource" in js
    assert "iterationMode:meta.iterationMode" in js
    assert "uiIterationMode" in js
    assert "uiParityAvailable" in js
    assert "ui_workflow_source:_uiModeMetadata.workflowSource||undefined" in messages
    assert "ui_iteration_mode:_uiModeMetadata.iterationMode||undefined" in messages
    assert "ui_parity_available:_uiModeMetadata.parityAvailable||undefined" in messages
    assert "ui_build_policy:_uiModeMetadata.buildPolicy||undefined" in messages
    assert "Runtime build policy" in messages
    assert "runtime workflow source" in messages
    assert "ui_preview_path:_uiModeMetadata.previewPath||undefined" in messages
    assert "ui-mode?projectId=" in ops_detail
    assert "openUiModeActivitySession" in ops_home
    assert "open-ui-mode-session" in ops_home
    assert "Open UI Mode" in ops_home
    assert "menu-session-activity-badge ui-mode" in ops_home
    assert "shellUrl('ui-mode.html')" in ops_home
    assert ".menu-session-activity-badge.ui-mode" in ops_css
    routes_src = (root / "api" / "routes.py").read_text(encoding="utf-8")
    streaming_src = (root / "api" / "streaming.py").read_text(encoding="utf-8")
    gateway_src = (root / "api" / "gateway_chat.py").read_text(encoding="utf-8")
    assert "_ui_mode_project_workspace" in routes_src
    assert "ui_execution_workspace = _ui_mode_project_workspace" in routes_src
    assert "is_ui_mode_fast_workspace" in routes_src
    assert "UI Mode project source workspace" in streaming_src
    assert "UI Mode runtime workflow source" in streaming_src
    assert "UI Mode iteration mode" in streaming_src
    assert "UI Mode Play parity available" in streaming_src
    assert "Fast path for UI edits" in streaming_src
    assert "source workspace as the working directory" in streaming_src
    assert "Do not run production builds" in streaming_src
    assert "Build policy hard stop" in streaming_src
    assert "explicit-user-approval only" in streaming_src
    assert "Do not run configured deploy/build scripts" in streaming_src
    assert "Rebuild preview now" in streaming_src
    assert "deploy/build scripts as a default" in streaming_src
    assert "Iframe reload does not rebuild" in streaming_src
    assert "Do not make those artifacts current automatically" in streaming_src
    assert "actual preview DOM" in streaming_src
    assert "all selected/highlighted-element descriptors" in streaming_src
    assert "temporary live-preview patch" in streaming_src
    assert "hermes-ui-preview-patch" in streaming_src
    assert "selected elements" in streaming_src
    assert "migrate the journal back into source files" in streaming_src
    assert '"ui_project_workspace"' in gateway_src
    assert '"ui_workflow_source"' in gateway_src
    assert '"ui_iteration_mode"' in gateway_src
    assert '"ui_parity_available"' in gateway_src
    assert '"ui_build_command"' in gateway_src
    assert '"ui_build_policy"' in gateway_src


def test_ui_mode_chat_start_uses_project_source_workspace_for_stale_sidecar_session(tmp_path, monkeypatch):
    project_id = "ui-project-source"
    registry_dir = tmp_path / "registry"
    project_path = tmp_path / "source-project"
    stale_workspace = tmp_path / "project_tasks"
    project_path.mkdir()
    stale_workspace.mkdir()
    _write_project_registry(registry_dir, project_id, project_path)
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(registry_dir))
    monkeypatch.setattr(routes, "resolve_trusted_workspace", lambda path=None: Path(path or project_path).expanduser().resolve())
    monkeypatch.setattr(routes, "set_last_workspace", lambda workspace: None)
    monkeypatch.setattr(routes, "_resolve_compatible_session_model_state", lambda model, provider: (model or "test/model", provider, False))

    session = Session(
        session_id="ui-mode-stale",
        workspace=str(stale_workspace),
        model="test/model",
        session_mode="ui_mode",
        project_id=project_id,
        ui_project_id=project_id,
        ui_project_label="UI Project",
    )

    monkeypatch.setattr(routes, "get_session", lambda session_id: session if session_id == session.session_id else (_ for _ in ()).throw(KeyError(session_id)))
    captured = {}

    def fake_start_chat_stream(s, **kwargs):
        captured.update(kwargs)
        s.workspace = kwargs["workspace"]
        return {"stream_id": "stream-1", "pending_started_at": 1.0}

    monkeypatch.setattr(routes, "_start_chat_stream_for_session", fake_start_chat_stream)

    handler = DummyHandler("POST")
    result = routes._handle_chat_start(
        handler,
        {
            "session_id": session.session_id,
            "message": "Remove selected items",
            "workspace": str(stale_workspace),
            "session_mode": "ui_mode",
            "ui_project_id": project_id,
            "ui_project_label": "UI Project",
        },
    )

    assert result in (True, None)

    assert handler.status == 200
    assert captured["workspace"] == str(project_path.resolve())
    assert session.workspace == str(project_path.resolve())
    assert session.ui_project_workspace == str(project_path.resolve())



def test_ui_mode_can_import_project_play_config(tmp_path):
    project_path = tmp_path / "project"
    project_path.mkdir()
    _write_tiny_play_sourced_ui_project(project_path)

    raw = json.loads((project_path / ".hermes" / "ui.json").read_text(encoding="utf-8"))
    normalized = core_ui.normalize_ui_config(raw, project_path)

    assert normalized["valid"] is True
    assert normalized["source"] == "play-config"
    assert normalized["playConfigPath"].endswith("project_play.json")
    config = normalized["config"]
    assert config["build"]["command"].startswith("python3 -c")
    assert config["dev"]["env"]["AUTH_DEBUG_LOGIN"] == "true"
    assert config["dev"]["env"]["SERVE_CLIENT_BUILD"] == "true"
    assert config["inspect"]["url"] == "/app"


def test_ui_mode_auto_detects_package_dev_before_project_play_config(tmp_path, monkeypatch):
    project_id = "fast-first-ui"
    registry_dir = tmp_path / "registry"
    project_path = tmp_path / "project"
    project_path.mkdir()
    _write_project_registry(registry_dir, project_id, project_path)
    _write_tiny_play_sourced_ui_project(project_path)
    (project_path / ".hermes" / "ui.json").unlink()
    (project_path / "package.json").write_text(json.dumps({"scripts": {"dev": "vite --host 0.0.0.0"}}), encoding="utf-8")
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(registry_dir))

    config_info = core_ui.get_project_ui_config_file_info(project_id)

    assert config_info["exists"] is False
    assert config_info["autoDetected"] is True
    assert config_info["autoSource"] == "package.json"
    assert config_info["source"] == "ui-config"
    assert config_info["valid"] is True
    assert config_info["playConfigPath"] == ""
    assert config_info["parityAvailable"] is True
    assert config_info["parityWorkflowSource"] == "play-config"
    assert config_info["parityConfigPath"].endswith("project_play.json")

    resolved = core_ui.get_project_ui_config(project_id)
    assert resolved["autoDetected"] is True
    assert resolved["autoSource"] == "package.json"
    assert resolved["source"] == "package.json"
    assert resolved["config"]["build"]["command"] == ""
    assert resolved["config"]["dev"]["command"] == "npm run dev"
    assert resolved["config"]["inspect"]["url"] == "/"

    parity = core_ui.get_project_ui_config(project_id, workflow="play-config")
    assert parity["autoDetected"] is True
    assert parity["autoSource"] == "project_play.json"
    assert parity["source"] == "play-config"
    assert parity["config"]["build"]["command"].startswith("python3 -c")
    assert parity["config"]["dev"]["command"] == "python3 -u server.py"
    assert parity["config"]["inspect"]["url"] == "/app"

    status = core_ui.build_project_ui_status(project_id)
    assert status["canStart"] is True
    assert status["workflowSource"] == "package.json"
    assert status["iterationMode"] == "fast-dev"
    assert status["buildPolicy"] == "explicit-user-approval"
    assert status["parityAvailable"] is True
    assert status["parityWorkflowSource"] == "play-config"
    assert status["configAutoDetected"] is True
    assert status["configAutoSource"] == "package.json"
    assert "fast UI workflow" in status["statusSummary"]


def test_ui_mode_auto_detects_monorepo_template_client_dev_with_play_parity(tmp_path, monkeypatch):
    project_id = "monorepo-template-ui"
    registry_dir = tmp_path / "registry"
    project_path = tmp_path / "project"
    project_path.mkdir()
    _write_project_registry(registry_dir, project_id, project_path)
    _write_monorepo_template_project(project_path)
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(registry_dir))

    config_info = core_ui.get_project_ui_config_file_info(project_id)

    assert config_info["exists"] is False
    assert config_info["autoDetected"] is True
    assert config_info["autoSource"] == "monorepo-template:packages/client"
    assert config_info["source"] == "ui-config"
    assert config_info["valid"] is True
    assert config_info["parityAvailable"] is True
    assert config_info["parityWorkflowSource"] == "play-config"
    assert config_info["parityConfigPath"].endswith("project_play.json")

    resolved = core_ui.get_project_ui_config(project_id)
    assert resolved["autoDetected"] is True
    assert resolved["autoSource"] == "monorepo-template:packages/client"
    assert resolved["source"] == "monorepo-template:packages/client"
    assert resolved["config"]["build"]["command"] == ""
    dev = resolved["config"]["dev"]
    assert dev["cwd"] == "."
    assert dev["command"] == "pnpm --filter ./packages/client run dev --host 127.0.0.1 --port ${PORT} --strictPort"
    assert dev["env"]["MONOREPO_ACTIVE_APP"] == "model-builder"
    assert dev["env"]["COREPACK_ENABLE_DOWNLOAD_PROMPT"] == "0"
    assert dev["env"]["NPM_CONFIG_STORE_DIR"] == ".cache/pnpm-store"
    assert "SERVE_CLIENT_BUILD" not in dev["env"]
    assert resolved["config"]["inspect"]["url"] == "/"

    parity = core_ui.get_project_ui_config(project_id, workflow="play-config")
    assert parity["source"] == "play-config"
    assert parity["config"]["build"]["command"] == "bash ./scripts/deploy-build.sh model-builder"
    assert parity["config"]["dev"]["env"]["SERVE_CLIENT_BUILD"] == "true"
    assert parity["config"]["inspect"]["url"] == "/app"

    status = core_ui.build_project_ui_status(project_id)
    assert status["canStart"] is True
    assert status["workflowSource"] == "monorepo-template:packages/client"
    assert status["iterationMode"] == "fast-dev"
    assert status["buildPolicy"] == "explicit-user-approval"
    assert status["parityAvailable"] is True
    assert status["configAutoSource"] == "monorepo-template:packages/client"
    assert "fast UI workflow" in status["statusSummary"]
    assert "monorepo template packages/client dev lane" in status["statusSummary"]


def test_ui_mode_auto_detects_monorepo_template_ui_dev_contract_before_client_fallback(tmp_path, monkeypatch):
    project_id = "monorepo-template-ui-dev"
    registry_dir = tmp_path / "registry"
    project_path = tmp_path / "project"
    project_path.mkdir()
    _write_project_registry(registry_dir, project_id, project_path)
    _write_monorepo_template_project(project_path)
    _add_monorepo_template_ui_dev_contract(project_path)
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(registry_dir))

    config_info = core_ui.get_project_ui_config_file_info(project_id)

    assert config_info["exists"] is False
    assert config_info["autoDetected"] is True
    assert config_info["autoSource"] == "monorepo-template:ui-dev"
    assert config_info["valid"] is True
    assert config_info["parityAvailable"] is True

    resolved = core_ui.get_project_ui_config(project_id)
    assert resolved["autoDetected"] is True
    assert resolved["autoSource"] == "monorepo-template:ui-dev"
    assert resolved["source"] == "monorepo-template:ui-dev"
    dev = resolved["config"]["dev"]
    assert dev["command"] == "pnpm run ui:dev"
    assert dev["env"]["MONOREPO_ACTIVE_APP"] == "model-builder"
    assert "SERVE_CLIENT_BUILD" not in dev["env"]

    status = core_ui.build_project_ui_status(project_id)
    assert status["workflowSource"] == "monorepo-template:ui-dev"
    assert status["iterationMode"] == "fast-dev"
    assert status["configAutoDetected"] is True
    assert status["configAutoSource"] == "monorepo-template:ui-dev"
    assert "monorepo template ui:dev contract" in status["statusSummary"]


def test_ui_mode_uses_tracked_monorepo_template_project_ui_contract(tmp_path, monkeypatch):
    project_id = "monorepo-template-project-ui"
    registry_dir = tmp_path / "registry"
    project_path = tmp_path / "project"
    project_path.mkdir()
    _write_project_registry(registry_dir, project_id, project_path)
    _write_monorepo_template_project(project_path)
    _add_monorepo_template_ui_dev_contract(project_path)
    _write_monorepo_template_ui_config(project_path)
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(registry_dir))

    config_info = core_ui.get_project_ui_config_file_info(project_id)

    assert config_info["exists"] is True
    assert config_info["autoDetected"] is False
    assert config_info["source"] == "monorepo-template:ui-dev"
    assert config_info["valid"] is True
    assert config_info["parityAvailable"] is True
    assert config_info["parityWorkflowSource"] == "play-config"
    assert config_info["parityConfigPath"].endswith("project_play.json")

    resolved = core_ui.get_project_ui_config(project_id)
    assert resolved.get("autoDetected") is not True
    assert resolved["source"] == "monorepo-template:ui-dev"
    assert resolved["config"]["dev"]["command"] == "pnpm run ui:dev"
    assert resolved["config"]["dev"]["env"]["COREPACK_ENABLE_DOWNLOAD_PROMPT"] == "0"
    assert "SERVE_CLIENT_BUILD" not in resolved["config"]["dev"]["env"]

    status = core_ui.build_project_ui_status(project_id)
    assert status["workflowSource"] == "monorepo-template:ui-dev"
    assert status["iterationMode"] == "fast-dev"
    assert status["parityAvailable"] is True
    assert status["configAutoDetected"] is False
    assert status["configAutoSource"] == ""
    assert status["statusSummary"] == "UI workflow is ready. Start UI Mode to inspect the live app."


def test_ui_mode_project_ui_contract_wins_over_legacy_local_play_pointer(tmp_path, monkeypatch):
    project_id = "monorepo-template-local-play-pointer"
    registry_dir = tmp_path / "registry"
    project_path = tmp_path / "project"
    project_path.mkdir()
    _write_project_registry(registry_dir, project_id, project_path)
    _write_monorepo_template_project(project_path)
    _add_monorepo_template_ui_dev_contract(project_path)
    _write_monorepo_template_ui_config(project_path)
    (project_path / ".hermes").mkdir(parents=True, exist_ok=True)
    (project_path / ".hermes" / "ui.json").write_text(json.dumps({"version": 1, "source": "project_play.json"}), encoding="utf-8")
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(registry_dir))

    config_info = core_ui.get_project_ui_config_file_info(project_id)

    assert config_info["exists"] is True
    assert config_info["path"].endswith("project_ui.json")
    assert config_info["source"] == "monorepo-template:ui-dev"
    assert config_info["valid"] is True
    assert config_info["parityAvailable"] is True
    assert config_info["parityWorkflowSource"] == "play-config"
    assert config_info["parityConfigPath"].endswith("project_play.json")

    resolved = core_ui.get_project_ui_config(project_id)
    assert resolved["path"].endswith("project_ui.json")
    assert resolved["source"] == "monorepo-template:ui-dev"
    assert resolved["config"]["dev"]["command"] == "pnpm run ui:dev"
    assert "SERVE_CLIENT_BUILD" not in resolved["config"]["dev"]["env"]

    parity = core_ui.get_project_ui_config(project_id, workflow="play-config")
    assert parity["source"] == "play-config"
    assert parity["config"]["build"]["command"] == "bash ./scripts/deploy-build.sh model-builder"
    assert parity["config"]["dev"]["command"] == "node -r ./scripts/register-runtime-paths.cjs packages/server/dist/packages/server/index.js"
    assert parity["config"]["dev"]["env"]["SERVE_CLIENT_BUILD"] == "true"
    assert parity["config"]["inspect"]["url"] == "/app"

    status = core_ui.build_project_ui_status(project_id)
    assert status["workflowSource"] == "monorepo-template:ui-dev"
    assert status["iterationMode"] == "fast-dev"
    assert status["parityAvailable"] is True


def test_ui_mode_default_start_uses_fast_package_dev_not_play_build(tmp_path, monkeypatch):
    project_id = "fast-start-ui"
    registry_dir = tmp_path / "registry"
    project_path = tmp_path / "project"
    project_path.mkdir()
    _write_project_registry(registry_dir, project_id, project_path)
    _write_tiny_play_sourced_ui_project(project_path)
    (project_path / ".hermes" / "ui.json").unlink()
    (project_path / "package.json").write_text(json.dumps({"scripts": {"dev": "python3 -u server.py"}}), encoding="utf-8")
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(registry_dir))

    captured = {}

    def fake_runtime_worker(ui_config, state):
        captured["ui_config"] = ui_config
        core_ui._mark_state(
            state,
            "ready",
            running=True,
            ready=True,
            preview_url=f"/ui-project/{project_id}/",
            inspect_url=f"/ui-project/{project_id}/",
            set_ready_at=True,
            message="fake ready",
        )

    monkeypatch.setattr(core_ui, "_runtime_worker", fake_runtime_worker)
    try:
        started = core_ui.start_project_ui_runtime(project_id, {"sessionId": "session-1"})
        assert started["status"] in {"starting", "ready"}
        deadline = time.time() + 2
        while time.time() < deadline and "ui_config" not in captured:
            time.sleep(0.02)

        ui_config = captured["ui_config"]
        assert ui_config["source"] == "package.json"
        assert ui_config["config"]["build"]["command"] == ""
        assert ui_config["config"]["dev"]["command"] == "npm run dev"
        assert not (project_path / "built.txt").exists()

        status = core_ui.build_project_ui_status(project_id)
        assert status["ready"] is True
        assert status["workflowSource"] == "package.json"
        assert status["iterationMode"] == "fast-dev"
        assert status["parityAvailable"] is True
        assert status["buildCommand"] in (None, "")
    finally:
        core_ui.stop_project_ui_runtime(project_id, purge=True)


def test_ui_mode_explicit_start_can_use_play_parity_build(tmp_path, monkeypatch):
    project_id = "parity-start-ui"
    registry_dir = tmp_path / "registry"
    project_path = tmp_path / "project"
    project_path.mkdir()
    _write_project_registry(registry_dir, project_id, project_path)
    _write_tiny_play_sourced_ui_project(project_path)
    (project_path / ".hermes" / "ui.json").unlink()
    (project_path / "package.json").write_text(json.dumps({"scripts": {"dev": "python3 -u server.py"}}), encoding="utf-8")
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(registry_dir))

    captured = {}

    def fake_runtime_worker(ui_config, state):
        captured["ui_config"] = ui_config
        core_ui._mark_state(
            state,
            "ready",
            running=True,
            ready=True,
            preview_url=f"/ui-project/{project_id}/app",
            inspect_url=f"/ui-project/{project_id}/app",
            set_ready_at=True,
            message="fake parity ready",
        )

    monkeypatch.setattr(core_ui, "_runtime_worker", fake_runtime_worker)
    try:
        started = core_ui.start_project_ui_runtime(project_id, {"sessionId": "session-1", "workflow": "play-config"})
        assert started["status"] in {"starting", "ready"}
        deadline = time.time() + 2
        while time.time() < deadline and "ui_config" not in captured:
            time.sleep(0.02)

        ui_config = captured["ui_config"]
        assert ui_config["source"] == "play-config"
        assert ui_config["config"]["build"]["command"].startswith("python3 -c")
        assert ui_config["config"]["dev"]["command"] == "python3 -u server.py"

        status = core_ui.build_project_ui_status(project_id)
        assert status["ready"] is True
        assert status["workflowSource"] == "play-config"
        assert status["iterationMode"] == "play-parity"
        assert status["parityAvailable"] is False
    finally:
        core_ui.stop_project_ui_runtime(project_id, purge=True)


def test_ui_mode_shell_cache_busts_script_by_file_mtime():
    root = Path(__file__).resolve().parents[1]
    script_mtime = (root / "static" / "ui-mode.js").stat().st_mtime_ns
    handler = DummyHandler("GET")
    second_handler = DummyHandler("GET")

    assert core_ui.serve_ui_mode_shell(handler) is True
    assert core_ui.serve_ui_mode_shell(second_handler) is True

    body = handler.wfile.getvalue().decode("utf-8")
    second_body = second_handler.wfile.getvalue().decode("utf-8")
    assert f"static/ui-mode.js?v=" in body
    assert str(script_mtime) in body
    first_token = body.split("static/ui-mode.js?v=", 1)[1].split('"', 1)[0]
    second_token = second_body.split("static/ui-mode.js?v=", 1)[1].split('"', 1)[0]
    assert first_token != second_token


def test_proxy_rewrites_vite_absolute_module_paths():
    project_id = "project-1"
    prefix = "/ui-project/project-1"
    html_body = b'''<!doctype html><html><head>
<script type="module">import { injectIntoGlobalHook } from "/@react-refresh"; import("/src/lazy.tsx");</script>
<script type="module" src="/@vite/client"></script>
</head><body><script type="module" src="/src/main.tsx"></script></body></html>'''
    html_text = core_ui._rewrite_html(html_body, project_id).decode("utf-8")
    assert f'from "{prefix}/@react-refresh"' in html_text
    assert f'import("{prefix}/src/lazy.tsx")' in html_text
    assert f'src="{prefix}/@vite/client"' in html_text
    assert f'src="{prefix}/src/main.tsx"' in html_text
    assert 'ui-proxy-compat.js?v=' in html_text

    js_body = b'''import "/@vite/client";
import dep from "/node_modules/.vite/deps/react.js?v=123";
import css from "/@fs/home/project/style.css";
const lazy = import('/src/lazy.tsx');
const cssUrl = "body{background:url('/@fs/home/project/font.woff2')}";
'''
    js_text = core_ui._rewrite_proxy_text(js_body, project_id).decode("utf-8")
    assert f'import "{prefix}/@vite/client"' in js_text
    assert f'from "{prefix}/node_modules/.vite/deps/react.js?v=123"' in js_text
    assert f'from "{prefix}/@fs/home/project/style.css"' in js_text
    assert f"import('{prefix}/src/lazy.tsx')" in js_text
    assert f"url('{prefix}/@fs/home/project/font.woff2')" in js_text


def test_top_level_ui_routes_delegate(monkeypatch):
    calls = []
    monkeypatch.setattr(core_ui, "serve_ui_mode_shell", lambda handler: calls.append(("shell",)) or True)

    def fake_proxy(handler, project_id, target_path, parsed, *, method="GET"):
        calls.append(("proxy", project_id, target_path, parsed.query, method))
        handler.send_response(200)
        handler.end_headers()

    monkeypatch.setattr(core_ui, "handle_ui_proxy_request", fake_proxy)

    assert routes.handle_get(DummyHandler("GET"), urlparse("/ui-mode")) is True
    assert routes.handle_get(DummyHandler("GET"), urlparse("/ui-project/project%201/nested/path?x=1")) is True
    assert calls == [("shell",), ("proxy", "project 1", "/nested/path", "x=1", "GET")]


def test_ui_mode_referer_keeps_root_relative_app_navigation_under_proxy():
    handler = DummyHandler("GET")
    handler.headers["Referer"] = "http://127.0.0.1:5003/ui-project/project%201/login"

    assert routes.handle_get(handler, urlparse("/app?from=login")) is True
    assert handler.status == 307
    assert handler.header("Location") == "/ui-project/project%201/app?from=login"

    normal = DummyHandler("GET")
    assert routes.handle_get(normal, urlparse("/app")) is False


def test_core_ui_runtime_lifecycle_and_html_proxy(tmp_path, monkeypatch):
    project_id = "tiny-ui"
    registry_dir = tmp_path / "registry"
    project_path = tmp_path / "project"
    project_path.mkdir()
    _write_project_registry(registry_dir, project_id, project_path)
    _write_tiny_ui_project(project_path)
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(registry_dir))

    try:
        config_info = core_ui.get_project_ui_config_file_info(project_id)
        assert config_info["exists"] is True
        assert config_info["valid"] is True

        started = core_ui.start_project_ui_runtime(project_id, {"sessionId": "session-1"})
        assert started["status"] in {"starting", "ready"}

        deadline = time.time() + 12
        status = core_ui.build_project_ui_status(project_id)
        while time.time() < deadline:
            status = core_ui.build_project_ui_status(project_id)
            if status["ready"]:
                break
            if status["status"] == "failed":
                raise AssertionError(status.get("error") or status)
            time.sleep(0.2)
        assert status["ready"] is True
        assert status["previewUrl"].startswith("/ui-project/tiny-ui/")
        assert status["allocatedPortHost"] == "127.0.0.1"

        parsed = urlparse(status["previewUrl"])
        handler = DummyHandler("GET")
        core_ui.handle_ui_proxy_request(handler, project_id, parsed.path[len("/ui-project/tiny-ui"):], parsed, method="GET")
        body = handler.wfile.getvalue().decode("utf-8")
        assert handler.status == 200
        assert handler.header("Cache-Control") == "no-store, no-cache, must-revalidate, max-age=0"
        assert handler.header("Pragma") == "no-cache"
        assert handler.header("Expires") == "0"
        assert handler.header("Referrer-Policy") == "same-origin"
        assert "Tiny UI" in body
        assert "/ui-project/tiny-ui/asset.js" in body
        assert "ui-proxy-compat.js" in body

        logs = core_ui.build_project_ui_logs(project_id, 100)
        assert "READY" in logs["text"]
    finally:
        core_ui.stop_project_ui_runtime(project_id, purge=True)


def test_core_ui_play_sourced_runtime_runs_build_before_start(tmp_path, monkeypatch):
    project_id = "tiny-play-ui"
    registry_dir = tmp_path / "registry"
    project_path = tmp_path / "project"
    project_path.mkdir()
    _write_project_registry(registry_dir, project_id, project_path)
    _write_tiny_play_sourced_ui_project(project_path)
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(registry_dir))

    try:
        config_info = core_ui.get_project_ui_config_file_info(project_id)
        assert config_info["valid"] is True
        assert config_info["source"] == "play-config"
        assert config_info["playConfigPath"].endswith("project_play.json")

        started = core_ui.start_project_ui_runtime(project_id, {"sessionId": "session-1"})
        assert started["status"] in {"building", "starting", "ready"}

        deadline = time.time() + 12
        status = core_ui.build_project_ui_status(project_id)
        while time.time() < deadline:
            status = core_ui.build_project_ui_status(project_id)
            if status["ready"]:
                break
            if status["status"] == "failed":
                raise AssertionError(status.get("error") or status)
            time.sleep(0.2)
        assert status["ready"] is True
        assert status["configSource"] == "play-config"
        assert status["previewUrl"].startswith("/ui-project/tiny-play-ui/app")
        assert status["buildCommand"].startswith("python3 -c")
        assert status["command"] == "python3 -u server.py"
        assert (project_path / "built.txt").read_text(encoding="utf-8") == "ok"

        logs = core_ui.build_project_ui_logs(project_id, 100)
        assert "Build stage completed successfully" in logs["text"]
        assert "AUTH_DEBUG_LOGIN" not in logs["text"]
    finally:
        core_ui.stop_project_ui_runtime(project_id, purge=True)

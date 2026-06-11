from __future__ import annotations

import io
import json
import time
from pathlib import Path
from urllib.parse import urlparse

from api import core_contracts, core_ui, models, routes, routes_core
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


def test_core_contract_exposes_ui_domain():
    route_map = core_contracts.public_route_map()
    assert "ui" in route_map["domains"]
    assert "GET /projects/{projectId}/ui/status" in route_map["domains"]["ui"]
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
    )

    assert session.session_mode == "ui_mode"
    compact = session.compact()
    assert compact["session_mode"] == "ui_mode"
    assert compact["ui_project_id"] == "summons-project"
    assert compact["ui_project_label"] == "Summons"
    assert compact["ui_preview_path"] == "/app"
    assert compact["ui_preview_title"] == "Summons Arena"

    session.save(skip_index=True)
    loaded = Session.load("ui-mode-session")

    assert loaded is not None
    assert loaded.session_mode == "ui_mode"
    assert loaded.ui_project_id == "summons-project"
    assert loaded.ui_project_label == "Summons"
    assert loaded.ui_preview_path == "/app"
    assert loaded.ui_preview_title == "Summons Arena"
    assert loaded.compact()["session_mode"] == "ui_mode"


def test_core_ui_routes_delegate_to_core_ui(monkeypatch):
    calls = []
    monkeypatch.setattr(core_ui, "get_project_ui_config_file_info", lambda project_id: calls.append(("config", project_id)) or {"projectId": project_id, "valid": True})
    monkeypatch.setattr(core_ui, "build_project_ui_status", lambda project_id: calls.append(("status", project_id)) or {"projectId": project_id, "status": "ready"})
    monkeypatch.setattr(core_ui, "build_project_ui_logs", lambda project_id, limit: calls.append(("logs", project_id, limit)) or {"projectId": project_id, "logs": []})
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

    body = {"sessionId": "abc123"}
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
        ("start", "project 1", body),
        ("restart", "project 1", body),
        ("stop", "project 1"),
    ]


def test_ui_mode_shell_and_static_sources_are_present():
    root = Path(__file__).resolve().parents[1]
    html = (root / "static" / "ui-mode.html").read_text(encoding="utf-8")
    js = (root / "static" / "ui-mode.js").read_text(encoding="utf-8")
    compat = (root / "static" / "ui-proxy-compat.js").read_text(encoding="utf-8")
    messages = (root / "static" / "messages.js").read_text(encoding="utf-8")
    ops_detail = (root / "static" / "ops-legacy-project-detail.js").read_text(encoding="utf-8")

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
    assert html.count('data-action="focus-preview"') == 1
    assert "Refresh status" in html
    assert "__CSRF_TOKEN_JSON__" in html
    assert "api/core/projects/" in js
    assert "api/session/new" in js
    assert "session_mode:'ui_mode'" in js
    assert "surface:'ui_mode'" in js
    assert "chatUrl.searchParams.set('sessionMode','ui_mode')" in js
    assert "sessionVerified:false" in js
    assert "api/session?session_id=" in js
    assert "clearChatSessionFromUrl" in js
    assert "Recreating session…" in js
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
    assert "hermes-ui-preview-context" in js
    assert "hermes-ui-mode-context-update" in js
    assert "sendContextToChat" not in js
    assert "hermes-ui-mode-compose-context" not in js
    assert "Auto-sent to chat" in js
    assert "Click preview element to highlight" in js
    assert "schedulePoll(status)" in js
    assert "value==='starting'||value==='building'" in js
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
    assert "hermes-ui-mode-context-update" in messages
    assert "_appendUiModeContextToOutgoingText" in messages
    assert "_uiModeFallbackContextText" in messages
    assert "_uiModeContextForOutgoingText" in messages
    assert "Highlighted/selected elements: none" in messages
    assert "_isUiModeChatSession" in messages
    assert "session_mode:_isUiModeChatSession()?'ui_mode':undefined" in messages
    assert "surface:_isUiModeChatSession()?'ui_mode':undefined" in messages
    assert "ui_project_label:_uiModeMetadata.projectLabel||undefined" in messages
    assert "ui_project_workspace:_uiModeMetadata.projectWorkspace||undefined" in messages
    assert "workspace:_uiModeMetadata.projectWorkspace||S.session.workspace" in messages
    assert "Project source workspace" in messages
    assert "ui_preview_path:_uiModeMetadata.previewPath||undefined" in messages
    assert "ui-mode?projectId=" in ops_detail
    routes_src = (root / "api" / "routes.py").read_text(encoding="utf-8")
    streaming_src = (root / "api" / "streaming.py").read_text(encoding="utf-8")
    gateway_src = (root / "api" / "gateway_chat.py").read_text(encoding="utf-8")
    assert "_ui_mode_project_workspace" in routes_src
    assert "ui_project_workspace = _ui_mode_project_workspace" in routes_src
    assert "UI Mode project source workspace" in streaming_src
    assert "Fast path for UI edits" in streaming_src
    assert "source workspace as the working directory" in streaming_src
    assert "Do not run production builds" in streaming_src
    assert "all selected/highlighted-element descriptors" in streaming_src
    assert '"ui_project_workspace"' in gateway_src


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

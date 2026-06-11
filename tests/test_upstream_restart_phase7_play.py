import io
import json
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest


def run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


@pytest.fixture()
def git_available():
    if not shutil.which("git"):
        pytest.skip("git is not available")


class _Headers(dict):
    def items(self):
        return super().items()


class _FakeHandler:
    def __init__(self, body=None, *, host="example.com", command="GET"):
        raw = json.dumps(body or {}).encode("utf-8")
        self.command = command
        self.status = None
        self.sent_headers = []
        self.body = bytearray()
        self.wfile = self
        self.rfile = io.BytesIO(raw)
        self.headers = _Headers({"Content-Length": str(len(raw)), "Host": host})

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent_headers.append((name, value))

    def end_headers(self):
        pass

    def write(self, data):
        self.body.extend(data)

    def header(self, name):
        for key, value in self.sent_headers:
            if key.lower() == name.lower():
                return value
        return None


def _response_json(handler: _FakeHandler) -> dict:
    return json.loads(bytes(handler.body).decode("utf-8"))


def init_project_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "play-project"
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    run_git(repo, "checkout", "-b", "feature/play-slice")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "initial")
    return repo


def valid_direct_config():
    return {
        "version": 2,
        "build": {"command": "python -c \"print('build')\"", "cwd": "."},
        "start": {"command": "python -c \"print('start')\"", "cwd": "."},
        "inspect": {"mode": "direct", "url": "http://127.0.0.1:5000/"},
    }


def valid_proxy_config():
    return {
        "version": 2,
        "build": {"command": "python -c \"print('build')\"", "cwd": "."},
        "start": {
            "command": "python -c \"print('start')\"",
            "cwd": ".",
            "port": {"mode": "auto", "host": "127.0.0.1", "envVar": "PORT", "range": {"min": 26000, "max": 26010}},
        },
        "inspect": {"mode": "proxy", "url": "/app"},
    }


def setup_project(monkeypatch, tmp_path, play_config, *, play_path="project_play.json"):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))
    repo = init_project_repo(tmp_path)
    target = repo / play_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(play_config, ensure_ascii=False, indent=2), encoding="utf-8")
    from api import ops_projects, play_pipeline

    project = ops_projects.create_ops_project({"name": "Play Project", "path": str(repo), "coreBranch": "main"})
    with play_pipeline._LOCK:
        play_pipeline._PIPELINES.clear()
        play_pipeline._RESERVED_PORTS.clear()
    return repo, project["id"]


def test_phase7_play_config_preference_and_document_routes_are_not_exposed(monkeypatch, tmp_path, git_available):
    repo, project_id = setup_project(monkeypatch, tmp_path, valid_direct_config())
    (repo / ".cloud-terminal").mkdir(parents=True, exist_ok=True)
    (repo / ".cloud-terminal" / "play.json").write_text(
        json.dumps({**valid_direct_config(), "inspect": {"mode": "direct", "url": "http://127.0.0.1:6000/"}}),
        encoding="utf-8",
    )

    from api import play_pipeline
    from api.routes import handle_get, handle_post

    info = play_pipeline.get_project_play_config_file_info(project_id)
    status = play_pipeline.build_project_play_status(project_id)

    assert info["exists"] is True
    assert info["valid"] is True
    assert info["configured"] is True
    assert info["path"] == str(repo / "project_play.json")
    assert status["status"] == "idle"
    assert status["configured"] is True
    assert status["configPath"] == str(repo / "project_play.json")

    saved_config = valid_proxy_config()
    config_save = _FakeHandler({"content": json.dumps(saved_config, ensure_ascii=False, indent=2)}, command="POST")
    assert handle_post(config_save, urlparse(f"http://example.com/api/ops/projects/{project_id}/play/config")) is False
    assert not (repo / ".hermes" / "play.json").exists()

    config_doc = _FakeHandler()
    assert handle_get(config_doc, urlparse(f"http://example.com/api/ops/projects/{project_id}/play/config")) is False


def test_phase7_play_auto_detects_package_scripts_when_config_file_is_missing(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))
    repo = init_project_repo(tmp_path)
    (repo / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (repo / "package.json").write_text(
        json.dumps(
            {
                "name": "auto-play-project",
                "private": True,
                "scripts": {"build": "echo build", "dev": "echo ready"},
            }
        ),
        encoding="utf-8",
    )
    from api import ops_projects, play_pipeline

    project = ops_projects.create_ops_project({"name": "Auto Play Project", "path": str(repo), "coreBranch": "main"})
    with play_pipeline._LOCK:
        play_pipeline._PIPELINES.clear()
        play_pipeline._RESERVED_PORTS.clear()

    info = play_pipeline.get_project_play_config_file_info(project["id"])
    status = play_pipeline.build_project_play_status(project["id"])
    config = play_pipeline.get_project_play_config(project["id"])

    assert info["exists"] is False
    assert info["autoDetected"] is True
    assert info["valid"] is True
    assert status["configured"] is True
    assert status["buildAvailable"] is True
    assert status["canBuild"] is True
    assert status["configAvailable"] is True
    assert status["configExists"] is False
    assert status["configAutoDetected"] is True
    assert status["buildOnly"] is False
    assert "Auto-detected Play workflow" in status["statusSummary"]
    assert config["config"]["build"]["command"] == "pnpm run build"
    assert config["config"]["start"]["command"] == "pnpm run dev"
    assert config["config"]["inspect"]["mode"] == "proxy"


def test_phase7_play_auto_detects_build_only_package_script(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))
    repo = init_project_repo(tmp_path)
    (repo / "package.json").write_text(
        json.dumps(
            {
                "name": "build-only-project",
                "private": True,
                "scripts": {"build": "echo build"},
            }
        ),
        encoding="utf-8",
    )
    from api import ops_notifications, ops_projects, play_pipeline
    from api.routes import handle_post

    project = ops_projects.create_ops_project({"name": "Build Only Project", "path": str(repo), "coreBranch": "main"})
    with play_pipeline._LOCK:
        play_pipeline._PIPELINES.clear()
        play_pipeline._RESERVED_PORTS.clear()

    info = play_pipeline.get_project_play_config_file_info(project["id"])
    status = play_pipeline.build_project_play_status(project["id"])
    config = play_pipeline.get_project_play_config(project["id"])

    assert info["exists"] is False
    assert info["autoDetected"] is True
    assert info["valid"] is True
    assert info["missing"] == []
    assert info["buildOnly"] is True
    assert status["configured"] is True
    assert status["buildAvailable"] is True
    assert status["canBuild"] is True
    assert status["configAvailable"] is True
    assert status["configExists"] is False
    assert status["buildOnly"] is True
    assert "package-script build workflow" in status["statusSummary"]
    assert config["config"]["buildOnly"] is True
    assert config["config"]["build"]["command"] == "npm run build"
    assert config["config"]["start"]["command"] == ""

    def fake_run_build_stage(_project_path, _config, state):
        play_pipeline._append_log(state, stage="build", stream="system", message="Build stage completed successfully.")

    monkeypatch.setattr(play_pipeline, "_run_build_stage", fake_run_build_stage)

    start = _FakeHandler({}, command="POST")
    assert handle_post(start, urlparse(f"http://example.com/api/ops/projects/{project['id']}/play/start")) is True

    deadline = time.time() + 2
    built_status = None
    while time.time() < deadline:
        built_status = play_pipeline.build_project_play_status(project["id"])
        if built_status["status"] == "built":
            break
        time.sleep(0.05)

    assert built_status is not None
    assert built_status["status"] == "built"
    assert built_status["ready"] is False
    assert built_status["inspectUrl"] is None
    assert built_status["buildOnly"] is True
    assert "Package-script build completed" in built_status["statusSummary"]

    payload = ops_notifications.list_pending_notifications(project["id"])
    play_note = next(item for item in payload["notifications"] if item["kind"] == "play")
    assert play_note["playStatus"] == "built"
    assert play_note["playNeedsRepair"] is False
    assert play_note["playLocked"] is False
    assert "Package-script build completed" in play_note["message"]


def test_phase7_play_start_stop_status_and_logs(monkeypatch, tmp_path, git_available):
    _repo, project_id = setup_project(monkeypatch, tmp_path, valid_proxy_config())

    from api import play_pipeline
    from api.routes import handle_get, handle_post

    def fake_run_build_stage(_project_path, _config, state):
      play_pipeline._append_log(state, stage="build", stream="system", message="Build stage completed successfully.")

    def fake_run_start_stage(_project, _project_path, runtime, state):
      play_pipeline._append_log(state, stage="start", stream="system", message="Application is ready for inspection.")
      play_pipeline._mark_state(state, "ready", running=True, ready=True, inspect_url=runtime["inspectUrl"], set_ready_at=True)

    monkeypatch.setattr(play_pipeline, "_run_build_stage", fake_run_build_stage)
    monkeypatch.setattr(play_pipeline, "_run_start_stage", fake_run_start_stage)
    monkeypatch.setattr(
        play_pipeline.managed_postgres,
        "ensure_project_database_env",
        lambda project_id: {
            "DATASTORE_ADAPTER": "postgres",
            "DATABASE_URL": f"postgresql://hermes:test@127.0.0.1:5433/hermes_{project_id}",
            "DATASTORE_POSTGRES_URL": f"postgresql://hermes:test@127.0.0.1:5433/hermes_{project_id}",
            "NAKAMA_DATABASE_URL": f"postgresql://hermes:test@127.0.0.1:5433/hermes_{project_id}",
            "PGHOST": "127.0.0.1",
            "PGPORT": "5433",
            "PGUSER": "hermes",
            "PGPASSWORD": "test",
            "PGDATABASE": f"hermes_{project_id}",
        },
    )

    start = _FakeHandler({}, command="POST")
    assert handle_post(start, urlparse(f"http://example.com/api/ops/projects/{project_id}/play/start")) is True
    assert _response_json(start)["started"] is True

    deadline = time.time() + 2
    ready_status = None
    while time.time() < deadline:
        ready_status = play_pipeline.build_project_play_status(project_id)
        if ready_status["ready"] is True:
            break
        time.sleep(0.05)
    assert ready_status is not None
    assert ready_status["ready"] is True
    assert ready_status["inspectUrl"] == f"/play-project/{project_id}/app"

    status_get = _FakeHandler()
    assert handle_get(status_get, urlparse(f"http://example.com/api/ops/projects/{project_id}/play/status")) is True
    assert _response_json(status_get)["ready"] is True

    logs_get = _FakeHandler()
    assert handle_get(logs_get, urlparse(f"http://example.com/api/ops/projects/{project_id}/play/logs?limit=50")) is True
    logs_payload = _response_json(logs_get)
    assert "Application is ready for inspection." in logs_payload["text"]

    restart = _FakeHandler({}, command="POST")
    assert handle_post(restart, urlparse(f"http://example.com/api/ops/projects/{project_id}/play/restart")) is True
    assert _response_json(restart)["restarted"] is True

    stop = _FakeHandler({}, command="POST")
    assert handle_post(stop, urlparse(f"http://example.com/api/ops/projects/{project_id}/play/stop")) is True
    assert _response_json(stop)["stopped"] is True


def test_phase7_play_build_timeout_fails_locked_notification(monkeypatch, tmp_path, git_available):
    config = valid_proxy_config()
    config["build"] = {
        **config["build"],
        "command": f"{sys.executable} -c \"import time; time.sleep(3)\"",
        "timeoutMs": 1000,
    }
    _repo, project_id = setup_project(monkeypatch, tmp_path, config)

    from api import ops_notifications, play_pipeline
    from api.routes import handle_post

    start = _FakeHandler({}, command="POST")
    assert handle_post(start, urlparse(f"http://example.com/api/ops/projects/{project_id}/play/start")) is True

    deadline = time.time() + 4
    failed_status = None
    while time.time() < deadline:
        failed_status = play_pipeline.build_project_play_status(project_id)
        if failed_status["status"] == "failed":
            break
        time.sleep(0.05)

    assert failed_status is not None
    assert failed_status["status"] == "failed"
    assert "Build timeout after 1s" in failed_status["error"]
    payload = ops_notifications.list_pending_notifications(project_id)
    play_note = next(item for item in payload["notifications"] if item["kind"] == "play")
    assert play_note["playStatus"] == "failed"
    assert play_note["playLocked"] is False
    assert "Build timeout after 1s" in play_note["playFallbackError"]


def test_phase7_ops_notifications_include_play_ready_state(monkeypatch, tmp_path, git_available):
    _repo, project_id = setup_project(monkeypatch, tmp_path, valid_proxy_config())

    from api import ops_notifications, play_pipeline

    with play_pipeline._LOCK:
        state = play_pipeline.PlayPipelineState(project_id=project_id)
        state.project_id = project_id
        state.status = "ready"
        state.running = True
        state.ready = True
        state.inspect_url = f"/play-project/{project_id}/app"
        state.ready_at = "2026-05-06T06:00:00Z"
        state.updated_at = "2026-05-06T06:00:00Z"
        play_pipeline._PIPELINES[project_id] = state

    payload = ops_notifications.list_pending_notifications(project_id)
    play_note = next(item for item in payload["notifications"] if item["kind"] == "play")

    assert play_note["project"]["id"] == project_id
    assert play_note["inspectUrl"] == f"/play-project/{project_id}/app"
    assert play_note["playStatus"] == "ready"
    assert play_note["playNeedsRepair"] is False


def test_phase7_ops_notifications_include_manual_play_build_state(monkeypatch, tmp_path, git_available):
    _repo, project_id = setup_project(monkeypatch, tmp_path, valid_proxy_config())

    from api import ops_notifications, play_pipeline

    with play_pipeline._LOCK:
        state = play_pipeline.PlayPipelineState(project_id=project_id)
        state.status = "building"
        state.running = True
        state.ready = False
        state.started_at = "2026-05-06T06:01:00Z"
        play_pipeline._PIPELINES[project_id] = state

    payload = ops_notifications.list_pending_notifications(project_id)
    play_note = next(item for item in payload["notifications"] if item["kind"] == "play")

    assert play_note["project"]["id"] == project_id
    assert play_note["playStatus"] == "building"
    assert play_note["playLocked"] is True
    assert play_note["inspectUrl"] == ""
    assert play_note["task"] == {"id": "", "text": "", "grade": "green", "done": False}
    assert play_note["terminalTarget"] == {
        "projectId": project_id,
        "taskId": "",
        "sessionId": "",
        "runId": "",
    }


def test_phase7_play_proxy_dispatch_rewrites_html_and_locations(monkeypatch, tmp_path, git_available):
    setup_project(monkeypatch, tmp_path, valid_proxy_config())

    from api import play_pipeline
    from api.routes import handle_get, handle_post

    with play_pipeline._LOCK:
        state = play_pipeline.PlayPipelineState(project_id="75e3")
        state.project_id = "75e3"
    # Replace with the actual project id from setup through the stored pipeline state.
    project_id = next(iter(play_pipeline.ops_projects.list_ops_projects()["projects"]))["id"]
    with play_pipeline._LOCK:
        state.project_id = project_id
        state.status = "ready"
        state.running = True
        state.ready = True
        state.allocated_port = 5123
        state.allocated_port_host = "127.0.0.1"
        state.run_id = "run-1"
        state.task_id = "task-1"
        state.session_id = "session-1"
        play_pipeline._PIPELINES[project_id] = state

    class FakeResponse:
        def __init__(self, *, status=200, headers=None, body=b""):
            self.status = status
            self.headers = _Headers(headers or {})
            self._body = body

        def read(self):
            return self._body

    html_response = FakeResponse(
        status=200,
        headers={"Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": "default-src 'self'; frame-src 'none'"},
        body=b"<html><head></head><body><img src=\"/assets/logo.png\"></body></html>",
    )
    redirect_response = FakeResponse(
        status=302,
        headers={"Location": "/login", "Content-Type": "text/plain; charset=utf-8"},
        body=b"redirect",
    )

    calls = []

    def fake_urlopen(request, timeout=30):
        calls.append((request.full_url, request.get_method(), request.data))
        if request.full_url.endswith("/api/run"):
            return redirect_response
        return html_response

    monkeypatch.setattr(play_pipeline.urlrequest, "urlopen", fake_urlopen)

    html_handler = _FakeHandler(command="GET")
    assert handle_get(html_handler, urlparse(f"http://example.com/play-project/{project_id}/app")) is True
    html = bytes(html_handler.body).decode("utf-8")
    assert html_handler.status == 200
    assert 'src=".hermes-webui/static/play-proxy-compat.js"' in html
    assert f'data-hermes-play-proxy-prefix="/play-project/{project_id}"' in html
    assert 'src=".hermes-webui/static/play-session-overlay.js"' in html
    assert f'data-hermes-play-project-id="{project_id}"' in html
    assert 'data-hermes-play-run-id="run-1"' in html
    assert 'data-hermes-play-task-id="task-1"' in html
    assert 'data-hermes-play-session-id="session-1"' in html
    assert 'data-hermes-play-session-url="/session/session-1"' in html
    assert f'src="/play-project/{project_id}/assets/logo.png"' in html
    csp = dict(html_handler.sent_headers)["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp

    post_handler = _FakeHandler({"ok": True}, command="POST")
    assert handle_post(post_handler, urlparse(f"http://example.com/play-project/{project_id}/api/run")) is True
    assert post_handler.status == 302
    assert dict(post_handler.sent_headers)["Location"] == f"/play-project/{project_id}/login"
    assert calls[-1][1] == "POST"


def test_phase7_play_session_overlay_embeds_simplified_session_view():
    overlay = (Path(__file__).resolve().parents[1] / "static" / "play-session-overlay.js").read_text(encoding="utf-8")
    sessions = (Path(__file__).resolve().parents[1] / "static" / "sessions.js").read_text(encoding="utf-8")
    routes = (Path(__file__).resolve().parents[1] / "api" / "routes.py").read_text(encoding="utf-8")
    helpers = (Path(__file__).resolve().parents[1] / "api" / "helpers.py").read_text(encoding="utf-8")

    assert "opsSessionInspect" in overlay
    assert "opsSessionInspectSource" in overlay
    assert 'data-hermes-play-full-session href="${escapeHtml(fullSessionUrl)}"' in overlay
    assert 'src="${escapeHtml(sessionUrl)}"' in overlay
    assert "querySelectorAll('script[data-hermes-play-overlay]')" in overlay
    assert "root.dataset.hermesPlayOverlayKey=overlayKey" in overlay
    assert "existing.classList.remove('is-collapsed')" in overlay
    assert "Session preview did not finish loading here." in overlay
    assert "sessionStorage.setItem(storageKey" not in overlay
    assert "requestedByUrl=qs.get('opsSessionInspect')==='1'||qs.get('opsSessionInspect')==='true'" in sessions
    assert "allow_same_origin_frame=parsed.path.startswith(\"/session/\")" in routes
    assert "'X-Frame-Options', 'SAMEORIGIN' if allow_same_origin_frame else 'DENY'" in helpers


def test_phase7_play_feedback_overlay_saves_user_feedback_tasks():
    overlay = (Path(__file__).resolve().parents[1] / "static" / "play-session-overlay.js").read_text(encoding="utf-8")

    assert "data-hermes-play-feedback" in overlay
    assert "hermesPlayFeedbackCapture" in overlay
    assert "includeContent:true" in overlay
    assert "return appUrl('/api/core/projects/'+encodeURIComponent(projectId)+suffix);" in overlay
    assert "feedbackApiFrame=document.createElement('iframe')" in overlay
    assert "body:{title:'User Feedback'}" in overlay
    assert "const savedText=\"We recieved this feedback from a user '\"+textValue+\"' analyze it in depth and fix it\";" in overlay
    assert "body:{epicId,text:savedText,grade:'green',markers:['User Feedback']}" in overlay
    assert "projectApiPath('/tasks/'+encodeURIComponent(createdTaskId)+'/images')" in overlay
    assert "Note the red marker." in overlay
    assert "Feedback sent. You can close this popup and keep playing." in overlay
    assert "if(!projectId&&!sessionId)return;" in overlay
    assert "if(!sessionId)return;" not in overlay


def test_phase7_play_feedback_overlay_injected_without_linked_session():
    from api import play_pipeline

    attrs = play_pipeline._play_proxy_overlay_attributes("feedback-only-project")
    assert 'data-hermes-play-overlay="enabled"' in attrs
    assert 'data-hermes-play-project-id="feedback-only-project"' in attrs
    assert 'data-hermes-play-session-id=""' in attrs

    html = play_pipeline._inject_play_proxy_scripts("<html><head></head><body>ready</body></html>", "feedback-only-project")
    assert 'src=".hermes-webui/static/play-session-overlay.js"' in html
    assert 'data-hermes-play-project-id="feedback-only-project"' in html


def test_phase7_play_proxy_injected_webui_scripts_are_relative_to_proxy_page(monkeypatch):
    from api import play_pipeline

    state = play_pipeline.PlayPipelineState(project_id="project-1")
    state.session_id = "session-1"
    monkeypatch.setitem(play_pipeline._PIPELINES, "project-1", state)

    html = play_pipeline._inject_play_proxy_scripts(
        "<html><head></head><body>ready</body></html>",
        "project-1",
        "/nested/app/",
    )

    assert 'src="../../.hermes-webui/static/play-proxy-compat.js"' in html
    assert 'src="../../.hermes-webui/static/play-session-overlay.js"' in html
    assert 'src="/static/play-proxy-compat.js"' not in html
    assert 'src="/static/play-session-overlay.js"' not in html


def test_phase7_play_proxy_compat_rewrites_app_calls_under_subpath_mount():
    script = textwrap.dedent(
        """
        (() => {
        const fs = require('fs');
        const vm = require('vm');
        const source = fs.readFileSync('static/play-proxy-compat.js', 'utf8');
        let fetchUrl = '';
        let socketUrl = '';
        function NativeWebSocket(url){ socketUrl = url; }
        NativeWebSocket.CONNECTING = 0;
        NativeWebSocket.OPEN = 1;
        NativeWebSocket.CLOSING = 2;
        NativeWebSocket.CLOSED = 3;
        const scriptTag = { dataset: { hermesPlayProxyPrefix: '/play-project/project-1' } };
        const context = {
          window: {
            location: {
              href: 'https://example.test/hermes/play-project/project-1/game',
              origin: 'https://example.test',
              pathname: '/hermes/play-project/project-1/game',
              protocol: 'https:',
            },
            fetch(url){ fetchUrl = url; return Promise.resolve({ ok: true }); },
            WebSocket: NativeWebSocket,
          },
          document: {
            querySelectorAll(){ return [scriptTag]; },
            currentScript: scriptTag,
          },
          URL,
          console,
        };
        vm.createContext(context);
        vm.runInContext(source, context);
        context.window.fetch('/api/trpc/query?batch=1');
        new context.window.WebSocket('/nakama/ws?token=1');
        if (fetchUrl !== '/hermes/play-project/project-1/api/trpc/query?batch=1') {
          throw new Error(`unexpected fetch URL: ${fetchUrl}`);
        }
        const expectedSocket = 'wss://example.test/hermes/play-project/project-1/nakama/ws?token=1';
        if (socketUrl !== expectedSocket) throw new Error(`unexpected socket URL: ${socketUrl}`);
        console.log('ok');
        })();
        """
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "ok"



def test_phase7_play_proxy_serves_injected_webui_static_without_upstream(monkeypatch):
    from api import play_pipeline

    project_id = "project-1"
    state = play_pipeline.PlayPipelineState(project_id=project_id)
    state.running = True
    state.ready = True
    state.allocated_port = 4321
    state.allocated_port_host = "127.0.0.1"
    monkeypatch.setitem(play_pipeline._PIPELINES, project_id, state)

    def fail_urlopen(*_args, **_kwargs):
        raise AssertionError("injected WebUI static route should not call Play upstream")

    monkeypatch.setattr(play_pipeline.urlrequest, "urlopen", fail_urlopen)
    handler = _FakeHandler(command="GET")
    play_pipeline.handle_play_proxy_request(
        handler,
        project_id,
        "/.hermes-webui/static/play-session-overlay.js",
        urlparse(f"http://example.com/play-project/{project_id}/.hermes-webui/static/play-session-overlay.js"),
        method="GET",
    )

    assert handler.status == 200
    assert handler.header("Content-Type") == "application/javascript; charset=utf-8"
    body = bytes(handler.body).decode("utf-8")
    assert "function appUrl(path)" in body


def test_phase7_play_proxy_csp_allows_injected_session_overlay():
    from api import play_pipeline

    rewritten = play_pipeline._rewrite_proxy_csp(
        "default-src 'none'; script-src 'none'; script-src-elem 'none'; "
        "style-src 'self'; frame-src 'none'; child-src 'none'"
    )

    assert "frame-src 'self'" in rewritten
    assert "child-src 'self'" in rewritten
    assert "script-src 'self'" in rewritten
    assert "script-src-elem 'self'" in rewritten
    assert "style-src 'self' 'unsafe-inline'" in rewritten
    assert "style-src-elem 'self' 'unsafe-inline'" in rewritten
    assert "script-src 'none'" not in rewritten
    assert "frame-src 'none'" not in rewritten


def test_phase7_text_helper_can_allow_same_origin_session_iframe():
    from api.helpers import t

    denied = _FakeHandler()
    t(denied, "<html></html>", content_type="text/html; charset=utf-8")
    assert denied.header("X-Frame-Options") == "DENY"

    allowed = _FakeHandler()
    t(allowed, "<html></html>", content_type="text/html; charset=utf-8", allow_same_origin_frame=True)
    assert allowed.header("X-Frame-Options") == "SAMEORIGIN"


def test_phase7_play_proxy_forwards_body_already_consumed_by_main_post_route(monkeypatch):
    from api import play_pipeline
    from api.routes_ops_play import handle_post

    project_id = "project-1"
    state = play_pipeline.PlayPipelineState(project_id=project_id)
    state.running = True
    state.ready = True
    state.allocated_port = 4321
    state.allocated_port_host = "127.0.0.1"
    monkeypatch.setitem(play_pipeline._PIPELINES, project_id, state)

    raw_body = b'{"0":{"json":{"username":"","password":""}}}'
    calls = []

    class FakeResponse:
        status = 200
        headers = _Headers({"Content-Type": "application/json"})

        def read(self):
            return b'{"ok":true}'

    def fake_urlopen(request, timeout=30):
        calls.append((request.full_url, request.get_method(), request.data))
        return FakeResponse()

    monkeypatch.setattr(play_pipeline.urlrequest, "urlopen", fake_urlopen)

    handler = _FakeHandler(command="POST")
    handler._raw_body = raw_body
    handler.rfile = io.BytesIO(b"")
    handler.headers["Content-Length"] = str(len(raw_body))

    assert handle_post(
        handler,
        urlparse(f"http://example.com/play-project/{project_id}/api/trpc/auth.login?batch=1"),
        {},
    ) is True

    assert handler.status == 200
    assert calls == [
        (
            "http://127.0.0.1:4321/api/trpc/auth.login?batch=1",
            "POST",
            raw_body,
        )
    ]


def test_phase7_ops_ui_renders_play_panel_and_actions():
    script = textwrap.dedent(
        """
        (async () => {
        const fs = require('fs');
        const vm = require('vm');

        class Root {
          constructor(){
            this.innerHTML = '';
            this.listeners = {};
          }
          addEventListener(name, handler){
            this.listeners[name] = handler;
          }
          querySelector(){
            return null;
          }
        }

        const fetchCalls = [];
        const projectsSource = fs.readFileSync('static/ops-projects.js', 'utf8');
        const notificationsSource = fs.readFileSync('static/ops-notifications.js', 'utf8');
        const runtimeSource = fs.readFileSync('static/ops-runtime.js', 'utf8');
        const fetch = async (path, options) => {
          fetchCalls.push({ path, options: options || null });
          if (path === '/api/ops/notifications/pending'){
            return { ok: true, json: async () => ({ count: 0, notifications: [] }) };
          }
          if (path === '/api/ops/projects'){
            return {
              ok: true,
              json: async () => ({
                projects: [
                  {
                    id: 'project-1',
                    name: 'Play Project',
                    path: '/tmp/play-project',
                    tasksBranch: 'feature/play-slice',
                    coreBranch: 'main',
                    taskCount: 0,
                    tasksFilePath: '/tmp/play-project/project_tasks/feature%2Fplay-slice.json'
                  }
                ]
              })
            };
          }
          if (path === '/api/ops/projects/project-1/tasks'){
            return {
              ok: true,
              json: async () => ({
                project: { id: 'project-1', name: 'Play Project' },
                epics: []
              })
            };
          }
          if (path === '/api/ops/projects/project-1/runtime/summary'){
            return {
              ok: true,
              json: async () => ({
                projectId: 'project-1',
                capabilities: {
                  gatherReports: { available: true, label: 'Gather reports' },
                  reviewRequests: { available: true, label: 'Review requests' },
                  play: { available: true, label: 'Play workflow', reason: 'Play endpoints are available.' }
                },
                gather: { count: 0, reports: [] },
                reviews: { count: 0, reviews: [] },
                play: {
                  status: 'idle',
                  statusSummary: 'Auto-detected package-script build workflow from package.json. Build the project to verify it.',
                  configExists: false,
                  configAvailable: true,
                  configAutoDetected: true,
                  buildAvailable: true,
                  canBuild: true,
                  valid: true,
                  inspectUrl: '',
                  ready: false,
                  running: false,
                  configPath: '/tmp/play-project/project_play.json'
                }
              })
            };
          }
          if (path === '/api/ops/projects/project-1/play/logs?limit=200'){
            return { ok: true, json: async () => ({ text: 'play log line' }) };
          }
          if (path === '/api/ops/projects/project-1/play/start'){
            return { ok: true, json: async () => ({ ok: true, started: true, status: { status: 'building' } }) };
          }
          throw new Error('Unexpected fetch path: ' + path);
        };

        const context = {
          console,
          window: { location: { assign: () => {} } },
          fetch,
          HTMLFormElement: function HTMLFormElement(){},
          HTMLElement: function HTMLElement(){},
          HTMLInputElement: function HTMLInputElement(){},
          FormData: function FormData(){
            return { get: (name) => name === 'content' ? '{\\n  "version": 2\\n}' : '' };
          },
          setTimeout,
          clearTimeout,
        };
        vm.createContext(context);
        vm.runInContext(notificationsSource, context);
        vm.runInContext(runtimeSource, context);
        vm.runInContext(projectsSource, context);

        const root = new Root();
        context.window.HermesOpsProjects.mount(root, {
          phase: 'phase-7',
          route: '/ops',
          apiBase: '/api/ops',
          version: 'test-version',
        });

        const click = root.listeners.click;
        click({
          target: {
            closest: (selector) => {
              if (selector !== '[data-ops-action]') return null;
              return { getAttribute: (name) => name === 'data-ops-action' ? 'toggle-projects' : '' };
            }
          }
        });

        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));

        if (!root.innerHTML.includes('Play workflow')){
          throw new Error('Play section did not render');
        }
        if (root.innerHTML.includes('Configure')){
          throw new Error('Legacy Play configure control rendered');
        }
        if (root.innerHTML.includes('Save Play config')){
          throw new Error('Legacy Play config editor rendered');
        }
        if (!root.innerHTML.includes('Build')){
          throw new Error('Play build control did not render');
        }

        click({
          target: {
            closest: (selector) => {
              if (selector !== '[data-ops-action]') return null;
              return { getAttribute: (name) => name === 'data-ops-action' ? 'show-play-logs' : '' };
            }
          }
        });
        await new Promise((resolve) => setTimeout(resolve, 0));
        if (!root.innerHTML.includes('play log line')){
          throw new Error('Play logs did not render');
        }

        click({
          target: {
            closest: (selector) => {
              if (selector !== '[data-ops-action]') return null;
              return { getAttribute: (name) => name === 'data-ops-action' ? 'start-play' : '' };
            }
          }
        });
        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));

        if (!fetchCalls.some((call) => call.path === '/api/ops/projects/project-1/play/start')){
          throw new Error('Play start endpoint was not requested');
        }
        if (fetchCalls.filter((call) => call.path === '/api/ops/notifications/pending').length < 2){
          throw new Error('Workflow notifications were not refreshed after manual Play start');
        }
        if (fetchCalls.some((call) => call.path === '/api/ops/projects/project-1/play/config')){
          throw new Error('Legacy Play config endpoint was requested');
        }
        if (!fetchCalls.some((call) => call.path === '/api/ops/projects/project-1/play/logs?limit=200')){
          throw new Error('Play logs endpoint was not requested');
        }
        console.log('ok');
        })().catch((error) => {
          console.error(error);
          process.exit(1);
        });
        """
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "ok"


def test_phase7_play_logs_include_status_snapshot(monkeypatch, tmp_path, git_available):
    _, project_id = setup_project(monkeypatch, tmp_path, valid_direct_config())

    from api import play_pipeline

    with play_pipeline._LOCK:
        state = play_pipeline.PlayPipelineState(project_id=project_id)
        state.status = "building"
        state.running = True
        state.logs.append({"message": "building app"})
        play_pipeline._PIPELINES[project_id] = state

    payload = play_pipeline.build_project_play_logs(project_id, limit=50)

    assert "building app" in payload["text"]
    assert payload["status"]["status"] == "building"
    assert payload["status"]["running"] is True


def test_phase7_play_injects_hermes_managed_postgres_env(monkeypatch, tmp_path):
    from api import play_pipeline

    monkeypatch.setattr(play_pipeline, "_allocate_port", lambda _host, _range: 25001)
    monkeypatch.setattr(
        play_pipeline.managed_postgres,
        "ensure_project_database_env",
        lambda project_id: {
            "DATASTORE_ADAPTER": "postgres",
            "DATABASE_URL": "postgresql://hermes:test@127.0.0.1:5433/hermes_project_1",
            "DATASTORE_POSTGRES_URL": "postgresql://hermes:test@127.0.0.1:5433/hermes_project_1",
            "NAKAMA_DATABASE_URL": "postgresql://hermes:test@127.0.0.1:5433/hermes_project_1",
            "PGHOST": "127.0.0.1",
            "PGPORT": "5433",
            "PGUSER": "hermes",
            "PGPASSWORD": "test",
            "PGDATABASE": "hermes_project_1",
        },
    )
    config = play_pipeline.normalize_play_config(
        {
            "version": 2,
            "build": {"command": "echo build"},
            "start": {
                "command": "echo start",
                "port": {"mode": "auto", "host": "127.0.0.1", "envVar": "PORT"},
            },
            "inspect": {"mode": "proxy", "url": "/app"},
        },
        tmp_path,
    )
    state = play_pipeline.PlayPipelineState(project_id="project-1")

    runtime = play_pipeline._prepare_start_runtime("project-1", config["config"], state)
    env = runtime["config"]["start"]["env"]

    assert env["PORT"] == "25001"
    assert env["DATASTORE_ADAPTER"] == "postgres"
    assert env["DATABASE_URL"] == "postgresql://hermes:test@127.0.0.1:5433/hermes_project_1"
    assert env["DATASTORE_POSTGRES_URL"] == env["DATABASE_URL"]
    assert env["NAKAMA_DATABASE_URL"] == env["DATABASE_URL"]
    assert env["PGDATABASE"] == "hermes_project_1"
    assert any("Hermes managed Postgres ready" in item["message"] for item in state.logs)


def test_phase7_play_explicit_database_url_skips_managed_postgres_and_aligns_aliases(monkeypatch, tmp_path):
    from api import play_pipeline

    called = []
    monkeypatch.setattr(play_pipeline, "_allocate_port", lambda _host, _range: 25001)
    monkeypatch.setattr(
        play_pipeline.managed_postgres,
        "ensure_project_database_env",
        lambda project_id: called.append(project_id) or {},
    )
    config = play_pipeline.normalize_play_config(
        {
            "version": 2,
            "build": {"command": "echo build"},
            "start": {
                "command": "echo start",
                "env": {"DATABASE_URL": "postgresql://explicit:test@db.example/app"},
                "port": {"mode": "auto", "host": "127.0.0.1", "envVar": "PORT"},
            },
            "inspect": {"mode": "proxy", "url": "/app"},
        },
        tmp_path,
    )
    state = play_pipeline.PlayPipelineState(project_id="project-1")

    runtime = play_pipeline._prepare_start_runtime("project-1", config["config"], state)
    env = runtime["config"]["start"]["env"]

    assert called == []
    assert env["DATABASE_URL"] == "postgresql://explicit:test@db.example/app"
    assert env["DATASTORE_POSTGRES_URL"] == env["DATABASE_URL"]
    assert env["NAKAMA_DATABASE_URL"] == env["DATABASE_URL"]
    assert "PGDATABASE" not in env
    assert any("Using Play-provided database connection env" in item["message"] for item in state.logs)

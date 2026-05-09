import io
import json
import shutil
import subprocess
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


def test_phase7_play_config_preference_and_document_save(monkeypatch, tmp_path, git_available):
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
    config_save = _FakeHandler({"content": json.dumps(saved_config, ensure_ascii=False, indent=2)})
    assert handle_post(config_save, urlparse(f"http://example.com/api/ops/projects/{project_id}/play/config")) is True
    save_payload = _response_json(config_save)
    assert save_payload["saved"] is True
    assert save_payload["path"] == str(repo / ".hermes" / "play.json")

    config_doc = _FakeHandler()
    assert handle_get(config_doc, urlparse(f"http://example.com/api/ops/projects/{project_id}/play/config")) is True
    doc_payload = _response_json(config_doc)
    assert doc_payload["targetPath"] == str(repo / ".hermes" / "play.json")
    assert '"mode": "proxy"' in doc_payload["content"]


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
    assert "/static/play-proxy-compat.js" in html
    assert f'data-hermes-play-proxy-prefix="/play-project/{project_id}"' in html
    assert f'src="/play-project/{project_id}/assets/logo.png"' in html
    assert dict(html_handler.sent_headers)["Content-Security-Policy"] == "default-src 'self'; frame-src 'self'"

    post_handler = _FakeHandler({"ok": True}, command="POST")
    assert handle_post(post_handler, urlparse(f"http://example.com/play-project/{project_id}/api/run")) is True
    assert post_handler.status == 302
    assert dict(post_handler.sent_headers)["Location"] == f"/play-project/{project_id}/login"
    assert calls[-1][1] == "POST"


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
                  statusSummary: 'Play config is ready. Start the pipeline to inspect the app.',
                  configExists: true,
                  valid: true,
                  inspectUrl: '',
                  ready: false,
                  running: false,
                  configPath: '/tmp/play-project/project_play.json'
                }
              })
            };
          }
          if (path === '/api/ops/projects/project-1/play/config'){
            if (options && options.method === 'POST'){
              return { ok: true, json: async () => ({ saved: true, path: '/tmp/play-project/.hermes/play.json' }) };
            }
            return {
              ok: true,
              json: async () => ({
                targetPath: '/tmp/play-project/.hermes/play.json',
                content: '{\\n  "version": 2\\n}'
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
        if (!root.innerHTML.includes('Configure')){
          throw new Error('Play configure control did not render');
        }
        if (!root.innerHTML.includes('Start')){
          throw new Error('Play start control did not render');
        }

        click({
          target: {
            closest: (selector) => {
              if (selector !== '[data-ops-action]') return null;
              return { getAttribute: (name) => name === 'data-ops-action' ? 'show-play-config' : '' };
            }
          }
        });
        await new Promise((resolve) => setTimeout(resolve, 0));
        if (!root.innerHTML.includes('Save Play config')){
          throw new Error('Play config editor did not render');
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

        if (!fetchCalls.some((call) => call.path === '/api/ops/projects/project-1/play/start')){
          throw new Error('Play start endpoint was not requested');
        }
        if (!fetchCalls.some((call) => call.path === '/api/ops/projects/project-1/play/config')){
          throw new Error('Play config endpoint was not requested');
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

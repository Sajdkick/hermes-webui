import io
import json
import shutil
import subprocess
import textwrap
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


def init_project_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "phase9-project"
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    run_git(repo, "checkout", "-b", "feature/phase9")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "initial")
    return repo


def test_phase9_task_launch_creates_run_activity_and_readable_output_route(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)

    from api.routes import handle_get, handle_post

    create = _FakeHandler({"name": "Phase 9 Project", "path": str(repo), "coreBranch": "main"})
    assert handle_post(create, urlparse("http://example.com/api/ops/projects")) is True
    project = _response_json(create)["project"]

    epic_create = _FakeHandler({"title": "Phase 9"})
    assert handle_post(epic_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/epics")) is True
    epic_id = _response_json(epic_create)["epic"]["id"]

    task_create = _FakeHandler({"epicId": epic_id, "text": "Create a run record"})
    assert handle_post(task_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    task = _response_json(task_create)["task"]

    launch = _FakeHandler()
    assert handle_post(
        launch,
        urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks/{task['id']}/sessions/launch"),
    ) is True
    launch_payload = _response_json(launch)
    run = launch_payload["run"]
    session = launch_payload["session"]

    assert run["projectId"] == project["id"]
    assert run["taskId"] == task["id"]
    assert run["sessionId"] == session["session_id"]
    assert launch_payload["linkage"]["runId"] == run["id"]

    listing = _FakeHandler()
    assert handle_get(listing, urlparse(f"http://example.com/api/ops/runs?projectId={project['id']}")) is True
    listing_payload = _response_json(listing)
    assert listing_payload["count"] == 1
    assert listing_payload["runs"][0]["id"] == run["id"]
    assert listing_payload["runs"][0]["status"] == "running"

    compat_create = _FakeHandler(
        {
            "projectId": project["id"],
            "taskId": task["id"],
            "sessionId": session["session_id"],
            "status": "waiting-approval",
            "summary": "Awaiting approval from the ops dashboard.",
            "metadata": {"source": "ops-dashboard", "engine": "hermes-session"},
        }
    )
    assert handle_post(compat_create, urlparse("http://example.com/api/ops/runs")) is True
    compat_run = _response_json(compat_create)["run"]
    assert compat_run["id"] == run["id"]
    assert compat_run["status"] == "waiting-approval"
    assert compat_run["summary"] == "Awaiting approval from the ops dashboard."
    assert compat_run["metadata"]["source"] == "ops-dashboard"
    assert compat_run["metadata"]["engine"] == "hermes-session"

    compat_update = _FakeHandler({"status": "running", "summary": "Task execution was started from the ops dashboard."})
    assert handle_post(compat_update, urlparse(f"http://example.com/api/ops/runs/{run['id']}")) is True
    updated_run = _response_json(compat_update)["run"]
    assert updated_run["id"] == run["id"]
    assert updated_run["status"] == "running"
    assert updated_run["summary"] == "Task execution was started from the ops dashboard."

    requests = _FakeHandler()
    assert handle_get(requests, urlparse(f"http://example.com/api/ops/runs/{run['id']}/requests")) is True
    assert _response_json(requests)["count"] == 0

    readable_dir = repo / ".cloud-terminal" / "readable-output" / session["session_id"]
    readable_dir.mkdir(parents=True, exist_ok=True)
    (readable_dir / "message.md").write_text("# Finished\n\nDone.\n", encoding="utf-8")

    readable = _FakeHandler()
    assert handle_get(readable, urlparse(f"http://example.com/api/ops/runs/{run['id']}/readable-output")) is True
    readable_payload = _response_json(readable)
    assert readable_payload["readableOutput"]["exists"] is True
    assert readable_payload["readableOutput"]["title"] == "Finished"

    complete = _FakeHandler({"status": "succeeded", "summary": "Done"})
    assert handle_post(complete, urlparse(f"http://example.com/api/ops/runs/{run['id']}/complete")) is True
    assert _response_json(complete)["run"]["status"] == "succeeded"

    detail = _FakeHandler()
    assert handle_get(detail, urlparse(f"http://example.com/api/ops/runs/{run['id']}")) is True
    detail_payload = _response_json(detail)["run"]
    assert detail_payload["status"] == "succeeded"
    assert detail_payload["readableOutput"]["available"] is True


def test_phase9_run_follows_lineage_tip_and_marks_completed_without_readable_output(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)

    from api.routes import handle_get, handle_post
    from api import session_sidecars

    create = _FakeHandler({"name": "Phase 9 Lineage Project", "path": str(repo), "coreBranch": "main"})
    assert handle_post(create, urlparse("http://example.com/api/ops/projects")) is True
    project = _response_json(create)["project"]

    epic_create = _FakeHandler({"title": "Phase 9"})
    assert handle_post(epic_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/epics")) is True
    epic_id = _response_json(epic_create)["epic"]["id"]

    task_create = _FakeHandler({"epicId": epic_id, "text": "Follow the latest run session tip"})
    assert handle_post(task_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    task = _response_json(task_create)["task"]

    launch = _FakeHandler()
    assert handle_post(
        launch,
        urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks/{task['id']}/sessions/launch"),
    ) is True
    launch_payload = _response_json(launch)
    run = launch_payload["run"]
    root_session_id = launch_payload["session"]["session_id"]

    tip_summary = {
        "session_id": "tiprun12345",
        "title": "Tip run session",
        "workspace": str(repo.resolve()),
        "model": "gpt-5.5",
        "model_provider": "openai-codex",
        "message_count": 3,
        "created_at": launch_payload["session"]["created_at"],
        "updated_at": launch_payload["session"]["updated_at"] + 15,
        "last_message_at": launch_payload["session"]["updated_at"] + 15,
        "pinned": False,
        "archived": False,
        "project_id": project["id"],
        "profile": "default",
        "active_stream_id": None,
        "pending_user_message": None,
        "has_pending_user_message": False,
        "is_cli_session": False,
        "source_tag": "ops_task",
        "raw_source": None,
        "session_source": None,
        "source_label": "Ops task",
        "enabled_toolsets": None,
        "is_streaming": False,
        "_lineage_root_id": root_session_id,
        "_lineage_tip_id": "tiprun12345",
    }
    monkeypatch.setattr(session_sidecars, "resolve_session_summary", lambda _sid: dict(tip_summary))
    monkeypatch.setattr(session_sidecars, "resolve_session_id", lambda _sid: "tiprun12345")

    detail = _FakeHandler()
    assert handle_get(detail, urlparse(f"http://example.com/api/ops/runs/{run['id']}")) is True
    detail_payload = _response_json(detail)["run"]
    assert detail_payload["sessionId"] == "tiprun12345"
    assert detail_payload["linkedSessionId"] == root_session_id
    assert detail_payload["status"] == "succeeded"


def test_phase9_ops_ui_renders_run_activity_panel():
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

        function HTMLFormElement(){}
        function HTMLElement(){}
        function HTMLInputElement(){}

        const fetchCalls = [];
        const runsSource = fs.readFileSync('static/ops-runs.js', 'utf8');
        const projectsSource = fs.readFileSync('static/ops-projects.js', 'utf8');
        const fetch = async (path) => {
          fetchCalls.push(path);
          if (path === '/api/ops/notifications/pending'){
            return { ok: true, json: async () => ({ count: 0, notifications: [] }) };
          }
          if (path === '/api/ops/runs'){
            return {
              ok: true,
              json: async () => ({
                count: 1,
                runs: [{
                  id: 'run-1',
                  projectId: 'project-1',
                  taskId: 'task-1',
                  title: 'Phase 9 Run',
                  status: 'waiting-approval',
                  updatedAt: '2026-05-03T10:00:00Z',
                  sessionUrl: '/session/session_1',
                  pendingRequestCount: 1,
                  project: { id: 'project-1', name: 'Phase 9 Project' },
                  task: { id: 'task-1', text: 'Inspect run activity' },
                  readableOutput: { available: true, url: '/api/ops/runs/run-1/readable-output' }
                }]
              })
            };
          }
          throw new Error('Unexpected fetch path: ' + path);
        };

        const context = {
          console,
          window: {},
          fetch,
          HTMLFormElement,
          HTMLElement,
          HTMLInputElement,
          FormData: function FormData(){ return { get: () => '' }; },
          setTimeout,
          clearTimeout,
        };
        vm.createContext(context);
        vm.runInContext(runsSource, context);
        vm.runInContext(projectsSource, context);

        const root = new Root();
        context.window.HermesOpsProjects.mount(root, {
          phase: 'phase-9',
          route: '/ops',
          apiBase: '/api/ops',
          version: 'test-version',
        });

        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));

        if (!root.innerHTML.includes('Run activity')){
          throw new Error('Run activity panel did not render');
        }
        if (!root.innerHTML.includes('Phase 9 Run')){
          throw new Error('Run title did not render');
        }
        if (!root.innerHTML.includes('Waiting approval')){
          throw new Error('Run status badge did not render');
        }
        if (!root.innerHTML.includes('Readable output')){
          throw new Error('Readable output link did not render');
        }
        if (!fetchCalls.includes('/api/ops/runs')){
          throw new Error('Run activity endpoint was not requested');
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

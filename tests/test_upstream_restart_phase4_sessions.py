import io
import json
import shutil
import subprocess
from pathlib import Path
import textwrap
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
    repo = tmp_path / "session-launch-project"
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    run_git(repo, "checkout", "-b", "feature/phase4")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "initial")
    return repo


def test_phase4_launch_task_session_creates_persisted_linked_session(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)

    from api.routes import handle_post, handle_get
    from tests.test_upstream_restart_phase2_projects import _FakeHandler as _RouteHandler, _response_json as _route_response_json

    create = _FakeHandler({"name": "Session Launch Project", "path": str(repo), "coreBranch": "main"})
    assert handle_post(create, urlparse("http://example.com/api/ops/projects")) is True
    project = _response_json(create)["project"]

    epic_create = _FakeHandler({"title": "Phase 4"})
    assert handle_post(epic_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/epics")) is True
    epic_id = _response_json(epic_create)["epic"]["id"]

    task_create = _FakeHandler({"epicId": epic_id, "text": "Launch a Hermes session from this task"})
    assert handle_post(task_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    task = _response_json(task_create)["task"]

    launch = _FakeHandler()
    assert handle_post(
        launch,
        urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks/{task['id']}/sessions/launch"),
    ) is True
    assert launch.status == 201
    payload = _response_json(launch)

    assert payload["session"]["workspace"] == str(repo.resolve())
    assert payload["session"]["source_tag"] == "ops_task"
    assert payload["session"]["source_label"] == "Ops task"
    assert payload["session"]["title"].startswith("Session Launch Project:")
    assert payload["sessionUrl"].endswith(payload["session"]["session_id"])
    assert payload["linkage"]["projectId"] == project["id"]
    assert payload["linkage"]["taskId"] == task["id"]
    assert payload["linkage"]["session"]["title"] == payload["session"]["title"]

    tasks = _RouteHandler()
    assert handle_get(tasks, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    task_payload = _route_response_json(tasks)
    linked_task = next(epic["tasks"][0] for epic in task_payload["epics"] if epic["id"] == epic_id)
    assert linked_task["linkedSessions"][0]["sessionId"] == payload["session"]["session_id"]
    assert linked_task["linkedSessions"][0]["sessionUrl"] == payload["sessionUrl"]
    assert linked_task["linkedSessions"][0]["available"] is True


def test_phase4_boot_keeps_ops_task_sessions_active():
    boot_js = Path("static/boot.js").read_text(encoding="utf-8")

    assert "function _keepEmptySessionActive(session)" in boot_js
    assert "return !!(session && session.source_tag === 'ops_task');" in boot_js
    assert "&& !_keepEmptySessionActive(S.session)" in boot_js


def test_phase4_ops_ui_renders_resume_link_and_launches_task_session():
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
        const fetch = async (path, options) => {
          fetchCalls.push({ path, options: options || null });
          if (path === '/api/ops/projects'){
            return {
              ok: true,
              json: async () => ({
                projects: [{
                  id: 'project-1',
                  name: 'Session UI Project',
                  path: '/tmp/session-ui-project',
                  tasksBranch: 'feature/phase4',
                  tasksFilePath: '/tmp/session-ui-project/project_tasks/feature%2Fphase4.json',
                  taskCount: 1
                }]
              })
            };
          }
          if (path === '/api/ops/projects/project-1/tasks'){
            return {
              ok: true,
              json: async () => ({
                project: { id: 'project-1', name: 'Session UI Project' },
                epics: [{
                  id: 'epic-1',
                  title: 'Phase 4',
                  tasks: [{
                    id: 'task-1',
                    text: 'Resume or launch from task',
                    grade: 'green',
                    done: false,
                    linkedSessions: [{
                      sessionId: 'sess123',
                      sessionUrl: '/session/sess123',
                      available: true,
                      session: { title: 'Task session', message_count: 2 }
                    }]
                  }]
                }]
              })
            };
          }
          if (path === '/api/ops/projects/project-1/tasks/task-1/sessions/launch'){
            return {
              ok: true,
              json: async () => ({ sessionUrl: '/session/sess999' })
            };
          }
          throw new Error('Unexpected fetch path: ' + path);
        };

        const source = fs.readFileSync('static/ops-projects.js', 'utf8');
        const assigned = [];
        const context = {
          console,
          fetch,
          window: {
            location: {
              assign: (value) => assigned.push(value)
            }
          },
          HTMLFormElement: function HTMLFormElement(){},
          HTMLElement: function HTMLElement(){},
          HTMLInputElement: function HTMLInputElement(){},
          setTimeout,
          clearTimeout,
        };
        vm.createContext(context);
        vm.runInContext(source, context);
        const root = new Root();
        context.window.HermesOpsProjects.mount(root, {
          phase: 'phase-4',
          route: '/ops',
          apiBase: '/api/ops',
          version: 'test-version',
        });

        root.listeners.click({
          target: {
            closest: () => ({
              getAttribute: (name) => name === 'data-ops-action' ? 'toggle-projects' : null
            })
          }
        });

        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));

        if (!root.innerHTML.includes('Resume latest')){
          throw new Error('Resume latest action was not rendered');
        }
        if (!root.innerHTML.includes('/session/sess123')){
          throw new Error('Linked session URL was not rendered');
        }
        if (!root.innerHTML.includes('New session')){
          throw new Error('New session action was not rendered');
        }

        root.listeners.click({
          target: {
            closest: () => ({
              getAttribute: (name) => {
                if (name === 'data-ops-action') return 'launch-task-session';
                if (name === 'data-task-id') return 'task-1';
                return null;
              }
            })
          }
        });

        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));

        if (!assigned.includes('/session/sess999')){
          throw new Error('Task launch did not redirect into the new Hermes session');
        }
        if (!fetchCalls.some((call) => call.path === '/api/ops/projects/project-1/tasks/task-1/sessions/launch')){
          throw new Error('Task launch endpoint was not called');
        }
        console.log('ok');
        })().catch((error) => {
          console.error(error && error.stack ? error.stack : error);
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

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

    legacy_launch = _FakeHandler()
    assert handle_post(
        legacy_launch,
        urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks/{task['id']}/session/ensure"),
    ) is True
    assert legacy_launch.status == 201
    legacy_payload = _response_json(legacy_launch)
    assert legacy_payload["session"]["source_tag"] == "ops_task"
    assert legacy_payload["sessionUrl"].endswith(legacy_payload["session"]["session_id"])


def test_phase4_ops_sessions_route_enriches_latest_task_session_tip(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)

    from api.routes import handle_get, handle_post
    from api import ops_sessions, session_sidecars

    create = _FakeHandler({"name": "Session Route Project", "path": str(repo), "coreBranch": "main"})
    assert handle_post(create, urlparse("http://example.com/api/ops/projects")) is True
    project = _response_json(create)["project"]

    epic_create = _FakeHandler({"title": "Phase 4"})
    assert handle_post(epic_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/epics")) is True
    epic_id = _response_json(epic_create)["epic"]["id"]

    task_create = _FakeHandler({"epicId": epic_id, "text": "Show the latest task session tip"})
    assert handle_post(task_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    task = _response_json(task_create)["task"]

    launch = _FakeHandler()
    assert handle_post(
        launch,
        urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks/{task['id']}/sessions/launch"),
    ) is True
    launch_payload = _response_json(launch)
    root_session_id = launch_payload["session"]["session_id"]

    tip_summary = {
        "session_id": "tiproute12345",
        "title": "Route tip session",
        "workspace": str(repo.resolve()),
        "model": "gpt-5.5",
        "model_provider": "openai-codex",
        "message_count": 4,
        "created_at": launch_payload["session"]["created_at"],
        "updated_at": launch_payload["session"]["updated_at"] + 30,
        "last_message_at": launch_payload["session"]["updated_at"] + 30,
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
        "_lineage_tip_id": "tiproute12345",
    }
    monkeypatch.setattr(session_sidecars, "all_sessions", lambda: [tip_summary])
    monkeypatch.setattr(ops_sessions, "all_sessions", lambda: [tip_summary])

    grouped = _FakeHandler()
    assert handle_get(grouped, urlparse(f"http://example.com/api/ops/sessions?projectId={project['id']}")) is True
    payload = _response_json(grouped)

    assert payload["groups"][0]["projectId"] == project["id"]
    assert payload["groups"][0]["sessions"][0]["session_id"] == "tiproute12345"
    assert payload["groups"][0]["sessions"][0]["ops_task_id"] == task["id"]
    assert payload["groups"][0]["sessions"][0]["ops_project_id"] == project["id"]


def test_phase4_ops_sessions_hides_orphaned_ops_task_sessions(monkeypatch, tmp_path):
    from api import ops_projects, ops_runs, ops_sessions

    project = {
        "id": "project-1",
        "name": "Hermes",
        "fullName": "Sajdkick/hermes-webui",
        "path": str(tmp_path / "repo"),
        "resolvedPath": str((tmp_path / "repo").resolve()),
        "coreBranch": "master",
    }
    monkeypatch.setattr(ops_projects, "get_ops_project", lambda project_id: project)
    monkeypatch.setattr(
        ops_projects,
        "read_ops_project_tasks",
        lambda project_id: {
            "epics": [
                {
                    "title": "Ops",
                    "tasks": [
                        {
                            "id": "task-1",
                            "text": "Investigate the real session",
                            "linkedSessions": [
                                {
                                    "sessionId": "linked-session",
                                    "updatedAt": "2026-05-05T12:00:00Z",
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    )
    monkeypatch.setattr(ops_runs, "list_ops_runs", lambda filters=None: {"runs": []})
    monkeypatch.setattr(
        ops_sessions,
        "all_sessions",
        lambda: [
            {
                "session_id": "linked-session",
                "_lineage_root_id": "linked-session",
                "workspace": str((tmp_path / "repo").resolve()),
                "title": "Hermes: Investigate the real session",
                "source_tag": "ops_task",
                "archived": False,
                "updated_at": "2026-05-05T12:00:00Z",
            },
            {
                "session_id": "manual-session",
                "_lineage_root_id": "manual-session",
                "workspace": str((tmp_path / "repo").resolve()),
                "title": "Manual investigation",
                "archived": False,
                "updated_at": "2026-05-05T12:05:00Z",
            },
            {
                "session_id": "orphan-session",
                "_lineage_root_id": "orphan-session",
                "workspace": str((tmp_path / "repo").resolve()),
                "title": "",
                "source_tag": "ops_task",
                "archived": False,
                "updated_at": "2026-05-05T12:10:00Z",
            },
        ],
    )

    payload = ops_sessions.list_ops_sessions(project["id"])

    session_ids = [session["session_id"] for session in payload["sessions"]]
    assert "orphan-session" not in session_ids
    assert "linked-session" in session_ids
    assert "manual-session" in session_ids
    assert payload["groups"][0]["sessionCount"] == 2
    linked = next(session for session in payload["sessions"] if session["session_id"] == "linked-session")
    assert linked["ops_task_id"] == "task-1"


def test_phase4_close_task_session_archives_linked_session_and_stops_run(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)

    from api.routes import handle_get, handle_post
    from api.models import get_session

    create = _FakeHandler({"name": "Session Close Project", "path": str(repo), "coreBranch": "main"})
    assert handle_post(create, urlparse("http://example.com/api/ops/projects")) is True
    project = _response_json(create)["project"]

    epic_create = _FakeHandler({"title": "Phase 4"})
    assert handle_post(epic_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/epics")) is True
    epic_id = _response_json(epic_create)["epic"]["id"]

    task_create = _FakeHandler({"epicId": epic_id, "text": "Close this linked session"})
    assert handle_post(task_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    task = _response_json(task_create)["task"]

    launch = _FakeHandler()
    assert handle_post(
        launch,
        urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks/{task['id']}/sessions/launch"),
    ) is True
    launch_payload = _response_json(launch)
    session_id = launch_payload["session"]["session_id"]
    run_id = launch_payload["run"]["id"]

    close = _FakeHandler({"sessionId": session_id})
    assert handle_post(
        close,
        urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks/{task['id']}/session/close"),
    ) is True
    close_payload = _response_json(close)

    assert close_payload["ok"] is True
    assert close_payload["sessionId"] == session_id
    assert close_payload["run"]["id"] == run_id
    assert close_payload["run"]["status"] == "stopped"
    assert get_session(session_id).archived is True

    tasks = _FakeHandler()
    assert handle_get(tasks, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    linked_task = next(epic["tasks"][0] for epic in _response_json(tasks)["epics"] if epic["id"] == epic_id)
    assert "inProgress" not in linked_task


def test_phase4_complete_task_route_marks_task_done_and_run_succeeded(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)

    from api.routes import handle_get, handle_post

    create = _FakeHandler({"name": "Session Complete Project", "path": str(repo), "coreBranch": "main"})
    assert handle_post(create, urlparse("http://example.com/api/ops/projects")) is True
    project = _response_json(create)["project"]

    epic_create = _FakeHandler({"title": "Phase 4"})
    assert handle_post(epic_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/epics")) is True
    epic_id = _response_json(epic_create)["epic"]["id"]

    task_create = _FakeHandler({"epicId": epic_id, "text": "Complete this linked session"})
    assert handle_post(task_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    task = _response_json(task_create)["task"]

    launch = _FakeHandler()
    assert handle_post(
        launch,
        urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks/{task['id']}/sessions/launch"),
    ) is True
    launch_payload = _response_json(launch)
    session_id = launch_payload["session"]["session_id"]

    complete = _FakeHandler({"sessionId": session_id})
    assert handle_post(
        complete,
        urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks/{task['id']}/complete"),
    ) is True
    complete_payload = _response_json(complete)

    assert complete_payload["ok"] is True
    assert complete_payload["task"]["done"] is True
    assert complete_payload["task"]["completedAt"]
    assert complete_payload["run"]["status"] == "succeeded"

    tasks = _FakeHandler()
    assert handle_get(tasks, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    linked_task = next(epic["tasks"][0] for epic in _response_json(tasks)["epics"] if epic["id"] == epic_id)
    assert linked_task["done"] is True


def test_phase4_complete_task_route_without_linked_session_still_marks_task_done(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)

    from api.routes import handle_get, handle_post

    create = _FakeHandler({"name": "Sessionless Complete Project", "path": str(repo), "coreBranch": "main"})
    assert handle_post(create, urlparse("http://example.com/api/ops/projects")) is True
    project = _response_json(create)["project"]

    epic_create = _FakeHandler({"title": "Phase 4"})
    assert handle_post(epic_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/epics")) is True
    epic_id = _response_json(epic_create)["epic"]["id"]

    task_create = _FakeHandler({"epicId": epic_id, "text": "Complete this task without a linked session"})
    assert handle_post(task_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    task = _response_json(task_create)["task"]

    complete = _FakeHandler({})
    assert handle_post(
        complete,
        urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks/{task['id']}/complete"),
    ) is True
    complete_payload = _response_json(complete)

    assert complete_payload["ok"] is True
    assert complete_payload["task"]["done"] is True
    assert complete_payload["task"]["completedAt"]
    assert complete_payload["run"] is None

    tasks = _FakeHandler()
    assert handle_get(tasks, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    linked_task = next(epic["tasks"][0] for epic in _response_json(tasks)["epics"] if epic["id"] == epic_id)
    assert linked_task["done"] is True


def test_phase4_plain_task_update_route_accepts_legacy_qa_fields(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)

    from api.routes import handle_get, handle_post

    create = _FakeHandler({"name": "Session Update Project", "path": str(repo), "coreBranch": "main"})
    assert handle_post(create, urlparse("http://example.com/api/ops/projects")) is True
    project = _response_json(create)["project"]

    epic_create = _FakeHandler({"title": "Phase 4"})
    assert handle_post(epic_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/epics")) is True
    epic_id = _response_json(epic_create)["epic"]["id"]

    task_create = _FakeHandler({"epicId": epic_id, "text": "Carry QA state"})
    assert handle_post(task_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    task = _response_json(task_create)["task"]

    update = _FakeHandler({"qaStatus": "needs-more-work", "moreWork": "Fix the regression", "inProgress": True})
    assert handle_post(
        update,
        urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks/{task['id']}"),
    ) is True
    updated_task = _response_json(update)["task"]
    assert updated_task["qaStatus"] == "needs-more-work"
    assert updated_task["moreWork"] == "Fix the regression"
    assert updated_task["inProgress"] is True

    tasks = _FakeHandler()
    assert handle_get(tasks, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    linked_task = next(epic["tasks"][0] for epic in _response_json(tasks)["epics"] if epic["id"] == epic_id)
    assert linked_task["qaStatus"] == "needs-more-work"
    assert linked_task["moreWork"] == "Fix the regression"


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


def test_phase4_legacy_execute_uses_persisted_model_state_when_ops_has_no_dropdown():
    script = textwrap.dedent(
        """
        (async () => {
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/ops-legacy-task-actions.js', 'utf8');
        let ensuredPayload = null;

        const windowRef = {
          HermesOpsModules: {},
          localStorage: {
            getItem(key){
              if (key === 'hermes-webui-model-state'){
                return JSON.stringify({ model: 'gpt-5.5', model_provider: 'openai' });
              }
              return null;
            }
          }
        };

        const context = {
          console,
          window: windowRef,
          document: {},
          setTimeout,
          clearTimeout,
        };
        vm.createContext(context);
        vm.runInContext(source, context);

        const project = { id: 'project-1', name: 'Hermes', path: '/tmp/hermes', profile: 'hermes' };
        const task = { id: 'task-1', text: 'Execute from ops', grade: 'green' };
        const dashboard = context.window.HermesOpsModules.taskActions.bindDashboard({
          OPS: {
            currentProject: project,
            sessions: [],
            taskDataByProject: {},
            taskAutomationBusyByProject: {},
            quickTaskImages: [],
            view: 'project-detail',
          },
          AgentBridge: {
            sessions: {
              ensureTask: async (_projectId, _taskId, payload) => {
                ensuredPayload = payload;
                return { session: { session_id: 'sess-1' } };
              },
            },
            runs: {
              create: async () => ({ id: 'run-1' }),
            },
          },
          api: async () => ({}),
          projectUrl: (projectId, suffix='') => '/api/ops/projects/' + projectId + suffix,
          projectPath: (entry) => entry.path,
          nameOf: (entry) => entry.name,
          findProject: () => project,
          findTask: () => ({ epic: { id: 'epic-1' }, task }),
          findTaskInData: () => null,
          allTasks: () => [],
          findSession: () => null,
          sessionTaskId: () => '',
          latestSessionForTask: () => null,
          sessionRefValue: (value) => typeof value === 'string' ? value : ((value && value.session_id) || ''),
          normalizeTaskGrade: (value) => value,
          getTaskQaStatus: () => '',
          getTaskMoreWork: () => '',
          actionableTaskCount: () => 1,
          summarizeTaskFilters: () => ({}),
          renderProjectDetail: () => {},
          loadProjectDetail: async () => {},
          refreshOpsSessions: async () => [],
          reloadProjectTasks: async () => ({}),
          loadProjects: async () => {},
          renderProjects: () => {},
          renderHome: () => {},
          loadSession: async () => {},
          renderSessionList: async () => {},
          closeOpsDashboard: () => {},
          showToast: () => {},
          showPromptDialog: async () => null,
          showConfirmDialog: async () => false,
          setBusy: () => {},
          domLookup: () => null,
          documentRef: {},
          windowRef,
          FileReaderRef: null,
          SRef: () => ({ session: null, activeProfile: 'default' }),
          addFiles: () => {},
          renderTray: () => {},
          clearSessionReadableOutput: () => {},
          clearPersistedSessionId: () => {},
          sendTurn: async () => {},
          autoResize: () => {},
          clearQuickTaskImages: () => {},
        });

        await dashboard.executeTask('task-1');
        if (!ensuredPayload){
          throw new Error('Expected ensureTask to be called.');
        }
        if (ensuredPayload.model !== 'gpt-5.5'){
          throw new Error('Expected persisted model to be forwarded to ensureTask.');
        }
        if (ensuredPayload.model_provider !== 'openai'){
          throw new Error('Expected persisted model_provider to be forwarded to ensureTask.');
        }
        if (ensuredPayload.profile !== 'default'){
          throw new Error('Expected active profile to be forwarded to ensureTask.');
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

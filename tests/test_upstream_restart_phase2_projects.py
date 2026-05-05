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

    def header(self, name):
        for key, value in self.sent_headers:
            if key.lower() == name.lower():
                return value
        return None


def _response_json(handler: _FakeHandler) -> dict:
    return json.loads(bytes(handler.body).decode("utf-8"))


def init_project_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "sample-project"
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    run_git(repo, "checkout", "-b", "feature/ops-shell")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "initial")
    return repo


def test_phase2_project_routes_round_trip_branch_scoped_tasks(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))
    repo = init_project_repo(tmp_path)
    (repo / "project_tasks.json").write_text(
        json.dumps({"epics": [{"id": "legacy-epic", "title": "Legacy epic", "tasks": []}]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    from api.routes import handle_get, handle_post

    create = _FakeHandler({"name": "Sample Project", "path": str(repo), "coreBranch": "main"})
    assert handle_post(create, urlparse("http://example.com/api/ops/projects")) is True
    assert create.status == 201
    project = _response_json(create)["project"]
    project_id = project["id"]

    listing = _FakeHandler()
    assert handle_get(listing, urlparse("http://example.com/api/ops/projects")) is True
    listed_projects = _response_json(listing)["projects"]
    assert listed_projects and listed_projects[0]["id"] == project_id
    assert listed_projects[0]["tasksBranch"] == "feature/ops-shell"
    assert listed_projects[0]["tasksFilePath"].endswith("project_tasks/feature%2Fops-shell.json")
    assert listed_projects[0]["epicCount"] == 1

    tasks_before = _FakeHandler()
    assert handle_get(tasks_before, urlparse(f"http://example.com/api/ops/projects/{project_id}/tasks")) is True
    tasks_payload = _response_json(tasks_before)
    assert tasks_payload["branch"] == "feature/ops-shell"
    assert tasks_payload["epics"][0]["title"] == "Legacy epic"

    epic_create = _FakeHandler({"title": "Restart work"})
    assert handle_post(epic_create, urlparse(f"http://example.com/api/ops/projects/{project_id}/epics")) is True
    assert epic_create.status == 201
    epic_id = _response_json(epic_create)["epic"]["id"]

    task_create = _FakeHandler(
        {
            "epicId": epic_id,
            "text": "Port branch task round-trip",
            "grade": "orange",
            "markers": ["migration", "ui"],
            "flags": ["blocked"],
        }
    )
    assert handle_post(task_create, urlparse(f"http://example.com/api/ops/projects/{project_id}/tasks")) is True
    assert task_create.status == 201
    task = _response_json(task_create)["task"]

    task_update = _FakeHandler({"done": True})
    assert handle_post(
        task_update,
        urlparse(f"http://example.com/api/ops/projects/{project_id}/tasks/{task['id']}/update"),
    ) is True
    assert _response_json(task_update)["task"]["done"] is True

    tasks_after = _FakeHandler()
    assert handle_get(tasks_after, urlparse(f"http://example.com/api/ops/projects/{project_id}/tasks")) is True
    epics = _response_json(tasks_after)["epics"]
    created_epic = next(epic for epic in epics if epic["id"] == epic_id)
    assert created_epic["tasks"][0]["text"] == "Port branch task round-trip"
    assert created_epic["tasks"][0]["done"] is True
    assert created_epic["tasks"][0]["markers"] == ["migration", "ui"]
    assert created_epic["tasks"][0]["flags"] == ["blocked"]


def test_phase2_shell_includes_projects_asset_and_payload():
    from api.routes import handle_get

    shell_page = _FakeHandler()
    assert handle_get(shell_page, urlparse("http://example.com/ops-phase")) is True
    html = bytes(shell_page.body).decode("utf-8")
    assert 'src="static/ops-projects.js?v=' in html
    assert 'data-ops-shell="cloud-terminal"' in html

    shell_api = _FakeHandler()
    assert handle_get(shell_api, urlparse("http://example.com/api/ops/shell")) is True
    payload = _response_json(shell_api)
    assert payload["phase"].startswith("phase-")
    assert payload["assets"]["projectsScript"] == "/static/ops-projects.js"

    script = _FakeHandler()
    assert handle_get(script, urlparse("http://example.com/static/ops-projects.js")) is True
    assert script.status == 200
    assert (script.header("Content-Type") or "").startswith("application/javascript")


def test_phase2_project_compatibility_routes_expose_legacy_ops_capabilities(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))
    repo = init_project_repo(tmp_path)

    from api.routes import handle_get, handle_post

    create = _FakeHandler({"name": "Compat Project", "path": str(repo), "coreBranch": "main"})
    assert handle_post(create, urlparse("http://example.com/api/ops/projects")) is True
    assert create.status == 201
    project = _response_json(create)["project"]
    project_id = project["id"]

    assert project["opsCapabilities"]["ensureWorkspace"] is True
    assert project["opsCapabilities"]["projectSettings"] is True
    assert project["opsCapabilities"]["projectActivity"] is True
    assert project["opsCapabilities"]["projectDeletion"] is True
    assert project["opsCapabilities"]["dependencyHealth"] is False
    assert project["opsCapabilities"]["deployment"] is False

    ensure_workspace = _FakeHandler({})
    assert handle_post(
        ensure_workspace,
        urlparse(f"http://example.com/api/ops/projects/{project_id}/ensure-workspace"),
    ) is True
    assert ensure_workspace.status == 200
    assert _response_json(ensure_workspace)["ok"] is True

    save_settings = _FakeHandler({"profile": ""})
    assert handle_post(
        save_settings,
        urlparse(f"http://example.com/api/ops/projects/{project_id}/settings"),
    ) is True
    assert save_settings.status == 200
    assert _response_json(save_settings)["project"]["profile"] is None

    deactivate = _FakeHandler({"active": False})
    assert handle_post(
        deactivate,
        urlparse(f"http://example.com/api/ops/projects/{project_id}/activity"),
    ) is True
    assert deactivate.status == 200
    assert _response_json(deactivate)["project"]["active"] is False

    listing = _FakeHandler()
    assert handle_get(listing, urlparse("http://example.com/api/ops/projects")) is True
    listed_projects = _response_json(listing)["projects"]
    listed_project = next(item for item in listed_projects if item["id"] == project_id)
    assert listed_project["active"] is False

    delete = _FakeHandler({"confirm": "delete-project"})
    assert handle_post(
        delete,
        urlparse(f"http://example.com/api/ops/projects/{project_id}/delete"),
    ) is True
    assert delete.status == 200
    assert _response_json(delete)["projects"] == []


def test_phase2_projects_view_renders_before_background_hydration():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (async () => {
          const source = fs.readFileSync('static/ops-legacy-projects.js', 'utf8');
          let releaseSessions = null;
          let releaseTasks = null;
          const groupedPromise = new Promise((resolve) => { releaseSessions = resolve; });
          const tasksPromise = new Promise((resolve) => { releaseTasks = resolve; });
          const rootEl = { innerHTML: '' };
          const project = {
            id: 'project-1',
            name: 'hermes-webui',
            fullName: 'Sajdkick/hermes-webui',
            path: '/tmp/hermes-webui',
            coreBranch: 'master',
            profile: 'hermes',
          };

          const windowRef = { HermesOpsModules: {} };
          const context = {
            console,
            window: windowRef,
            document: {
              getElementById(){ return null; },
            },
            setTimeout,
            clearTimeout,
          };
          vm.createContext(context);
          vm.runInContext(source, context);

          const dashboard = context.window.HermesOpsModules.projects.bindDashboard({
            OPS: {
              view: 'home',
              projects: [],
              profiles: [],
              sessions: [],
              sessionGroups: null,
              counts: {},
              taskDataByProject: {},
              currentProject: null,
              taskData: null,
              showCreate: false,
              playStatusByProject: {},
              gitStatusByProject: {},
            },
            api: async (path) => {
              if (path === '/api/ops/projects') {
                return { projects: [project] };
              }
              if (path === '/api/ops/projects/project-1/tasks') {
                return tasksPromise;
              }
              throw new Error('Unexpected api path: ' + path);
            },
            AgentBridge: {
              sessions: {
                grouped: async () => groupedPromise,
                list: async () => ({ sessions: [] }),
              },
              profiles: {
                list: async () => ({ profiles: [{ name: 'hermes' }] }),
              },
            },
            root: () => rootEl,
            esc: (value) => String(value ?? ''),
            svg: { plus: '', refresh: '', arrow: '', chat: '', folder: '' },
            nameOf: (entry) => entry.fullName || entry.name || entry.id,
            projectPath: (entry) => entry.path,
            projectUrl: (projectId, suffix = '') => '/api/ops/projects/' + projectId + suffix,
            projectProfileLabel: (entry) => entry.profile || 'No assigned profile',
            renderProjectProfileOptions: () => '',
            projectUsesBranchTitle: () => false,
            projectCardTitle: (entry) => entry.fullName || entry.name || entry.id,
            projectContextLabel: () => '',
            projectAccentStyle: () => '',
            setDashboardTopbar: () => {},
            renderLoading: (label) => { rootEl.innerHTML = label; },
            renderGitHubDiscovery: () => '',
            renderSessionWorkspaceActions: () => '',
            renderProjectSessionRows: () => '',
            showToast: () => {},
            resetTaskFilters: () => {},
            renderProjectDetail: () => '',
            refreshProjectPlayStatus: async () => null,
            refreshProjectGitStatus: async () => null,
            playStatusFor: () => null,
            playStatusKind: () => '',
            playStatusLabel: () => '',
            loadOpsRuns: async () => [],
            loadProjectDependencyStatus: async () => null,
            loadProjectGatherReports: async () => null,
            loadProjectReviewRequests: async () => null,
            loadProjectDeployment: async () => null,
            loadProjectDatabase: async () => null,
          });

          const result = await Promise.race([
            dashboard.openProjects().then(() => 'resolved'),
            new Promise((resolve) => setTimeout(() => resolve('timeout'), 100)),
          ]);
          if (result !== 'resolved') {
            throw new Error('openProjects waited for background hydration.');
          }
          if (!rootEl.innerHTML.includes('Sajdkick/hermes-webui')) {
            throw new Error('Projects view did not render project cards immediately.');
          }
          if (!rootEl.innerHTML.includes('project-page-content')) {
            throw new Error('Projects view did not switch to the Cloud Terminal project-page shell.');
          }
          if (!rootEl.innerHTML.includes('quick-response-panel')) {
            throw new Error('Projects view did not use the Cloud Terminal quick-response shell.');
          }
          if (!rootEl.innerHTML.includes('quick-response-project-card')) {
            throw new Error('Projects view did not render Cloud Terminal-style project cards.');
          }
          if (!rootEl.innerHTML.includes('Loading task counts...')) {
            throw new Error('Projects view did not show interim background hydration state.');
          }

          releaseSessions({ sessions: [], groups: [], ungrouped: [] });
          releaseTasks({ epics: [{ id: 'epic-1', title: 'Quick tasks', tasks: [{ id: 'task-1', done: false }] }] });
          await new Promise((resolve) => setTimeout(resolve, 0));
          await new Promise((resolve) => setTimeout(resolve, 0));

          if (!rootEl.innerHTML.includes('1 active task')) {
            throw new Error('Projects view did not hydrate task counts after the background requests resolved.');
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


def test_phase2_project_detail_uses_cloud_terminal_task_shell():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (() => {
          const source = fs.readFileSync('static/ops-legacy-project-detail.js', 'utf8');
          const rootEl = { innerHTML: '' };
          const windowRef = { HermesOpsModules: {} };
          const context = {
            console,
            window: windowRef,
            document: {},
            setTimeout,
            clearTimeout,
            URL,
          };
          vm.createContext(context);
          vm.runInContext(source, context);

          const project = {
            id: 'project-1',
            name: 'hermes-webui',
            fullName: 'Sajdkick/hermes-webui',
            path: '/tmp/hermes-webui',
            coreBranch: 'master',
            profile: 'hermes',
            active: true,
          };
          const epics = [{
            id: 'epic-1',
            title: 'Quick tasks',
            tasks: [{
              id: 'task-1',
              text: 'Match the Cloud Terminal task shell',
              done: false,
              grade: 'orange',
              createdAt: '2026-05-05T00:00:00Z',
              dependencies: [],
              flags: ['ui'],
              markers: ['AI suggestion'],
            }],
          }];

          const dashboard = context.window.HermesOpsModules.projectDetail.bindDashboard({
            OPS: {
              currentProject: project,
              taskData: { branch: 'master', epics },
              taskFilters: { status: 'active', grade: '', token: '' },
              taskCreateCollapsed: false,
              taskFiltersCollapsed: false,
              taskAutomationBusyByProject: {},
              editingTask: null,
            },
            root: () => rootEl,
            esc: (value) => String(value ?? ''),
            svg: { plus: '', refresh: '', close: '', play: '', folder: '', grid: '', arrow: '', trash: '', check: '' },
            setDashboardTopbar: () => {},
            showError: () => {},
            summarizeEpics: (items) => {
              const allTasks = (items || []).flatMap((epic) => epic.tasks || []);
              return {
                epics: (items || []).length,
                active: allTasks.filter((task) => !task.done && !task.archived).length,
                done: allTasks.filter((task) => task.done).length,
              };
            },
            nameOf: (entry) => entry.fullName || entry.name || entry.id,
            projectPath: (entry) => entry.path,
            projectProfileLabel: (entry) => entry.profile || 'No assigned profile',
            rememberTaskFilterFocus: () => {},
            restoreTaskFilterFocus: () => {},
            syncEpicCollapseState: () => {},
            isEpicCollapsed: () => false,
            renderProjectPlayControls: () => '',
            renderProjectSettings: () => '',
            renderProjectHealth: () => '',
            renderProjectGitStatus: () => '',
            renderProjectPlayConfigEditor: () => '',
            renderProjectRuntimeSnapshot: () => '',
            renderProjectRuntimeScreenshot: () => '',
            renderProjectPlayLogs: () => '',
            renderProjectGatherReports: () => '',
            renderProjectReviewRequests: () => '',
            renderProjectDeployment: () => '',
            renderProjectDatabase: () => '',
            renderProjectRunActivity: () => '',
            renderRunDetailPanel: () => '',
            resolvedTaskSession: () => null,
            sessionRefValue: (value) => value || '',
            updateTaskGrade: async () => null,
            windowRef,
            URLRef: URL,
          });

          dashboard.renderProjectDetail();
          const html = rootEl.innerHTML;
          if (!html.includes('tasks-wrapper show')) throw new Error('Missing Cloud Terminal tasks wrapper shell.');
          if (!html.includes('tasks-hero')) throw new Error('Missing Cloud Terminal tasks hero.');
          if (!html.includes('tasks-layout')) throw new Error('Missing Cloud Terminal tasks layout.');
          if (!html.includes('tasks-card tasks-card-create')) throw new Error('Missing Cloud Terminal create card.');
          if (!html.includes('tasks-card tasks-card-filters')) throw new Error('Missing Cloud Terminal filters card.');
          if (!html.includes('tasks-list')) throw new Error('Missing Cloud Terminal tasks list.');
          if (!html.includes('epic-card')) throw new Error('Missing Cloud Terminal epic cards.');
          if (!html.includes('task-item')) throw new Error('Missing Cloud Terminal task items.');
          if (html.includes('ops-toolbar')) throw new Error('Legacy Hermes toolbar should not render inside the Cloud Terminal task shell.');
          if (html.includes('ops-create-band')) throw new Error('Legacy Hermes create band should not render inside the Cloud Terminal task shell.');

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

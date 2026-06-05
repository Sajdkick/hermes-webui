import base64
import io
import json
import shutil
import subprocess
import textwrap
from pathlib import Path
from urllib.parse import urlparse

import pytest


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


def _run_git(repo: Path, *args: str) -> str:
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


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "task-image-project"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test User")
    _run_git(repo, "checkout", "-b", "feature/task-images")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "initial")
    return repo


def test_ops_task_image_upload_route_persists_file_and_task_reference(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))

    repo = _init_repo(tmp_path)

    from api.routes import handle_post, handle_get

    create = _FakeHandler({"name": "Task Image Project", "path": str(repo), "coreBranch": "main"})
    assert handle_post(create, urlparse("http://example.com/api/ops/projects")) is True
    project = _response_json(create)["project"]

    epic_create = _FakeHandler({"title": "Quick tasks"})
    assert handle_post(epic_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/epics")) is True
    epic_id = _response_json(epic_create)["epic"]["id"]

    task_create = _FakeHandler({"epicId": epic_id, "text": "Use the attached screenshot"})
    assert handle_post(task_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    task = _response_json(task_create)["task"]

    png_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=")
    upload = _FakeHandler(
        {
            "filename": "screen shot.png",
            "mimeType": "image/png",
            "content": "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii"),
        }
    )
    assert handle_post(
        upload,
        urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks/{task['id']}/images"),
    ) is True
    assert upload.status == 201
    image = _response_json(upload)["image"]
    image_path = Path(image["path"])
    assert image_path.exists()
    assert image_path.read_bytes() == png_bytes
    assert image_path.name == "screen-shot.png"
    assert str(image_path).startswith(str(tmp_path / "hermes-home"))

    tasks = _FakeHandler()
    assert handle_get(tasks, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    uploaded_task = _response_json(tasks)["epics"][0]["tasks"][0]
    assert uploaded_task["images"] == str(image_path)


def test_ops_open_session_forces_reload_to_avoid_stale_active_session_state():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (async () => {
          const source = fs.readFileSync('static/ops-legacy-task-actions.js', 'utf8');
          const windowRef = { HermesOpsModules: {}, _opsDashboardOpen: true };
          const context = { console, window: windowRef, document: {} };
          vm.createContext(context);
          vm.runInContext(source, context);

          let loadCall = null;
          const dashboard = context.window.HermesOpsModules.taskActions.bindDashboard({
            OPS: { sessions: [] },
            AgentBridge: { sessions: {}, runs: {} },
            api: async () => ({}),
            projectUrl: () => '',
            projectPath: () => '',
            nameOf: () => 'Project',
            findProject: () => null,
            findTask: () => null,
            findTaskInData: () => null,
            allTasks: () => [],
            findSession: () => null,
            sessionTaskId: () => '',
            latestSessionForTask: () => null,
            sessionRefValue: (entry) => typeof entry === 'string' ? entry : (entry && (entry.session_id || entry.id)) || '',
            normalizeTaskGrade: () => 'green',
            getTaskQaStatus: () => '',
            getTaskMoreWork: () => '',
            actionableTaskCount: () => 0,
            summarizeTaskFilters: () => '',
            renderProjectDetail: () => {},
            loadProjectDetail: async () => ({}),
            refreshOpsSessions: async () => [],
            reloadProjectTasks: async () => ({}),
            loadProjects: async () => [],
            renderProjects: () => {},
            renderHome: () => {},
            loadSession: async (sid, options) => { loadCall = { sid, options }; },
            renderSessionList: async () => {},
            closeOpsDashboard: () => {},
            enterOpsSessionInspectMode: () => {},
            showToast: () => {},
            showPromptDialog: async () => null,
            showConfirmDialog: async () => false,
            setBusy: () => {},
            domLookup: () => ({ value: '', files: [] }),
            documentRef: context.document,
            windowRef,
            FileReaderRef: function(){},
            SRef: () => ({ session: { session_id: 'target-session' }, messages: [{ role: 'assistant', content: 'stale' }], entries: [] }),
            addFiles: () => {},
            renderTray: () => {},
            clearPersistedSessionId: () => {},
            sendTurn: async () => {},
            autoResize: () => {},
            clearQuickTaskImages: () => {},
          });

          await dashboard.openOpsSession('target-session');
          if (!loadCall || loadCall.sid !== 'target-session' || !loadCall.options || loadCall.options.force !== true) {
            throw new Error(`Expected forced loadSession call, got ${JSON.stringify(loadCall)}`);
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

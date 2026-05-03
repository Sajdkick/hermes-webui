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


def init_sync_repos(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    run_git(tmp_path, "init", "--bare", str(remote))

    seed = tmp_path / "seed"
    seed.mkdir()
    run_git(seed, "init")
    run_git(seed, "config", "user.email", "test@example.com")
    run_git(seed, "config", "user.name", "Test User")
    run_git(seed, "checkout", "-b", "main")
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    run_git(seed, "add", "README.md")
    run_git(seed, "commit", "-m", "seed")
    run_git(seed, "remote", "add", "origin", str(remote))
    run_git(seed, "push", "-u", "origin", "main")
    run_git(remote, "symbolic-ref", "HEAD", "refs/heads/main")

    work = tmp_path / "work"
    run_git(tmp_path, "clone", str(remote), str(work))
    run_git(work, "config", "user.email", "test@example.com")
    run_git(work, "config", "user.name", "Test User")
    run_git(work, "checkout", "-b", "feature/phase8-sync")
    return seed, work


def test_phase8_project_git_status_compares_against_core_branch(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    seed, work = init_sync_repos(tmp_path)

    (work / "README.md").write_text("seed\nlocal\n", encoding="utf-8")
    run_git(work, "add", "README.md")
    run_git(work, "commit", "-m", "local ahead")

    (seed / "README.md").write_text("seed\nremote\n", encoding="utf-8")
    run_git(seed, "add", "README.md")
    run_git(seed, "commit", "-m", "remote ahead")
    run_git(seed, "push", "origin", "main")
    run_git(work, "fetch", "origin")

    from api.routes import handle_get, handle_post

    create = _FakeHandler({"name": "Phase 8 Sync Project", "path": str(work), "coreBranch": "main"})
    assert handle_post(create, urlparse("http://example.com/api/ops/projects")) is True
    project = _response_json(create)["project"]

    status_handler = _FakeHandler()
    assert handle_get(
        status_handler,
        urlparse(f"http://example.com/api/ops/projects/{project['id']}/git/status"),
    ) is True
    assert status_handler.status == 200
    status = _response_json(status_handler)["git"]

    assert status["branch"] == "feature/phase8-sync"
    assert status["configuredUpstream"] == ""
    assert status["upstream"] == "origin/main"
    assert status["coreBranch"] == "main"
    assert status["ahead"] >= 1
    assert status["behind"] >= 1
    assert status["dirty"] is False
    assert status["lastCommit"]["subject"] == "local ahead"


def test_phase8_ops_ui_renders_git_status_panel():
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
        const gitSource = fs.readFileSync('static/ops-git.js', 'utf8');
        const projectsSource = fs.readFileSync('static/ops-projects.js', 'utf8');
        const fetch = async (path) => {
          fetchCalls.push(path);
          if (path === '/api/ops/notifications/pending'){
            return { ok: true, json: async () => ({ count: 0, notifications: [] }) };
          }
          if (path === '/api/profiles'){
            return { ok: true, json: async () => ({ active: 'default', profiles: [] }) };
          }
          if (path === '/api/ops/projects'){
            return {
              ok: true,
              json: async () => ({
                projects: [{
                  id: 'project-1',
                  name: 'Phase 8 Sync Project',
                  path: '/tmp/phase8-sync-project',
                  coreBranch: 'main',
                  tasksBranch: 'feature/phase8-sync',
                  tasksFilePath: '/tmp/phase8-sync-project/project_tasks/feature%2Fphase8-sync.json',
                  taskCount: 0,
                  profile: 'default',
                  defaultModel: '',
                  defaultModelProvider: ''
                }]
              })
            };
          }
          if (path === '/api/ops/projects/project-1/tasks'){
            return {
              ok: true,
              json: async () => ({
                project: { id: 'project-1', name: 'Phase 8 Sync Project' },
                epics: []
              })
            };
          }
          if (path === '/api/ops/projects/project-1/git/status'){
            return {
              ok: true,
              json: async () => ({
                git: {
                  projectId: 'project-1',
                  coreBranch: 'main',
                  branch: 'feature/phase8-sync',
                  upstream: 'origin/main',
                  ahead: 1,
                  behind: 2,
                  dirty: false,
                  conflicts: 0,
                  counts: { files: 0, untracked: 0, conflicts: 0 },
                  repositoryRoot: '/tmp/phase8-sync-project',
                  lastCommit: { shortSha: 'abc1234', subject: 'Local sync work' }
                }
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
                  snapshot: { available: true, label: 'Runtime snapshot' },
                  screenshot: { available: true, label: 'Runtime screenshot' },
                  actions: { available: true, label: 'Runtime actions' },
                  play: { available: true, label: 'Play workflow' }
                },
                gather: { count: 0, reports: [] },
                reviews: { count: 0, reviews: [] },
                play: {
                  status: 'idle',
                  statusSummary: 'Play config is ready.',
                  configExists: true,
                  valid: true,
                  inspectUrl: '',
                  ready: false,
                  running: false,
                  configPath: '/tmp/phase8-sync-project/project_play.json'
                }
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
        vm.runInContext(gitSource, context);
        vm.runInContext(projectsSource, context);

        const root = new Root();
        context.window.HermesOpsProjects.mount(root, {
          phase: 'phase-8',
          route: '/ops',
          apiBase: '/api/ops',
          version: 'test-version',
        });

        const click = root.listeners.click;
        click({
          target: {
            closest: () => ({
              getAttribute: (name) => name === 'data-ops-action' ? 'toggle-projects' : null
            })
          }
        });

        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));

        if (!root.innerHTML.includes('Git status')){
          throw new Error('Git status panel did not render');
        }
        if (!root.innerHTML.includes('Diverged')){
          throw new Error('Derived git status label did not render');
        }
        if (!root.innerHTML.includes('Sync target origin/main')){
          throw new Error('Git status summary did not render');
        }
        if (!fetchCalls.includes('/api/ops/projects/project-1/git/status')){
          throw new Error('Git status endpoint was not requested');
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

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
    repo = tmp_path / "phase8-project"
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    run_git(repo, "checkout", "-b", "feature/phase8")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "initial")
    return repo


def _write_profile(home: Path, name: str, *, default_model: str, provider: str):
    profile_home = home if name == "default" else home / "profiles" / name
    profile_home.mkdir(parents=True, exist_ok=True)
    (profile_home / "config.yaml").write_text(
        textwrap.dedent(
            f"""
            model:
              provider: {provider}
              default: {default_model}
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def test_phase8_project_defaults_flow_into_task_launch(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)
    hermes_home = tmp_path / "hermes-home"
    _write_profile(hermes_home, "default", default_model="deepseek/deepseek-v4-flash", provider="deepseek")
    _write_profile(hermes_home, "research", default_model="qwen/qwen3-coder", provider="qwen")

    from api import profiles as api_profiles
    from api.routes import handle_get, handle_post

    monkeypatch.setattr(api_profiles, "_DEFAULT_HERMES_HOME", hermes_home)

    create = _FakeHandler({"name": "Phase 8 Project", "path": str(repo), "coreBranch": "main", "profile": "research"})
    assert handle_post(create, urlparse("http://example.com/api/ops/projects")) is True
    assert create.status == 201
    project = _response_json(create)["project"]
    assert project["profile"] == "research"
    assert project["defaultModel"] is None

    listing = _FakeHandler()
    assert handle_get(listing, urlparse("http://example.com/api/ops/projects")) is True
    listed = _response_json(listing)["projects"][0]
    assert listed["profile"] == "research"

    epic_create = _FakeHandler({"title": "Phase 8"})
    assert handle_post(epic_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/epics")) is True
    epic_id = _response_json(epic_create)["epic"]["id"]

    task_create = _FakeHandler({"epicId": epic_id, "text": "Launch with profile defaults"})
    assert handle_post(task_create, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    task = _response_json(task_create)["task"]

    launch_profile_default = _FakeHandler()
    assert handle_post(
        launch_profile_default,
        urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks/{task['id']}/sessions/launch"),
    ) is True
    profile_default_payload = _response_json(launch_profile_default)
    assert profile_default_payload["session"]["profile"] == "research"
    assert profile_default_payload["session"]["model"] == "qwen/qwen3-coder"
    assert profile_default_payload["session"]["model_provider"] == "qwen"

    update = _FakeHandler(
        {
            "profile": "default",
            "defaultModel": "openai/gpt-5.4-mini",
            "defaultModelProvider": "openai",
        }
    )
    assert handle_post(update, urlparse(f"http://example.com/api/ops/projects/{project['id']}/update")) is True
    updated_project = _response_json(update)["project"]
    assert updated_project["profile"] == "default"
    assert updated_project["defaultModel"] == "openai/gpt-5.4-mini"
    assert updated_project["defaultModelProvider"] == "openai"

    launch_override = _FakeHandler()
    assert handle_post(
        launch_override,
        urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks/{task['id']}/sessions/launch"),
    ) is True
    override_payload = _response_json(launch_override)
    assert override_payload["session"]["profile"] == "default"
    assert override_payload["session"]["model"] == "openai/gpt-5.4-mini"
    assert override_payload["session"]["model_provider"] == "openai"


def test_phase8_ops_ui_renders_project_defaults_form_and_save():
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
        const projectsSource = fs.readFileSync('static/ops-projects.js', 'utf8');
        const fetch = async (path, options) => {
          fetchCalls.push({ path, options: options || null });
          if (path === '/api/ops/notifications/pending'){
            return { ok: true, json: async () => ({ count: 0, notifications: [] }) };
          }
          if (path === '/api/profiles'){
            return {
              ok: true,
              json: async () => ({
                active: 'research',
                profiles: [
                  { name: 'default', model: 'deepseek/deepseek-v4-flash', provider: 'deepseek' },
                  { name: 'research', model: 'qwen/qwen3-coder', provider: 'qwen' }
                ]
              })
            };
          }
          if (path === '/api/ops/projects'){
            return {
              ok: true,
              json: async () => ({
                projects: [{
                  id: 'project-1',
                  name: 'Phase 8 Project',
                  path: '/tmp/phase8-project',
                  tasksBranch: 'feature/phase8',
                  tasksFilePath: '/tmp/phase8-project/project_tasks/feature%2Fphase8.json',
                  taskCount: 0,
                  profile: 'research',
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
                project: { id: 'project-1', name: 'Phase 8 Project' },
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
                  configPath: '/tmp/phase8-project/project_play.json'
                }
              })
            };
          }
          if (path === '/api/ops/projects/project-1/update'){
            return {
              ok: true,
              json: async () => ({
                project: {
                  id: 'project-1',
                  name: 'Phase 8 Project',
                  profile: 'research',
                  defaultModel: 'openai/gpt-5.4-mini',
                  defaultModelProvider: 'openai'
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
          FormData: function FormData(form){
            if (form && form.__kind === 'project-defaults'){
              return {
                get: (name) => ({
                  profile: 'research',
                  defaultModel: 'openai/gpt-5.4-mini',
                  defaultModelProvider: 'openai'
                })[name] || ''
              };
            }
            return { get: () => '' };
          },
          setTimeout,
          clearTimeout,
        };
        vm.createContext(context);
        vm.runInContext(projectsSource, context);

        const root = new Root();
        context.window.HermesOpsProjects.mount(root, {
          phase: 'phase-8',
          route: '/ops',
          apiBase: '/api/ops',
          version: 'test-version',
        });

        const click = root.listeners.click;
        const submit = root.listeners.submit;

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

        if (!root.innerHTML.includes('Launch defaults')){
          throw new Error('Project defaults form did not render');
        }
        if (!root.innerHTML.includes('research')){
          throw new Error('Selected project profile did not render');
        }
        if (!root.innerHTML.includes('Selected profile defaults: Model qwen/qwen3-coder')){
          throw new Error('Profile metadata hint did not render');
        }

        const defaultsForm = new HTMLFormElement();
        defaultsForm.__kind = 'project-defaults';
        defaultsForm.matches = (selector) => selector === '[data-ops-form="project-defaults"]';
        submit({
          preventDefault(){},
          target: defaultsForm
        });

        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));

        if (!fetchCalls.some((call) => call.path === '/api/profiles')){
          throw new Error('/api/profiles was not requested');
        }
        const updateCall = fetchCalls.find((call) => call.path === '/api/ops/projects/project-1/update');
        if (!updateCall){
          throw new Error('Project defaults update endpoint was not requested');
        }
        const body = JSON.parse(updateCall.options.body || '{}');
        if (body.profile !== 'research' || body.defaultModel !== 'openai/gpt-5.4-mini' || body.defaultModelProvider !== 'openai'){
          throw new Error('Project defaults update payload was incorrect');
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

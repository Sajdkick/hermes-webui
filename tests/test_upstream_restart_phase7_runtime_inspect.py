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
    repo = tmp_path / "inspect-project"
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    run_git(repo, "checkout", "-b", "feature/runtime-inspect")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "initial")
    return repo


def test_phase7_runtime_inspect_routes_wrap_ct_runtime(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)

    from api import ops_projects, ops_runtime_inspect
    from api.routes import handle_get, handle_post

    project = ops_projects.create_ops_project({"name": "Inspect Project", "path": str(repo), "coreBranch": "main"})
    project_id = project["id"]

    screenshot_path = repo / ".hermes" / "ops" / "captures" / "runtime-check.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot_path.write_text("png-data", encoding="utf-8")
    action_capture_path = repo / ".hermes" / "ops" / "captures" / "runtime-action.png"
    action_capture_path.write_text("png-data", encoding="utf-8")
    manifest_path = repo / ".hermes" / "ops" / "runtime-inspect" / "artifacts" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text('{"items":[]}', encoding="utf-8")

    commands = []

    def fake_ct_runtime(project_path, args):
        entry = {"command": ["ct-runtime", *args], "cwd": str(project_path)}
        if "--script-file" in args:
            script_path = Path(args[args.index("--script-file") + 1])
            entry["script"] = json.loads(script_path.read_text(encoding="utf-8"))
        commands.append(entry)
        command = entry["command"]
        if command[:3] == ["ct-runtime", "inspect", "url"]:
            payload = {
                "inspectUrl": f"/play-project/{project_id}/app/runtime-preview",
                "browserUrl": "http://127.0.0.1:25123/app/runtime-preview",
                "inspectSession": {"id": "inspect-session-1", "currentPublicUrl": f"/play-project/{project_id}/app/runtime-preview"},
            }
        elif command[:3] == ["ct-runtime", "inspect", "reset-state"]:
            payload = {
                "summary": "Reset debug state and primed the inspect session.",
                "inspectUrl": f"/play-project/{project_id}/app/editor",
                "browserUrl": "http://127.0.0.1:25123/app/editor",
                "inspectSession": {"id": "inspect-session-1", "currentPublicUrl": f"/play-project/{project_id}/app/editor"},
            }
        elif command[:3] == ["ct-runtime", "inspect", "screenshot"]:
            payload = {
                "absolutePath": str(screenshot_path),
                "inspectUrl": f"/play-project/{project_id}/app/editor",
                "capture": {"kind": "element-screenshot", "selector": "canvas", "absolutePath": str(screenshot_path)},
                "page": {"summary": 'Captured /app/editor. Title: "Editor".', "pageTitle": "Editor", "finalPath": "/app/editor"},
                "inspectSession": {"id": "inspect-session-2"},
            }
        elif command[:3] == ["ct-runtime", "inspect", "action"]:
            payload = {
                "success": True,
                "inspectUrl": f"/play-project/{project_id}/app/editor",
                "actions": {
                    "requestedCount": 2,
                    "executedCount": 2,
                    "results": [
                        {"index": 0, "description": 'Waited for "canvas".'},
                        {"index": 1, "description": 'Clicked "canvas".'},
                    ],
                },
                "capture": {"absolutePath": str(action_capture_path), "kind": "full-page-screenshot"},
                "artifacts": {"manifest": {"absolutePath": str(manifest_path)}},
                "page": {"pageTitle": "Editor", "finalPath": "/app/editor"},
                "inspectSession": {"id": "inspect-session-3"},
            }
        else:
            raise AssertionError(f"Unexpected command: {command}")
        return payload

    monkeypatch.setattr(ops_runtime_inspect, "_run_ct_runtime_json", fake_ct_runtime)

    snapshot = _FakeHandler({})
    assert handle_post(snapshot, urlparse(f"http://example.com/api/ops/projects/{project_id}/runtime/inspect/snapshot")) is True
    snapshot_payload = _response_json(snapshot)["snapshot"]
    assert snapshot.status == 201
    assert snapshot_payload["kind"] == "inspect-url"
    assert snapshot_payload["inspectUrl"] == f"/play-project/{project_id}/app/runtime-preview"

    reset_state = _FakeHandler({"resetState": True, "timeoutMs": 45000})
    assert handle_post(reset_state, urlparse(f"http://example.com/api/ops/projects/{project_id}/runtime/inspect/snapshot")) is True
    reset_payload = _response_json(reset_state)["snapshot"]
    assert reset_payload["kind"] == "reset-state"
    assert "Reset debug state" in reset_payload["summary"]

    screenshot = _FakeHandler({"url": "/app/editor", "selector": "canvas", "fileName": "frame-check"})
    assert handle_post(screenshot, urlparse(f"http://example.com/api/ops/projects/{project_id}/runtime/inspect/screenshot")) is True
    screenshot_payload = _response_json(screenshot)["screenshot"]
    assert screenshot.status == 201
    assert screenshot_payload["absolutePath"] == str(screenshot_path)
    assert screenshot_payload["capture"]["selector"] == "canvas"

    action = _FakeHandler(
        {
            "url": "/app/editor",
            "fileName": "runtime-action",
            "captureScreenshot": True,
            "script": json.dumps(
                [
                    {"type": "waitForSelectorVisible", "selector": "canvas"},
                    {"type": "click", "selector": "canvas", "x": 120, "y": 90},
                ]
            ),
        }
    )
    assert handle_post(action, urlparse(f"http://example.com/api/ops/projects/{project_id}/runtime/inspect/action")) is True
    action_payload = _response_json(action)["action"]
    assert action.status == 201
    assert action_payload["actions"]["requestedCount"] == 2
    assert action_payload["capture"]["absolutePath"] == str(action_capture_path)

    latest_snapshot = _FakeHandler()
    assert handle_get(latest_snapshot, urlparse(f"http://example.com/api/ops/projects/{project_id}/runtime/inspect/snapshot/latest")) is True
    assert _response_json(latest_snapshot)["snapshot"]["kind"] == "reset-state"

    latest_screenshot = _FakeHandler()
    assert handle_get(latest_screenshot, urlparse(f"http://example.com/api/ops/projects/{project_id}/runtime/inspect/screenshot/latest")) is True
    assert _response_json(latest_screenshot)["screenshot"]["absolutePath"] == str(screenshot_path)

    latest_action = _FakeHandler()
    assert handle_get(latest_action, urlparse(f"http://example.com/api/ops/projects/{project_id}/runtime/inspect/action/latest")) is True
    assert _response_json(latest_action)["action"]["actions"]["executedCount"] == 2

    summary = _FakeHandler()
    assert handle_get(summary, urlparse(f"http://example.com/api/ops/projects/{project_id}/runtime/summary")) is True
    summary_payload = _response_json(summary)
    assert summary_payload["capabilities"]["snapshot"]["available"] is True
    assert summary_payload["capabilities"]["screenshot"]["available"] is True
    assert summary_payload["capabilities"]["actions"]["available"] is True
    assert summary_payload["snapshot"]["kind"] == "reset-state"
    assert summary_payload["screenshot"]["absolutePath"] == str(screenshot_path)
    assert summary_payload["actions"]["capture"]["absolutePath"] == str(action_capture_path)

    inspect_dir = repo / ".hermes" / "ops" / "runtime-inspect"
    assert (inspect_dir / "snapshot.json").exists()
    assert (inspect_dir / "screenshot.json").exists()
    assert (inspect_dir / "action.json").exists()

    assert commands[0]["command"] == ["ct-runtime", "inspect", "url"]
    assert commands[1]["command"] == ["ct-runtime", "inspect", "reset-state", "--timeout", "45000ms"]
    assert commands[2]["command"] == [
        "ct-runtime",
        "inspect",
        "screenshot",
        "--url",
        "/app/editor",
        "--selector",
        "canvas",
        "--file-name",
        "frame-check",
    ]
    assert commands[3]["command"][:3] == ["ct-runtime", "inspect", "action"]
    assert "--capture-screenshot" in commands[3]["command"]
    assert commands[3]["script"]["actions"][1]["type"] == "click"
    assert all(Path(entry["cwd"]).resolve() == repo.resolve() for entry in commands)


def test_phase7_ops_ui_renders_runtime_inspect_controls():
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
                    name: 'Inspect Project',
                    path: '/tmp/inspect-project',
                    tasksBranch: 'feature/runtime-inspect',
                    coreBranch: 'main',
                    taskCount: 0,
                    tasksFilePath: '/tmp/inspect-project/project_tasks/feature%2Fruntime-inspect.json'
                  }
                ]
              })
            };
          }
          if (path === '/api/ops/projects/project-1/tasks'){
            return {
              ok: true,
              json: async () => ({
                project: { id: 'project-1', name: 'Inspect Project' },
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
                snapshot: {
                  kind: 'reset-state',
                  summary: 'Reset debug state and primed the inspect session.',
                  inspectUrl: '/play-project/project-1/app/editor',
                  sessionId: 'inspect-session-1',
                  updatedAt: '2026-05-03T00:00:00.000Z'
                },
                screenshot: {
                  kind: 'screenshot',
                  summary: 'Captured /app/editor. Title: "Editor".',
                  absolutePath: '/tmp/inspect-project/.hermes/ops/captures/runtime-check.png',
                  inspectUrl: '/play-project/project-1/app/editor',
                  updatedAt: '2026-05-03T00:01:00.000Z'
                },
                actions: {
                  kind: 'action',
                  summary: 'Executed 2/2 runtime inspect actions.',
                  actions: { requestedCount: 2, executedCount: 2 },
                  capture: { absolutePath: '/tmp/inspect-project/.hermes/ops/captures/runtime-action.png' },
                  updatedAt: '2026-05-03T00:02:00.000Z'
                },
                play: {
                  status: 'idle',
                  statusSummary: 'Play config is ready. Start the pipeline to inspect the app.',
                  configExists: true,
                  valid: true,
                  inspectUrl: '',
                  ready: false,
                  running: false,
                  configPath: '/tmp/inspect-project/project_play.json'
                }
              })
            };
          }
          if (path === '/api/ops/projects/project-1/runtime/inspect/snapshot'){
            return { ok: true, json: async () => ({ snapshot: { kind: 'inspect-url' } }) };
          }
          if (path === '/api/ops/projects/project-1/runtime/inspect/screenshot'){
            return { ok: true, json: async () => ({ screenshot: { kind: 'screenshot' } }) };
          }
          if (path === '/api/ops/projects/project-1/runtime/inspect/action'){
            return { ok: true, json: async () => ({ action: { kind: 'action' } }) };
          }
          throw new Error('Unexpected fetch path: ' + path);
        };

        const context = {
          console,
          window: { location: { assign: () => {} } },
          fetch,
          HTMLFormElement,
          HTMLElement,
          HTMLInputElement,
          FormData: function FormData(form){
            if (form && form.__kind === 'runtime-screenshot'){
              return {
                get: (name) => ({
                  url: '/app/editor',
                  selector: 'canvas',
                  fileName: 'runtime-check'
                })[name] || ''
              };
            }
            if (form && form.__kind === 'runtime-action'){
              return {
                get: (name) => ({
                  url: '/app/editor',
                  fileName: 'runtime-action',
                  captureScreenshot: name === 'captureScreenshot' ? 'on' : undefined,
                  script: '[{"type":"waitForSelectorVisible","selector":"canvas"},{"type":"click","selector":"canvas"}]'
                })[name] || ''
              };
            }
            return { get: () => '' };
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
        const submit = root.listeners.submit;

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

        if (!root.innerHTML.includes('Inspect toolkit')){
          throw new Error('Inspect toolkit did not render');
        }
        if (!root.innerHTML.includes('Capture screenshot')){
          throw new Error('Runtime screenshot form did not render');
        }
        if (!root.innerHTML.includes('Run actions')){
          throw new Error('Runtime action form did not render');
        }
        if (!root.innerHTML.includes('runtime-check.png')){
          throw new Error('Latest runtime screenshot summary did not render');
        }

        click({
          target: {
            closest: (selector) => {
              if (selector !== '[data-ops-action]') return null;
              return { getAttribute: (name) => name === 'data-ops-action' ? 'run-inspect-url' : '' };
            }
          }
        });

        const screenshotForm = new HTMLFormElement();
        screenshotForm.__kind = 'runtime-screenshot';
        screenshotForm.matches = (selector) => selector === '[data-ops-form="runtime-screenshot"]';
        submit({
          preventDefault(){},
          target: screenshotForm
        });

        const actionForm = new HTMLFormElement();
        actionForm.__kind = 'runtime-action';
        actionForm.matches = (selector) => selector === '[data-ops-form="runtime-action"]';
        submit({
          preventDefault(){},
          target: actionForm
        });

        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));

        if (!fetchCalls.some((call) => call.path === '/api/ops/projects/project-1/runtime/inspect/snapshot')){
          throw new Error('Runtime snapshot endpoint was not requested');
        }
        if (!fetchCalls.some((call) => call.path === '/api/ops/projects/project-1/runtime/inspect/screenshot')){
          throw new Error('Runtime screenshot endpoint was not requested');
        }
        if (!fetchCalls.some((call) => call.path === '/api/ops/projects/project-1/runtime/inspect/action')){
          throw new Error('Runtime action endpoint was not requested');
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

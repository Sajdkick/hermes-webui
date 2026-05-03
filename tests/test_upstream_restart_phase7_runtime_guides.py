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
    repo = tmp_path / "runtime-project"
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    run_git(repo, "checkout", "-b", "feature/runtime-guides")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "initial")
    return repo


def test_phase7_runtime_guides_routes_round_trip(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)

    from api import ops_guides, ops_projects
    from api.routes import handle_get, handle_post

    monkeypatch.setattr(ops_guides, "OPS_GATHER_REPORTS_FILE", tmp_path / "ops-gather-reports.json")
    monkeypatch.setattr(ops_guides, "OPS_REVIEW_REQUESTS_FILE", tmp_path / "ops-review-requests.json")

    project = ops_projects.create_ops_project({"name": "Runtime Project", "path": str(repo), "coreBranch": "main"})
    project_id = project["id"]

    report_create = _FakeHandler(
        {
            "title": "Homepage pass",
            "summary": "Initial visual pass",
            "status": "running",
            "url": "http://127.0.0.1:3000/",
            "taskId": "task-1",
            "sessionId": "session-1",
            "metadata": {"viewport": "desktop"},
        }
    )
    assert handle_post(report_create, urlparse(f"http://example.com/api/ops/projects/{project_id}/runtime/gather/reports")) is True
    assert report_create.status == 201
    report = _response_json(report_create)["report"]
    assert report["title"] == "Homepage pass"
    assert report["status"] == "running"
    assert Path(report["reportPath"]).exists()
    assert Path(report["reportPath"]).is_relative_to(repo / ".hermes" / "ops" / "gather")

    report_event = _FakeHandler(
        {
            "type": "assertion",
            "level": "warning",
            "message": "Header overlaps on mobile.",
            "status": "failed",
            "summary": "Mobile layout needs work.",
        }
    )
    assert handle_post(
        report_event,
        urlparse(f"http://example.com/api/ops/projects/{project_id}/runtime/gather/reports/{report['id']}/events"),
    ) is True
    updated_report = _response_json(report_event)["report"]
    assert updated_report["status"] == "failed"
    assert updated_report["eventsCount"] == 2

    review_create = _FakeHandler(
        {
            "title": "Homepage review",
            "prompt": "Check layout and text overlap.",
            "kind": "visual",
            "taskId": "task-1",
            "sessionId": "session-1",
            "gatherReportId": report["id"],
        }
    )
    assert handle_post(review_create, urlparse(f"http://example.com/api/ops/projects/{project_id}/runtime/inspect/reviews")) is True
    assert review_create.status == 201
    review = _response_json(review_create)["review"]
    assert review["status"] == "requested"
    assert Path(review["reviewPath"]).exists()
    assert Path(review["reviewPath"]).is_relative_to(repo / ".hermes" / "ops" / "reviews")

    review_complete = _FakeHandler(
        {
            "status": "failed",
            "summary": "Toolbar overlaps the main heading.",
            "issues": [{"code": "overlap", "severity": "high"}],
        }
    )
    assert handle_post(
        review_complete,
        urlparse(f"http://example.com/api/ops/projects/{project_id}/runtime/inspect/reviews/{review['id']}/complete"),
    ) is True
    completed_review = _response_json(review_complete)["review"]
    assert completed_review["status"] == "failed"
    assert completed_review["result"]["issues"][0]["code"] == "overlap"

    summary = _FakeHandler()
    assert handle_get(summary, urlparse(f"http://example.com/api/ops/projects/{project_id}/runtime/summary")) is True
    summary_payload = _response_json(summary)
    assert summary_payload["gather"]["count"] == 1
    assert summary_payload["gather"]["latest"]["summary"] == "Mobile layout needs work."
    assert summary_payload["reviews"]["count"] == 1
    assert summary_payload["reviews"]["latest"]["summary"] == "Toolbar overlaps the main heading."
    assert summary_payload["capabilities"]["gatherReports"]["available"] is True
    assert summary_payload["capabilities"]["play"]["available"] is True

    latest_review = _FakeHandler()
    assert handle_get(
        latest_review,
        urlparse(f"http://example.com/api/ops/projects/{project_id}/runtime/inspect/reviews/latest"),
    ) is True
    assert _response_json(latest_review)["review"]["id"] == review["id"]


def test_phase7_shell_includes_runtime_asset_and_payload():
    from api.routes import handle_get

    shell_page = _FakeHandler()
    assert handle_get(shell_page, urlparse("http://example.com/ops")) is True
    html = bytes(shell_page.body).decode("utf-8")
    assert "/static/ops-runtime.js" in html

    shell_api = _FakeHandler()
    assert handle_get(shell_api, urlparse("http://example.com/api/ops/shell")) is True
    payload = _response_json(shell_api)
    assert payload["phase"].startswith("phase-")
    assert payload["assets"]["runtimeScript"] == "/static/ops-runtime.js"

    script = _FakeHandler()
    assert handle_get(script, urlparse("http://example.com/static/ops-runtime.js")) is True
    assert script.status == 200
    assert (script.header("Content-Type") or "").startswith("application/javascript")


def test_phase7_ops_ui_renders_runtime_summary():
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
                    name: 'Runtime Project',
                    path: '/tmp/runtime-project',
                    tasksBranch: 'feature/runtime-guides',
                    coreBranch: 'main',
                    taskCount: 0,
                    tasksFilePath: '/tmp/runtime-project/project_tasks/feature%2Fruntime-guides.json'
                  }
                ]
              })
            };
          }
          if (path === '/api/ops/projects/project-1/tasks'){
            return {
              ok: true,
              json: async () => ({
                project: { id: 'project-1', name: 'Runtime Project' },
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
                  play: { available: false, label: 'Play workflow', reason: 'Pending port' }
                },
                gather: {
                  count: 1,
                  reports: [
                    {
                      id: 'gather-1',
                      title: 'Homepage pass',
                      status: 'failed',
                      summary: 'Mobile layout needs work.',
                      updatedAt: '2026-05-03T00:00:00.000Z',
                      reportPath: '/tmp/runtime-project/.hermes/ops/gather/gather-1/report.json',
                      latestEvent: { message: 'Header overlaps on mobile.' }
                    }
                  ]
                },
                reviews: {
                  count: 1,
                  reviews: [
                    {
                      id: 'review-1',
                      title: 'Homepage review',
                      status: 'failed',
                      prompt: 'Check layout and text overlap.',
                      summary: 'Toolbar overlaps the main heading.',
                      updatedAt: '2026-05-03T00:01:00.000Z',
                      reviewPath: '/tmp/runtime-project/.hermes/ops/reviews/review-1/review.json'
                    }
                  ]
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
          HTMLFormElement: function HTMLFormElement(){},
          HTMLElement: function HTMLElement(){},
          HTMLInputElement: function HTMLInputElement(){},
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
              return {
                getAttribute: (name) => name === 'data-ops-action' ? 'toggle-projects' : ''
              };
            }
          }
        });

        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));

        if (!root.innerHTML.includes('Runtime evidence')){
          throw new Error('Runtime evidence panel did not render');
        }
        if (!root.innerHTML.includes('Homepage pass')){
          throw new Error('Gather report title did not render');
        }
        if (!root.innerHTML.includes('Toolbar overlaps the main heading.')){
          throw new Error('Review summary did not render');
        }
        if (!fetchCalls.some((call) => call.path === '/api/ops/projects/project-1/runtime/summary')){
          throw new Error('Runtime summary endpoint was not requested');
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

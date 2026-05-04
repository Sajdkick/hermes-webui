import io
import json
import shutil
import subprocess
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

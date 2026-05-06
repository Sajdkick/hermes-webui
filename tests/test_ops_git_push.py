import io
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

import api.routes as routes
from api import ops_git, routes_ops_git


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


def _git(repo: Path, *args: str) -> str:
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


def test_ops_git_post_route_dispatches_push(monkeypatch):
    monkeypatch.setattr(
        ops_git,
        "execute_project_git_operation",
        lambda project_id, operation, body: {
            "id": "git-push-1",
            "projectId": project_id,
            "operation": operation,
            "status": "succeeded",
            "body": body,
        },
    )

    handler = _FakeHandler({"confirm": "push"})

    assert routes_ops_git.handle_post(
        handler,
        urlparse("http://example.com/api/ops/projects/project-1/git/push"),
        {"confirm": "push"},
    ) is True
    assert handler.status == 200
    payload = _response_json(handler)
    assert payload["operation"]["projectId"] == "project-1"
    assert payload["operation"]["operation"] == "push"


def test_ops_git_post_route_is_registered_in_main_routes(monkeypatch):
    calls = []
    handler = SimpleNamespace(command="POST", headers={}, host="127.0.0.1")

    def fake_post(_handler, parsed, body):
        calls.append((parsed.path, body))
        return parsed.path == "/api/ops/projects/project-1/git/push"

    monkeypatch.setattr(routes_ops_git, "handle_post", fake_post)
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    monkeypatch.setattr(routes, "read_body", lambda _handler: {"confirm": "push"})

    assert routes.handle_post(handler, SimpleNamespace(path="/api/ops/projects/project-1/git/push", query="")) is True
    assert calls == [("/api/ops/projects/project-1/git/push", {"confirm": "push"})]


def test_ops_git_commands_use_cloud_terminal_github_token_env(monkeypatch, tmp_path):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs.get("env") or {}
        return subprocess.CompletedProcess(args, 0, stdout="ok\n", stderr="")

    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert ops_git._git_stdout(tmp_path, ["status"]) == "ok"

    env = captured["env"]
    assert captured["args"] == ["git", "status"]
    assert env["GIT_ASKPASS"] == "echo"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_CONFIG_COUNT"] == "1"
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert env["GIT_CONFIG_VALUE_0"].startswith("AUTHORIZATION: basic ")


def test_execute_project_push_pushes_ahead_commit(monkeypatch, tmp_path, git_available):
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "checkout", "-b", "main")
    (repo / "README.md").write_text("initial\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main")

    (repo / "README.md").write_text("initial\nlocal change\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "local change")

    project = {"id": "project-1", "resolvedPath": str(repo), "coreBranch": "main"}
    monkeypatch.setattr(ops_git.ops_projects, "get_ops_project", lambda project_id: project)

    before = ops_git.get_project_git_status("project-1")
    assert before["ahead"] == 1

    operation = ops_git.execute_project_git_operation("project-1", "push", {"confirm": "push"})

    assert operation["status"] == "succeeded"
    assert operation["operation"] == "push"
    assert "Pushed main to origin/main." in operation["summary"]
    assert operation["finalStatus"]["ahead"] == 0
    assert _git(remote, "rev-parse", "refs/heads/main") == _git(repo, "rev-parse", "HEAD")


def test_execute_project_push_auto_commits_dirty_changes_and_merges_into_core_branch(monkeypatch, tmp_path, git_available):
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)

    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init")
    _git(seed, "config", "user.email", "test@example.com")
    _git(seed, "config", "user.name", "Test User")
    _git(seed, "checkout", "-b", "main")
    (seed / "README.md").write_text("initial\n", encoding="utf-8")
    _git(seed, "add", "README.md")
    _git(seed, "commit", "-m", "initial")
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "-u", "origin", "main")
    _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")

    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", str(remote), str(repo)], check=True, capture_output=True, text=True)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "checkout", "-b", "feature/push-auto")

    (repo / "README.md").write_text("initial\nfeature change\n", encoding="utf-8")

    project = {"id": "project-1", "resolvedPath": str(repo), "coreBranch": "main"}
    monkeypatch.setattr(ops_git.ops_projects, "get_ops_project", lambda project_id: project)

    before = ops_git.get_project_git_status("project-1")
    assert before["branch"] == "feature/push-auto"
    assert before["dirty"] is True

    operation = ops_git.execute_project_git_operation(
        "project-1",
        "push",
        {"confirm": "push", "message": "Auto commit from push"},
    )

    assert operation["status"] == "succeeded"
    assert "Committed local changes." in operation["summary"]
    assert "Merged feature/push-auto into main." in operation["summary"]
    assert "Pushed main to origin/main." in operation["summary"]
    assert operation["finalStatus"]["branch"] == "main"
    assert operation["finalStatus"]["dirty"] is False
    assert operation["finalStatus"]["ahead"] == 0
    assert _git(repo, "branch", "--show-current") == "main"
    assert _git(repo, "log", "-1", "--format=%s") == "Auto commit from push"
    assert _git(remote, "rev-parse", "refs/heads/main") == _git(repo, "rev-parse", "HEAD")


def test_execute_project_push_promotes_not_synced_tasks_after_success(monkeypatch, tmp_path, git_available):
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "checkout", "-b", "main")
    (repo / "README.md").write_text("initial\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main")

    task_file = repo / "project_tasks" / "main.json"
    task_file.parent.mkdir(parents=True, exist_ok=True)
    task_file.write_text(
        json.dumps(
            {
                "epics": [
                    {
                        "id": "epic-1",
                        "title": "Release",
                        "tasks": [
                            {
                                "id": "task-1",
                                "text": "Ship changes",
                                "done": False,
                                "qaStatus": "not-synced",
                                "inProgress": True,
                                "moreWork": "Waiting for push",
                            },
                            {
                                "id": "task-2",
                                "text": "Already done",
                                "done": True,
                                "qaStatus": "not-synced",
                            },
                        ],
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (repo / "README.md").write_text("initial\nlocal change\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "local change")

    project = {"id": "project-1", "resolvedPath": str(repo), "coreBranch": "main"}
    monkeypatch.setattr(ops_git.ops_projects, "get_ops_project", lambda project_id: project)

    operation = ops_git.execute_project_git_operation("project-1", "push", {"confirm": "push"})

    assert operation["status"] == "succeeded"
    assert operation["taskUpdates"] == 1
    assert operation["readyForTestTaskIds"] == ["task-1"]
    assert "Marked 1 task ready for test." in operation["summary"]

    payload = json.loads(task_file.read_text(encoding="utf-8"))
    tasks = payload["epics"][0]["tasks"]
    assert tasks[0]["qaStatus"] == "ready-for-test"
    assert "inProgress" not in tasks[0]
    assert "moreWork" not in tasks[0]
    assert tasks[1]["qaStatus"] == "not-synced"


def test_get_project_git_status_ignores_cloud_terminal_runtime_artifacts(monkeypatch, tmp_path, git_available):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "checkout", "-b", "main")
    (repo / "README.md").write_text("initial\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")

    artifact_path = repo / ".cloud-terminal" / "readable-output" / "session-1"
    artifact_path.mkdir(parents=True, exist_ok=True)
    (artifact_path / "message.md").write_text("runtime note\n", encoding="utf-8")

    project = {"id": "project-1", "resolvedPath": str(repo), "coreBranch": "main"}
    monkeypatch.setattr(ops_git.ops_projects, "get_ops_project", lambda project_id: project)

    status = ops_git.get_project_git_status("project-1")

    assert status["dirty"] is False
    assert status["counts"]["files"] == 0
    assert status["files"] == []

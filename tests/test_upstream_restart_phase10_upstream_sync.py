import io
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

import api.routes as routes
from api import ops_projects, ops_upstream_sync, routes_ops_upstream_sync


def run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def register_project(monkeypatch, tmp_path: Path, repo: Path) -> dict:
    projects_dir = tmp_path / "projects"
    write_json(projects_dir / "projects.json", [])
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(projects_dir))
    monkeypatch.setattr(ops_projects, "load_workspaces", lambda: [])
    monkeypatch.setattr(ops_projects, "save_workspaces", lambda workspaces: None)
    monkeypatch.setattr(ops_projects, "validate_workspace_to_add", lambda path: Path(path).resolve())
    return ops_projects.create_ops_project({"name": "Sync Project", "path": str(repo), "coreBranch": "main"})


def init_sync_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    run_git(repo, "checkout", "-b", "feature/local")
    (repo / "README.md").write_text("initial\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "initial")

    upstream_remote = tmp_path / "upstream.git"
    subprocess.run(["git", "init", "--bare", str(upstream_remote)], check=True, capture_output=True, text=True)
    run_git(repo, "remote", "add", "origin", str(upstream_remote))
    run_git(repo, "remote", "add", "upstream", str(upstream_remote))
    run_git(repo, "push", "origin", "HEAD:refs/heads/main")
    run_git(upstream_remote, "symbolic-ref", "HEAD", "refs/heads/main")
    run_git(repo, "push", "-u", "origin", "feature/local")

    seed = tmp_path / "seed"
    run_git(tmp_path, "clone", str(upstream_remote), str(seed))
    run_git(seed, "config", "user.email", "test@example.com")
    run_git(seed, "config", "user.name", "Test User")
    run_git(seed, "checkout", "main")
    return repo, seed


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


def test_phase10_prepare_upstream_sync_context_creates_worktree_and_collects_state(tmp_path, monkeypatch, git_available):
    repo, seed = init_sync_repo(tmp_path)
    project = register_project(monkeypatch, tmp_path, repo)
    monkeypatch.setattr(ops_upstream_sync, "OPS_UPSTREAM_SYNC_ROOT", tmp_path / "ops" / "upstream-sync")
    monkeypatch.setattr(ops_upstream_sync, "OPS_UPSTREAM_SYNC_RECORDS_DIR", tmp_path / "ops" / "upstream-sync" / "records")
    monkeypatch.setattr(ops_upstream_sync, "OPS_UPSTREAM_SYNC_WORKTREES_DIR", tmp_path / "ops" / "upstream-sync" / "worktrees")

    (seed / "README.md").write_text("seed\nupstream change\n", encoding="utf-8")
    run_git(seed, "add", "README.md")
    run_git(seed, "commit", "-m", "upstream change")
    run_git(seed, "push", "origin", "main")

    context = ops_upstream_sync._create_context(project["id"], {})

    assert context.repo_path == repo.resolve()
    assert context.source_branch == "feature/local"
    assert context.upstream_remote == "upstream"
    assert context.upstream_branch == "main"
    assert context.upstream_ref == "upstream/main"
    assert context.worktree_path.is_dir()
    assert run_git(context.worktree_path, "rev-parse", "--abbrev-ref", "HEAD") == context.sync_branch


def test_phase10_start_upstream_sync_session_records_prompt_and_session(monkeypatch, tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    record_root = tmp_path / "ops" / "upstream-sync"
    monkeypatch.setattr(ops_upstream_sync, "OPS_UPSTREAM_SYNC_ROOT", record_root)
    monkeypatch.setattr(ops_upstream_sync, "OPS_UPSTREAM_SYNC_RECORDS_DIR", record_root / "records")
    monkeypatch.setattr(ops_upstream_sync, "OPS_UPSTREAM_SYNC_WORKTREES_DIR", record_root / "worktrees")

    project = {"id": "project-1", "name": "Sync Project", "coreBranch": "main"}
    context = ops_upstream_sync.UpstreamSyncContext(
        project=project,
        repo_path=tmp_path / "repo",
        worktree_path=worktree,
        source_branch="feature/local",
        source_head_sha="abc123def4567890",
        sync_branch="upstream-sync/feature-local/20260504-000000",
        upstream_remote="upstream",
        upstream_branch="main",
        upstream_ref="upstream/main",
        profile="default",
        model="gpt-5.5",
        model_provider="openai",
    )

    class FakeSession:
        def __init__(self):
            self.session_id = "sess-1"
            self.workspace = str(worktree)
            self.model = "gpt-5.5"
            self.model_provider = "openai"
            self.messages = []
            self.title = ""
            self.source_tag = None
            self.source_label = None

        def save(self):
            return None

        def compact(self):
            return {"session_id": self.session_id, "workspace": self.workspace, "model": self.model}

    monkeypatch.setattr(ops_upstream_sync, "_create_context", lambda project_id, body=None: context)
    monkeypatch.setattr(ops_upstream_sync, "new_session", lambda **kwargs: FakeSession())
    monkeypatch.setattr(ops_upstream_sync, "_start_session_prompt", lambda session, message: "stream-1")
    monkeypatch.setattr(
        ops_upstream_sync,
        "_status_from_record",
        lambda record: {"recordId": record["id"], "state": "awaiting_review", "message": "Review pending.", "sessionUrl": "/session/sess-1"},
    )

    result = ops_upstream_sync.start_project_upstream_sync("project-1", {})

    assert result["ok"] is True
    assert result["streamId"] == "stream-1"
    assert result["sessionUrl"] == "/session/sess-1"
    record = ops_upstream_sync._read_record(result["recordId"])
    assert record is not None
    assert record["sessionId"] == "sess-1"
    assert record["sourceBranch"] == "feature/local"
    assert record["sourceHeadSha"] == "abc123def4567890"
    assert record["profile"] == "default"
    assert record["model"] == "gpt-5.5"
    assert "Read AGENTS.md" in record["prompt"]
    assert "Type 1: /ops dashboard/project/task-flow work" in record["prompt"]
    assert "If upstream already fixed it, remove our local patch" in record["prompt"]
    assert "docs/local-upstream-patches.md" in record["prompt"]
    assert str(worktree) in record["prompt"]


def test_phase10_upstream_sync_prefers_active_profile_defaults_when_present(monkeypatch):
    project = {
        "id": "project-1",
        "name": "Sync Project",
        "profile": "hermes",
        "defaultModel": "gpt-5.2",
        "defaultModelProvider": "openai-codex",
    }

    monkeypatch.setattr(ops_upstream_sync, "_active_profile_name", lambda: "summons")
    monkeypatch.setattr(
        ops_upstream_sync.ops_sessions,
        "_profile_config_defaults",
        lambda profile: ("gpt-5.5", "openai-codex") if profile == "summons" else ("gpt-5.2", "openai-codex"),
    )
    monkeypatch.setattr(
        ops_upstream_sync.ops_sessions,
        "project_session_defaults",
        lambda _project: ("gpt-5.2", "openai-codex"),
    )
    monkeypatch.setattr(
        ops_upstream_sync.ops_sessions,
        "project_profile",
        lambda _project: "hermes",
    )

    profile, model, provider = ops_upstream_sync._resolve_profile_and_model(project, {})

    assert profile == "summons"
    assert model == "gpt-5.5"
    assert provider == "openai-codex"


def test_phase10_upstream_sync_respects_explicit_profile_override(monkeypatch):
    project = {
        "id": "project-1",
        "name": "Sync Project",
        "profile": "hermes",
    }

    monkeypatch.setattr(ops_upstream_sync, "_active_profile_name", lambda: "summons")
    monkeypatch.setattr(
        ops_upstream_sync.ops_sessions,
        "_profile_config_defaults",
        lambda profile: ("gpt-5.4-mini", "openai") if profile == "default" else ("gpt-5.5", "openai-codex"),
    )
    monkeypatch.setattr(
        ops_upstream_sync.ops_sessions,
        "project_session_defaults",
        lambda _project: ("gpt-5.2", "openai-codex"),
    )
    monkeypatch.setattr(
        ops_upstream_sync.ops_sessions,
        "project_profile",
        lambda _project: "hermes",
    )

    profile, model, provider = ops_upstream_sync._resolve_profile_and_model(project, {"profile": "default"})

    assert profile == "default"
    assert model == "gpt-5.4-mini"
    assert provider == "openai"


def test_phase10_apply_upstream_sync_fast_forwards_live_checkout(tmp_path, monkeypatch, git_available):
    repo, seed = init_sync_repo(tmp_path)
    project = register_project(monkeypatch, tmp_path, repo)
    monkeypatch.setattr(ops_upstream_sync, "OPS_UPSTREAM_SYNC_ROOT", tmp_path / "ops" / "upstream-sync")
    monkeypatch.setattr(ops_upstream_sync, "OPS_UPSTREAM_SYNC_RECORDS_DIR", tmp_path / "ops" / "upstream-sync" / "records")
    monkeypatch.setattr(ops_upstream_sync, "OPS_UPSTREAM_SYNC_WORKTREES_DIR", tmp_path / "ops" / "upstream-sync" / "worktrees")

    (seed / "README.md").write_text("seed\nupstream change\n", encoding="utf-8")
    run_git(seed, "add", "README.md")
    run_git(seed, "commit", "-m", "upstream change")
    run_git(seed, "push", "origin", "main")

    context = ops_upstream_sync._create_context(project["id"], {})
    run_git(context.worktree_path, "merge", "--no-edit", context.upstream_ref)
    record = ops_upstream_sync._write_record(
        {
            "id": context.worktree_path.name,
            "projectId": project["id"],
            "sessionId": "sess-apply",
            "repoPath": str(context.repo_path),
            "worktreePath": str(context.worktree_path),
            "sourceBranch": context.source_branch,
            "sourceHeadSha": context.source_head_sha,
            "syncBranch": context.sync_branch,
            "upstreamRemote": context.upstream_remote,
            "upstreamBranch": context.upstream_branch,
            "upstreamRef": context.upstream_ref,
            "profile": None,
            "model": None,
            "modelProvider": None,
            "prompt": "prompt",
            "createdAt": "2026-05-04T00:00:00Z",
            "appliedAt": None,
            "appliedHeadSha": None,
        }
    )

    status = ops_upstream_sync.list_project_upstream_sync(project["id"])
    assert status["hasSync"] is True
    assert status["sync"]["canApply"] is True
    assert status["sync"]["state"] == "ready_for_review"

    result = ops_upstream_sync.apply_project_upstream_sync(project["id"], {"recordId": record["id"]})

    assert result["ok"] is True
    assert result["sync"]["applied"] is True
    assert result["sync"]["state"] == "applied"
    assert run_git(repo, "rev-parse", "HEAD") == run_git(context.worktree_path, "rev-parse", "HEAD")
    assert "upstream change" in (repo / "README.md").read_text(encoding="utf-8")


def test_phase10_upstream_sync_routes_dispatch_through_ops_modules(monkeypatch):
    dispatch_calls = []
    handler = SimpleNamespace(command="POST", headers={}, host="127.0.0.1")

    def fake_get(_handler, parsed):
        dispatch_calls.append(("get", parsed.path))
        return parsed.path == "/api/ops/projects/project-1/upstream-sync"

    def fake_post(_handler, parsed, body):
        dispatch_calls.append(("post", parsed.path, body))
        return parsed.path in {
            "/api/ops/projects/project-1/upstream-sync/start",
            "/api/ops/projects/project-1/upstream-sync/apply",
        }

    monkeypatch.setattr(routes_ops_upstream_sync, "handle_get", fake_get)
    monkeypatch.setattr(routes_ops_upstream_sync, "handle_post", fake_post)
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    monkeypatch.setattr(routes, "read_body", lambda _handler: {"recordId": "sync-1"})

    assert routes.handle_get(handler, SimpleNamespace(path="/api/ops/projects/project-1/upstream-sync", query="")) is True
    assert routes.handle_post(handler, SimpleNamespace(path="/api/ops/projects/project-1/upstream-sync/start", query="")) is True
    assert routes.handle_post(handler, SimpleNamespace(path="/api/ops/projects/project-1/upstream-sync/apply", query="")) is True

    assert dispatch_calls == [
        ("get", "/api/ops/projects/project-1/upstream-sync"),
        ("post", "/api/ops/projects/project-1/upstream-sync/start", {"recordId": "sync-1"}),
        ("post", "/api/ops/projects/project-1/upstream-sync/apply", {"recordId": "sync-1"}),
    ]


def test_phase10_upstream_sync_route_module_handles_direct_endpoints(monkeypatch):
    responses = []

    def fake_j(_handler, payload, status=200):
        responses.append((payload, status))
        return True

    monkeypatch.setattr(routes_ops_upstream_sync, "j", fake_j)
    monkeypatch.setattr(
        ops_upstream_sync,
        "list_project_upstream_sync",
        lambda project_id: {"projectId": project_id, "hasSync": False, "sync": None, "records": []},
    )
    monkeypatch.setattr(
        ops_upstream_sync,
        "start_project_upstream_sync",
        lambda project_id, body: {"ok": True, "projectId": project_id, "started": body},
    )
    monkeypatch.setattr(
        ops_upstream_sync,
        "apply_project_upstream_sync",
        lambda project_id, body: {"ok": True, "projectId": project_id, "applied": body},
    )

    handler = SimpleNamespace()
    assert routes_ops_upstream_sync.handle_get(handler, SimpleNamespace(path="/api/ops/projects/project-1/upstream-sync", query="")) is True
    assert routes_ops_upstream_sync.handle_post(handler, SimpleNamespace(path="/api/ops/projects/project-1/upstream-sync/start", query=""), {"profile": "default"}) is True
    assert routes_ops_upstream_sync.handle_post(handler, SimpleNamespace(path="/api/ops/projects/project-1/upstream-sync/apply", query=""), {"recordId": "sync-1"}) is True

    assert responses == [
        ({"projectId": "project-1", "hasSync": False, "sync": None, "records": []}, 200),
        ({"ok": True, "projectId": "project-1", "started": {"profile": "default"}}, 201),
        ({"ok": True, "projectId": "project-1", "applied": {"recordId": "sync-1"}}, 200),
    ]

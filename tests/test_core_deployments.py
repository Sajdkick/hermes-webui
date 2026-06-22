import json
import io
from email.message import Message
from pathlib import Path
from urllib.parse import urlparse

import pytest

from api import auth, core_deployments, routes
from api.runtime_process_cleanup import RuntimeProcessInfo


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class DummyHandler:
    def __init__(self, command: str = "GET", *, headers: dict | None = None, body: bytes = b"") -> None:
        self.command = command
        self.headers = headers or {}
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.status = None
        self.response_headers = []

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.response_headers.append((key, value))

    def end_headers(self) -> None:
        pass


def test_legacy_play_proxy_deployment_path_is_public_without_referer():
    handler = DummyHandler(headers={})
    parsed = urlparse("/play-proxy/run-1/deploy/alternativedata/api/trpc/auth.me?batch=1")

    assert core_deployments.is_deployment_public_request(handler, parsed) is True
    assert core_deployments.deployment_slug_from_request_context(handler, parsed) == "alternativedata"


def test_legacy_play_proxy_deployment_handler_strips_run_prefix(monkeypatch):
    handler = DummyHandler(headers={})
    parsed = urlparse("/play-proxy/run-1/deploy/alternativedata/api/trpc/auth.me?batch=1")
    calls = []

    def fake_proxy(inner_handler, slug, target_path, inner_parsed, *, method="GET"):
        calls.append((inner_handler, slug, target_path, inner_parsed.query, method))
        return True

    monkeypatch.setattr(core_deployments, "handle_deployment_proxy_request", fake_proxy)

    assert core_deployments.handle_legacy_play_proxy_deployment_request(handler, parsed, method="POST") is True
    assert calls == [(handler, "alternativedata", "/api/trpc/auth.me", "batch=1", "POST")]


def test_core_deployment_reads_cloud_terminal_record_without_writing_metadata(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    repo = projects_dir / "repo"
    repo.mkdir(parents=True)
    write_json(
        projects_dir / "projects.json",
        [{"id": "project-1", "name": "Alternative Data", "slug": "alternative-data", "path": str(repo), "coreBranch": "main"}],
    )
    deployments_dir = projects_dir / ".deployments"
    snapshot_source = deployments_dir / "items" / "alternativedata" / "source"
    snapshot_source.mkdir(parents=True)
    metadata = [
        {
            "id": "deployment-1",
            "projectId": "project-1",
            "slug": "alternativedata",
            "provider": "local-legacy",
            "databaseMode": "persistent",
            "status": "published",
            "createdAt": "2026-04-09T16:40:02.705Z",
            "updatedAt": "2026-05-26T15:56:33.451Z",
            "publishedAt": "2026-05-26T15:56:33.451Z",
            "providerConfig": {"ignored": True},
            "providerState": {"secretToken": "[REDACTED]"},
        }
    ]
    metadata_path = deployments_dir / "deployments.json"
    write_json(metadata_path, metadata)
    before = metadata_path.read_text(encoding="utf-8")

    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(projects_dir))
    monkeypatch.delenv("PROJECT_DEPLOYMENTS_DIR", raising=False)

    payload = core_deployments.get_project_deployment("project-1")

    assert metadata_path.read_text(encoding="utf-8") == before
    assert not (repo / ".hermes" / "ops" / "deployments" / "deployment.json").exists()
    deployment = payload["deployment"]
    assert deployment["source"] == "cloud-terminal"
    assert deployment["provider"] == "local-legacy"
    assert deployment["status"] == "published"
    assert deployment["slug"] == "alternativedata"
    assert deployment["url"] == "/deploy/alternativedata/"
    assert deployment["databaseMode"] == "persistent"
    assert deployment["database"] == {
        "mode": "persistent",
        "preservesExistingData": True,
        "deploymentProjectId": "project-1__deployment",
    }
    assert "without recreating or overwriting" in deployment["summary"]
    assert payload["artifacts"][0]["kind"] == "cloud-terminal-snapshot"
    assert payload["artifacts"][0]["exists"] is True
    assert payload["logs"][0]["action"] == "cloud-terminal.metadata"


def test_core_deployment_native_record_takes_precedence_over_cloud_terminal(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    repo = projects_dir / "repo"
    repo.mkdir(parents=True)
    write_json(
        projects_dir / "projects.json",
        [{"id": "project-1", "name": "Alternative Data", "slug": "alternative-data", "path": str(repo), "coreBranch": "main"}],
    )
    write_json(
        projects_dir / ".deployments" / "deployments.json",
        [{"id": "deployment-1", "projectId": "project-1", "slug": "alternativedata", "provider": "local-legacy", "databaseMode": "persistent", "status": "published"}],
    )
    write_json(
        repo / ".hermes" / "ops" / "deployments" / "deployment.json",
        {"provider": "manual", "status": "ready", "summary": "Hermes native record"},
    )
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(projects_dir))
    monkeypatch.delenv("PROJECT_DEPLOYMENTS_DIR", raising=False)

    payload = core_deployments.get_project_deployment("project-1")

    assert payload["deployment"]["status"] == "ready"
    assert payload["deployment"]["provider"] == "manual"
    assert payload["deployment"].get("source") != "cloud-terminal"
    assert not any(artifact.get("kind") == "cloud-terminal-snapshot" for artifact in payload["artifacts"])


def test_core_deployment_redeploy_local_legacy_builds_and_replaces_snapshot_without_auth(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    repo = projects_dir / "repo"
    repo.mkdir(parents=True)
    (repo / "app.txt").write_text("new code", encoding="utf-8")
    (repo / ".env").write_text("SECRET=do-not-copy", encoding="utf-8")
    write_json(
        repo / "project_play.json",
        {
            "build": {
                "command": "python3 -c \"from pathlib import Path; Path('built.txt').write_text('built via core', encoding='utf-8'); assets=Path('packages/client/dist/assets'); assets.mkdir(parents=True, exist_ok=True); (assets/'new-hash.js').write_text('new asset', encoding='utf-8')\"",
                "cwd": ".",
                "env": {"CORE_TEST_VALUE": "1"},
                "timeoutSeconds": 30,
            }
        },
    )
    write_json(
        projects_dir / "projects.json",
        [{"id": "project-1", "name": "Alternative Data", "slug": "alternative-data", "path": str(repo), "coreBranch": "main"}],
    )
    deployments_dir = projects_dir / ".deployments"
    snapshot_source = deployments_dir / "items" / "alternativedata" / "source"
    snapshot_source.mkdir(parents=True)
    (snapshot_source / "old.txt").write_text("old code", encoding="utf-8")
    old_assets = snapshot_source / "packages" / "client" / "dist" / "assets"
    old_assets.mkdir(parents=True)
    (old_assets / "old-hash.js").write_text("old asset", encoding="utf-8")
    metadata_path = deployments_dir / "deployments.json"
    write_json(
        metadata_path,
        [
            {
                "id": "deployment-1",
                "projectId": "project-1",
                "slug": "alternativedata",
                "provider": "local-legacy",
                "databaseMode": "persistent",
                "status": "published",
                "createdAt": "2026-04-09T16:40:02.705Z",
                "updatedAt": "2026-05-26T15:56:33.451Z",
                "publishedAt": "2026-05-26T15:56:33.451Z",
                "providerConfig": {"keep": "yes"},
                "providerState": {"entryUrl": "/deploy/alternativedata/"},
            }
        ],
    )
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(projects_dir))
    monkeypatch.delenv("HERMES_WEBUI_CLOUD_TERMINAL_API_BASE_URL", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("PROJECT_DEPLOYMENTS_DIR", raising=False)

    payload = core_deployments.redeploy_project_deployment(
        "project-1",
        {"confirm": "redeploy", "databaseMode": "persistent"},
    )

    operation = payload["operation"]
    assert operation["kind"] == "deployment.redeploy"
    assert operation["status"] == "succeeded"
    assert operation["result"]["delegated"] is False
    assert operation["result"]["coreSnapshot"] is True
    assert operation["result"]["build"]["skipped"] is False
    assert operation["result"]["snapshot"]["sourceFileCount"] >= 3
    assert (snapshot_source / "app.txt").read_text(encoding="utf-8") == "new code"
    assert (snapshot_source / "built.txt").read_text(encoding="utf-8") == "built via core"
    assert (snapshot_source / "packages" / "client" / "dist" / "assets" / "new-hash.js").read_text(encoding="utf-8") == "new asset"
    assert (snapshot_source / "packages" / "client" / "dist" / "assets" / "old-hash.js").read_text(encoding="utf-8") == "old asset"
    assert operation["result"]["snapshot"]["preservedAssets"]["preservedFileCount"] == 1
    assert not (snapshot_source / "old.txt").exists()
    assert not (snapshot_source / ".env").exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))[0]
    assert metadata["databaseMode"] == "persistent"
    assert metadata["providerConfig"] == {"keep": "yes"}
    assert metadata["providerState"] == {"entryUrl": "/deploy/alternativedata/"}
    assert metadata["status"] == "published"
    assert metadata["lastError"] is None
    assert metadata["updatedAt"] != "2026-05-26T15:56:33.451Z"
    assert payload["deployment"]["database"]["preservesExistingData"] is True


def test_core_deployment_redeploy_build_failure_leaves_snapshot_and_metadata_unchanged(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    repo = projects_dir / "repo"
    repo.mkdir(parents=True)
    (repo / "new.txt").write_text("new code", encoding="utf-8")
    write_json(
        repo / "project_play.json",
        {"build": {"command": "python3 -c \"import sys; print('bad build'); sys.exit(7)\"", "cwd": ".", "timeoutSeconds": 30}},
    )
    write_json(
        projects_dir / "projects.json",
        [{"id": "project-1", "name": "Alternative Data", "slug": "alternative-data", "path": str(repo), "coreBranch": "main"}],
    )
    deployments_dir = projects_dir / ".deployments"
    snapshot_source = deployments_dir / "items" / "alternativedata" / "source"
    snapshot_source.mkdir(parents=True)
    (snapshot_source / "old.txt").write_text("old code", encoding="utf-8")
    metadata_path = deployments_dir / "deployments.json"
    write_json(
        metadata_path,
        [{"id": "deployment-1", "projectId": "project-1", "slug": "alternativedata", "provider": "local-legacy", "databaseMode": "persistent", "status": "published", "providerConfig": {"keep": True}}],
    )
    before = metadata_path.read_text(encoding="utf-8")
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(projects_dir))
    monkeypatch.delenv("HERMES_WEBUI_CLOUD_TERMINAL_API_BASE_URL", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("PROJECT_DEPLOYMENTS_DIR", raising=False)

    with pytest.raises(core_deployments.CoreApiError) as excinfo:
        core_deployments.redeploy_project_deployment("project-1", {"confirm": "redeploy", "databaseMode": "persistent"})

    assert excinfo.value.code == "DEPLOYMENT_REDEPLOY_BUILD_FAILED"
    assert metadata_path.read_text(encoding="utf-8") == before
    assert (snapshot_source / "old.txt").read_text(encoding="utf-8") == "old code"
    assert not (snapshot_source / "new.txt").exists()


def test_core_deployment_local_legacy_start_installs_snapshot_dependencies_before_runtime(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    repo = projects_dir / "repo"
    repo.mkdir(parents=True)
    (repo / ".env").write_text("JWT_SECRET=dev-secret-key-must-be-long-1234567890\nAUTH_DEBUG_LOGIN=false\n", encoding="utf-8")
    snapshot_source = projects_dir / ".deployments" / "items" / "alternativedata" / "source"
    snapshot_source.mkdir(parents=True)
    write_json(snapshot_source / "package.json", {"packageManager": "pnpm@10.12.4"})
    write_json(
        snapshot_source / "project_play.json",
        {
            "start": {
                "command": "node server.js",
                "cwd": ".",
                "env": {"AUTH_DEBUG_LOGIN": "true"},
                "port": {"mode": "auto", "host": "127.0.0.1", "envVar": "PORT", "range": {"min": 24500, "max": 24510}},
            },
            "inspect": {"mode": "proxy", "url": "/", "readyTimeoutMs": 1000},
        },
    )
    project = {"id": "project-1", "name": "Alternative Data", "path": str(repo), "coreBranch": "main"}
    record = {"id": "deployment-1", "projectId": "project-1", "slug": "alternativedata", "provider": "local-legacy"}
    calls = []

    def fake_install(_project, _state, install_snapshot_path):
        calls.append(("install", str(install_snapshot_path)))
        return {"skipped": False, "command": "pnpm install --frozen-lockfile", "exitCode": 0}

    class FakeProc:
        pid = 12345
        stdout = io.StringIO("")
        stderr = io.StringIO("")

        def poll(self):
            return None

        def wait(self):
            return 0

    def fake_popen(*args, **kwargs):
        env = kwargs.get("env", {})
        calls.append(("popen", kwargs.get("cwd"), env.get("PORT"), env.get("JWT_SECRET"), env.get("AUTH_DEBUG_LOGIN")))
        return FakeProc()

    port_checks = []

    def fake_is_port_open(_host, port):
        port_checks.append(port)
        return len(port_checks) > 1

    monkeypatch.setattr(core_deployments, "_maybe_install_runtime_dependencies", fake_install)
    monkeypatch.setattr(core_deployments.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(core_deployments, "_is_port_open", fake_is_port_open)
    monkeypatch.setattr(core_deployments, "_stop_stale_deployment_runtime_processes", lambda *args, **kwargs: [])

    result = core_deployments._start_local_legacy_runtime(project, record, snapshot_source)

    assert calls[0] == ("install", str(snapshot_source))
    assert calls[1][0] == "popen"
    assert calls[1][1] == str(snapshot_source)
    assert calls[1][2] == "24500"
    assert calls[1][3] == "dev-secret-key-must-be-long-1234567890"
    assert calls[1][4] == "true"
    assert result["dependencies"]["command"] == "pnpm install --frozen-lockfile"


def test_core_deployment_stops_stale_runtime_processes_by_slug(monkeypatch):
    infos = [
        RuntimeProcessInfo(
            pid=101,
            cmdline="node packages/server/dist/packages/server/index.js",
            environ={"HERMES_DEPLOYMENT": "true", "HERMES_DEPLOYMENT_SLUG": "alternativedata"},
            pgid=101,
        ),
        RuntimeProcessInfo(
            pid=102,
            cmdline="node packages/server/dist/packages/server/index.js",
            environ={"HERMES_DEPLOYMENT": "true", "HERMES_DEPLOYMENT_SLUG": "alternativedata"},
            pgid=900,
        ),
        RuntimeProcessInfo(
            pid=103,
            cmdline="node packages/server/dist/packages/server/index.js",
            environ={"HERMES_DEPLOYMENT": "true", "HERMES_DEPLOYMENT_SLUG": "other"},
            pgid=103,
        ),
        RuntimeProcessInfo(
            pid=104,
            cmdline="node packages/server/dist/packages/server/index.js",
            environ={"HERMES_DEPLOYMENT": "false", "HERMES_DEPLOYMENT_SLUG": "alternativedata"},
            pgid=104,
        ),
    ]
    killed = []
    state = core_deployments._DeploymentRuntimeState(
        project_id="project-1",
        deployment_id="deployment-1",
        slug="alternativedata",
        snapshot_path="/tmp/snapshot",
    )

    monkeypatch.setattr(core_deployments, "iter_runtime_processes", lambda: iter(infos))
    monkeypatch.setattr(core_deployments, "terminate_process_group", lambda pid: killed.append(pid) or True)
    monkeypatch.setattr(core_deployments.os, "getpgid", lambda pid: 900 if pid == 999 else pid)
    monkeypatch.setattr(core_deployments, "_append_runtime_log", lambda *args, **kwargs: None)

    stopped = core_deployments._stop_stale_deployment_runtime_processes({"id": "project-1"}, state, keep_pid=999)

    assert stopped == [101]
    assert killed == [101]


def test_core_deployment_redeploy_uses_internal_service_token_for_loopback_provider(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    repo = projects_dir / "repo"
    repo.mkdir(parents=True)
    write_json(
        projects_dir / "projects.json",
        [{"id": "project-1", "name": "Alternative Data", "slug": "alternative-data", "path": str(repo), "coreBranch": "main"}],
    )
    write_json(
        projects_dir / ".deployments" / "deployments.json",
        [{"id": "deployment-1", "projectId": "project-1", "slug": "alternativedata", "provider": "container-local", "databaseMode": "persistent", "status": "published"}],
    )
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(projects_dir))
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_API_BASE_URL", "http://127.0.0.1:5999")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"updated":true,"deployment":{"status":"published"}}'

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = req.data
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(core_deployments.urlrequest, "urlopen", fake_urlopen)

    payload = core_deployments.redeploy_project_deployment(
        "project-1",
        {"confirm": "redeploy", "databaseMode": "persistent"},
    )

    assert captured["url"] == "http://127.0.0.1:5999/api/projects/project-1/deployment/update"
    assert captured["headers"]["Authorization"].startswith("Bearer ")
    assert captured["headers"]["X-session-token"] in captured["headers"]["Authorization"]
    assert captured["headers"]["X-cloud-terminal-internal"] == "hermes-core"
    assert json.loads(captured["body"].decode("utf-8"))["databaseMode"] == "persistent"
    assert payload["operation"]["kind"] == "deployment.redeploy"
    assert payload["operation"]["result"]["delegated"] is True


def test_core_deployment_redeploy_delegates_with_cloud_terminal_session_token(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    repo = projects_dir / "repo"
    repo.mkdir(parents=True)
    write_json(
        projects_dir / "projects.json",
        [{"id": "project-1", "name": "Alternative Data", "slug": "alternative-data", "path": str(repo), "coreBranch": "main"}],
    )
    write_json(
        projects_dir / ".deployments" / "deployments.json",
        [{"id": "deployment-1", "projectId": "project-1", "slug": "alternativedata", "provider": "container-local", "databaseMode": "persistent", "status": "published"}],
    )
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(projects_dir))
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_API_BASE_URL", "http://127.0.0.1:5999")
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"updated":true,"deployment":{"status":"published"}}'

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = req.data
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(core_deployments.urlrequest, "urlopen", fake_urlopen)

    payload = core_deployments.redeploy_project_deployment(
        "project-1",
        {"confirm": "redeploy", "databaseMode": "persistent"},
        request_headers={"X-Session-Token": "ct-token"},
    )

    assert captured["url"] == "http://127.0.0.1:5999/api/projects/project-1/deployment/update"
    assert captured["headers"]["X-session-token"] == "ct-token"
    assert json.loads(captured["body"].decode("utf-8"))["databaseMode"] == "persistent"
    assert payload["operation"]["result"]["delegated"] is True


def test_core_deployment_redeploy_rejects_database_mode_changes(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    repo = projects_dir / "repo"
    repo.mkdir(parents=True)
    write_json(
        projects_dir / "projects.json",
        [{"id": "project-1", "name": "Alternative Data", "slug": "alternative-data", "path": str(repo), "coreBranch": "main"}],
    )
    write_json(
        projects_dir / ".deployments" / "deployments.json",
        [{"id": "deployment-1", "projectId": "project-1", "slug": "alternativedata", "provider": "local-legacy", "databaseMode": "persistent", "status": "published"}],
    )
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(projects_dir))
    monkeypatch.delenv("PROJECT_DEPLOYMENTS_DIR", raising=False)

    with pytest.raises(core_deployments.CoreApiError) as excinfo:
        core_deployments.redeploy_project_deployment("project-1", {"confirm": "redeploy", "databaseMode": "empty"})

    assert excinfo.value.code == "DEPLOYMENT_DATABASE_MODE_CHANGE_REJECTED"


def test_core_deployment_record_rejects_redeploy_reserved_action(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    repo = projects_dir / "repo"
    repo.mkdir(parents=True)
    write_json(
        projects_dir / "projects.json",
        [{"id": "project-1", "name": "Alternative Data", "slug": "alternative-data", "path": str(repo), "coreBranch": "main"}],
    )
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(projects_dir))

    with pytest.raises(core_deployments.CoreApiError) as excinfo:
        core_deployments.record_project_deployment("project-1", {"provider": "manual"}, action="redeploy")

    assert excinfo.value.code == "DEPLOYMENT_REDEPLOY_RESERVED_ACTION"
    assert not (repo / ".hermes" / "ops" / "deployments" / "deployment.json").exists()


def test_core_deployment_provider_registry_marks_cloud_terminal_redeploy_capability():
    providers = {provider["id"]: provider for provider in core_deployments.provider_registry()["providers"]}

    assert providers["local-legacy"]["capabilities"]["redeploy"] is True
    assert providers["local-legacy"]["capabilities"]["preservesDatabase"] is True


def test_deployment_compatibility_post_routes_before_csrf(monkeypatch):
    calls = []

    def fake_proxy(handler, parsed, *, method="GET"):
        calls.append((parsed.path, parsed.query, method))
        handler.send_response(204)
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return True

    monkeypatch.setattr(core_deployments, "handle_deployment_compatibility_proxy_request", fake_proxy)
    handler = DummyHandler(
        "POST",
        headers={
            "Origin": "https://hermes.example.test",
            "Referer": "https://hermes.example.test/deploy/alternativedata/login",
            "Host": "hermes.example.test",
            "Content-Type": "application/json",
            "Content-Length": "11",
        },
        body=b'{"ok":true}',
    )

    assert routes.handle_post(handler, urlparse("/api/trpc/auth.signup?batch=1")) is True

    assert calls == [("/api/trpc/auth.signup", "batch=1", "POST")]
    assert handler.status == 204


def test_deployment_compatibility_auth_bypass_uses_referer_or_cookie_context():
    referer_handler = DummyHandler(
        headers={"Referer": "https://hermes.example.test/deploy/alternativedata/login"},
    )
    cookie_handler = DummyHandler(
        headers={"Cookie": "__ct_deployment=alternativedata; other=1"},
    )
    no_context_handler = DummyHandler(headers={})
    parsed = urlparse("/api/trpc/auth.login?batch=1")

    assert core_deployments.is_deployment_public_request(referer_handler, parsed) is True
    assert core_deployments.is_deployment_public_request(cookie_handler, parsed) is True
    assert auth.check_auth(referer_handler, parsed) is True
    assert core_deployments.is_deployment_public_request(no_context_handler, parsed) is False


def test_deployment_compatibility_claims_only_known_app_api_paths():
    handler = DummyHandler(headers={"Cookie": "__hermes_deployment=alternativedata"})

    for path in (
        "/api/blob/media/avatar.png",
        "/api/nakama/realtime-debug-gather",
        "/api/trpc/auth.me?batch=1",
        "/assets/index.js",
    ):
        parsed = urlparse(path)

        assert core_deployments.is_deployment_public_request(handler, parsed) is True

    for path in (
        "/api",
        "/api/auth/login",
        "/api/chat/start",
        "/api/core/projects/project-1/deployment",
        "/api/models",
        "/api/ops/notifications/dismissed",
        "/api/projects",
        "/api/session/new",
        "/api/session/status",
        "/api/sessions/activity",
    ):
        parsed = urlparse(path)

        assert core_deployments.is_deployment_public_request(handler, parsed) is False
        assert core_deployments.handle_deployment_compatibility_proxy_request(handler, parsed) is False


def test_deployment_compatibility_proxy_forwards_raw_auth_body(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    repo = projects_dir / "repo"
    repo.mkdir(parents=True)
    write_json(
        projects_dir / "projects.json",
        [{"id": "project-1", "name": "Alternative Data", "slug": "alternative-data", "path": str(repo), "coreBranch": "main"}],
    )
    deployments_dir = projects_dir / ".deployments"
    snapshot_source = deployments_dir / "items" / "alternativedata" / "source"
    snapshot_source.mkdir(parents=True)
    write_json(
        deployments_dir / "deployments.json",
        [{"id": "deployment-1", "projectId": "project-1", "slug": "alternativedata", "provider": "local-legacy", "databaseMode": "persistent", "status": "published"}],
    )
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(projects_dir))
    monkeypatch.delenv("PROJECT_DEPLOYMENTS_DIR", raising=False)

    class FakeProc:
        def poll(self):
            return None

    state = core_deployments._DeploymentRuntimeState(
        project_id="project-1",
        deployment_id="deployment-1",
        slug="alternativedata",
        snapshot_path=str(snapshot_source),
        host="127.0.0.1",
        port=27654,
        running=True,
        ready=True,
        public_base_path="/deploy/alternativedata",
        public_path="/deploy/alternativedata/",
        public_entry_path="/deploy/alternativedata/app",
        inspect_path="/app",
    )
    state.process = FakeProc()  # type: ignore[assignment]
    monkeypatch.setattr(core_deployments, "_DEPLOYMENT_RUNTIMES", {"project-1": state})
    captured = {}

    class FakeResponse:
        status = 200

        def __init__(self):
            self.headers = Message()
            self.headers.add_header("Content-Type", "application/json")

        def read(self):
            return b'{"ok":true}'

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = req.data
        captured["headers"] = dict(req.header_items())
        return FakeResponse()

    monkeypatch.setattr(core_deployments.urlrequest, "urlopen", fake_urlopen)
    raw_body = b'{"json":{"username":"debug","password":"password123"}}'
    handler = DummyHandler(
        "POST",
        headers={
            "Referer": "https://hermes.example.test/deploy/alternativedata/login",
            "Content-Type": "application/json",
            "Content-Length": str(len(raw_body)),
        },
        body=raw_body,
    )

    assert core_deployments.handle_deployment_compatibility_proxy_request(
        handler,
        urlparse("/api/trpc/auth.signup?batch=1"),
        method="POST",
    ) is True

    assert captured["url"] == "http://127.0.0.1:27654/api/trpc/auth.signup?batch=1"
    assert captured["body"] == raw_body
    assert handler.status == 200
    assert ("Set-Cookie", "__hermes_deployment=alternativedata; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800") in handler.response_headers
    assert handler.wfile.getvalue() == b'{"ok":true}'

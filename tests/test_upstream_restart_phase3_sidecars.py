import json
from pathlib import Path
import shutil
import subprocess
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


def init_project_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "sidecar-project"
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    run_git(repo, "checkout", "-b", "feature/sidecars")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "initial")
    return repo


def test_phase3_sidecar_linkage_does_not_pollute_core_session_json(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)

    from api import ops_projects, session_sidecars
    from api.models import Session

    project = ops_projects.create_ops_project({"name": "Sidecar Project", "path": str(repo), "coreBranch": "main"})
    epic_id = ops_projects.add_ops_project_epic(project["id"], "Quick tasks")["epic"]["id"]
    task = ops_projects.add_ops_project_task(
        project["id"],
        epic_id,
        "Attach an existing Hermes session",
        markers=["phase-3"],
    )["task"]

    session = Session(session_id="sesslink123", title="Linked session", messages=[{"role": "user", "content": "hello"}])
    session.save()

    linkage = session_sidecars.set_session_linkage(session.session_id, project["id"], task["id"], run_id="run-1")

    assert linkage["projectId"] == project["id"]
    assert linkage["taskId"] == task["id"]
    assert linkage["runId"] == "run-1"
    assert linkage["session"]["title"] == "Linked session"

    raw_session = json.loads(session.path.read_text(encoding="utf-8"))
    assert "projectId" not in raw_session
    assert "taskId" not in raw_session
    assert "runId" not in raw_session
    assert "linkedAt" not in raw_session
    assert "updatedAt" not in raw_session

    tasks_payload = ops_projects.read_ops_project_tasks(project["id"])
    linked_task = next(epic["tasks"][0] for epic in tasks_payload["epics"] if epic["id"] == epic_id)
    assert linked_task["linkedSessions"][0]["session"]["title"] == "Linked session"
    assert linked_task["linkedSessions"][0]["sessionId"] == "sesslink123"


def test_phase3_linked_session_state_is_visible_through_ops_route(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)

    from api.routes import handle_get
    from api import ops_projects, session_sidecars
    from api.models import Session
    from tests.test_upstream_restart_phase2_projects import _FakeHandler, _response_json

    project = ops_projects.create_ops_project({"name": "Route Sidecar Project", "path": str(repo), "coreBranch": "main"})
    epic_id = ops_projects.add_ops_project_epic(project["id"], "Quick tasks")["epic"]["id"]
    task = ops_projects.add_ops_project_task(project["id"], epic_id, "Show linked session state")["task"]
    session = Session(session_id="sessroute123", title="Route-linked session", messages=[{"role": "user", "content": "hello"}])
    session.save()
    session_sidecars.set_session_linkage(session.session_id, project["id"], task["id"])

    handler = _FakeHandler()
    assert handle_get(handler, urlparse(f"http://example.com/api/ops/projects/{project['id']}/tasks")) is True
    payload = _response_json(handler)
    linked_task = next(epic["tasks"][0] for epic in payload["epics"] if epic["id"] == epic_id)
    assert linked_task["linkedSessions"][0]["session"]["title"] == "Route-linked session"


def test_phase3_invalid_sidecar_fails_closed(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)

    from api import ops_projects
    from api.config import STATE_DIR

    project = ops_projects.create_ops_project({"name": "Fail Closed Project", "path": str(repo), "coreBranch": "main"})
    epic_id = ops_projects.add_ops_project_epic(project["id"], "Quick tasks")["epic"]["id"]
    ops_projects.add_ops_project_task(project["id"], epic_id, "Keep task loading when sidecar is corrupt")

    sidecar_dir = STATE_DIR / "ops" / "session-links"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    (sidecar_dir / "broken123.json").write_text("{not json", encoding="utf-8")

    payload = ops_projects.read_ops_project_tasks(project["id"])
    assert payload["epics"][0]["tasks"][0]["text"] == "Keep task loading when sidecar is corrupt"
    assert payload["epics"][0]["tasks"][0]["linkedSessions"] == []


def test_phase3_project_linkage_records_use_sidecar_index(monkeypatch, tmp_path):
    from api import session_sidecars

    sidecar_dir = tmp_path / "session-links"
    sidecar_dir.mkdir()
    monkeypatch.setattr(session_sidecars, "_sidecar_dir", lambda: sidecar_dir)
    session_sidecars._invalidate_sidecar_index()
    for index in range(6):
        project_id = "project-1" if index % 2 == 0 else "project-2"
        (sidecar_dir / f"session{index}.json").write_text(
            json.dumps(
                {
                    "sessionId": f"session{index}",
                    "projectId": project_id,
                    "taskId": f"task-{index}",
                    "linkedAt": f"2026-05-06T00:00:0{index}.000Z",
                    "updatedAt": f"2026-05-06T00:00:0{index}.000Z",
                }
            ),
            encoding="utf-8",
        )

    original_read_json = session_sidecars._read_json
    read_calls = []

    def counted_read_json(path):
        read_calls.append(path.name)
        return original_read_json(path)

    monkeypatch.setattr(session_sidecars, "_read_json", counted_read_json)

    first = session_sidecars.list_project_linkage_records("project-1")
    second = session_sidecars.list_project_linkage_records("project-1")

    assert [record["sessionId"] for record in first] == ["session4", "session2", "session0"]
    assert second == first
    assert len(read_calls) == 6

    (sidecar_dir / "session6.json").write_text(
        json.dumps(
            {
                "sessionId": "session6",
                "projectId": "project-1",
                "taskId": "task-6",
                "linkedAt": "2026-05-06T00:00:06.000Z",
                "updatedAt": "2026-05-06T00:00:06.000Z",
            }
        ),
        encoding="utf-8",
    )
    updated = session_sidecars.list_project_linkage_records("project-1")

    assert updated[0]["sessionId"] == "session6"
    assert len(updated) == 4
    assert len(read_calls) == 13


def test_phase3_project_linkages_resolve_sessions_in_bulk(monkeypatch, tmp_path):
    from api import session_sidecars

    sidecar_dir = tmp_path / "session-links"
    sidecar_dir.mkdir()
    monkeypatch.setattr(session_sidecars, "_sidecar_dir", lambda: sidecar_dir)
    session_sidecars._invalidate_sidecar_index()
    for index in range(5):
        (sidecar_dir / f"bulksess{index}.json").write_text(
            json.dumps(
                {
                    "sessionId": f"bulksess{index}",
                    "projectId": "project-1",
                    "taskId": f"task-{index}",
                    "linkedAt": f"2026-05-06T00:00:0{index}.000Z",
                    "updatedAt": f"2026-05-06T00:00:0{index}.000Z",
                }
            ),
            encoding="utf-8",
        )

    all_sessions_calls = {"count": 0}

    def fake_all_sessions():
        all_sessions_calls["count"] += 1
        return [
            {
                "session_id": f"bulksess{index}",
                "title": f"Bulk Session {index}",
                "message_count": 1,
                "created_at": float(index),
                "updated_at": float(index),
                "last_message_at": float(index),
                "archived": False,
            }
            for index in range(5)
        ]

    monkeypatch.setattr(session_sidecars, "all_sessions", fake_all_sessions)
    monkeypatch.setattr(
        session_sidecars,
        "_session_summary",
        lambda _sid: (_ for _ in ()).throw(AssertionError("per-linkage session load should not run")),
    )

    linkages = session_sidecars.list_project_linkages("project-1")

    assert all_sessions_calls["count"] == 1
    assert len(linkages) == 5
    assert {linkage["session"]["title"] for linkage in linkages} == {
        f"Bulk Session {index}" for index in range(5)
    }


def test_phase3_sidecar_linkage_resolves_latest_lineage_tip(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)

    from api import ops_projects, session_sidecars
    from api.models import Session

    project = ops_projects.create_ops_project({"name": "Lineage Project", "path": str(repo), "coreBranch": "main"})
    epic_id = ops_projects.add_ops_project_epic(project["id"], "Quick tasks")["epic"]["id"]
    task = ops_projects.add_ops_project_task(project["id"], epic_id, "Follow the latest session tip")["task"]

    root_session = Session(session_id="rootsess12345", title="Root session", workspace=str(repo), messages=[{"role": "user", "content": "hello"}])
    root_session.save()
    session_sidecars.set_session_linkage(root_session.session_id, project["id"], task["id"], run_id="run-tip")

    monkeypatch.setattr(
        session_sidecars,
        "all_sessions",
        lambda: [
            {
                "session_id": "tipsess67890",
                "title": "Tip session",
                "workspace": str(repo),
                "message_count": 3,
                "created_at": root_session.created_at,
                "updated_at": root_session.updated_at + 50,
                "last_message_at": root_session.updated_at + 50,
                "pinned": False,
                "archived": False,
                "project_id": None,
                "profile": "default",
                "active_stream_id": None,
                "pending_user_message": None,
                "has_pending_user_message": False,
                "is_cli_session": False,
                "source_tag": "ops_task",
                "raw_source": None,
                "session_source": None,
                "source_label": "Ops task",
                "enabled_toolsets": None,
                "is_streaming": False,
                "_lineage_root_id": root_session.session_id,
                "_lineage_tip_id": "tipsess67890",
            }
        ],
    )

    linkage = session_sidecars.get_session_linkage(root_session.session_id)
    assert linkage["linkedSessionId"] == root_session.session_id
    assert linkage["sessionId"] == "tipsess67890"
    assert linkage["lineageRootId"] == root_session.session_id
    assert linkage["lineageTipId"] == "tipsess67890"
    assert linkage["session"]["title"] == "Tip session"

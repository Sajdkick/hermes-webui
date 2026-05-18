from types import SimpleNamespace

from api import ops_sessions, session_sidecars


class FakeSession(SimpleNamespace):
    def compact(self):
        return {
            "session_id": self.session_id,
            "source_tag": self.source_tag,
            "archived": self.archived,
            "updated_at": getattr(self, "updated_at", 0),
            "last_message_at": getattr(self, "last_message_at", 0),
        }

    def save(self, touch_updated_at=True):
        self.saved = True
        self.saved_touch_updated_at = touch_updated_at


def test_ops_task_activity_dedupe_uses_enriched_project_task_metadata():
    sessions = [
        {
            "session_id": "older",
            "projectId": "project-1",
            "opsTaskId": "task-1",
            "updated_at": 1,
            "lastActivityAt": 1,
        },
        {
            "session_id": "newer",
            "projectId": "project-1",
            "opsTaskId": "task-1",
            "updated_at": 2,
            "lastActivityAt": 2,
        },
    ]

    deduped = ops_sessions._dedupe_ops_task_sessions(sessions)

    assert [session["session_id"] for session in deduped] == ["newer"]


def test_ops_task_activity_dedupe_prefers_continuation_tip_over_touched_root():
    sessions = [
        {
            "session_id": "7f8bfd8c4867",
            "projectId": "project-1",
            "opsTaskId": "task-1",
            "updated_at": 1778997597.1959627,
            "last_message_at": 1778951380.0,
            "lastActivityAt": 1778961190.045,
            "message_count": 554,
        },
        {
            "session_id": "20260516_171951_c84dbb",
            "projectId": "project-1",
            "opsTaskId": "task-1",
            "updated_at": 1778961190.0457518,
            "last_message_at": 1778961190.0,
            "lastActivityAt": 1778961190.045,
            "message_count": 904,
            "parent_session_id": "7f8bfd8c4867",
        },
    ]

    deduped = ops_sessions._dedupe_ops_task_sessions(sessions)

    assert [session["session_id"] for session in deduped] == ["20260516_171951_c84dbb"]


def test_find_existing_task_session_falls_back_to_task_linked_sessions(monkeypatch):
    session = FakeSession(
        session_id="session_1",
        source_tag=ops_sessions.OPS_TASK_SOURCE_TAG,
        archived=False,
        active_stream_id=None,
        pending_user_message=None,
        updated_at=2,
    )
    monkeypatch.setattr(ops_sessions.session_sidecars, "task_linkage_map", lambda _project_id: {})
    monkeypatch.setattr(
        ops_sessions.ops_projects,
        "get_ops_project_task",
        lambda project_id, task_id: {
            "task": {
                "id": task_id,
                "linkedSessions": [
                    {"sessionId": "session_1", "projectId": project_id, "taskId": task_id, "runId": "run-1"}
                ],
            }
        },
    )
    monkeypatch.setattr(ops_sessions, "get_session", lambda session_id: session if session_id == "session_1" else None)

    existing = ops_sessions._find_existing_task_session("project-1", "task-1")

    assert existing is not None
    assert existing["session"].session_id == "session_1"
    assert existing["linkage"]["runId"] == "run-1"


def test_sidecar_resolution_prefers_archived_latest_tip_over_visible_old_sibling(monkeypatch):
    root = {
        "session_id": "root",
        "archived": False,
        "updated_at": 30,
        "last_message_at": 30,
        "message_count": 10,
    }
    old_sibling = {
        "session_id": "old_child",
        "parent_session_id": "root",
        "_lineage_root_id": "root",
        "archived": False,
        "updated_at": 300,
        "last_message_at": 100,
        "message_count": 20,
    }
    latest_tip = {
        "session_id": "latest_child",
        "parent_session_id": "root",
        "_lineage_root_id": "root",
        "archived": True,
        "updated_at": 200,
        "last_message_at": 200,
        "message_count": 40,
    }

    monkeypatch.setattr(session_sidecars, "_session_summary", lambda sid: root if sid == "root" else None)
    monkeypatch.setattr(session_sidecars, "all_sessions", lambda: [root, old_sibling, latest_tip])

    summary = session_sidecars.resolve_session_summary("root")

    assert summary["session_id"] == "latest_child"


def test_find_existing_task_session_allows_archived_tip_for_relaunch(monkeypatch):
    archived_tip = FakeSession(
        session_id="latest_child",
        source_tag=ops_sessions.OPS_TASK_SOURCE_TAG,
        archived=True,
        active_stream_id=None,
        pending_user_message=None,
        updated_at=20,
        last_message_at=20,
    )
    monkeypatch.setattr(
        ops_sessions.session_sidecars,
        "task_linkage_map",
        lambda _project_id: {
            "task-1": [
                {
                    "sessionId": "latest_child",
                    "linkedSessionId": "root",
                    "projectId": "project-1",
                    "taskId": "task-1",
                    "session": {"session_id": "latest_child", "archived": True},
                }
            ]
        },
    )
    monkeypatch.setattr(
        ops_sessions.ops_projects,
        "get_ops_project_task",
        lambda project_id, task_id: {"task": {"id": task_id, "linkedSessions": []}},
    )
    monkeypatch.setattr(ops_sessions, "get_session", lambda session_id: archived_tip if session_id == "latest_child" else None)

    existing = ops_sessions._find_existing_task_session("project-1", "task-1")

    assert existing is not None
    assert existing["session"].session_id == "latest_child"

def test_close_task_session_archives_requested_lineage_tip_when_task_linkage_is_stale(monkeypatch):
    task = {
        "id": "task-1",
        "linkedSessions": [{"sessionId": "root", "linkedSessionId": "root"}],
    }
    root = FakeSession(
        session_id="root",
        source_tag=ops_sessions.OPS_TASK_SOURCE_TAG,
        archived=False,
        active_stream_id=None,
        pending_user_message=None,
    )
    tip = FakeSession(
        session_id="tip",
        source_tag=ops_sessions.OPS_TASK_SOURCE_TAG,
        archived=False,
        active_stream_id=None,
        pending_user_message=None,
    )

    monkeypatch.setattr(
        ops_sessions.ops_projects,
        "read_ops_project_tasks",
        lambda project_id: {"epics": [{"tasks": [task]}]},
    )
    monkeypatch.setattr(
        ops_sessions.session_sidecars,
        "resolve_session_id",
        lambda session_id: "tip" if session_id in {"root", "tip"} else None,
    )
    monkeypatch.setattr(
        ops_sessions,
        "get_session",
        lambda session_id: {"root": root, "tip": tip}[session_id],
    )

    def update_task(project_id, task_id, patch):
        task.update(patch)
        return {"task": task}

    monkeypatch.setattr(ops_sessions.ops_projects, "update_ops_project_task", update_task)
    monkeypatch.setattr(ops_sessions.ops_projects, "_now_iso", lambda: "2026-05-17T00:00:00Z")

    result = ops_sessions.close_task_session("project-1", "task-1", {"sessionId": "tip"})

    assert result["sessionId"] == "tip"
    assert tip.archived is True
    assert getattr(tip, "saved", False) is True
    assert root.archived is False
    assert task["inProgress"] is False
    assert task["sessionId"] == ""

def test_close_task_session_archives_requested_visible_root_when_resolver_prefers_archived_tip(monkeypatch):
    task = {
        "id": "task-1",
        "linkedSessions": [
            {
                "sessionId": "tip",
                "linkedSessionId": "root",
                "session": {"session_id": "tip", "parent_session_id": "root", "archived": True},
                "runId": "run-1",
            }
        ],
    }
    root = FakeSession(
        session_id="root",
        source_tag=ops_sessions.OPS_TASK_SOURCE_TAG,
        archived=False,
        active_stream_id=None,
        pending_user_message=None,
    )
    tip = FakeSession(
        session_id="tip",
        source_tag=ops_sessions.OPS_TASK_SOURCE_TAG,
        archived=True,
        active_stream_id=None,
        pending_user_message=None,
    )

    monkeypatch.setattr(
        ops_sessions.ops_projects,
        "read_ops_project_tasks",
        lambda project_id: {"epics": [{"tasks": [task]}]},
    )
    monkeypatch.setattr(
        ops_sessions.session_sidecars,
        "resolve_session_summary",
        lambda session_id: {"session_id": "tip", "parent_session_id": "root"} if session_id == "root" else None,
    )
    monkeypatch.setattr(
        ops_sessions.session_sidecars,
        "resolve_session_id",
        lambda session_id: "tip" if session_id == "root" else session_id,
    )
    monkeypatch.setattr(
        ops_sessions,
        "all_sessions",
        lambda: [
            {
                "session_id": "root",
                "source_tag": ops_sessions.OPS_TASK_SOURCE_TAG,
                "project_id": "project-1",
                "archived": False,
            },
            {
                "session_id": "tip",
                "parent_session_id": "root",
                "source_tag": ops_sessions.OPS_TASK_SOURCE_TAG,
                "project_id": "project-1",
                "archived": True,
            },
        ],
    )
    monkeypatch.setattr(ops_sessions, "get_session", lambda session_id: {"root": root, "tip": tip}[session_id])

    def update_task(project_id, task_id, patch):
        task.update(patch)
        return {"task": task}

    monkeypatch.setattr(ops_sessions.ops_projects, "update_ops_project_task", update_task)
    monkeypatch.setattr(ops_sessions.ops_projects, "_now_iso", lambda: "2026-05-17T00:00:00Z")

    result = ops_sessions.close_task_session("project-1", "task-1", {"sessionId": "root"})

    assert result["sessionId"] == "root"
    assert result["closedSessionIds"] == ["root", "tip"]
    assert root.archived is True
    assert tip.archived is True
    assert getattr(root, "saved", False) is True


def test_close_task_session_archives_stale_visible_siblings_for_same_task(monkeypatch):
    task = {
        "id": "task-1",
        "linkedSessions": [
            {
                "sessionId": "current-tip",
                "linkedSessionId": "root",
                "session": {"session_id": "current-tip", "parent_session_id": "root", "archived": True},
                "runId": "run-1",
            }
        ],
    }
    root = FakeSession(
        session_id="root",
        source_tag=ops_sessions.OPS_TASK_SOURCE_TAG,
        archived=False,
        active_stream_id=None,
        pending_user_message=None,
    )
    clicked_child = FakeSession(
        session_id="clicked_child",
        source_tag=ops_sessions.OPS_TASK_SOURCE_TAG,
        archived=False,
        active_stream_id=None,
        pending_user_message=None,
    )
    stale_sibling = FakeSession(
        session_id="stale_sibling",
        source_tag=ops_sessions.OPS_TASK_SOURCE_TAG,
        archived=False,
        active_stream_id=None,
        pending_user_message=None,
    )
    current_tip = FakeSession(
        session_id="current-tip",
        source_tag=ops_sessions.OPS_TASK_SOURCE_TAG,
        archived=True,
        active_stream_id=None,
        pending_user_message=None,
    )

    monkeypatch.setattr(
        ops_sessions.ops_projects,
        "read_ops_project_tasks",
        lambda project_id: {"epics": [{"tasks": [task]}]},
    )
    monkeypatch.setattr(ops_sessions.session_sidecars, "resolve_session_summary", lambda session_id: None)
    monkeypatch.setattr(ops_sessions.session_sidecars, "resolve_session_id", lambda session_id: session_id)
    monkeypatch.setattr(
        ops_sessions,
        "all_sessions",
        lambda: [
            {
                "session_id": "root",
                "source_tag": ops_sessions.OPS_TASK_SOURCE_TAG,
                "project_id": "project-1",
                "archived": False,
            },
            {
                "session_id": "clicked_child",
                "parent_session_id": "root",
                "source_tag": ops_sessions.OPS_TASK_SOURCE_TAG,
                "project_id": "project-1",
                "archived": False,
            },
            {
                "session_id": "stale_sibling",
                "parent_session_id": "root",
                "source_tag": ops_sessions.OPS_TASK_SOURCE_TAG,
                "project_id": "project-1",
                "archived": False,
            },
        ],
    )
    sessions = {
        "root": root,
        "clicked_child": clicked_child,
        "stale_sibling": stale_sibling,
        "current-tip": current_tip,
    }
    monkeypatch.setattr(ops_sessions, "get_session", lambda session_id: sessions[session_id])

    def update_task(project_id, task_id, patch):
        task.update(patch)
        return {"task": task}

    run_updates = []

    def update_run(run_id, patch):
        run_updates.append((run_id, patch))
        return {"id": run_id, **patch}

    from api import ops_runs

    monkeypatch.setattr(ops_sessions.ops_projects, "update_ops_project_task", update_task)
    monkeypatch.setattr(ops_sessions.ops_projects, "_now_iso", lambda: "2026-05-17T00:00:00Z")
    monkeypatch.setattr(ops_runs, "update_ops_run", update_run)

    result = ops_sessions.close_task_session("project-1", "task-1", {"sessionId": "clicked_child"})

    assert result["sessionId"] == "clicked_child"
    assert result["closedSessionIds"] == ["clicked_child", "current-tip", "root", "stale_sibling"]
    assert clicked_child.archived is True
    assert stale_sibling.archived is True
    assert root.archived is True
    assert current_tip.archived is True
    assert task["inProgress"] is False
    assert task["sessionId"] == ""
    assert run_updates and run_updates[0][0] == "run-1"


from api import session_activity


def _patch_activity_source(monkeypatch, sessions):
    monkeypatch.setattr(session_activity, "_read_state", lambda: {"groups": [], "assignments": []})
    monkeypatch.setattr(session_activity, "_list_ops_activity_source", lambda *args, **kwargs: {"sessions": sessions})


def test_session_activity_hides_stale_pending_untitled_sidecars(monkeypatch):
    _patch_activity_source(
        monkeypatch,
        [
            {
                "session_id": "stale_first_turn",
                "title": "Untitled",
                "active_stream_id": "stream-replayable",
                "pending_user_message": "resume",
                "is_streaming": False,
                "updated_at": 100,
            }
        ],
    )

    payload = session_activity.list_session_activity()

    assert payload["sessionCount"] == 0
    assert payload["sessions"] == []


def test_session_activity_keeps_durable_running_ops_task_without_live_stream(monkeypatch):
    _patch_activity_source(
        monkeypatch,
        [
            {
                "session_id": "ops_task_session",
                "title": "Project: Fix the dashboard",
                "is_streaming": False,
                "updated_at": 200,
                "ops_project_id": "project-1",
                "repositoryLabel": "Repo",
                "ops_task": {"id": "task-1", "text": "Fix the dashboard"},
                "ops_run": {"id": "run-1", "status": "running"},
            }
        ],
    )

    payload = session_activity.list_session_activity()

    assert payload["sessionCount"] == 1
    [item] = payload["sessions"]
    assert item["id"] == "ops_task_session"
    assert item["label"] == "Fix the dashboard"
    assert item["taskText"] == "Fix the dashboard"
    assert item["activityStatus"]["key"] == "active"


def test_session_activity_keeps_live_non_ops_stream(monkeypatch):
    _patch_activity_source(
        monkeypatch,
        [
            {
                "session_id": "live_general_session",
                "title": "Untitled",
                "active_stream_id": "live-stream",
                "pending_user_message": "hello",
                "is_streaming": True,
                "updated_at": 300,
            }
        ],
    )

    payload = session_activity.list_session_activity()

    assert payload["sessionCount"] == 1
    [item] = payload["sessions"]
    assert item["id"] == "live_general_session"
    assert item["activityStatus"]["key"] == "active"
    assert item["activityStatus"]["labelText"] == "Codex is working"


def test_session_activity_uses_lean_source_not_rich_ops_sessions(monkeypatch):
    calls = []
    rich_calls = []
    monkeypatch.setattr(session_activity, "_read_state", lambda: {"groups": [], "assignments": []})

    def lean_source():
        calls.append("lean")
        return {"sessions": []}

    def rich_source(*args, **kwargs):
        rich_calls.append("rich")
        return {"sessions": [{"session_id": "should-not-load", "ops_run": {"status": "running"}}]}

    monkeypatch.setattr(session_activity, "_lean_activity_source", lean_source)
    monkeypatch.setattr(session_activity.ops_sessions, "list_ops_sessions", rich_source)

    payload = session_activity.list_session_activity()

    assert payload["sessionCount"] == 0
    assert calls == ["lean"]
    assert rich_calls == []


def test_session_activity_allows_explicit_rich_fallback_for_debug(monkeypatch):
    calls = []
    rich_calls = []
    monkeypatch.setattr(session_activity, "_read_state", lambda: {"groups": [], "assignments": []})

    def lean_source():
        calls.append("lean")
        return {"sessions": []}

    def rich_source(*args, **kwargs):
        rich_calls.append("rich")
        return {
            "sessions": [
                {
                    "session_id": "rich-session",
                    "ops_run": {"status": "running"},
                    "updated_at": 123,
                }
            ]
        }

    monkeypatch.setattr(session_activity, "_lean_activity_source", lean_source)
    monkeypatch.setattr(session_activity.ops_sessions, "list_ops_sessions", rich_source)

    payload = session_activity.list_session_activity(allow_rich_fallback=True)

    assert payload["sessionCount"] == 1
    assert payload["sessions"][0]["id"] == "rich-session"
    assert calls == ["lean"]
    assert rich_calls == ["rich"]


def test_session_activity_falls_back_to_rich_source_when_lean_source_errors(monkeypatch):
    rich_calls = []
    monkeypatch.setattr(session_activity, "_read_state", lambda: {"groups": [], "assignments": []})
    monkeypatch.setattr(
        session_activity,
        "_lean_activity_source",
        lambda: (_ for _ in ()).throw(RuntimeError("lean source unavailable")),
    )

    def rich_source(*args, **kwargs):
        rich_calls.append("rich")
        return {
            "sessions": [
                {
                    "session_id": "fallback-session",
                    "ops_run": {"status": "running"},
                    "updated_at": 456,
                }
            ]
        }

    monkeypatch.setattr(session_activity.ops_sessions, "list_ops_sessions", rich_source)

    payload = session_activity.list_session_activity()

    assert payload["sessionCount"] == 1
    assert payload["sessions"][0]["id"] == "fallback-session"
    assert rich_calls == ["rich"]


def test_lean_activity_source_uses_raw_indexes_without_rich_ops_calls(monkeypatch, tmp_path):
    from api import ops_projects, ops_sessions

    workspace = tmp_path / "hermes"
    workspace.mkdir()
    project = {
        "id": "project-1",
        "name": "Hermes",
        "fullName": "Hermes WebUI",
        "path": str(workspace),
        "coreBranch": "master",
    }
    monkeypatch.setattr(
        session_activity,
        "all_sessions",
        lambda: [
            {
                "session_id": "active_1",
                "_lineage_root_id": "active_1",
                "title": "Hermes: Speed up active sessions",
                "workspace": str(workspace),
                "source_tag": ops_sessions.OPS_TASK_SOURCE_TAG,
                "is_streaming": False,
                "message_count": 2,
                "created_at": 100,
                "updated_at": 200,
                "last_message_at": 200,
            }
        ],
    )
    monkeypatch.setattr(
        session_activity.ops_sessions.session_sidecars,
        "_with_parent_lineage_metadata",
        lambda rows: rows,
    )
    monkeypatch.setattr(ops_projects, "_read_projects", lambda: [project])
    monkeypatch.setattr(
        session_activity,
        "_read_raw_ops_runs",
        lambda: [
            {
                "id": "run-1",
                "sessionId": "active_1",
                "projectId": "project-1",
                "taskId": "task-1",
                "status": "running",
                "updatedAt": "2026-05-12T12:01:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        session_activity,
        "_load_project_tasks_by_id",
        lambda _project: {"task-1": {"id": "task-1", "text": "Speed up active sessions", "done": False}},
    )
    monkeypatch.setattr(
        ops_sessions,
        "list_ops_sessions",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("rich session source called")),
    )
    monkeypatch.setattr(
        ops_projects,
        "list_ops_projects",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("rich project source called")),
    )
    monkeypatch.setattr(
        ops_projects,
        "read_ops_project_tasks",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("sidecar task source called")),
    )

    payload = session_activity._lean_activity_source()

    [item] = payload["sessions"]
    assert item["session_id"] == "active_1"
    assert item["ops_project_id"] == "project-1"
    assert item["ops_run"]["id"] == "run-1"
    assert item["ops_task"]["text"] == "Speed up active sessions"


def test_lean_activity_source_matches_runs_through_visible_sidecar_aliases(monkeypatch, tmp_path):
    from api import ops_projects, ops_sessions

    workspace = tmp_path / "hermes"
    workspace.mkdir()
    project = {
        "id": "project-1",
        "name": "Hermes",
        "fullName": "Hermes WebUI",
        "path": str(workspace),
        "coreBranch": "master",
    }
    monkeypatch.setattr(
        session_activity,
        "all_sessions",
        lambda: [
            {
                "session_id": "visible-snapshot",
                "_lineage_root_id": "visible-snapshot",
                "title": "Hermes: Continue task",
                "workspace": str(workspace),
                "source_tag": ops_sessions.OPS_TASK_SOURCE_TAG,
                "is_streaming": False,
                "message_count": 8,
                "created_at": 100,
                "updated_at": 300,
                "last_message_at": 300,
            }
        ],
    )
    monkeypatch.setattr(
        session_activity.ops_sessions.session_sidecars,
        "_with_parent_lineage_metadata",
        lambda rows: rows,
    )
    monkeypatch.setattr(ops_projects, "_read_projects", lambda: [project])
    monkeypatch.setattr(
        session_activity,
        "_read_raw_ops_runs",
        lambda: [
            {
                "id": "run-1",
                "sessionId": "hidden-root",
                "projectId": "project-1",
                "taskId": "task-1",
                "status": "succeeded",
                "updatedAt": "2026-05-12T12:01:00Z",
                "metadata": {"resolvedSessionId": "hidden-tip"},
            }
        ],
    )
    monkeypatch.setattr(
        session_activity.ops_sessions.session_sidecars,
        "list_project_linkage_records",
        lambda project_id: [
            {"sessionId": "hidden-root", "projectId": project_id, "taskId": "task-1", "runId": "run-1"},
            {"sessionId": "hidden-tip", "projectId": project_id, "taskId": "task-1", "runId": "run-1"},
            {"sessionId": "visible-snapshot", "projectId": project_id, "taskId": "task-1", "runId": "run-1"},
        ],
    )
    monkeypatch.setattr(
        session_activity,
        "_load_project_tasks_by_id",
        lambda _project: {"task-1": {"id": "task-1", "text": "Continue task", "done": False}},
    )
    monkeypatch.setattr(
        ops_sessions,
        "list_ops_sessions",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("rich session source called")),
    )

    payload = session_activity._lean_activity_source()

    [item] = payload["sessions"]
    assert item["session_id"] == "visible-snapshot"
    assert item["ops_run"]["id"] == "run-1"
    assert item["ops_task"]["id"] == "task-1"


def test_activity_only_ops_sessions_skips_unrelated_project_run_loads(monkeypatch):
    from api import ops_projects, ops_runs, ops_sessions

    projects = [
        {"id": "project-1", "name": "Hermes", "resolvedPath": "/workspace/hermes", "coreBranch": "master"},
        {"id": "project-2", "name": "Other", "resolvedPath": "/workspace/other", "coreBranch": "main"},
    ]
    monkeypatch.setattr(ops_projects, "list_ops_projects", lambda: {"projects": projects})
    monkeypatch.setattr(
        ops_sessions,
        "all_sessions",
        lambda: [
            {
                "session_id": "active_1",
                "_lineage_root_id": "active_1",
                "source_tag": ops_sessions.OPS_TASK_SOURCE_TAG,
                "is_streaming": False,
                "updated_at": "2026-05-12T12:00:00Z",
            }
        ],
    )

    def task_contexts(project_id):
        if project_id == "project-1":
            return [
                {
                    "id": "task-1",
                    "text": "Speed up active sessions",
                    "done": False,
                    "linkedSessions": [
                        {
                            "sessionId": "active_1",
                            "runId": "run-1",
                            "updatedAt": "2026-05-12T12:01:00Z",
                        }
                    ],
                }
            ]
        return [
            {
                "id": "task-2",
                "text": "Unrelated old task",
                "done": False,
                "linkedSessions": [
                    {
                        "sessionId": "old_session",
                        "runId": "run-2",
                        "updatedAt": "2026-05-01T12:01:00Z",
                    }
                ],
            }
        ]

    run_calls = []

    def list_ops_runs(filters):
        run_calls.append(filters["projectId"])
        if filters["projectId"] == "project-1":
            return {"runs": [{"id": "run-1", "status": "running"}]}
        return {"runs": [{"id": "run-2", "status": "running"}]}

    monkeypatch.setattr(ops_sessions, "_task_contexts", task_contexts)
    monkeypatch.setattr(ops_runs, "list_ops_runs", list_ops_runs)

    payload = ops_sessions.list_ops_sessions(activity_only=True)

    assert run_calls == ["project-1"]
    assert payload["sessions"][0]["ops_project_id"] == "project-1"
    assert payload["sessions"][0]["ops_run"]["id"] == "run-1"

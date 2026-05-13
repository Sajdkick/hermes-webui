from api import session_activity


def test_session_activity_hides_stale_pending_untitled_sidecars(monkeypatch):
    monkeypatch.setattr(session_activity, "_read_state", lambda: {"groups": [], "assignments": []})
    monkeypatch.setattr(
        session_activity.ops_sessions,
        "list_ops_sessions",
        lambda: {
            "sessions": [
                {
                    "session_id": "stale_first_turn",
                    "title": "Untitled",
                    "active_stream_id": "stream-replayable",
                    "pending_user_message": "resume",
                    "is_streaming": False,
                    "updated_at": 100,
                }
            ]
        },
    )

    payload = session_activity.list_session_activity()

    assert payload["sessionCount"] == 0
    assert payload["sessions"] == []


def test_session_activity_keeps_durable_running_ops_task_without_live_stream(monkeypatch):
    monkeypatch.setattr(session_activity, "_read_state", lambda: {"groups": [], "assignments": []})
    monkeypatch.setattr(
        session_activity.ops_sessions,
        "list_ops_sessions",
        lambda: {
            "sessions": [
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
            ]
        },
    )

    payload = session_activity.list_session_activity()

    assert payload["sessionCount"] == 1
    [item] = payload["sessions"]
    assert item["id"] == "ops_task_session"
    assert item["label"] == "Fix the dashboard"
    assert item["taskText"] == "Fix the dashboard"
    assert item["activityStatus"]["key"] == "active"


def test_session_activity_keeps_live_non_ops_stream(monkeypatch):
    monkeypatch.setattr(session_activity, "_read_state", lambda: {"groups": [], "assignments": []})
    monkeypatch.setattr(
        session_activity.ops_sessions,
        "list_ops_sessions",
        lambda: {
            "sessions": [
                {
                    "session_id": "live_general_session",
                    "title": "Untitled",
                    "active_stream_id": "live-stream",
                    "pending_user_message": "hello",
                    "is_streaming": True,
                    "updated_at": 300,
                }
            ]
        },
    )

    payload = session_activity.list_session_activity()

    assert payload["sessionCount"] == 1
    [item] = payload["sessions"]
    assert item["id"] == "live_general_session"
    assert item["activityStatus"]["key"] == "connecting"


def test_session_activity_requests_activity_only_ops_source(monkeypatch):
    calls = []
    monkeypatch.setattr(session_activity, "_read_state", lambda: {"groups": [], "assignments": []})

    def list_ops_sessions(*, activity_only=False):
        calls.append(activity_only)
        return {"sessions": []}

    monkeypatch.setattr(session_activity.ops_sessions, "list_ops_sessions", list_ops_sessions)

    payload = session_activity.list_session_activity()

    assert payload["sessionCount"] == 0
    assert calls == [True]


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
                "session_id": "active-1",
                "_lineage_root_id": "active-1",
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
                            "sessionId": "active-1",
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
                        "sessionId": "old-session",
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

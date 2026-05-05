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

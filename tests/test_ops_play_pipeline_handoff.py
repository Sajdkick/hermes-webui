import json
from datetime import datetime, timezone

from api import ops_notifications, ops_runs, play_pipeline


def _patch_run_context(monkeypatch, tmp_path):
    runs_file = tmp_path / "runs.json"
    runs_file.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(ops_runs, "OPS_RUNS_FILE", runs_file)
    monkeypatch.setattr(ops_runs, "_session_summary", lambda _session_id: None)
    monkeypatch.setattr(ops_runs.session_sidecars, "resolve_session_id", lambda session_id: None)
    monkeypatch.setattr(
        ops_runs.session_readable_output,
        "get_session_readable_output",
        lambda _session_id: (_ for _ in ()).throw(ops_runs.session_readable_output.SessionReadableOutputError("missing", 404)),
    )
    monkeypatch.setattr(
        ops_runs.ops_projects,
        "get_ops_project",
        lambda project_id: {"id": project_id, "name": "Demo", "path": "/tmp/demo", "coreBranch": "main"},
    )
    monkeypatch.setattr(
        ops_runs.ops_projects,
        "get_ops_project_task",
        lambda project_id, task_id: {
            "epicId": "epic-1",
            "task": {"id": task_id, "text": "Run Play", "grade": "green", "done": False},
        },
    )
    return runs_file


def test_successful_run_triggers_configured_play_pipeline(monkeypatch, tmp_path):
    runs_file = _patch_run_context(monkeypatch, tmp_path)
    runs_file.write_text(
        json.dumps(
            [
                {
                    "id": "run-1",
                    "projectId": "project-1",
                    "taskId": "task-1",
                    "sessionId": "session-1",
                    "title": "Run Play",
                    "summary": "",
                    "status": "running",
                    "createdAt": "2026-05-06T00:00:00.000Z",
                    "updatedAt": "2026-05-06T00:00:00.000Z",
                    "metadata": {},
                }
            ]
        ),
        encoding="utf-8",
    )
    started = []
    monkeypatch.setattr(play_pipeline, "get_project_play_config_file_info", lambda project_id: {"valid": True})
    monkeypatch.setattr(
        play_pipeline,
        "start_project_play_pipeline",
        lambda project_id, body: started.append((project_id, body))
        or {"pipelineId": "pipe-1", "status": "building"},
    )

    run = ops_runs.update_ops_run("run-1", {"status": "succeeded"})

    assert started == [("project-1", {"runId": "run-1", "taskId": "task-1", "sessionId": "session-1"})]
    assert run["metadata"]["playPipelineId"] == "pipe-1"
    assert run["metadata"]["playPipelineStatus"] == "building"
    stored = json.loads(runs_file.read_text(encoding="utf-8"))[0]
    assert stored["metadata"]["playPipelineId"] == "pipe-1"


def test_successful_run_triggers_play_after_completed_session_was_closed_first(monkeypatch, tmp_path):
    runs_file = _patch_run_context(monkeypatch, tmp_path)
    runs_file.write_text(
        json.dumps(
            [
                {
                    "id": "run-1",
                    "projectId": "project-1",
                    "taskId": "task-1",
                    "sessionId": "session-1",
                    "title": "Run Play",
                    "summary": "Session closed from the ops dashboard.",
                    "status": "stopped",
                    "createdAt": "2026-05-06T00:00:00.000Z",
                    "updatedAt": "2026-05-06T00:00:00.000Z",
                    "completedAt": "2026-05-06T00:00:00.000Z",
                    "metadata": {},
                }
            ]
        ),
        encoding="utf-8",
    )
    started = []
    monkeypatch.setattr(play_pipeline, "get_project_play_config_file_info", lambda project_id: {"valid": True})
    monkeypatch.setattr(
        play_pipeline,
        "start_project_play_pipeline",
        lambda project_id, body: started.append((project_id, body))
        or {"pipelineId": "pipe-1", "status": "building"},
    )

    run = ops_runs.update_ops_run("run-1", {"status": "succeeded"})

    assert started == [("project-1", {"runId": "run-1", "taskId": "task-1", "sessionId": "session-1"})]
    assert run["metadata"]["playPipelineId"] == "pipe-1"
    assert run["metadata"]["playPipelineStatus"] == "building"


def test_successful_run_does_not_trigger_play_without_valid_config(monkeypatch, tmp_path):
    runs_file = _patch_run_context(monkeypatch, tmp_path)
    runs_file.write_text(
        json.dumps(
            [
                {
                    "id": "run-1",
                    "projectId": "project-1",
                    "taskId": "task-1",
                    "sessionId": "session-1",
                    "title": "Run Play",
                    "summary": "",
                    "status": "running",
                    "createdAt": "2026-05-06T00:00:00.000Z",
                    "updatedAt": "2026-05-06T00:00:00.000Z",
                    "metadata": {},
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(play_pipeline, "get_project_play_config_file_info", lambda project_id: {"valid": False})
    monkeypatch.setattr(
        play_pipeline,
        "start_project_play_pipeline",
        lambda project_id, body: (_ for _ in ()).throw(AssertionError("should not start Play")),
    )

    run = ops_runs.update_ops_run("run-1", {"status": "succeeded"})

    assert "playPipelineTriggeredAt" not in run.get("metadata", {})


def test_play_status_surfaces_terminal_target(monkeypatch):
    monkeypatch.setattr(
        play_pipeline,
        "get_project_play_config_file_info",
        lambda project_id: {"configured": True, "valid": True, "exists": True, "path": "/tmp/play.json", "branch": "main"},
    )
    state = play_pipeline.PlayPipelineState(
        project_id="project-1",
        run_id="run-1",
        task_id="task-1",
        session_id="session-1",
        status="ready",
        ready=True,
        inspect_url="/play-project/project-1/",
        ready_at="2026-05-06T00:00:00.000Z",
    )
    with play_pipeline._LOCK:
        play_pipeline._PIPELINES["project-1"] = state
    try:
        status = play_pipeline.build_project_play_status("project-1")
    finally:
        with play_pipeline._LOCK:
            play_pipeline._PIPELINES.pop("project-1", None)

    assert status["runId"] == "run-1"
    assert status["taskId"] == "task-1"
    assert status["sessionId"] == "session-1"
    assert status["terminalTarget"] == {
        "projectId": "project-1",
        "runId": "run-1",
        "taskId": "task-1",
        "sessionId": "session-1",
    }


def test_play_notification_includes_task_and_terminal_target(monkeypatch):
    monkeypatch.setattr(
        ops_notifications.ops_projects,
        "get_ops_project_task",
        lambda project_id, task_id: {
            "task": {"id": task_id, "text": "Inspect app", "grade": "orange", "done": False}
        },
    )

    notification = ops_notifications._play_notification(
        {"id": "project-1", "name": "Demo"},
        {
            "status": "ready",
            "ready": True,
            "readyAt": "2026-05-06T00:00:00.000Z",
            "inspectUrl": "/play-project/project-1/",
            "statusSummary": "Play app is ready.",
            "terminalTarget": {"runId": "run-1", "taskId": "task-1", "sessionId": "session-1"},
        },
    )

    assert notification["kind"] == "play"
    assert notification["task"] == {"id": "task-1", "text": "Inspect app", "grade": "orange", "done": False}
    assert notification["terminalTarget"] == {
        "projectId": "project-1",
        "runId": "run-1",
        "taskId": "task-1",
        "sessionId": "session-1",
    }
    assert "run-1" in notification["notificationKey"]


def test_play_building_notification_is_locked_and_replaces_done_handoff(monkeypatch):
    monkeypatch.setattr(
        ops_notifications.ops_projects,
        "get_ops_project_task",
        lambda project_id, task_id: {
            "task": {"id": task_id, "text": "Build app", "grade": "green", "done": False}
        },
    )

    notification = ops_notifications._play_notification(
        {"id": "project-1", "name": "Demo"},
        {
            "status": "building",
            "running": True,
            "startedAt": "2026-05-06T00:00:00.000Z",
            "statusSummary": "Play build is running.",
            "terminalTarget": {"runId": "run-1", "taskId": "task-1", "sessionId": "session-1"},
        },
    )

    assert notification["kind"] == "play"
    assert notification["playStatus"] == "building"
    assert notification["playNeedsRepair"] is False
    assert notification["playLocked"] is True
    assert notification["inspectUrl"] == ""
    assert notification["message"] == "Play build is running."
    assert notification["notificationKey"].startswith("play:project-1:run-1:building:")
    assert notification["terminalTarget"] == {
        "projectId": "project-1",
        "runId": "run-1",
        "taskId": "task-1",
        "sessionId": "session-1",
    }


def test_pending_notifications_start_play_for_completed_linked_session(monkeypatch, tmp_path):
    runs_file = _patch_run_context(monkeypatch, tmp_path)
    timestamp = "2026-05-06T00:00:00.000Z"
    runs_file.write_text(
        json.dumps(
            [
                {
                    "id": "run-1",
                    "projectId": "project-1",
                    "taskId": "task-1",
                    "sessionId": "session-1",
                    "title": "Run Play",
                    "summary": "",
                    "status": "running",
                    "createdAt": timestamp,
                    "updatedAt": timestamp,
                    "metadata": {},
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ops_runs,
        "_session_summary",
        lambda session_id: {
            "session_id": "session-1",
            "message_count": 4,
            "active_stream_id": "",
            "pending_user_message": False,
            "updated_at": timestamp,
        },
    )
    monkeypatch.setattr(ops_runs, "_run_requests_for_session", lambda _session_id: [])
    monkeypatch.setattr(ops_runs, "_readable_output_state", lambda _session_id: {"available": False})
    monkeypatch.setattr(
        ops_notifications.ops_projects,
        "get_ops_project",
        lambda project_id: {"id": project_id, "name": "Demo", "path": "/tmp/demo", "coreBranch": "main"},
    )
    monkeypatch.setattr(ops_notifications.session_sidecars, "list_project_linkage_records", lambda _project_id: [])
    monkeypatch.setattr(ops_notifications.session_sidecars, "list_project_linkages", lambda _project_id: [])
    monkeypatch.setattr(
        ops_notifications.ops_projects,
        "get_ops_project_task",
        lambda project_id, task_id: {
            "task": {"id": task_id, "text": "Run Play", "grade": "green", "done": False}
        },
    )
    monkeypatch.setattr(
        play_pipeline,
        "get_project_play_config_file_info",
        lambda project_id: {"configured": True, "valid": True, "exists": True, "path": "/tmp/play.json", "branch": "main"},
    )
    started = []

    def start_play(project_id, body):
        started.append((project_id, body))
        state = play_pipeline.PlayPipelineState(
            project_id=project_id,
            pipeline_id="pipe-1",
            run_id=body.get("runId"),
            task_id=body.get("taskId"),
            session_id=body.get("sessionId"),
            status="building",
            running=True,
            started_at=timestamp,
        )
        with play_pipeline._LOCK:
            play_pipeline._PIPELINES[project_id] = state
        return play_pipeline.build_project_play_status(project_id)

    monkeypatch.setattr(play_pipeline, "start_project_play_pipeline", start_play)
    with play_pipeline._LOCK:
        play_pipeline._PIPELINES.pop("project-1", None)
    try:
        payload = ops_notifications.list_pending_notifications("project-1")
    finally:
        with play_pipeline._LOCK:
            play_pipeline._PIPELINES.pop("project-1", None)

    assert started == [("project-1", {"runId": "run-1", "taskId": "task-1", "sessionId": "session-1"})]
    play_note = next(item for item in payload["notifications"] if item["kind"] == "play")
    assert play_note["playStatus"] == "building"
    assert play_note["playLocked"] is True
    assert play_note["terminalTarget"] == {
        "projectId": "project-1",
        "taskId": "task-1",
        "sessionId": "session-1",
        "runId": "run-1",
    }
    stored = json.loads(runs_file.read_text(encoding="utf-8"))[0]
    assert stored["metadata"]["playPipelineTriggeredAt"]
    assert stored["metadata"]["playPipelineStatus"] == "building"


def test_stale_play_handoff_emits_repairable_play_notification(monkeypatch, tmp_path):
    runs_file = _patch_run_context(monkeypatch, tmp_path)
    triggered_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    runs_file.write_text(
        json.dumps(
            [
                {
                    "id": "run-1",
                    "projectId": "project-1",
                    "taskId": "task-1",
                    "sessionId": "session-1",
                    "title": "Run Play",
                    "summary": "Task completed from the ops dashboard.",
                    "status": "running",
                    "createdAt": triggered_at,
                    "updatedAt": triggered_at,
                    "metadata": {
                        "taskText": "Run Play",
                        "playPipelineTriggeredAt": triggered_at,
                        "playPipelineId": "pipe-1",
                        "playPipelineStatus": "building",
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ops_notifications.ops_projects,
        "get_ops_project",
        lambda project_id: {"id": project_id, "name": "Demo", "path": "/tmp/demo", "coreBranch": "main"},
    )
    monkeypatch.setattr(ops_notifications.session_sidecars, "list_project_linkages", lambda _project_id: [])
    monkeypatch.setattr(
        ops_notifications.ops_projects,
        "get_ops_project_task",
        lambda project_id, task_id: {
            "task": {"id": task_id, "text": "Run Play", "grade": "green", "done": False}
        },
    )
    monkeypatch.setattr(
        play_pipeline,
        "get_project_play_config_file_info",
        lambda project_id: {"configured": True, "valid": True, "exists": True, "path": "/tmp/play.json", "branch": "main"},
    )
    with play_pipeline._LOCK:
        play_pipeline._PIPELINES.pop("project-1", None)

    payload = ops_notifications.list_pending_notifications("project-1")

    play_note = next(item for item in payload["notifications"] if item["kind"] == "play")
    assert play_note["notificationKey"].startswith("play:project-1:run-1:stale:")
    assert play_note["playStatus"] == "stale"
    assert play_note["playNeedsRepair"] is True
    assert play_note["playRepairAvailable"] is True
    assert play_note["playPrimaryAction"] == "start-inspect"
    assert "no active Play pipeline state" in play_note["playFallbackError"]
    assert play_note["terminalTarget"] == {
        "projectId": "project-1",
        "taskId": "task-1",
        "sessionId": "session-1",
        "runId": "run-1",
    }

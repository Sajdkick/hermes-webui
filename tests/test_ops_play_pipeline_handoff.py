import json

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

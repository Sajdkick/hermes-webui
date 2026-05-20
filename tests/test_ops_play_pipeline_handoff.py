import json
from datetime import datetime, timezone
from pathlib import Path

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


def test_stream_completion_marks_ops_run_without_waiting_for_notifications_poll():
    source = (Path(__file__).resolve().parents[1] / "api" / "streaming.py").read_text(encoding="utf-8")

    assert "from api.ops_runs import complete_ops_runs_for_session" in source
    assert "complete_ops_runs_for_session(session_id, resolved_session_id=s.session_id)" in source


def test_successful_run_triggers_play_after_stream_completion_without_polling(monkeypatch, tmp_path):
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

    result = ops_runs.complete_ops_runs_for_session("session-1")

    assert result["updated"] == 1
    assert started == [("project-1", {"runId": "run-1", "taskId": "task-1", "sessionId": "session-1"})]
    stored = json.loads(runs_file.read_text(encoding="utf-8"))[0]
    assert stored["status"] == "succeeded"
    assert stored["completedAt"]
    assert stored["metadata"]["playPipelineTriggeredAt"]
    assert stored["metadata"]["playPipelineStatus"] == "building"


def test_stream_completion_play_handoff_uses_resolved_session_tip(monkeypatch, tmp_path):
    runs_file = _patch_run_context(monkeypatch, tmp_path)
    runs_file.write_text(
        json.dumps(
            [
                {
                    "id": "run-1",
                    "projectId": "project-1",
                    "taskId": "task-1",
                    "sessionId": "session-root",
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

    result = ops_runs.complete_ops_runs_for_session("session-root", resolved_session_id="session-tip")

    assert result["updated"] == 1
    assert started == [("project-1", {"runId": "run-1", "taskId": "task-1", "sessionId": "session-tip"})]
    stored = json.loads(runs_file.read_text(encoding="utf-8"))[0]
    assert stored["sessionId"] == "session-root"
    assert stored["metadata"]["resolvedSessionId"] == "session-tip"
    assert stored["metadata"]["playPipelineTriggeredAt"]
    assert stored["metadata"]["playPipelineStatus"] == "building"


def test_stream_completion_matches_existing_run_from_continuation_sidecar(monkeypatch, tmp_path):
    runs_file = _patch_run_context(monkeypatch, tmp_path)
    runs_file.write_text(
        json.dumps(
            [
                {
                    "id": "run-1",
                    "projectId": "project-1",
                    "taskId": "task-1",
                    "sessionId": "session_root",
                    "title": "Run Play",
                    "summary": "",
                    "status": "succeeded",
                    "createdAt": "2026-05-06T00:00:00.000Z",
                    "updatedAt": "2026-05-06T01:00:00.000Z",
                    "completedAt": "2026-05-06T01:00:00.000Z",
                    "metadata": {
                        "resolvedSessionId": "session_old_tip",
                        "playPipelineTriggeredAt": "2026-05-06T01:00:00.000Z",
                        "playPipelineId": "old-pipe",
                        "playPipelineStatus": "building",
                    },
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
        or {"pipelineId": "new-pipe", "status": "building"},
    )
    monkeypatch.setattr(
        ops_runs.session_sidecars,
        "get_session_linkage",
        lambda session_id: {
            "sessionId": "session_tip",
            "linkedSessionId": "session_tip",
            "lineageTipId": "session_tip",
            "runId": "run-1",
        }
        if session_id == "session_tip"
        else None,
    )

    result = ops_runs.complete_ops_runs_for_session("session_tip")

    assert result["updated"] == 1
    assert started == [("project-1", {"runId": "run-1", "taskId": "task-1", "sessionId": "session_tip"})]
    stored = json.loads(runs_file.read_text(encoding="utf-8"))[0]
    assert stored["sessionId"] == "session_root"
    assert stored["metadata"]["resolvedSessionId"] == "session_tip"
    assert stored["metadata"]["playPipelineId"] == "new-pipe"
    assert stored["metadata"]["playPipelineStatus"] == "building"


def test_stream_completion_restarts_play_for_reiterated_successful_run(monkeypatch, tmp_path):
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
                    "status": "succeeded",
                    "createdAt": "2026-05-06T00:00:00.000Z",
                    "updatedAt": "2026-05-06T01:00:00.000Z",
                    "completedAt": "2026-05-06T01:00:00.000Z",
                    "metadata": {
                        "playPipelineTriggeredAt": "2026-05-06T01:00:00.000Z",
                        "playPipelineId": "old-pipe",
                        "playPipelineStatus": "ready",
                    },
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
        or {"pipelineId": "new-pipe", "status": "building"},
    )

    result = ops_runs.complete_ops_runs_for_session("session-1")

    assert result["updated"] == 1
    assert started == [("project-1", {"runId": "run-1", "taskId": "task-1", "sessionId": "session-1"})]
    stored = json.loads(runs_file.read_text(encoding="utf-8"))[0]
    assert stored["status"] == "succeeded"
    assert stored["metadata"]["playPipelineId"] == "new-pipe"
    assert stored["metadata"]["playPipelineStatus"] == "building"
    assert stored["metadata"]["playPipelineTriggeredAt"] != "2026-05-06T01:00:00.000Z"


def test_stream_completion_forces_play_after_early_notification_poll(monkeypatch, tmp_path):
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
                    "updatedAt": "2026-05-06T01:00:00.000Z",
                    "metadata": {
                        "playPipelineTriggeredAt": "2026-05-06T01:00:00.000Z",
                        "playPipelineId": "old-pipe",
                        "playPipelineStatus": "ready",
                    },
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
        or {"pipelineId": "new-pipe", "status": "building"},
    )

    result = ops_runs.complete_ops_runs_for_session("session-1")

    assert result["updated"] == 1
    assert started == [("project-1", {"runId": "run-1", "taskId": "task-1", "sessionId": "session-1"})]
    stored = json.loads(runs_file.read_text(encoding="utf-8"))[0]
    assert stored["metadata"]["playPipelineId"] == "new-pipe"
    assert stored["metadata"]["playPipelineStatus"] == "building"


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


def test_play_proxy_overlay_attributes_use_pipeline_session_id(monkeypatch):
    state = play_pipeline.PlayPipelineState(
        project_id="project-1",
        run_id="run-1",
        task_id="task-1",
        session_id="session-tip",
        status="ready",
        ready=True,
        inspect_url="/play-project/project-1/",
        ready_at="2026-05-06T00:00:00.000Z",
    )
    with play_pipeline._LOCK:
        play_pipeline._PIPELINES["project-1"] = state
    try:
        attrs = play_pipeline._play_proxy_overlay_attributes("project-1")
    finally:
        with play_pipeline._LOCK:
            play_pipeline._PIPELINES.pop("project-1", None)

    assert 'data-hermes-play-session-id="session-tip"' in attrs
    assert 'data-hermes-play-session-url="/session/session-tip"' in attrs


def test_start_play_pipeline_replaces_existing_ready_pipeline(monkeypatch, tmp_path):
    project_path = tmp_path / "project"
    project_path.mkdir()
    monkeypatch.setattr(
        play_pipeline,
        "get_project_play_config",
        lambda project_id: {
            "project": {"id": project_id, "name": "Demo", "path": str(project_path), "coreBranch": "main"},
            "projectPath": project_path,
            "path": str(project_path / ".hermes" / "play.json"),
            "branch": "main",
            "config": {
                "version": 2,
                "buildOnly": True,
                "build": {"command": "true", "cwd": ".", "env": {}, "timeoutMs": 1000},
                "start": {"command": "", "cwd": ".", "env": {}, "port": {"mode": "fixed"}},
                "inspect": {"mode": "direct", "url": "", "readyTimeoutMs": 5000},
            },
        },
    )
    monkeypatch.setattr(
        play_pipeline,
        "get_project_play_config_file_info",
        lambda project_id: {
            "configured": True,
            "valid": True,
            "exists": True,
            "path": str(project_path / ".hermes" / "play.json"),
            "branch": "main",
            "buildOnly": True,
        },
    )
    monkeypatch.setattr(play_pipeline, "_pipeline_worker", lambda play_config, state: None)
    old_state = play_pipeline.PlayPipelineState(
        project_id="project-1",
        pipeline_id="old-pipe",
        run_id="old-run",
        status="ready",
        running=True,
        ready=True,
        inspect_url="/play-project/project-1/",
    )
    with play_pipeline._LOCK:
        play_pipeline._PIPELINES["project-1"] = old_state
    try:
        status = play_pipeline.start_project_play_pipeline(
            "project-1",
            {"runId": "new-run", "taskId": "task-1", "sessionId": "session-1"},
        )
        with play_pipeline._LOCK:
            new_state = play_pipeline._PIPELINES["project-1"]
    finally:
        with play_pipeline._LOCK:
            play_pipeline._PIPELINES.pop("project-1", None)

    assert old_state.stop_requested is True
    assert new_state is not old_state
    assert new_state.pipeline_id != "old-pipe"
    assert status["pipelineId"] == new_state.pipeline_id
    assert status["status"] == "building"
    assert status["runId"] == "new-run"


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

    assert notification is not None
    assert notification["kind"] == "play"
    assert notification["playStatus"] == "building"
    assert notification["playNeedsRepair"] is False
    assert notification["playLocked"] is True
    assert notification["inspectUrl"] == ""
    assert notification["message"] == "Play build is running."
    assert notification["notificationKey"] == "play:project-1:run-1:building"
    assert notification["terminalTarget"] == {
        "projectId": "project-1",
        "runId": "run-1",
        "taskId": "task-1",
        "sessionId": "session-1",
    }


def test_play_building_notification_key_stays_stable_when_updated_at_changes(monkeypatch):
    monkeypatch.setattr(
        ops_notifications.ops_projects,
        "get_ops_project_task",
        lambda project_id, task_id: {
            "task": {"id": task_id, "text": "Build app", "grade": "green", "done": False}
        },
    )
    project = {"id": "project-1", "name": "Demo"}
    base_status = {
        "status": "building",
        "running": True,
        "statusSummary": "Play build is running.",
        "terminalTarget": {"runId": "run-1", "taskId": "task-1", "sessionId": "session-1"},
    }

    first = ops_notifications._play_notification(project, {**base_status, "updatedAt": "2026-05-06T00:00:00.000Z"})
    second = ops_notifications._play_notification(project, {**base_status, "updatedAt": "2026-05-06T00:00:05.000Z"})

    assert first is not None
    assert second is not None
    assert first["playLocked"] is True
    assert first["notificationKey"] == second["notificationKey"] == "play:project-1:run-1:building"


def test_play_building_notification_key_changes_for_restarted_pipeline(monkeypatch):
    monkeypatch.setattr(
        ops_notifications.ops_projects,
        "get_ops_project_task",
        lambda project_id, task_id: {
            "task": {"id": task_id, "text": "Build app", "grade": "green", "done": False}
        },
    )
    project = {"id": "project-1", "name": "Demo"}
    base_status = {
        "status": "building",
        "running": True,
        "startedAt": "2026-05-06T00:00:00.000Z",
        "statusSummary": "Play build is running.",
        "terminalTarget": {"runId": "run-1", "taskId": "task-1", "sessionId": "session-1"},
    }

    old_pipeline = ops_notifications._play_notification(project, {**base_status, "pipelineId": "old-pipe"})
    restarted_pipeline = ops_notifications._play_notification(project, {**base_status, "pipelineId": "new-pipe"})
    restarted_pipeline_updated = ops_notifications._play_notification(
        project,
        {**base_status, "pipelineId": "new-pipe", "updatedAt": "2026-05-06T00:00:05.000Z"},
    )

    assert old_pipeline is not None
    assert restarted_pipeline is not None
    assert restarted_pipeline_updated is not None
    assert old_pipeline["notificationKey"] == "play:project-1:run-1:old-pipe:building"
    assert restarted_pipeline["notificationKey"] == "play:project-1:run-1:new-pipe:building"
    assert restarted_pipeline_updated["notificationKey"] == restarted_pipeline["notificationKey"]


def test_play_refresh_preserves_locked_notification_during_transient_empty_poll():
    source = (Path(__file__).resolve().parents[1] / "static" / "ops-legacy-play.js").read_text(encoding="utf-8")

    assert "previousProjectPlayNotes=projectPlayNotifications(id)" in source
    assert "!hasFreshProjectPlay&&shouldPollPlayStatus(OPS.playStatusByProject[id])" in source
    assert "lockedPrevious=previousProjectPlayNotes.find(isLockedPlayNotification)" in source


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


def test_play_failed_notification_attaches_scrollable_logs(monkeypatch):
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
            "status": "failed",
            "finishedAt": "2026-05-06T00:00:00.000Z",
            "failureSummary": "Build failed.",
            "terminalTarget": {"runId": "run-1", "taskId": "task-1", "sessionId": "session-1"},
            "playLogs": [
                {"at": "2026-05-06T00:00:00.000Z", "stage": "build", "stream": "stdout", "message": "npm run build"},
                {"at": "2026-05-06T00:00:01.000Z", "stage": "build", "stream": "stderr", "message": "TOKEN=super-secret failed"},
            ],
        },
    )

    assert notification is not None
    assert notification["playStatus"] == "failed"
    assert "npm run build" in notification["playLogText"]
    assert "TOKEN=[REDACTED]" in notification["playLogText"]
    assert "super-secret" not in notification["playLogText"]


def test_play_fallback_notification_attaches_metadata_logs(monkeypatch, tmp_path):
    _patch_run_context(monkeypatch, tmp_path).write_text(
        json.dumps(
            [
                {
                    "id": "run-1",
                    "projectId": "project-1",
                    "taskId": "task-1",
                    "sessionId": "session-1",
                    "title": "Run Play",
                    "summary": "Task completed from the ops dashboard.",
                    "status": "succeeded",
                    "createdAt": "2026-05-06T00:00:00.000Z",
                    "updatedAt": "2026-05-06T00:00:00.000Z",
                    "metadata": {
                        "taskText": "Run Play",
                        "playPipelineTriggeredAt": "2026-05-06T00:00:00.000Z",
                        "playPipelineStatus": "building",
                        "playLogText": "build output\nSECRET=hidden-value",
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ops_notifications, "_recent_notification_time", lambda _value: True)
    monkeypatch.setattr(
        ops_notifications.ops_projects,
        "get_ops_project_task",
        lambda project_id, task_id: {
            "task": {"id": task_id, "text": "Run Play", "grade": "green", "done": False}
        },
    )

    note = ops_notifications._play_handoff_fallback_notification({"id": "project-1", "name": "Demo"}, ops_runs._read_runs()[0])

    assert note is not None
    assert note["playStatus"] == "stale"
    assert "build output" in note["playLogText"]
    assert "SECRET=[REDACTED]" in note["playLogText"]
    assert "hidden-value" not in note["playLogText"]


def test_play_notification_renderer_includes_log_scrollview():
    source = (Path(__file__).resolve().parents[1] / "static" / "ops-legacy-notifications.js").read_text(encoding="utf-8")
    css = (Path(__file__).resolve().parents[1] / "static" / "ops-legacy.css").read_text(encoding="utf-8")

    assert "playNotificationLogText" in source
    assert "menu-notification-play-log-panel" in source
    assert "menu-notification-play-log-scroll" in source
    assert ".menu-notification-play-log-scroll" in css
    assert "max-height:220px;overflow:auto" in css


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

def test_failed_play_build_sends_redacted_logs_back_to_linked_session(monkeypatch):
    calls = []

    def fake_repair_handler(session_id, prompt, metadata):
        calls.append({"session_id": session_id, "prompt": prompt, "metadata": metadata})
        return {"ok": True, "stream_id": "repair-stream-1"}

    play_pipeline.register_build_failure_repair_handler(fake_repair_handler)
    try:
        state = play_pipeline.PlayPipelineState(
            project_id="project-1",
            run_id="run-1",
            task_id="task-1",
            session_id="session-1",
        )
        play_pipeline._append_log(state, stage="build", stream="stdout", message="building package")
        play_pipeline._append_log(state, stage="build", stream="stderr", message="TOKEN=super-secret-value")

        play_pipeline._request_build_failure_repair(state, "Build failed: process exited with code 1.")

        assert len(calls) == 1
        assert calls[0]["session_id"] == "session-1"
        assert calls[0]["metadata"] == {
            "projectId": "project-1",
            "runId": "run-1",
            "taskId": "task-1",
            "pipelineId": state.pipeline_id,
            "reason": "Build failed: process exited with code 1.",
        }
        prompt = calls[0]["prompt"]
        assert prompt.startswith("The build failed, these are the logs, analyze them and fix the issue.")
        assert "building package" in prompt
        assert "TOKEN=[REDACTED]" in prompt
        assert "super-secret-value" not in prompt
        assert state.repair_requested_at
        assert state.repair_stream_id == "repair-stream-1"
        assert state.repair_error is None
        with play_pipeline._LOCK:
            play_pipeline._PIPELINES["project-1"] = state
        monkeypatch.setattr(
            play_pipeline,
            "get_project_play_config_file_info",
            lambda project_id: {"configured": True, "valid": True, "exists": True, "path": "/tmp/play.json", "branch": "main"},
        )
        status = play_pipeline.build_project_play_status("project-1")
        assert status["repairRequestedAt"] == state.repair_requested_at
        assert status["repairStreamId"] == "repair-stream-1"
    finally:
        with play_pipeline._LOCK:
            play_pipeline._PIPELINES.pop("project-1", None)
        play_pipeline.register_build_failure_repair_handler(None)

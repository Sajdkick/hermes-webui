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


def test_sidecar_resolution_derives_lineage_from_parent_chain_without_state_db_metadata(monkeypatch):
    root = {
        "session_id": "root",
        "archived": False,
        "updated_at": 300,
        "last_message_at": 30,
        "message_count": 10,
    }
    old_sibling = {
        "session_id": "old_child",
        "parent_session_id": "root",
        "archived": False,
        "updated_at": 400,
        "last_message_at": 100,
        "message_count": 20,
    }
    middle = {
        "session_id": "middle",
        "parent_session_id": "root",
        "archived": True,
        "updated_at": 150,
        "last_message_at": 150,
        "message_count": 30,
    }
    latest_tip = {
        "session_id": "latest_child",
        "parent_session_id": "middle",
        "archived": True,
        "updated_at": 200,
        "last_message_at": 200,
        "message_count": 40,
    }

    monkeypatch.setattr(session_sidecars, "_session_summary", lambda sid: root if sid == "root" else None)
    monkeypatch.setattr(session_sidecars, "all_sessions", lambda: [root, old_sibling, middle, latest_tip])

    root_summary = session_sidecars.resolve_session_summary("root")
    old_child_summary = session_sidecars.resolve_session_summary("old_child")
    middle_summary = session_sidecars.resolve_session_summary("middle")

    assert root_summary is not None
    assert old_child_summary is not None
    assert middle_summary is not None
    assert root_summary["session_id"] == "latest_child"
    assert old_child_summary["session_id"] == "latest_child"
    assert middle_summary["session_id"] == "latest_child"


def test_sidecar_resolution_uses_task_sidecar_group_when_index_lacks_parent_chain(monkeypatch):
    root = {
        "session_id": "root",
        "archived": False,
        "updated_at": 300,
        "last_message_at": 30,
        "message_count": 10,
    }
    older_touched_segment = {
        "session_id": "older_segment",
        "parent_session_id": "root",
        "archived": False,
        "updated_at": 300,
        "last_message_at": 300,
        "message_count": 40,
    }
    latest_tip = {
        "session_id": "latest_child",
        "parent_session_id": "missing_middle",
        "archived": False,
        "updated_at": 200,
        "last_message_at": 200,
        "message_count": 40,
    }
    summaries = {"root": root, "older_segment": older_touched_segment, "latest_child": latest_tip}
    records = [
        {
            "sessionId": "root",
            "projectId": "project-1",
            "taskId": "task-1",
            "runId": "run-1",
            "updatedAt": "2026-05-21T10:00:00Z",
        },
        {
            "sessionId": "older_segment",
            "projectId": "project-1",
            "taskId": "task-1",
            "runId": "run-1",
            "updatedAt": "2026-05-21T11:00:00Z",
        },
        {
            "sessionId": "latest_child",
            "projectId": "project-1",
            "taskId": "task-1",
            "runId": "run-1",
            "updatedAt": "2026-05-21T12:00:00Z",
        },
    ]

    monkeypatch.setattr(session_sidecars, "_session_summary", lambda sid: summaries.get(sid))
    monkeypatch.setattr(session_sidecars, "all_sessions", lambda: [root])
    monkeypatch.setattr(
        session_sidecars,
        "_read_json",
        lambda _path: {"sessionId": "root", "projectId": "project-1", "taskId": "task-1", "runId": "run-1"},
    )
    monkeypatch.setattr(session_sidecars, "list_project_linkage_records", lambda _project_id: records)

    summary = session_sidecars.resolve_session_summary("root")

    assert summary is not None
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


def test_launch_task_session_force_new_skips_existing_task_lookup(monkeypatch, tmp_path):
    """Fresh Quick Tasks should not scan project-wide linked-session sidecars."""
    project = {
        "id": "project-1",
        "name": "Hermes WebUI",
        "path": str(tmp_path),
        "resolvedPath": str(tmp_path),
        "profile": "hermes-webui",
    }
    task = {"id": "task-1", "text": "Run a fresh quick task"}
    created = {}

    class CreatedSession:
        session_id = "session-force-new"
        messages = []
        active_stream_id = None

        def __init__(self, **kwargs):
            self.profile = kwargs.get("profile")
            self.project_id = kwargs.get("project_id")
            self.workspace = kwargs.get("workspace")
            self.model = kwargs.get("model")
            self.model_provider = kwargs.get("model_provider")
            self.title = ""
            self.source_tag = None
            self.source_label = None

        def save(self):
            self.saved = True

        def compact(self):
            return {
                "session_id": self.session_id,
                "profile": self.profile,
                "project_id": self.project_id,
                "source_tag": self.source_tag,
            }

    def fail_existing_lookup(_project_id, _task_id):
        raise AssertionError("forceNew task launch should not look up existing linked sessions")

    def fake_new_session(**kwargs):
        created.update(kwargs)
        return CreatedSession(**kwargs)

    monkeypatch.setattr(ops_sessions, "_find_existing_task_session", fail_existing_lookup)
    monkeypatch.setattr(
        ops_sessions.session_sidecars,
        "task_linkage_map",
        lambda _project_id: (_ for _ in ()).throw(AssertionError("task_linkage_map should not be called")),
    )
    monkeypatch.setattr(
        ops_sessions.ops_projects,
        "get_ops_project_task",
        lambda project_id, task_id: {"project": project, "task": task},
    )
    monkeypatch.setattr(ops_sessions, "new_session", fake_new_session)
    monkeypatch.setattr(
        ops_sessions,
        "_profile_config_defaults",
        lambda profile: ("project-default-model", "project-provider"),
    )
    monkeypatch.setattr(
        ops_sessions.ops_projects,
        "update_ops_project_task",
        lambda project_id, task_id, patch: {"task": {**task, **patch}},
    )
    monkeypatch.setattr(ops_sessions.ops_projects, "_now_iso", lambda: "2026-05-17T00:00:00Z")
    monkeypatch.setattr(
        ops_sessions.session_sidecars,
        "set_session_linkage",
        lambda session_id, project_id, task_id, run_id="": {"sessionId": session_id, "runId": run_id},
    )

    from api import ops_runs

    monkeypatch.setattr(
        ops_runs,
        "create_task_run",
        lambda project_id, task_id, session_id, title="": {"id": "run-1", "sessionId": session_id},
    )
    monkeypatch.setattr(ops_runs, "run_url", lambda run_id: f"/ops/runs/{run_id}")

    result = ops_sessions.launch_task_session("project-1", "task-1", {"forceNew": True})

    assert created["profile"] == "hermes-webui"
    assert result["session"]["session_id"] == "session-force-new"
    assert result.get("reused") is not True


def test_launch_task_session_uses_project_profile_over_payload(monkeypatch, tmp_path):
    """Ops project task launches must not inherit the globally selected UI profile."""
    project = {
        "id": "project-1",
        "name": "Hermes WebUI",
        "path": str(tmp_path),
        "resolvedPath": str(tmp_path),
        "profile": "hermes-webui",
    }
    task = {"id": "task-1", "text": "Fix profile routing"}
    created = {}
    defaults_called = []

    class CreatedSession:
        session_id = "session-task"
        messages = []
        active_stream_id = None

        def __init__(self, *, profile, project_id, workspace, model, model_provider):
            self.profile = profile
            self.project_id = project_id
            self.workspace = workspace
            self.model = model
            self.model_provider = model_provider
            self.title = ""
            self.source_tag = None
            self.source_label = None

        def save(self):
            self.saved = True

        def compact(self):
            return {
                "session_id": self.session_id,
                "profile": self.profile,
                "project_id": self.project_id,
                "source_tag": self.source_tag,
            }

    def fake_new_session(**kwargs):
        created.update(kwargs)
        return CreatedSession(**kwargs)

    monkeypatch.setattr(ops_sessions, "_find_existing_task_session", lambda _project_id, _task_id: None)
    monkeypatch.setattr(
        ops_sessions.ops_projects,
        "get_ops_project_task",
        lambda project_id, task_id: {"project": project, "task": task},
    )
    monkeypatch.setattr(ops_sessions, "new_session", fake_new_session)

    def fake_profile_defaults(profile):
        defaults_called.append(profile)
        return "project-default-model", "project-provider"

    monkeypatch.setattr(ops_sessions, "_profile_config_defaults", fake_profile_defaults)
    monkeypatch.setattr(
        ops_sessions.ops_projects,
        "update_ops_project_task",
        lambda project_id, task_id, patch: {"task": {**task, **patch}},
    )
    monkeypatch.setattr(ops_sessions.ops_projects, "_now_iso", lambda: "2026-05-17T00:00:00Z")
    monkeypatch.setattr(
        ops_sessions.session_sidecars,
        "set_session_linkage",
        lambda session_id, project_id, task_id, run_id="": {"sessionId": session_id, "runId": run_id},
    )

    from api import ops_runs

    monkeypatch.setattr(
        ops_runs,
        "create_task_run",
        lambda project_id, task_id, session_id, title="": {"id": "run-1", "sessionId": session_id},
    )
    monkeypatch.setattr(ops_runs, "run_url", lambda run_id: f"/ops/runs/{run_id}")

    result = ops_sessions.launch_task_session(
        "project-1",
        "task-1",
        {
            "profile": "laxlyftet",
            "model": "stale-browser-model",
            "model_provider": "openai-codex",
        },
    )

    assert created["profile"] == "hermes-webui"
    assert created["model"] == "project-default-model"
    assert created["model_provider"] == "project-provider"
    assert result["session"]["profile"] == "hermes-webui"
    assert defaults_called == ["hermes-webui"]


def test_launch_task_session_defaults_blank_project_profile_to_default(monkeypatch, tmp_path):
    """A blank/default project profile means root default, not active UI profile."""
    project = {
        "id": "project-1",
        "name": "Default project",
        "path": str(tmp_path),
        "resolvedPath": str(tmp_path),
        "profile": None,
    }
    task = {"id": "task-1", "text": "Use default profile"}
    created = {}
    defaults_called = []

    class CreatedSession:
        session_id = "session-default-task"
        messages = []
        active_stream_id = None

        def __init__(self, **kwargs):
            self.profile = kwargs.get("profile")
            self.project_id = kwargs.get("project_id")
            self.workspace = kwargs.get("workspace")
            self.model = kwargs.get("model")
            self.model_provider = kwargs.get("model_provider")
            self.title = ""
            self.source_tag = None
            self.source_label = None

        def save(self):
            self.saved = True

        def compact(self):
            return {"session_id": self.session_id, "profile": self.profile, "project_id": self.project_id}

    def fake_profile_defaults(profile):
        defaults_called.append(profile)
        return "default-profile-model", "default-provider"

    def fake_new_session(**kwargs):
        created.update(kwargs)
        return CreatedSession(**kwargs)

    monkeypatch.setattr(ops_sessions, "_find_existing_task_session", lambda _project_id, _task_id: None)
    monkeypatch.setattr(
        ops_sessions.ops_projects,
        "get_ops_project_task",
        lambda project_id, task_id: {"project": project, "task": task},
    )
    monkeypatch.setattr(ops_sessions, "_profile_config_defaults", fake_profile_defaults)
    monkeypatch.setattr(ops_sessions, "new_session", fake_new_session)
    monkeypatch.setattr(
        ops_sessions.ops_projects,
        "update_ops_project_task",
        lambda project_id, task_id, patch: {"task": {**task, **patch}},
    )
    monkeypatch.setattr(ops_sessions.ops_projects, "_now_iso", lambda: "2026-05-17T00:00:00Z")
    monkeypatch.setattr(
        ops_sessions.session_sidecars,
        "set_session_linkage",
        lambda session_id, project_id, task_id, run_id="": {"sessionId": session_id, "runId": run_id},
    )

    from api import ops_runs

    monkeypatch.setattr(
        ops_runs,
        "create_task_run",
        lambda project_id, task_id, session_id, title="": {"id": "run-1", "sessionId": session_id},
    )
    monkeypatch.setattr(ops_runs, "run_url", lambda run_id: f"/ops/runs/{run_id}")

    result = ops_sessions.launch_task_session("project-1", "task-1", {"profile": "laxlyftet"})

    assert created["profile"] == "default"
    assert result["session"]["profile"] == "default"
    assert defaults_called == ["default"]


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


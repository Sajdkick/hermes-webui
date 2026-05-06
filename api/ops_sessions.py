"""Fork-owned task session launch helpers for the clean restart branch."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote

import yaml

from api.config import get_effective_default_model
from api import ops_projects, session_sidecars
from api.models import all_sessions, get_session, new_session


OPS_TASK_SOURCE_TAG = "ops_task"
OPS_TASK_SOURCE_LABEL = "Ops task"


class OpsSessionError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def session_url(session_id: str) -> str:
    key = str(session_id or "").strip()
    if not key:
        raise OpsSessionError("Session id is required.")
    return f"/session/{quote(key, safe='')}"


def _epoch_seconds(value) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _session_sort_key(session: dict) -> float:
    return max(
        _epoch_seconds(session.get("last_message_at")),
        _epoch_seconds(session.get("updated_at")),
        _epoch_seconds(session.get("created_at")),
        0.0,
    )


def _session_aliases(session: dict | None) -> set[str]:
    aliases: set[str] = set()
    if not isinstance(session, dict):
        return aliases
    for field in ("session_id", "_lineage_root_id", "_lineage_tip_id", "parent_session_id"):
        value = str(session.get(field) or "").strip()
        if value:
            aliases.add(value)
    return aliases


def _session_matches_project(session: dict, project: dict) -> bool:
    if not isinstance(session, dict) or not isinstance(project, dict):
        return False
    session_project_id = str(session.get("project_id") or "").strip()
    if session_project_id and session_project_id == str(project.get("id") or "").strip():
        return True
    workspace = str(session.get("workspace") or "").rstrip("/")
    project_path = str(project.get("resolvedPath") or project.get("path") or "").rstrip("/")
    return bool(workspace and project_path and workspace == project_path)


def _task_contexts(project_id: str) -> list[dict]:
    payload = ops_projects.read_ops_project_tasks(project_id)
    contexts: list[dict] = []
    for epic in payload.get("epics") or []:
        epic_title = str(epic.get("title") or "").strip()
        for task in epic.get("tasks") or []:
            task_context = dict(task)
            if epic_title:
                task_context["epicTitle"] = epic_title
            contexts.append(task_context)
    return contexts


def _session_status_flags(run: dict | None) -> dict:
    status = str((run or {}).get("status") or "").strip().lower()
    waiting_for_approval = status == "waiting-approval"
    waiting_for_input = status == "waiting-input"
    return {
        "waitingForApproval": waiting_for_approval,
        "waitingForInput": waiting_for_input,
        "waitingSince": _epoch_seconds((run or {}).get("updatedAt")),
        "lastOutputAt": _epoch_seconds(((run or {}).get("readableOutput") or {}).get("updatedAt")),
    }


def _enrich_session_summary(session: dict, project: dict | None = None, task: dict | None = None, run: dict | None = None) -> dict:
    enriched = dict(session)
    if project:
        project_id = str(project.get("id") or "").strip()
        if project_id:
            enriched["ops_project_id"] = project_id
            enriched["projectId"] = project_id
        repository_label = str(project.get("fullName") or project.get("name") or project_id).strip()
        if repository_label:
            enriched["repositoryLabel"] = repository_label
        branch_label = str(project.get("coreBranch") or project.get("tasksBranch") or "").strip()
        if branch_label:
            enriched["branchLabel"] = branch_label
    if task:
        task_id = str(task.get("id") or "").strip()
        if task_id:
            enriched["ops_task_id"] = task_id
            enriched["opsTaskId"] = task_id
        enriched["ops_task"] = {
            "id": task_id,
            "text": task.get("text"),
            "grade": task.get("grade"),
            "done": task.get("done"),
            "epicTitle": task.get("epicTitle"),
        }
    if run:
        enriched["ops_run"] = run
        enriched["ops_run_id"] = str(run.get("id") or "").strip()
        enriched["ops_pending_request_count"] = int(run.get("pendingRequestCount") or 0)
        enriched["lastActivityAt"] = _epoch_seconds(run.get("updatedAt")) or _session_sort_key(session)
        status_flags = _session_status_flags(run)
        enriched.update({key: value for key, value in status_flags.items() if value})
    else:
        enriched.setdefault("lastActivityAt", _session_sort_key(session))
    if str(enriched.get("source_tag") or "").strip() == OPS_TASK_SOURCE_TAG:
        enriched.setdefault("taskStartedBy", {"id": "ops-dashboard", "label": "Ops dashboard"})
    return enriched


def _task_workspace(project: dict) -> str | None:
    raw = str(project.get("resolvedPath") or project.get("path") or "").strip()
    if not raw:
        return None
    return str(Path(raw).expanduser().resolve())


def _task_session_title(project: dict, task: dict) -> str:
    task_text = str(task.get("text") or "").strip() or "Task session"
    project_name = str(project.get("name") or project.get("fullName") or "").strip()
    title = f"{project_name}: {task_text}" if project_name else task_text
    return title[:160]


def _project_profile(project: dict) -> str | None:
    profile = str(project.get("profile") or "").strip()
    return profile or None


def _profile_config_defaults(profile: str | None) -> tuple[str | None, str | None]:
    if not profile:
        return None, None
    from api.profiles import get_hermes_home_for_profile, get_profile_runtime_env

    home = get_hermes_home_for_profile(profile)
    if not home.exists():
        raise OpsSessionError(f"Profile not found: {profile}")

    config_data = {}
    config_path = home / "config.yaml"
    if config_path.exists():
        try:
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config_data = loaded
        except Exception:
            config_data = {}
    env_values = get_profile_runtime_env(home)
    env_model = (
        str(env_values.get("HERMES_MODEL") or "").strip()
        or str(env_values.get("OPENAI_MODEL") or "").strip()
        or str(env_values.get("LLM_MODEL") or "").strip()
    )
    model_cfg = config_data.get("model", {}) if isinstance(config_data, dict) else {}
    provider = None
    if isinstance(model_cfg, dict):
        provider = str(model_cfg.get("provider") or "").strip().lower() or None
    default_model = env_model or get_effective_default_model(config_data)
    return default_model or None, provider


def _project_session_defaults(project: dict) -> tuple[str | None, str | None]:
    explicit_model = str(project.get("defaultModel") or "").strip() or None
    explicit_provider = str(project.get("defaultModelProvider") or "").strip().lower() or None
    if explicit_model:
        if explicit_provider:
            return explicit_model, explicit_provider
        _profile_model, profile_provider = _profile_config_defaults(_project_profile(project))
        return explicit_model, profile_provider
    return _profile_config_defaults(_project_profile(project))


def _payload_session_defaults(body: dict | None) -> tuple[str | None, str | None]:
    payload = body if isinstance(body, dict) else {}
    requested_model = str(payload.get("model") or "").strip()
    requested_provider = str(payload.get("model_provider") or "").strip().lower() or None
    if not requested_model:
        return None, None
    try:
        from api.routes import _session_model_state_from_request

        model, provider = _session_model_state_from_request(requested_model, requested_provider)
        return model, provider
    except Exception:
        if requested_model.startswith("@") and ":" in requested_model:
            provider_hint, bare_model = requested_model[1:].rsplit(":", 1)
            provider = str(provider_hint or "").strip().lower() or requested_provider
            model = str(bare_model or "").strip()
            return model or None, provider
        return requested_model, requested_provider


def _payload_profile(body: dict | None) -> str | None:
    payload = body if isinstance(body, dict) else {}
    requested_profile = str(payload.get("profile") or "").strip()
    return requested_profile or None


def project_profile(project: dict) -> str | None:
    return _project_profile(project)


def project_session_defaults(project: dict) -> tuple[str | None, str | None]:
    return _project_session_defaults(project)


def list_ops_sessions(project_id: str | None = None) -> dict:
    projects = (
        [ops_projects.get_ops_project(project_id)]
        if project_id
        else list(ops_projects.list_ops_projects().get("projects") or [])
    )
    project_by_id = {
        str(project.get("id") or "").strip(): project
        for project in projects
        if isinstance(project, dict)
    }

    linkage_index: dict[str, dict] = {}
    project_tasks: dict[str, list[dict]] = {}
    for project in projects:
        pid = str(project.get("id") or "").strip()
        if not pid:
            continue
        tasks = _task_contexts(pid)
        project_tasks[pid] = tasks
        try:
            from api import ops_runs

            runs = list(ops_runs.list_ops_runs({"projectId": pid}).get("runs") or [])
        except Exception:
            runs = []
        run_by_id = {
            str(run.get("id") or "").strip(): run
            for run in runs
            if isinstance(run, dict) and str(run.get("id") or "").strip()
        }
        for task in tasks:
            for linkage in task.get("linkedSessions") or []:
                if not isinstance(linkage, dict):
                    continue
                run = run_by_id.get(str(linkage.get("runId") or "").strip())
                meta = {
                    "project": project,
                    "task": task,
                    "run": run,
                    "updatedAt": str(linkage.get("updatedAt") or linkage.get("linkedAt") or ""),
                }
                aliases = {
                    str(linkage.get("sessionId") or "").strip(),
                    str(linkage.get("linkedSessionId") or "").strip(),
                }
                aliases.update(_session_aliases(linkage.get("session") if isinstance(linkage.get("session"), dict) else None))
                for alias in {value for value in aliases if value}:
                    current = linkage_index.get(alias)
                    if not current or meta["updatedAt"] >= current.get("updatedAt", ""):
                        linkage_index[alias] = meta

    logical_sessions: dict[str, dict] = {}
    for session in all_sessions():
        if not isinstance(session, dict) or session.get("archived"):
            continue
        lineage_root = str(session.get("_lineage_root_id") or session.get("session_id") or "").strip()
        if not lineage_root:
            continue
        current = logical_sessions.get(lineage_root)
        if not current or _session_sort_key(session) >= _session_sort_key(current):
            logical_sessions[lineage_root] = dict(session)

    grouped_sessions: dict[str, list[dict]] = {}
    ungrouped: list[dict] = []
    for session in sorted(logical_sessions.values(), key=_session_sort_key, reverse=True):
        meta = None
        for alias in _session_aliases(session):
            if alias in linkage_index:
                meta = linkage_index[alias]
                break
        project = meta.get("project") if meta else None
        task = meta.get("task") if meta else None
        run = meta.get("run") if meta else None
        if str(session.get("source_tag") or "").strip() == OPS_TASK_SOURCE_TAG and not task:
            continue
        if not project:
            for candidate in projects:
                if _session_matches_project(session, candidate):
                    project = candidate
                    break
        enriched = _enrich_session_summary(session, project, task, run)
        if project and str(project.get("id") or "").strip():
            grouped_sessions.setdefault(str(project.get("id") or "").strip(), []).append(enriched)
        else:
            ungrouped.append(enriched)

    groups = []
    for project in projects:
        pid = str(project.get("id") or "").strip()
        sessions = sorted(grouped_sessions.get(pid, []), key=_session_sort_key, reverse=True)
        if not sessions:
            continue
        waiting_count = sum(1 for session in sessions if session.get("waitingForApproval") or session.get("waitingForInput"))
        pending_request_count = sum(int(session.get("ops_pending_request_count") or 0) for session in sessions)
        groups.append(
            {
                "key": f"project:{pid}",
                "groupType": "activity",
                "projectId": pid,
                "project": project,
                "label": str(project.get("fullName") or project.get("name") or pid).strip() or pid,
                "contextLabel": str(project.get("coreBranch") or "").strip(),
                "sessions": sessions,
                "sessionCount": len(sessions),
                "activeCount": len(sessions),
                "pendingRequestCount": pending_request_count,
                "waitingCount": waiting_count,
                "latestUpdatedAt": max((_session_sort_key(session) for session in sessions), default=0.0),
            }
        )

    groups.sort(
        key=lambda group: (
            float(group.get("latestUpdatedAt") or 0.0),
            str(group.get("label") or ""),
        ),
        reverse=True,
    )
    ungrouped.sort(key=_session_sort_key, reverse=True)
    sessions = []
    for group in groups:
        sessions.extend(group.get("sessions") or [])
    sessions.extend(ungrouped)
    return {"sessions": sessions, "groups": groups, "ungrouped": ungrouped}


def launch_task_session(project_id: str, task_id: str, body: dict | None = None) -> dict:
    resolved = ops_projects.get_ops_project_task(project_id, task_id)
    project = resolved["project"]
    task = resolved["task"]
    requested_profile = _payload_profile(body)
    profile = requested_profile or _project_profile(project)
    model, model_provider = _payload_session_defaults(body)
    if not model:
        if requested_profile:
            model, model_provider = _profile_config_defaults(requested_profile)
        else:
            model, model_provider = _project_session_defaults(project)

    session = new_session(
        workspace=_task_workspace(project),
        model=model,
        model_provider=model_provider,
        profile=profile,
        project_id=project["id"],
    )
    session.title = _task_session_title(project, task)
    session.source_tag = OPS_TASK_SOURCE_TAG
    session.source_label = OPS_TASK_SOURCE_LABEL
    session.save()

    from api import ops_runs

    run = ops_runs.create_task_run(project["id"], task["id"], session.session_id, title=session.title)
    linkage = session_sidecars.set_session_linkage(
        session.session_id,
        project["id"],
        task["id"],
        run_id=str(run.get("id") or ""),
    )
    task_update = ops_projects.update_ops_project_task(
        project["id"],
        task["id"],
        {
            "inProgress": True,
            "startedAt": str(task.get("startedAt") or "").strip() or ops_projects._now_iso(),
            "lastSessionAt": ops_projects._now_iso(),
        },
    )["task"]
    return {
        "project": project,
        "task": task_update,
        "session": session.compact() | {"messages": session.messages},
        "sessionUrl": session_url(session.session_id),
        "linkage": linkage,
        "run": run,
        "runUrl": ops_runs.run_url(str(run.get("id") or "")),
    }


def close_task_session(project_id: str, task_id: str, body: dict | None = None) -> dict:
    payload = body if isinstance(body, dict) else {}
    task_payload = ops_projects.read_ops_project_tasks(project_id)
    requested_session_id = str(payload.get("sessionId") or payload.get("session_id") or "").strip()

    target_task = None
    for epic in task_payload.get("epics") or []:
        for task in epic.get("tasks") or []:
            if str(task.get("id") or "").strip() == str(task_id or "").strip():
                target_task = task
                break
        if target_task:
            break
    if not isinstance(target_task, dict):
        raise OpsSessionError("Task not found.", 404)

    linkages = list(target_task.get("linkedSessions") or [])
    selected_linkage = None
    if requested_session_id:
        for linkage in linkages:
            aliases = {
                str(linkage.get("sessionId") or "").strip(),
                str(linkage.get("linkedSessionId") or "").strip(),
            }
            aliases.update(_session_aliases(linkage.get("session") if isinstance(linkage.get("session"), dict) else None))
            if requested_session_id in aliases:
                selected_linkage = linkage
                break
    if not selected_linkage and linkages:
        selected_linkage = linkages[0]

    resolved_session_id = str((selected_linkage or {}).get("sessionId") or "").strip()
    if not resolved_session_id and requested_session_id:
        resolved_session_id = session_sidecars.resolve_session_id(requested_session_id) or requested_session_id
    if not resolved_session_id:
        raise OpsSessionError("Session not found.", 404)

    try:
        session = get_session(resolved_session_id)
    except KeyError as exc:
        raise OpsSessionError("Session not found.", 404) from exc

    session.archived = True
    session.save(touch_updated_at=False)

    updated_task = ops_projects.update_ops_project_task(
        project_id,
        task_id,
        {
            "inProgress": False,
            "lastSessionAt": ops_projects._now_iso(),
        },
    )["task"]

    run = None
    run_id = str((selected_linkage or {}).get("runId") or "").strip()
    if run_id:
        try:
            from api import ops_runs

            run = ops_runs.update_ops_run(
                run_id,
                {
                    "status": "stopped",
                    "summary": "Session closed from the ops dashboard.",
                    "completedAt": ops_projects._now_iso(),
                },
            )
        except Exception:
            run = None

    return {
        "ok": True,
        "sessionId": resolved_session_id,
        "sessionUrl": session_url(resolved_session_id),
        "task": updated_task,
        "run": run,
    }


def complete_task_session(project_id: str, task_id: str, body: dict | None = None) -> dict:
    payload = body if isinstance(body, dict) else {}
    requested_session_id = str(payload.get("sessionId") or payload.get("session_id") or "").strip()
    closed = None
    try:
        if requested_session_id:
            closed = close_task_session(project_id, task_id, {"sessionId": requested_session_id})
        else:
            closed = close_task_session(project_id, task_id, {})
    except OpsSessionError:
        closed = None

    updated_task = ops_projects.update_ops_project_task(
        project_id,
        task_id,
        {
            "done": True,
            "qaStatus": "",
            "moreWork": "",
            "inProgress": False,
            "completedAt": ops_projects._now_iso(),
        },
    )["task"]

    run = None
    if isinstance(closed, dict):
        run = closed.get("run")
        run_id = str((run or {}).get("id") or "").strip()
        if run_id:
            try:
                from api import ops_runs

                run = ops_runs.update_ops_run(
                    run_id,
                    {
                        "status": "succeeded",
                        "summary": "Task completed from the ops dashboard.",
                        "completedAt": ops_projects._now_iso(),
                    },
                )
            except Exception:
                pass

    return {"ok": True, "task": updated_task, "run": run}

"""Fork-owned task session launch helpers for the clean restart branch."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from api import ops_projects, session_sidecars
from api.models import new_session


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


def launch_task_session(project_id: str, task_id: str) -> dict:
    resolved = ops_projects.get_ops_project_task(project_id, task_id)
    project = resolved["project"]
    task = resolved["task"]

    session = new_session(
        workspace=_task_workspace(project),
        profile=project.get("profile") or None,
    )
    session.title = _task_session_title(project, task)
    session.source_tag = OPS_TASK_SOURCE_TAG
    session.source_label = OPS_TASK_SOURCE_LABEL
    session.save()

    linkage = session_sidecars.set_session_linkage(session.session_id, project["id"], task["id"])
    return {
        "project": project,
        "task": task,
        "session": session.compact() | {"messages": session.messages},
        "sessionUrl": session_url(session.session_id),
        "linkage": linkage,
    }

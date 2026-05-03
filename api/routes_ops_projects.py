"""Fork-owned project and task routes for the clean restart branch."""

from __future__ import annotations

import re

from api.helpers import j
from api import ops_projects, ops_sessions


_PROJECTS_RE = re.compile(r"^/api/ops/projects/?$")
_PROJECT_RE = re.compile(r"^/api/ops/projects/([^/]+)/?$")
_PROJECT_UPDATE_RE = re.compile(r"^/api/ops/projects/([^/]+)/update/?$")
_PROJECT_TASKS_RE = re.compile(r"^/api/ops/projects/([^/]+)/tasks/?$")
_PROJECT_EPICS_RE = re.compile(r"^/api/ops/projects/([^/]+)/epics/?$")
_PROJECT_TASK_UPDATE_RE = re.compile(r"^/api/ops/projects/([^/]+)/tasks/([^/]+)/update/?$")
_PROJECT_TASK_SESSION_LAUNCH_RE = re.compile(r"^/api/ops/projects/([^/]+)/tasks/([^/]+)/sessions/launch/?$")


def handle_get(handler, parsed) -> bool:
    try:
        if _PROJECTS_RE.match(parsed.path):
            j(handler, ops_projects.list_ops_projects())
            return True

        match = _PROJECT_RE.match(parsed.path)
        if match:
            j(handler, {"project": ops_projects.get_ops_project(match.group(1))})
            return True

        match = _PROJECT_TASKS_RE.match(parsed.path)
        if match:
            j(handler, ops_projects.read_ops_project_tasks(match.group(1)))
            return True

        return False
    except (ops_projects.OpsProjectError, ops_sessions.OpsSessionError) as exc:
        j(handler, {"error": str(exc)}, status=exc.status)
        return True


def handle_post(handler, parsed, body: dict) -> bool:
    try:
        if _PROJECTS_RE.match(parsed.path):
            j(handler, {"project": ops_projects.create_ops_project(body)}, status=201)
            return True

        match = _PROJECT_UPDATE_RE.match(parsed.path)
        if match:
            j(handler, ops_projects.update_ops_project(match.group(1), body))
            return True

        match = _PROJECT_EPICS_RE.match(parsed.path)
        if match:
            j(handler, ops_projects.add_ops_project_epic(match.group(1), body.get("title")), status=201)
            return True

        match = _PROJECT_TASKS_RE.match(parsed.path)
        if match:
            j(
                handler,
                ops_projects.add_ops_project_task(
                    match.group(1),
                    body.get("epicId"),
                    body.get("text"),
                    dependencies=body.get("dependencies"),
                    grade=body.get("grade"),
                    markers=body.get("markers"),
                    flags=body.get("flags"),
                ),
                status=201,
            )
            return True

        match = _PROJECT_TASK_UPDATE_RE.match(parsed.path)
        if match:
            j(handler, ops_projects.update_ops_project_task(match.group(1), match.group(2), body))
            return True

        match = _PROJECT_TASK_SESSION_LAUNCH_RE.match(parsed.path)
        if match:
            j(handler, ops_sessions.launch_task_session(match.group(1), match.group(2)), status=201)
            return True

        return False
    except (ops_projects.OpsProjectError, ops_sessions.OpsSessionError) as exc:
        j(handler, {"error": str(exc)}, status=exc.status)
        return True

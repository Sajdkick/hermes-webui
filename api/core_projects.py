"""Shell-neutral project, task, and safe project-file facade for Core API."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from api import ops_projects
from api.core_contracts import CoreApiError, coerce_core_error, project_root, redact_payload, relative_to_project, safe_project_child
from api.helpers import _redact_text

MAX_PROJECT_FILE_READ_BYTES = 512 * 1024
MAX_PROJECT_FILE_LIST_ENTRIES = 500

ProjectCoreError = CoreApiError


def _wrap(fn, *args, **kwargs):
    try:
        return redact_payload(fn(*args, **kwargs))
    except ops_projects.OpsProjectError as exc:
        raise coerce_core_error(exc, code="PROJECT_ERROR") from exc


def list_projects() -> dict:
    return _wrap(ops_projects.list_ops_projects)


def get_project(project_id: str) -> dict:
    return _wrap(ops_projects.get_ops_project, project_id)


def create_project(body: dict | None) -> dict:
    return _wrap(ops_projects.create_ops_project, body or {})


def update_project(project_id: str, body: dict | None) -> dict:
    return _wrap(ops_projects.update_ops_project, project_id, body or {})


def set_project_activity(project_id: str, active: Any) -> dict:
    return _wrap(ops_projects.set_ops_project_activity, project_id, active)


def delete_project(project_id: str) -> dict:
    return _wrap(ops_projects.delete_ops_project, project_id)


def ensure_project_workspace(project_id: str) -> dict:
    return _wrap(ops_projects.ensure_ops_project_workspace, project_id)


def read_project_tasks(project_id: str) -> dict:
    return _wrap(ops_projects.read_ops_project_tasks, project_id)


def ensure_project_epic(project_id: str, title: str) -> dict:
    return _wrap(ops_projects.ensure_ops_project_epic, project_id, title)


def add_project_epic(project_id: str, title: str) -> dict:
    return _wrap(ops_projects.add_ops_project_epic, project_id, title)


def add_project_task(project_id: str, body: dict | None) -> dict:
    payload = body if isinstance(body, dict) else {}
    return _wrap(
        ops_projects.add_ops_project_task,
        project_id,
        payload.get("epicId"),
        payload.get("text"),
        dependencies=payload.get("dependencies"),
        grade=payload.get("grade"),
        markers=payload.get("markers"),
        flags=payload.get("flags"),
    )


def update_project_task(project_id: str, task_id: str, body: dict | None) -> dict:
    return _wrap(ops_projects.update_ops_project_task, project_id, task_id, body or {})


def delete_project_task(project_id: str, task_id: str) -> dict:
    return _wrap(ops_projects.delete_ops_project_task, project_id, task_id)


def delete_project_epic(project_id: str, epic_id: str) -> dict:
    return _wrap(ops_projects.delete_ops_project_epic, project_id, epic_id)


def archive_completed_project_tasks(project_id: str) -> dict:
    return _wrap(ops_projects.archive_completed_ops_project_tasks, project_id)


def add_project_task_image(project_id: str, task_id: str, body: dict | None) -> dict:
    return _wrap(ops_projects.add_ops_project_task_image, project_id, task_id, body or {})


def _file_entry(project: dict, path: Path) -> dict:
    stat = path.stat()
    rel = relative_to_project(project, path)
    return {
        "name": path.name,
        "path": rel,
        "kind": "directory" if path.is_dir() else "file",
        "size": stat.st_size if path.is_file() else None,
        "modifiedAt": stat.st_mtime,
        "mimeType": mimetypes.guess_type(path.name)[0] or "application/octet-stream" if path.is_file() else None,
    }


def list_project_files(project_id: str, relative_path: str = "") -> dict:
    project = get_project(project_id)
    target = safe_project_child(project, relative_path)
    if not target.exists():
        raise CoreApiError("Project path not found.", 404, code="PROJECT_FILE_NOT_FOUND")
    if not target.is_dir():
        raise CoreApiError("Project path is not a directory.", 400, code="PROJECT_FILE_NOT_DIRECTORY")
    entries = []
    try:
        children = sorted(target.iterdir(), key=lambda child: (not child.is_dir(), child.name.lower()))
    except OSError as exc:
        raise CoreApiError("Unable to list project directory.", 500, code="PROJECT_FILE_LIST_FAILED") from exc
    for child in children[:MAX_PROJECT_FILE_LIST_ENTRIES]:
        try:
            entries.append(_file_entry(project, child))
        except OSError:
            continue
    return redact_payload({
        "projectId": project["id"],
        "root": str(project_root(project)),
        "path": relative_to_project(project, target),
        "entries": entries,
        "truncated": len(children) > MAX_PROJECT_FILE_LIST_ENTRIES,
    })


def read_project_file(project_id: str, relative_path: str, *, max_bytes: int = MAX_PROJECT_FILE_READ_BYTES) -> dict:
    project = get_project(project_id)
    target = safe_project_child(project, relative_path)
    if not target.exists():
        raise CoreApiError("Project file not found.", 404, code="PROJECT_FILE_NOT_FOUND")
    if not target.is_file():
        raise CoreApiError("Project path is not a file.", 400, code="PROJECT_FILE_NOT_FILE")
    try:
        size = target.stat().st_size
    except OSError as exc:
        raise CoreApiError("Unable to stat project file.", 500, code="PROJECT_FILE_READ_FAILED") from exc
    limit = max(1, min(int(max_bytes or MAX_PROJECT_FILE_READ_BYTES), MAX_PROJECT_FILE_READ_BYTES))
    try:
        raw = target.read_bytes()[: limit + 1]
    except OSError as exc:
        raise CoreApiError("Unable to read project file.", 500, code="PROJECT_FILE_READ_FAILED") from exc
    truncated = len(raw) > limit or size > limit
    raw = raw[:limit]
    try:
        text = raw.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        raise CoreApiError("Binary project files are not returned by the Core API.", 415, code="PROJECT_FILE_BINARY")
    return redact_payload({
        "projectId": project["id"],
        "path": relative_to_project(project, target),
        "size": size,
        "truncated": truncated,
        "encoding": encoding,
        "mimeType": mimetypes.guess_type(target.name)[0] or "text/plain",
        "content": _redact_text(text),
    })

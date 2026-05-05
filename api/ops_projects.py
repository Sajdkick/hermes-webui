"""Fork-owned Phase 2 project and task registry for the clean restart branch."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from urllib.parse import quote
import uuid
from datetime import datetime, timezone

from api.config import REPO_ROOT
from api.workspace import load_workspaces, save_workspaces, validate_workspace_to_add


DEFAULT_CORE_BRANCH = "main"
DEFAULT_TASKS_SCOPE = "default"
DEFAULT_TASK_GRADE = "green"
TASK_GRADE_VALUES = {"green", "orange", "red"}
TASK_QA_STATUS_VALUES = {"ready-for-test", "needs-more-work", "not-synced"}
TASKS_DIR_NAME = "project_tasks"
LEGACY_TASKS_FILE_NAME = "project_tasks.json"
LEGACY_OPS_CAPABILITIES = {
    "ensureWorkspace": True,
    "projectSettings": True,
    "projectActivity": True,
    "projectDeletion": True,
    "dependencyHealth": False,
    "dependencyInstall": False,
    "inodeScan": False,
    "inodeCleanup": False,
    "deployment": False,
}


class OpsProjectError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _projects_dir() -> Path:
    explicit = (
        os.getenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR")
        or os.getenv("PROJECTS_DIR")
        or ""
    ).strip()
    if explicit:
        return Path(explicit).expanduser().resolve()

    candidates = [
        REPO_ROOT.parent,
        REPO_ROOT.parent / "projects",
        REPO_ROOT.parent / "cloud-terminal" / "projects",
    ]
    for candidate in candidates:
        if (candidate / "projects.json").exists():
            return candidate.resolve()
    return candidates[0].resolve()


def ops_projects_metadata_path() -> Path:
    return _projects_dir() / "projects.json"


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise OpsProjectError(f"{path.name} contains invalid JSON.", 500) from exc
    except OSError as exc:
        raise OpsProjectError(f"Unable to read {path.name}.", 500) from exc


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def _ensure_registry() -> None:
    metadata = ops_projects_metadata_path()
    metadata.parent.mkdir(parents=True, exist_ok=True)
    if not metadata.exists():
        _write_json(metadata, [])


def _slugify(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in str(value or "").strip())
    slug = "-".join(part for part in cleaned.split("-") if part).strip("-")
    return slug or "project"


def _unique_slug(base: str, projects: list[dict]) -> str:
    used = {str(project.get("slug") or "") for project in projects}
    slug = _slugify(base)
    if slug not in used:
        return slug
    index = 2
    while f"{slug}-{index}" in used:
        index += 1
    return f"{slug}-{index}"


def _normalize_project(project) -> tuple[dict | None, bool]:
    if not isinstance(project, dict):
        return None, True
    normalized = dict(project)
    changed = False

    if not str(normalized.get("id") or "").strip():
        normalized["id"] = str(uuid.uuid4())
        changed = True

    path = str(normalized.get("path") or "").strip()
    if not path:
        return None, True
    normalized["path"] = path

    name = str(normalized.get("name") or "").strip() or Path(path).name or normalized["id"]
    if name != normalized.get("name"):
        changed = True
    normalized["name"] = name

    full_name = str(normalized.get("fullName") or "").strip() or name
    if full_name != normalized.get("fullName"):
        changed = True
    normalized["fullName"] = full_name

    slug = str(normalized.get("slug") or "").strip() or _slugify(name)
    if slug != normalized.get("slug"):
        changed = True
    normalized["slug"] = slug

    core_branch = str(normalized.get("coreBranch") or "").strip() or DEFAULT_CORE_BRANCH
    if core_branch != normalized.get("coreBranch"):
        changed = True
    normalized["coreBranch"] = core_branch

    normalized["active"] = normalized.get("active") is not False
    if normalized.get("profile") is not None:
        profile = str(normalized.get("profile") or "").strip()
        normalized["profile"] = profile or None
    if normalized.get("defaultModel") is not None or normalized.get("default_model") is not None:
        default_model = str(normalized.get("defaultModel") or normalized.get("default_model") or "").strip()
        normalized["defaultModel"] = default_model or None
    if normalized.get("defaultModelProvider") is not None or normalized.get("default_model_provider") is not None:
        default_model_provider = str(
            normalized.get("defaultModelProvider") or normalized.get("default_model_provider") or ""
        ).strip().lower()
        normalized["defaultModelProvider"] = default_model_provider or None

    if not str(normalized.get("createdAt") or "").strip():
        normalized["createdAt"] = _now_iso()
        changed = True

    return normalized, changed


def _read_projects() -> list[dict]:
    _ensure_registry()
    metadata = ops_projects_metadata_path()
    raw = _read_json(metadata, [])
    if not isinstance(raw, list):
        raise OpsProjectError("projects.json must contain a JSON array.", 500)

    projects: list[dict] = []
    changed = False
    for entry in raw:
        normalized, entry_changed = _normalize_project(entry)
        if normalized:
            projects.append(normalized)
        if entry_changed:
            changed = True

    if changed:
        _write_json(metadata, projects)
    return projects


def _write_projects(projects: list[dict]) -> None:
    _write_json(ops_projects_metadata_path(), projects)


def _paths_equal(left: str | Path, right: str | Path) -> bool:
    try:
        return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
    except Exception:
        return str(left) == str(right)


def _project_path(project: dict, *, strict: bool = True) -> Path:
    raw = str(project.get("path") or project.get("resolvedPath") or "").strip()
    if not raw:
        raise OpsProjectError("Project path is missing.", 500)
    path = Path(raw).expanduser().resolve()
    if strict:
        if not path.exists():
            raise OpsProjectError(f"Project path does not exist: {path}", 404)
        if not path.is_dir():
            raise OpsProjectError(f"Project path is not a directory: {path}", 400)
    return path


def _run_git(repo_path: Path, args: list[str], *, timeout: int = 8) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(repo_path),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return ""
    except subprocess.TimeoutExpired:
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _current_branch(project_path: Path) -> str | None:
    branch = _run_git(project_path, ["rev-parse", "--abbrev-ref", "HEAD"])
    if not branch or branch == "HEAD":
        return None
    return branch


def _project_core_branch(project: dict) -> str:
    return str(project.get("coreBranch") or "").strip() or DEFAULT_CORE_BRANCH


def tasks_branch(project: dict) -> str:
    try:
        project_path = _project_path(project)
    except OpsProjectError:
        return _project_core_branch(project)
    return _current_branch(project_path) or _project_core_branch(project)


def _sanitize_branch_file_name(branch: str) -> str:
    trimmed = str(branch or "").strip()
    if not trimmed:
        return DEFAULT_TASKS_SCOPE
    encoded = quote(trimmed, safe="")
    if encoded in {"", ".", ".."}:
        return DEFAULT_TASKS_SCOPE
    return encoded


def tasks_file_path(project: dict) -> Path:
    return _project_path(project, strict=False) / TASKS_DIR_NAME / f"{_sanitize_branch_file_name(tasks_branch(project))}.json"


def ensure_tasks_file(project: dict) -> Path:
    task_file = tasks_file_path(project)
    if task_file.exists():
        return task_file
    task_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file = _project_path(project) / LEGACY_TASKS_FILE_NAME
    if legacy_file.exists():
        task_file.write_text(legacy_file.read_text(encoding="utf-8"), encoding="utf-8")
        return task_file
    _write_json(task_file, {"epics": []})
    return task_file


def _normalize_string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _normalize_task_qa_status(value) -> str:
    return str(value or "").strip().lower().replace("_", "-").replace(" ", "-")


def _normalize_task(task) -> tuple[dict | None, bool]:
    if not isinstance(task, dict):
        return None, True
    normalized = dict(task)
    changed = False

    if not str(normalized.get("id") or "").strip():
        normalized["id"] = str(uuid.uuid4())
        changed = True

    text = str(normalized.get("text") or "").strip()
    if not text:
        return None, True
    if text != normalized.get("text"):
        changed = True
    normalized["text"] = text

    normalized["done"] = bool(normalized.get("done"))
    normalized["dependencies"] = _normalize_string_list(normalized.get("dependencies"))

    grade = str(normalized.get("grade") or "").strip().lower()
    if grade not in TASK_GRADE_VALUES:
        grade = DEFAULT_TASK_GRADE
        changed = True
    normalized["grade"] = grade

    if not str(normalized.get("createdAt") or "").strip():
        normalized["createdAt"] = _now_iso()
        changed = True

    return normalized, changed


def _normalize_epic(epic) -> tuple[dict | None, bool]:
    if not isinstance(epic, dict):
        return None, True
    normalized = dict(epic)
    changed = False

    if not str(normalized.get("id") or "").strip():
        normalized["id"] = str(uuid.uuid4())
        changed = True

    title = str(normalized.get("title") or "").strip()
    if not title:
        return None, True
    if title != normalized.get("title"):
        changed = True
    normalized["title"] = title

    tasks = []
    for entry in normalized.get("tasks") or []:
        task, task_changed = _normalize_task(entry)
        if task:
            tasks.append(task)
        if task_changed:
            changed = True
    normalized["tasks"] = tasks
    return normalized, changed


def _normalize_tasks_payload(payload) -> tuple[dict, bool]:
    if not isinstance(payload, dict):
        payload = {}
        changed = True
    else:
        changed = False
    epics = []
    for entry in payload.get("epics") or []:
        epic, epic_changed = _normalize_epic(entry)
        if epic:
            epics.append(epic)
        if epic_changed:
            changed = True
    return {"epics": epics}, changed


def _read_tasks_data(project: dict) -> tuple[dict, Path, str]:
    task_file = ensure_tasks_file(project)
    payload = _read_json(task_file, {"epics": []})
    normalized, changed = _normalize_tasks_payload(payload)
    if changed:
        _write_json(task_file, normalized)
    return normalized, task_file, tasks_branch(project)


def _write_tasks_data(project: dict, payload: dict) -> dict:
    task_file = ensure_tasks_file(project)
    normalized, _ = _normalize_tasks_payload(payload)
    _write_json(task_file, normalized)
    return normalized


def _task_counts(project: dict) -> dict:
    try:
        payload, task_file, branch = _read_tasks_data(project)
        epics = payload.get("epics") or []
        return {
            "tasksBranch": branch,
            "tasksFilePath": str(task_file),
            "epicCount": len(epics),
            "taskCount": sum(len(epic.get("tasks") or []) for epic in epics),
        }
    except OpsProjectError as exc:
        return {
            "tasksBranch": tasks_branch(project),
            "tasksFilePath": str(tasks_file_path(project)),
            "epicCount": 0,
            "taskCount": 0,
            "pathError": str(exc),
        }


def _serialize_project(project: dict) -> dict:
    serialized = dict(project)
    serialized["resolvedPath"] = str(_project_path(project, strict=False))
    serialized["opsCapabilities"] = dict(LEGACY_OPS_CAPABILITIES)
    serialized.update(_task_counts(project))
    return serialized


def list_ops_projects() -> dict:
    projects = [_serialize_project(project) for project in _read_projects()]
    projects.sort(key=lambda project: (project.get("active") is False, str(project.get("name") or "").lower()))
    return {
        "projects": projects,
        "projectsDir": str(_projects_dir()),
        "metadataPath": str(ops_projects_metadata_path()),
    }


def get_ops_project(project_id: str) -> dict:
    key = str(project_id or "").strip()
    if not key:
        raise OpsProjectError("Project id is required.")
    project = next((entry for entry in _read_projects() if entry.get("id") == key), None)
    if not project:
        raise OpsProjectError("Project not found.", 404)
    return _serialize_project(project)


def _ensure_workspace(project_path: Path, name: str) -> None:
    workspaces = load_workspaces()
    if any(_paths_equal(entry.get("path", ""), project_path) for entry in workspaces):
        return
    workspaces.append({"path": str(project_path), "name": name})
    save_workspaces(workspaces)


def ensure_ops_project_workspace(project_id: str) -> dict:
    project = get_ops_project(project_id)
    _ensure_workspace(_project_path(project), str(project.get("name") or project.get("id") or "Project"))
    return {"ok": True, "project": get_ops_project(project_id)}


def _validate_project_profile(profile: str | None) -> str | None:
    value = str(profile or "").strip()
    if not value or value == "default":
        return value or None
    try:
        from api.profiles import get_hermes_home_for_profile
    except ImportError:
        return value
    if not get_hermes_home_for_profile(value).exists():
        raise OpsProjectError(f"Profile not found: {value}")
    return value


def create_ops_project(body: dict) -> dict:
    name = str((body or {}).get("name") or "").strip()[:128]
    if not name:
        raise OpsProjectError("Project name is required.")

    raw_path = str((body or {}).get("path") or "").strip()
    if not raw_path:
        raise OpsProjectError("Project path is required.")
    try:
        project_path = validate_workspace_to_add(raw_path)
    except ValueError as exc:
        raise OpsProjectError(str(exc)) from exc

    projects = _read_projects()
    if any(_paths_equal(entry.get("path", ""), project_path) for entry in projects):
        raise OpsProjectError("A project for that path already exists.", 409)

    core_branch = str((body or {}).get("coreBranch") or DEFAULT_CORE_BRANCH).strip() or DEFAULT_CORE_BRANCH
    full_name = str((body or {}).get("fullName") or name).strip() or name
    project = {
        "id": str(uuid.uuid4()),
        "name": name,
        "fullName": full_name,
        "slug": _unique_slug(str((body or {}).get("slug") or name), projects),
        "path": str(project_path),
        "coreBranch": core_branch,
        "createdAt": _now_iso(),
        "active": True,
        "profile": _validate_project_profile((body or {}).get("profile")),
        "defaultModel": str((body or {}).get("defaultModel") or "").strip() or None,
        "defaultModelProvider": str((body or {}).get("defaultModelProvider") or "").strip().lower() or None,
    }
    clone_url = str((body or {}).get("cloneUrl") or "").strip()
    if clone_url:
        project["cloneUrl"] = clone_url

    ensure_tasks_file(project)
    projects.append(project)
    _write_projects(projects)
    _ensure_workspace(project_path, name)
    return _serialize_project(project)


def update_ops_project(project_id: str, body: dict | None) -> dict:
    project = get_ops_project(project_id)
    body = body if isinstance(body, dict) else {}
    projects = _read_projects()
    index = next((idx for idx, entry in enumerate(projects) if entry.get("id") == project["id"]), -1)
    if index < 0:
        raise OpsProjectError("Project not found.", 404)

    updated = dict(projects[index])
    if "profile" in body:
        updated["profile"] = _validate_project_profile(body.get("profile"))
    if "defaultModel" in body:
        updated["defaultModel"] = str(body.get("defaultModel") or "").strip() or None
    if "defaultModelProvider" in body:
        updated["defaultModelProvider"] = str(body.get("defaultModelProvider") or "").strip().lower() or None

    projects[index] = updated
    _write_projects(projects)
    return {"project": _serialize_project(updated)}


def set_ops_project_activity(project_id: str, active: bool) -> dict:
    project = get_ops_project(project_id)
    projects = _read_projects()
    index = next((idx for idx, entry in enumerate(projects) if entry.get("id") == project["id"]), -1)
    if index < 0:
        raise OpsProjectError("Project not found.", 404)

    updated = dict(projects[index])
    updated["active"] = bool(active)
    updated["updatedAt"] = _now_iso()
    projects[index] = updated
    _write_projects(projects)
    serialized = _serialize_project(updated)
    return {"ok": True, "project": serialized, "activity": {"active": serialized["active"]}}


def delete_ops_project(project_id: str) -> dict:
    project = get_ops_project(project_id)
    projects = _read_projects()
    remaining = [entry for entry in projects if entry.get("id") != project["id"]]
    if len(remaining) == len(projects):
        raise OpsProjectError("Project not found.", 404)
    _write_projects(remaining)
    return {"ok": True, "projects": [_serialize_project(entry) for entry in remaining]}


def read_ops_project_tasks(project_id: str) -> dict:
    project = get_ops_project(project_id)
    payload, task_file, branch = _read_tasks_data(project)
    from api import session_sidecars

    linkage_map = session_sidecars.task_linkage_map(project["id"])
    epics = []
    for epic in payload.get("epics") or []:
        tasks = []
        for task in epic.get("tasks") or []:
            tasks.append({**task, "linkedSessions": linkage_map.get(str(task.get("id") or ""), [])})
        epics.append({**epic, "tasks": tasks})
    return {
        **payload,
        "epics": epics,
        "project": project,
        "branch": branch,
        "tasksFile": str(task_file),
        "tasksFilePath": str(task_file),
    }


def add_ops_project_epic(project_id: str, title: str) -> dict:
    project = get_ops_project(project_id)
    trimmed = str(title or "").strip()
    if not trimmed:
        raise OpsProjectError("Epic title is required.")
    data, _, _ = _read_tasks_data(project)
    epic = {"id": str(uuid.uuid4()), "title": trimmed, "tasks": []}
    _write_tasks_data(project, {**data, "epics": [*(data.get("epics") or []), epic]})
    return {"epic": epic}


def add_ops_project_task(project_id: str, epic_id: str, text: str, dependencies=None, grade=None, markers=None, flags=None) -> dict:
    project = get_ops_project(project_id)
    epic_key = str(epic_id or "").strip()
    if not epic_key:
        raise OpsProjectError("Epic id is required.")
    trimmed = str(text or "").strip()
    if not trimmed:
        raise OpsProjectError("Task text is required.")

    data, _, _ = _read_tasks_data(project)
    epics = list(data.get("epics") or [])
    epic_index = next((index for index, epic in enumerate(epics) if epic.get("id") == epic_key), -1)
    if epic_index < 0:
        raise OpsProjectError("Epic not found.", 404)

    task_ids = {
        task.get("id")
        for epic in epics
        for task in epic.get("tasks") or []
        if task.get("id")
    }
    normalized_grade = str(grade or "").strip().lower() or DEFAULT_TASK_GRADE
    if normalized_grade not in TASK_GRADE_VALUES:
        raise OpsProjectError("Task grade is invalid.")
    task = {
        "id": str(uuid.uuid4()),
        "text": trimmed,
        "done": False,
        "dependencies": [dep for dep in _normalize_string_list(dependencies) if dep in task_ids],
        "grade": normalized_grade,
        "createdAt": _now_iso(),
    }
    normalized_markers = _normalize_string_list(markers)
    normalized_flags = _normalize_string_list(flags)
    if normalized_markers:
        task["markers"] = normalized_markers
    if normalized_flags:
        task["flags"] = normalized_flags

    target_epic = dict(epics[epic_index])
    target_epic["tasks"] = [*(target_epic.get("tasks") or []), task]
    epics[epic_index] = target_epic
    _write_tasks_data(project, {**data, "epics": epics})
    return {"epicId": epic_key, "task": task}


def _find_task(epics: list[dict], task_id: str) -> tuple[int, int]:
    for epic_index, epic in enumerate(epics):
        for task_index, task in enumerate(epic.get("tasks") or []):
            if task.get("id") == task_id:
                return epic_index, task_index
    return -1, -1


def get_ops_project_task(project_id: str, task_id: str) -> dict:
    project = get_ops_project(project_id)
    task_key = str(task_id or "").strip()
    if not task_key:
        raise OpsProjectError("Task id is required.")
    data, _, _ = _read_tasks_data(project)
    epics = list(data.get("epics") or [])
    epic_index, task_index = _find_task(epics, task_key)
    if epic_index < 0:
        raise OpsProjectError("Task not found.", 404)
    epic = epics[epic_index]
    task = dict((epic.get("tasks") or [])[task_index])
    return {"project": project, "epicId": epic.get("id"), "task": task}


def update_ops_project_task(project_id: str, task_id: str, updates: dict) -> dict:
    project = get_ops_project(project_id)
    task_key = str(task_id or "").strip()
    if not task_key:
        raise OpsProjectError("Task id is required.")

    data, _, _ = _read_tasks_data(project)
    epics = list(data.get("epics") or [])
    epic_index, task_index = _find_task(epics, task_key)
    if epic_index < 0:
        raise OpsProjectError("Task not found.", 404)

    source_epic = dict(epics[epic_index])
    updated_task = dict((source_epic.get("tasks") or [])[task_index])
    updates = updates or {}

    if "text" in updates:
        text = str(updates.get("text") or "").strip()
        if not text:
            raise OpsProjectError("Task text is required.")
        updated_task["text"] = text

    if "done" in updates:
        updated_task["done"] = bool(updates.get("done"))

    if "grade" in updates:
        grade = str(updates.get("grade") or "").strip().lower()
        if grade not in TASK_GRADE_VALUES:
            raise OpsProjectError("Task grade is invalid.")
        updated_task["grade"] = grade

    if "dependencies" in updates:
        task_ids = {
            task.get("id")
            for epic in epics
            for task in epic.get("tasks") or []
            if task.get("id") and task.get("id") != task_key
        }
        updated_task["dependencies"] = [
            dep for dep in _normalize_string_list(updates.get("dependencies")) if dep in task_ids
        ]

    for field in ("markers", "flags"):
        if field in updates:
            normalized = _normalize_string_list(updates.get(field))
            if normalized:
                updated_task[field] = normalized
            else:
                updated_task.pop(field, None)

    if "qaStatus" in updates:
        qa_status = _normalize_task_qa_status(updates.get("qaStatus"))
        if qa_status and qa_status not in TASK_QA_STATUS_VALUES:
            raise OpsProjectError("Task QA status is invalid.")
        if qa_status:
            updated_task["qaStatus"] = qa_status
        else:
            updated_task.pop("qaStatus", None)

    for field in ("moreWork", "sessionId", "lastSessionAt", "startedAt", "completedAt", "archivedAt", "images"):
        if field not in updates:
            continue
        value = updates.get(field)
        if field == "images":
            normalized = ", ".join(_normalize_string_list(value))
            if normalized:
                updated_task[field] = normalized
            else:
                updated_task.pop(field, None)
            continue
        text = str(value or "").strip()
        if text:
            updated_task[field] = text
        else:
            updated_task.pop(field, None)

    for field in ("inProgress", "archived"):
        if field not in updates:
            continue
        if bool(updates.get(field)):
            updated_task[field] = True
        else:
            updated_task.pop(field, None)

    if updated_task.get("done") and not str(updated_task.get("completedAt") or "").strip():
        updated_task["completedAt"] = _now_iso()

    tasks = list(source_epic.get("tasks") or [])
    tasks[task_index] = updated_task
    source_epic["tasks"] = tasks
    epics[epic_index] = source_epic
    _write_tasks_data(project, {**data, "epics": epics})
    return {"task": updated_task}


def promote_not_synced_tasks_to_ready_for_test(project_id: str) -> dict:
    project = get_ops_project(project_id)
    data, _, _ = _read_tasks_data(project)
    updated_count = 0
    updated_task_ids: list[str] = []
    updated_epics: list[dict] = []
    touched_any = False

    for epic in data.get("epics") or []:
        tasks = []
        touched_epic = False
        for task in epic.get("tasks") or []:
            if bool(task.get("done")) or _normalize_task_qa_status(task.get("qaStatus")) != "not-synced":
                tasks.append(task)
                continue
            updated_task = dict(task)
            updated_task["qaStatus"] = "ready-for-test"
            updated_task.pop("inProgress", None)
            updated_task.pop("moreWork", None)
            task_id = str(updated_task.get("id") or "").strip()
            if task_id:
                updated_task_ids.append(task_id)
            updated_count += 1
            touched_epic = True
            tasks.append(updated_task)
        if touched_epic:
            touched_any = True
            updated_epics.append({**epic, "tasks": tasks})
        else:
            updated_epics.append(epic)

    if touched_any:
        _write_tasks_data(project, {**data, "epics": updated_epics})

    return {"updatedCount": updated_count, "updatedTaskIds": updated_task_ids}


def delete_ops_project_task(project_id: str, task_id: str) -> dict:
    project = get_ops_project(project_id)
    task_key = str(task_id or "").strip()
    if not task_key:
        raise OpsProjectError("Task id is required.")

    data, _, _ = _read_tasks_data(project)
    epics = list(data.get("epics") or [])
    epic_index, task_index = _find_task(epics, task_key)
    if epic_index < 0:
        raise OpsProjectError("Task not found.", 404)

    source_epic = dict(epics[epic_index])
    tasks = list(source_epic.get("tasks") or [])
    deleted = dict(tasks.pop(task_index))
    source_epic["tasks"] = tasks
    epics[epic_index] = source_epic
    _write_tasks_data(project, {**data, "epics": epics})
    return {"ok": True, "task": deleted}


def delete_ops_project_epic(project_id: str, epic_id: str) -> dict:
    project = get_ops_project(project_id)
    epic_key = str(epic_id or "").strip()
    if not epic_key:
        raise OpsProjectError("Epic id is required.")

    data, _, _ = _read_tasks_data(project)
    epics = list(data.get("epics") or [])
    remaining = [dict(epic) for epic in epics if str(epic.get("id") or "").strip() != epic_key]
    if len(remaining) == len(epics):
        raise OpsProjectError("Epic not found.", 404)
    _write_tasks_data(project, {**data, "epics": remaining})
    return {"ok": True, "epics": remaining}


def archive_completed_ops_project_tasks(project_id: str) -> dict:
    project = get_ops_project(project_id)
    data, _, _ = _read_tasks_data(project)
    epics = []
    archived_count = 0
    archived_at = _now_iso()
    for epic in data.get("epics") or []:
        next_epic = dict(epic)
        next_tasks = []
        for task in epic.get("tasks") or []:
            next_task = dict(task)
            if next_task.get("done") and not next_task.get("archived"):
                next_task["archived"] = True
                next_task["archivedAt"] = archived_at
                archived_count += 1
            next_tasks.append(next_task)
        next_epic["tasks"] = next_tasks
        epics.append(next_epic)
    _write_tasks_data(project, {**data, "epics": epics})
    return {"ok": True, "archived": archived_count}

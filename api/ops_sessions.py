"""Fork-owned task session launch helpers for the clean restart branch."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import yaml

from api.config import get_effective_default_model
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


def launch_task_session(project_id: str, task_id: str) -> dict:
    resolved = ops_projects.get_ops_project_task(project_id, task_id)
    project = resolved["project"]
    task = resolved["task"]
    profile = _project_profile(project)
    model, model_provider = _project_session_defaults(project)

    session = new_session(
        workspace=_task_workspace(project),
        model=model,
        model_provider=model_provider,
        profile=profile,
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

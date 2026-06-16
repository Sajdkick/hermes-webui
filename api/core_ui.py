"""Core UI Mode live runtime and proxy boundary.

UI Mode starts a project runtime once, exposes status/logs through /api/core, and
proxies a live preview through /ui-project/{projectId}/... so framework
HMR/live-reload can update the iframe when the project uses a dev server. For
projects with Play config, UI Mode can source the Play build/start/inspect
contract so the preview matches the Play runtime instead of using a separate dev
server path.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from api import ops_projects
from api.core_contracts import CoreApiError, now_iso, project_root, redact_payload
from api.helpers import _redact_text, t
from api.updates import WEBUI_VERSION

UI_CONFIG_FILE_NAMES = (".hermes/ui.json", ".cloud-terminal/ui.json", "project_ui.json")
AUTO_DETECTED_SOURCE_KEY = "__uiAutoSource"
AUTO_DETECTED_PARITY_SOURCE_KEY = "__uiParitySource"
UI_LOG_LINE_LIMIT = 1000
UI_MODE_BUILD_POLICY = "explicit-user-approval"
UI_READY_TIMEOUT_DEFAULT_MS = 60 * 1000
UI_READY_PATTERN = re.compile(r"(ready|listening|started|compiled|server running|running at|local:)", re.I)
UI_PROJECT_PROXY_BASE_PATH = "/ui-project"
UI_REFERER_NAVIGATION_PREFIXES = (
    "/app",
    "/login",
    "/auth",
    "/assets",
    "/api/trpc",
    "/api/blob",
    "/v2",
    "/rpc",
    "/socket",
    "/ws",
)
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

_LOCK = threading.RLock()
_BUILD_LOCK = threading.Lock()
_RESERVED_PORTS: set[tuple[str, int]] = set()
_RUNTIMES: dict[str, "UiRuntimeState"] = {}
UI_SESSION_STATE_VERSION = 1


@dataclass
class UiRuntimeState:
    project_id: str
    runtime_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str | None = None
    status: str = "idle"
    running: bool = False
    ready: bool = False
    error: str | None = None
    preview_url: str | None = None
    inspect_url: str | None = None
    config_path: str | None = None
    config_branch: str | None = None
    config_auto_detected: bool = False
    config_auto_source: str | None = None
    workflow_source: str | None = None
    play_config_path: str | None = None
    started_at: str | None = None
    ready_at: str | None = None
    finished_at: str | None = None
    updated_at: float = field(default_factory=time.time)
    stop_requested: bool = False
    process: subprocess.Popen | None = None
    pid: int | None = None
    pgid: int | None = None
    allocated_port: int | None = None
    allocated_port_host: str | None = None
    allocated_port_env_var: str | None = None
    build_command: str | None = None
    command: str | None = None
    cwd: str | None = None
    logs: list[dict] = field(default_factory=list)


class UiRuntimeError(CoreApiError):
    """Stable Core UI runtime exception shape."""

    def __init__(self, message: str, status: int = 400, *, code: str = "UI_RUNTIME_ERROR") -> None:
        super().__init__(message, status=status, code=code)


def _project_label(project: dict) -> str:
    return str(project.get("fullName") or project.get("name") or project.get("slug") or project.get("id") or "Project")


def _get_project(project_id: str) -> dict:
    try:
        return ops_projects.get_ops_project(project_id)
    except ops_projects.OpsProjectError as exc:
        raise UiRuntimeError(str(exc), status=exc.status, code="PROJECT_ERROR") from exc


def _project_path(project: dict) -> Path:
    try:
        return project_root(project)
    except CoreApiError as exc:
        raise UiRuntimeError(str(exc), status=exc.status, code=exc.code) from exc


def _project_branch(project: dict) -> str:
    try:
        return ops_projects.tasks_branch(project)
    except Exception:
        return str(project.get("coreBranch") or "main")


def _safe_state_component(value: str) -> str:
    text = str(value or "").strip()
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip(".-") or "project"
    return f"{slug[:72]}-{uuid.uuid5(uuid.NAMESPACE_URL, text or 'project').hex[:8]}"


def _ui_mode_state_root() -> Path:
    from api import config as _config

    return Path(_config.STATE_DIR).expanduser().resolve() / "ui-mode"


def _ui_mode_project_state_dir(project_id: str) -> Path:
    return _ui_mode_state_root() / "projects" / _safe_state_component(project_id)


def _ui_mode_session_state_path(project_id: str) -> Path:
    return _ui_mode_project_state_dir(project_id) / "session.json"


def _ui_mode_project_workspaces_dir(project_id: str) -> Path:
    return _ui_mode_state_root() / "workspaces" / _safe_state_component(project_id)


def _ui_mode_fast_workspace(project_id: str, session_id: str) -> Path:
    return _ui_mode_project_workspaces_dir(project_id) / _safe_state_component(session_id)


def _load_ui_mode_session_state(project_id: str) -> dict:
    path = _ui_mode_session_state_path(project_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(redact_payload(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _write_ui_mode_session_state(project_id: str, payload: dict) -> None:
    _write_json_atomic(_ui_mode_session_state_path(project_id), payload)


def _current_ui_status_metadata(project_id: str) -> dict:
    try:
        status = build_project_ui_status(project_id)
        return status if isinstance(status, dict) else {}
    except Exception:
        return {}


def _ui_session_metadata(project_id: str, project: dict, status: dict | None = None) -> dict:
    status = status if isinstance(status, dict) else {}
    source_workspace = str(_project_path(project))
    preview_url = str(status.get("previewUrl") or "").strip()
    preview_path = str(status.get("previewPath") or status.get("inspectUrl") or "").strip()
    return {
        "ui_project_id": project_id,
        "ui_project_label": _project_label(project),
        "ui_project_workspace": source_workspace,
        "ui_preview_path": preview_path,
        "ui_preview_url": preview_url,
        "ui_preview_title": str(status.get("previewTitle") or "").strip(),
        "ui_workflow_source": str(status.get("workflowSource") or status.get("configSource") or "").strip(),
        "ui_iteration_mode": str(status.get("iterationMode") or "").strip(),
        "ui_status_summary": str(status.get("statusSummary") or status.get("summary") or "").strip(),
        "ui_build_command": str(status.get("buildCommand") or "").strip(),
        "ui_runtime_command": str(status.get("command") or "").strip(),
        "ui_build_policy": UI_MODE_BUILD_POLICY,
        "ui_parity_available": "true" if status.get("parityAvailable") is True else "",
        "ui_parity_workflow_source": str(status.get("parityWorkflowSource") or "").strip(),
        "ui_parity_config_path": str(status.get("parityConfigPath") or "").strip(),
    }


def _apply_ui_session_metadata(session, metadata: dict, *, workspace: Path) -> bool:
    changed = False
    expected_workspace = str(workspace.resolve())
    if getattr(session, "workspace", None) != expected_workspace:
        session.workspace = expected_workspace
        changed = True
    if getattr(session, "session_mode", None) != "ui_mode":
        session.session_mode = "ui_mode"
        changed = True
    for key, value in (metadata or {}).items():
        if not value:
            continue
        if getattr(session, key, None) != value:
            setattr(session, key, value)
            changed = True
    return changed


def _ui_fast_agents_md(project_id: str, project: dict, source_workspace: str, context_path: Path) -> str:
    label = _project_label(project)
    return f"""# UI Mode Fast Workspace

You are working in Hermes UI Mode for **{label}** (`{project_id}`).

This generated workspace is intentionally lightweight so UI-only edits are fast.
Use `{context_path.name}` first for the current preview URL/path, selected elements,
runtime/HMR status, source workspace, and workflow commands.

## Fast iteration rules

1. Prefer real source edits through `./source` or the `sourceWorkspace` value in
   `{context_path.name}`. The source workspace is `{source_workspace}`.
2. Use the warm live preview and HMR/live reload before considering a restart.
3. Follow a fast verification budget for routine UI-only edits: source assertions,
   focused component tests, and cheap DOM/served-asset checks first. Do not run
   deploy/build scripts as the default "done" step.
4. Build policy: `{UI_MODE_BUILD_POLICY}`. For routine UI-only edits, a full
   deploy/static/production build is opt-in even when this preview is Play/static
   build sourced and your source change is not visible in the current iframe yet.
   Stop after source/test verification and offer the user: **Rebuild preview now**,
   **Leave source-only**, or **Create/apply a temporary preview patch**. Only run
   the configured build after the current user explicitly asks for that build or
   approves that offered option.
5. Runtime restart is also opt-in for routine UI-only edits. Restart only when
   dependency/config/server-runtime code changed, process state is broken, or the
   current user explicitly asks for restart/rebuild verification.
6. Use preview reload/cache busting before considering a runtime restart.
7. Keep changes scoped to the user's UI request. Avoid broad generated-bundle or
   task-metadata searches unless the user explicitly asks for build-output work.
8. If the preview is Play/static-build sourced, be transparent: report the quick
   source/test verification promptly and say live-preview visibility still needs
   an explicit rebuild instead of spending the turn on a full deploy build.
9. If a quick scratch experiment is useful, record it under `preview-patches/`
   and migrate accepted changes back to source before claiming the change is durable.
10. For visual claims, verify against the live preview/DOM state when practical.

## Generated files

- `ui-context.json` — current UI Mode project/runtime context.
- `source` — symlink/pointer to the real project source tree.
- `preview-patches/` — session-scoped scratch patch journal location.

Do not treat generated build artifacts as the source of truth.
"""


def _write_ui_fast_workspace(project_id: str, session_id: str, project: dict, status: dict | None = None) -> dict:
    workspace = _ui_mode_fast_workspace(project_id, session_id)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "preview-patches").mkdir(parents=True, exist_ok=True)
    source_workspace = str(_project_path(project))
    context_path = workspace / "ui-context.json"
    agents_path = workspace / "AGENTS.md"
    source_link = workspace / "source"
    agents_path.write_text(_ui_fast_agents_md(project_id, project, source_workspace, context_path), encoding="utf-8")

    try:
        if source_link.is_symlink() or (source_link.exists() and not source_link.is_dir()):
            source_link.unlink()
        if not source_link.exists():
            source_link.symlink_to(source_workspace, target_is_directory=True)
    except Exception:
        (workspace / "source.txt").write_text(source_workspace + "\n", encoding="utf-8")

    status = status if isinstance(status, dict) else {}
    context = {
        "version": 1,
        "mode": "ui_mode_fast_workspace",
        "projectId": project_id,
        "projectLabel": _project_label(project),
        "sourceWorkspace": source_workspace,
        "fastWorkspace": str(workspace.resolve()),
        "previewUrl": status.get("previewUrl") or "",
        "previewPath": status.get("previewPath") or status.get("inspectUrl") or "",
        "workflowSource": status.get("workflowSource") or status.get("configSource") or "",
        "statusSummary": status.get("statusSummary") or status.get("summary") or "",
        "buildCommand": status.get("buildCommand") or "",
        "runtimeCommand": status.get("command") or "",
        "buildPolicy": UI_MODE_BUILD_POLICY,
        "buildPolicySummary": "Full deploy/static/production builds are explicit user-approval only for routine UI-only edits; stop after source/test verification and offer rebuild/source-only/temporary-preview-patch options.",
        "updatedAt": now_iso(),
    }
    _write_json_atomic(context_path, context)
    return {
        "workspace": str(workspace.resolve()),
        "contextPath": str(context_path.resolve()),
        "agentsPath": str(agents_path.resolve()),
        "sourceWorkspace": source_workspace,
    }


def is_ui_mode_fast_workspace(path: str | Path | None, project_id: str | None = None) -> bool:
    if not path:
        return False
    try:
        candidate = Path(path).expanduser().resolve()
        root = (
            _ui_mode_project_workspaces_dir(project_id).resolve()
            if project_id
            else (_ui_mode_state_root() / "workspaces").resolve()
        )
        candidate.relative_to(root)
    except Exception:
        return False
    return (candidate / "ui-context.json").exists() and (candidate / "AGENTS.md").exists()


def _publish_session_change(reason: str, profile: str | None = None) -> None:
    try:
        from api.session_events import publish_session_list_changed

        if profile:
            try:
                publish_session_list_changed(reason, profile=profile)
            except TypeError:
                publish_session_list_changed(reason)
        else:
            publish_session_list_changed(reason)
    except Exception:
        pass


def _ui_session_response(project_id: str, session, workspace_info: dict, *, created: bool, reset: bool = False, previous_session_id: str | None = None, pruned: dict | None = None) -> dict:
    return {
        "ok": True,
        "projectId": project_id,
        "created": bool(created),
        "reset": bool(reset),
        "previousSessionId": previous_session_id or None,
        "sessionId": getattr(session, "session_id", ""),
        "session": session.compact() | {"messages": getattr(session, "messages", []) or []},
        "fastWorkspace": workspace_info.get("workspace") or "",
        "contextPath": workspace_info.get("contextPath") or "",
        "agentsPath": workspace_info.get("agentsPath") or "",
        "sourceWorkspace": workspace_info.get("sourceWorkspace") or "",
        "pruned": pruned or {},
    }


def _valid_tracked_ui_session(session, project_id: str) -> bool:
    return bool(
        session
        and getattr(session, "session_mode", None) == "ui_mode"
        and str(getattr(session, "ui_project_id", None) or getattr(session, "project_id", None) or "") == str(project_id)
        and not getattr(session, "archived", False)
    )


def _get_tracked_ui_session(project_id: str):
    state = _load_ui_mode_session_state(project_id)
    session_id = str(state.get("sessionId") or state.get("session_id") or "").strip()
    if not session_id:
        return None
    try:
        from api.models import get_session

        session = get_session(session_id)
        if _valid_tracked_ui_session(session, project_id):
            return session
    except Exception:
        return None
    return None


def _create_project_ui_session(project_id: str, project: dict, status: dict | None = None):
    from api.models import new_session

    status = status if isinstance(status, dict) else _current_ui_status_metadata(project_id)
    metadata = _ui_session_metadata(project_id, project, status)
    profile = None
    model = None
    model_provider = None
    try:
        from api import ops_sessions

        profile = ops_sessions.project_profile(project) or "default"
        model, model_provider = ops_sessions.project_session_defaults(project)
    except Exception:
        profile = str(project.get("profile") or "").strip() or "default"
    # Create once with a temporary valid workspace, then switch to the generated
    # workspace after the session id is known.
    session = new_session(
        workspace=metadata["ui_project_workspace"],
        model=model,
        model_provider=model_provider,
        profile=profile,
        project_id=project_id,
        session_mode="ui_mode",
        ui_metadata=metadata,
    )
    session.title = f"{_project_label(project)}: UI Mode"
    workspace_info = _write_ui_fast_workspace(project_id, session.session_id, project, status)
    _apply_ui_session_metadata(session, metadata, workspace=Path(workspace_info["workspace"]))
    session.save()
    _publish_session_change("ui_session_new", profile=getattr(session, "profile", None))
    return session, workspace_info


def get_project_ui_session(project_id: str, *, create: bool = True) -> dict:
    """Return or create the project-owned UI Mode chat session."""
    project = _get_project(project_id)
    status = _current_ui_status_metadata(project_id)
    with _LOCK:
        session = _get_tracked_ui_session(project_id)
        created = False
        if session is None:
            if not create:
                raise UiRuntimeError("No UI Mode chat session is tracked for this project.", status=404, code="UI_SESSION_NOT_FOUND")
            session, workspace_info = _create_project_ui_session(project_id, project, status)
            created = True
        else:
            workspace_info = _write_ui_fast_workspace(project_id, session.session_id, project, status)
            metadata = _ui_session_metadata(project_id, project, status)
            if _apply_ui_session_metadata(session, metadata, workspace=Path(workspace_info["workspace"])):
                session.save()
        _write_ui_mode_session_state(
            project_id,
            {
                "version": UI_SESSION_STATE_VERSION,
                "projectId": project_id,
                "sessionId": session.session_id,
                "fastWorkspace": workspace_info.get("workspace"),
                "sourceWorkspace": workspace_info.get("sourceWorkspace"),
                "contextPath": workspace_info.get("contextPath"),
                "updatedAt": now_iso(),
            },
        )
        return _ui_session_response(project_id, session, workspace_info, created=created)


def _retire_ui_session(session_id: str) -> bool:
    sid = str(session_id or "").strip()
    if not sid:
        return False
    try:
        from api.models import get_session
        from api.config import _evict_session_agent

        session = get_session(sid)
        if getattr(session, "active_stream_id", None):
            raise UiRuntimeError("UI Mode chat is currently running. Stop or wait for it before resetting.", status=409, code="UI_SESSION_ACTIVE")
        if not getattr(session, "archived", False):
            session.archived = True
            session.save()
        _evict_session_agent(sid)
        _publish_session_change("ui_session_reset", profile=getattr(session, "profile", None))
        return True
    except UiRuntimeError:
        raise
    except Exception:
        return False


def reset_project_ui_session(project_id: str, body: dict | None = None) -> dict:
    """Archive the tracked UI Mode chat and create a fresh fast-workspace session."""
    project = _get_project(project_id)
    status = _current_ui_status_metadata(project_id)
    with _LOCK:
        state = _load_ui_mode_session_state(project_id)
        previous_session_id = str((body or {}).get("sessionId") or state.get("sessionId") or "").strip()
        if previous_session_id:
            _retire_ui_session(previous_session_id)
        session, workspace_info = _create_project_ui_session(project_id, project, status)
        _write_ui_mode_session_state(
            project_id,
            {
                "version": UI_SESSION_STATE_VERSION,
                "projectId": project_id,
                "sessionId": session.session_id,
                "previousSessionId": previous_session_id or None,
                "fastWorkspace": workspace_info.get("workspace"),
                "sourceWorkspace": workspace_info.get("sourceWorkspace"),
                "contextPath": workspace_info.get("contextPath"),
                "updatedAt": now_iso(),
            },
        )
        return _ui_session_response(project_id, session, workspace_info, created=True, reset=True, previous_session_id=previous_session_id or None)


def prune_project_ui_sessions(project_id: str, body: dict | None = None) -> dict:
    """Remove generated UI fast workspaces that are no longer the tracked session."""
    body = body if isinstance(body, dict) else {}
    keep_current = body.get("keepCurrent") is not False
    state = _load_ui_mode_session_state(project_id)
    current_id = str(state.get("sessionId") or "").strip() if keep_current else ""
    current_dir = _safe_state_component(current_id) if current_id else ""
    root = _ui_mode_project_workspaces_dir(project_id)
    removed = 0
    kept = 0
    if root.exists():
        for child in root.iterdir():
            if not child.is_dir():
                continue
            if current_dir and child.name == current_dir:
                kept += 1
                continue
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    return {"ok": True, "projectId": project_id, "removedWorkspaces": removed, "keptWorkspaces": kept}


def _append_log(state: UiRuntimeState, *, stage: str = "system", stream: str = "system", message: str = "") -> None:
    text = _redact_text(str(message or "").replace("\r\n", "\n").replace("\r", "\n"))
    if not text:
        return
    stamp = now_iso()
    with _LOCK:
        for line in text.split("\n"):
            if not line:
                continue
            state.logs.append({"at": stamp, "stage": stage, "stream": stream, "message": line})
        if len(state.logs) > UI_LOG_LINE_LIMIT:
            del state.logs[: len(state.logs) - UI_LOG_LINE_LIMIT]
        state.updated_at = time.time()


def _format_log(entry: dict) -> str:
    return f"[{entry.get('at') or now_iso()}] [{entry.get('stage') or 'system'}:{entry.get('stream') or 'system'}] {entry.get('message') or ''}"


def _last_log_line(logs: list[dict] | None) -> str:
    for entry in reversed(logs or []):
        message = str((entry or {}).get("message") or "").strip()
        if message:
            return message[:500]
    return ""


def _mark_state(
    state: UiRuntimeState,
    status: str,
    *,
    running: bool = False,
    ready: bool = False,
    error: str | None = None,
    preview_url: str | None = None,
    inspect_url: str | None = None,
    set_started_at: bool = False,
    set_ready_at: bool = False,
    set_finished_at: bool = False,
    message: str = "",
) -> None:
    with _LOCK:
        state.status = status
        state.running = running
        state.ready = ready
        state.error = error
        if preview_url is not None:
            state.preview_url = preview_url or None
        if inspect_url is not None:
            state.inspect_url = inspect_url or None
        if set_started_at:
            state.started_at = now_iso()
        if set_ready_at:
            state.ready_at = now_iso()
        if set_finished_at:
            state.finished_at = now_iso()
        state.updated_at = time.time()
    if message:
        _append_log(state, stage="system", stream="stderr" if status == "failed" else "stdout", message=message)


def _normalize_command(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalize_relative_cwd(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    return text or "."


def _resolve_cwd(project_path: Path, raw_cwd: str) -> Path:
    resolved = (project_path / _normalize_relative_cwd(raw_cwd)).resolve()
    try:
        resolved.relative_to(project_path)
    except ValueError as exc:
        raise UiRuntimeError("UI command cwd must stay inside the project directory.", code="UI_CWD_OUTSIDE_PROJECT") from exc
    if not resolved.exists() or not resolved.is_dir():
        raise UiRuntimeError("UI command cwd is missing.", status=404, code="UI_CWD_MISSING")
    return resolved


def _normalize_env(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    env: dict[str, str] = {}
    for key, raw in value.items():
        name = str(key or "").strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            continue
        if raw is None:
            continue
        env[name] = "true" if raw is True else "false" if raw is False else str(raw)
    return env


def _normalize_port_host(value: Any) -> str:
    host = value.strip().lower() if isinstance(value, str) else ""
    return host or "127.0.0.1"


def _normalize_port_range(value: Any) -> dict[str, int]:
    source = value if isinstance(value, dict) else {}
    try:
        minimum = int(source.get("min", 30000))
    except Exception:
        minimum = 30000
    try:
        maximum = int(source.get("max", 39999))
    except Exception:
        maximum = 39999
    minimum = max(1024, minimum)
    maximum = min(65535, maximum)
    if maximum < minimum:
        return {"min": 30000, "max": 39999}
    return {"min": minimum, "max": maximum}


def _normalize_ready_timeout_ms(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = UI_READY_TIMEOUT_DEFAULT_MS
    return max(1000, min(30 * 60 * 1000, parsed))


def _normalize_build_timeout_ms(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = 30 * 60 * 1000
    return max(1000, min(6 * 60 * 60 * 1000, parsed))


def _config_candidates(project_path: Path) -> list[Path]:
    return [project_path / name for name in UI_CONFIG_FILE_NAMES]


def _play_config_candidates(project_path: Path) -> list[Path]:
    try:
        from api import play_pipeline

        names = (
            play_pipeline.HERMES_PLAY_FILE_NAME,
            play_pipeline.LEGACY_PLAY_FILE_NAME,
            play_pipeline.MODERN_PLAY_FILE_NAME,
        )
    except Exception:
        names = (".hermes/play.json", "project_play.json", ".cloud-terminal/play.json")
    return [project_path / name for name in names]


def _existing_play_config_path(project_path: Path) -> Path | None:
    return next((path for path in _play_config_candidates(project_path) if path.exists()), None)


def _relative_config_path(project_path: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_path.resolve()).as_posix()
    except Exception:
        return str(path)


def _auto_detected_source(auto_config: dict | None) -> str:
    if isinstance(auto_config, dict):
        source = str(auto_config.get(AUTO_DETECTED_SOURCE_KEY) or "").strip()
        if source:
            return source
    return "package.json"


def _normalize_workflow_source_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "ui-config"
    # Keep this as a status/contract label, not a path or command escape hatch.
    # The actual command and cwd fields are normalized independently.
    if not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,96}", text):
        return "ui-config"
    if text.lower() == "play-config":
        return "ui-config"
    return text


def _package_manager_for_project(project_path: Path) -> str:
    if (project_path / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (project_path / "yarn.lock").exists():
        return "yarn"
    if (project_path / "bun.lockb").exists() or (project_path / "bun.lock").exists():
        return "bun"
    payload = _read_json_object(project_path / "package.json")
    package_manager = str((payload or {}).get("packageManager") or "").strip().lower()
    if package_manager.startswith("pnpm"):
        return "pnpm"
    if package_manager.startswith("yarn"):
        return "yarn"
    if package_manager.startswith("bun"):
        return "bun"
    return "npm"


def _package_script_command(package_manager: str, script: str) -> str:
    if package_manager == "yarn":
        return f"yarn {script}"
    return f"{package_manager} run {script}"


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _play_config_runtime_env(project_path: Path) -> dict[str, str]:
    play_path = _existing_play_config_path(project_path)
    if play_path is None:
        return {}
    payload = _read_json_object(play_path)
    if not payload:
        return {}
    start_raw = payload.get("start")
    start_section = start_raw if isinstance(start_raw, dict) else {}
    env = _normalize_env(start_section.get("env"))
    selected: dict[str, str] = {}
    for key in ("MONOREPO_ACTIVE_APP", "MONOREPO_DEFAULT_APP", "ACTIVE_APPS"):
        value = str(env.get(key) or "").strip()
        if value:
            selected[key] = value
    return selected


def _auto_detect_monorepo_template_ui_config(project_path: Path) -> dict | None:
    """Detect the standardized generated-app monorepo template fast UI lane.

    Older Cloud Terminal/Hermes projects use a root deployment Play config for
    production parity, while the fast browser UI is served by the Vite client in
    ``packages/client``. The root package often has no ``dev`` script, so a
    generic root-package heuristic would either miss the project entirely or fall
    back to the slow Play/static build lane.
    """

    root_package_json = project_path / "package.json"
    client_package_json = project_path / "packages" / "client" / "package.json"
    if not root_package_json.exists() or not client_package_json.exists():
        return None
    root_payload = _read_json_object(root_package_json)
    client_payload = _read_json_object(client_package_json)
    if not root_payload or not client_payload:
        return None
    scripts_raw = client_payload.get("scripts")
    scripts: dict[str, Any] = scripts_raw if isinstance(scripts_raw, dict) else {}
    if not scripts.get("dev"):
        return None

    template_markers = [
        project_path / "packages" / "apps" / "package.json",
        project_path / "packages" / "server" / "package.json",
        project_path / "packages" / "schemas" / "package.json",
        project_path / "scripts" / "active-app.sh",
    ]
    if not any(path.exists() for path in template_markers):
        return None

    package_manager = _package_manager_for_project(project_path)
    root_scripts_raw = root_payload.get("scripts")
    root_scripts: dict[str, Any] = root_scripts_raw if isinstance(root_scripts_raw, dict) else {}
    ui_dev_script = project_path / "scripts" / "ui-dev.sh"
    if root_scripts.get("ui:dev"):
        command = _package_script_command(package_manager, "ui:dev")
        auto_source = "monorepo-template:ui-dev"
    elif ui_dev_script.exists():
        command = "bash ./scripts/ui-dev.sh"
        auto_source = "monorepo-template:ui-dev"
    else:
        command = f"{package_manager} --filter ./packages/client run dev -- --host 127.0.0.1 --port ${{PORT}} --strictPort"
        auto_source = "monorepo-template:packages/client"
    env = {
        "HOST": "127.0.0.1",
        "VITE_HOST": "127.0.0.1",
        "NO_PROXY": os.environ.get("NO_PROXY", "localhost,127.0.0.1"),
        "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
        "NPM_CONFIG_STORE_DIR": ".cache/pnpm-store",
        "npm_config_store_dir": ".cache/pnpm-store",
        **_play_config_runtime_env(project_path),
    }
    config: dict[str, Any] = {
        "version": 1,
        AUTO_DETECTED_SOURCE_KEY: auto_source,
        "dev": {
            "command": command,
            "cwd": ".",
            "env": env,
            "port": {
                "mode": "auto",
                "host": "127.0.0.1",
                "envVar": "PORT",
                "range": {"min": 30000, "max": 39999},
            },
        },
        "inspect": {"mode": "proxy", "url": "/", "readyTimeoutMs": UI_READY_TIMEOUT_DEFAULT_MS},
    }
    play_path = _existing_play_config_path(project_path)
    if play_path is not None:
        config[AUTO_DETECTED_PARITY_SOURCE_KEY] = _relative_config_path(project_path, play_path)
    return config


def _auto_detect_package_ui_config(project_path: Path) -> dict | None:
    package_json = project_path / "package.json"
    if not package_json.exists():
        return None
    payload = _read_json_object(package_json)
    if not payload:
        return None
    scripts_raw = payload.get("scripts") if isinstance(payload, dict) else {}
    scripts: dict[str, Any] = scripts_raw if isinstance(scripts_raw, dict) else {}
    script = "dev" if scripts.get("dev") else ("start" if scripts.get("start") else "")
    if not script:
        return None
    package_manager = _package_manager_for_project(project_path)
    return {
        "version": 1,
        AUTO_DETECTED_SOURCE_KEY: "package.json",
        "dev": {
            "command": _package_script_command(package_manager, script),
            "cwd": ".",
            "env": {"HOST": "127.0.0.1"},
            "port": {
                "mode": "auto",
                "host": "127.0.0.1",
                "envVar": "PORT",
                "range": {"min": 30000, "max": 39999},
            },
        },
        "inspect": {"mode": "proxy", "url": "/", "readyTimeoutMs": UI_READY_TIMEOUT_DEFAULT_MS},
    }


def _auto_detect_play_ui_config(project_path: Path) -> dict | None:
    play_path = _existing_play_config_path(project_path)
    if play_path is None:
        return None
    source = _relative_config_path(project_path, play_path)
    return {"version": 1, "source": source, AUTO_DETECTED_SOURCE_KEY: source}


def _auto_detect_ui_config(project_path: Path) -> dict | None:
    monorepo_template_config = _auto_detect_monorepo_template_ui_config(project_path)
    if monorepo_template_config is not None:
        return monorepo_template_config
    package_config = _auto_detect_package_ui_config(project_path)
    if package_config is not None:
        play_path = _existing_play_config_path(project_path)
        if play_path is not None:
            package_config[AUTO_DETECTED_PARITY_SOURCE_KEY] = _relative_config_path(project_path, play_path)
        return package_config
    return _auto_detect_play_ui_config(project_path)


def _is_play_parity_request(value: Any) -> bool:
    text = str(value or "").strip().lower().replace("_", "-")
    return text in {"play", "play-config", "play-parity", "parity", "production", "prod", "build"}


def _play_source_request(source: dict[str, Any]) -> str:
    raw = source.get("usePlayConfig")
    if raw is True:
        return "project_play.json"
    if raw is False:
        return ""
    for key in ("playConfig", "playConfigPath", "source", "extends", "workflow"):
        value = source.get(key)
        if not isinstance(value, str):
            continue
        text = value.strip()
        lowered = text.lower()
        if lowered in {"play", "play-config", "play_config", "project_play", "project-play"}:
            return "project_play.json"
        if lowered.endswith(".json") and ("play" in lowered or lowered.startswith(".hermes/") or lowered.startswith(".cloud-terminal/")):
            return text
    return ""


def _resolve_play_config_path(project_path: Path, requested: str) -> Path:
    try:
        from api import play_pipeline

        candidates = [
            project_path / play_pipeline.HERMES_PLAY_FILE_NAME,
            project_path / play_pipeline.LEGACY_PLAY_FILE_NAME,
            project_path / play_pipeline.MODERN_PLAY_FILE_NAME,
        ]
    except Exception:
        candidates = [project_path / ".hermes/play.json", project_path / "project_play.json", project_path / ".cloud-terminal/play.json"]
    request = str(requested or "").strip()
    if request and request not in {"play", "play-config", "project_play.json"}:
        resolved = (project_path / request).resolve()
        try:
            resolved.relative_to(project_path)
        except ValueError as exc:
            raise UiRuntimeError("UI Play config source must stay inside the project directory.", code="UI_PLAY_CONFIG_OUTSIDE_PROJECT") from exc
        return resolved
    return next((path for path in candidates if path.exists()), candidates[1])


def _normalize_play_sourced_ui_config(source: dict[str, Any], project_path: Path, requested: str) -> dict:
    play_path = _resolve_play_config_path(project_path, requested)
    if not play_path.exists():
        return {
            "valid": False,
            "missing": ["play-config"],
            "errors": [f"Play config source not found: {play_path}"],
            "config": {},
            "source": "play-config",
            "playConfigPath": str(play_path),
        }
    try:
        raw = json.loads(play_path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {
            "valid": False,
            "missing": [],
            "errors": ["Play config source is invalid JSON."],
            "config": {},
            "source": "play-config",
            "playConfigPath": str(play_path),
        }
    from api import play_pipeline

    normalized = play_pipeline.normalize_play_config(raw, project_path)
    play_config = normalized.get("config") or {}
    config = {
        "version": int(source.get("version") or 1),
        "source": "play-config",
        "playConfigPath": str(play_path),
        "build": dict(play_config.get("build") or {}),
        "dev": dict(play_config.get("start") or {}),
        "inspect": dict(play_config.get("inspect") or {}),
    }
    missing = list(normalized.get("missing") or [])
    errors = list(normalized.get("errors") or [])
    if play_config.get("buildOnly") is True:
        missing.extend(["start.command", "inspect.url"])
    try:
        if config.get("build", {}).get("command"):
            _resolve_cwd(project_path, config["build"].get("cwd") or ".")
        _resolve_cwd(project_path, config["dev"].get("cwd") or ".")
    except CoreApiError as exc:
        errors.append(str(exc))
    return {
        "valid": not missing and not errors,
        "missing": missing,
        "errors": errors,
        "config": config,
        "source": "play-config",
        "playConfigPath": str(play_path),
    }


def normalize_ui_config(payload: dict, project_path: Path) -> dict:
    source: dict[str, Any] = payload if isinstance(payload, dict) else {}
    play_source = _play_source_request(source)
    if play_source:
        return _normalize_play_sourced_ui_config(source, project_path, play_source)
    build_raw = source.get("build")
    build_section: dict[str, Any] = build_raw if isinstance(build_raw, dict) else {}
    dev_raw = source.get("dev")
    dev_section: dict[str, Any] = dev_raw if isinstance(dev_raw, dict) else {}
    if not dev_section:
        start_raw = source.get("start")
        if isinstance(start_raw, dict):
            dev_section = start_raw
    if not dev_section:
        ui_raw = source.get("ui")
        if isinstance(ui_raw, dict):
            dev_section = ui_raw
    inspect_raw = source.get("inspect")
    inspect_section: dict[str, Any] = inspect_raw if isinstance(inspect_raw, dict) else {}
    port_raw = dev_section.get("port")
    port_section: dict[str, Any] = port_raw if isinstance(port_raw, dict) else {}
    port_mode = str(port_section.get("mode") or "auto").strip().lower()
    if port_mode != "auto":
        port_mode = "auto"

    command = _normalize_command(dev_section.get("command") or source.get("devCommand") or source.get("command"))
    build_command = _normalize_command(build_section.get("command") or source.get("buildCommand"))
    inspect_url = _normalize_command(inspect_section.get("url") or source.get("inspectUrl") or source.get("previewUrl")) or "/"
    inspect_mode = str(inspect_section.get("mode") or source.get("inspectMode") or "proxy").strip().lower()
    if inspect_mode != "proxy":
        inspect_mode = "proxy"

    workflow_source = _normalize_workflow_source_label(source.get("workflowSource") or source.get("uiWorkflowSource"))
    config = {
        "version": int(source.get("version") or 1),
        "source": workflow_source,
        "build": {
            "command": build_command,
            "cwd": _normalize_relative_cwd(build_section.get("cwd") or source.get("buildCwd")),
            "env": _normalize_env(build_section.get("env") or source.get("buildEnv")),
            "timeoutMs": _normalize_build_timeout_ms(build_section.get("timeoutMs") or source.get("buildTimeoutMs")),
        },
        "dev": {
            "command": command,
            "cwd": _normalize_relative_cwd(dev_section.get("cwd") or source.get("cwd")),
            "env": _normalize_env(dev_section.get("env") or source.get("env")),
            "port": {
                "mode": port_mode,
                "host": _normalize_port_host(port_section.get("host") or dev_section.get("host") or source.get("host")),
                "envVar": _normalize_command(port_section.get("envVar") or dev_section.get("portEnvVar") or source.get("portEnvVar")) or "PORT",
                "range": _normalize_port_range(port_section.get("range") or source.get("portRange")),
            },
        },
        "inspect": {
            "mode": inspect_mode,
            "url": inspect_url,
            "readyPattern": _normalize_command(inspect_section.get("readyPattern") or source.get("readyPattern")),
            "readyTimeoutMs": _normalize_ready_timeout_ms(inspect_section.get("readyTimeoutMs") or source.get("readyTimeoutMs")),
        },
    }
    missing: list[str] = []
    errors: list[str] = []
    if not command:
        missing.append("dev.command")
    try:
        if build_command:
            _resolve_cwd(project_path, config["build"]["cwd"])
        _resolve_cwd(project_path, config["dev"]["cwd"])
    except CoreApiError as exc:
        errors.append(str(exc))
    return {"valid": not missing and not errors, "missing": missing, "errors": errors, "config": config, "source": workflow_source}


def get_project_ui_config_file_info(project_id: str) -> dict:
    project = _get_project(project_id)
    project_path = _project_path(project)
    candidates = _config_candidates(project_path)
    selected = next((path for path in candidates if path.exists()), candidates[0])
    payload = {
        "projectId": project_id,
        "path": str(selected),
        "branch": _project_branch(project),
        "scope": "shared",
        "exists": selected.exists(),
        "configured": False,
        "valid": False,
        "missing": [],
        "errors": [],
        "parseError": None,
        "autoDetected": False,
        "autoSource": "",
        "source": "",
        "playConfigPath": "",
        "parityAvailable": False,
        "parityWorkflowSource": "",
        "parityConfigPath": "",
    }
    if not selected.exists():
        auto_config = _auto_detect_ui_config(project_path)
        if not auto_config:
            return payload
        normalized = normalize_ui_config(auto_config, project_path)
        payload["configured"] = normalized["valid"]
        payload["valid"] = normalized["valid"]
        payload["missing"] = normalized["missing"]
        payload["errors"] = normalized["errors"]
        payload["autoDetected"] = True
        payload["autoSource"] = _auto_detected_source(auto_config)
        payload["source"] = normalized.get("source") or "auto"
        payload["playConfigPath"] = normalized.get("playConfigPath") or ""
        parity_source = str(auto_config.get(AUTO_DETECTED_PARITY_SOURCE_KEY) or "").strip() if isinstance(auto_config, dict) else ""
        if parity_source and payload["source"] != "play-config":
            payload["parityAvailable"] = True
            payload["parityWorkflowSource"] = "play-config"
            payload["parityConfigPath"] = str((project_path / parity_source).resolve())
        return payload
    try:
        raw = json.loads(selected.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        payload["parseError"] = "UI config file is invalid JSON."
        return payload
    normalized = normalize_ui_config(raw, project_path)
    payload["configured"] = normalized["valid"]
    payload["valid"] = normalized["valid"]
    payload["missing"] = normalized["missing"]
    payload["errors"] = normalized["errors"]
    payload["source"] = normalized.get("source") or "ui-config"
    payload["playConfigPath"] = normalized.get("playConfigPath") or ""
    play_path = _existing_play_config_path(project_path)
    if play_path is not None and payload["source"] != "play-config":
        payload["parityAvailable"] = True
        payload["parityWorkflowSource"] = "play-config"
        payload["parityConfigPath"] = str(play_path.resolve())
    return payload


def get_project_ui_config(project_id: str, *, workflow: Any = "") -> dict:
    project = _get_project(project_id)
    project_path = _project_path(project)
    if _is_play_parity_request(workflow):
        auto_config = _auto_detect_play_ui_config(project_path)
        if not auto_config:
            raise UiRuntimeError("Play parity config not found for this project.", status=404, code="UI_PLAY_CONFIG_NOT_FOUND")
        normalized = normalize_ui_config(auto_config, project_path)
        if not normalized["valid"]:
            missing = ", ".join(normalized["missing"])
            errors = ", ".join(normalized["errors"])
            details = "; ".join(part for part in (f"Missing: {missing}" if missing else "", errors) if part)
            raise UiRuntimeError(f"Play parity UI config is invalid. {details}".strip(), code="UI_CONFIG_INVALID")
        info = get_project_ui_config_file_info(project_id)
        return {
            "project": project,
            "projectPath": project_path,
            "path": info["path"],
            "branch": info["branch"],
            "config": normalized["config"],
            "autoDetected": True,
            "autoSource": _auto_detected_source(auto_config),
            "source": normalized.get("source") or "play-config",
            "playConfigPath": normalized.get("playConfigPath") or "",
        }
    info = get_project_ui_config_file_info(project_id)
    if not info["exists"]:
        auto_config = _auto_detect_ui_config(project_path)
        if auto_config:
            normalized = normalize_ui_config(auto_config, project_path)
            if normalized["valid"]:
                return {
                    "project": project,
                    "projectPath": project_path,
                    "path": info["path"],
                    "branch": info["branch"],
                    "config": normalized["config"],
                    "autoDetected": True,
                    "autoSource": _auto_detected_source(auto_config),
                    "source": _auto_detected_source(auto_config) if (normalized.get("source") or "") == "ui-config" else (normalized.get("source") or "auto"),
                    "playConfigPath": normalized.get("playConfigPath") or "",
                }
            missing = ", ".join(normalized["missing"])
            errors = ", ".join(normalized["errors"])
            details = "; ".join(part for part in (f"Missing: {missing}" if missing else "", errors) if part)
            raise UiRuntimeError(f"Auto-detected UI config is incomplete. {details}".strip(), code="UI_CONFIG_INVALID")
        raise UiRuntimeError("UI config file not found for this project.", status=404, code="UI_CONFIG_NOT_FOUND")
    if info.get("parseError"):
        raise UiRuntimeError(str(info["parseError"]), code="UI_CONFIG_PARSE_ERROR")
    try:
        raw = json.loads(Path(info["path"]).read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise UiRuntimeError("UI config file is invalid JSON.", code="UI_CONFIG_PARSE_ERROR") from exc
    normalized = normalize_ui_config(raw, project_path)
    if not normalized["valid"]:
        missing = ", ".join(normalized["missing"])
        errors = ", ".join(normalized["errors"])
        details = "; ".join(part for part in (f"Missing: {missing}" if missing else "", errors) if part)
        raise UiRuntimeError(f"UI config is invalid. {details}".strip(), code="UI_CONFIG_INVALID")
    return {
        "project": project,
        "projectPath": project_path,
        "path": info["path"],
        "branch": info["branch"],
        "config": normalized["config"],
        "source": normalized.get("source") or "ui-config",
        "playConfigPath": normalized.get("playConfigPath") or "",
    }


def _try_reserve_port(host: str, port: int) -> bool:
    key = (host, port)
    with _LOCK:
        if key in _RESERVED_PORTS:
            return False
        _RESERVED_PORTS.add(key)
    return True


def _release_port(host: str | None, port: int | None) -> None:
    if not host or not port:
        return
    with _LOCK:
        _RESERVED_PORTS.discard((host, int(port)))


def _probe_port_available(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
        return True
    except OSError:
        return False


def _allocate_port(host: str, port_range: dict[str, int]) -> int:
    minimum = int(port_range.get("min") or 30000)
    maximum = int(port_range.get("max") or 39999)
    span = max(1, maximum - minimum + 1)
    start = int(time.time() * 1000) % span
    for offset in range(span):
        port = minimum + ((start + offset) % span)
        if not _try_reserve_port(host, port):
            continue
        if _probe_port_available(host, port):
            return port
        _release_port(host, port)
    raise UiRuntimeError(f"Port allocation failure: no free port in range {minimum}-{maximum}.", status=500, code="UI_PORT_ALLOCATION_FAILED")


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def _normalize_proxy_path(raw_url: str) -> tuple[str, str]:
    value = str(raw_url or "").strip() or "/"
    if value.startswith("/"):
        parsed = urlparse.urlsplit(value)
    else:
        try:
            parsed = urlparse.urlsplit(value if "://" in value else f"http://placeholder.local/{value}")
        except Exception:
            parsed = urlparse.urlsplit(f"/{value}")
    request_path = parsed.path or "/"
    if parsed.query:
        request_path = f"{request_path}?{parsed.query}"
    inspect_path = request_path
    if parsed.fragment:
        inspect_path = f"{inspect_path}#{parsed.fragment}"
    return request_path, inspect_path


def _ui_proxy_prefix(project_id: str) -> str:
    return f"{UI_PROJECT_PROXY_BASE_PATH}/{urlparse.quote(project_id, safe='')}"


def _build_proxy_preview_url(project_id: str, inspect_path: str) -> str:
    path = inspect_path if inspect_path.startswith("/") else f"/{inspect_path}"
    return f"{_ui_proxy_prefix(project_id)}{path}"


def _is_ui_referer_navigation_path(path: str) -> bool:
    clean = str(path or "") or "/"
    return any(clean == prefix or clean.startswith(f"{prefix}/") for prefix in UI_REFERER_NAVIGATION_PREFIXES)


def _project_id_from_ui_referer(handler) -> str:
    referer = str(handler.headers.get("Referer") or handler.headers.get("Referrer") or "").strip()
    if not referer:
        return ""
    try:
        ref_path = urlparse.urlsplit(referer).path or ""
    except Exception:
        return ""
    if not ref_path.startswith(f"{UI_PROJECT_PROXY_BASE_PATH}/"):
        return ""
    tail = ref_path[len(f"{UI_PROJECT_PROXY_BASE_PATH}/"):]
    project_id, _, _ = tail.partition("/")
    return urlparse.unquote(project_id) if project_id else ""


def redirect_ui_project_referer_navigation(handler, parsed, *, method: str = "GET") -> bool:
    """Keep root-relative app navigations inside an active UI Mode iframe proxy.

    Some Play-sourced apps navigate with absolute app paths such as `/app` after
    login. Inside UI Mode those paths must remain under `/ui-project/{id}/...`;
    otherwise WebUI handles `/app` itself and returns its own `not found` page.
    Only redirect app/public path prefixes and only when the request carries a
    UI-project referrer, so normal WebUI routes keep their original behavior.
    """
    if str(method or "GET").upper() not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}:
        return False
    if not _is_ui_referer_navigation_path(getattr(parsed, "path", "")):
        return False
    project_id = _project_id_from_ui_referer(handler)
    if not project_id:
        return False
    target = _build_proxy_preview_url(project_id, getattr(parsed, "path", "") or "/")
    query = getattr(parsed, "query", "") or ""
    if query:
        target = f"{target}?{query}"
    body = b""
    handler.send_response(307)
    handler.send_header("Location", target)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    if str(method or "GET").upper() != "HEAD":
        handler.wfile.write(body)
    return True


def _build_command_env(overrides: dict[str, str]) -> dict[str, str]:
    env = dict(os.environ)
    env.update({str(key): str(value) for key, value in (overrides or {}).items() if value is not None})
    for key in ("TERMINAL_SU_PASSWORD", "SU_PASSWORD", "TERMINAL_SU_USER", "SU_USER"):
        env.pop(key, None)
    return env


def _spawn_dev_stage(project_path: Path, command: str, cwd: str, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        ["bash", "-lc", command],
        cwd=str(_resolve_cwd(project_path, cwd)),
        env=_build_command_env(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True,
    )


def _reader_thread(
    state: UiRuntimeState,
    proc: subprocess.Popen,
    stream_name: str,
    ready_regex: re.Pattern | None,
    ready_event: threading.Event | None,
    stage: str = "dev",
) -> None:
    stream = proc.stdout if stream_name == "stdout" else proc.stderr
    if not stream:
        return
    try:
        for line in stream:
            _append_log(state, stage=stage, stream=stream_name, message=line.rstrip("\n"))
            if ready_regex and ready_event and ready_regex.search(line):
                ready_event.set()
    except Exception as exc:
        _append_log(state, stage=stage, stream="stderr", message=f"Log reader failed: {exc}")


def _join_reader_threads(threads: list[threading.Thread]) -> None:
    for thread in threads:
        thread.join(timeout=1)


def _terminate_process(proc: subprocess.Popen | None, timeout: float = 4.0) -> None:
    if not proc or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            return
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.05)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _run_build_stage(project_path: Path, config: dict, state: UiRuntimeState) -> None:
    build_config = dict(config.get("build") or {})
    command = _normalize_command(build_config.get("command"))
    if not command:
        return
    timeout_ms = _normalize_build_timeout_ms(build_config.get("timeoutMs"))
    proc = _spawn_dev_stage(project_path, command, build_config.get("cwd") or ".", dict(build_config.get("env") or {}))
    with _LOCK:
        state.process = proc
        state.pid = int(proc.pid)
        state.pgid = int(proc.pid)
        state.build_command = command
    _append_log(state, stage="build", stream="system", message=f"Running: {command}")
    _append_log(state, stage="build", stream="system", message=f"Build timeout: {round(timeout_ms / 1000)}s")
    threads = [
        threading.Thread(target=_reader_thread, args=(state, proc, "stdout", None, None, "build"), daemon=True),
        threading.Thread(target=_reader_thread, args=(state, proc, "stderr", None, None, "build"), daemon=True),
    ]
    for thread in threads:
        thread.start()
    deadline = time.time() + (timeout_ms / 1000)
    timed_out = False
    while True:
        code = proc.poll()
        if code is not None:
            break
        if state.stop_requested:
            _terminate_process(proc)
            code = proc.poll()
            break
        if time.time() >= deadline:
            timed_out = True
            _terminate_process(proc)
            code = proc.poll()
            break
        time.sleep(0.2)
    _join_reader_threads(threads)
    with _LOCK:
        state.process = None
        state.pid = None
        state.pgid = None
    if state.stop_requested:
        return
    if timed_out:
        raise UiRuntimeError(f"UI build timeout after {round(timeout_ms / 1000)}s.", status=500, code="UI_BUILD_TIMEOUT")
    if code != 0:
        raise UiRuntimeError(f"UI build failed: process exited with code {code}.", status=500, code="UI_BUILD_FAILED")
    _append_log(state, stage="build", stream="system", message="Build stage completed successfully.")


def _prepare_dev_runtime(project_id: str, config: dict, state: UiRuntimeState) -> dict:
    dev_config = dict(config["dev"])
    dev_env = dict(dev_config.get("env") or {})
    port_cfg = dev_config.get("port") or {}
    host = _normalize_port_host(port_cfg.get("host"))
    env_var = _normalize_command(port_cfg.get("envVar")) or "PORT"
    port = _allocate_port(host, port_cfg.get("range") or {})
    dev_env[env_var] = str(port)
    dev_env.setdefault("HOST", host)
    dev_env.setdefault("HOSTNAME", host)
    inspect = config["inspect"]
    inspect_url = str(inspect.get("url") or "/")
    inspect_url = inspect_url.replace(f"${{{env_var}}}", str(port)).replace(f"${env_var}", str(port))
    _, inspect_path = _normalize_proxy_path(inspect_url)
    preview_url = _build_proxy_preview_url(project_id, inspect_path)
    with _LOCK:
        state.allocated_port = port
        state.allocated_port_host = host
        state.allocated_port_env_var = env_var
        state.command = dev_config.get("command")
        state.cwd = dev_config.get("cwd") or "."
    dev_config["env"] = dev_env
    return {"config": {**config, "dev": dev_config}, "previewUrl": preview_url}


def _runtime_worker(ui_config: dict, state: UiRuntimeState) -> None:
    project = ui_config["project"]
    project_path = ui_config["projectPath"]
    config = ui_config["config"]
    proc: subprocess.Popen | None = None
    threads: list[threading.Thread] = []
    try:
        build_ran = False
        if _normalize_command((config.get("build") or {}).get("command")):
            with _BUILD_LOCK:
                if state.stop_requested:
                    return
                _mark_state(state, "building", running=True, ready=False, message="Starting UI build stage...")
                _run_build_stage(project_path, config, state)
                build_ran = True
        if state.stop_requested:
            return
        start_message = "Build complete. Starting UI runtime..." if build_ran else "Starting UI runtime..."
        _mark_state(state, "starting", running=True, ready=False, message=start_message)
        runtime = _prepare_dev_runtime(state.project_id, config, state)
        dev_config = runtime["config"]["dev"]
        command = dev_config["command"]
        ready_pattern = runtime["config"]["inspect"].get("readyPattern") or ""
        ready_regex = re.compile(ready_pattern, re.I) if ready_pattern else UI_READY_PATTERN
        ready_timeout = _normalize_ready_timeout_ms(runtime["config"]["inspect"].get("readyTimeoutMs"))
        ready_event = threading.Event()
        proc = _spawn_dev_stage(project_path, command, dev_config.get("cwd") or ".", dict(dev_config.get("env") or {}))
        with _LOCK:
            state.process = proc
            state.pid = int(proc.pid)
            state.pgid = int(proc.pid)
        _append_log(state, stage="dev", stream="system", message=f"Running: {command}")
        _append_log(state, stage="dev", stream="system", message=f"Allocated port: {state.allocated_port} (host {state.allocated_port_host or '127.0.0.1'}).")
        _append_log(state, stage="dev", stream="system", message=f"Preview URL: {runtime['previewUrl']}")
        for stream_name in ("stdout", "stderr"):
            thread = threading.Thread(target=_reader_thread, args=(state, proc, stream_name, ready_regex, ready_event), daemon=True)
            thread.start()
            threads.append(thread)
        deadline = time.time() + (ready_timeout / 1000)
        while time.time() <= deadline:
            if state.stop_requested:
                return
            code = proc.poll()
            if code is not None:
                _join_reader_threads(threads)
                raise UiRuntimeError(f"UI runtime exited before ready (exit code {code}).", status=500, code="UI_DEV_EXITED")
            port_ready = bool(state.allocated_port and _is_port_open(state.allocated_port_host or "127.0.0.1", state.allocated_port))
            if port_ready or (ready_event.is_set() and not state.allocated_port):
                break
            time.sleep(0.2)
        else:
            _terminate_process(proc)
            raise UiRuntimeError(f"UI runtime ready timeout after {round(ready_timeout / 1000)}s.", status=500, code="UI_READY_TIMEOUT")
        _mark_state(
            state,
            "ready",
            running=True,
            ready=True,
            preview_url=runtime["previewUrl"],
            inspect_url=runtime["previewUrl"],
            set_ready_at=True,
            message=f"{_project_label(project)} UI runtime is ready.",
        )
        code = proc.wait()
        _join_reader_threads(threads)
        with _LOCK:
            state.process = None
            state.pid = None
            state.pgid = None
        _release_port(state.allocated_port_host, state.allocated_port)
        if state.stop_requested:
            _mark_state(state, "stopped", running=False, ready=False, set_finished_at=True, message="UI runtime stopped.")
        elif code == 0:
            _mark_state(state, "stopped", running=False, ready=False, set_finished_at=True, message="UI runtime exited.")
        else:
            _mark_state(state, "failed", running=False, ready=False, error=f"UI runtime exited with code {code}.", set_finished_at=True)
    except Exception as exc:
        if state.stop_requested:
            return
        _terminate_process(proc or state.process)
        _release_port(state.allocated_port_host, state.allocated_port)
        message = str(exc) or "UI runtime failed."
        _append_log(state, stage="system", stream="stderr", message=f"Failure reason: {message}")
        _mark_state(state, "failed", running=False, ready=False, error=message, set_finished_at=True, message=message)


def start_project_ui_runtime(project_id: str, body: dict | None = None) -> dict:
    payload = body if isinstance(body, dict) else {}
    workflow = payload.get("workflow") or payload.get("uiWorkflow") or payload.get("workflowSource") or payload.get("uiWorkflowSource")
    ui_config = get_project_ui_config(project_id, workflow=workflow)
    stop_project_ui_runtime(project_id, purge=True)
    state = UiRuntimeState(
        project_id=project_id,
        config_path=ui_config["path"],
        config_branch=ui_config["branch"],
        config_auto_detected=ui_config.get("autoDetected") is True,
        config_auto_source=str(ui_config.get("autoSource") or "") or None,
        workflow_source=str(ui_config.get("source") or "").strip() or None,
        play_config_path=str(ui_config.get("playConfigPath") or "").strip() or None,
        session_id=str(payload.get("sessionId") or payload.get("session_id") or "").strip() or None,
    )
    _mark_state(state, "starting", running=True, ready=False, set_started_at=True, message="Starting UI runtime...")
    with _LOCK:
        _RUNTIMES[project_id] = state
    threading.Thread(target=_runtime_worker, args=(ui_config, state), daemon=True).start()
    return build_project_ui_status(project_id)


def restart_project_ui_runtime(project_id: str, body: dict | None = None) -> dict:
    stop_project_ui_runtime(project_id, purge=True)
    return start_project_ui_runtime(project_id, body)


def stop_project_ui_runtime(project_id: str, *, purge: bool = False) -> dict | None:
    with _LOCK:
        state = _RUNTIMES.get(project_id)
    if not state:
        return None
    state.stop_requested = True
    _terminate_process(state.process)
    with _LOCK:
        state.process = None
        state.pid = None
        state.pgid = None
    _release_port(state.allocated_port_host, state.allocated_port)
    if purge:
        with _LOCK:
            _RUNTIMES.pop(project_id, None)
        return None
    _mark_state(state, "stopped", running=False, ready=False, set_finished_at=True, message="UI runtime stopped.")
    return build_project_ui_status(project_id)


def _ui_status_summary(config_info: dict, snapshot: dict) -> str:
    if config_info.get("parseError"):
        return str(config_info["parseError"])
    state_name = str(snapshot.get("status") or "idle").strip().lower()
    if state_name == "building":
        return "UI build stage is running."
    if state_name == "starting":
        return "UI runtime is starting."
    if state_name == "ready":
        preview_url = str(snapshot.get("preview_url") or "").strip()
        return f"UI runtime is ready at {preview_url}." if preview_url else "UI runtime is ready."
    if state_name == "failed":
        return str(snapshot.get("error") or "UI runtime failed.")
    if state_name == "stopped":
        return "UI runtime is stopped."
    if config_info.get("source") == "play-config":
        if config_info.get("valid") is True:
            return "UI Mode will use the project's Play build/start config. Start UI Mode to inspect the same app runtime as Play."
        missing = config_info.get("missing") or []
        errors = config_info.get("errors") or []
        parts = []
        if missing:
            parts.append("Missing: " + ", ".join(str(part) for part in missing))
        if errors:
            parts.extend(str(part) for part in errors)
        detail = "; ".join(parts)
        return f"Play-sourced UI config is incomplete. {detail}".strip()
    if config_info.get("exists") is not True and config_info.get("autoDetected") is True:
        if config_info.get("valid") is True:
            auto_source = str(config_info.get("autoSource") or "").strip()
            if auto_source == "monorepo-template:ui-dev":
                source_label = "the monorepo template ui:dev contract"
            elif auto_source == "monorepo-template:packages/client":
                source_label = "the monorepo template packages/client dev lane"
            else:
                source_label = auto_source or "package.json"
            if config_info.get("parityAvailable") is True:
                return f"Auto-detected fast UI workflow from {source_label}. Play parity is available explicitly."
            return f"Auto-detected UI workflow from {source_label}. Start UI Mode to inspect the live app."
        missing = config_info.get("missing") or []
        return f"Auto-detected UI workflow is incomplete. Missing: {', '.join(str(part) for part in missing)}"
    if config_info.get("exists") is not True:
        return "No UI config found for this project."
    if config_info.get("valid") is not True:
        missing = config_info.get("missing") or []
        errors = config_info.get("errors") or []
        parts = []
        if missing:
            parts.append("Missing: " + ", ".join(str(part) for part in missing))
        if errors:
            parts.extend(str(part) for part in errors)
        return "UI config is incomplete. " + "; ".join(parts)
    return "UI workflow is ready. Start UI Mode to inspect the live app."


def _ui_runtime_available(config_info: dict) -> bool:
    return config_info.get("valid") is True


def _ui_workflow_source(config_info: dict) -> str:
    source = str(config_info.get("source") or "").strip()
    if config_info.get("autoDetected") is True and source in {"", "ui-config"}:
        return str(config_info.get("autoSource") or "auto").strip() or "auto"
    if source:
        return source
    if config_info.get("autoDetected") is True:
        return str(config_info.get("autoSource") or "auto").strip() or "auto"
    if config_info.get("exists") is True:
        return "ui-config"
    return ""


def build_project_ui_status(project_id: str) -> dict:
    config_info = get_project_ui_config_file_info(project_id)
    with _LOCK:
        state = _RUNTIMES.get(project_id)
        snapshot = dict(state.__dict__) if state else {}
    state_name = str(snapshot.get("status") or "idle").lower()
    summary = _ui_status_summary(config_info, snapshot)
    runtime_available = _ui_runtime_available(config_info)
    workflow_source = str(snapshot.get("workflow_source") or "").strip() or _ui_workflow_source(config_info)
    play_config_path = str(snapshot.get("play_config_path") or config_info.get("playConfigPath") or "").strip()
    iteration_mode = "play-parity" if workflow_source == "play-config" else ("fast-dev" if runtime_available else "")
    label_by_state = {
        "idle": "UI ready" if runtime_available else "UI unavailable",
        "building": "UI building",
        "starting": "UI starting",
        "ready": "UI live",
        "failed": "UI failed",
        "stopped": "Stopped",
    }
    kind_by_state = {"building": "warning", "starting": "warning", "ready": "ready", "failed": "error", "stopped": "idle"}
    logs = list(snapshot.get("logs") or []) if isinstance(snapshot.get("logs"), list) else []
    return redact_payload({
        "projectId": project_id,
        "runtimeId": snapshot.get("runtime_id"),
        "sessionId": snapshot.get("session_id"),
        "terminalTarget": {"projectId": project_id, "sessionId": snapshot.get("session_id") or ""},
        "configured": config_info.get("configured") is True,
        "valid": config_info.get("valid") is True,
        "uiAvailable": runtime_available,
        "canStart": runtime_available,
        "unavailableReason": "" if runtime_available else summary,
        "workflowSource": workflow_source,
        "iterationMode": iteration_mode,
        "buildPolicy": UI_MODE_BUILD_POLICY,
        "configExists": config_info.get("exists") is True,
        "configAvailable": runtime_available or config_info.get("exists") is True or config_info.get("autoDetected") is True,
        "configValid": config_info.get("valid") is True,
        "configSource": workflow_source or config_info.get("source"),
        "playConfigPath": play_config_path,
        "parityAvailable": config_info.get("parityAvailable") is True and workflow_source != "play-config",
        "parityWorkflowSource": config_info.get("parityWorkflowSource") or "",
        "parityConfigPath": config_info.get("parityConfigPath") or "",
        "configAutoDetected": config_info.get("autoDetected") is True,
        "configAutoSource": config_info.get("autoSource") or "",
        "configPath": config_info.get("path"),
        "configBranch": config_info.get("branch"),
        "configMissing": config_info.get("missing") or [],
        "configErrors": config_info.get("errors") or [],
        "configParseError": config_info.get("parseError"),
        "status": snapshot.get("status") or "idle",
        "kind": kind_by_state.get(state_name, "ready" if runtime_available else "idle"),
        "label": label_by_state.get(state_name, "UI status"),
        "title": summary,
        "summary": summary,
        "statusSummary": summary,
        "failureSummary": summary if state_name == "failed" else None,
        "lastLogLine": _last_log_line(logs),
        "running": snapshot.get("running") is True,
        "ready": snapshot.get("ready") is True,
        "error": snapshot.get("error"),
        "previewUrl": snapshot.get("preview_url"),
        "inspectUrl": snapshot.get("inspect_url") or snapshot.get("preview_url"),
        "allocatedPort": snapshot.get("allocated_port"),
        "allocatedPortHost": snapshot.get("allocated_port_host"),
        "allocatedPortEnvVar": snapshot.get("allocated_port_env_var"),
        "buildCommand": snapshot.get("build_command"),
        "command": snapshot.get("command"),
        "startedAt": snapshot.get("started_at"),
        "readyAt": snapshot.get("ready_at"),
        "finishedAt": snapshot.get("finished_at"),
        "updatedAt": snapshot.get("updated_at"),
        "logsAvailable": bool(logs),
    })


def build_project_ui_logs(project_id: str, limit: int | str = 1000) -> dict:
    try:
        count = max(50, min(5000, int(limit)))
    except Exception:
        count = 1000
    with _LOCK:
        state = _RUNTIMES.get(project_id)
        logs = list(state.logs[-count:]) if state else []
    return redact_payload({"logs": logs, "text": "\n".join(_format_log(entry) for entry in logs), "status": build_project_ui_status(project_id)})


def _proxy_error(handler, status: int, message: str) -> None:
    body = _redact_text(message).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _inject_ui_proxy_scripts(text: str, project_id: str) -> str:
    prefix = html.escape(_ui_proxy_prefix(project_id), quote=True)
    compat_path = Path(__file__).parent.parent / "static" / "ui-proxy-compat.js"
    try:
        compat_token = str(compat_path.stat().st_mtime_ns)
    except OSError:
        compat_token = WEBUI_VERSION
    compat_token = html.escape(urlparse.quote(str(compat_token), safe=""), quote=True)
    loader = f'<script src="/static/ui-proxy-compat.js?v={compat_token}" data-hermes-ui-proxy-prefix="{prefix}"></script>'
    lowered = text.lower()
    head_index = lowered.find("</head>")
    if head_index >= 0:
        return f"{text[:head_index]}{loader}{text[head_index:]}"
    return f"{loader}{text}"


def _rewrite_module_specifiers(text: str, project_id: str) -> str:
    prefix = _ui_proxy_prefix(project_id)

    def repl(match: re.Match) -> str:
        return f"{match.group(1)}{match.group(2)}{prefix}/{match.group(3)}{match.group(4)}"

    # Vite dev responses contain absolute ES module specifiers in both HTML inline scripts
    # and transformed JavaScript. If they stay rooted at '/', the iframe requests WebUI-root
    # paths like /@vite/client or /node_modules/... and the React app mounts as a blank page.
    for pattern in (
        r"(\bfrom\s*)([\"'])/(?!/)([^\"']*)([\"'])",
        r"(\bimport\s*)([\"'])/(?!/)([^\"']*)([\"'])",
        r"(\bimport\s*\(\s*)([\"'])/(?!/)([^\"']*)([\"'])",
    ):
        text = re.sub(pattern, repl, text)
    return text


def _rewrite_css_urls(text: str, project_id: str) -> str:
    prefix = _ui_proxy_prefix(project_id)

    def repl(match: re.Match) -> str:
        quote = match.group(1) or ""
        path = match.group(2)
        if path.startswith(prefix):
            return match.group(0)
        return f"url({quote}{prefix}{path}{quote}"

    return re.sub(r"url\(\s*([\"']?)(/(?!/)[^\"')\s]+)\1", repl, text, flags=re.I)


def _rewrite_proxy_text(body: bytes, project_id: str, *, rewrite_modules: bool = True, rewrite_css: bool = True) -> bytes:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body
    if rewrite_modules:
        text = _rewrite_module_specifiers(text, project_id)
    if rewrite_css:
        text = _rewrite_css_urls(text, project_id)
    return text.encode("utf-8")


def _rewrite_html(body: bytes, project_id: str) -> bytes:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body
    prefix = _ui_proxy_prefix(project_id)
    escaped_prefix = html.escape(prefix, quote=True)
    text = re.sub(r'\b(src|href|action|poster)=(["\'])/(?!/)', rf'\1=\2{escaped_prefix}/', text, flags=re.I)
    text = re.sub(r"\burl\(/(?!/)", f"url({prefix}/", text, flags=re.I)
    text = _rewrite_module_specifiers(text, project_id)
    text = _inject_ui_proxy_scripts(text, project_id)
    return text.encode("utf-8")


def _is_rewritable_proxy_text(content_type: str) -> bool:
    lowered = (content_type or "").lower()
    return any(marker in lowered for marker in ("javascript", "ecmascript", "text/css", "text/plain"))


def _rewrite_proxy_location(location: str, project_id: str, request_path: str) -> str:
    raw = str(location or "").strip()
    if not raw:
        return raw
    prefix = _ui_proxy_prefix(project_id)
    if raw.startswith(prefix):
        return raw
    parsed = urlparse.urlparse(raw)
    if parsed.scheme or parsed.netloc:
        if not _is_proxy_host_allowed(parsed.hostname):
            return raw
        target_path = parsed.path or "/"
        target_query = f"?{parsed.query}" if parsed.query else ""
        target_fragment = f"#{parsed.fragment}" if parsed.fragment else ""
        return f"{prefix}{target_path}{target_query}{target_fragment}"
    joined = urlparse.urljoin(request_path or "/", raw)
    joined_parsed = urlparse.urlparse(joined)
    target_path = joined_parsed.path or "/"
    target_query = f"?{joined_parsed.query}" if joined_parsed.query else ""
    target_fragment = f"#{joined_parsed.fragment}" if joined_parsed.fragment else ""
    return f"{prefix}{target_path}{target_query}{target_fragment}"


def _is_proxy_host_allowed(host: str | None) -> bool:
    normalized = (host or "").strip().lower()
    return normalized in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def _is_websocket_proxy_request(handler) -> bool:
    upgrade = str(handler.headers.get("Upgrade", "") or "").strip().lower()
    connection = str(handler.headers.get("Connection", "") or "").strip().lower()
    return upgrade == "websocket" and "upgrade" in connection


def _pipe_socket_bytes(source: socket.socket, target: socket.socket) -> None:
    try:
        while True:
            chunk = source.recv(65536)
            if not chunk:
                break
            target.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            target.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _handle_ui_proxy_websocket(handler, host: str, port: int, path: str, *, method: str = "GET") -> None:
    upstream = None
    try:
        upstream = socket.create_connection((host, int(port)), timeout=10)
        request_lines = [f"{method.upper()} {path} HTTP/1.1", f"Host: {host}:{int(port)}"]
        for key, value in handler.headers.items():
            lowered = key.lower()
            if lowered in {"host", "content-length"}:
                continue
            request_lines.append(f"{key}: {value}")
        upstream.sendall(("\r\n".join(request_lines) + "\r\n\r\n").encode("iso-8859-1"))
        response = b""
        while b"\r\n\r\n" not in response and len(response) < 65536:
            chunk = upstream.recv(4096)
            if not chunk:
                break
            response += chunk
        if not response:
            return _proxy_error(handler, 502, "UI WebSocket proxy did not receive a handshake response.")
        handler.connection.sendall(response)
        first_line = response.split(b"\r\n", 1)[0].lower()
        if b" 101 " not in first_line:
            return
        upstream.settimeout(None)
        handler.connection.settimeout(None)
        client_to_upstream = threading.Thread(target=_pipe_socket_bytes, args=(handler.connection, upstream), daemon=True)
        client_to_upstream.start()
        _pipe_socket_bytes(upstream, handler.connection)
        client_to_upstream.join(timeout=1)
    except Exception as exc:
        if upstream is None:
            return _proxy_error(handler, 502, f"UI WebSocket proxy failed: {exc}")
        try:
            handler.connection.close()
        except OSError:
            pass
    finally:
        try:
            if upstream:
                upstream.close()
        except OSError:
            pass


def handle_ui_proxy_request(handler, project_id: str, target_path: str, parsed, *, method: str = "GET") -> None:
    with _LOCK:
        state = _RUNTIMES.get(project_id)
        if state:
            host = state.allocated_port_host or "127.0.0.1"
            port = state.allocated_port
            ready = state.ready
            running = state.running
        else:
            host = "127.0.0.1"
            port = None
            ready = False
            running = False
    if not state or not ready or not running or not port:
        return _proxy_error(handler, 404, "UI project target not found.")
    if not _is_proxy_host_allowed(host):
        return _proxy_error(handler, 403, "UI proxy target host is not allowed.")

    path = target_path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    upstream_url = f"http://{host}:{int(port)}{path}"

    if _is_websocket_proxy_request(handler):
        return _handle_ui_proxy_websocket(handler, host, int(port), path, method=method)

    body = None
    if method.upper() not in {"GET", "HEAD"}:
        raw_body = getattr(handler, "_raw_body", None)
        if isinstance(raw_body, bytes):
            body = raw_body
        else:
            length = int(handler.headers.get("Content-Length", 0) or 0)
            body = handler.rfile.read(length) if length else b""
    headers = {}
    for key, value in handler.headers.items():
        lowered = key.lower()
        if lowered in HOP_BY_HOP_HEADERS or lowered in {"host", "content-length", "accept-encoding"}:
            continue
        headers[key] = value
    request = urlrequest.Request(upstream_url, data=body, headers=headers, method=method.upper())
    try:
        response = urlrequest.urlopen(request, timeout=30)
        status = response.status
        response_headers = response.headers
        response_body = response.read()
    except urlerror.HTTPError as exc:
        status = exc.code
        response_headers = exc.headers
        response_body = exc.read()
    except Exception as exc:
        return _proxy_error(handler, 502, f"UI proxy request failed: {exc}")

    content_type = response_headers.get("Content-Type", "")
    content_type_lower = content_type.lower()
    is_html = "text/html" in content_type_lower
    if is_html:
        response_body = _rewrite_html(response_body, project_id)
    elif _is_rewritable_proxy_text(content_type):
        response_body = _rewrite_proxy_text(response_body, project_id)

    handler.send_response(status)
    for key, value in response_headers.items():
        lowered = key.lower()
        if lowered in HOP_BY_HOP_HEADERS or lowered in {"content-length", "content-encoding", "cache-control", "expires", "pragma", "etag", "last-modified", "referrer-policy"}:
            continue
        if lowered == "location":
            value = _rewrite_proxy_location(value, project_id, target_path or "/")
        handler.send_header(key, value)
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Expires", "0")
    handler.send_header("Referrer-Policy", "same-origin")
    handler.send_header("Content-Length", str(len(response_body)))
    handler.end_headers()
    if method.upper() != "HEAD":
        handler.wfile.write(response_body)


def serve_ui_mode_shell(handler) -> bool:
    static_dir = (Path(__file__).parent.parent / "static").resolve()
    shell_path = static_dir / "ui-mode.html"
    script_path = static_dir / "ui-mode.js"
    try:
        script_version = f"{WEBUI_VERSION}-{script_path.stat().st_mtime_ns}-{time.time_ns()}"
    except Exception:
        script_version = f"{WEBUI_VERSION}-{time.time_ns()}"
    version_token = urlparse.quote(script_version, safe="")
    csrf_token = ""
    try:
        from api.auth import csrf_token_for_session, is_auth_enabled, parse_cookie, verify_session

        if is_auth_enabled():
            cookie_val = parse_cookie(handler)
            if cookie_val and verify_session(cookie_val):
                csrf_token = csrf_token_for_session(cookie_val) or ""
    except Exception:
        csrf_token = ""
    try:
        html_text = (
            shell_path.read_text(encoding="utf-8")
            .replace("__WEBUI_VERSION__", version_token)
            .replace("__CSRF_TOKEN_JSON__", json.dumps(csrf_token))
        )
    except Exception as exc:
        raise UiRuntimeError(f"Unable to load UI Mode shell: {exc}", status=503, code="UI_MODE_SHELL_UNAVAILABLE") from exc
    t(handler, html_text, content_type="text/html; charset=utf-8")
    return True

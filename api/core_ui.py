"""Core UI Mode live dev runtime and proxy boundary.

UI Mode is intentionally separate from the Play build pipeline: it starts a
project's dev server once, exposes status/logs through /api/core, and proxies a
live preview through /ui-project/{projectId}/... so framework HMR/live-reload can
update the iframe without production rebuilds.
"""

from __future__ import annotations

import html
import json
import os
import re
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
UI_LOG_LINE_LIMIT = 1000
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


def _package_manager_for_project(project_path: Path) -> str:
    if (project_path / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (project_path / "yarn.lock").exists():
        return "yarn"
    if (project_path / "bun.lockb").exists() or (project_path / "bun.lock").exists():
        return "bun"
    return "npm"


def _package_script_command(package_manager: str, script: str) -> str:
    if package_manager == "yarn":
        return f"yarn {script}"
    return f"{package_manager} run {script}"


def _auto_detect_ui_config(project_path: Path) -> dict | None:
    package_json = project_path / "package.json"
    if not package_json.exists():
        return None
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return None
    scripts_raw = payload.get("scripts") if isinstance(payload, dict) else {}
    scripts: dict[str, Any] = scripts_raw if isinstance(scripts_raw, dict) else {}
    script = "dev" if scripts.get("dev") else ("start" if scripts.get("start") else "")
    if not script:
        return None
    package_manager = _package_manager_for_project(project_path)
    return {
        "version": 1,
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

    config = {
        "version": int(source.get("version") or 1),
        "source": "ui-config",
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
    return {"valid": not missing and not errors, "missing": missing, "errors": errors, "config": config, "source": "ui-config"}


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
        payload["autoSource"] = "package.json"
        payload["source"] = normalized.get("source") or "auto"
        payload["playConfigPath"] = normalized.get("playConfigPath") or ""
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
    return payload


def get_project_ui_config(project_id: str) -> dict:
    project = _get_project(project_id)
    project_path = _project_path(project)
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
                    "autoSource": "package.json",
                    "source": normalized.get("source") or "auto",
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
        if _normalize_command((config.get("build") or {}).get("command")):
            with _BUILD_LOCK:
                if state.stop_requested:
                    return
                _mark_state(state, "building", running=True, ready=False, message="Starting UI build stage...")
                _run_build_stage(project_path, config, state)
        if state.stop_requested:
            return
        _mark_state(state, "starting", running=True, ready=False, message="Build complete. Starting UI runtime...")
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
    ui_config = get_project_ui_config(project_id)
    stop_project_ui_runtime(project_id, purge=True)
    state = UiRuntimeState(
        project_id=project_id,
        config_path=ui_config["path"],
        config_branch=ui_config["branch"],
        config_auto_detected=ui_config.get("autoDetected") is True,
        config_auto_source=str(ui_config.get("autoSource") or "") or None,
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
    if config_info.get("exists") is not True and config_info.get("autoDetected") is True:
        if config_info.get("valid") is True:
            return "Auto-detected UI workflow from package.json. Start UI Mode to inspect the live app."
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
    if config_info.get("source") == "play-config":
        return "UI Mode will use the project's Play build/start config. Start UI Mode to inspect the same app runtime as Play."
    return "UI workflow is ready. Start UI Mode to inspect the live app."


def _ui_runtime_available(config_info: dict) -> bool:
    return config_info.get("valid") is True


def _ui_workflow_source(config_info: dict) -> str:
    source = str(config_info.get("source") or "").strip()
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
    workflow_source = _ui_workflow_source(config_info)
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
        "configExists": config_info.get("exists") is True,
        "configAvailable": runtime_available or config_info.get("exists") is True or config_info.get("autoDetected") is True,
        "configValid": config_info.get("valid") is True,
        "configSource": config_info.get("source") or workflow_source,
        "playConfigPath": config_info.get("playConfigPath") or "",
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

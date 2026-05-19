"""Fork-owned Play pipeline for the clean restart branch."""

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from api import ops_projects


LEGACY_PLAY_FILE_NAME = "project_play.json"
MODERN_PLAY_FILE_NAME = ".cloud-terminal/play.json"
HERMES_PLAY_FILE_NAME = ".hermes/play.json"
PLAY_LOG_LINE_LIMIT = 1000
PLAY_BUILD_TIMEOUT_DEFAULT_MS = 30 * 60 * 1000
PLAY_READY_TIMEOUT_DEFAULT_MS = 10 * 60 * 1000
PLAY_READY_PATTERN = re.compile(r"(ready|listening|started|compiled|server running|running at)", re.I)
PLAY_PROJECT_PROXY_BASE_PATH = "/play-project"
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
_PIPELINES: dict[str, "PlayPipelineState"] = {}


class PlayPipelineError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class PlayPipelineState:
    project_id: str
    pipeline_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str | None = None
    task_id: str | None = None
    session_id: str | None = None
    status: str = "idle"
    running: bool = False
    ready: bool = False
    error: str | None = None
    inspect_url: str | None = None
    inspect_mode: str | None = None
    config_path: str | None = None
    config_branch: str | None = None
    started_at: str | None = None
    ready_at: str | None = None
    finished_at: str | None = None
    updated_at: float = field(default_factory=time.time)
    stop_requested: bool = False
    build_pid: int | None = None
    start_pid: int | None = None
    build_pgid: int | None = None
    start_pgid: int | None = None
    build_process: subprocess.Popen | None = None
    start_process: subprocess.Popen | None = None
    allocated_port: int | None = None
    allocated_port_host: str | None = None
    allocated_port_env_var: str | None = None
    logs: list[dict] = field(default_factory=list)
    repair_requested_at: str | None = None
    repair_stream_id: str | None = None
    repair_error: str | None = None


_BUILD_FAILURE_REPAIR_HANDLER = None


def register_build_failure_repair_handler(handler) -> None:
    """Register the WebUI session-turn handoff for failed Play builds."""
    global _BUILD_FAILURE_REPAIR_HANDLER
    _BUILD_FAILURE_REPAIR_HANDLER = handler if callable(handler) else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _project_label(project: dict) -> str:
    return str(project.get("fullName") or project.get("name") or project.get("slug") or project.get("id") or "Project")


def _project_path(project: dict) -> Path:
    raw = str(project.get("resolvedPath") or project.get("path") or "").strip()
    if not raw:
        raise PlayPipelineError("Project path is missing.", 500)
    path = Path(raw).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise PlayPipelineError("Project directory is missing on the server.", 404)
    return path


def _get_project(project_id: str) -> dict:
    try:
        return ops_projects.get_ops_project(project_id)
    except ops_projects.OpsProjectError as exc:
        raise PlayPipelineError(str(exc), exc.status) from exc


def _play_branch(project: dict) -> str:
    try:
        return ops_projects.tasks_branch(project)
    except Exception:
        return str(project.get("coreBranch") or "main")


def _append_log(state: PlayPipelineState, *, stage: str = "system", stream: str = "system", message: str = "") -> None:
    text = str(message or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return
    now = _now_iso()
    with _LOCK:
        for line in text.split("\n"):
            if not line:
                continue
            state.logs.append({"at": now, "stage": stage, "stream": stream, "message": line})
        if len(state.logs) > PLAY_LOG_LINE_LIMIT:
            del state.logs[: len(state.logs) - PLAY_LOG_LINE_LIMIT]
        state.updated_at = time.time()


def _format_log(entry: dict) -> str:
    return f"[{entry.get('at') or _now_iso()}] [{entry.get('stage') or 'system'}:{entry.get('stream') or 'system'}] {entry.get('message') or ''}"


def _last_log_line(logs: list[dict] | None) -> str:
    for entry in reversed(logs or []):
        message = str((entry or {}).get("message") or "").strip()
        if message:
            return message[:500]
    return ""


def _redact_repair_log_text(value: str, *, limit: int = 60000) -> str:
    text = str(value or "")[:limit]
    if not text:
        return ""
    try:
        from api.helpers import _redact_text

        text = _redact_text(text)
    except Exception:
        pass
    text = re.sub(r"(?i)(password|passwd|token|api[_-]?key|secret|authorization|cookie)(\s*[:=]\s*)([^\s'\"]+)", r"\1\2[REDACTED]", text)
    text = re.sub(r"(?i)(bearer\s+)[a-z0-9._~+/-]+=*", r"\1[REDACTED]", text)
    return text[:limit]


def _play_build_failure_repair_prompt(state: PlayPipelineState, message: str) -> str:
    logs = "\n".join(_format_log(entry) for entry in list(state.logs)[-200:])
    logs = _redact_repair_log_text(logs) or "(no build logs captured)"
    context = []
    if state.run_id:
        context.append(f"Run: {state.run_id}")
    if state.task_id:
        context.append(f"Task: {state.task_id}")
    if state.project_id:
        context.append(f"Project: {state.project_id}")
    context_text = "\n".join(context)
    if context_text:
        context_text = f"\n\n{context_text}"
    reason = _redact_repair_log_text(message, limit=4000) or "Play build failed."
    return (
        "The build failed, these are the logs, analyze them and fix the issue."
        f"{context_text}\n\nFailure reason: {reason}\n\n"
        "Logs:\n```text\n"
        f"{logs}\n"
        "```"
    )


def _resolve_build_failure_repair_handler():
    if callable(_BUILD_FAILURE_REPAIR_HANDLER):
        return _BUILD_FAILURE_REPAIR_HANDLER
    try:
        from api import routes

        handler = getattr(routes, "start_play_build_failure_repair_turn", None)
        return handler if callable(handler) else None
    except Exception:
        return None


def _request_build_failure_repair(state: PlayPipelineState, message: str) -> None:
    session_id = str(state.session_id or "").strip()
    if not session_id:
        return
    with _LOCK:
        if state.repair_requested_at:
            return
    handler = _resolve_build_failure_repair_handler()
    if not callable(handler):
        with _LOCK:
            state.repair_error = "No session repair handler is registered."
        _append_log(state, stage="system", stream="stderr", message="Could not send build failure logs back to session: no repair handler is registered.")
        return
    prompt = _play_build_failure_repair_prompt(state, message)
    metadata = {
        "projectId": state.project_id,
        "runId": state.run_id or "",
        "taskId": state.task_id or "",
        "pipelineId": state.pipeline_id,
        "reason": message,
    }
    try:
        result = handler(session_id, prompt, metadata)
    except Exception as exc:
        with _LOCK:
            state.repair_error = str(exc) or exc.__class__.__name__
        _append_log(state, stage="system", stream="stderr", message=f"Could not send build failure logs back to session: {state.repair_error}")
        return
    if isinstance(result, dict) and result.get("ok") is False:
        error_text = str(result.get("error") or "Session repair handoff failed.")
        with _LOCK:
            state.repair_error = error_text
        _append_log(state, stage="system", stream="stderr", message=f"Could not send build failure logs back to session: {error_text}")
        return
    stream_id = str((result or {}).get("stream_id") or (result or {}).get("streamId") or "").strip() if isinstance(result, dict) else ""
    now = _now_iso()
    with _LOCK:
        state.repair_requested_at = now
        state.repair_stream_id = stream_id or None
        state.repair_error = None
        state.updated_at = time.time()
    suffix = f" (stream {stream_id})" if stream_id else ""
    _append_log(state, stage="system", stream="stdout", message=f"Sent build failure logs back to session for automatic repair{suffix}.")


def _mark_state(
    state: PlayPipelineState,
    status: str,
    *,
    running: bool = False,
    ready: bool = False,
    error: str | None = None,
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
        state.updated_at = time.time()
        if inspect_url is not None:
            state.inspect_url = inspect_url or None
        if set_started_at:
            state.started_at = _now_iso()
        if set_ready_at:
            state.ready_at = _now_iso()
        if set_finished_at:
            state.finished_at = _now_iso()
    if message:
        _append_log(state, stage="system", stream="stderr" if status == "failed" else "stdout", message=message)


def _normalize_command(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


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
        if isinstance(raw, bool):
            env[name] = "true" if raw else "false"
        else:
            env[name] = str(raw)
    return env


def _normalize_relative_cwd(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    return text or "."


def _resolve_cwd(project_path: Path, raw_cwd: str) -> Path:
    resolved = (project_path / _normalize_relative_cwd(raw_cwd)).resolve()
    try:
        resolved.relative_to(project_path)
    except ValueError as exc:
        raise PlayPipelineError("Play command cwd must stay inside the project directory.") from exc
    return resolved


def _normalize_inspect_mode(value: Any) -> str:
    return "proxy" if isinstance(value, str) and value.strip().lower() == "proxy" else "direct"


def _normalize_port_host(value: Any) -> str:
    host = value.strip().lower() if isinstance(value, str) else ""
    return host or "127.0.0.1"


def _normalize_port_range(value: Any) -> dict[str, int]:
    source = value if isinstance(value, dict) else {}
    try:
        minimum = int(source.get("min", 20000))
    except Exception:
        minimum = 20000
    try:
        maximum = int(source.get("max", 29999))
    except Exception:
        maximum = 29999
    minimum = max(1024, minimum)
    maximum = min(65535, maximum)
    if maximum < minimum:
        return {"min": 20000, "max": 29999}
    return {"min": minimum, "max": maximum}


def _normalize_ready_timeout_ms(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = PLAY_READY_TIMEOUT_DEFAULT_MS
    return max(5000, min(30 * 60 * 1000, parsed))


def _normalize_build_timeout_ms(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = PLAY_BUILD_TIMEOUT_DEFAULT_MS
    return max(1000, min(6 * 60 * 60 * 1000, parsed))


def normalize_play_config(payload: dict, project_path: Path) -> dict:
    source = payload if isinstance(payload, dict) else {}
    build_section = source.get("build") if isinstance(source.get("build"), dict) else {}
    start_section = source.get("start") if isinstance(source.get("start"), dict) else {}
    if not start_section and isinstance(source.get("run"), dict):
        start_section = source["run"]
    inspect_section = source.get("inspect") if isinstance(source.get("inspect"), dict) else {}
    port_section = start_section.get("port") if isinstance(start_section.get("port"), dict) else {}

    inspect_url = _normalize_command(
        inspect_section.get("url") or source.get("inspectUrl") or source.get("previewUrl") or source.get("url")
    )
    inspect_mode = _normalize_inspect_mode(inspect_section.get("mode") or source.get("inspectMode"))
    start_port_mode = "auto" if str(port_section.get("mode") or "").strip().lower() == "auto" else "fixed"
    build_only = bool(source.get("buildOnly") is True or source.get("build_only") is True)

    config = {
        "version": int(source.get("version") or 2),
        "buildOnly": build_only,
        "build": {
            "command": _normalize_command(build_section.get("command") or source.get("buildCommand")),
            "cwd": _normalize_relative_cwd(build_section.get("cwd") or source.get("buildCwd")),
            "env": _normalize_env(build_section.get("env") or source.get("buildEnv")),
            "timeoutMs": _normalize_build_timeout_ms(build_section.get("timeoutMs") or source.get("buildTimeoutMs")),
        },
        "start": {
            "command": _normalize_command(start_section.get("command") or source.get("startCommand") or source.get("runCommand")),
            "cwd": _normalize_relative_cwd(start_section.get("cwd") or source.get("startCwd") or source.get("runCwd")),
            "env": _normalize_env(start_section.get("env") or source.get("startEnv") or source.get("runEnv")),
            "port": {
                "mode": start_port_mode,
                "host": _normalize_port_host(port_section.get("host")),
                "envVar": _normalize_command(port_section.get("envVar")) or "PORT",
                "range": _normalize_port_range(port_section.get("range")),
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
    if not config["build"]["command"]:
        missing.append("build.command")
    if not build_only:
        if not config["start"]["command"]:
            missing.append("start.command")
        if not inspect_url:
            missing.append("inspect.url")
        if inspect_mode == "direct" and inspect_url.startswith("/"):
            missing.append("inspect.url")
        if inspect_mode == "proxy" and start_port_mode != "auto":
            missing.append("start.port.mode")

    return {"valid": not missing, "missing": missing, "errors": [], "config": config}


def _config_candidates(project_path: Path) -> list[Path]:
    return [
        project_path / HERMES_PLAY_FILE_NAME,
        project_path / LEGACY_PLAY_FILE_NAME,
        project_path / MODERN_PLAY_FILE_NAME,
    ]


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


def _auto_detect_play_config(project_path: Path) -> dict | None:
    package_json = project_path / "package.json"
    if not package_json.exists():
        return None
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return None
    scripts = payload.get("scripts") if isinstance(payload, dict) and isinstance(payload.get("scripts"), dict) else {}
    if not scripts:
        return None
    package_manager = _package_manager_for_project(project_path)
    build_script = "build" if scripts.get("build") else ""
    start_script = "start" if scripts.get("start") else ("dev" if scripts.get("dev") else "")
    if not build_script and not start_script:
        return None
    return {
        "version": 2,
        "buildOnly": bool(build_script and not start_script),
        "build": {
            "command": _package_script_command(package_manager, build_script) if build_script else "true",
            "cwd": ".",
            "env": {"CI": "true"},
        },
        "start": {
            "command": _package_script_command(package_manager, start_script) if start_script else "",
            "cwd": ".",
            "env": {"HOST": "127.0.0.1"},
            "port": {
                "mode": "auto",
                "host": "127.0.0.1",
                "envVar": "PORT",
                "range": {"min": 20000, "max": 29999},
            },
        },
        "inspect": {"mode": "proxy", "url": "/"},
    }


def get_project_play_config_file_info(project_id: str) -> dict:
    project = _get_project(project_id)
    project_path = _project_path(project)
    candidates = _config_candidates(project_path)
    selected = next((path for path in candidates if path.exists()), candidates[0])
    payload = {
        "path": str(selected),
        "branch": _play_branch(project),
        "scope": "shared",
        "exists": selected.exists(),
        "configured": False,
        "valid": False,
        "missing": [],
        "errors": [],
        "parseError": None,
    }
    if not selected.exists():
        auto_config = _auto_detect_play_config(project_path)
        if not auto_config:
            return payload
        normalized = normalize_play_config(auto_config, project_path)
        payload["configured"] = normalized["valid"]
        payload["valid"] = normalized["valid"]
        payload["missing"] = normalized["missing"]
        payload["errors"] = normalized["errors"]
        payload["buildOnly"] = normalized["config"].get("buildOnly") is True
        payload["autoDetected"] = True
        payload["autoSource"] = "package.json"
        return payload
    try:
        raw = json.loads(selected.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        payload["parseError"] = "Play config file is invalid JSON."
        return payload
    normalized = normalize_play_config(raw, project_path)
    payload["valid"] = normalized["valid"]
    payload["configured"] = normalized["valid"]
    payload["missing"] = normalized["missing"]
    payload["errors"] = normalized["errors"]
    payload["buildOnly"] = normalized["config"].get("buildOnly") is True
    return payload


def get_project_play_config(project_id: str) -> dict:
    project = _get_project(project_id)
    project_path = _project_path(project)
    info = get_project_play_config_file_info(project_id)
    if not info["exists"]:
        auto_config = _auto_detect_play_config(project_path)
        if auto_config:
            normalized = normalize_play_config(auto_config, project_path)
            if normalized["valid"]:
                return {
                    "project": project,
                    "projectPath": project_path,
                    "path": info["path"],
                    "branch": info["branch"],
                    "config": normalized["config"],
                    "autoDetected": True,
                    "autoSource": "package.json",
                }
            missing = ", ".join(normalized["missing"])
            raise PlayPipelineError(f"Auto-detected Play config is incomplete. Missing: {missing}.")
        raise PlayPipelineError("Play config file not found for this project.", 404)
    if info.get("parseError"):
        raise PlayPipelineError(info["parseError"])
    try:
        raw = json.loads(Path(info["path"]).read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise PlayPipelineError("Play config file is invalid JSON.") from exc
    normalized = normalize_play_config(raw, project_path)
    if not normalized["valid"]:
        missing = ", ".join(normalized["missing"])
        raise PlayPipelineError(f"Play config is invalid. Missing: {missing}.")
    return {"project": project, "projectPath": project_path, "path": info["path"], "branch": info["branch"], "config": normalized["config"]}


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
    minimum = int(port_range.get("min") or 20000)
    maximum = int(port_range.get("max") or 29999)
    span = max(1, maximum - minimum + 1)
    start = int(time.time() * 1000) % span
    for offset in range(span):
        port = minimum + ((start + offset) % span)
        if not _try_reserve_port(host, port):
            continue
        if _probe_port_available(host, port):
            return port
        _release_port(host, port)
    raise PlayPipelineError(f"Port allocation failure: no free port in range {minimum}-{maximum}.")


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def _interpolate_port(value: str, env_var: str, port: int) -> str:
    return str(value or "").replace(f"${{{env_var}}}", str(port)).replace(f"${env_var}", str(port))


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


def _build_proxy_inspect_url(project_id: str, inspect_path: str) -> str:
    path = inspect_path if inspect_path.startswith("/") else f"/{inspect_path}"
    return f"{PLAY_PROJECT_PROXY_BASE_PATH}/{urlparse.quote(project_id, safe='')}{path}"


def _build_command_env(overrides: dict[str, str]) -> dict[str, str]:
    env = dict(os.environ)
    env.update({str(key): str(value) for key, value in (overrides or {}).items() if value is not None})
    for key in ("TERMINAL_SU_PASSWORD", "SU_PASSWORD", "TERMINAL_SU_USER", "SU_USER"):
        env.pop(key, None)
    return env


def _spawn_stage(project_path: Path, command: str, cwd: str, env: dict[str, str]) -> subprocess.Popen:
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


def _reader_thread(state: PlayPipelineState, proc: subprocess.Popen, stream_name: str, stage: str, ready_regex: re.Pattern | None, ready_event: threading.Event | None) -> None:
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


def _run_build_stage(project_path: Path, config: dict, state: PlayPipelineState) -> None:
    command = config["build"]["command"]
    env = dict(config["build"].get("env") or {})
    timeout_ms = _normalize_build_timeout_ms(config["build"].get("timeoutMs"))
    proc = _spawn_stage(project_path, command, config["build"].get("cwd") or ".", env)
    with _LOCK:
        state.build_process = proc
        state.build_pid = int(proc.pid)
        state.build_pgid = int(proc.pid)
    _append_log(state, stage="build", stream="system", message=f"Running: {command}")
    _append_log(state, stage="build", stream="system", message=f"Build timeout: {round(timeout_ms / 1000)}s")
    threads = [
        threading.Thread(target=_reader_thread, args=(state, proc, "stdout", "build", None, None), daemon=True),
        threading.Thread(target=_reader_thread, args=(state, proc, "stderr", "build", None, None), daemon=True),
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
        state.build_process = None
        state.build_pid = None
        state.build_pgid = None
    if state.stop_requested:
        return
    if timed_out:
        raise PlayPipelineError(f"Build timeout after {round(timeout_ms / 1000)}s.", 500)
    if code != 0:
        raise PlayPipelineError(f"Build failed: process exited with code {code}.", 500)
    _append_log(state, stage="build", stream="system", message="Build stage completed successfully.")


def _prepare_start_runtime(project_id: str, config: dict, state: PlayPipelineState) -> dict:
    start_config = dict(config["start"])
    start_env = dict(start_config.get("env") or {})
    inspect = config["inspect"]
    inspect_mode = inspect["mode"]
    inspect_url = inspect["url"]
    state.inspect_mode = inspect_mode

    auto_port = start_config.get("port", {}).get("mode") == "auto"
    if auto_port:
        port_cfg = start_config["port"]
        host = _normalize_port_host(port_cfg.get("host"))
        env_var = _normalize_command(port_cfg.get("envVar")) or "PORT"
        port = _allocate_port(host, port_cfg.get("range") or {})
        start_env[env_var] = str(port)
        inspect_url = _interpolate_port(inspect_url, env_var, port)
        state.allocated_port = port
        state.allocated_port_host = host
        state.allocated_port_env_var = env_var

    if inspect_mode == "proxy":
        if not state.allocated_port:
            raise PlayPipelineError("Play config requires start.port.mode=auto when inspect.mode=proxy.")
        _, inspect_path = _normalize_proxy_path(inspect_url)
        inspect_url = _build_proxy_inspect_url(project_id, inspect_path)

    start_config["env"] = start_env
    return {"config": {**config, "start": start_config}, "inspectUrl": inspect_url, "autoPort": auto_port}


def _run_start_stage(project: dict, project_path: Path, runtime: dict, state: PlayPipelineState) -> None:
    config = runtime["config"]
    start_config = config["start"]
    inspect_url = runtime["inspectUrl"]
    ready_pattern = config["inspect"].get("readyPattern") or ""
    ready_regex = re.compile(ready_pattern, re.I) if ready_pattern else PLAY_READY_PATTERN
    ready_timeout = _normalize_ready_timeout_ms(config["inspect"].get("readyTimeoutMs"))
    ready_event = threading.Event()
    command = start_config["command"]
    stage_env = dict(start_config.get("env") or {})
    proc = _spawn_stage(project_path, command, start_config.get("cwd") or ".", stage_env)
    with _LOCK:
        state.start_process = proc
        state.start_pid = int(proc.pid)
        state.start_pgid = int(proc.pid)
    _append_log(state, stage="start", stream="system", message=f"Running: {command}")
    _append_log(state, stage="start", stream="system", message=f"Effective inspect URL: {inspect_url}")
    threads = []
    for stream_name in ("stdout", "stderr"):
        thread = threading.Thread(
            target=_reader_thread,
            args=(state, proc, stream_name, "start", ready_regex, ready_event),
            daemon=True,
        )
        thread.start()
        threads.append(thread)

    deadline = time.time() + (ready_timeout / 1000)
    fallback_ready_at = time.time() + 2.5 if not ready_pattern and not state.allocated_port else None
    while time.time() <= deadline:
        if state.stop_requested:
            return
        code = proc.poll()
        if code is not None:
            _join_reader_threads(threads)
            raise PlayPipelineError(f"Start exited before ready (exit code {code}).", 500)
        if ready_event.is_set():
            break
        if state.allocated_port and _is_port_open(state.allocated_port_host or "127.0.0.1", state.allocated_port):
            break
        if fallback_ready_at and time.time() >= fallback_ready_at:
            break
        time.sleep(0.2)
    else:
        _terminate_process(proc)
        raise PlayPipelineError(f"Ready timeout after {round(ready_timeout / 1000)}s.", 500)

    _mark_state(
        state,
        "ready",
        running=True,
        ready=True,
        inspect_url=inspect_url,
        set_ready_at=True,
        message=f"{_project_label(project)} is ready for inspection.",
    )

    code = proc.wait()
    _join_reader_threads(threads)
    with _LOCK:
        state.start_process = None
        state.start_pid = None
        state.start_pgid = None
    _release_port(state.allocated_port_host, state.allocated_port)
    if state.stop_requested:
        _mark_state(state, "stopped", running=False, ready=False, set_finished_at=True, message="Play server stopped.")
    elif code == 0:
        _mark_state(state, "stopped", running=False, ready=False, set_finished_at=True, message="Play server exited.")
    else:
        _mark_state(state, "failed", running=False, ready=False, error=f"Play server exited with code {code}.", set_finished_at=True)


def _pipeline_worker(play_config: dict, state: PlayPipelineState) -> None:
    project = play_config["project"]
    project_path = play_config["projectPath"]
    config = play_config["config"]
    build_completed = False
    try:
        if state.status == "queued":
            _append_log(state, stage="build", stream="system", message="Waiting for another Play build to finish...")
        with _BUILD_LOCK:
            if state.stop_requested:
                return
            _mark_state(state, "building", running=True, ready=False, message="Starting Play build stage...")
            _run_build_stage(project_path, config, state)
            build_completed = True
        if state.stop_requested:
            return
        if config.get("buildOnly") is True:
            _mark_state(
                state,
                "built",
                running=False,
                ready=False,
                set_finished_at=True,
                message=f"{_project_label(project)} package-script build completed.",
            )
            return
        runtime = _prepare_start_runtime(state.project_id, config, state)
        if state.allocated_port:
            _append_log(
                state,
                stage="start",
                stream="system",
                message=f"Allocated port: {state.allocated_port} (host {state.allocated_port_host or '127.0.0.1'}).",
            )
        _mark_state(state, "starting", running=True, ready=False, inspect_url=runtime["inspectUrl"], message="Build complete. Starting application...")
        _run_start_stage(project, project_path, runtime, state)
    except Exception as exc:
        if state.stop_requested:
            return
        build_stage_failed = not build_completed and state.status == "building"
        _terminate_process(state.build_process)
        _terminate_process(state.start_process)
        _release_port(state.allocated_port_host, state.allocated_port)
        message = str(exc) or "Play pipeline failed."
        _append_log(state, stage="system", stream="stderr", message=f"Failure reason: {message}")
        _mark_state(state, "failed", running=False, ready=False, error=message, set_finished_at=True, message=message)
        if build_stage_failed:
            _request_build_failure_repair(state, message)


def start_project_play_pipeline(project_id: str, body: dict | None = None) -> dict:
    _body = body if isinstance(body, dict) else {}
    terminal_target = _body.get("terminalTarget") if isinstance(_body.get("terminalTarget"), dict) else {}
    play_config = get_project_play_config(project_id)
    stop_project_play_pipeline(project_id, purge=True)
    state = PlayPipelineState(
        project_id=project_id,
        config_path=play_config["path"],
        config_branch=play_config["branch"],
        run_id=str(_body.get("runId") or _body.get("run_id") or terminal_target.get("runId") or terminal_target.get("run_id") or "").strip() or None,
        task_id=str(_body.get("taskId") or _body.get("task_id") or terminal_target.get("taskId") or terminal_target.get("task_id") or "").strip() or None,
        session_id=str(_body.get("sessionId") or _body.get("session_id") or terminal_target.get("sessionId") or terminal_target.get("session_id") or "").strip() or None,
    )
    queued = _BUILD_LOCK.locked()
    _mark_state(
        state,
        "queued" if queued else "building",
        running=True,
        ready=False,
        set_started_at=True,
        message="Play build queued. Waiting for another project build to finish..." if queued else "Starting Play build stage...",
    )
    with _LOCK:
        _PIPELINES[project_id] = state
    threading.Thread(target=_pipeline_worker, args=(play_config, state), daemon=True).start()
    return build_project_play_status(project_id)


def restart_project_play_pipeline(project_id: str, body: dict | None = None) -> dict:
    stop_project_play_pipeline(project_id, purge=True)
    return start_project_play_pipeline(project_id, body)


def stop_project_play_pipeline(project_id: str, *, purge: bool = False) -> dict | None:
    with _LOCK:
        state = _PIPELINES.get(project_id)
    if not state:
        return None
    state.stop_requested = True
    _terminate_process(state.build_process)
    _terminate_process(state.start_process)
    with _LOCK:
        state.build_process = None
        state.start_process = None
        state.build_pid = None
        state.start_pid = None
        state.build_pgid = None
        state.start_pgid = None
    _release_port(state.allocated_port_host, state.allocated_port)
    if purge:
        with _LOCK:
            _PIPELINES.pop(project_id, None)
        return None
    _mark_state(state, "stopped", running=False, ready=False, set_finished_at=True, message="Play pipeline stopped.")
    return build_project_play_status(project_id)


def _play_status_summary(config_info: dict, snapshot: dict) -> str:
    if config_info.get("parseError"):
        return str(config_info["parseError"])
    build_only = config_info.get("buildOnly") is True
    state = str(snapshot.get("status") or "idle").strip().lower()
    if state == "queued":
        return "Play build is queued."
    if state == "building":
        return "Play build is running."
    if state == "starting":
        return "Play application is starting."
    if state == "ready":
        inspect_url = str(snapshot.get("inspect_url") or "").strip()
        return f"Play app is ready at {inspect_url}." if inspect_url else "Play app is ready."
    if state == "built":
        return "Package-script build completed successfully."
    if state == "failed":
        return str(snapshot.get("error") or "Play pipeline failed.")
    if state == "stopped":
        return "Play pipeline is stopped."
    if config_info.get("exists") is not True and config_info.get("autoDetected") is True:
        if config_info.get("valid") is True:
            if build_only:
                return "Auto-detected package-script build workflow from package.json. Build the project to verify it."
            return "Auto-detected Play workflow from package.json. Start the pipeline to inspect the app."
        missing = config_info.get("missing") or []
        return f"Auto-detected Play workflow is incomplete. Missing: {', '.join(str(part) for part in missing)}"
    if config_info.get("exists") is not True:
        return "No Play config found for this project."
    if config_info.get("valid") is not True:
        missing = config_info.get("missing") or []
        return f"Play config is incomplete. Missing: {', '.join(str(part) for part in missing)}"
    return "Package-script build workflow is ready." if build_only else "Play config is ready. Start the pipeline to inspect the app."


def _play_build_available(config_info: dict) -> bool:
    """Return whether the project has a runnable Build workflow.

    Build eligibility comes from the normalized workflow, not from the
    existence of a legacy per-project Play config file. A workflow may be
    backed by a shared/modern Play config or by auto-detected package scripts.
    """

    return config_info.get("valid") is True


def _play_workflow_source(config_info: dict) -> str:
    if config_info.get("autoDetected") is True:
        return str(config_info.get("autoSource") or "auto").strip() or "auto"
    if config_info.get("exists") is True:
        return "play-config"
    return ""


def build_project_play_status(project_id: str) -> dict:
    config_info = get_project_play_config_file_info(project_id)
    with _LOCK:
        state = _PIPELINES.get(project_id)
        snapshot = dict(state.__dict__) if state else {}
    summary = _play_status_summary(config_info, snapshot)
    state_name = str(snapshot.get("status") or "idle").lower()
    build_available = _play_build_available(config_info)
    workflow_source = _play_workflow_source(config_info)
    label_by_state = {
        "idle": "Build ready" if build_available else "Build unavailable",
        "queued": "Build queued",
        "building": "Building",
        "starting": "Starting",
        "ready": "Play ready",
        "built": "Built",
        "failed": "Build failed",
        "stopped": "Stopped",
    }
    kind_by_state = {
        "queued": "warning",
        "building": "warning",
        "starting": "warning",
        "ready": "ready",
        "built": "ready",
        "failed": "error",
        "stopped": "idle",
    }
    inspect_url = snapshot.get("inspect_url")
    raw_logs = snapshot.get("logs")
    logs = list(raw_logs) if isinstance(raw_logs, list) else []
    payload = {
        "projectId": project_id,
        "pipelineId": snapshot.get("pipeline_id"),
        "runId": snapshot.get("run_id"),
        "taskId": snapshot.get("task_id"),
        "sessionId": snapshot.get("session_id"),
        "terminalTarget": {
            "projectId": project_id,
            "runId": snapshot.get("run_id") or "",
            "taskId": snapshot.get("task_id") or "",
            "sessionId": snapshot.get("session_id") or "",
        },
        "configured": config_info.get("configured") is True,
        "valid": config_info.get("valid") is True,
        "buildAvailable": build_available,
        "canBuild": build_available,
        "buildUnavailableReason": "" if build_available else summary,
        "workflowSource": workflow_source,
        "configExists": config_info.get("exists") is True,
        "configAvailable": build_available or config_info.get("exists") is True or config_info.get("autoDetected") is True,
        "configValid": config_info.get("valid") is True,
        "configAutoDetected": config_info.get("autoDetected") is True,
        "configAutoSource": config_info.get("autoSource") or "",
        "buildOnly": config_info.get("buildOnly") is True,
        "configPath": config_info.get("path"),
        "configBranch": config_info.get("branch"),
        "configMissing": config_info.get("missing") or [],
        "configErrors": config_info.get("errors") or [],
        "configParseError": config_info.get("parseError"),
        "status": snapshot.get("status") or "idle",
        "kind": kind_by_state.get(state_name, "ready" if config_info.get("valid") is True else "idle"),
        "label": label_by_state.get(state_name, "Play status"),
        "title": summary,
        "summary": summary,
        "statusSummary": summary,
        "failureSummary": summary if state_name == "failed" else None,
        "lastLogLine": _last_log_line(snapshot.get("logs") if isinstance(snapshot.get("logs"), list) else []),
        "running": snapshot.get("running") is True,
        "ready": snapshot.get("ready") is True,
        "error": snapshot.get("error"),
        "inspectUrl": inspect_url,
        "inspectMode": snapshot.get("inspect_mode"),
        "allocatedPort": snapshot.get("allocated_port"),
        "allocatedPortHost": snapshot.get("allocated_port_host"),
        "startedAt": snapshot.get("started_at"),
        "readyAt": snapshot.get("ready_at"),
        "finishedAt": snapshot.get("finished_at"),
        "updatedAt": snapshot.get("updated_at"),
        "repairRequestedAt": snapshot.get("repair_requested_at"),
        "repairStreamId": snapshot.get("repair_stream_id"),
        "repairError": snapshot.get("repair_error"),
        "logsAvailable": bool(snapshot.get("logs")),
    }
    if state_name == "failed" and logs:
        payload["playLogs"] = logs
        payload["playLogText"] = "\n".join(_format_log(entry) for entry in logs)
    return payload


def build_project_play_logs(project_id: str, limit: int = 1000) -> dict:
    try:
        count = max(50, min(5000, int(limit)))
    except Exception:
        count = 1000
    with _LOCK:
        state = _PIPELINES.get(project_id)
        logs = list(state.logs[-count:]) if state else []
    return {
        "logs": logs,
        "text": "\n".join(_format_log(entry) for entry in logs),
        "status": build_project_play_status(project_id),
    }


def _proxy_error(handler, status: int, message: str) -> None:
    body = message.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _play_proxy_prefix(project_id: str) -> str:
    return f"{PLAY_PROJECT_PROXY_BASE_PATH}/{urlparse.quote(project_id, safe='')}"


def _play_proxy_overlay_attributes(project_id: str) -> str:
    with _LOCK:
        state = _PIPELINES.get(project_id)
        if not state or not state.session_id:
            return ""
        values = {
            "data-hermes-play-overlay": "enabled",
            "data-hermes-play-project-id": project_id,
            "data-hermes-play-run-id": state.run_id or "",
            "data-hermes-play-task-id": state.task_id or "",
            "data-hermes-play-session-id": state.session_id or "",
            "data-hermes-play-session-url": f"/session/{urlparse.quote(state.session_id or '', safe='')}",
        }
    return " ".join(f'{name}="{html.escape(str(value), quote=True)}"' for name, value in values.items())


def _inject_play_proxy_scripts(text: str, project_id: str) -> str:
    prefix = html.escape(_play_proxy_prefix(project_id), quote=True)
    overlay_attrs = _play_proxy_overlay_attributes(project_id)
    overlay_loader = f'<script src="/static/play-session-overlay.js" {overlay_attrs}></script>' if overlay_attrs else ""
    loader = (
        f'<script src="/static/play-proxy-compat.js" data-hermes-play-proxy-prefix="{prefix}"></script>'
        f"{overlay_loader}"
    )
    lowered = text.lower()
    head_index = lowered.find("</head>")
    if head_index >= 0:
        return f"{text[:head_index]}{loader}{text[head_index:]}"
    return f"{loader}{text}"


def _rewrite_html(body: bytes, project_id: str) -> bytes:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body
    prefix = _play_proxy_prefix(project_id)
    escaped_prefix = html.escape(prefix, quote=True)
    text = re.sub(r'\b(src|href|action|poster)=(["\'])/(?!/)', rf'\1=\2{escaped_prefix}/', text, flags=re.I)
    text = re.sub(r"\burl\(/(?!/)", f"url({prefix}/", text, flags=re.I)
    text = _inject_play_proxy_scripts(text, project_id)
    return text.encode("utf-8")


def _rewrite_proxy_csp_source_directive(directive: str, required_sources: tuple[str, ...]) -> str:
    parts = [part for part in str(directive or "").split() if part]
    if not parts:
        return directive
    name = parts[0]
    sources = parts[1:]
    if required_sources:
        sources = [source for source in sources if source.lower() != "'none'"]
    seen = {source.lower() for source in sources}
    for required in required_sources:
        if required.lower() not in seen:
            sources.append(required)
            seen.add(required.lower())
    return " ".join([name, *sources])


def _rewrite_proxy_csp(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return raw
    directives = [segment.strip() for segment in raw.split(";")]
    rewritten: list[str] = []
    frame_src_seen = False
    child_src_seen = False
    script_src_seen = False
    script_src_elem_seen = False
    style_src_seen = False
    style_src_elem_seen = False
    for directive in directives:
        if not directive:
            continue
        lower = directive.lower()
        if lower.startswith("frame-src"):
            rewritten.append(_rewrite_proxy_csp_source_directive(directive, ("'self'",)))
            frame_src_seen = True
            continue
        if lower.startswith("child-src"):
            rewritten.append(_rewrite_proxy_csp_source_directive(directive, ("'self'",)))
            child_src_seen = True
            continue
        if lower.startswith("script-src-elem"):
            rewritten.append(_rewrite_proxy_csp_source_directive(directive, ("'self'",)))
            script_src_elem_seen = True
            continue
        if lower.startswith("script-src"):
            rewritten.append(_rewrite_proxy_csp_source_directive(directive, ("'self'",)))
            script_src_seen = True
            continue
        if lower.startswith("style-src-elem"):
            rewritten.append(_rewrite_proxy_csp_source_directive(directive, ("'self'", "'unsafe-inline'")))
            style_src_elem_seen = True
            continue
        if lower.startswith("style-src"):
            rewritten.append(_rewrite_proxy_csp_source_directive(directive, ("'self'", "'unsafe-inline'")))
            style_src_seen = True
            continue
        rewritten.append(directive)
    if not frame_src_seen:
        rewritten.append("frame-src 'self'")
    if not child_src_seen:
        rewritten.append("child-src 'self'")
    if not script_src_seen:
        rewritten.append("script-src 'self'")
    if not script_src_elem_seen:
        rewritten.append("script-src-elem 'self'")
    if not style_src_seen:
        rewritten.append("style-src 'self' 'unsafe-inline'")
    if not style_src_elem_seen:
        rewritten.append("style-src-elem 'self' 'unsafe-inline'")
    return "; ".join(segment for segment in rewritten if segment)


def _rewrite_proxy_location(location: str, project_id: str, request_path: str) -> str:
    raw = str(location or "").strip()
    if not raw:
        return raw
    prefix = _play_proxy_prefix(project_id)
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


def _handle_play_proxy_websocket(handler, host: str, port: int, path: str, *, method: str = "GET") -> None:
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
            return _proxy_error(handler, 502, "Play WebSocket proxy did not receive a handshake response.")
        handler.connection.sendall(response)
        first_line = response.split(b"\r\n", 1)[0].lower()
        if b" 101 " not in first_line:
            return

        upstream.settimeout(None)
        handler.connection.settimeout(None)
        client_to_upstream = threading.Thread(
            target=_pipe_socket_bytes,
            args=(handler.connection, upstream),
            daemon=True,
        )
        client_to_upstream.start()
        _pipe_socket_bytes(upstream, handler.connection)
        client_to_upstream.join(timeout=1)
    except Exception as exc:
        if upstream is None:
            return _proxy_error(handler, 502, f"Play WebSocket proxy failed: {exc}")
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


def handle_play_proxy_request(handler, project_id: str, target_path: str, parsed, *, method: str = "GET") -> None:
    with _LOCK:
        state = _PIPELINES.get(project_id)
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
        return _proxy_error(handler, 404, "Play project target not found.")
    if not _is_proxy_host_allowed(host):
        return _proxy_error(handler, 403, "Play proxy target host is not allowed.")

    path = target_path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    upstream_url = f"http://{host}:{int(port)}{path}"

    if _is_websocket_proxy_request(handler):
        return _handle_play_proxy_websocket(handler, host, int(port), path, method=method)

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
        if lowered in HOP_BY_HOP_HEADERS or lowered in {"host", "content-length"}:
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
        return _proxy_error(handler, 502, f"Play proxy request failed: {exc}")

    content_type = response_headers.get("Content-Type", "")
    is_html = "text/html" in content_type.lower()
    if is_html:
        response_body = _rewrite_html(response_body, project_id)

    handler.send_response(status)
    for key, value in response_headers.items():
        lowered = key.lower()
        if lowered in HOP_BY_HOP_HEADERS or lowered in {"content-length", "content-encoding"}:
            continue
        if lowered == "location":
            value = _rewrite_proxy_location(value, project_id, target_path or "/")
        elif is_html and lowered in {"content-security-policy", "content-security-policy-report-only"}:
            value = _rewrite_proxy_csp(value)
        handler.send_header(key, value)
    handler.send_header("Content-Length", str(len(response_body)))
    handler.end_headers()
    if method.upper() != "HEAD":
        handler.wfile.write(response_body)

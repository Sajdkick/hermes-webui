"""Fork-owned runtime inspect wrappers for the clean restart branch."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api import ops_projects


RUNTIME_INSPECT_DIR = ".hermes/ops/runtime-inspect"
DEFAULT_TIMEOUT_MS = 10 * 60 * 1000
COMMAND_TIMEOUT_SECONDS = 15 * 60
VALID_RECORD_KINDS = {"snapshot", "screenshot", "action"}
HERMES_RUNTIME_ENV = "HERMES_RUNTIME_BIN"


def _default_hermes_runtime_candidates() -> list[Path]:
    candidates: list[Path] = []
    repo_root = Path(__file__).resolve().parents[1]
    candidates.append(repo_root / "bin" / "hermes-runtime")
    home = os.environ.get("HOME", "").strip()
    if home:
        candidates.append(Path(home) / ".local" / "bin" / "hermes-runtime")
    return candidates


def _resolve_hermes_runtime_command() -> str:
    override = os.environ.get(HERMES_RUNTIME_ENV, "").strip()
    if override:
        override_path = Path(override).expanduser()
        if override_path.is_file() and os.access(override_path, os.X_OK):
            return str(override_path)
        raise OpsRuntimeInspectError(f"{HERMES_RUNTIME_ENV} does not point to an executable hermes-runtime binary.", 500)

    path_match = shutil.which("hermes-runtime")
    if path_match:
        return path_match

    for candidate in _default_hermes_runtime_candidates():
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    raise OpsRuntimeInspectError(
        "hermes-runtime is not installed on the server. Expected it on PATH or at one of: "
        + ", ".join(str(candidate) for candidate in _default_hermes_runtime_candidates()),
        500,
    )


class OpsRuntimeInspectError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _text(value: Any, *, limit: int = 4096) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _positive_int(value: Any, *, label: str, minimum: int = 1) -> int | None:
    if value in {None, ""}:
        return None
    try:
        parsed = int(value)
    except Exception as exc:
        raise OpsRuntimeInspectError(f"{label} must be an integer.") from exc
    if parsed < minimum:
        comparator = "greater than or equal to zero" if minimum == 0 else "greater than zero"
        raise OpsRuntimeInspectError(f"{label} must be {comparator}.")
    return parsed


def _project_path(project: dict) -> Path:
    raw = str(project.get("resolvedPath") or project.get("path") or "").strip()
    if not raw:
        raise OpsRuntimeInspectError("Project path is missing.", 500)
    path = Path(raw).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise OpsRuntimeInspectError("Project directory is missing on the server.", 404)
    return path


def _get_project(project_id: str) -> tuple[dict, Path]:
    try:
        project = ops_projects.get_ops_project(project_id)
    except ops_projects.OpsProjectError as exc:
        raise OpsRuntimeInspectError(str(exc), exc.status) from exc
    return project, _project_path(project)


def _inspect_dir(project_path: Path) -> Path:
    directory = project_path / RUNTIME_INSPECT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _record_path(project_path: Path, kind: str) -> Path:
    normalized = kind.strip().lower()
    if normalized not in VALID_RECORD_KINDS:
        raise OpsRuntimeInspectError("Unknown runtime inspect record kind.", 500)
    return _inspect_dir(project_path) / f"{normalized}.json"


def _read_record(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _write_record(path: Path, record: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def _format_duration_ms(value: int | None) -> str | None:
    return f"{value}ms" if value is not None else None


def _append_flag(args: list[str], flag: str, value: str | int | None) -> None:
    if value in {None, ""}:
        return
    args.extend([flag, str(value)])


def _parse_action_script(body: dict | None) -> dict:
    payload = body if isinstance(body, dict) else {}
    if isinstance(payload.get("actions"), list):
        return {
            "actions": payload.get("actions"),
            "url": _text(payload.get("url"), limit=2048),
            "sessionId": _text(payload.get("sessionId") or payload.get("session"), limit=256),
            "keepSession": _bool(payload.get("keepSession")),
            "fileName": _text(payload.get("fileName"), limit=256),
            "width": payload.get("width"),
            "height": payload.get("height"),
            "delayMs": payload.get("delayMs"),
            "timeoutMs": payload.get("timeoutMs"),
            "gatherReportId": _text(payload.get("gatherReportId") or payload.get("gather"), limit=256),
            "compare": _text(payload.get("compare"), limit=1024),
            "captureScreenshot": _bool(payload.get("captureScreenshot")),
        }
    raw_script = payload.get("script")
    if not isinstance(raw_script, str) or not raw_script.strip():
        raise OpsRuntimeInspectError('Runtime inspect actions require an "actions" array or a "script" JSON string.')
    try:
        parsed = json.loads(raw_script)
    except json.JSONDecodeError as exc:
        raise OpsRuntimeInspectError(f'Runtime inspect action script must be valid JSON ({exc.msg}).') from exc
    if isinstance(parsed, list):
        script = {"actions": parsed}
    elif isinstance(parsed, dict) and isinstance(parsed.get("actions"), list):
        script = dict(parsed)
    else:
        raise OpsRuntimeInspectError('Runtime inspect action scripts must be a JSON array or an object with an "actions" array.')
    for key, value in {
        "url": payload.get("url"),
        "sessionId": payload.get("sessionId") or payload.get("session"),
        "fileName": payload.get("fileName"),
        "gatherReportId": payload.get("gatherReportId") or payload.get("gather"),
        "compare": payload.get("compare"),
    }.items():
        if value not in {None, ""}:
            script[key] = value
    for key, value in {
        "keepSession": payload.get("keepSession"),
        "captureScreenshot": payload.get("captureScreenshot"),
        "width": payload.get("width"),
        "height": payload.get("height"),
        "delayMs": payload.get("delayMs"),
        "timeoutMs": payload.get("timeoutMs"),
    }.items():
        if value not in {None, ""}:
            script[key] = value
    return script


def _failure_status(message: str) -> int:
    lowered = message.lower()
    if any(token in lowered for token in ("must", "requires", "unknown", "invalid", "expected", "missing")):
        return 400
    return 500


def _run_hermes_runtime_json(project_path: Path, args: list[str]) -> dict:
    command = [_resolve_hermes_runtime_command(), *args, "--json"]
    try:
        completed = subprocess.run(
            command,
            cwd=str(project_path),
            check=False,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise OpsRuntimeInspectError("Resolved hermes-runtime binary could not be executed.", 500) from exc
    except subprocess.TimeoutExpired as exc:
        raise OpsRuntimeInspectError("hermes-runtime inspect command timed out.", 504) from exc
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if completed.returncode != 0:
        try:
            payload = json.loads(stdout) if stdout else None
        except json.JSONDecodeError:
            payload = None
        message = ""
        if isinstance(payload, dict):
            message = _text(payload.get("error"), limit=4000)
        if not message:
            message = _text(stderr or stdout, limit=4000)
        if not message:
            message = "hermes-runtime inspect command failed."
        raise OpsRuntimeInspectError(message, _failure_status(message))
    if not stdout:
        raise OpsRuntimeInspectError("hermes-runtime inspect command returned no JSON payload.", 500)
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise OpsRuntimeInspectError("hermes-runtime inspect command returned invalid JSON.", 500) from exc
    if not isinstance(payload, dict):
        raise OpsRuntimeInspectError("hermes-runtime inspect command returned an unexpected payload.", 500)
    return payload


def _snapshot_summary(payload: dict, *, reset_state: bool) -> str:
    if reset_state:
        return _text(payload.get("summary") or payload.get("statusSummary"), limit=4000) or "Runtime state reset completed."
    inspect_url = _text(payload.get("inspectUrl") or payload.get("currentPublicUrl") or payload.get("url"), limit=2048)
    return f"Resolved inspect URL {inspect_url}." if inspect_url else "Resolved the active inspect target."


def _normalize_snapshot_record(project_id: str, payload: dict, *, reset_state: bool, record_path: Path) -> dict:
    inspect_session = payload.get("inspectSession") if isinstance(payload.get("inspectSession"), dict) else {}
    inspect_url = _text(
        payload.get("inspectUrl")
        or payload.get("currentPublicUrl")
        or inspect_session.get("currentPublicUrl")
        or payload.get("url"),
        limit=2048,
    )
    browser_url = _text(payload.get("browserUrl") or payload.get("currentUrl"), limit=2048)
    now = _now_iso()
    return {
        "kind": "reset-state" if reset_state else "inspect-url",
        "projectId": project_id,
        "summary": _snapshot_summary(payload, reset_state=reset_state),
        "inspectUrl": inspect_url,
        "browserUrl": browser_url,
        "sessionId": _text(inspect_session.get("id") or payload.get("sessionId"), limit=256),
        "inspectSession": inspect_session,
        "updatedAt": now,
        "recordPath": str(record_path),
        "result": payload,
    }


def _normalize_screenshot_record(project_id: str, payload: dict, record_path: Path) -> dict:
    inspect_session = payload.get("inspectSession") if isinstance(payload.get("inspectSession"), dict) else {}
    page = payload.get("page") if isinstance(payload.get("page"), dict) else {}
    capture = payload.get("capture") if isinstance(payload.get("capture"), dict) else {}
    summary = _text(page.get("summary"), limit=4000) or "Runtime screenshot captured."
    now = _now_iso()
    return {
        "kind": "screenshot",
        "projectId": project_id,
        "summary": summary,
        "inspectUrl": _text(payload.get("inspectUrl"), limit=2048),
        "absolutePath": _text(payload.get("absolutePath") or capture.get("absolutePath") or payload.get("outputPath"), limit=4096),
        "sessionId": _text(inspect_session.get("id") or payload.get("sessionId"), limit=256),
        "capture": capture,
        "page": page,
        "inspectSession": inspect_session,
        "updatedAt": now,
        "recordPath": str(record_path),
        "result": payload,
    }


def _normalize_action_record(project_id: str, payload: dict, record_path: Path) -> dict:
    inspect_session = payload.get("inspectSession") if isinstance(payload.get("inspectSession"), dict) else {}
    action_summary = payload.get("actions") if isinstance(payload.get("actions"), dict) else {}
    capture = payload.get("capture") if isinstance(payload.get("capture"), dict) else {}
    requested = int(action_summary.get("requestedCount") or 0)
    executed = int(action_summary.get("executedCount") or 0)
    summary = _text(payload.get("summary"), limit=4000) or f"Executed {executed}/{requested} runtime inspect actions."
    now = _now_iso()
    return {
        "kind": "action",
        "projectId": project_id,
        "summary": summary,
        "inspectUrl": _text(payload.get("inspectUrl"), limit=2048),
        "sessionId": _text(inspect_session.get("id") or payload.get("sessionId"), limit=256),
        "actions": action_summary,
        "capture": capture,
        "page": payload.get("page") if isinstance(payload.get("page"), dict) else {},
        "artifacts": payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {},
        "inspectSession": inspect_session,
        "updatedAt": now,
        "recordPath": str(record_path),
        "result": payload,
    }


def get_latest_snapshot(project_id: str) -> dict:
    _project, project_path = _get_project(project_id)
    return {"snapshot": _read_record(_record_path(project_path, "snapshot"))}


def get_latest_screenshot(project_id: str) -> dict:
    _project, project_path = _get_project(project_id)
    return {"screenshot": _read_record(_record_path(project_path, "screenshot"))}


def get_latest_action(project_id: str) -> dict:
    _project, project_path = _get_project(project_id)
    return {"action": _read_record(_record_path(project_path, "action"))}


def capture_snapshot(project_id: str, body: dict | None) -> dict:
    _project, project_path = _get_project(project_id)
    payload = body if isinstance(body, dict) else {}
    reset_state = _bool(payload.get("resetState"))
    timeout_ms = _positive_int(payload.get("timeoutMs"), label="timeoutMs")
    args = ["inspect", "reset-state" if reset_state else "url"]
    if reset_state:
        _append_flag(args, "--timeout", _format_duration_ms(timeout_ms or DEFAULT_TIMEOUT_MS))
    result = _run_hermes_runtime_json(project_path, args)
    path = _record_path(project_path, "snapshot")
    record = _normalize_snapshot_record(project_id, result, reset_state=reset_state, record_path=path)
    _write_record(path, record)
    return {"snapshot": record}


def capture_screenshot(project_id: str, body: dict | None) -> dict:
    _project, project_path = _get_project(project_id)
    payload = body if isinstance(body, dict) else {}
    args = ["inspect", "screenshot"]
    _append_flag(args, "--url", _text(payload.get("url"), limit=2048))
    _append_flag(args, "--session", _text(payload.get("sessionId") or payload.get("session"), limit=256))
    if _bool(payload.get("keepSession")):
        args.append("--keep-session")
    _append_flag(args, "--selector", _text(payload.get("selector"), limit=1024))
    nth = _positive_int(payload.get("nth"), label="nth", minimum=0)
    _append_flag(args, "--nth", nth)
    width = _positive_int(payload.get("width"), label="width")
    _append_flag(args, "--width", width)
    height = _positive_int(payload.get("height"), label="height")
    _append_flag(args, "--height", height)
    delay_ms = _positive_int(payload.get("delayMs"), label="delayMs")
    _append_flag(args, "--delay", _format_duration_ms(delay_ms))
    timeout_ms = _positive_int(payload.get("timeoutMs"), label="timeoutMs")
    _append_flag(args, "--timeout", _format_duration_ms(timeout_ms))
    _append_flag(args, "--file-name", _text(payload.get("fileName"), limit=256))
    result = _run_hermes_runtime_json(project_path, args)
    path = _record_path(project_path, "screenshot")
    record = _normalize_screenshot_record(project_id, result, path)
    _write_record(path, record)
    return {"screenshot": record}


def run_action(project_id: str, body: dict | None) -> dict:
    _project, project_path = _get_project(project_id)
    script = _parse_action_script(body if isinstance(body, dict) else {})
    args = ["inspect", "action"]
    _append_flag(args, "--url", _text(script.get("url"), limit=2048))
    _append_flag(args, "--session", _text(script.get("sessionId") or script.get("session"), limit=256))
    if _bool(script.get("keepSession")):
        args.append("--keep-session")
    if _bool(script.get("captureScreenshot")):
        args.append("--capture-screenshot")
    width = _positive_int(script.get("width"), label="width")
    _append_flag(args, "--width", width)
    height = _positive_int(script.get("height"), label="height")
    _append_flag(args, "--height", height)
    delay_ms = _positive_int(script.get("delayMs"), label="delayMs")
    _append_flag(args, "--delay", _format_duration_ms(delay_ms))
    timeout_ms = _positive_int(script.get("timeoutMs"), label="timeoutMs")
    _append_flag(args, "--timeout", _format_duration_ms(timeout_ms))
    _append_flag(args, "--file-name", _text(script.get("fileName"), limit=256))
    _append_flag(args, "--gather", _text(script.get("gatherReportId") or script.get("gather"), limit=256))
    _append_flag(args, "--compare", _text(script.get("compare"), limit=1024))
    script_dir = _inspect_dir(project_path)
    script_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="inspect-action-",
            suffix=".json",
            dir=script_dir,
            delete=False,
        ) as handle:
            json.dump({"actions": script.get("actions") or []}, handle, ensure_ascii=False, indent=2)
            script_path = Path(handle.name)
        _append_flag(args, "--script-file", str(script_path))
        result = _run_hermes_runtime_json(project_path, args)
    finally:
        if script_path and script_path.exists():
            script_path.unlink(missing_ok=True)
    path = _record_path(project_path, "action")
    record = _normalize_action_record(project_id, result, path)
    _write_record(path, record)
    return {"action": record}

"""Hermes WebUI gather-report helpers.

A gather report is a small, session-scoped evidence log for temporary runtime
instrumentation. Agents create a report, add a narrow browser/server hook that
POSTs structured events to the returned ingest endpoint, ask the user to
reproduce the behavior, then inspect the saved report from disk or the CLI.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from api.config import STATE_DIR

GATHER_TOKEN_HEADER = "X-Hermes-Gather-Token"
MAX_GATHER_EVENTS = 2000
MAX_GATHER_TEXT = 20_000
_REPORT_ID_RE = re.compile(r"^[a-f0-9-]{36}$", re.IGNORECASE)
_REPORT_LOCK = threading.Lock()


class GatherError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _reports_dir() -> Path:
    path = STATE_DIR / "gather"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _validate_report_id(report_id: str) -> str:
    key = str(report_id or "").strip()
    if not key or not _REPORT_ID_RE.match(key):
        raise GatherError("Gather report not found.", 404)
    return key


def _report_path(report_id: str) -> Path:
    return _reports_dir() / f"{_validate_report_id(report_id)}.json"


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:MAX_GATHER_TEXT]
    if isinstance(value, list):
        return [_json_safe(item, depth=depth + 1) for item in value[:200]]
    if isinstance(value, tuple):
        return [_json_safe(item, depth=depth + 1) for item in value[:200]]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= 200:
                result["…"] = "truncated"
                break
            result[str(key)[:200]] = _json_safe(item, depth=depth + 1)
        return result
    return str(value)[:MAX_GATHER_TEXT]


def _read_report(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GatherError("Gather report not found.", 404) from exc
    except Exception as exc:
        raise GatherError("Could not read gather report.", 500) from exc
    if not isinstance(payload, dict):
        raise GatherError("Gather report is invalid.", 500)
    return payload


def _write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".json.{secrets.token_hex(6)}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _public_report(payload: dict, *, include_events: bool = True, include_token: bool = False) -> dict:
    report = dict(payload.get("report") or {})
    events = list(payload.get("events") or [])
    report["eventCount"] = len(events)
    report["latestEvent"] = events[-1] if events else None
    result: dict[str, Any] = {"report": report}
    if include_events:
        result["events"] = events
    if include_token:
        token = str(payload.get("token") or "")
        if token:
            result["ingest"] = {
                "path": f"/api/gather/{report.get('id')}/events",
                "url": f"/api/gather/{report.get('id')}/events",
                "tokenHeader": GATHER_TOKEN_HEADER,
                "token": token,
            }
    return result


def create_gather_report(
    title: str = "",
    *,
    session_id: str = "",
    workspace: str = "",
) -> dict:
    report_id = str(uuid.uuid4())
    now = time.time()
    path = _report_path(report_id)
    title = str(title or "").strip() or "Gather report"
    payload = {
        "version": 1,
        "token": secrets.token_urlsafe(32),
        "report": {
            "id": report_id,
            "title": title[:160],
            "sessionId": str(session_id or ""),
            "workspace": str(workspace or ""),
            "path": str(path),
            "created_at": now,
            "updated_at": now,
            "eventCount": 0,
            "latestEvent": None,
        },
        "events": [],
    }
    with _REPORT_LOCK:
        _write_report(path, payload)
    return _public_report(payload, include_events=False, include_token=True)


def show_gather_report(report_id: str) -> dict:
    with _REPORT_LOCK:
        payload = _read_report(_report_path(report_id))
    return _public_report(payload, include_events=True, include_token=False)


def list_gather_reports(limit: int = 50) -> dict:
    reports = []
    with _REPORT_LOCK:
        for path in sorted(_reports_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                payload = _read_report(path)
                reports.append(_public_report(payload, include_events=False, include_token=False)["report"])
            except GatherError:
                continue
            if len(reports) >= limit:
                break
    return {"reports": reports}


def append_gather_event(report_id: str, token: str, body: dict) -> dict:
    if not isinstance(body, dict):
        raise GatherError("Gather event body must be a JSON object.")
    path = _report_path(report_id)
    with _REPORT_LOCK:
        payload = _read_report(path)
        expected = str(payload.get("token") or "")
        if not expected or not secrets.compare_digest(str(token or ""), expected):
            raise GatherError("Gather token is invalid.", 403)
        events = list(payload.get("events") or [])
        now = time.time()
        event = {
            "id": str(uuid.uuid4()),
            "created_at": now,
            "type": str(body.get("type") or "log")[:80],
            "level": str(body.get("level") or "info")[:40],
            "label": str(body.get("label") or "")[:200],
            "message": str(body.get("message") or "")[:MAX_GATHER_TEXT],
            "route": str(body.get("route") or "")[:1000],
            "url": str(body.get("url") or "")[:2000],
            "data": _json_safe(body.get("data") if "data" in body else {}),
            "meta": _json_safe(body.get("meta") if "meta" in body else None),
        }
        events.append(event)
        if len(events) > MAX_GATHER_EVENTS:
            events = events[-MAX_GATHER_EVENTS:]
        report = dict(payload.get("report") or {})
        report["updated_at"] = now
        report["eventCount"] = len(events)
        report["latestEvent"] = event
        payload["report"] = report
        payload["events"] = events
        _write_report(path, payload)
    return {"ok": True, "report": report, "event": event}


def report_id_from_events_path(path: str) -> str | None:
    match = re.match(r"^/api/gather/([^/]+)/events/?$", str(path or ""))
    if not match:
        return None
    return match.group(1)

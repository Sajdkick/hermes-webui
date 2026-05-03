"""Fork-owned runtime gather and review records for the clean restart branch."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.config import STATE_DIR
from api import ops_projects


OPS_GATHER_REPORTS_FILE = STATE_DIR / "ops" / "gather-reports.json"
OPS_REVIEW_REQUESTS_FILE = STATE_DIR / "ops" / "review-requests.json"
GATHER_REPORT_STATUS_VALUES = {"created", "running", "succeeded", "failed"}
GATHER_REPORT_EVENT_LEVEL_VALUES = {"debug", "info", "warning", "error"}
REVIEW_REQUEST_STATUS_VALUES = {"requested", "running", "succeeded", "failed", "canceled"}
REVIEW_REQUEST_KIND_VALUES = {"visual", "image", "runtime", "accessibility", "other"}
GATHER_EVENTS_MAX = 2000
_LOCK = threading.RLock()


class OpsGuideError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _text(value: Any, *, limit: int = 512) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _json_safe(val) for key, val in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(item) for item in value]
        return str(value)


def _safe_name(value: Any) -> str:
    cleaned = "".join(char if str(char).isalnum() or str(char) in "._-" else "-" for char in str(value or "").strip())
    collapsed = "-".join(part for part in cleaned.split("-") if part).strip(".-")
    return collapsed[:80] or "report"


def _status(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    return normalized if normalized in GATHER_REPORT_STATUS_VALUES else "created"


def _review_status(value: Any, *, default: str = "requested") -> str:
    normalized = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    if not normalized:
        return default
    return normalized if normalized in REVIEW_REQUEST_STATUS_VALUES else default


def _review_kind(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    return normalized if normalized in REVIEW_REQUEST_KIND_VALUES else "visual"


def _event_level(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "warn":
        normalized = "warning"
    if normalized == "fatal":
        normalized = "error"
    return normalized if normalized in GATHER_REPORT_EVENT_LEVEL_VALUES else "info"


def _project_path(project: dict) -> Path:
    raw = str(project.get("resolvedPath") or project.get("path") or "").strip()
    if not raw:
        raise OpsGuideError("Project path is missing.", 500)
    path = Path(raw).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise OpsGuideError("Project directory is missing on the server.", 404)
    return path


def _get_project(project_id: str) -> tuple[dict, Path]:
    try:
        project = ops_projects.get_ops_project(project_id)
    except ops_projects.OpsProjectError as exc:
        raise OpsGuideError(str(exc), exc.status) from exc
    return project, _project_path(project)


def _read_store(path: Path, normalize) -> dict[str, list[dict]]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    store: dict[str, list[dict]] = {}
    for project_id, records in parsed.items():
        if not isinstance(project_id, str) or not isinstance(records, list):
            continue
        store[project_id] = [
            normalize(record, project_id=project_id)
            for record in records
            if isinstance(record, dict)
        ]
    return store


def _write_store(path: Path, store: dict[str, list[dict]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _event(body: dict | None = None) -> dict:
    body = body if isinstance(body, dict) else {}
    now = _now_iso()
    return {
        "id": _text(body.get("id"), limit=128) or f"event_{uuid.uuid4().hex}",
        "type": _text(body.get("type") or body.get("kind"), limit=128) or "note",
        "level": _event_level(body.get("level")),
        "message": _text(body.get("message") or body.get("summary"), limit=4000),
        "source": _text(body.get("source"), limit=128) or "hermes-runtime",
        "metadata": _json_safe(body.get("metadata") if isinstance(body.get("metadata"), dict) else {}),
        "createdAt": _text(body.get("createdAt"), limit=64) or now,
    }


def _normalize_report(entry: dict, *, project_id: str) -> dict:
    now = _now_iso()
    report = dict(entry)
    report["id"] = _text(report.get("id"), limit=128) or f"gather_{uuid.uuid4().hex}"
    report["projectId"] = _text(report.get("projectId") or report.get("project_id"), limit=128) or project_id
    report["runId"] = _text(report.get("runId") or report.get("run_id"), limit=128)
    report["taskId"] = _text(report.get("taskId") or report.get("task_id"), limit=128)
    report["sessionId"] = _text(report.get("sessionId") or report.get("session_id"), limit=128)
    report["title"] = _text(report.get("title") or report.get("name"), limit=256) or "Runtime gather report"
    report["summary"] = _text(report.get("summary"), limit=4000)
    report["status"] = _status(report.get("status"))
    report["url"] = _text(report.get("url"), limit=2048)
    report["metadata"] = _json_safe(report.get("metadata") if isinstance(report.get("metadata"), dict) else {})
    events = report.get("events")
    if isinstance(events, list):
        report["events"] = [_event(event) for event in events if isinstance(event, dict)][-GATHER_EVENTS_MAX:]
    else:
        report["events"] = []
    report["eventsCount"] = len(report["events"])
    report["latestEvent"] = report["events"][-1] if report["events"] else None
    report["createdAt"] = _text(report.get("createdAt") or report.get("created_at"), limit=64) or now
    report["updatedAt"] = _text(report.get("updatedAt") or report.get("updated_at"), limit=64) or report["createdAt"]
    report["artifactDir"] = _text(report.get("artifactDir") or report.get("artifact_dir"), limit=4096)
    report["reportPath"] = _text(report.get("reportPath") or report.get("report_path"), limit=4096)
    return report


def _normalize_review(entry: dict, *, project_id: str) -> dict:
    now = _now_iso()
    review = dict(entry)
    review["id"] = _text(review.get("id"), limit=128) or f"review_{uuid.uuid4().hex}"
    review["projectId"] = _text(review.get("projectId") or review.get("project_id"), limit=128) or project_id
    review["runId"] = _text(review.get("runId") or review.get("run_id"), limit=128)
    review["taskId"] = _text(review.get("taskId") or review.get("task_id"), limit=128)
    review["sessionId"] = _text(review.get("sessionId") or review.get("session_id"), limit=128)
    review["gatherReportId"] = _text(review.get("gatherReportId") or review.get("gather_report_id"), limit=128)
    review["screenshotPath"] = _text(review.get("screenshotPath") or review.get("screenshot_path"), limit=4096)
    review["imagePath"] = _text(review.get("imagePath") or review.get("image_path"), limit=4096)
    review["actionId"] = _text(review.get("actionId") or review.get("action_id"), limit=128)
    review["title"] = _text(review.get("title") or review.get("name"), limit=256) or "Runtime review"
    review["prompt"] = _text(review.get("prompt") or review.get("instructions"), limit=8000)
    review["summary"] = _text(review.get("summary"), limit=4000)
    review["kind"] = _review_kind(review.get("kind") or review.get("type"))
    review["status"] = _review_status(review.get("status"))
    review["url"] = _text(review.get("url"), limit=2048)
    review["result"] = _json_safe(review.get("result") if isinstance(review.get("result"), dict) else {})
    review["metadata"] = _json_safe(review.get("metadata") if isinstance(review.get("metadata"), dict) else {})
    events = review.get("events")
    if isinstance(events, list):
        review["events"] = [_event(event) for event in events if isinstance(event, dict)][-GATHER_EVENTS_MAX:]
    else:
        review["events"] = []
    review["eventsCount"] = len(review["events"])
    review["latestEvent"] = review["events"][-1] if review["events"] else None
    review["createdAt"] = _text(review.get("createdAt") or review.get("created_at"), limit=64) or now
    review["updatedAt"] = _text(review.get("updatedAt") or review.get("updated_at"), limit=64) or review["createdAt"]
    review["artifactDir"] = _text(review.get("artifactDir") or review.get("artifact_dir"), limit=4096)
    review["reviewPath"] = _text(review.get("reviewPath") or review.get("review_path"), limit=4096)
    return review


def _persist_report_file(project_path: Path, report: dict) -> dict:
    directory = project_path / ".hermes" / "ops" / "gather" / _safe_name(report["id"])
    directory.mkdir(parents=True, exist_ok=True)
    report["artifactDir"] = str(directory)
    report["reportPath"] = str(directory / "report.json")
    Path(report["reportPath"]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _persist_review_file(project_path: Path, review: dict) -> dict:
    directory = project_path / ".hermes" / "ops" / "reviews" / _safe_name(review["id"])
    directory.mkdir(parents=True, exist_ok=True)
    review["artifactDir"] = str(directory)
    review["reviewPath"] = str(directory / "review.json")
    Path(review["reviewPath"]).write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    return review


def _find_record(records: list[dict], record_id: str, *, kind: str) -> tuple[int, dict]:
    for index, record in enumerate(records):
        if record.get("id") == record_id:
            return index, record
    label = "Gather report" if kind == "report" else "Review request"
    raise OpsGuideError(f"{label} not found.", 404)


def list_gather_reports(project_id: str, filters: dict | None = None) -> dict:
    project, _project_path_value = _get_project(project_id)
    filters = filters or {}
    run_id = _text(filters.get("runId") or filters.get("run_id"), limit=128)
    task_id = _text(filters.get("taskId") or filters.get("task_id"), limit=128)
    session_id = _text(filters.get("sessionId") or filters.get("session_id"), limit=128)
    status = _status(filters.get("status")) if filters.get("status") else ""
    raw_limit = str(filters.get("limit") or "").strip()
    limit = int(raw_limit) if raw_limit.isdigit() else 20
    limit = max(1, min(limit, 100))
    with _LOCK:
        reports = list(_read_store(OPS_GATHER_REPORTS_FILE, _normalize_report).get(str(project.get("id") or project_id), []))
    if run_id:
        reports = [report for report in reports if report.get("runId") == run_id]
    if task_id:
        reports = [report for report in reports if report.get("taskId") == task_id]
    if session_id:
        reports = [report for report in reports if report.get("sessionId") == session_id]
    if status:
        reports = [report for report in reports if report.get("status") == status]
    reports.sort(key=lambda item: item.get("updatedAt") or item.get("createdAt") or "", reverse=True)
    return {"reports": reports[:limit], "count": len(reports)}


def get_gather_report(project_id: str, report_id: str) -> dict:
    project, _project_path_value = _get_project(project_id)
    with _LOCK:
        reports = _read_store(OPS_GATHER_REPORTS_FILE, _normalize_report).get(str(project.get("id") or project_id), [])
        _index, report = _find_record(reports, report_id, kind="report")
    return {"report": report}


def get_latest_gather_report(project_id: str) -> dict:
    listing = list_gather_reports(project_id, {"limit": 1})
    return {"report": listing["reports"][0] if listing["reports"] else None}


def create_gather_report(project_id: str, body: dict | None) -> dict:
    project, project_path = _get_project(project_id)
    body = body if isinstance(body, dict) else {}
    now = _now_iso()
    report = _normalize_report(
        {
            "id": body.get("id"),
            "projectId": str(project.get("id") or project_id),
            "runId": body.get("runId") or body.get("run_id"),
            "taskId": body.get("taskId") or body.get("task_id"),
            "sessionId": body.get("sessionId") or body.get("session_id"),
            "title": body.get("title") or body.get("name"),
            "summary": body.get("summary"),
            "status": body.get("status"),
            "url": body.get("url"),
            "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            "events": body.get("events") if isinstance(body.get("events"), list) else [],
            "createdAt": now,
            "updatedAt": now,
        },
        project_id=str(project.get("id") or project_id),
    )
    if not report["events"]:
        report["events"].append(
            _event({"type": "report.created", "message": report["summary"] or report["title"], "source": "ops-gather"})
        )
        report["eventsCount"] = len(report["events"])
        report["latestEvent"] = report["events"][-1]
    report = _persist_report_file(project_path, report)
    with _LOCK:
        store = _read_store(OPS_GATHER_REPORTS_FILE, _normalize_report)
        reports = store.setdefault(report["projectId"], [])
        match_index = next((index for index, item in enumerate(reports) if item.get("id") == report["id"]), -1)
        created = match_index < 0
        if created:
            reports.append(report)
        else:
            reports[match_index] = report
        _write_store(OPS_GATHER_REPORTS_FILE, store)
    return {"report": report, "created": created}


def append_gather_report_event(project_id: str, report_id: str, body: dict | None) -> dict:
    project, project_path = _get_project(project_id)
    with _LOCK:
        store = _read_store(OPS_GATHER_REPORTS_FILE, _normalize_report)
        reports = store.get(str(project.get("id") or project_id), [])
        index, report = _find_record(reports, report_id, kind="report")
        event = _event(body)
        report["events"].append(event)
        report["events"] = report["events"][-GATHER_EVENTS_MAX:]
        if isinstance(body, dict):
            if body.get("status") is not None:
                report["status"] = _status(body.get("status"))
            if body.get("summary") is not None:
                report["summary"] = _text(body.get("summary"), limit=4000)
        report["eventsCount"] = len(report["events"])
        report["latestEvent"] = report["events"][-1] if report["events"] else None
        report["updatedAt"] = _now_iso()
        report = _persist_report_file(project_path, report)
        reports[index] = report
        _write_store(OPS_GATHER_REPORTS_FILE, store)
    return {"report": report, "event": event}


def list_review_requests(project_id: str, filters: dict | None = None) -> dict:
    project, _project_path_value = _get_project(project_id)
    filters = filters or {}
    run_id = _text(filters.get("runId") or filters.get("run_id"), limit=128)
    task_id = _text(filters.get("taskId") or filters.get("task_id"), limit=128)
    session_id = _text(filters.get("sessionId") or filters.get("session_id"), limit=128)
    status = _review_status(filters.get("status"), default="") if filters.get("status") else ""
    kind = _review_kind(filters.get("kind") or filters.get("type")) if (filters.get("kind") or filters.get("type")) else ""
    raw_limit = str(filters.get("limit") or "").strip()
    limit = int(raw_limit) if raw_limit.isdigit() else 20
    limit = max(1, min(limit, 100))
    with _LOCK:
        reviews = list(_read_store(OPS_REVIEW_REQUESTS_FILE, _normalize_review).get(str(project.get("id") or project_id), []))
    if run_id:
        reviews = [review for review in reviews if review.get("runId") == run_id]
    if task_id:
        reviews = [review for review in reviews if review.get("taskId") == task_id]
    if session_id:
        reviews = [review for review in reviews if review.get("sessionId") == session_id]
    if status:
        reviews = [review for review in reviews if review.get("status") == status]
    if kind:
        reviews = [review for review in reviews if review.get("kind") == kind]
    reviews.sort(key=lambda item: item.get("updatedAt") or item.get("createdAt") or "", reverse=True)
    return {"reviews": reviews[:limit], "count": len(reviews)}


def get_review_request(project_id: str, review_id: str) -> dict:
    project, _project_path_value = _get_project(project_id)
    with _LOCK:
        reviews = _read_store(OPS_REVIEW_REQUESTS_FILE, _normalize_review).get(str(project.get("id") or project_id), [])
        _index, review = _find_record(reviews, review_id, kind="review")
    return {"review": review}


def get_latest_review_request(project_id: str) -> dict:
    listing = list_review_requests(project_id, {"limit": 1})
    return {"review": listing["reviews"][0] if listing["reviews"] else None}


def create_review_request(project_id: str, body: dict | None) -> dict:
    project, project_path = _get_project(project_id)
    body = body if isinstance(body, dict) else {}
    now = _now_iso()
    review = _normalize_review(
        {
            "id": body.get("id"),
            "projectId": str(project.get("id") or project_id),
            "runId": body.get("runId") or body.get("run_id"),
            "taskId": body.get("taskId") or body.get("task_id"),
            "sessionId": body.get("sessionId") or body.get("session_id"),
            "gatherReportId": body.get("gatherReportId") or body.get("gather_report_id"),
            "screenshotPath": body.get("screenshotPath") or body.get("screenshot_path"),
            "imagePath": body.get("imagePath") or body.get("image_path"),
            "actionId": body.get("actionId") or body.get("action_id"),
            "title": body.get("title") or body.get("name"),
            "prompt": body.get("prompt") or body.get("instructions"),
            "summary": body.get("summary"),
            "kind": body.get("kind") or body.get("type"),
            "status": body.get("status") or "requested",
            "url": body.get("url"),
            "result": body.get("result") if isinstance(body.get("result"), dict) else {},
            "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            "events": body.get("events") if isinstance(body.get("events"), list) else [],
            "createdAt": now,
            "updatedAt": now,
        },
        project_id=str(project.get("id") or project_id),
    )
    if not review["events"]:
        review["events"].append(
            _event({"type": "review.requested", "message": review["prompt"] or review["title"], "source": "ops-review"})
        )
        review["eventsCount"] = len(review["events"])
        review["latestEvent"] = review["events"][-1]
    review = _persist_review_file(project_path, review)
    with _LOCK:
        store = _read_store(OPS_REVIEW_REQUESTS_FILE, _normalize_review)
        reviews = store.setdefault(review["projectId"], [])
        match_index = next((index for index, item in enumerate(reviews) if item.get("id") == review["id"]), -1)
        created = match_index < 0
        if created:
            reviews.append(review)
        else:
            reviews[match_index] = review
        _write_store(OPS_REVIEW_REQUESTS_FILE, store)
    return {"review": review, "created": created}


def complete_review_request(project_id: str, review_id: str, body: dict | None) -> dict:
    project, project_path = _get_project(project_id)
    body = body if isinstance(body, dict) else {}
    with _LOCK:
        store = _read_store(OPS_REVIEW_REQUESTS_FILE, _normalize_review)
        reviews = store.get(str(project.get("id") or project_id), [])
        index, review = _find_record(reviews, review_id, kind="review")
        status = _review_status(body.get("status"), default="succeeded")
        if status not in {"succeeded", "failed", "canceled"}:
            status = "succeeded"
        review["status"] = status
        if body.get("summary") is not None:
            review["summary"] = _text(body.get("summary"), limit=4000)
        result = body.get("result") if isinstance(body.get("result"), dict) else {}
        if body.get("assessment") is not None:
            result = {**result, "assessment": _json_safe(body.get("assessment"))}
        if body.get("issues") is not None:
            result = {**result, "issues": _json_safe(body.get("issues"))}
        if result:
            review["result"] = _json_safe({**(review.get("result") or {}), **result})
        if body.get("metadata") is not None and isinstance(body.get("metadata"), dict):
            review["metadata"] = _json_safe({**(review.get("metadata") or {}), **body["metadata"]})
        event_type = "review.failed" if status == "failed" else "review.canceled" if status == "canceled" else "review.completed"
        review["events"].append(
            _event(
                {
                    "type": event_type,
                    "level": "error" if status == "failed" else "info",
                    "message": review["summary"] or review["title"],
                    "source": "ops-review",
                }
            )
        )
        review["events"] = review["events"][-GATHER_EVENTS_MAX:]
        review["eventsCount"] = len(review["events"])
        review["latestEvent"] = review["events"][-1] if review["events"] else None
        review["updatedAt"] = _now_iso()
        review = _persist_review_file(project_path, review)
        reviews[index] = review
        _write_store(OPS_REVIEW_REQUESTS_FILE, store)
    return {"review": review}

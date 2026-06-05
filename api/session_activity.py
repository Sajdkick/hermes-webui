"""Cloud Terminal-style session activity helpers for the standalone ops UI."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from api import ops_projects, ops_sessions
from api.models import all_sessions


SESSION_ACTIVITY_GROUP_LABEL_MAX_LENGTH = int(
    os.getenv("SESSION_ACTIVITY_GROUP_LABEL_MAX_LENGTH") or "80"
)
SESSION_ACTIVITY_GROUP_LIMIT = int(
    os.getenv("SESSION_ACTIVITY_GROUP_LIMIT_PER_USER") or "40"
)
SESSION_ACTIVITY_GROUP_ASSIGNMENT_LIMIT = int(
    os.getenv("SESSION_ACTIVITY_GROUP_ASSIGNMENT_LIMIT_PER_USER") or "400"
)
SESSION_ACTIVITY_REFRESH_INTERVAL_MS = 5000
SESSION_ACTIVITY_PLAY_HANDOFF_VISIBILITY_SECONDS = 24 * 60 * 60
_ACTIVE_RUN_STATUSES = {
    "queued",
    "starting",
    "running",
    "waiting-input",
    "waiting-approval",
}
_VISIBLE_RUN_STATUSES = _ACTIVE_RUN_STATUSES | {"failed", "stopped", "succeeded"}
_ACTIVE_PLAY_HANDOFF_STATUSES = {
    "",
    "unknown",
    "queued",
    "building",
    "starting",
    "running",
}


class SessionActivityError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _epoch_seconds(value) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _profile_state_dir() -> Path:
    try:
        from api.profiles import get_active_hermes_home

        state_dir = get_active_hermes_home() / "webui_state"
    except Exception:
        state_dir = Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser() / "webui_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def _state_path() -> Path:
    return _profile_state_dir() / "session_activity_groups.json"


def _normalize_group_label(value) -> str:
    if not isinstance(value, str):
        return ""
    normalized = " ".join(value.split()).strip()
    if not normalized:
        return ""
    return normalized[:SESSION_ACTIVITY_GROUP_LABEL_MAX_LENGTH].strip()


def _normalize_group(entry: dict | None, fallback_position: int = 0) -> dict | None:
    if not isinstance(entry, dict):
        return None
    group_id = str(entry.get("id") or "").strip()
    label = _normalize_group_label(entry.get("label"))
    if not group_id or not label:
        return None
    parsed_position = int(entry.get("position") or fallback_position or 0)
    created_at = str(entry.get("createdAt") or "").strip() or _now_iso()
    updated_at = str(entry.get("updatedAt") or "").strip() or created_at
    return {
        "id": group_id,
        "label": label,
        "position": max(0, parsed_position),
        "createdAt": created_at,
        "updatedAt": updated_at,
    }


def _normalize_assignment(entry: dict | None, valid_group_ids: set[str]) -> dict | None:
    if not isinstance(entry, dict):
        return None
    session_id = str(entry.get("sessionId") or "").strip()
    group_id = str(entry.get("groupId") or "").strip()
    if not session_id or not group_id or group_id not in valid_group_ids:
        return None
    return {
        "sessionId": session_id,
        "groupId": group_id,
        "updatedAt": str(entry.get("updatedAt") or "").strip() or _now_iso(),
    }


def _read_state() -> dict:
    path = _state_path()
    if not path.exists():
        return {"groups": [], "assignments": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"groups": [], "assignments": []}
    groups: list[dict] = []
    seen_group_ids: set[str] = set()
    for index, entry in enumerate(payload.get("groups") or []):
        normalized = _normalize_group(entry, index)
        if not normalized or normalized["id"] in seen_group_ids:
            continue
        seen_group_ids.add(normalized["id"])
        groups.append(normalized)
    groups.sort(key=lambda item: (int(item.get("position") or 0), str(item.get("label") or "")))
    groups = [
        {**group, "position": index}
        for index, group in enumerate(groups[:SESSION_ACTIVITY_GROUP_LIMIT])
    ]
    valid_group_ids = {group["id"] for group in groups}
    assignment_by_session_id: dict[str, dict] = {}
    for entry in payload.get("assignments") or []:
        normalized = _normalize_assignment(entry, valid_group_ids)
        if not normalized:
            continue
        assignment_by_session_id[normalized["sessionId"]] = normalized
    assignments = list(assignment_by_session_id.values())[:SESSION_ACTIVITY_GROUP_ASSIGNMENT_LIMIT]
    return {"groups": groups, "assignments": assignments}


def _write_state(state: dict, reason: str) -> None:
    path = _state_path()
    groups = list(state.get("groups") or [])
    assignments = list(state.get("assignments") or [])
    if not groups and not assignments:
        if path.exists():
            path.unlink()
        return
    payload = {
        "version": 1,
        "savedAt": _now_iso(),
        "reason": reason,
        "groups": groups,
        "assignments": assignments,
    }
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _session_aliases(session: dict | None) -> set[str]:
    aliases: set[str] = set()
    if not isinstance(session, dict):
        return aliases
    for field in ("session_id", "_lineage_root_id", "_lineage_tip_id", "parent_session_id"):
        value = str(session.get(field) or "").strip()
        if value:
            aliases.add(value)
    member_ids = session.get("_lineage_member_ids")
    if isinstance(member_ids, (list, tuple, set)):
        aliases.update(str(value).strip() for value in member_ids if str(value or "").strip())
    return aliases


def _canonical_assignment_session_id(session_id: str) -> str:
    requested = str(session_id or "").strip()
    if not requested:
        return ""
    for session in all_sessions():
        if requested not in _session_aliases(session):
            continue
        return str(session.get("_lineage_root_id") or session.get("session_id") or requested).strip() or requested
    return requested


def _session_has_live_stream(session: dict) -> bool:
    # active_stream_id is durable sidecar state and can survive a crashed or
    # restarted WebUI process. all_sessions() overlays is_streaming from the
    # in-process STREAMS registry, so only that runtime flag proves a stream is
    # currently alive. This keeps stale first-turn sidecars out of the ops
    # dashboard activity list while preserving durable ops run state.
    return bool(session.get("is_streaming"))


def _recent_epoch(value, *, max_age_seconds: int = SESSION_ACTIVITY_PLAY_HANDOFF_VISIBILITY_SECONDS) -> bool:
    stamp = _epoch_seconds(value)
    if stamp <= 0:
        return False
    return stamp >= datetime.now(timezone.utc).timestamp() - max_age_seconds


def _play_handoff_activity_status(run: dict) -> str:
    if not isinstance(run, dict):
        return ""
    raw_metadata = run.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    triggered_at = metadata.get("playPipelineTriggeredAt")
    attempted_at = metadata.get("playPipelineAttemptedAt")
    status_at = triggered_at or attempted_at or run.get("updatedAt") or run.get("updated_at")
    if not _recent_epoch(status_at):
        return ""
    if str(metadata.get("playPipelineError") or "").strip():
        return "failed"
    if not triggered_at:
        return ""
    status = str(metadata.get("playPipelineStatus") or "").strip().lower().replace("_", "-").replace(" ", "-")
    return status if status in _ACTIVE_PLAY_HANDOFF_STATUSES else ""


def _activity_status(session: dict) -> dict | None:
    raw_run = session.get("ops_run")
    run = raw_run if isinstance(raw_run, dict) else {}
    run_status = str(run.get("status") or "").strip().lower()
    play_handoff_status = _play_handoff_activity_status(run)
    has_live_stream = _session_has_live_stream(session)
    if session.get("waitingForApproval") or run_status == "waiting-approval":
        return {
            "key": "approval",
            "toneClass": "approval",
            "labelText": "Codex needs approval",
            "title": "Codex is waiting for approval in this session.",
        }
    if session.get("waitingForInput") or run_status == "waiting-input":
        return {
            "key": "waiting",
            "toneClass": "waiting",
            "labelText": "Codex needs input",
            "title": "Codex is waiting for input in this session.",
        }
    if has_live_stream:
        return {
            "key": "active",
            "toneClass": "active",
            "labelText": "Codex is working",
            "title": "Codex is actively processing this session.",
        }
    if session.get("pending_user_message") or run_status in {"queued", "starting"}:
        return {
            "key": "connecting",
            "toneClass": "connecting",
            "labelText": "Connecting to Codex",
            "title": "Connecting to Codex for live session state.",
        }
    if run_status == "running":
        return {
            "key": "active",
            "toneClass": "active",
            "labelText": "Codex is working",
            "title": "Codex is actively processing this session.",
        }
    if run_status == "failed":
        return {
            "key": "degraded",
            "toneClass": "degraded",
            "labelText": "Codex degraded",
            "title": "Codex app-server is degraded for this session.",
        }
    if play_handoff_status:
        if play_handoff_status == "failed":
            return {
                "key": "degraded",
                "toneClass": "degraded",
                "labelText": "Play handoff failed",
                "title": "Play handoff failed for this completed Ops run.",
            }
        return {
            "key": "play-handoff",
            "toneClass": "connecting",
            "labelText": "Play handoff pending",
            "title": "Play was triggered for this completed Ops run and is still pending or needs attention.",
        }
    if run_status in {"stopped", "succeeded"}:
        return {
            "key": "done",
            "toneClass": "done",
            "labelText": "Codex completed",
            "title": "Completion has been detected for this session.",
        }
    return None


def _is_activity_session(session: dict) -> bool:
    if not isinstance(session, dict) or session.get("archived"):
        return False
    raw_run = session.get("ops_run")
    run = raw_run if isinstance(raw_run, dict) else {}
    run_status = str(run.get("status") or "").strip().lower()
    raw_task = session.get("ops_task")
    task = raw_task if isinstance(raw_task, dict) else {}
    if session.get("waitingForApproval") or session.get("waitingForInput"):
        return True
    if _session_has_live_stream(session):
        return True
    if str(task.get("id") or "").strip():
        return True
    if str(session.get("source_tag") or "").strip() == ops_sessions.OPS_TASK_SOURCE_TAG:
        return True
    if _play_handoff_activity_status(run):
        return True
    return run_status in _ACTIVE_RUN_STATUSES


def _activity_title(session: dict) -> str:
    for candidate in (
        session.get("label"),
        ((session.get("ops_task") or {}).get("text") if isinstance(session.get("ops_task"), dict) else ""),
        session.get("title"),
        session.get("branchLabel"),
        session.get("repositoryLabel"),
    ):
        value = str(candidate or "").strip()
        if value:
            return value
    return "Untitled"


def _activity_project_name(session: dict) -> str:
    return str(
        session.get("projectName")
        or session.get("repositoryLabel")
        or session.get("branchLabel")
        or "Default workspace"
    ).strip() or "Default workspace"


def _activity_repo_label(session: dict) -> str:
    return str(session.get("repositoryLabel") or _activity_project_name(session)).strip()


def _activity_last_output_at(session: dict, run: dict) -> float | None:
    for candidate in (
        session.get("lastOutputAt"),
        session.get("lastActivityAt"),
        session.get("updated_at"),
        session.get("last_message_at"),
        session.get("created_at"),
    ):
        stamp = _epoch_seconds(candidate)
        if stamp > 0:
            return stamp
    return None


def _normalize_run_status(value) -> str:
    return str(value or "").strip().lower().replace("_", "-").replace(" ", "-")


def _text(value, *, limit: int = 512) -> str:
    if not isinstance(value, str):
        value = "" if value is None else str(value)
    return value.strip()[:limit]


def _session_sort_key(session: dict) -> float:
    return max(
        _epoch_seconds(session.get("last_message_at")),
        _epoch_seconds(session.get("updated_at")),
        _epoch_seconds(session.get("created_at")),
        0.0,
    )


def _run_sort_key(run: dict) -> float:
    return max(
        _epoch_seconds(run.get("updatedAt") or run.get("updated_at")),
        _epoch_seconds(run.get("completedAt") or run.get("completed_at")),
        _epoch_seconds(run.get("createdAt") or run.get("created_at")),
        0.0,
    )


def _minimal_ops_projects_by_id() -> dict[str, dict]:
    """Return project metadata without task counts, git probes, or sidecar scans."""
    try:
        raw_projects = ops_projects._read_projects()
    except Exception:
        return {}

    projects: dict[str, dict] = {}
    for project in raw_projects:
        if not isinstance(project, dict):
            continue
        project_id = str(project.get("id") or "").strip()
        if not project_id:
            continue
        item = dict(project)
        path = str(item.get("path") or item.get("resolvedPath") or "").strip()
        if path and not item.get("resolvedPath"):
            try:
                item["resolvedPath"] = str(Path(path).expanduser().resolve())
            except Exception:
                item["resolvedPath"] = path
        item.setdefault("fullName", item.get("name") or project_id)
        projects[project_id] = item
    return projects


def _project_id_for_session(session: dict) -> str:
    return str(
        session.get("ops_project_id")
        or session.get("projectId")
        or session.get("project_id")
        or ""
    ).strip()


def _candidate_task_files(project: dict) -> list[Path]:
    path = str(project.get("path") or project.get("resolvedPath") or "").strip()
    if not path:
        return []
    try:
        root = Path(path).expanduser().resolve()
    except Exception:
        root = Path(path).expanduser()
    tasks_dir = root / getattr(ops_projects, "TASKS_DIR_NAME", "project_tasks")
    sanitize = getattr(ops_projects, "_sanitize_branch_file_name", lambda value: _text(value, limit=128) or "default")
    default_scope = getattr(ops_projects, "DEFAULT_TASKS_SCOPE", "default")
    branches = [
        project.get("tasksBranch"),
        project.get("coreBranch"),
        default_scope,
        "main",
        "master",
    ]
    candidates: list[Path] = []
    seen: set[Path] = set()

    def add(candidate: Path) -> None:
        try:
            key = candidate.resolve()
        except Exception:
            key = candidate
        if key not in seen:
            seen.add(key)
            candidates.append(candidate)

    for branch in branches:
        branch_name = _text(branch, limit=128)
        if branch_name:
            add(tasks_dir / f"{sanitize(branch_name)}.json")
    add(root / getattr(ops_projects, "LEGACY_TASKS_FILE_NAME", "project_tasks.json"))
    try:
        extras = sorted(
            tasks_dir.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        extras = []
    for candidate in extras[:12]:
        add(candidate)
    return candidates


def _load_project_tasks_by_id(project: dict) -> dict[str, dict]:
    """Read task text/done state without resolving session sidecars."""
    tasks_by_id: dict[str, dict] = {}
    normalize_payload = getattr(ops_projects, "_normalize_tasks_payload", None)
    for path in _candidate_task_files(project):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if callable(normalize_payload):
            try:
                payload = normalize_payload(payload)[0]
            except Exception:
                pass
        epics = payload.get("epics") or [] if isinstance(payload, dict) else []
        for epic in epics:
            epic_title = _text((epic or {}).get("title"), limit=256)
            for task in (epic or {}).get("tasks") or []:
                if not isinstance(task, dict):
                    continue
                task_id = _text(task.get("id"), limit=128)
                if not task_id or task_id in tasks_by_id:
                    continue
                task_context = dict(task)
                if epic_title:
                    task_context["epicTitle"] = epic_title
                tasks_by_id[task_id] = task_context
    return tasks_by_id


def _read_raw_ops_runs() -> list[dict]:
    """Read run records once without per-run enrichment."""
    try:
        from api import ops_runs

        lock = getattr(ops_runs, "_LOCK", None)
        if lock is not None:
            with lock:
                return [dict(run) for run in ops_runs._read_runs()]
        return [dict(run) for run in ops_runs._read_runs()]
    except Exception:
        return []


def _run_task_context(run: dict, project: dict | None, task_cache: dict[str, dict[str, dict]]) -> dict | None:
    project_id = _text(run.get("projectId") or run.get("project_id"), limit=128)
    task_id = _text(run.get("taskId") or run.get("task_id"), limit=128)
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    if project and project_id and project_id not in task_cache:
        task_cache[project_id] = _load_project_tasks_by_id(project)
    task = (task_cache.get(project_id) or {}).get(task_id)
    if isinstance(task, dict):
        return dict(task)
    task_text = _text(metadata.get("taskText") or metadata.get("task_text") or run.get("title"), limit=512)
    if task_id or task_text:
        return {
            "id": task_id,
            "text": task_text,
            "done": False,
        }
    return None


def _project_context_for_session(session: dict, project_by_id: dict[str, dict]) -> dict | None:
    project_id = _project_id_for_session(session)
    if project_id and project_id in project_by_id:
        return project_by_id[project_id]
    workspace = str(session.get("workspace") or "").rstrip("/")
    if not workspace:
        return None
    for project in project_by_id.values():
        project_path = str(project.get("resolvedPath") or project.get("path") or "").rstrip("/")
        if project_path and project_path == workspace:
            return project
    return None


def _sidecar_records_for_runs(raw_runs: list[dict]) -> list[dict]:
    """Load lightweight sidecar records for projects referenced by raw runs."""
    project_ids = {
        _text(run.get("projectId") or run.get("project_id"), limit=128)
        for run in raw_runs
        if isinstance(run, dict)
    }
    records: list[dict] = []
    for project_id in sorted(project_ids):
        if not project_id:
            continue
        try:
            records.extend(ops_sessions.session_sidecars.list_project_linkage_records(project_id))
        except Exception:
            continue
    return [record for record in records if isinstance(record, dict)]


def _best_activity_session_id(candidate_ids: set[str], session_by_id: dict[str, dict]) -> str:
    candidates = [session_by_id[session_id] for session_id in candidate_ids if session_id in session_by_id]
    if not candidates:
        return ""
    best = max(candidates, key=_session_sort_key)
    return _text(best.get("session_id"), limit=128)


def _sidecar_activity_aliases(
    raw_runs: list[dict],
    alias_to_session_id: dict[str, str],
    session_by_id: dict[str, dict],
) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """Map Ops run/task ids to currently visible logical sessions via sidecars.

    The activity poller intentionally starts from the cheap sidebar session list,
    which hides many pre-compression snapshots. A run can still point at a hidden
    root or hidden continuation while a visible sibling/snapshot has the same
    task/run sidecar. Use those sidecars as aliases so incomplete Ops tasks do
    not vanish from activity just because compression hid the stored run ids.
    """
    run_aliases: dict[str, set[str]] = {}
    task_aliases: dict[tuple[str, str], set[str]] = {}
    for record in _sidecar_records_for_runs(raw_runs):
        record_session_id = _text(record.get("sessionId") or record.get("session_id"), limit=128)
        mapped_session_id = alias_to_session_id.get(record_session_id)
        if not mapped_session_id or mapped_session_id not in session_by_id:
            continue
        run_id = _text(record.get("runId") or record.get("run_id"), limit=128)
        if run_id:
            run_aliases.setdefault(run_id, set()).add(mapped_session_id)
        project_id = _text(record.get("projectId") or record.get("project_id"), limit=128)
        task_id = _text(record.get("taskId") or record.get("task_id"), limit=128)
        if project_id and task_id:
            task_aliases.setdefault((project_id, task_id), set()).add(mapped_session_id)
    return (
        {run_id: _best_activity_session_id(ids, session_by_id) for run_id, ids in run_aliases.items()},
        {key: _best_activity_session_id(ids, session_by_id) for key, ids in task_aliases.items()},
    )


def _lean_activity_source() -> dict:
    """Build the activity list from cheap indexes and raw run records only.

    The rich Ops sessions endpoint intentionally resolves projects, tasks,
    linkages, runs, pending requests, and session sidecars. The
    activity poller runs every few seconds, so it must avoid that N+1 enrichment
    path and use already-indexed session summaries plus a single raw runs read.
    """
    try:
        session_summaries = [session for session in all_sessions() if isinstance(session, dict)]
    except Exception:
        session_summaries = []

    try:
        from api.session_auto_archive import archive_stale_sessions

        archive_result = archive_stale_sessions(session_summaries)
        if int(archive_result.get("archived") or 0) > 0:
            session_summaries = [session for session in all_sessions() if isinstance(session, dict)]
    except Exception:
        pass

    try:
        session_summaries = ops_sessions.session_sidecars._with_parent_lineage_metadata(session_summaries)
    except Exception:
        pass

    project_by_id = _minimal_ops_projects_by_id()
    task_cache: dict[str, dict[str, dict]] = {}
    logical_sessions: dict[str, dict] = {}
    alias_to_session_id: dict[str, str] = {}
    for session in session_summaries:
        if not isinstance(session, dict) or session.get("archived"):
            continue
        lineage_root = str(session.get("_lineage_root_id") or session.get("session_id") or "").strip()
        session_id = str(session.get("session_id") or "").strip()
        if not lineage_root or not session_id:
            continue
        current = logical_sessions.get(lineage_root)
        if not current or ops_sessions._ops_task_session_rank(session) >= ops_sessions._ops_task_session_rank(current):
            logical_sessions[lineage_root] = dict(session)
    session_by_id: dict[str, dict] = {}
    for session in logical_sessions.values():
        session_id = str(session.get("session_id") or "").strip()
        if not session_id:
            continue
        session_by_id[session_id] = session
        for alias in _session_aliases(session):
            alias_to_session_id[alias] = session_id

    run_context_by_session_id: dict[str, dict] = {}
    raw_runs = _read_raw_ops_runs()
    sidecar_run_aliases, sidecar_task_aliases = _sidecar_activity_aliases(raw_runs, alias_to_session_id, session_by_id)
    for raw_run in raw_runs:
        status = _normalize_run_status(raw_run.get("status")) or "running"
        if status not in _VISIBLE_RUN_STATUSES:
            continue
        stored_session_id = _text(raw_run.get("sessionId") or raw_run.get("session_id"), limit=128)
        if not stored_session_id:
            continue
        session_id = alias_to_session_id.get(stored_session_id)
        if not session_id:
            metadata = raw_run.get("metadata") if isinstance(raw_run.get("metadata"), dict) else {}
            resolved_session_id = _text(metadata.get("resolvedSessionId") or metadata.get("resolved_session_id"), limit=128)
            session_id = alias_to_session_id.get(resolved_session_id)
        if not session_id:
            run_id = _text(raw_run.get("id") or raw_run.get("runId") or raw_run.get("run_id"), limit=128)
            session_id = sidecar_run_aliases.get(run_id, "")
        if not session_id:
            project_task_key = (
                _text(raw_run.get("projectId") or raw_run.get("project_id"), limit=128),
                _text(raw_run.get("taskId") or raw_run.get("task_id"), limit=128),
            )
            session_id = sidecar_task_aliases.get(project_task_key, "")
        if not session_id:
            continue
        session = session_by_id.get(session_id)
        if not isinstance(session, dict) or session.get("archived"):
            continue
        run = dict(raw_run)
        run["status"] = status
        run.setdefault("pendingRequestCount", 0)
        project_id = _text(run.get("projectId") or run.get("project_id") or _project_id_for_session(session), limit=128)
        project = project_by_id.get(project_id) or _project_context_for_session(session, project_by_id)
        task = _run_task_context(run, project, task_cache)
        current = run_context_by_session_id.get(session_id)
        if not current or _run_sort_key(run) >= _run_sort_key(current.get("run") or {}):
            run_context_by_session_id[session_id] = {"run": run, "project": project, "task": task}

    enriched_sessions: list[dict] = []
    for session in sorted(logical_sessions.values(), key=_session_sort_key, reverse=True):
        session_id = str(session.get("session_id") or "").strip()
        context = run_context_by_session_id.get(session_id) or {}
        project = context.get("project") or _project_context_for_session(session, project_by_id)
        task = context.get("task")
        run = context.get("run")
        if run or _session_has_live_stream(session):
            enriched_sessions.append(ops_sessions._enrich_session_summary(session, project, task, run))

    try:
        enriched_sessions = ops_sessions._dedupe_ops_task_sessions(enriched_sessions)
    except Exception:
        enriched_sessions.sort(key=_session_sort_key, reverse=True)
    return {"sessions": enriched_sessions}


def _serialize_activity_session(session: dict, assignment_map: dict[str, str]) -> dict:
    run = session.get("ops_run") if isinstance(session.get("ops_run"), dict) else {}
    group_id = None
    for alias in _session_aliases(session):
        if alias in assignment_map:
            group_id = assignment_map[alias]
            break
    status = _activity_status(session) or {
        "key": "idle",
        "toneClass": "idle",
        "labelText": "Quiet",
        "title": "No recent Codex activity detected for this session.",
    }
    last_output_at = _activity_last_output_at(session, run)
    task = session.get("ops_task") if isinstance(session.get("ops_task"), dict) else {}
    return {
        "id": str(session.get("session_id") or "").strip(),
        "projectId": str(session.get("ops_project_id") or session.get("projectId") or "").strip() or None,
        "projectName": _activity_project_name(session),
        "repoLabel": _activity_repo_label(session),
        "branchLabel": str(session.get("branchLabel") or "").strip() or None,
        "label": _activity_title(session),
        "taskId": str(task.get("id") or "").strip() or None,
        "taskText": str(task.get("text") or "").strip() or None,
        "lastActive": session.get("updated_at"),
        "lastOutputAt": last_output_at,
        "outputSequence": max(0, int(session.get("message_count") or 0)),
        "notificationFlowState": "running",
        "approvalPromptVisible": False,
        "promptVisible": False,
        "promptLine": None,
        "waitingForInput": bool(session.get("waitingForInput")),
        "waitingForInputSince": session.get("waitingSince"),
        "groupId": group_id,
        "running": True,
        "activityStatus": status,
    }


def _truthy_env(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _session_activity_rich_fallback_enabled() -> bool:
    return _truthy_env(os.getenv("HERMES_WEBUI_SESSION_ACTIVITY_RICH_FALLBACK"))


def _rich_ops_activity_source() -> dict | None:
    try:
        fallback = ops_sessions.list_ops_sessions()
    except Exception:
        return None
    return fallback if isinstance(fallback, dict) else None


def _list_ops_activity_source(*, allow_rich_fallback: bool | None = None) -> dict:
    rich_fallback_requested = (
        _session_activity_rich_fallback_enabled()
        if allow_rich_fallback is None
        else bool(allow_rich_fallback)
    )
    try:
        source = _lean_activity_source()
    except Exception:
        fallback = _rich_ops_activity_source()
        if fallback is not None:
            return fallback
        raise
    # An empty lean result is authoritative for the poller. Falling back to the
    # rich Ops session route just to prove emptiness can turn a cheap activity
    # refresh into a multi-second global enrichment pass.
    if source.get("sessions") or not rich_fallback_requested:
        return source
    fallback = _rich_ops_activity_source()
    if isinstance(fallback, dict) and fallback.get("sessions"):
        return fallback
    return source


def list_session_activity(*, allow_rich_fallback: bool | None = None) -> dict:
    state = _read_state()
    assignment_map = {
        str(entry.get("sessionId") or "").strip(): str(entry.get("groupId") or "").strip()
        for entry in state.get("assignments") or []
        if str(entry.get("sessionId") or "").strip() and str(entry.get("groupId") or "").strip()
    }
    try:
        source = _list_ops_activity_source(allow_rich_fallback=allow_rich_fallback)
    except Exception:
        source = {"sessions": []}
    sessions = [
        _serialize_activity_session(session, assignment_map)
        for session in source.get("sessions") or []
        if _is_activity_session(session)
    ]
    sessions.sort(
        key=lambda item: (
            float(item.get("lastOutputAt") or 0.0),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    return {
        "generatedAt": _now_iso(),
        "detectionMode": "ops_run_state",
        "refreshIntervalMs": SESSION_ACTIVITY_REFRESH_INTERVAL_MS,
        "groupCount": len(state.get("groups") or []),
        "groups": state.get("groups") or [],
        "sessionCount": len(sessions),
        "sessions": sessions,
    }


def create_session_activity_group(label: str) -> dict:
    state = _read_state()
    if len(state["groups"]) >= SESSION_ACTIVITY_GROUP_LIMIT:
        raise SessionActivityError(f"Group limit reached ({SESSION_ACTIVITY_GROUP_LIMIT}).")
    normalized_label = _normalize_group_label(label)
    if not normalized_label:
        raise SessionActivityError("Group label is required.")
    now_iso = _now_iso()
    group = {
        "id": uuid.uuid4().hex,
        "label": normalized_label,
        "position": len(state["groups"]),
        "createdAt": now_iso,
        "updatedAt": now_iso,
    }
    state["groups"].append(group)
    _write_state(state, "session_activity_group_created")
    return group


def rename_session_activity_group(group_id: str, label: str) -> dict:
    state = _read_state()
    normalized_group_id = str(group_id or "").strip()
    normalized_label = _normalize_group_label(label)
    if not normalized_group_id:
        raise SessionActivityError("Group id is required.")
    if not normalized_label:
        raise SessionActivityError("Group label is required.")
    target = next((group for group in state["groups"] if group["id"] == normalized_group_id), None)
    if not target:
        raise SessionActivityError("Group not found.", 404)
    target["label"] = normalized_label
    target["updatedAt"] = _now_iso()
    _write_state(state, "session_activity_group_updated")
    return target


def delete_session_activity_group(group_id: str) -> dict:
    state = _read_state()
    normalized_group_id = str(group_id or "").strip()
    if not normalized_group_id:
        raise SessionActivityError("Group id is required.")
    groups = [group for group in state["groups"] if group["id"] != normalized_group_id]
    if len(groups) == len(state["groups"]):
        raise SessionActivityError("Group not found.", 404)
    removed_assignment_count = sum(
        1 for entry in state["assignments"] if entry.get("groupId") == normalized_group_id
    )
    state["groups"] = [
        {**group, "position": index}
        for index, group in enumerate(groups)
    ]
    state["assignments"] = [
        entry for entry in state["assignments"] if entry.get("groupId") != normalized_group_id
    ]
    _write_state(state, "session_activity_group_deleted")
    return {
        "groupId": normalized_group_id,
        "removedAssignmentCount": removed_assignment_count,
    }


def set_session_activity_group_assignment(session_id: str, group_id: str | None) -> dict:
    state = _read_state()
    canonical_session_id = _canonical_assignment_session_id(session_id)
    if not canonical_session_id:
        raise SessionActivityError("Session id is required.")
    normalized_group_id = str(group_id or "").strip() or None
    if normalized_group_id and not any(group["id"] == normalized_group_id for group in state["groups"]):
        raise SessionActivityError("Group not found.", 404)
    existing_index = next(
        (
            index
            for index, entry in enumerate(state["assignments"])
            if str(entry.get("sessionId") or "").strip() == canonical_session_id
        ),
        -1,
    )
    if normalized_group_id is None:
        if existing_index < 0:
            return {"sessionId": canonical_session_id, "groupId": None, "changed": False}
        state["assignments"].pop(existing_index)
        _write_state(state, "session_activity_group_assignment_cleared")
        return {"sessionId": canonical_session_id, "groupId": None, "changed": True}
    if existing_index < 0 and len(state["assignments"]) >= SESSION_ACTIVITY_GROUP_ASSIGNMENT_LIMIT:
        raise SessionActivityError(
            f"Session group assignment limit reached ({SESSION_ACTIVITY_GROUP_ASSIGNMENT_LIMIT})."
        )
    assignment = {
        "sessionId": canonical_session_id,
        "groupId": normalized_group_id,
        "updatedAt": _now_iso(),
    }
    if existing_index >= 0:
        state["assignments"][existing_index] = assignment
    else:
        state["assignments"].append(assignment)
    _write_state(state, "session_activity_group_assignment_updated")
    return {"sessionId": canonical_session_id, "groupId": normalized_group_id, "changed": True}

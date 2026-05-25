"""Automatic cleanup for stale WebUI sessions.

The activity dashboard polls frequently, so this module performs a cheap,
throttled sweep that archives sessions untouched for more than a week.  It only
full-loads sessions that are already stale candidates and never saves a
metadata-only stub, preserving full transcripts while clearing stale pending /
stream sidecar fields from the sidebar and activity views.
"""

from __future__ import annotations

from datetime import datetime
import os
import threading
import time


STALE_SESSION_ARCHIVE_AFTER_SECONDS = int(
    os.getenv("HERMES_WEBUI_STALE_SESSION_ARCHIVE_AFTER_SECONDS") or str(7 * 24 * 60 * 60)
)
STALE_SESSION_ARCHIVE_SWEEP_INTERVAL_SECONDS = int(
    os.getenv("HERMES_WEBUI_STALE_SESSION_ARCHIVE_SWEEP_INTERVAL_SECONDS") or "60"
)
_ACTIVE_RUN_STATUSES = {
    "queued",
    "starting",
    "running",
    "waiting-input",
    "waiting-approval",
}
_SWEEP_LOCK = threading.Lock()
_LAST_SWEEP_AT = 0.0


def _epoch_seconds(value) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _normalize_run_status(value) -> str:
    return str(value or "").strip().lower().replace("_", "-").replace(" ", "-")


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


def _last_touched_at(session: dict) -> float:
    return max(
        _epoch_seconds(session.get("last_message_at")),
        _epoch_seconds(session.get("updated_at")),
        _epoch_seconds(session.get("created_at")),
        _epoch_seconds(session.get("pending_started_at")),
        0.0,
    )


def _run_touched_at(run: dict) -> float:
    return max(
        _epoch_seconds(run.get("updatedAt") or run.get("updated_at")),
        _epoch_seconds(run.get("completedAt") or run.get("completed_at")),
        _epoch_seconds(run.get("createdAt") or run.get("created_at")),
        0.0,
    )


def _recent_active_run_aliases(*, cutoff: float) -> set[str]:
    """Return session aliases tied to live/recent active Ops runs.

    A months-old run stuck in ``running`` should not keep an untouched session
    visible forever; a currently updating active run must never be archived.
    Missing run timestamps are treated as active/recent for safety.
    """
    try:
        from api import ops_runs

        lock = getattr(ops_runs, "_LOCK", None)
        if lock is not None:
            with lock:
                runs = [dict(run) for run in ops_runs._read_runs()]
        else:
            runs = [dict(run) for run in ops_runs._read_runs()]
    except Exception:
        return set()

    aliases: set[str] = set()
    for run in runs:
        if not isinstance(run, dict):
            continue
        if _normalize_run_status(run.get("status")) not in _ACTIVE_RUN_STATUSES:
            continue
        touched_at = _run_touched_at(run)
        if touched_at and touched_at < cutoff:
            continue
        for field in ("sessionId", "session_id"):
            value = str(run.get(field) or "").strip()
            if value:
                aliases.add(value)
        metadata_raw = run.get("metadata")
        metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
        for field in ("resolvedSessionId", "resolved_session_id"):
            value = str(metadata.get(field) or "").strip()
            if value:
                aliases.add(value)
    return aliases


def _is_archive_candidate(
    session: dict,
    *,
    cutoff: float,
    recent_active_aliases: set[str],
) -> bool:
    if not isinstance(session, dict):
        return False
    if session.get("archived") or session.get("pinned"):
        return False
    if session.get("is_streaming"):
        return False
    if session.get("waitingForApproval") or session.get("waitingForInput"):
        return False
    session_id = str(session.get("session_id") or "").strip()
    if not session_id:
        return False
    if _session_aliases(session) & recent_active_aliases:
        return False
    touched_at = _last_touched_at(session)
    return bool(touched_at and touched_at < cutoff)


def _load_mutable_session(session_id: str):
    from api import models

    with models.LOCK:
        in_memory = models.SESSIONS.get(session_id)
    if in_memory is not None:
        return in_memory
    return models.Session.load(session_id)


def _runtime_compact(session) -> dict:
    from api import models

    try:
        active_stream_ids = models._active_stream_ids()
    except Exception:
        active_stream_ids = set()
    return session.compact(include_runtime=True, active_stream_ids=active_stream_ids)


def archive_stale_sessions(
    session_summaries,
    *,
    now: float | None = None,
    force: bool = False,
    max_age_seconds: int | None = None,
) -> dict:
    """Archive sessions untouched longer than ``max_age_seconds``.

    The caller passes already-indexed compact summaries.  This function is
    throttled by default and only full-loads candidate sessions before mutating
    ``archived`` plus stale ``active_stream_id`` / pending-message fields.
    """
    global _LAST_SWEEP_AT

    now_ts = float(now if now is not None else time.time())
    age_seconds = int(max_age_seconds or STALE_SESSION_ARCHIVE_AFTER_SECONDS)
    if age_seconds <= 0:
        return {"archived": 0, "checked": 0, "skipped": "disabled"}

    if not force:
        with _SWEEP_LOCK:
            if now_ts - _LAST_SWEEP_AT < STALE_SESSION_ARCHIVE_SWEEP_INTERVAL_SECONDS:
                return {"archived": 0, "checked": 0, "skipped": "throttled"}
            _LAST_SWEEP_AT = now_ts

    summaries = [session for session in (session_summaries or []) if isinstance(session, dict)]
    cutoff = now_ts - age_seconds
    recent_active_aliases = _recent_active_run_aliases(cutoff=cutoff)
    candidate_ids: list[str] = []
    seen: set[str] = set()
    for summary in summaries:
        if not _is_archive_candidate(summary, cutoff=cutoff, recent_active_aliases=recent_active_aliases):
            continue
        session_id = str(summary.get("session_id") or "").strip()
        if session_id and session_id not in seen:
            seen.add(session_id)
            candidate_ids.append(session_id)

    archived_ids: list[str] = []
    for session_id in candidate_ids:
        try:
            session = _load_mutable_session(session_id)
        except Exception:
            session = None
        if session is None:
            continue
        try:
            compact = _runtime_compact(session)
            if not _is_archive_candidate(compact, cutoff=cutoff, recent_active_aliases=recent_active_aliases):
                continue
            session.archived = True
            setattr(session, "active_stream_id", None)
            setattr(session, "pending_user_message", None)
            session.pending_attachments = []
            setattr(session, "pending_started_at", None)
            session.save(touch_updated_at=False)
            archived_ids.append(session_id)
        except Exception:
            continue

    return {
        "archived": len(archived_ids),
        "checked": len(candidate_ids),
        "sessionIds": archived_ids,
        "cutoff": cutoff,
        "maxAgeSeconds": age_seconds,
    }

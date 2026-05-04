"""Fork-owned maintenance-session upstream-sync helpers."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api import ops_git, ops_projects, ops_sessions
from api.config import STATE_DIR, STREAMS, STREAMS_LOCK, _get_session_agent_lock
from api.models import get_session, new_session
from api.streaming import _run_agent_streaming
from api.workspace import set_last_workspace


OPS_MAINTENANCE_SOURCE_TAG = "ops_maintenance"
OPS_MAINTENANCE_SOURCE_LABEL = "Ops maintenance"
OPS_UPSTREAM_SYNC_ROOT = STATE_DIR / "ops" / "upstream-sync"
OPS_UPSTREAM_SYNC_RECORDS_DIR = OPS_UPSTREAM_SYNC_ROOT / "records"
OPS_UPSTREAM_SYNC_WORKTREES_DIR = OPS_UPSTREAM_SYNC_ROOT / "worktrees"
_LOCK = threading.RLock()


class OpsUpstreamSyncError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class UpstreamSyncContext:
    project: dict
    repo_path: Path
    worktree_path: Path
    source_branch: str
    source_head_sha: str
    sync_branch: str
    upstream_remote: str
    upstream_branch: str
    upstream_ref: str
    profile: str | None
    model: str | None
    model_provider: str | None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _text(value: Any, *, limit: int = 512) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _safe_slug(value: str) -> str:
    raw = "".join(char.lower() if char.isalnum() else "-" for char in _text(value, limit=256))
    slug = "-".join(part for part in raw.split("-") if part)
    return slug or "sync"


def _record_id(project_id: str, source_branch: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"upstream-sync-{_safe_slug(project_id)}-{_safe_slug(source_branch)}-{stamp}"


def _record_path(record_id: str) -> Path:
    key = _text(record_id, limit=256)
    if not key:
        raise OpsUpstreamSyncError("Upstream sync record id is required.")
    return OPS_UPSTREAM_SYNC_RECORDS_DIR / f"{_safe_slug(key)}.json"


def _read_record(record_id: str) -> dict | None:
    path = _record_path(record_id)
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise OpsUpstreamSyncError(f"Upstream sync record {record_id} contains invalid JSON.", 500) from exc
    return parsed if isinstance(parsed, dict) else None


def _write_record(record: dict) -> dict:
    record_id = _text(record.get("id"), limit=256)
    if not record_id:
        raise OpsUpstreamSyncError("Upstream sync record id is required.", 500)
    OPS_UPSTREAM_SYNC_RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    path = _record_path(record_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return record


def _run_git(repo_path: Path, args: list[str], *, timeout: float = 30.0, check: bool = True) -> subprocess.CompletedProcess:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise OpsUpstreamSyncError("Git is not available on this system.", 500) from exc
    except subprocess.TimeoutExpired as exc:
        raise OpsUpstreamSyncError(f"Git {' '.join(args[:2] or ['operation'])} timed out.", 504) from exc
    except OSError as exc:
        raise OpsUpstreamSyncError("Unable to run git for upstream sync.", 500) from exc
    if check and completed.returncode != 0:
        detail = _text((completed.stderr or completed.stdout or "").strip(), limit=1200)
        raise OpsUpstreamSyncError(detail or "Git command failed.", 409)
    return completed


def _git_stdout(repo_path: Path, args: list[str], *, timeout: float = 15.0) -> str:
    return _run_git(repo_path, args, timeout=timeout).stdout.strip()


def _project_repo_path(project_id: str) -> tuple[dict, Path]:
    project = ops_projects.get_ops_project(project_id)
    raw_path = project.get("resolvedPath") or project.get("path")
    if not raw_path:
        raise OpsUpstreamSyncError("Project path is unavailable.", 404)
    path = Path(str(raw_path)).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise OpsUpstreamSyncError("Project path is unavailable.", 404)
    inside = _run_git(path, ["rev-parse", "--is-inside-work-tree"], check=False, timeout=6.0)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        raise OpsUpstreamSyncError("Project path is not inside a Git repository.", 409)
    return project, path


def _working_tree_status(repo_path: Path) -> tuple[bool, str]:
    result = _run_git(
        repo_path,
        [
            "status",
            "--porcelain=v1",
            "--",
            ".",
            *[f":(exclude){path}" for path in ops_git.STATUS_EXCLUDED_PATHS],
        ],
        check=False,
        timeout=8.0,
    )
    if result.returncode != 0:
        return False, ""
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    summary = ", ".join(lines[:8])
    if len(lines) > 8:
        summary = f"{summary}, +{len(lines) - 8} more"
    return bool(lines), summary


def _git_path(repo_path: Path, relative_path: str) -> Path | None:
    result = _run_git(repo_path, ["rev-parse", "--git-path", relative_path], check=False, timeout=6.0)
    if result.returncode != 0:
        return None
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = (repo_path / path).resolve()
    return path


def _operation_in_progress(repo_path: Path) -> tuple[bool, str]:
    checks = [
        ("merge", _git_path(repo_path, "MERGE_HEAD")),
        ("rebase", _git_path(repo_path, "rebase-apply")),
        ("rebase", _git_path(repo_path, "rebase-merge")),
        ("cherry-pick", _git_path(repo_path, "CHERRY_PICK_HEAD")),
        ("revert", _git_path(repo_path, "REVERT_HEAD")),
    ]
    active = [label for label, path in checks if path and path.exists()]
    return bool(active), ", ".join(sorted(set(active)))


def _ref_exists(repo_path: Path, ref: str) -> bool:
    if not ref:
        return False
    return _run_git(repo_path, ["rev-parse", "--verify", ref], check=False, timeout=8.0).returncode == 0


def _detect_upstream_branch(repo_path: Path, remote: str, core_branch: str) -> str:
    preferred = _text(core_branch, limit=256) or "main"
    if _ref_exists(repo_path, f"{remote}/{preferred}"):
        return preferred
    symbolic = _run_git(repo_path, ["symbolic-ref", f"refs/remotes/{remote}/HEAD"], check=False, timeout=8.0)
    if symbolic.returncode == 0:
        ref = symbolic.stdout.strip()
        prefix = f"refs/remotes/{remote}/"
        if ref.startswith(prefix):
            branch = ref[len(prefix):].strip()
            if branch:
                return branch
    raise OpsUpstreamSyncError(
        f"Remote '{remote}' does not expose branch '{preferred}' and has no detectable default branch.",
        409,
    )


def _session_url(session_id: str) -> str:
    return ops_sessions.session_url(session_id)


def _maintenance_prompt(context: UpstreamSyncContext) -> str:
    return (
        "You are working in a maintenance worktree for an upstream sync.\n\n"
        "Rules:\n"
        "1. Read AGENTS.md before making changes.\n"
        "2. Treat this worktree as the review/apply candidate only; do not edit the source checkout directly.\n"
        "3. Merge or replay the upstream core branch into this worktree, resolve conflicts carefully, run focused verification, and summarize the risk.\n"
        "4. Leave the source checkout untouched until the /ops apply action fast-forwards it.\n"
        "5. If you uncover unrelated messy code, add a follow-up task in the branch-scoped project_tasks file.\n\n"
        f"Source branch: {context.source_branch}\n"
        f"Source head: {context.source_head_sha}\n"
        f"Upstream remote: {context.upstream_remote}\n"
        f"Upstream ref: {context.upstream_ref}\n"
        f"Maintenance branch: {context.sync_branch}\n"
        f"Maintenance worktree: {context.worktree_path}\n"
        "The source checkout's uncommitted project-scoped metadata is not present here unless you copy it deliberately.\n"
        "When the maintenance result is ready, tell the user to return to /ops and use Apply reviewed sync."
    )


def _start_session_prompt(session, message: str) -> str:
    workspace = str(Path(session.workspace).expanduser().resolve())
    stream_id = uuid.uuid4().hex
    with _get_session_agent_lock(session.session_id):
        session.active_stream_id = stream_id
        session.pending_user_message = message
        session.pending_attachments = []
        session.pending_started_at = time.time()
        session.save()
    set_last_workspace(workspace)
    q = queue.Queue()
    with STREAMS_LOCK:
        STREAMS[stream_id] = q
    thread = threading.Thread(
        target=_run_agent_streaming,
        args=(session.session_id, message, session.model, workspace, stream_id, []),
        kwargs={"model_provider": getattr(session, "model_provider", None)},
        daemon=True,
    )
    thread.start()
    return stream_id


def _load_records() -> list[dict]:
    if not OPS_UPSTREAM_SYNC_RECORDS_DIR.exists():
        return []
    records: list[dict] = []
    for path in sorted(OPS_UPSTREAM_SYNC_RECORDS_DIR.glob("*.json")):
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
    records.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    return records


def _project_records(project_id: str) -> list[dict]:
    key = _text(project_id, limit=128)
    return [record for record in _load_records() if _text(record.get("projectId"), limit=128) == key]


def _latest_project_record(project_id: str) -> dict | None:
    records = _project_records(project_id)
    return records[0] if records else None


def _status_from_record(record: dict) -> dict:
    project_id = _text(record.get("projectId"), limit=128)
    project = ops_projects.get_ops_project(project_id)
    repo_path = Path(str(record.get("repoPath") or "")).expanduser().resolve()
    worktree_path = Path(str(record.get("worktreePath") or "")).expanduser().resolve()
    source_branch = _text(record.get("sourceBranch"), limit=256)
    source_head_sha = _text(record.get("sourceHeadSha"), limit=128)
    sync_branch = _text(record.get("syncBranch"), limit=256)
    upstream_remote = _text(record.get("upstreamRemote"), limit=128)
    upstream_branch = _text(record.get("upstreamBranch"), limit=256)
    upstream_ref = _text(record.get("upstreamRef"), limit=256)
    session_id = _text(record.get("sessionId"), limit=128)
    applied_at = _text(record.get("appliedAt"), limit=64)
    applied_head_sha = _text(record.get("appliedHeadSha"), limit=128)
    source_head_now = _git_stdout(repo_path, ["rev-parse", "HEAD"], timeout=10.0)
    current_branch = _git_stdout(repo_path, ["branch", "--show-current"], timeout=6.0)
    worktree_head_sha = _git_stdout(worktree_path, ["rev-parse", "HEAD"], timeout=10.0) if worktree_path.exists() else ""
    source_dirty, source_dirty_summary = _working_tree_status(repo_path)
    worktree_dirty, worktree_dirty_summary = _working_tree_status(worktree_path) if worktree_path.exists() else (False, "")
    source_op, source_op_name = _operation_in_progress(repo_path)
    worktree_op, worktree_op_name = _operation_in_progress(worktree_path) if worktree_path.exists() else (False, "")
    session = None
    if session_id:
        try:
            session = get_session(session_id, metadata_only=True).compact()
        except Exception:
            session = None

    state = "awaiting_review"
    can_apply = False
    blockers: list[str] = []
    message = "Maintenance worktree is waiting for review."
    if applied_at:
        state = "applied"
        message = f"Applied {sync_branch} into {source_branch}."
    elif not worktree_path.exists():
        state = "blocked"
        blockers.append("Maintenance worktree is missing.")
        message = "Maintenance worktree is missing."
    elif current_branch != source_branch:
        state = "blocked"
        blockers.append(f"Source checkout moved to {current_branch or 'detached HEAD'}.")
        message = "Source checkout branch moved since the maintenance session started."
    elif source_head_now != source_head_sha:
        state = "blocked"
        blockers.append("Source checkout head moved.")
        message = "Source checkout head moved since the maintenance session started."
    elif source_op:
        state = "blocked"
        blockers.append(f"Source checkout has {source_op_name} in progress.")
        message = "Source checkout has an in-progress Git operation."
    elif worktree_op:
        state = "blocked"
        blockers.append(f"Maintenance worktree has {worktree_op_name} in progress.")
        message = "Maintenance worktree has an in-progress Git operation."
    elif source_dirty:
        state = "blocked"
        blockers.append(source_dirty_summary or "Source checkout is dirty.")
        message = "Source checkout is dirty. Clean or stash it before applying."
    elif worktree_dirty:
        state = "blocked"
        blockers.append(worktree_dirty_summary or "Maintenance worktree is dirty.")
        message = "Maintenance worktree is dirty. Finish or clean it before applying."
    elif not worktree_head_sha or worktree_head_sha == source_head_sha:
        state = "awaiting_review"
        message = "Maintenance worktree has not advanced beyond the source branch yet."
    else:
        descendant = _run_git(repo_path, ["merge-base", "--is-ancestor", source_head_sha, sync_branch], check=False, timeout=10.0)
        if descendant.returncode != 0:
            state = "blocked"
            blockers.append("Maintenance branch no longer descends from the recorded source head.")
            message = "Maintenance branch no longer descends from the recorded source head."
        else:
            state = "ready_for_review"
            can_apply = True
            message = f"Ready to fast-forward {source_branch} from {source_head_sha[:12]} to {worktree_head_sha[:12]}."

    return {
        "projectId": project_id,
        "projectName": project.get("name"),
        "recordId": _text(record.get("id"), limit=256),
        "sessionId": session_id or None,
        "sessionUrl": _session_url(session_id) if session_id else None,
        "session": session,
        "state": state,
        "canApply": can_apply,
        "applied": bool(applied_at),
        "message": message,
        "blockers": blockers,
        "repoPath": str(repo_path),
        "worktreePath": str(worktree_path),
        "sourceBranch": source_branch,
        "sourceHeadSha": source_head_sha,
        "currentSourceBranch": current_branch,
        "currentSourceHeadSha": source_head_now,
        "syncBranch": sync_branch,
        "syncHeadSha": worktree_head_sha or None,
        "upstreamRemote": upstream_remote,
        "upstreamBranch": upstream_branch,
        "upstreamRef": upstream_ref,
        "sourceDirty": source_dirty,
        "sourceDirtySummary": source_dirty_summary,
        "worktreeDirty": worktree_dirty,
        "worktreeDirtySummary": worktree_dirty_summary,
        "profile": _text(record.get("profile"), limit=128) or None,
        "model": _text(record.get("model"), limit=256) or None,
        "modelProvider": _text(record.get("modelProvider"), limit=128) or None,
        "createdAt": _text(record.get("createdAt"), limit=64),
        "appliedAt": applied_at or None,
        "appliedHeadSha": applied_head_sha or None,
        "prompt": _text(record.get("prompt"), limit=8000),
    }


def _resolve_record(project_id: str, record_id: str = "") -> dict:
    record = _read_record(record_id) if record_id else _latest_project_record(project_id)
    if not record:
        raise OpsUpstreamSyncError("Upstream sync record not found.", 404)
    if _text(record.get("projectId"), limit=128) != _text(project_id, limit=128):
        raise OpsUpstreamSyncError("Upstream sync record does not belong to this project.", 404)
    return record


def _create_context(project_id: str, body: dict | None = None) -> UpstreamSyncContext:
    body = body if isinstance(body, dict) else {}
    project, repo_path = _project_repo_path(project_id)
    upstream_remote = _text(body.get("upstreamRemote"), limit=128) or "upstream"
    remotes = {line.strip() for line in _git_stdout(repo_path, ["remote"], timeout=8.0).splitlines() if line.strip()}
    if upstream_remote not in remotes:
        raise OpsUpstreamSyncError(
            f"Remote '{upstream_remote}' is not configured for this checkout. Add the upstream Hermes remote first.",
            409,
        )
    _run_git(repo_path, ["fetch", upstream_remote, "--prune", "--quiet"], timeout=90.0)
    source_branch = _git_stdout(repo_path, ["branch", "--show-current"], timeout=6.0)
    if not source_branch:
        raise OpsUpstreamSyncError("Upstream sync requires a checked-out source branch.", 409)
    source_head_sha = _git_stdout(repo_path, ["rev-parse", "HEAD"], timeout=8.0)
    core_branch = _text(project.get("coreBranch"), limit=256) or "main"
    upstream_branch = _detect_upstream_branch(repo_path, upstream_remote, core_branch)
    upstream_ref = f"{upstream_remote}/{upstream_branch}"
    record_id = _record_id(str(project.get("id") or project_id), source_branch)
    worktree_path = OPS_UPSTREAM_SYNC_WORKTREES_DIR / record_id
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    sync_branch = f"upstream-sync/{_safe_slug(source_branch)}/{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    _run_git(repo_path, ["worktree", "add", "-b", sync_branch, str(worktree_path), "HEAD"], timeout=180.0)
    profile = _text(body.get("profile"), limit=128) or ops_sessions.project_profile(project)
    model = _text(body.get("model"), limit=256) or None
    model_provider = _text(body.get("modelProvider"), limit=128).lower() or None
    default_model, default_provider = ops_sessions.project_session_defaults(project)
    if not model:
        model = default_model
        if not model_provider:
            model_provider = default_provider
    elif not model_provider and default_model == model and default_provider:
        model_provider = default_provider
    return UpstreamSyncContext(
        project=project,
        repo_path=repo_path,
        worktree_path=worktree_path,
        source_branch=source_branch,
        source_head_sha=source_head_sha,
        sync_branch=sync_branch,
        upstream_remote=upstream_remote,
        upstream_branch=upstream_branch,
        upstream_ref=upstream_ref,
        profile=profile or None,
        model=model or None,
        model_provider=model_provider or None,
    )


def list_project_upstream_sync(project_id: str) -> dict:
    project = ops_projects.get_ops_project(project_id)
    records = _project_records(project_id)
    current = _status_from_record(records[0]) if records else None
    history = []
    for record in records[:5]:
        status = _status_from_record(record)
        history.append(
            {
                "recordId": status["recordId"],
                "state": status["state"],
                "message": status["message"],
                "createdAt": status["createdAt"],
                "appliedAt": status["appliedAt"],
                "sessionUrl": status["sessionUrl"],
                "syncBranch": status["syncBranch"],
                "sourceBranch": status["sourceBranch"],
            }
        )
    return {
        "projectId": project.get("id") or project_id,
        "project": project,
        "hasSync": bool(current),
        "sync": current,
        "records": history,
    }


def start_project_upstream_sync(project_id: str, body: dict | None = None) -> dict:
    context = _create_context(project_id, body)
    title = f"Upstream sync: {context.upstream_branch} -> {context.source_branch}"[:160]
    session = new_session(
        workspace=str(context.worktree_path),
        model=context.model,
        model_provider=context.model_provider,
        profile=context.profile,
    )
    session.title = title
    session.source_tag = OPS_MAINTENANCE_SOURCE_TAG
    session.source_label = OPS_MAINTENANCE_SOURCE_LABEL
    session.save()
    prompt = _maintenance_prompt(context)
    stream_id = _start_session_prompt(session, prompt)
    record = _write_record(
        {
            "id": context.worktree_path.name,
            "projectId": context.project.get("id"),
            "sessionId": session.session_id,
            "repoPath": str(context.repo_path),
            "worktreePath": str(context.worktree_path),
            "sourceBranch": context.source_branch,
            "sourceHeadSha": context.source_head_sha,
            "syncBranch": context.sync_branch,
            "upstreamRemote": context.upstream_remote,
            "upstreamBranch": context.upstream_branch,
            "upstreamRef": context.upstream_ref,
            "profile": context.profile,
            "model": context.model,
            "modelProvider": context.model_provider,
            "prompt": prompt,
            "createdAt": _now_iso(),
            "appliedAt": None,
            "appliedHeadSha": None,
        }
    )
    return {
        "ok": True,
        "message": f"Started maintenance sync session in {context.worktree_path.name}.",
        "project": context.project,
        "session": session.compact() | {"messages": session.messages},
        "sessionUrl": _session_url(session.session_id),
        "streamId": stream_id,
        "recordId": record["id"],
        "sync": _status_from_record(record),
    }


def apply_project_upstream_sync(project_id: str, body: dict | None = None) -> dict:
    body = body if isinstance(body, dict) else {}
    record = _resolve_record(project_id, _text(body.get("recordId") or body.get("record_id"), limit=256))
    status = _status_from_record(record)
    if status.get("applied"):
        raise OpsUpstreamSyncError("This upstream sync has already been applied.", 409)
    if not status.get("canApply"):
        raise OpsUpstreamSyncError(
            f"Cannot apply upstream sync: {status.get('message') or 'review is not complete.'}",
            409,
        )
    repo_path = Path(status["repoPath"]).expanduser().resolve()
    sync_branch = _text(status.get("syncBranch"), limit=256)
    source_branch = _text(status.get("sourceBranch"), limit=256)
    before_sha = _git_stdout(repo_path, ["rev-parse", "HEAD"], timeout=8.0)
    _run_git(repo_path, ["merge", "--ff-only", sync_branch], timeout=120.0)
    after_sha = _git_stdout(repo_path, ["rev-parse", "HEAD"], timeout=8.0)
    record["appliedAt"] = _now_iso()
    record["appliedHeadSha"] = after_sha
    _write_record(record)
    return {
        "ok": True,
        "message": f"Applied {sync_branch} into {source_branch}. {before_sha[:12]} -> {after_sha[:12]}.",
        "sync": _status_from_record(record),
    }

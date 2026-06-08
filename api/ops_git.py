"""Fork-owned project git status helpers for the clean restart branch."""

from __future__ import annotations

import base64
import os
import re
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from api import ops_projects, ops_sessions


STATUS_EXCLUDED_PATHS = [".cloud-terminal", ".hermes", "project_tasks", "project_tasks.json"]
TOKEN_ENV_NAMES = ("HERMES_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")
GITHUB_HTTP_EXTRAHEADER_CONFIG_KEY = "http.https://github.com/.extraheader"
_REPO_OPERATION_LOCKS: dict[str, threading.Lock] = {}
_REPO_OPERATION_LOCKS_GUARD = threading.Lock()


class OpsGitError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class OpsGitMergeConflict(Exception):
    def __init__(self, description: str, detail: str = ""):
        super().__init__(description)
        self.description = description
        self.detail = detail


def _append_git_config_entry(env: dict[str, str], key: str, value: str) -> dict[str, str]:
    next_env = dict(env)
    try:
        config_count = int(next_env.get("GIT_CONFIG_COUNT") or "0")
    except ValueError:
        config_count = 0
    if config_count < 0:
        config_count = 0
    next_env[f"GIT_CONFIG_KEY_{config_count}"] = key
    next_env[f"GIT_CONFIG_VALUE_{config_count}"] = value
    next_env["GIT_CONFIG_COUNT"] = str(config_count + 1)
    return next_env


def _github_token() -> str:
    for name in TOKEN_ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _github_authorization_header(token: str) -> str:
    encoded = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
    return f"AUTHORIZATION: basic {encoded}"


def _git_env() -> dict[str, str]:
    env = {
        **os.environ,
        "GIT_ASKPASS": "echo",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_SSH_COMMAND": os.environ.get("GIT_SSH_COMMAND") or "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new",
    }
    token = _github_token()
    if token:
        env = _append_git_config_entry(env, GITHUB_HTTP_EXTRAHEADER_CONFIG_KEY, _github_authorization_header(token))
    return env


def _repo_operation_lock(repo_path: Path) -> threading.Lock:
    key = str(repo_path.resolve())
    with _REPO_OPERATION_LOCKS_GUARD:
        lock = _REPO_OPERATION_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _REPO_OPERATION_LOCKS[key] = lock
        return lock


def _run_git(repo_path: Path, args: list[str], *, timeout: float = 4.0) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(repo_path),
            env=_git_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OpsGitError(f"Git {' '.join(args[:1] or ['status'])} timed out.", 504) from exc
    except FileNotFoundError as exc:
        raise OpsGitError("Git is not available on this system.", 500) from exc
    except OSError as exc:
        raise OpsGitError("Unable to run git for this project.", 500) from exc


def _is_git_index_lock_error(detail: str) -> bool:
    value = str(detail or "").lower()
    return "index.lock" in value and (
        "file exists" in value
        or "unable to create" in value
        or "another git process" in value
        or "remove the file manually" in value
    )


def _git_path_raw(repo_path: Path, relative_path: str) -> Path | None:
    result = _run_git(repo_path, ["rev-parse", "--git-path", relative_path], timeout=6.0)
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = (repo_path / path).resolve()
    return path


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def _active_git_processes_for_repo(repo_path: Path) -> list[int]:
    proc_root = Path("/proc")
    if not proc_root.exists():
        return []
    repo_root = repo_path.resolve()
    git_dir = _git_path_raw(repo_path, "") or (repo_root / ".git")
    active: list[int] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            pid = int(entry.name)
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        try:
            cmdline_bytes = (entry / "cmdline").read_bytes()
        except OSError:
            cmdline_bytes = b""
        cmdline = cmdline_bytes.replace(b"\x00", b" ").decode("utf-8", "ignore")
        try:
            comm = (entry / "comm").read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            comm = ""
        first_arg = cmdline.split(" ", 1)[0] if cmdline else ""
        process_name = Path(first_arg).name or comm
        if "git" not in process_name and not comm.startswith("git"):
            continue
        try:
            cwd = Path(os.readlink(entry / "cwd")).resolve()
        except OSError:
            cwd = None
        if cwd and (_path_is_within(cwd, repo_root) or _path_is_within(cwd, git_dir)):
            active.append(pid)
            continue
        if str(repo_root) in cmdline or str(git_dir) in cmdline:
            active.append(pid)
    return active


def _clear_stale_git_index_lock(repo_path: Path) -> bool:
    lock_path = _git_path_raw(repo_path, "index.lock") or (repo_path / ".git" / "index.lock")
    if not lock_path.exists():
        return False
    active_pids = _active_git_processes_for_repo(repo_path)
    if active_pids:
        raise OpsGitError("Another Git process is still running for this project. Wait for it to finish, then try again.", 409)
    try:
        lock_path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise OpsGitError("A stale Git index lock is present and could not be removed automatically.", 409) from exc


def _run_git_with_index_lock_recovery(repo_path: Path, args: list[str], *, timeout: float = 4.0) -> subprocess.CompletedProcess:
    result = _run_git(repo_path, args, timeout=timeout)
    if result.returncode != 0 and _is_git_index_lock_error(_git_failure_detail(result)):
        _clear_stale_git_index_lock(repo_path)
        result = _run_git(repo_path, args, timeout=timeout)
    return result


def _git_stdout(repo_path: Path, args: list[str], *, timeout: float = 4.0) -> str | None:
    result = _run_git_with_index_lock_recovery(repo_path, args, timeout=timeout)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _status_args() -> list[str]:
    return [
        "status",
        "--porcelain=v1",
        "-b",
        "--",
        ".",
        *[f":(exclude){path}" for path in STATUS_EXCLUDED_PATHS],
    ]


def _is_status_excluded_path(path: str) -> bool:
    normalized = str(path or "").replace("\\", "/").lstrip("./")
    if not normalized:
        return False
    for excluded in STATUS_EXCLUDED_PATHS:
        clean = excluded.strip("/")
        if normalized == clean or normalized.startswith(f"{clean}/"):
            return True
    return False


def _parse_z_paths(raw: str) -> list[str]:
    if not raw:
        return []
    return [part for part in raw.split("\x00") if part]


def _git_z_paths(repo_path: Path, args: list[str], *, timeout: float = 8.0) -> list[str]:
    result = _run_git_with_index_lock_recovery(repo_path, args, timeout=timeout)
    if result.returncode != 0:
        raise OpsGitError(_git_failure_detail(result) or f"Git {' '.join(args[:1] or ['operation'])} failed.", 409)
    return _parse_z_paths(result.stdout)


def _paths_to_stage(repo_path: Path) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for path in [
        *_git_z_paths(repo_path, ["diff", "--name-only", "-z"], timeout=8.0),
        *_git_z_paths(repo_path, ["ls-files", "-o", "--exclude-standard", "-z"], timeout=8.0),
    ]:
        if not path or path in seen or _is_status_excluded_path(path):
            continue
        seen.add(path)
        paths.append(path)
    return paths


def _unstage_status_excluded_paths(repo_path: Path) -> None:
    # The project page intentionally hides these local Hermes/Cloud Terminal
    # artifacts from status. Keep the push button consistent by ensuring an
    # already-staged artifact is not silently included in the auto-commit.
    _checked_git(repo_path, ["reset", "-q", "--", *STATUS_EXCLUDED_PATHS], timeout=30.0)


def _stage_project_changes(repo_path: Path) -> None:
    _unstage_status_excluded_paths(repo_path)
    paths = _paths_to_stage(repo_path)
    if not paths:
        return
    batch_size = 100
    for index in range(0, len(paths), batch_size):
        _checked_git(repo_path, ["add", "-A", "--", *paths[index : index + batch_size]], timeout=30.0)


def _project_repo_path(project_id: str) -> tuple[dict, Path]:
    project = ops_projects.get_ops_project(project_id)
    raw_path = project.get("resolvedPath") or project.get("path")
    if not raw_path:
        raise OpsGitError("Project path is unavailable.", 404)
    path = Path(str(raw_path)).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise OpsGitError("Project path is unavailable.", 404)
    return project, path


def _parse_int(value: str | None) -> int:
    if value and value.isdigit():
        return int(value)
    return 0


def _git_path(repo_path: Path, relative_path: str) -> Path | None:
    raw = _git_stdout(repo_path, ["rev-parse", "--git-path", relative_path], timeout=6.0)
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = (repo_path / path).resolve()
    return path


def _git_operation_state(repo_path: Path) -> dict:
    merge_head = _git_path(repo_path, "MERGE_HEAD")
    rebase_apply = _git_path(repo_path, "rebase-apply")
    rebase_merge = _git_path(repo_path, "rebase-merge")
    cherry_pick_head = _git_path(repo_path, "CHERRY_PICK_HEAD")
    revert_head = _git_path(repo_path, "REVERT_HEAD")
    merge_in_progress = bool(merge_head and merge_head.exists())
    rebase_in_progress = bool(
        (rebase_apply and rebase_apply.exists()) or (rebase_merge and rebase_merge.exists())
    )
    cherry_pick_in_progress = bool(cherry_pick_head and cherry_pick_head.exists())
    revert_in_progress = bool(revert_head and revert_head.exists())
    return {
        "mergeInProgress": merge_in_progress,
        "rebaseInProgress": rebase_in_progress,
        "cherryPickInProgress": cherry_pick_in_progress,
        "revertInProgress": revert_in_progress,
        "operationInProgress": (
            merge_in_progress or rebase_in_progress or cherry_pick_in_progress or revert_in_progress
        ),
    }


def _parse_status_lines(lines: list[str]) -> dict:
    counts = {
        "files": 0,
        "staged": 0,
        "modified": 0,
        "deleted": 0,
        "renamed": 0,
        "untracked": 0,
        "conflicts": 0,
    }
    files: list[dict] = []
    conflict_pairs = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}

    for line in lines:
        if not line or line.startswith("##") or len(line) < 3:
            continue
        xy = line[:2]
        path = line[3:].strip()
        if not path:
            continue
        entry = {"path": path, "index": xy[0], "worktree": xy[1], "status": xy}
        counts["files"] += 1
        if xy == "??":
            counts["untracked"] += 1
            entry["kind"] = "untracked"
        else:
            if xy[0] not in (" ", "?"):
                counts["staged"] += 1
            if xy[1] not in (" ", "?"):
                counts["modified"] += 1
            if "D" in xy:
                counts["deleted"] += 1
            if "R" in xy or "C" in xy:
                counts["renamed"] += 1
            if xy in conflict_pairs or "U" in xy:
                counts["conflicts"] += 1
                entry["kind"] = "conflict"
            elif "D" in xy:
                entry["kind"] = "deleted"
            elif "R" in xy or "C" in xy:
                entry["kind"] = "renamed"
            else:
                entry["kind"] = "modified"
        files.append(entry)

    return {"counts": counts, "files": files[:100]}


def _last_commit(repo_path: Path) -> dict | None:
    raw = _git_stdout(repo_path, ["log", "-1", "--format=%H%x00%h%x00%s%x00%cI"])
    if not raw:
        return None
    parts = raw.split("\x00")
    if len(parts) != 4:
        return None
    return {
        "sha": parts[0],
        "shortSha": parts[1],
        "subject": parts[2],
        "committedAt": parts[3],
    }


def _git_ref_exists(repo_path: Path, ref: str) -> bool:
    if not ref:
        return False
    return _run_git(repo_path, ["rev-parse", "--verify", ref], timeout=8.0).returncode == 0


def _local_branch_exists(repo_path: Path, branch: str) -> bool:
    return _git_ref_exists(repo_path, f"refs/heads/{str(branch or '').strip()}")


def _remote_branch_exists(repo_path: Path, branch: str, remote: str = "origin") -> bool:
    name = str(branch or "").strip()
    if not name:
        return False
    return _git_ref_exists(repo_path, f"refs/remotes/{remote}/{name}")


def _comparison_ref(repo_path: Path, core_branch: str, upstream: str) -> str:
    remote_core = f"origin/{core_branch}"
    if _git_ref_exists(repo_path, remote_core):
        return remote_core
    if _git_ref_exists(repo_path, core_branch):
        return core_branch
    return upstream


def get_project_git_status(project_id: str) -> dict:
    project, repo_path = _project_repo_path(project_id)
    core_branch = str(project.get("coreBranch") or "main").strip() or "main"
    inside_work_tree = _git_stdout(repo_path, ["rev-parse", "--is-inside-work-tree"])
    if inside_work_tree != "true":
        return {
            "projectId": project.get("id") or project_id,
            "path": str(repo_path),
            "coreBranch": core_branch,
            "isGitRepo": False,
            "status": "not-git",
            "dirty": False,
            "hasUntrackedFiles": False,
            "ahead": 0,
            "behind": 0,
            "conflicts": 0,
            "files": [],
            "counts": {
                "files": 0,
                "staged": 0,
                "modified": 0,
                "deleted": 0,
                "renamed": 0,
                "untracked": 0,
                "conflicts": 0,
            },
        }

    repository_root = _git_stdout(repo_path, ["rev-parse", "--show-toplevel"]) or str(repo_path)
    branch = _git_stdout(repo_path, ["branch", "--show-current"]) or ""
    detached = False
    if not branch:
        detached = True
        branch = "HEAD"
    head_sha = _git_stdout(repo_path, ["rev-parse", "HEAD"]) or ""
    configured_upstream = _git_stdout(repo_path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]) or ""
    comparison_ref = _comparison_ref(repo_path, core_branch, configured_upstream)
    ahead = _parse_int(_git_stdout(repo_path, ["rev-list", "--count", f"{comparison_ref}..HEAD"])) if comparison_ref else 0
    behind = _parse_int(_git_stdout(repo_path, ["rev-list", "--count", f"HEAD..{comparison_ref}"])) if comparison_ref else 0
    status_output = _git_stdout(repo_path, _status_args(), timeout=6.0) or ""
    parsed = _parse_status_lines(status_output.splitlines())
    counts = parsed["counts"]
    operation_state = _git_operation_state(repo_path)
    dirty = counts["files"] > 0 or operation_state["operationInProgress"]
    conflicts = counts["conflicts"]
    state = "conflicts" if conflicts or operation_state["operationInProgress"] else "dirty" if dirty else "clean"

    return {
        "projectId": project.get("id") or project_id,
        "path": str(repo_path),
        "repositoryRoot": repository_root,
        "coreBranch": core_branch,
        "isGitRepo": True,
        "status": state,
        "branch": branch,
        "detached": detached,
        "headSha": head_sha,
        "headShortSha": head_sha[:12] if head_sha else "",
        "upstream": comparison_ref or configured_upstream,
        "configuredUpstream": configured_upstream,
        "ahead": ahead,
        "behind": behind,
        "dirty": dirty,
        "hasUntrackedFiles": counts["untracked"] > 0,
        "conflicts": conflicts,
        "counts": counts,
        "files": parsed["files"],
        "lastCommit": _last_commit(repo_path),
        **operation_state,
    }



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _git_failure_detail(result: subprocess.CompletedProcess) -> str:
    return (result.stderr or result.stdout or "").strip()[:1600]


_GIT_DETAIL_REDACTIONS = (
    re.compile(r"(?i)(token|api[_-]?key|secret|password|passwd|cookie)(\s*[=:]\s*)([^\s'\"]+)"),
    re.compile(r"(?i)(authorization:\s*(?:bearer|basic)\s+)([^\s'\"]+)"),
    re.compile(r"(?i)(https?://[^\s/:@]+:)([^\s/@]+)(@)"),
)


def _redact_git_detail(detail: str) -> str:
    value = str(detail or "")[:1600]
    if not value:
        return ""
    value = _GIT_DETAIL_REDACTIONS[0].sub(r"\1\2[REDACTED]", value)
    value = _GIT_DETAIL_REDACTIONS[1].sub(r"\1[REDACTED]", value)
    value = _GIT_DETAIL_REDACTIONS[2].sub(r"\1[REDACTED]\3", value)
    return value


def _conflict_files_from_status(status: dict) -> list[str]:
    files = []
    seen = set()
    for entry in status.get("files") or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "").strip()
        if not path or path in seen:
            continue
        if entry.get("kind") == "conflict" or "U" in str(entry.get("status") or ""):
            seen.add(path)
            files.append(path)
    return files


def _merge_conflict_detected(repo_path: Path, detail: str = "") -> bool:
    value = str(detail or "").lower()
    if "automatic merge failed" in value or "fix conflicts" in value or "conflict (" in value:
        return True
    try:
        status_output = _git_stdout(repo_path, _status_args(), timeout=8.0) or ""
        parsed = _parse_status_lines(status_output.splitlines())
        if int(parsed.get("counts", {}).get("conflicts") or 0) > 0:
            return True
    except Exception:
        pass
    try:
        return bool(_git_operation_state(repo_path).get("mergeInProgress"))
    except Exception:
        return False


def _git_conflict_handoff_operation(
    project_id: str,
    project: dict,
    repo_path: Path,
    reason: str,
    *,
    detail: str = "",
    attempted_merge: str = "",
    remote: str = "origin",
    remote_branch: str = "",
    operation_name: str = "push",
    body: dict | None = None,
) -> dict:
    status = get_project_git_status(project_id)
    conflict_files = _conflict_files_from_status(status)
    core_branch = str(status.get("coreBranch") or project.get("coreBranch") or "main").strip() or "main"
    conflict = {
        "projectId": str(project.get("id") or project_id),
        "reason": str(reason or "Project Git sync found conflicts."),
        "detail": _redact_git_detail(detail),
        "attemptedMerge": attempted_merge,
        "repositoryRoot": str(status.get("repositoryRoot") or repo_path),
        "coreBranch": core_branch,
        "branch": str(status.get("branch") or ""),
        "remote": str(remote or "origin"),
        "remoteBranch": str(remote_branch or core_branch),
        "files": conflict_files,
        "status": status,
    }
    try:
        handoff = ops_sessions.launch_project_git_conflict_session(project, conflict, body)
    except ops_sessions.OpsSessionError as exc:
        raise OpsGitError(
            f"Project Git sync found conflicts, but the conflict analysis session could not be started: {exc}",
            getattr(exc, "status", 409) or 409,
        ) from exc

    summary = "Project Git sync found merge conflicts. Started a conflict analysis session."
    if handoff.get("agentStartError"):
        summary += f" Open the session to continue; automatic start reported: {handoff['agentStartError']}"
    operation = _operation_record(
        str(project.get("id") or project_id),
        str(operation_name or "push").strip().lower() or "push",
        "blocked",
        summary,
        final_status=status,
    )
    operation["conflictHandoff"] = handoff
    operation["sessionId"] = handoff.get("sessionId")
    operation["sessionUrl"] = handoff.get("sessionUrl")
    operation["conflictFiles"] = conflict_files
    operation["error"] = conflict["reason"]
    return operation


def _remote_exists(repo_path: Path, remote: str) -> bool:
    result = _run_git(repo_path, ["remote", "get-url", remote], timeout=6.0)
    return result.returncode == 0 and bool(result.stdout.strip())


def _configured_upstream_parts(configured_upstream: str) -> tuple[str, str]:
    value = str(configured_upstream or "").strip()
    if not value or "/" not in value:
        return "", ""
    remote, branch = value.split("/", 1)
    return remote.strip(), branch.strip()


def _push_target(repo_path: Path, status: dict) -> tuple[str, str, bool]:
    remote, remote_branch = _configured_upstream_parts(str(status.get("configuredUpstream") or ""))
    branch = str(status.get("branch") or "").strip()
    if not branch or branch == "HEAD" or status.get("detached"):
        raise OpsGitError("Cannot push a detached HEAD from the project page.", 409)
    if remote and remote_branch:
        return remote, remote_branch, False
    if _remote_exists(repo_path, "origin"):
        return "origin", branch, True
    raise OpsGitError("No configured upstream or origin remote is available for this project.", 409)


def _core_branch_push_target(repo_path: Path, core_branch: str, status: dict) -> tuple[str, str, bool]:
    branch = str(core_branch or "").strip()
    if not branch:
        raise OpsGitError("Project core branch is unavailable.", 409)
    if not _remote_exists(repo_path, "origin"):
        raise OpsGitError("No origin remote is available for this project.", 409)
    upstream_remote, upstream_branch = _configured_upstream_parts(str(status.get("configuredUpstream") or ""))
    set_upstream = not (upstream_remote == "origin" and upstream_branch == branch)
    return "origin", branch, set_upstream


def _checked_git(repo_path: Path, args: list[str], *, timeout: float = 60.0) -> subprocess.CompletedProcess:
    result = _run_git_with_index_lock_recovery(repo_path, args, timeout=timeout)
    if result.returncode != 0:
        raise OpsGitError(_git_failure_detail(result) or f"Git {' '.join(args[:1] or ['operation'])} failed.", 409)
    return result


def _fetch_remote_tracking_branch(repo_path: Path, remote: str, branch: str) -> bool:
    result = _run_git_with_index_lock_recovery(
        repo_path,
        ["fetch", remote, f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}"],
        timeout=90.0,
    )
    if result.returncode == 0:
        return True
    detail = _git_failure_detail(result)
    if "couldn't find remote ref" in detail.lower():
        return False
    raise OpsGitError(detail or f"Git fetch from {remote}/{branch} failed.", 409)


def _merge_ref(repo_path: Path, ref: str, description: str) -> None:
    result = _run_git_with_index_lock_recovery(
        repo_path,
        [
            "-c",
            "user.name=Codex Terminal",
            "-c",
            "user.email=terminal@example.com",
            "merge",
            "--no-edit",
            ref,
        ],
        timeout=90.0,
    )
    if result.returncode == 0:
        return
    detail = _git_failure_detail(result)
    message = f"{description} could not be merged automatically."
    if _merge_conflict_detected(repo_path, detail):
        raise OpsGitMergeConflict(message, _redact_git_detail(detail))
    _run_git(repo_path, ["merge", "--abort"], timeout=30.0)
    if detail:
        message = f"{message}\n{_redact_git_detail(detail)}"
    raise OpsGitError(message, 409)


def _merge_remote_updates_if_needed(repo_path: Path, remote: str, branch: str) -> bool:
    if not _fetch_remote_tracking_branch(repo_path, remote, branch):
        return False
    remote_ref = f"{remote}/{branch}"
    behind = _parse_int(_git_stdout(repo_path, ["rev-list", "--count", f"HEAD..{remote_ref}"], timeout=8.0))
    if behind <= 0:
        return False
    _merge_ref(repo_path, remote_ref, f"Remote changes from {remote}/{branch}")
    return True


def _is_non_fast_forward_push_rejection(detail: str) -> bool:
    value = str(detail or "").lower()
    return (
        "fetch first" in value
        or "non-fast-forward" in value
        or ("failed to push some refs" in value and "updates were rejected" in value)
        or ("rejected" in value and "remote contains work" in value)
    )


def _push_head_with_recovery(repo_path: Path, push_args: list[str], remote: str, remote_branch: str) -> bool:
    result = _run_git_with_index_lock_recovery(repo_path, push_args, timeout=90.0)
    if result.returncode == 0:
        return False
    detail = _git_failure_detail(result)
    if _is_non_fast_forward_push_rejection(detail):
        merged_remote = _merge_remote_updates_if_needed(repo_path, remote, remote_branch)
        if merged_remote:
            retry = _run_git_with_index_lock_recovery(repo_path, push_args, timeout=90.0)
            if retry.returncode == 0:
                return True
            detail = _git_failure_detail(retry) or detail
    raise OpsGitError(detail or "Git push failed.", 409)


def _default_push_commit_message() -> str:
    return f"Sync changes from Codex Terminal ({_now_iso()})"


def _commit_project_changes_if_needed(repo_path: Path, commit_message: str | None) -> bool:
    status_output = _git_stdout(repo_path, _status_args(), timeout=8.0) or ""
    if not status_output.strip():
        return False
    _stage_project_changes(repo_path)
    message = str(commit_message or "").strip() or _default_push_commit_message()
    _checked_git(
        repo_path,
        [
            "-c",
            "user.name=Codex Terminal",
            "-c",
            "user.email=terminal@example.com",
            "commit",
            "-m",
            message,
        ],
        timeout=90.0,
    )
    return True


def _ensure_local_core_branch(repo_path: Path, core_branch: str) -> None:
    branch = str(core_branch or "").strip()
    if not branch:
        raise OpsGitError("Project core branch is unavailable.", 409)
    if _local_branch_exists(repo_path, branch):
        return
    if not _remote_branch_exists(repo_path, branch):
        _fetch_remote_tracking_branch(repo_path, "origin", branch)
    if _remote_branch_exists(repo_path, branch):
        _checked_git(repo_path, ["checkout", "-B", branch, f"origin/{branch}"], timeout=30.0)
        return
    raise OpsGitError(f'Core branch "{branch}" does not exist on origin.', 409)


def _operation_record(project_id: str, operation: str, status: str, summary: str, *, final_status: dict | None = None) -> dict:
    return {
        "id": f"git-{operation}-{uuid.uuid4().hex[:12]}",
        "projectId": project_id,
        "operation": operation,
        "status": status,
        "summary": summary,
        "createdAt": _now_iso(),
        "updatedAt": _now_iso(),
        "finalStatus": final_status,
    }


def _execute_project_push(project_id: str, body: dict | None = None, operation_name: str = "push") -> dict:
    project, repo_path = _project_repo_path(project_id)
    lock = _repo_operation_lock(repo_path)
    if not lock.acquire(timeout=180.0):
        raise OpsGitError("Another project Git operation is still running. Try again when it finishes.", 409)
    try:
        return _execute_project_push_locked(project_id, project, repo_path, body, operation_name=operation_name)
    finally:
        lock.release()


def _execute_project_push_locked(
    project_id: str,
    project: dict,
    repo_path: Path,
    body: dict | None = None,
    operation_name: str = "push",
) -> dict:
    operation_name = str(operation_name or "push").strip().lower() or "push"
    index_lock_removed = _clear_stale_git_index_lock(repo_path)
    status = get_project_git_status(project_id)
    if not status.get("isGitRepo"):
        raise OpsGitError("Project path is not inside a Git repository.", 409)
    current_branch = str(status.get("branch") or "").strip()
    core_branch = str(status.get("coreBranch") or project.get("coreBranch") or current_branch or "main").strip() or "main"
    remote = "origin"
    remote_branch = core_branch
    if status.get("operationInProgress") or int(status.get("conflicts") or 0) > 0:
        return _git_conflict_handoff_operation(
            project_id,
            project,
            repo_path,
            "Existing Git conflicts or an in-progress Git operation must be resolved before the project Git operation can finish.",
            attempted_merge="existing repository conflict state",
            remote=remote,
            remote_branch=remote_branch,
            operation_name=operation_name,
            body=body,
        )
    if not current_branch or current_branch == "HEAD" or status.get("detached"):
        raise OpsGitError("Cannot push a detached HEAD from the project page.", 409)

    try:
        commit_message = str((body or {}).get("message") or "").strip() or _default_push_commit_message()
        committed_changes = False
        if bool(status.get("dirty")):
            committed_changes = _commit_project_changes_if_needed(repo_path, commit_message)
            status = get_project_git_status(project_id)

        merged_branch = ""
        merged_remote = False
        remote, remote_branch, set_upstream = _core_branch_push_target(repo_path, core_branch, status)
        if current_branch != core_branch:
            _ensure_local_core_branch(repo_path, core_branch)
            if str(status.get("branch") or "").strip() != core_branch:
                _checked_git(repo_path, ["checkout", core_branch], timeout=30.0)
            status = get_project_git_status(project_id)
            remote, remote_branch, set_upstream = _core_branch_push_target(repo_path, core_branch, status)
            merged_remote = _merge_remote_updates_if_needed(repo_path, remote, remote_branch)
            _merge_ref(repo_path, current_branch, f"Branch {current_branch}")
            merged_branch = current_branch
            status = get_project_git_status(project_id)
        else:
            merged_remote = _merge_remote_updates_if_needed(repo_path, remote, remote_branch)
            if merged_remote:
                status = get_project_git_status(project_id)

        ahead = int(status.get("ahead") or 0)
        if ahead <= 0 and not committed_changes and not merged_branch:
            if not merged_remote:
                raise OpsGitError("This project has no committed changes to push.", 409)
            task_updates = {"updatedCount": 0, "updatedTaskIds": []}
            pushed = False
        else:
            push_args = ["push"]
            if set_upstream:
                push_args.append("-u")
            push_args.extend([remote, f"HEAD:refs/heads/{remote_branch}"])
            if _push_head_with_recovery(repo_path, push_args, remote, remote_branch):
                merged_remote = True
            task_updates = ops_projects.promote_not_synced_tasks_to_ready_for_test(str(project.get("id") or project_id))
            pushed = True
    except OpsGitMergeConflict as exc:
        return _git_conflict_handoff_operation(
            project_id,
            project,
            repo_path,
            exc.description,
            detail=exc.detail,
            attempted_merge=exc.description,
            remote=remote,
            remote_branch=remote_branch,
            operation_name=operation_name,
            body=body,
        )

    final_status = get_project_git_status(project_id)
    summary_parts: list[str] = []
    if index_lock_removed:
        summary_parts.append("Removed stale Git index lock.")
    if committed_changes:
        summary_parts.append("Committed local changes.")
    if merged_remote:
        summary_parts.append(f"Merged remote changes from {remote}/{remote_branch}.")
    if merged_branch:
        summary_parts.append(f"Merged {merged_branch} into {core_branch}.")
    if pushed:
        summary_parts.append(f"Pushed {core_branch} to {remote}/{remote_branch}.")
    else:
        summary_parts.append(f"No local changes needed pushing after syncing {remote}/{remote_branch}.")
    if int(task_updates.get("updatedCount") or 0) > 0:
        count = int(task_updates["updatedCount"])
        summary_parts.append(f"Marked {count} task{'s' if count != 1 else ''} ready for test.")
    summary = " ".join(summary_parts)
    operation = _operation_record(
        str(project.get("id") or project_id),
        operation_name,
        "succeeded",
        summary,
        final_status=final_status,
    )
    operation["taskUpdates"] = int(task_updates.get("updatedCount") or 0)
    operation["readyForTestTaskIds"] = list(task_updates.get("updatedTaskIds") or [])
    return operation


def execute_project_git_operation(project_id: str, operation: str, body: dict | None = None) -> dict:
    op = str(operation or "").strip().lower()
    confirm = str((body or {}).get("confirm") or "").strip().lower()
    if op not in {"push", "sync"}:
        raise OpsGitError("Unsupported Git operation.", 404)
    if confirm and confirm != op:
        raise OpsGitError("Git operation confirmation did not match the requested operation.", 400)
    if op in {"push", "sync"}:
        return _execute_project_push(project_id, body, operation_name=op)
    raise OpsGitError("Unsupported Git operation.", 404)

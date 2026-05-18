"""Fork-owned project git status helpers for the clean restart branch."""

from __future__ import annotations

import base64
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from api import ops_projects


STATUS_EXCLUDED_PATHS = [".cloud-terminal", ".hermes", "project_tasks", "project_tasks.json"]
TOKEN_ENV_NAMES = ("HERMES_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")
GITHUB_HTTP_EXTRAHEADER_CONFIG_KEY = "http.https://github.com/.extraheader"


class OpsGitError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


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


def _git_stdout(repo_path: Path, args: list[str], *, timeout: float = 4.0) -> str | None:
    result = _run_git(repo_path, args, timeout=timeout)
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
    result = _run_git(repo_path, args, timeout=timeout)
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
    result = _run_git(repo_path, args, timeout=timeout)
    if result.returncode != 0:
        raise OpsGitError(_git_failure_detail(result) or f"Git {' '.join(args[:1] or ['operation'])} failed.", 409)
    return result


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


def _execute_project_push(project_id: str, body: dict | None = None) -> dict:
    project, repo_path = _project_repo_path(project_id)
    status = get_project_git_status(project_id)
    if not status.get("isGitRepo"):
        raise OpsGitError("Project path is not inside a Git repository.", 409)
    if status.get("operationInProgress") or int(status.get("conflicts") or 0) > 0:
        raise OpsGitError("Resolve the in-progress Git operation or conflicts before pushing.", 409)
    current_branch = str(status.get("branch") or "").strip()
    core_branch = str(status.get("coreBranch") or project.get("coreBranch") or current_branch or "main").strip() or "main"
    if int(status.get("behind") or 0) > 0:
        raise OpsGitError("This branch is behind its sync target. Sync before pushing.", 409)
    if not current_branch or current_branch == "HEAD" or status.get("detached"):
        raise OpsGitError("Cannot push a detached HEAD from the project page.", 409)

    commit_message = str((body or {}).get("message") or "").strip() or _default_push_commit_message()
    committed_changes = False
    if bool(status.get("dirty")):
        committed_changes = _commit_project_changes_if_needed(repo_path, commit_message)
        status = get_project_git_status(project_id)

    merged_branch = ""
    if current_branch != core_branch:
        _ensure_local_core_branch(repo_path, core_branch)
        if str(status.get("branch") or "").strip() != core_branch:
            _checked_git(repo_path, ["checkout", core_branch], timeout=30.0)
        _checked_git(repo_path, ["merge", current_branch], timeout=90.0)
        merged_branch = current_branch
        status = get_project_git_status(project_id)

    ahead = int(status.get("ahead") or 0)
    if ahead <= 0 and not committed_changes and not merged_branch:
        raise OpsGitError("This project has no committed changes to push.", 409)

    remote, remote_branch, set_upstream = _core_branch_push_target(repo_path, core_branch, status)
    push_args = ["push"]
    if set_upstream:
        push_args.append("-u")
    push_args.extend([remote, f"HEAD:refs/heads/{remote_branch}"])
    _checked_git(repo_path, push_args, timeout=90.0)
    task_updates = ops_projects.promote_not_synced_tasks_to_ready_for_test(str(project.get("id") or project_id))
    final_status = get_project_git_status(project_id)
    summary_parts: list[str] = []
    if committed_changes:
        summary_parts.append("Committed local changes.")
    if merged_branch:
        summary_parts.append(f"Merged {merged_branch} into {core_branch}.")
    summary_parts.append(f"Pushed {core_branch} to {remote}/{remote_branch}.")
    if int(task_updates.get("updatedCount") or 0) > 0:
        count = int(task_updates["updatedCount"])
        summary_parts.append(f"Marked {count} task{'s' if count != 1 else ''} ready for test.")
    summary = " ".join(summary_parts)
    operation = _operation_record(
        str(project.get("id") or project_id),
        "push",
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
    if op == "push":
        return _execute_project_push(project_id, body)
    raise OpsGitError("Project-page sync is not available from this endpoint yet. Use the upstream sync review flow before pushing.", 501)

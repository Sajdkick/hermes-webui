"""Fork-owned project git status helpers for the clean restart branch."""

from __future__ import annotations

import subprocess
from pathlib import Path

from api import ops_projects


STATUS_EXCLUDED_PATHS = [".hermes", "project_tasks", "project_tasks.json"]


class OpsGitError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _run_git(repo_path: Path, args: list[str], *, timeout: float = 4.0) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(repo_path),
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

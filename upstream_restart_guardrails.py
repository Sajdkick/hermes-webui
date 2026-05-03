from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


HOTSPOT_FILES = [
    "api/routes.py",
    "api/models.py",
    "api/streaming.py",
    "api/config.py",
    "api/profiles.py",
    "static/ui.js",
    "static/messages.js",
    "static/sessions.js",
    "static/panels.js",
    "static/boot.js",
    "static/index.html",
    "static/style.css",
]

PREFERRED_BUDGET = 20
HARD_BUDGET = 50
DEFAULT_BASE_REFS = (
    "upstream/master",
    "upstream/main",
    "origin/master",
    "origin/main",
    "master",
    "main",
)


class RestartGuardrailError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _run_git(args: list[str], cwd: Path, *, timeout: int = 15) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RestartGuardrailError("git is not available in this environment.", 500) from exc
    except subprocess.TimeoutExpired as exc:
        raise RestartGuardrailError(f"git {' '.join(args)} timed out after {timeout}s.", 504) from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RestartGuardrailError(detail or f"git {' '.join(args)} failed.", 502)
    return completed.stdout.strip()


def _repo_root(repo_path: Path | None = None) -> Path:
    candidate = Path(repo_path or Path.cwd()).expanduser().resolve()
    try:
        root = _run_git(["rev-parse", "--show-toplevel"], candidate, timeout=10)
    except RestartGuardrailError as exc:
        raise RestartGuardrailError("This checkout is not a Git repository.", 409) from exc
    return Path(root).expanduser().resolve()


def _try_rev_parse(repo_root: Path, ref: str) -> str:
    try:
        return _run_git(["rev-parse", "--verify", ref], repo_root, timeout=10)
    except RestartGuardrailError:
        return ""


def _resolve_base_ref(repo_root: Path, preferred_base_ref: str) -> tuple[str, bool]:
    candidates = [preferred_base_ref, *DEFAULT_BASE_REFS]
    seen = set()
    for ref in candidates:
        if ref in seen:
            continue
        seen.add(ref)
        if _try_rev_parse(repo_root, ref):
            return ref, ref != preferred_base_ref
    raise RestartGuardrailError(
        "Could not resolve a restart baseline ref. Expected upstream/master or another default branch ref.",
        409,
    )


def _budget_status(total: int) -> str:
    if total <= 0:
        return "clean"
    if total <= PREFERRED_BUDGET:
        return "within-budget"
    if total <= HARD_BUDGET:
        return "needs-justification"
    return "review-required"


def _parse_numstat(raw: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added = parts[0].strip()
        deleted = parts[1].strip()
        path = "\t".join(parts[2:]).strip()
        binary = added == "-" or deleted == "-"
        insertions = 0 if binary else int(added or "0")
        deletions = 0 if binary else int(deleted or "0")
        total = insertions + deletions
        rows.append(
            {
                "path": path,
                "insertions": insertions,
                "deletions": deletions,
                "total": total,
                "binary": binary,
                "budgetStatus": _budget_status(total),
            }
        )
    rows.sort(key=lambda row: (-int(row.get("total") or 0), str(row.get("path") or "")))
    return rows


def _diff_numstat(repo_root: Path, diff_args: list[str]) -> list[dict[str, Any]]:
    raw = _run_git(
        ["diff", "--numstat", *diff_args, "--", *HOTSPOT_FILES],
        repo_root,
        timeout=15,
    )
    return _parse_numstat(raw)


def _summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "changed": 0,
        "withinBudget": 0,
        "needsJustification": 0,
        "reviewRequired": 0,
        "totalLines": 0,
    }
    for row in rows:
        total = int(row.get("total") or 0)
        if total <= 0:
            continue
        summary["changed"] += 1
        summary["totalLines"] += total
        status = row.get("budgetStatus")
        if status == "review-required":
            summary["reviewRequired"] += 1
        elif status == "needs-justification":
            summary["needsJustification"] += 1
        else:
            summary["withinBudget"] += 1
    return summary


def _report_status(base_ref: str, branch_counts: dict[str, int], working_tree_counts: dict[str, int], fallback: bool) -> tuple[str, str]:
    review_required = int(branch_counts.get("reviewRequired") or 0) + int(working_tree_counts.get("reviewRequired") or 0)
    needs_justification = int(branch_counts.get("needsJustification") or 0) + int(working_tree_counts.get("needsJustification") or 0)
    if review_required:
        return "blocked", f"{review_required} hotspot file(s) exceed the hard restart budget against {base_ref}."
    if needs_justification or fallback:
        detail = []
        if int(branch_counts.get("changed") or 0):
            detail.append(f"{branch_counts['changed']} committed hotspot file(s)")
        if int(working_tree_counts.get("changed") or 0):
            detail.append(f"{working_tree_counts['changed']} working-tree hotspot file(s)")
        message = ", ".join(detail) if detail else "No hotspot churn"
        if fallback:
            message += f"; using fallback baseline ref {base_ref}"
        return "warning", f"{message} exceed the preferred restart budget."
    return "ready", f"Hotspot churn stays within the restart budget against {base_ref}."


def get_restart_guardrails(repo_path: str | Path | None = None, *, preferred_base_ref: str = "upstream/master") -> dict[str, Any]:
    repo_root = _repo_root(Path(repo_path) if repo_path is not None else None)
    base_ref, fallback_base_ref = _resolve_base_ref(repo_root, preferred_base_ref)
    merge_base = _run_git(["merge-base", base_ref, "HEAD"], repo_root, timeout=10)
    branch_hotspots = _diff_numstat(repo_root, [f"{merge_base}..HEAD"])
    working_tree_hotspots = _diff_numstat(repo_root, ["HEAD"])
    branch_counts = _summarize(branch_hotspots)
    working_tree_counts = _summarize(working_tree_hotspots)
    status, summary = _report_status(base_ref, branch_counts, working_tree_counts, fallback_base_ref)
    return {
        "status": status,
        "summary": summary,
        "repoPath": str(repo_root),
        "preferredBaseRef": preferred_base_ref,
        "baseRef": base_ref,
        "fallbackBaseRef": fallback_base_ref,
        "mergeBase": merge_base,
        "preferredBudget": PREFERRED_BUDGET,
        "hardBudget": HARD_BUDGET,
        "branchHotspots": branch_hotspots,
        "workingTreeHotspots": working_tree_hotspots,
        "branchCounts": branch_counts,
        "workingTreeCounts": working_tree_counts,
    }


def _status_rank(status: str) -> int:
    normalized = str(status or "").strip().lower()
    if normalized == "blocked":
        return 2
    if normalized == "warning":
        return 1
    return 0


def _print_text_report(report: dict[str, Any]) -> None:
    print(f"Restart guardrails: {report['status']} - {report['summary']}")
    print(
        "Budget: "
        f"preferred<={report['preferredBudget']} lines, "
        f"hard<={report['hardBudget']} lines, "
        f"base={report['baseRef']}, "
        f"merge-base={report['mergeBase']}"
    )
    print(
        "Branch hotspot counts: "
        f"changed={report['branchCounts']['changed']}, "
        f"needs-justification={report['branchCounts']['needsJustification']}, "
        f"review-required={report['branchCounts']['reviewRequired']}"
    )
    print(
        "Working tree hotspot counts: "
        f"changed={report['workingTreeCounts']['changed']}, "
        f"needs-justification={report['workingTreeCounts']['needsJustification']}, "
        f"review-required={report['workingTreeCounts']['reviewRequired']}"
    )
    for label, rows in (
        ("Committed hotspot churn", report["branchHotspots"]),
        ("Working tree hotspot churn", report["workingTreeHotspots"]),
    ):
        print(f"{label}:")
        if not rows:
            print("  (none)")
            continue
        for row in rows:
            print(
                "  "
                f"{row['path']}: +{row['insertions']} / -{row['deletions']} "
                f"({row['total']} lines, {row['budgetStatus']})"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report restart hotspot churn against upstream.")
    parser.add_argument("--repo", default=".", help="Path to the Git repository to inspect.")
    parser.add_argument("--base-ref", default="upstream/master", help="Preferred upstream baseline ref.")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    parser.add_argument(
        "--fail-on",
        choices=("never", "warning", "blocked"),
        default="never",
        help="Exit nonzero when the report status meets or exceeds this threshold.",
    )
    args = parser.parse_args(argv)
    try:
        report = get_restart_guardrails(args.repo, preferred_base_ref=args.base_ref)
    except RestartGuardrailError as exc:
        print(str(exc), file=sys.stderr)
        return exc.status if exc.status >= 1 else 1
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_text_report(report)
    if args.fail_on != "never" and _status_rank(report["status"]) >= _status_rank(args.fail_on):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

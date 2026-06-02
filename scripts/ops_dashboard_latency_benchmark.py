#!/usr/bin/env python3
"""Measure Ops dashboard menu/poll path latency and state cardinality.

This is a lightweight developer diagnostic for the Cloud Terminal-style Ops
menu. It intentionally times the same public helper functions used by the UI so
before/after optimization work can be compared with one command:

    /usr/bin/python3 scripts/ops_dashboard_latency_benchmark.py --repeat 3

The rich helper calls may perform the same reconciliation/enrichment work the UI
currently performs. Run against isolated state when investigating behavior that
might mutate local run/session lifecycle state.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _safe_call(fn: Callable[[], Any]) -> tuple[Any, str | None]:
    try:
        return fn(), None
    except Exception as exc:  # pragma: no cover - diagnostic path
        return None, f"{type(exc).__name__}: {exc}"


def _time_call(fn: Callable[[], Any], repeat: int) -> dict[str, Any]:
    durations: list[float] = []
    last_result: Any = None
    error: str | None = None
    for _ in range(max(1, repeat)):
        start = time.perf_counter()
        result, error = _safe_call(fn)
        durations.append((time.perf_counter() - start) * 1000.0)
        last_result = result
        if error:
            break
    payload: dict[str, Any] = {
        "runs": len(durations),
        "ms": {
            "min": round(min(durations), 2),
            "max": round(max(durations), 2),
            "avg": round(statistics.fmean(durations), 2),
        },
    }
    if len(durations) > 1:
        payload["ms"]["median"] = round(statistics.median(durations), 2)
    if error:
        payload["error"] = error
    if isinstance(last_result, dict):
        for key in ("count", "sessionCount", "projectCount"):
            if key in last_result:
                payload[key] = last_result.get(key)
        for key, count_key in (
            ("projects", "projectCount"),
            ("sessions", "sessionCount"),
            ("runs", "runCount"),
            ("notifications", "notificationCount"),
        ):
            if isinstance(last_result.get(key), list):
                payload[count_key] = len(last_result.get(key) or [])
    return payload


def _count_state() -> dict[str, Any]:
    from api.config import STATE_DIR
    from api import ops_projects, ops_runs
    from api.models import all_sessions

    projects_payload, projects_error = _safe_call(ops_projects.list_ops_projects)
    sessions_payload, sessions_error = _safe_call(all_sessions)

    raw_runs: list[dict] = []
    runs_error: str | None = None
    try:
        lock = getattr(ops_runs, "_LOCK", None)
        if lock is not None:
            with lock:
                raw_runs = list(ops_runs._read_runs())
        else:
            raw_runs = list(ops_runs._read_runs())
    except Exception as exc:  # pragma: no cover - diagnostic path
        runs_error = f"{type(exc).__name__}: {exc}"

    sidecar_dir = STATE_DIR / "ops" / "session-links"
    sidecars = list(sidecar_dir.glob("*.json")) if sidecar_dir.exists() else []

    task_files: set[Path] = set()
    for project in (projects_payload or {}).get("projects", []) if isinstance(projects_payload, dict) else []:
        if not isinstance(project, dict):
            continue
        root_value = str(project.get("resolvedPath") or project.get("path") or "").strip()
        if not root_value:
            continue
        root = Path(root_value).expanduser()
        task_files.update((root / "project_tasks").glob("*.json")) if (root / "project_tasks").exists() else None
        legacy = root / "project_tasks.json"
        if legacy.exists():
            task_files.add(legacy)

    task_file_sizes = []
    for path in task_files:
        try:
            task_file_sizes.append(path.stat().st_size)
        except OSError:
            pass

    counts: dict[str, Any] = {
        "stateDir": str(STATE_DIR),
        "projectCount": len((projects_payload or {}).get("projects", [])) if isinstance(projects_payload, dict) else 0,
        "visibleSessionCount": len(sessions_payload or []) if isinstance(sessions_payload, list) else 0,
        "rawRunCount": len(raw_runs),
        "sidecarCount": len(sidecars),
        "sidecarBytes": sum(path.stat().st_size for path in sidecars if path.exists()),
        "taskFileCount": len(task_file_sizes),
        "taskFileBytes": sum(task_file_sizes),
        "largestTaskFileBytes": max(task_file_sizes) if task_file_sizes else 0,
    }
    errors = {
        "projects": projects_error,
        "sessions": sessions_error,
        "runs": runs_error,
    }
    counts["errors"] = {key: value for key, value in errors.items() if value}
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=1, help="times to run each measured helper")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a readable table")
    args = parser.parse_args()

    from api import ops_notifications, ops_projects, ops_runs, ops_sessions, session_activity
    from api.models import all_sessions

    measurements = {
        "ops_projects.list_ops_project_summaries": _time_call(ops_projects.list_ops_project_summaries, args.repeat),
        "ops_projects.list_ops_projects": _time_call(ops_projects.list_ops_projects, args.repeat),
        "models.all_sessions": _time_call(lambda: {"sessions": all_sessions()}, args.repeat),
        "ops_runs.list_ops_run_summaries": _time_call(lambda: ops_runs.list_ops_run_summaries({}), args.repeat),
        "ops_runs.list_ops_runs": _time_call(lambda: ops_runs.list_ops_runs({}), args.repeat),
        "ops_notifications.list_pending_notifications": _time_call(ops_notifications.list_pending_notifications, args.repeat),
        "session_activity.list_session_activity": _time_call(session_activity.list_session_activity, args.repeat),
        "ops_sessions.list_ops_sessions": _time_call(ops_sessions.list_ops_sessions, args.repeat),
    }
    payload = {
        "repeat": max(1, args.repeat),
        "counts": _count_state(),
        "measurements": measurements,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print("Ops dashboard latency benchmark")
    print("================================")
    counts = payload["counts"]
    print(f"stateDir: {counts['stateDir']}")
    for key in (
        "projectCount",
        "visibleSessionCount",
        "rawRunCount",
        "sidecarCount",
        "taskFileCount",
        "taskFileBytes",
        "largestTaskFileBytes",
    ):
        print(f"{key}: {counts.get(key)}")
    if counts.get("errors"):
        print(f"countErrors: {counts['errors']}")
    print()
    print(f"{'operation':48} {'avg ms':>10} {'min':>10} {'max':>10} details")
    print("-" * 100)
    for name, item in measurements.items():
        ms = item.get("ms", {})
        details = []
        for key in ("projectCount", "sessionCount", "runCount", "notificationCount", "count"):
            if key in item:
                details.append(f"{key}={item[key]}")
        if item.get("error"):
            details.append(f"error={item['error']}")
        print(f"{name:48} {ms.get('avg', 0):10.2f} {ms.get('min', 0):10.2f} {ms.get('max', 0):10.2f} {' '.join(details)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fork-owned runtime summary helpers for the clean restart branch."""

from __future__ import annotations

from api import core_play, ops_guides, ops_projects, ops_runtime_inspect


def runtime_capabilities() -> dict:
    return {
        "gatherReports": {"available": True, "label": "Gather reports"},
        "reviewRequests": {"available": True, "label": "Review requests"},
        "snapshot": {
            "available": True,
            "label": "Runtime snapshot",
            "reason": "Inspect URL resolution and reset-state endpoints are available on the clean branch.",
        },
        "screenshot": {
            "available": True,
            "label": "Runtime screenshot",
            "reason": "Hermes runtime-backed screenshot capture is available through fork-owned endpoints.",
        },
        "actions": {
            "available": True,
            "label": "Runtime actions",
            "reason": "Hermes runtime-backed scripted inspect actions are available through fork-owned endpoints.",
        },
        "play": {
            "available": True,
            "label": "Play workflow",
            "reason": "Play config, status, logs, start, stop, restart, and proxy endpoints are available on the clean branch.",
        },
    }


def get_runtime_summary(project_id: str) -> dict:
    project = ops_projects.get_ops_project(project_id)
    gather = ops_guides.list_gather_reports(project["id"], {"limit": 3})
    reviews = ops_guides.list_review_requests(project["id"], {"limit": 3})
    play_status = core_play.get_project_play_status(project["id"])
    snapshot = ops_runtime_inspect.get_latest_snapshot(project["id"])["snapshot"]
    screenshot = ops_runtime_inspect.get_latest_screenshot(project["id"])["screenshot"]
    action = ops_runtime_inspect.get_latest_action(project["id"])["action"]
    return {
        "projectId": project["id"],
        "capabilities": runtime_capabilities(),
        "gather": {
            "count": gather["count"],
            "reports": gather["reports"],
            "latest": gather["reports"][0] if gather["reports"] else None,
        },
        "reviews": {
            "count": reviews["count"],
            "reviews": reviews["reviews"],
            "latest": reviews["reviews"][0] if reviews["reviews"] else None,
        },
        "snapshot": snapshot,
        "screenshot": screenshot,
        "actions": action,
        "play": play_status,
    }

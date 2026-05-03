"""Fork-owned runtime summary helpers for the clean restart branch."""

from __future__ import annotations

from api import ops_guides, ops_projects, play_pipeline


def runtime_capabilities() -> dict:
    return {
        "gatherReports": {"available": True, "label": "Gather reports"},
        "reviewRequests": {"available": True, "label": "Review requests"},
        "snapshot": {
            "available": False,
            "label": "Runtime snapshot",
            "reason": "Runtime snapshot endpoints are not ported on the clean branch yet.",
        },
        "screenshot": {
            "available": False,
            "label": "Runtime screenshot",
            "reason": "Runtime screenshot endpoints are not ported on the clean branch yet.",
        },
        "actions": {
            "available": False,
            "label": "Runtime actions",
            "reason": "Runtime action endpoints are not ported on the clean branch yet.",
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
    play_status = play_pipeline.build_project_play_status(project["id"])
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
        "play": play_status,
    }

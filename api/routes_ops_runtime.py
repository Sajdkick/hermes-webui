"""Fork-owned runtime evidence routes for the clean restart branch."""

from __future__ import annotations

import re
from urllib.parse import parse_qs

from api.helpers import j
from api import ops_guides, ops_projects, ops_runtime_tools


_RUNTIME_SUMMARY_RE = re.compile(r"^/api/ops/projects/([^/]+)/runtime/summary/?$")
_RUNTIME_CAPABILITIES_RE = re.compile(r"^/api/ops/projects/([^/]+)/runtime/capabilities/?$")
_GATHER_REPORTS_RE = re.compile(r"^/api/ops/projects/([^/]+)/runtime/gather/reports/?$")
_GATHER_REPORT_LATEST_RE = re.compile(r"^/api/ops/projects/([^/]+)/runtime/gather/reports/latest/?$")
_GATHER_REPORT_RE = re.compile(r"^/api/ops/projects/([^/]+)/runtime/gather/reports/([^/]+)/?$")
_GATHER_REPORT_EVENTS_RE = re.compile(r"^/api/ops/projects/([^/]+)/runtime/gather/reports/([^/]+)/events/?$")
_REVIEWS_RE = re.compile(r"^/api/ops/projects/([^/]+)/runtime/inspect/reviews/?$")
_REVIEW_LATEST_RE = re.compile(r"^/api/ops/projects/([^/]+)/runtime/inspect/reviews/latest/?$")
_REVIEW_RE = re.compile(r"^/api/ops/projects/([^/]+)/runtime/inspect/reviews/([^/]+)/?$")
_REVIEW_COMPLETE_RE = re.compile(r"^/api/ops/projects/([^/]+)/runtime/inspect/reviews/([^/]+)/complete/?$")


def _filters(parsed) -> dict:
    return {key: values[0] for key, values in parse_qs(parsed.query).items() if values}


def handle_get(handler, parsed) -> bool:
    try:
        match = _RUNTIME_SUMMARY_RE.match(parsed.path)
        if match:
            j(handler, ops_runtime_tools.get_runtime_summary(match.group(1)))
            return True

        match = _RUNTIME_CAPABILITIES_RE.match(parsed.path)
        if match:
            ops_projects.get_ops_project(match.group(1))
            j(handler, {"projectId": match.group(1), "capabilities": ops_runtime_tools.runtime_capabilities()})
            return True

        match = _GATHER_REPORT_LATEST_RE.match(parsed.path)
        if match:
            j(handler, ops_guides.get_latest_gather_report(match.group(1)))
            return True

        match = _GATHER_REPORT_RE.match(parsed.path)
        if match:
            j(handler, ops_guides.get_gather_report(match.group(1), match.group(2)))
            return True

        match = _GATHER_REPORTS_RE.match(parsed.path)
        if match:
            j(handler, ops_guides.list_gather_reports(match.group(1), _filters(parsed)))
            return True

        match = _REVIEW_LATEST_RE.match(parsed.path)
        if match:
            j(handler, ops_guides.get_latest_review_request(match.group(1)))
            return True

        match = _REVIEW_RE.match(parsed.path)
        if match:
            j(handler, ops_guides.get_review_request(match.group(1), match.group(2)))
            return True

        match = _REVIEWS_RE.match(parsed.path)
        if match:
            j(handler, ops_guides.list_review_requests(match.group(1), _filters(parsed)))
            return True

        return False
    except (ops_guides.OpsGuideError, ops_projects.OpsProjectError) as exc:
        j(handler, {"error": str(exc)}, status=exc.status)
        return True


def handle_post(handler, parsed, body: dict) -> bool:
    try:
        match = _GATHER_REPORTS_RE.match(parsed.path)
        if match:
            j(handler, ops_guides.create_gather_report(match.group(1), body), status=201)
            return True

        match = _GATHER_REPORT_EVENTS_RE.match(parsed.path)
        if match:
            j(handler, ops_guides.append_gather_report_event(match.group(1), match.group(2), body))
            return True

        match = _REVIEWS_RE.match(parsed.path)
        if match:
            j(handler, ops_guides.create_review_request(match.group(1), body), status=201)
            return True

        match = _REVIEW_COMPLETE_RE.match(parsed.path)
        if match:
            j(handler, ops_guides.complete_review_request(match.group(1), match.group(2), body))
            return True

        return False
    except (ops_guides.OpsGuideError, ops_projects.OpsProjectError) as exc:
        j(handler, {"error": str(exc)}, status=exc.status)
        return True

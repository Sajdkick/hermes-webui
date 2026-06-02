"""Core API runtime inspect/gather facade."""

from __future__ import annotations

from api import ops_guides, ops_projects, ops_runtime_inspect, ops_runtime_tools
from api.core_contracts import coerce_core_error, redact_payload

RuntimeCoreError = ops_runtime_inspect.OpsRuntimeInspectError


def runtime_capabilities(project_id: str = "") -> dict:
    try:
        if project_id:
            ops_projects.get_ops_project(project_id)
        return redact_payload({"projectId": project_id, "capabilities": ops_runtime_tools.runtime_capabilities()})
    except ops_projects.OpsProjectError as exc:
        raise coerce_core_error(exc, code="RUNTIME_PROJECT_ERROR") from exc


def runtime_summary(project_id: str) -> dict:
    try:
        return redact_payload(ops_runtime_tools.get_runtime_summary(project_id))
    except (ops_guides.OpsGuideError, ops_runtime_inspect.OpsRuntimeInspectError, ops_projects.OpsProjectError) as exc:
        raise coerce_core_error(exc, code="RUNTIME_ERROR") from exc


def list_gather_reports(project_id: str, filters=None):
    try: return redact_payload(ops_guides.list_gather_reports(project_id, filters or {}))
    except ops_guides.OpsGuideError as exc: raise coerce_core_error(exc, code="RUNTIME_GATHER_ERROR") from exc

def get_gather_report(project_id: str, report_id: str):
    try: return redact_payload(ops_guides.get_gather_report(project_id, report_id))
    except ops_guides.OpsGuideError as exc: raise coerce_core_error(exc, code="RUNTIME_GATHER_ERROR") from exc

def get_latest_gather_report(project_id: str):
    try: return redact_payload(ops_guides.get_latest_gather_report(project_id))
    except ops_guides.OpsGuideError as exc: raise coerce_core_error(exc, code="RUNTIME_GATHER_ERROR") from exc

def create_gather_report(project_id: str, body=None):
    try: return redact_payload(ops_guides.create_gather_report(project_id, body or {}))
    except ops_guides.OpsGuideError as exc: raise coerce_core_error(exc, code="RUNTIME_GATHER_ERROR") from exc

def append_gather_report_event(project_id: str, report_id: str, body=None):
    try: return redact_payload(ops_guides.append_gather_report_event(project_id, report_id, body or {}))
    except ops_guides.OpsGuideError as exc: raise coerce_core_error(exc, code="RUNTIME_GATHER_ERROR") from exc

def list_review_requests(project_id: str, filters=None):
    try: return redact_payload(ops_guides.list_review_requests(project_id, filters or {}))
    except ops_guides.OpsGuideError as exc: raise coerce_core_error(exc, code="RUNTIME_REVIEW_ERROR") from exc

def get_review_request(project_id: str, review_id: str):
    try: return redact_payload(ops_guides.get_review_request(project_id, review_id))
    except ops_guides.OpsGuideError as exc: raise coerce_core_error(exc, code="RUNTIME_REVIEW_ERROR") from exc

def get_latest_review_request(project_id: str):
    try: return redact_payload(ops_guides.get_latest_review_request(project_id))
    except ops_guides.OpsGuideError as exc: raise coerce_core_error(exc, code="RUNTIME_REVIEW_ERROR") from exc

def create_review_request(project_id: str, body=None):
    try: return redact_payload(ops_guides.create_review_request(project_id, body or {}))
    except ops_guides.OpsGuideError as exc: raise coerce_core_error(exc, code="RUNTIME_REVIEW_ERROR") from exc

def complete_review_request(project_id: str, review_id: str, body=None):
    try: return redact_payload(ops_guides.complete_review_request(project_id, review_id, body or {}))
    except ops_guides.OpsGuideError as exc: raise coerce_core_error(exc, code="RUNTIME_REVIEW_ERROR") from exc

def get_latest_snapshot(project_id: str):
    try: return redact_payload(ops_runtime_inspect.get_latest_snapshot(project_id))
    except ops_runtime_inspect.OpsRuntimeInspectError as exc: raise coerce_core_error(exc, code="RUNTIME_INSPECT_ERROR") from exc

def get_latest_screenshot(project_id: str):
    try: return redact_payload(ops_runtime_inspect.get_latest_screenshot(project_id))
    except ops_runtime_inspect.OpsRuntimeInspectError as exc: raise coerce_core_error(exc, code="RUNTIME_INSPECT_ERROR") from exc

def get_latest_action(project_id: str):
    try: return redact_payload(ops_runtime_inspect.get_latest_action(project_id))
    except ops_runtime_inspect.OpsRuntimeInspectError as exc: raise coerce_core_error(exc, code="RUNTIME_INSPECT_ERROR") from exc

def capture_snapshot(project_id: str, body=None):
    try: return redact_payload(ops_runtime_inspect.capture_snapshot(project_id, body or {}))
    except ops_runtime_inspect.OpsRuntimeInspectError as exc: raise coerce_core_error(exc, code="RUNTIME_INSPECT_ERROR") from exc

def capture_screenshot(project_id: str, body=None):
    try: return redact_payload(ops_runtime_inspect.capture_screenshot(project_id, body or {}))
    except ops_runtime_inspect.OpsRuntimeInspectError as exc: raise coerce_core_error(exc, code="RUNTIME_INSPECT_ERROR") from exc

def run_action(project_id: str, body=None):
    try: return redact_payload(ops_runtime_inspect.run_action(project_id, body or {}))
    except ops_runtime_inspect.OpsRuntimeInspectError as exc: raise coerce_core_error(exc, code="RUNTIME_INSPECT_ERROR") from exc

"""HTTP routes for the Hermes Core API namespace."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote

from api.helpers import j
from api.core_contracts import CoreApiError, capabilities, error_payload, public_route_map
from api import (
    core_database,
    core_deployments,
    core_git,
    core_host,
    core_play,
    core_projects,
    core_runtime_tools,
    core_session_assets,
)

_PROJECT_ID = r"([^/]+)"
_TASK_ID = r"([^/]+)"
_EPIC_ID = r"([^/]+)"
_REVIEW_ID = r"([^/]+)"
_REPORT_ID = r"([^/]+)"

_ROOT_RE = re.compile(r"^/api/core/?$")
_CAPABILITIES_RE = re.compile(r"^/api/core/capabilities/?$")
_HEALTH_RE = re.compile(r"^/api/core/health/?$")
_HOST_HEALTH_RE = re.compile(r"^/api/core/host/health/?$")
_HOST_PROXY_RE = re.compile(r"^/api/core/host/proxy/?$")
_PROJECTS_RE = re.compile(r"^/api/core/projects/?$")
_PROJECT_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/?$")
_PROJECT_UPDATE_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/update/?$")
_PROJECT_SETTINGS_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/settings/?$")
_PROJECT_ACTIVITY_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/activity/?$")
_PROJECT_DELETE_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/delete/?$")
_PROJECT_ENSURE_WORKSPACE_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/ensure-workspace/?$")
_PROJECT_FILES_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/files/?$")
_PROJECT_FILE_CONTENT_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/files/content/?$")
_PROJECT_TASKS_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/tasks/?$")
_PROJECT_EPICS_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/epics/?$")
_PROJECT_EPIC_ENSURE_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/epics/ensure/?$")
_PROJECT_EPIC_DELETE_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/epics/{_EPIC_ID}/delete/?$")
_PROJECT_TASK_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/tasks/{_TASK_ID}/?$")
_PROJECT_TASK_UPDATE_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/tasks/{_TASK_ID}/update/?$")
_PROJECT_TASK_IMAGE_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/tasks/{_TASK_ID}/images/?$")
_PROJECT_TASK_DELETE_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/tasks/{_TASK_ID}/delete/?$")
_PROJECT_TASK_ARCHIVE_COMPLETED_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/tasks/archive-completed/?$")
_PLAY_CONFIG_FILE_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/play-config-file/?$")
_PLAY_STATUS_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/play/status/?$")
_PLAY_LOGS_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/play/logs/?$")
_PLAY_START_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/play/start/?$")
_PLAY_RESTART_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/play/restart/?$")
_PLAY_STOP_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/play/stop/?$")
_DEPLOYMENT_PROVIDERS_RE = re.compile(r"^/api/core/deployments/providers/?$")
_PROJECT_DEPLOYMENT_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/deployment/?$")
_PROJECT_DEPLOYMENT_LOGS_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/deployment/logs/?$")
_PROJECT_DEPLOYMENT_ARTIFACTS_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/deployment/artifacts/?$")
_PROJECT_DEPLOYMENT_SCAFFOLD_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/deployment/artifacts/scaffold/?$")
_PROJECT_DEPLOYMENT_EXECUTE_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/deployment/execute/?$")
_PROJECT_DEPLOYMENT_REDEPLOY_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/deployment/(?:redeploy|update)/?$")
_PROJECT_DEPLOYMENT_ACTION_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/deployment/([^/]+)/?$")
_DATABASE_SETTINGS_RE = re.compile(r"^/api/core/database/settings/?$")
_DATABASE_TEST_RE = re.compile(r"^/api/core/database/test/?$")
_DATABASE_TABLES_RE = re.compile(r"^/api/core/database/inspect/tables/?$")
_DATABASE_QUERY_RE = re.compile(r"^/api/core/database/inspect/query/?$")
_PROJECT_DATABASE_SETTINGS_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/database/settings/?$")
_PROJECT_DATABASE_TEST_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/database/test/?$")
_PROJECT_DATABASE_TABLES_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/database/inspect/tables/?$")
_PROJECT_DATABASE_QUERY_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/database/inspect/query/?$")
_PROJECT_GIT_STATUS_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/git/status/?$")
_PROJECT_GIT_OPERATION_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/git/(push|sync)/?$")
_GITHUB_STATUS_RE = re.compile(r"^/api/core/github/status/?$")
_GITHUB_REPOS_RE = re.compile(r"^/api/core/github/repos/?$")
_GITHUB_BRANCHES_RE = re.compile(r"^/api/core/github/repos/([^/]+)/([^/]+)/branches/?$")
_GITHUB_IMPORT_RE = re.compile(r"^/api/core/github/import/?$")
_RUNTIME_SUMMARY_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/summary/?$")
_RUNTIME_CAPABILITIES_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/capabilities/?$")
_GATHER_REPORTS_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/gather/reports/?$")
_GATHER_REPORT_LATEST_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/gather/reports/latest/?$")
_GATHER_REPORT_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/gather/reports/{_REPORT_ID}/?$")
_GATHER_REPORT_EVENTS_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/gather/reports/{_REPORT_ID}/events/?$")
_REVIEWS_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/inspect/reviews/?$")
_REVIEW_LATEST_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/inspect/reviews/latest/?$")
_REVIEW_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/inspect/reviews/{_REVIEW_ID}/?$")
_REVIEW_COMPLETE_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/inspect/reviews/{_REVIEW_ID}/complete/?$")
_SNAPSHOT_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/inspect/snapshot/?$")
_SNAPSHOT_LATEST_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/inspect/snapshot/latest/?$")
_SCREENSHOT_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/inspect/screenshot/?$")
_SCREENSHOT_LATEST_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/inspect/screenshot/latest/?$")
_ACTION_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/inspect/action/?$")
_ACTION_LATEST_RE = re.compile(rf"^/api/core/projects/{_PROJECT_ID}/runtime/inspect/action/latest/?$")
_SESSION_ACTIVITY_RE = re.compile(r"^/api/core/session-activity/?$")
_SESSION_ACTIVITY_GROUPS_RE = re.compile(r"^/api/core/session-activity/groups/?$")
_SESSION_ACTIVITY_GROUP_RENAME_RE = re.compile(r"^/api/core/session-activity/groups/([^/]+)/rename/?$")
_SESSION_ACTIVITY_GROUP_DELETE_RE = re.compile(r"^/api/core/session-activity/groups/([^/]+)/delete/?$")
_SESSION_ACTIVITY_ASSIGNMENT_RE = re.compile(r"^/api/core/session-activity/group-assignment/?$")
_SESSION_READABLE_OUTPUT_RE = re.compile(r"^/api/core/sessions/([^/]+)/readable-output/?$")


def _filters(parsed) -> dict:
    return {key: values[0] for key, values in parse_qs(parsed.query).items() if values}


def _q(parsed, name: str, default: str = "") -> str:
    return parse_qs(parsed.query).get(name, [default])[0]


def _send_error(handler, exc: Exception) -> None:
    if not isinstance(exc, CoreApiError):
        exc = CoreApiError(str(exc), status=int(getattr(exc, "status", 500) or 500), code="CORE_ROUTE_ERROR")
    j(handler, error_payload(exc), status=exc.status)


def handle_get(handler, parsed) -> bool:
    try:
        if _ROOT_RE.match(parsed.path):
            j(handler, {"coreApi": public_route_map(), "capabilities": capabilities()})
            return True
        if _CAPABILITIES_RE.match(parsed.path):
            j(handler, capabilities())
            return True
        if _HEALTH_RE.match(parsed.path) or _HOST_HEALTH_RE.match(parsed.path):
            j(handler, core_host.host_health())
            return True
        if _HOST_PROXY_RE.match(parsed.path):
            j(handler, core_host.proxy_descriptors())
            return True
        if _PROJECTS_RE.match(parsed.path):
            j(handler, core_projects.list_projects())
            return True
        match = _PROJECT_RE.match(parsed.path)
        if match:
            j(handler, {"project": core_projects.get_project(unquote(match.group(1)))})
            return True
        match = _PROJECT_FILES_RE.match(parsed.path)
        if match:
            j(handler, core_projects.list_project_files(unquote(match.group(1)), _q(parsed, "path")))
            return True
        match = _PROJECT_FILE_CONTENT_RE.match(parsed.path)
        if match:
            j(handler, core_projects.read_project_file(unquote(match.group(1)), _q(parsed, "path")))
            return True
        match = _PROJECT_TASKS_RE.match(parsed.path)
        if match:
            j(handler, core_projects.read_project_tasks(unquote(match.group(1))))
            return True
        match = _PLAY_CONFIG_FILE_RE.match(parsed.path)
        if match:
            j(handler, core_play.get_project_play_config_file_info(unquote(match.group(1))))
            return True
        match = _PLAY_STATUS_RE.match(parsed.path)
        if match:
            j(handler, core_play.get_project_play_status(unquote(match.group(1))))
            return True
        match = _PLAY_LOGS_RE.match(parsed.path)
        if match:
            j(handler, core_play.get_project_play_logs(unquote(match.group(1)), _q(parsed, "limit", "")))
            return True
        if _DEPLOYMENT_PROVIDERS_RE.match(parsed.path):
            j(handler, core_deployments.provider_registry())
            return True
        match = _PROJECT_DEPLOYMENT_RE.match(parsed.path)
        if match:
            j(handler, core_deployments.get_project_deployment(unquote(match.group(1))))
            return True
        match = _PROJECT_DEPLOYMENT_LOGS_RE.match(parsed.path)
        if match:
            j(handler, {"projectId": unquote(match.group(1)), "logs": core_deployments.get_project_deployment(unquote(match.group(1))).get("logs", [])})
            return True
        match = _PROJECT_DEPLOYMENT_ARTIFACTS_RE.match(parsed.path)
        if match:
            j(handler, core_deployments.detect_project_artifacts(unquote(match.group(1))))
            return True
        if _DATABASE_SETTINGS_RE.match(parsed.path):
            j(handler, core_database.get_settings())
            return True
        if _DATABASE_TABLES_RE.match(parsed.path):
            j(handler, core_database.inspect_tables())
            return True
        match = _PROJECT_DATABASE_SETTINGS_RE.match(parsed.path)
        if match:
            j(handler, core_database.get_project_settings(unquote(match.group(1))))
            return True
        match = _PROJECT_DATABASE_TABLES_RE.match(parsed.path)
        if match:
            j(handler, core_database.inspect_project_tables(unquote(match.group(1))))
            return True
        match = _PROJECT_GIT_STATUS_RE.match(parsed.path)
        if match:
            j(handler, {"git": core_git.get_project_git_status(unquote(match.group(1)))})
            return True
        if _GITHUB_STATUS_RE.match(parsed.path):
            j(handler, core_git.github_status())
            return True
        if _GITHUB_REPOS_RE.match(parsed.path):
            j(handler, core_git.list_repositories(_filters(parsed)))
            return True
        match = _GITHUB_BRANCHES_RE.match(parsed.path)
        if match:
            j(handler, core_git.list_branches(unquote(match.group(1)), unquote(match.group(2)), _filters(parsed)))
            return True
        match = _RUNTIME_SUMMARY_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.runtime_summary(unquote(match.group(1))))
            return True
        match = _RUNTIME_CAPABILITIES_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.runtime_capabilities(unquote(match.group(1))))
            return True
        match = _GATHER_REPORT_LATEST_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.get_latest_gather_report(unquote(match.group(1))))
            return True
        match = _GATHER_REPORT_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.get_gather_report(unquote(match.group(1)), unquote(match.group(2))))
            return True
        match = _GATHER_REPORTS_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.list_gather_reports(unquote(match.group(1)), _filters(parsed)))
            return True
        match = _REVIEW_LATEST_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.get_latest_review_request(unquote(match.group(1))))
            return True
        match = _REVIEW_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.get_review_request(unquote(match.group(1)), unquote(match.group(2))))
            return True
        match = _REVIEWS_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.list_review_requests(unquote(match.group(1)), _filters(parsed)))
            return True
        match = _SNAPSHOT_LATEST_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.get_latest_snapshot(unquote(match.group(1))))
            return True
        match = _SCREENSHOT_LATEST_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.get_latest_screenshot(unquote(match.group(1))))
            return True
        match = _ACTION_LATEST_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.get_latest_action(unquote(match.group(1))))
            return True
        if _SESSION_ACTIVITY_RE.match(parsed.path):
            j(handler, core_session_assets.list_activity())
            return True
        match = _SESSION_READABLE_OUTPUT_RE.match(parsed.path)
        if match:
            j(handler, core_session_assets.get_readable_output(unquote(match.group(1))))
            return True
        return False
    except Exception as exc:
        _send_error(handler, exc)
        return True


def handle_post(handler, parsed, body: dict) -> bool:
    try:
        if _PROJECTS_RE.match(parsed.path):
            j(handler, {"project": core_projects.create_project(body)}, status=201)
            return True
        match = _PROJECT_UPDATE_RE.match(parsed.path) or _PROJECT_SETTINGS_RE.match(parsed.path)
        if match:
            j(handler, core_projects.update_project(unquote(match.group(1)), body))
            return True
        match = _PROJECT_ACTIVITY_RE.match(parsed.path)
        if match:
            j(handler, core_projects.set_project_activity(unquote(match.group(1)), body.get("active")))
            return True
        match = _PROJECT_DELETE_RE.match(parsed.path)
        if match:
            j(handler, core_projects.delete_project(unquote(match.group(1))))
            return True
        match = _PROJECT_ENSURE_WORKSPACE_RE.match(parsed.path)
        if match:
            j(handler, core_projects.ensure_project_workspace(unquote(match.group(1))))
            return True
        match = _PROJECT_EPIC_ENSURE_RE.match(parsed.path)
        if match:
            result = core_projects.ensure_project_epic(unquote(match.group(1)), str(body.get("title") or ""))
            j(handler, result, status=201 if result.get("created") else 200)
            return True
        match = _PROJECT_EPICS_RE.match(parsed.path)
        if match:
            j(handler, core_projects.add_project_epic(unquote(match.group(1)), body.get("title")), status=201)
            return True
        match = _PROJECT_TASKS_RE.match(parsed.path)
        if match:
            j(handler, core_projects.add_project_task(unquote(match.group(1)), body), status=201)
            return True
        match = _PROJECT_TASK_UPDATE_RE.match(parsed.path) or _PROJECT_TASK_RE.match(parsed.path)
        if match:
            j(handler, core_projects.update_project_task(unquote(match.group(1)), unquote(match.group(2)), body))
            return True
        match = _PROJECT_TASK_IMAGE_RE.match(parsed.path)
        if match:
            j(handler, core_projects.add_project_task_image(unquote(match.group(1)), unquote(match.group(2)), body), status=201)
            return True
        match = _PROJECT_TASK_DELETE_RE.match(parsed.path)
        if match:
            j(handler, core_projects.delete_project_task(unquote(match.group(1)), unquote(match.group(2))))
            return True
        match = _PROJECT_EPIC_DELETE_RE.match(parsed.path)
        if match:
            j(handler, core_projects.delete_project_epic(unquote(match.group(1)), unquote(match.group(2))))
            return True
        match = _PROJECT_TASK_ARCHIVE_COMPLETED_RE.match(parsed.path)
        if match:
            j(handler, core_projects.archive_completed_project_tasks(unquote(match.group(1))))
            return True
        match = _PLAY_START_RE.match(parsed.path)
        if match:
            status = core_play.start_project_play(unquote(match.group(1)), body)
            j(handler, {"ok": True, "started": True, "status": status, "message": "Play pipeline started."})
            return True
        match = _PLAY_RESTART_RE.match(parsed.path)
        if match:
            status = core_play.restart_project_play(unquote(match.group(1)), body)
            j(handler, {"ok": True, "restarted": True, "status": status, "message": "Play pipeline restarted."})
            return True
        match = _PLAY_STOP_RE.match(parsed.path)
        if match:
            project_id = unquote(match.group(1))
            status = core_play.stop_project_play(project_id) or core_play.get_project_play_status(project_id)
            j(handler, {"ok": True, "stopped": True, "status": status, "message": "Play pipeline stopped."})
            return True
        match = _PROJECT_DEPLOYMENT_RE.match(parsed.path)
        if match:
            j(handler, core_deployments.record_project_deployment(unquote(match.group(1)), body), status=201)
            return True
        match = _PROJECT_DEPLOYMENT_SCAFFOLD_RE.match(parsed.path)
        if match:
            j(handler, core_deployments.scaffold_project_deployment(unquote(match.group(1)), body), status=201)
            return True
        match = _PROJECT_DEPLOYMENT_EXECUTE_RE.match(parsed.path)
        if match:
            j(handler, core_deployments.execute_project_deployment(unquote(match.group(1)), body), status=202)
            return True
        match = _PROJECT_DEPLOYMENT_REDEPLOY_RE.match(parsed.path)
        if match:
            j(handler, core_deployments.redeploy_project_deployment(unquote(match.group(1)), body, request_headers=handler.headers), status=202)
            return True
        match = _PROJECT_DEPLOYMENT_ACTION_RE.match(parsed.path)
        if match:
            j(handler, core_deployments.record_project_deployment(unquote(match.group(1)), body, action=unquote(match.group(2))), status=201)
            return True
        if _DATABASE_SETTINGS_RE.match(parsed.path):
            j(handler, {"ok": True, **core_database.save_settings(body)})
            return True
        if _DATABASE_TEST_RE.match(parsed.path):
            j(handler, core_database.test_connection(body))
            return True
        if _DATABASE_QUERY_RE.match(parsed.path):
            j(handler, core_database.execute_readonly_query(body))
            return True
        match = _PROJECT_DATABASE_SETTINGS_RE.match(parsed.path)
        if match:
            j(handler, {"ok": True, **core_database.save_project_settings(unquote(match.group(1)), body)})
            return True
        match = _PROJECT_DATABASE_TEST_RE.match(parsed.path)
        if match:
            j(handler, core_database.test_project_connection(unquote(match.group(1)), body))
            return True
        match = _PROJECT_DATABASE_QUERY_RE.match(parsed.path)
        if match:
            j(handler, core_database.execute_project_readonly_query(unquote(match.group(1)), body))
            return True
        match = _PROJECT_GIT_OPERATION_RE.match(parsed.path)
        if match:
            j(handler, {"operation": core_git.execute_project_git_operation(unquote(match.group(1)), unquote(match.group(2)), body)})
            return True
        if _GITHUB_IMPORT_RE.match(parsed.path):
            j(handler, {"ok": True, **core_git.import_repository(body)}, status=201)
            return True
        match = _GATHER_REPORTS_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.create_gather_report(unquote(match.group(1)), body), status=201)
            return True
        match = _GATHER_REPORT_EVENTS_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.append_gather_report_event(unquote(match.group(1)), unquote(match.group(2)), body))
            return True
        match = _REVIEWS_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.create_review_request(unquote(match.group(1)), body), status=201)
            return True
        match = _REVIEW_COMPLETE_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.complete_review_request(unquote(match.group(1)), unquote(match.group(2)), body))
            return True
        match = _SNAPSHOT_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.capture_snapshot(unquote(match.group(1)), body), status=201)
            return True
        match = _SCREENSHOT_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.capture_screenshot(unquote(match.group(1)), body), status=201)
            return True
        match = _ACTION_RE.match(parsed.path)
        if match:
            j(handler, core_runtime_tools.run_action(unquote(match.group(1)), body), status=201)
            return True
        if _SESSION_ACTIVITY_GROUPS_RE.match(parsed.path):
            j(handler, core_session_assets.create_activity_group(body.get("label")), status=201)
            return True
        match = _SESSION_ACTIVITY_GROUP_RENAME_RE.match(parsed.path)
        if match:
            j(handler, core_session_assets.rename_activity_group(unquote(match.group(1)), body.get("label")))
            return True
        match = _SESSION_ACTIVITY_GROUP_DELETE_RE.match(parsed.path)
        if match:
            j(handler, core_session_assets.delete_activity_group(unquote(match.group(1))))
            return True
        if _SESSION_ACTIVITY_ASSIGNMENT_RE.match(parsed.path):
            j(handler, core_session_assets.set_activity_group_assignment(body.get("sessionId") or body.get("session_id"), body.get("groupId")))
            return True
        return False
    except Exception as exc:
        _send_error(handler, exc)
        return True

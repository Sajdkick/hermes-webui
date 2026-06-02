"""Fork-owned Play routes for the clean restart branch."""

from __future__ import annotations

import re as _re
from urllib.parse import parse_qs, unquote

from api.helpers import bad, j
from api import core_play


def handle_get(handler, parsed) -> bool:
    play_proxy_match = _re.match(r"^/play-project/([^/]+)(/.*)?$", parsed.path)
    if play_proxy_match:
        core_play.handle_play_proxy_request(
            handler,
            unquote(play_proxy_match.group(1)),
            play_proxy_match.group(2) or "/",
            parsed,
            method=handler.command or "GET",
        )
        return True

    ops_project_play_config_match = _re.match(r"^/api/ops/projects/([^/]+)/play-config-file/?$", parsed.path)
    if ops_project_play_config_match:
        try:
            j(handler, core_play.get_project_play_config_file_info(unquote(ops_project_play_config_match.group(1))))
        except core_play.PlayPipelineError as e:
            bad(handler, str(e), e.status)
        return True

    ops_project_play_status_match = _re.match(r"^/api/ops/projects/([^/]+)/play/status/?$", parsed.path)
    if ops_project_play_status_match:
        try:
            j(handler, core_play.get_project_play_status(unquote(ops_project_play_status_match.group(1))))
        except core_play.PlayPipelineError as e:
            bad(handler, str(e), e.status)
        return True

    ops_project_play_logs_match = _re.match(r"^/api/ops/projects/([^/]+)/play/logs/?$", parsed.path)
    if ops_project_play_logs_match:
        try:
            raw_limit = parse_qs(parsed.query).get("limit", ["1000"])[0]
            j(handler, core_play.get_project_play_logs(unquote(ops_project_play_logs_match.group(1)), raw_limit))
        except core_play.PlayPipelineError as e:
            bad(handler, str(e), e.status)
        return True

    return False


def handle_post(handler, parsed, body) -> bool:
    play_proxy_match = _re.match(r"^/play-project/([^/]+)(/.*)?$", parsed.path)
    if play_proxy_match:
        core_play.handle_play_proxy_request(
            handler,
            unquote(play_proxy_match.group(1)),
            play_proxy_match.group(2) or "/",
            parsed,
            method=handler.command or "POST",
        )
        return True

    ops_project_play_start_match = _re.match(r"^/api/ops/projects/([^/]+)/play/start/?$", parsed.path)
    if ops_project_play_start_match:
        try:
            status = core_play.start_project_play(unquote(ops_project_play_start_match.group(1)), body)
            j(handler, {"ok": True, "started": True, "status": status, "message": "Play pipeline started."})
        except core_play.PlayPipelineError as e:
            bad(handler, str(e), e.status)
        return True

    ops_project_play_restart_match = _re.match(r"^/api/ops/projects/([^/]+)/play/restart/?$", parsed.path)
    if ops_project_play_restart_match:
        try:
            status = core_play.restart_project_play(unquote(ops_project_play_restart_match.group(1)), body)
            j(handler, {"ok": True, "restarted": True, "status": status, "message": "Play pipeline restarted."})
        except core_play.PlayPipelineError as e:
            bad(handler, str(e), e.status)
        return True

    ops_project_play_stop_match = _re.match(r"^/api/ops/projects/([^/]+)/play/stop/?$", parsed.path)
    if ops_project_play_stop_match:
        try:
            project_id = unquote(ops_project_play_stop_match.group(1))
            status = core_play.stop_project_play(project_id)
            if status is None:
                status = core_play.get_project_play_status(project_id)
            j(handler, {"ok": True, "stopped": True, "status": status, "message": "Play pipeline stopped."})
        except core_play.PlayPipelineError as e:
            bad(handler, str(e), e.status)
        return True

    return False

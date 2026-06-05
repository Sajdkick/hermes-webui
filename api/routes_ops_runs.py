"""Fork-owned run activity routes for the clean restart branch."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote

from api.helpers import j
from api import ops_runs


_RUNS_RE = re.compile(r"^/api/ops/runs/?$")
_RUNS_SUMMARY_RE = re.compile(r"^/api/ops/runs/summary/?$")
_RUN_RE = re.compile(r"^/api/ops/runs/([^/]+)/?$")
_RUN_COMPLETE_RE = re.compile(r"^/api/ops/runs/([^/]+)/complete/?$")
_RUN_REQUESTS_RE = re.compile(r"^/api/ops/runs/([^/]+)/requests/?$")
_RUN_RUNTIME_STATUS_RE = re.compile(r"^/api/ops/runs/([^/]+)/runtime/status/?$")
_RUN_STALE_SCAN_RE = re.compile(r"^/api/ops/runs/stale-scan/?$")


def handle_get(handler, parsed) -> bool:
    try:
        if _RUNS_RE.match(parsed.path):
            filters = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
            j(handler, ops_runs.list_ops_runs(filters))
            return True

        if _RUNS_SUMMARY_RE.match(parsed.path):
            filters = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
            j(handler, ops_runs.list_ops_run_summaries(filters))
            return True

        match = _RUN_REQUESTS_RE.match(parsed.path)
        if match:
            j(handler, ops_runs.list_ops_run_requests(unquote(match.group(1))))
            return True

        match = _RUN_RUNTIME_STATUS_RE.match(parsed.path)
        if match:
            j(handler, ops_runs.get_ops_run_runtime_status(unquote(match.group(1))))
            return True

        match = _RUN_RE.match(parsed.path)
        if match:
            j(handler, {"run": ops_runs.get_ops_run(unquote(match.group(1)))})
            return True
        return False
    except ops_runs.OpsRunError as exc:
        j(handler, {"error": str(exc)}, status=exc.status)
        return True


def handle_post(handler, parsed, body: dict) -> bool:
    try:
        if _RUNS_RE.match(parsed.path):
            j(handler, {"run": ops_runs.create_ops_run(body)}, status=201)
            return True

        match = _RUN_RE.match(parsed.path)
        if match:
            j(handler, {"run": ops_runs.update_ops_run(unquote(match.group(1)), body)})
            return True

        match = _RUN_COMPLETE_RE.match(parsed.path)
        if match:
            j(handler, {"run": ops_runs.complete_ops_run(unquote(match.group(1)), body)})
            return True

        if _RUN_STALE_SCAN_RE.match(parsed.path):
            j(handler, ops_runs.mark_stale_ops_runs(body))
            return True
        return False
    except ops_runs.OpsRunError as exc:
        j(handler, {"error": str(exc)}, status=exc.status)
        return True

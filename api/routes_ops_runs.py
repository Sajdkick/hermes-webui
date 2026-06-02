"""Fork-owned run activity routes for the clean restart branch."""

from __future__ import annotations

import mimetypes
import re
from urllib.parse import parse_qs, quote, unquote

from api.helpers import _security_headers, j
from api import ops_runs


_RUNS_RE = re.compile(r"^/api/ops/runs/?$")
_RUNS_SUMMARY_RE = re.compile(r"^/api/ops/runs/summary/?$")
_RUN_RE = re.compile(r"^/api/ops/runs/([^/]+)/?$")
_RUN_COMPLETE_RE = re.compile(r"^/api/ops/runs/([^/]+)/complete/?$")
_RUN_REQUESTS_RE = re.compile(r"^/api/ops/runs/([^/]+)/requests/?$")
_RUN_RUNTIME_STATUS_RE = re.compile(r"^/api/ops/runs/([^/]+)/runtime/status/?$")
_RUN_READABLE_RE = re.compile(r"^/api/ops/runs/([^/]+)/readable-output/?$")
_RUN_READABLE_ASSET_RE = re.compile(r"^/api/ops/runs/([^/]+)/readable-output/assets/(.+)$")
_RUN_STALE_SCAN_RE = re.compile(r"^/api/ops/runs/stale-scan/?$")


def _send_file(handler, target):
    try:
        raw_bytes = target.read_bytes()
    except PermissionError:
        j(handler, {"error": "Readable output is not readable."}, status=403)
        return True
    except Exception:
        j(handler, {"error": "Could not read readable output asset."}, status=500)
        return True
    mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    handler.send_response(200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(len(raw_bytes)))
    handler.send_header("Cache-Control", "private, max-age=3600")
    _security_headers(handler)
    handler.send_header("Content-Disposition", f'inline; filename="{target.name}"')
    handler.end_headers()
    handler.wfile.write(raw_bytes)
    return True


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

        match = _RUN_READABLE_ASSET_RE.match(parsed.path)
        if match:
            return _send_file(
                handler,
                ops_runs.resolve_ops_run_readable_asset(unquote(match.group(1)), unquote(match.group(2))),
            )

        match = _RUN_READABLE_RE.match(parsed.path)
        if match:
            run_id = unquote(match.group(1))
            payload = ops_runs.get_ops_run_readable_output(run_id)
            artifact = payload.get("readableOutput") if isinstance(payload, dict) else None
            if isinstance(artifact, dict):
                artifact["assetBaseUrl"] = f"/api/ops/runs/{quote(run_id, safe='')}/readable-output/assets/"
            j(handler, payload)
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

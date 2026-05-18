"""Fork-owned ops shell routes."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import quote

from api.helpers import _security_headers, j, t
from api.updates import WEBUI_VERSION


_STATIC_DIR = (Path(__file__).parent.parent / "static").resolve()
_OPS_SHELL_PATH = (_STATIC_DIR / "ops-shell.html").resolve()
_LEGACY_OPS_SHELL_PATH = (_STATIC_DIR / "ops-legacy.html").resolve()
_SESSION_PREFIXED_OPS_ROUTE_RE = re.compile(r"^/session/[^/]+/(ops|ops-phase)/?$")
_OPS_PAGE_DEBUG_LOG_PATH = Path(
    os.environ.get("HERMES_WEBUI_STATE_DIR")
    or (Path.home() / ".hermes" / "webui")
) / "ops-page-debug.jsonl"
logger = logging.getLogger(__name__)


_OPS_SHELL_ERROR_HTML = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Hermes is restarting</title>
</head>
<body style=\"margin:0;padding:2rem;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#111827;color:#e5e7eb;\">
  <main style=\"max-width:40rem;margin:10vh auto;line-height:1.5;\">
    <h1 style=\"font-size:1.5rem;margin:0 0 0.75rem;\">Hermes is restarting…</h1>
    <p style=\"margin:0;color:#cbd5e1;\">The Cloud Terminal shell could not load cleanly. Refresh in a moment if this page does not update automatically.</p>
  </main>
</body>
</html>"""


def _serve_ops_shell_unavailable(handler, exc: Exception) -> bool:
    """Return HTML for ops shell failures so shell routes never render JSON."""
    logger.warning("Failed to serve ops shell route: %s", exc)
    t(
        handler,
        _OPS_SHELL_ERROR_HTML,
        status=503,
        content_type="text/html; charset=utf-8",
    )
    return True


def _ops_shell_payload() -> dict:
    return {
        "app": "cloud-terminal",
        "phase": "phase-10",
        "status": "ready",
        "route": "/ops-phase",
        "apiBase": "/api/ops",
        "assets": {
            "entryScript": "/static/cloud-terminal-entry.js",
            "entryStylesheet": "/static/cloud-terminal.css",
            "databaseScript": "/static/ops-database.js",
            "gitScript": "/static/ops-git.js",
            "githubScript": "/static/ops-github-admin.js",
            "notificationsScript": "/static/ops-notifications.js",
            "runsScript": "/static/ops-runs.js",
            "runtimeScript": "/static/ops-runtime.js",
            "upstreamSyncScript": "/static/ops-upstream-sync.js",
            "projectsScript": "/static/ops-projects.js",
        },
        "version": WEBUI_VERSION,
    }


def _ops_shell_html() -> str:
    version_token = quote(WEBUI_VERSION, safe="")
    return _OPS_SHELL_PATH.read_text(encoding="utf-8").replace("__WEBUI_VERSION__", version_token)


def _legacy_ops_shell_html() -> str:
    version_token = quote(WEBUI_VERSION, safe="")
    return _LEGACY_OPS_SHELL_PATH.read_text(encoding="utf-8").replace("__WEBUI_VERSION__", version_token)


def redirect_session_prefixed_ops_shell(handler, parsed) -> bool:
    if not _SESSION_PREFIXED_OPS_ROUTE_RE.match(parsed.path or ""):
        return False
    target = "/ops-phase"
    if parsed.query:
        target += "?" + parsed.query
    handler.send_response(302)
    handler.send_header("Location", target)
    handler.send_header("Cache-Control", "no-store")
    _security_headers(handler, allow_same_origin_frame=True)
    handler.end_headers()
    return True


def serve_legacy_ops_shell(handler) -> bool:
    try:
        html = _legacy_ops_shell_html()
    except Exception as exc:
        return _serve_ops_shell_unavailable(handler, exc)
    t(handler, html, content_type="text/html; charset=utf-8")
    return True


def handle_post(handler, parsed, body: dict) -> bool:
    if parsed.path != "/api/ops/page-debug":
        return False
    payload = body if isinstance(body, dict) else {}
    entry = {
        "receivedAt": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "path": parsed.path,
        "payload": payload,
    }
    try:
        _OPS_PAGE_DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _OPS_PAGE_DEBUG_LOG_PATH.open("a", encoding="utf-8") as fh:
          fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Failed to write ops page debug event: %s", exc)
        return j(handler, {"error": "Failed to store ops page debug event."}, status=500)
    return j(handler, {"ok": True})


def handle_get(handler, parsed) -> bool:
    if parsed.path in ("/ops", "/ops/"):
        return serve_legacy_ops_shell(handler)

    if parsed.path in ("/ops-phase", "/ops-phase/"):
        try:
            html = _ops_shell_html()
        except Exception as exc:
            return _serve_ops_shell_unavailable(handler, exc)
        t(handler, html, content_type="text/html; charset=utf-8")
        return True

    if parsed.path == "/api/ops/shell":
        j(handler, _ops_shell_payload())
        return True

    return False

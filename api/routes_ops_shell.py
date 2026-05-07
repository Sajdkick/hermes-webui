"""Fork-owned ops shell routes."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from api.helpers import j, t
from api.updates import WEBUI_VERSION


_STATIC_DIR = (Path(__file__).parent.parent / "static").resolve()
_OPS_SHELL_PATH = (_STATIC_DIR / "ops-shell.html").resolve()
_LEGACY_OPS_SHELL_PATH = (_STATIC_DIR / "ops-legacy.html").resolve()


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


def serve_legacy_ops_shell(handler) -> bool:
    try:
        html = _legacy_ops_shell_html()
    except OSError:
        j(handler, {"error": "ops shell is unavailable"}, status=500)
        return True
    t(handler, html, content_type="text/html; charset=utf-8")
    return True


def handle_get(handler, parsed) -> bool:
    if parsed.path in ("/ops", "/ops/"):
        return serve_legacy_ops_shell(handler)

    if parsed.path in ("/ops-phase", "/ops-phase/"):
        try:
            html = _ops_shell_html()
        except OSError:
            j(handler, {"error": "ops shell is unavailable"}, status=500)
            return True
        t(handler, html, content_type="text/html; charset=utf-8")
        return True

    if parsed.path == "/api/ops/shell":
        j(handler, _ops_shell_payload())
        return True

    return False

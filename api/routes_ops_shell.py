"""Fork-owned ops shell routes for the clean restart branch."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from api.helpers import j, t
from api.updates import WEBUI_VERSION


_STATIC_DIR = (Path(__file__).parent.parent / "static").resolve()
_OPS_SHELL_PATH = (_STATIC_DIR / "ops-shell.html").resolve()


def _ops_shell_payload() -> dict:
    return {
        "app": "cloud-terminal",
        "phase": "phase-6",
        "status": "ready",
        "route": "/ops",
        "apiBase": "/api/ops",
        "assets": {
            "entryScript": "/static/cloud-terminal-entry.js",
            "entryStylesheet": "/static/cloud-terminal.css",
            "notificationsScript": "/static/ops-notifications.js",
            "projectsScript": "/static/ops-projects.js",
        },
        "version": WEBUI_VERSION,
    }


def _ops_shell_html() -> str:
    version_token = quote(WEBUI_VERSION, safe="")
    return _OPS_SHELL_PATH.read_text(encoding="utf-8").replace("__WEBUI_VERSION__", version_token)


def handle_get(handler, parsed) -> bool:
    if parsed.path in ("/ops", "/ops/"):
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

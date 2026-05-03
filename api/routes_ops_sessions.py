"""Fork-owned session readable-output routes for the clean restart branch."""

from __future__ import annotations

import mimetypes
import re
from urllib.parse import quote, unquote

from api.helpers import _security_headers, bad, j
from api import session_readable_output


_SESSION_READABLE_OUTPUT_RE = re.compile(r"^/api/ops/sessions/([^/]+)/readable-output/?$")
_SESSION_READABLE_ASSET_RE = re.compile(r"^/api/ops/sessions/([^/]+)/readable-output/assets/(.+)$")


def _send_file(handler, target):
    try:
        raw_bytes = target.read_bytes()
    except PermissionError:
        return bad(handler, "Readable output is not readable.", 403)
    except Exception:
        return bad(handler, "Could not read readable output asset.", 500)
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
    match = _SESSION_READABLE_ASSET_RE.match(parsed.path)
    if match:
        try:
            target = session_readable_output.resolve_session_readable_asset(
                unquote(match.group(1)),
                unquote(match.group(2)),
            )
        except session_readable_output.SessionReadableOutputError as exc:
            return bad(handler, str(exc), exc.status)
        return _send_file(handler, target)

    match = _SESSION_READABLE_OUTPUT_RE.match(parsed.path)
    if match:
        try:
            payload = session_readable_output.get_session_readable_output(unquote(match.group(1)))
        except session_readable_output.SessionReadableOutputError as exc:
            return bad(handler, str(exc), exc.status)
        artifact = payload.get("readableOutput") if isinstance(payload, dict) else None
        if isinstance(artifact, dict):
            artifact["assetBaseUrl"] = (
                f"/api/ops/sessions/{quote(unquote(match.group(1)), safe='')}/readable-output/assets/"
            )
        j(handler, payload)
        return True

    return False

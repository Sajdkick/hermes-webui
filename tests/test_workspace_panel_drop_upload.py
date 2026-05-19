"""Workspace panel local file/folder drag-and-drop uploads."""

from __future__ import annotations

import io
import json
import pathlib
import urllib.error
import urllib.request
import uuid
from types import SimpleNamespace

import pytest

from api import upload
from tests._pytest_port import BASE


class FakeUploadHandler:
    def __init__(self, body: bytes, content_type: str):
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
        }
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.status = None
        self.response_headers = []

    def send_response(self, status: int):
        self.status = status

    def send_header(self, key: str, value: str):
        self.response_headers.append((key, value))

    def end_headers(self):
        pass


def _multipart(fields: dict[str, str], file_name: str, file_bytes: bytes) -> tuple[bytes, str]:
    boundary = f"----HermesWorkspaceUpload{uuid.uuid4().hex}".encode("ascii")
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                b"--" + boundary + b"\r\n",
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            b"--" + boundary + b"\r\n",
            f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'.encode("utf-8"),
            b"Content-Type: text/plain\r\n\r\n",
            file_bytes,
            b"\r\n",
            b"--" + boundary + b"--\r\n",
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary.decode('ascii')}"


def _decode(handler: FakeUploadHandler) -> dict:
    return json.loads(handler.wfile.getvalue().decode("utf-8"))


def _post_json(path: str, body: dict) -> tuple[dict, int]:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8")), response.status
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode("utf-8") or "{}"), exc.code


def _post_multipart(path: str, body: bytes, content_type: str, *, origin: str | None = None) -> tuple[dict, int]:
    headers = {"Content-Type": content_type}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8")), response.status
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8")
        return json.loads(payload or "{}"), exc.code


def test_workspace_upload_preserves_subfolder_paths(tmp_path, monkeypatch):
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    monkeypatch.setattr(upload, "get_session", lambda sid: SimpleNamespace(workspace=str(tmp_path)))
    body, content_type = _multipart(
        {"session_id": "session-1", "dir": "target", "rel_path": "folder/nested/example.txt"},
        "example.txt",
        b"hello workspace",
    )
    handler = FakeUploadHandler(body, content_type)

    upload.handle_workspace_upload(handler)

    payload = _decode(handler)
    assert handler.status == 200
    assert payload["ok"] is True
    assert payload["path"] == "target/folder/nested/example.txt"
    assert (tmp_path / "target" / "folder" / "nested" / "example.txt").read_bytes() == b"hello workspace"


@pytest.mark.parametrize(
    "rel_path",
    ["../escape.txt", "/absolute.txt", "C:/Users/me/secret.txt", "folder/../../escape.txt"],
)
def test_workspace_upload_rejects_traversal_and_absolute_paths(tmp_path, monkeypatch, rel_path):
    monkeypatch.setattr(upload, "get_session", lambda sid: SimpleNamespace(workspace=str(tmp_path)))
    body, content_type = _multipart(
        {"session_id": "session-1", "dir": ".", "rel_path": rel_path},
        "escape.txt",
        b"nope",
    )
    handler = FakeUploadHandler(body, content_type)

    upload.handle_workspace_upload(handler)

    payload = _decode(handler)
    assert handler.status == 400
    assert "Invalid upload path" in payload["error"] or "not in the subpath" in payload["error"]
    assert not (tmp_path / "escape.txt").exists()


@pytest.mark.parametrize("dir_path", ["../escape", "/tmp", "C:/Users/me"])
def test_workspace_upload_rejects_invalid_target_directories(tmp_path, monkeypatch, dir_path):
    monkeypatch.setattr(upload, "get_session", lambda sid: SimpleNamespace(workspace=str(tmp_path)))
    body, content_type = _multipart(
        {"session_id": "session-1", "dir": dir_path, "rel_path": "example.txt"},
        "example.txt",
        b"nope",
    )
    handler = FakeUploadHandler(body, content_type)

    upload.handle_workspace_upload(handler)

    payload = _decode(handler)
    assert handler.status == 400
    assert "Invalid upload path" in payload["error"] or "not in the subpath" in payload["error"]
    assert not any(tmp_path.iterdir())


def test_workspace_upload_route_accepts_browser_multipart(cleanup_test_sessions):
    session_payload, session_status = _post_json("/api/session/new", {})
    assert session_status == 200, session_payload
    sid = session_payload["session"]["session_id"]
    cleanup_test_sessions.append(sid)
    workspace = pathlib.Path(session_payload["session"]["workspace"])
    target_dir = workspace / "target"
    target_dir.mkdir(parents=True, exist_ok=True)
    body, content_type = _multipart(
        {"session_id": sid, "dir": "target", "rel_path": "folder/nested/example.txt"},
        "example.txt",
        b"hello through route",
    )

    payload, status = _post_multipart("/api/file/upload", body, content_type, origin=BASE)

    assert status == 200, payload
    assert payload["ok"] is True
    assert payload["path"] == "target/folder/nested/example.txt"
    assert (target_dir / "folder" / "nested" / "example.txt").read_bytes() == b"hello through route"


def test_workspace_upload_route_is_before_json_body_reader():
    routes = open("api/routes.py", encoding="utf-8").read()
    route_idx = routes.index('if parsed.path == "/api/file/upload"')
    read_body_idx = routes.index("body = read_body(handler)")
    assert route_idx < read_body_idx


def test_workspace_panel_drop_frontend_preserves_folders_and_uses_workspace_endpoint():
    workspace_js = open("static/workspace.js", encoding="utf-8").read()
    ui_js = open("static/ui.js", encoding="utf-8").read()
    style_css = open("static/style.css", encoding="utf-8").read()
    i18n_js = open("static/i18n.js", encoding="utf-8").read()

    assert "_setupWorkspacePanelUploadDrop" in workspace_js
    assert "webkitGetAsEntry" in workspace_js
    assert "_collectDroppedWorkspaceEntry" in workspace_js
    assert "api/file/upload" in workspace_js
    assert "_redirectIfUnauth" not in workspace_js
    assert "XMLHttpRequest" in workspace_js
    assert "xhr.status===401" in workspace_js
    assert "X-Hermes-CSRF-Token" in workspace_js
    assert "firstFailure" in workspace_js
    assert "_workspaceUploadIndicatorUpdate" in workspace_js
    assert "_workspaceUploadIndicatorFinish" in workspace_js
    assert "workspaceUploadIndicator" in open("static/index.html", encoding="utf-8").read()
    assert "rel_path" in workspace_js
    assert "e.stopPropagation()" in workspace_js
    assert "dataset.wsPath=item.path" in ui_js
    assert "dataset.wsType=item.type" in ui_js
    assert "workspace-drop-over" in style_css
    assert "workspace-upload-indicator" in style_css
    assert "workspace_upload_complete" in i18n_js
    assert "workspace_upload_progress" in i18n_js

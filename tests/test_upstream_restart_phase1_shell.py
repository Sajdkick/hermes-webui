import json
from urllib.parse import urlparse


class _FakeHandler:
    def __init__(self):
        self.status = None
        self.sent_headers = []
        self.body = bytearray()
        self.wfile = self
        self.headers = {}

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent_headers.append((name, value))

    def end_headers(self):
        pass

    def write(self, data):
        self.body.extend(data)

    def header(self, name):
        for key, value in self.sent_headers:
            if key.lower() == name.lower():
                return value
        return None


def test_ops_shell_route_is_registered_and_serves_html():
    from api.routes import handle_get

    handler = _FakeHandler()
    parsed = urlparse("http://example.com/ops")

    assert handle_get(handler, parsed) is True
    assert handler.status == 200
    assert (handler.header("Content-Type") or "").startswith("text/html")
    html = bytes(handler.body).decode("utf-8")
    assert 'data-ops-shell="cloud-terminal"' in html
    assert "/static/ops-projects.js" in html
    assert "/static/cloud-terminal-entry.js" in html
    assert "/static/cloud-terminal.css" in html


def test_ops_shell_bootstrap_api_is_registered():
    from api.routes import handle_get

    handler = _FakeHandler()
    parsed = urlparse("http://example.com/api/ops/shell")

    assert handle_get(handler, parsed) is True
    assert handler.status == 200
    assert (handler.header("Content-Type") or "").startswith("application/json")
    payload = json.loads(bytes(handler.body).decode("utf-8"))
    assert payload["phase"].startswith("phase-")
    assert payload["route"] == "/ops"
    assert payload["assets"]["entryScript"] == "/static/cloud-terminal-entry.js"
    assert payload["assets"]["entryStylesheet"] == "/static/cloud-terminal.css"
    assert payload["assets"]["projectsScript"] == "/static/ops-projects.js"


def test_ops_shell_assets_are_served_by_static_route():
    from api.routes import handle_get

    script = _FakeHandler()
    assert handle_get(script, urlparse("http://example.com/static/cloud-terminal-entry.js")) is True
    assert script.status == 200
    assert (script.header("Content-Type") or "").startswith("application/javascript")

    stylesheet = _FakeHandler()
    assert handle_get(stylesheet, urlparse("http://example.com/static/cloud-terminal.css")) is True
    assert stylesheet.status == 200
    assert (stylesheet.header("Content-Type") or "").startswith("text/css")

    projects_script = _FakeHandler()
    assert handle_get(projects_script, urlparse("http://example.com/static/ops-projects.js")) is True
    assert projects_script.status == 200
    assert (projects_script.header("Content-Type") or "").startswith("application/javascript")

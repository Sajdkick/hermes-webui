import json
from pathlib import Path
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
    assert 'document.write(\'<base href="' in html
    assert 'href="static/cloud-terminal.css?v=__WEBUI_VERSION__"' not in html
    assert 'href="static/cloud-terminal.css?v=' in html
    assert 'src="static/ops-github-admin.js?v=' in html
    assert 'src="static/ops-database.js?v=' in html
    assert 'src="static/ops-git.js?v=' in html
    assert 'src="static/ops-runs.js?v=' in html
    assert 'src="static/ops-upstream-sync.js?v=' in html
    assert 'src="static/ops-projects.js?v=' in html
    assert 'src="static/cloud-terminal-entry.js?v=' in html
    assert 'href="api/ops/shell"' in html


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
    assert payload["assets"]["githubScript"] == "/static/ops-github-admin.js"
    assert payload["assets"]["databaseScript"] == "/static/ops-database.js"
    assert payload["assets"]["gitScript"] == "/static/ops-git.js"
    assert payload["assets"]["runsScript"] == "/static/ops-runs.js"
    assert payload["assets"]["upstreamSyncScript"] == "/static/ops-upstream-sync.js"
    assert payload["assets"]["projectsScript"] == "/static/ops-projects.js"


def test_ops_entry_uses_base_relative_shell_fetch():
    source = Path("static/cloud-terminal-entry.js").read_text(encoding="utf-8")

    assert "const base=(typeof document!=='undefined' && document.baseURI)" in source
    assert "return new URL(rel, base).href;" in source
    assert "fetch(appUrl('api/ops/shell')" in source


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

    git_script = _FakeHandler()
    assert handle_get(git_script, urlparse("http://example.com/static/ops-git.js")) is True
    assert git_script.status == 200
    assert (git_script.header("Content-Type") or "").startswith("application/javascript")

    runs_script = _FakeHandler()
    assert handle_get(runs_script, urlparse("http://example.com/static/ops-runs.js")) is True
    assert runs_script.status == 200
    assert (runs_script.header("Content-Type") or "").startswith("application/javascript")

    github_script = _FakeHandler()
    assert handle_get(github_script, urlparse("http://example.com/static/ops-github-admin.js")) is True
    assert github_script.status == 200
    assert (github_script.header("Content-Type") or "").startswith("application/javascript")

    database_script = _FakeHandler()
    assert handle_get(database_script, urlparse("http://example.com/static/ops-database.js")) is True
    assert database_script.status == 200
    assert (database_script.header("Content-Type") or "").startswith("application/javascript")

    upstream_sync_script = _FakeHandler()
    assert handle_get(upstream_sync_script, urlparse("http://example.com/static/ops-upstream-sync.js")) is True
    assert upstream_sync_script.status == 200
    assert (upstream_sync_script.header("Content-Type") or "").startswith("application/javascript")

    projects_script = _FakeHandler()
    assert handle_get(projects_script, urlparse("http://example.com/static/ops-projects.js")) is True
    assert projects_script.status == 200
    assert (projects_script.header("Content-Type") or "").startswith("application/javascript")

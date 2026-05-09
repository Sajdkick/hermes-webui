"""Regression coverage for shell/home route fallbacks.

The WebUI shell should never render a JSON error page for shell routes, even if
HTML serving fails during a restart/update race. The Cloud Terminal fork keeps
`/` owned by the ops shell and exposes the upstream chat shell at `/index.html`;
both boundaries should fail as HTML instead of API-style JSON.
"""

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


class _BrokenHtmlPath:
    def read_text(self, *args, **kwargs):
        raise RuntimeError("simulated shell html read failure")


def _assert_html_unavailable(handler):
    assert handler.status == 503
    assert (handler.header("Content-Type") or "").startswith("text/html; charset=utf-8")
    assert handler.header("Cache-Control") == "no-store"

    body = bytes(handler.body).decode("utf-8")
    assert "Hermes is restarting" in body
    assert "application/json" not in (handler.header("Content-Type") or "")
    assert '"error"' not in body


def test_index_shell_internal_error_returns_html_503_not_json(monkeypatch):
    from api import routes

    monkeypatch.setattr(routes, "_INDEX_HTML_PATH", _BrokenHtmlPath())

    handler = _FakeHandler()
    assert routes.handle_get(handler, urlparse("http://example.com/index.html")) is True

    _assert_html_unavailable(handler)


def test_root_ops_shell_internal_error_returns_html_503_not_json(monkeypatch):
    from api import routes_ops_shell
    from api import routes

    monkeypatch.setattr(routes_ops_shell, "_LEGACY_OPS_SHELL_PATH", _BrokenHtmlPath())

    handler = _FakeHandler()
    assert routes.handle_get(handler, urlparse("http://example.com/")) is True

    _assert_html_unavailable(handler)

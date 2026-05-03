import io
import json
import subprocess
import textwrap
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


def _response_json(handler: _FakeHandler) -> dict:
    return json.loads(bytes(handler.body).decode("utf-8"))


def test_phase5_session_readable_output_routes_use_workspace_repo_fallback(tmp_path):
    repo_root = tmp_path / "readable-output-project"
    app_dir = repo_root / "apps" / "demo"
    app_dir.mkdir(parents=True)
    (repo_root / ".git").mkdir()

    from api.models import new_session
    from api.routes import handle_get

    session = new_session(workspace=str(app_dir))
    session.title = "Readable output session"
    session.save()

    readable_dir = repo_root / ".cloud-terminal" / "readable-output" / session.session_id
    asset_dir = readable_dir / "assets"
    asset_dir.mkdir(parents=True)
    message_path = readable_dir / "message.md"
    message_path.write_text("# Session note\n\n![Result](assets/result.png)\n", encoding="utf-8")
    (asset_dir / "result.png").write_bytes(b"png")

    payload_handler = _FakeHandler()
    assert handle_get(
        payload_handler,
        urlparse(f"http://example.com/api/ops/sessions/{session.session_id}/readable-output"),
    ) is True
    payload = _response_json(payload_handler)
    artifact = payload["readableOutput"]

    assert artifact["exists"] is True
    assert artifact["path"] == str(message_path)
    assert artifact["assetDir"] == str(asset_dir)
    assert artifact["assetBaseUrl"] == f"/api/ops/sessions/{session.session_id}/readable-output/assets/"
    assert artifact["title"] == "Session note"
    assert artifact["assets"][0]["path"] == "result.png"

    asset_handler = _FakeHandler()
    assert handle_get(
        asset_handler,
        urlparse(f"http://example.com/api/ops/sessions/{session.session_id}/readable-output/assets/result.png"),
    ) is True
    assert asset_handler.status == 200
    assert (asset_handler.header("Content-Type") or "").startswith("image/png")
    assert bytes(asset_handler.body) == b"png"


def test_phase5_readable_output_frontend_wiring_and_wrappers_present():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    messages_js = Path("static/messages.js").read_text(encoding="utf-8")
    product_js = Path("static/readable-output-ui.js").read_text(encoding="utf-8")

    assert 'id="sessionReadableOutputHost"' in index_html
    assert 'static/readable-output-ui.css' in index_html
    assert 'static/readable-output-ui.js' in index_html
    assert "window.loadSession=async function(sid)" in product_js
    assert "window.newSession=async function()" in product_js
    assert "loadSessionReadableOutput(completedSid)" in messages_js


def test_phase5_readable_output_ui_loads_and_clears_with_session_wrappers():
    script = textwrap.dedent(
        """
        (async () => {
        const fs = require('fs');
        const vm = require('vm');

        const host = { hidden: true, innerHTML: '' };
        const fetchCalls = [];
        const source = fs.readFileSync('static/readable-output-ui.js', 'utf8');
        const context = {
          console,
          S: {
            session: { session_id: 'session-1' },
            readableOutput: null,
            readableOutputSessionId: '',
            readableOutputDismissedViewKey: '',
          },
          window: {},
          fetch: async (path) => {
            fetchCalls.push(path);
            return {
              ok: true,
              json: async () => ({
                readableOutput: {
                  exists: true,
                  title: 'Readable output',
                  path: '/tmp/message.md',
                  markdown: '# Done\\n\\n![Result](assets/result.png)\\n',
                  assetBaseUrl: '/api/ops/sessions/session-1/readable-output/assets/',
                  assets: [{ path: 'result.png' }],
                  updated_at: 1,
                  size: 24
                }
              })
            };
          },
          renderMd: (markdown) => '<article>'+markdown+'</article>',
          $: (id) => id === 'sessionReadableOutputHost' ? host : null,
          document: { getElementById: (id) => id === 'sessionReadableOutputHost' ? host : null },
        };
        context.window = context;
        context.window.loadSession = async function(sid){
          context.S.session = { session_id: sid };
          return { ok: true };
        };
        context.window.newSession = async function(){
          context.S.session = { session_id: 'session-2' };
          return { ok: true };
        };

        vm.createContext(context);
        vm.runInContext(source, context);

        await context.window.loadSession('session-1');

        if (host.hidden) throw new Error('Readable output host stayed hidden after session load');
        if (!host.innerHTML.includes('Readable output')) throw new Error('Readable output card did not render');
        if (!host.innerHTML.includes('/api/ops/sessions/session-1/readable-output/assets/assets/result.png')) {
          throw new Error('Readable output asset refs were not rewritten');
        }

        await context.window.newSession();

        if (!host.hidden) throw new Error('Readable output host did not clear on new session');
        if (!fetchCalls.includes('/api/ops/sessions/session-1/readable-output')) {
          throw new Error('Readable output session route was not requested');
        }
        console.log('ok');
        })().catch((error) => {
          console.error(error && error.stack ? error.stack : error);
          process.exit(1);
        });
        """
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "ok"

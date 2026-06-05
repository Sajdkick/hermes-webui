from pathlib import Path
import re
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[1]


def test_ops_session_inspect_keeps_composer_available():
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")

    assert "body.ops-session-inspect .rail" in css
    assert "body.ops-session-inspect .sidebar" in css
    assert "body.ops-session-inspect .rightpanel" in css
    assert "body.ops-session-inspect .ops-session-inspect-back:not([hidden])" in css
    hidden_selectors = re.findall(r"body\.ops-session-inspect [^{]+\{display:none!important;\}", css)
    assert all(".composer-wrap" not in selector for selector in hidden_selectors)


def test_ops_session_inspect_refresh_button_is_wired():
    index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    sessions_js = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")

    assert "id=\"opsSessionInspectRefresh\"" in index
    assert "onclick=\"forceRefreshOpsSessionInspectMode()\"" in index
    assert "body.ops-session-inspect .ops-session-inspect-refresh:not([hidden])" in css
    assert "window.forceRefreshOpsSessionInspectMode=forceRefreshOpsSessionInspectMode" in sessions_js
    assert "await loadSession(sid,{force:true})" in sessions_js
    assert "position:fixed" in css
    assert "z-index:1200" in css
    assert "pointer-events:auto" in css


def test_ops_session_inspect_refresh_uses_same_session_stale_response_guard():
    sessions_js = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")

    assert "let _loadingSessionSeq = 0" in sessions_js
    assert "const loadToken = _beginSessionLoad(sid)" in sessions_js
    assert "_isStaleSessionLoad(sid, loadToken)" in sessions_js
    assert "_clearSessionLoad(sid, loadToken)" in sessions_js


def test_forced_same_session_refresh_rebuilds_message_cache():
    sessions_js = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")

    assert "const explicitForce=options.force===true" in sessions_js
    assert "const resetConversationPane=currentSid!==sid||explicitForce||needsRecovery" in sessions_js
    assert "S.messages = [];" in sessions_js
    assert "Refreshing conversation…" in sessions_js


def test_play_session_overlay_requires_real_inspect_shell_before_showing_iframe():
    overlay_js = (ROOT / "static" / "play-session-overlay.js").read_text(encoding="utf-8")

    assert "function frameInspectReady()" in overlay_js
    assert "doc.body.classList.contains('ops-session-inspect')" in overlay_js
    assert "frame.classList.add('is-pending')" in overlay_js
    assert "frame.hidden=true" in overlay_js
    assert "scheduleFrameVerification()" in overlay_js
    assert "if(!frameLoadSeen)showFallback();" in overlay_js
    assert "loaded=true" not in overlay_js


def test_standalone_ops_host_resolves_root_relative_api_urls_from_session_pages():
    script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const code = fs.readFileSync({str(ROOT / 'static' / 'ops-legacy-host.js')!r}, 'utf8');
        const windowRef = {{
          location: {{ origin: 'http://example.test', href: 'http://example.test/session/sess-1?opsSessionInspect=1' }},
          localStorage: {{ getItem: () => null, setItem: () => null, removeItem: () => null }},
        }};
        const documentRef = {{
          baseURI: 'http://example.test/session/sess-1?opsSessionInspect=1',
          getElementById: () => null,
          createElement: () => ({{ className: '', id: '', style: {{}}, classList: {{ add: () => null, remove: () => null }}, remove: () => null }}),
          body: {{ appendChild: () => null }},
          addEventListener: () => null,
        }};
        const context = {{ console, window: windowRef, document: documentRef, URL, FormData, Headers, fetch: async () => ({{}}) }};
        vm.createContext(context);
        vm.runInContext(code, context, {{ filename: 'ops-legacy-host.js' }});
        const appUrl = context.window.__opsLegacyAppUrl;
        if (typeof appUrl !== 'function') throw new Error('standalone host did not export appUrl');
        const rootApi = appUrl('/api/session?session_id=sess-1');
        if (rootApi !== 'http://example.test/api/session?session_id=sess-1') {{
          throw new Error('Root API URL resolved relative to the session route: ' + rootApi);
        }}
        const relativeAsset = appUrl('static/app.js');
        if (relativeAsset !== 'http://example.test/session/static/app.js') {{
          throw new Error('Non-root relative URLs should still resolve against document.baseURI: ' + relativeAsset);
        }}
        console.log('ok');
        """
    )
    completed = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True, cwd=ROOT)
    assert completed.stdout.strip() == "ok"

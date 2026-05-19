from pathlib import Path
import re


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

"""Tests for /reasoning show|hide slash command and show_thinking setting.

Covers:
  - show_thinking in _SETTINGS_DEFAULTS and _SETTINGS_BOOL_KEYS (api/config.py)
  - window._showThinking initialised in boot.js (settings and fallback paths)
  - window._showThinking guard in ui.js renderMessages thinking card
  - _renderLiveThinking guard in messages.js
  - cmdReasoning function present in commands.js with show/hide/effort handling
  - /reasoning in COMMANDS array (not just SLASH_SUBARG_SOURCES)
  - show|hide present as subArgs in COMMANDS entry
"""

import io
import json
import pathlib
import re
from urllib.parse import urlparse

REPO = pathlib.Path(__file__).parent.parent


def read(rel):
    return (REPO / rel).read_text(encoding='utf-8')


class DummyHandler:
    def __init__(self, body: dict | None = None) -> None:
        self.command = "POST"
        raw = json.dumps(body or {}).encode('utf-8')
        self.headers = {'Content-Length': str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self.status = None
        self.response_headers = []

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.response_headers.append((key, value))

    def end_headers(self) -> None:
        pass

    def json_payload(self) -> dict:
        return json.loads(self.wfile.getvalue().decode('utf-8'))


# ── api/config.py ─────────────────────────────────────────────────────────────

class TestShowThinkingConfig:
    """show_thinking must appear in defaults and bool keys."""

    def test_show_thinking_in_defaults(self):
        src = read('api/config.py')
        assert '"show_thinking": True' in src, (
            "show_thinking must be True in _SETTINGS_DEFAULTS"
        )

    def test_show_thinking_in_bool_keys(self):
        src = read('api/config.py')
        assert '"show_thinking"' in src
        # Find the _SETTINGS_BOOL_KEYS set and confirm show_thinking is in it
        m = re.search(r'_SETTINGS_BOOL_KEYS\s*=\s*\{([^}]+)\}', src, re.DOTALL)
        assert m, "_SETTINGS_BOOL_KEYS not found"
        assert 'show_thinking' in m.group(1), (
            "show_thinking must be in _SETTINGS_BOOL_KEYS"
        )


# ── static/boot.js ────────────────────────────────────────────────────────────

class TestBootJsShowThinking:
    """window._showThinking must be set in both the settings and fallback paths."""

    def test_settings_path_initialises_show_thinking(self):
        src = read('static/boot.js')
        # Must read from the settings object, defaulting true when absent
        assert 'window._showThinking=s.show_thinking!==false' in src, (
            "boot.js must initialise _showThinking from settings (default true)"
        )

    def test_fallback_path_initialises_show_thinking_true(self):
        src = read('static/boot.js')
        assert 'window._showThinking=true' in src, (
            "boot.js fallback path must default _showThinking to true"
        )


# ── static/ui.js ──────────────────────────────────────────────────────────────

class TestUiJsThinkingGate:
    """Historical thinking cards must be gated by window._showThinking."""

    def test_thinking_card_gated_in_render_messages(self):
        src = read('static/ui.js')
        assert 'window._showThinking!==false' in src, (
            "ui.js must gate thinkingCardHtml on window._showThinking"
        )
        # The guard must be on the same line as _thinkingCardHtml insertion
        lines = src.splitlines()
        for line in lines:
            if '_thinkingCardHtml' in line and 'insertAdjacentHTML' in line:
                assert 'window._showThinking' in line, (
                    f"thinking card insertion must be gated: {line.strip()}"
                )
                break


# ── static/messages.js ────────────────────────────────────────────────────────

class TestMessagesJsLiveThinkingGate:
    """Live streaming thinking card must be hidden when _showThinking is false."""

    def test_live_thinking_gated(self):
        src = read('static/messages.js')
        assert 'window._showThinking===false' in src, (
            "messages.js _renderLiveThinking must early-return when _showThinking is false"
        )
        # Guard must be inside _renderLiveThinking
        m = re.search(r'function _renderLiveThinking\(.*?\{(.*?)^\s*\}',
                      src, re.DOTALL | re.MULTILINE)
        assert m, "_renderLiveThinking not found"
        assert 'window._showThinking' in m.group(1)


# ── static/commands.js ────────────────────────────────────────────────────────

class TestReasoningCommand:
    """cmdReasoning must be wired into COMMANDS with show/hide subArgs."""

    def test_reasoning_in_commands_array(self):
        src = read('static/commands.js')
        # Must appear in COMMANDS array (not just SLASH_SUBARG_SOURCES)
        m = re.search(r'const COMMANDS\s*=\s*\[(.*?)\];', src, re.DOTALL)
        assert m, "COMMANDS array not found"
        commands_block = m.group(1)
        assert 'reasoning' in commands_block, (
            "/reasoning must be in the COMMANDS array with a fn: handler"
        )
        assert 'fn:cmdReasoning' in commands_block or "fn: cmdReasoning" in commands_block, (
            "/reasoning entry must reference cmdReasoning"
        )

    def test_reasoning_subargs_include_show_hide(self):
        src = read('static/commands.js')
        m = re.search(r'const COMMANDS\s*=\s*\[(.*?)\];', src, re.DOTALL)
        assert m
        commands_block = m.group(1)
        # Find the reasoning entry
        rm = re.search(r"\{name:'reasoning'.*?\}", commands_block, re.DOTALL)
        assert rm, "reasoning entry not found in COMMANDS"
        entry = rm.group(0)
        assert 'show' in entry, "subArgs must include 'show'"
        assert 'hide' in entry, "subArgs must include 'hide'"

    def test_reasoning_not_only_in_subarg_sources(self):
        src = read('static/commands.js')
        # It's fine if SLASH_SUBARG_SOURCES is empty or doesn't have reasoning
        # (reasoning moved to COMMANDS with a real fn)
        m = re.search(r'const SLASH_SUBARG_SOURCES\s*=\s*\{(.*?)\};', src, re.DOTALL)
        if m:
            subarg_block = m.group(1)
            assert 'reasoning' not in subarg_block, (
                "reasoning must not remain in SLASH_SUBARG_SOURCES once it has a fn: handler"
            )

    def test_cmd_reasoning_function_exists(self):
        src = read('static/commands.js')
        assert 'function cmdReasoning' in src, (
            "cmdReasoning function must be defined"
        )

    def test_cmd_reasoning_handles_show(self):
        src = read('static/commands.js')
        m = re.search(r'function cmdReasoning\(.*?\n\}', src, re.DOTALL)
        assert m, "cmdReasoning not found"
        fn = m.group(0)
        # Handler must write to the UI render gate (assignment may use a
        # boolean literal or a locally-computed variable) and call renderMessages.
        assert re.search(r'window\._showThinking\s*=\s*(?:true|on)\b', fn), (
            "cmdReasoning show branch must assign true/on to window._showThinking"
        )
        assert 'renderMessages' in fn, (
            "show/hide branch must call renderMessages()"
        )
        # Persistence: POST to /api/reasoning (CLI-shared config.yaml) AND
        # /api/settings (boot.js mirror).
        assert "api('/api/reasoning'" in fn, (
            "show/hide branch must POST to /api/reasoning so config.yaml "
            "display.show_reasoning is updated (CLI parity)"
        )
        assert 'show_thinking' in fn, (
            "show/hide branch must also mirror show_thinking into "
            "WebUI settings.json for boot.js hydration"
        )

    def test_cmd_reasoning_handles_hide(self):
        src = read('static/commands.js')
        m = re.search(r'function cmdReasoning\(.*?\n\}', src, re.DOTALL)
        assert m
        fn = m.group(0)
        # The hide branch shares logic with show via a computed `on` variable;
        # the combined branch must test for both show|on and hide|off.
        assert "arg==='hide'" in fn, "hide branch missing"
        assert "arg==='off'" in fn, "off alias missing"

    def test_cmd_reasoning_i18n_key_exists(self):
        i18n = read('static/i18n.js')
        assert 'cmd_reasoning' in i18n, (
            "i18n.js must define the cmd_reasoning key"
        )

    def test_cmd_reasoning_posts_api_endpoints_not_gets(self):
        """Regression: the api() helper spreads its 2nd arg into fetch(), so
        passing a plain options object without method:'POST' silently becomes
        a GET and the update is dropped.  Every mutating call inside
        cmdReasoning (/api/reasoning, /api/settings) must be a proper POST."""
        src = read('static/commands.js')
        m = re.search(r'function cmdReasoning\(.*?\n\}', src, re.DOTALL)
        assert m
        fn = m.group(0)
        # Every write call — /api/reasoning and /api/settings — must be a POST.
        write_calls = re.findall(
            r"api\('/api/(?:reasoning|settings)'\s*,[^)]*\)", fn
        )
        assert write_calls, "cmdReasoning must POST to /api/reasoning or /api/settings"
        for call in write_calls:
            assert "method:'POST'" in call or 'method: "POST"' in call, (
                f"write call missing method:'POST' — would fall through "
                f"to GET and silently drop the update: {call}"
            )
            assert 'JSON.stringify' in call, (
                f"write call missing JSON body: {call}"
            )

    def test_cmd_reasoning_routes_effort_through_api_reasoning(self):
        """Effort levels POST to /api/reasoning. In WebUI chats they default
        to a session-local override; explicit profile/global scope updates the
        profile default."""
        src = read('static/commands.js')
        m = re.search(r'function cmdReasoning\(.*?\n\}', src, re.DOTALL)
        assert m
        fn = m.group(0)
        assert "api('/api/reasoning'" in fn, (
            "cmdReasoning must POST effort levels to /api/reasoning"
        )
        assert 'effort:effort' in fn or 'effort: effort' in fn or '_payloadForEffort(effort' in fn, (
            "effort-level branch must send {effort: <level>} to /api/reasoning"
        )
        assert "payload.scope='session'" in fn or "scope:'session'" in fn, (
            "/reasoning <level> must default to a session-scoped override when a session is active"
        )
        assert "profile <level>" in fn, (
            "/reasoning profile <level> must remain available for profile-wide defaults"
        )
        assert '_reasoningEffort=' not in fn, (
            "cmdReasoning must not keep a dead client-side _reasoningEffort "
            "(effort now round-trips through /api/reasoning)"
        )

    def test_cmd_reasoning_supports_session_default_clear(self):
        src = read('static/commands.js')
        assert "'default'" in src, (
            "/reasoning default must clear the current session override back to the profile default"
        )
        assert "default only clears this session" in src

    def test_composer_reasoning_chip_posts_session_scope(self):
        src = read('static/ui.js')
        assert "params.set('session_id'" in src, (
            "reasoning status GET must include session_id so the chip shows the session override"
        )
        assert 'function _reasoningMutationPayload' in src
        assert "payload.scope='session'" in src, (
            "composer reasoning dropdown must POST session-scoped effort by default"
        )
        assert "session_reasoning_effort" in src and "profile_reasoning_effort" in src
        html = read('static/index.html')
        assert 'data-effort=""' in html and 'Use profile default' in html, (
            "dropdown must expose a way to clear the session override"
        )

    def test_cmd_reasoning_routes_display_through_api_reasoning(self):
        """show|hide|on|off must POST to /api/reasoning (config.yaml
        display.show_reasoning — the CLI's key) in addition to mirroring
        into WebUI settings.json for boot.js hydration."""
        src = read('static/commands.js')
        m = re.search(r'function cmdReasoning\(.*?\n\}', src, re.DOTALL)
        assert m
        fn = m.group(0)
        assert 'display:arg' in fn or 'display: arg' in fn or "'display'" in fn, (
            "show|hide branch must send {display: arg} to /api/reasoning so "
            "config.yaml display.show_reasoning matches the CLI's source"
        )

    def test_cmd_reasoning_supports_all_cli_effort_levels(self):
        """The effort-level set must match hermes_constants.VALID_REASONING_EFFORTS
        + 'none' — i.e. the exact set the CLI accepts in /reasoning."""
        src = read('static/commands.js')
        m = re.search(r'function cmdReasoning\(.*?\n\}', src, re.DOTALL)
        assert m
        fn = m.group(0)
        for level in ('none', 'minimal', 'low', 'medium', 'high', 'xhigh'):
            assert f"'{level}'" in fn, (
                f"cmdReasoning must accept '{level}' (CLI parity with "
                f"hermes_constants.parse_reasoning_effort)"
            )

    def test_reasoning_subargs_match_cli_levels(self):
        """Autocomplete subArgs must expose every CLI effort level + show/hide."""
        src = read('static/commands.js')
        m = re.search(r"\{name:'reasoning'[^}]*\}", src, re.DOTALL)
        assert m, "reasoning COMMANDS entry not found"
        entry = m.group(0)
        for suggestion in (
            'show', 'hide', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh'
        ):
            assert f"'{suggestion}'" in entry, (
                f"reasoning subArgs must include '{suggestion}' for CLI parity"
            )


# ── api/config.py — reasoning helpers ────────────────────────────────────────

class TestReasoningConfigHelpers:
    """Validate that api/config.py exposes the CLI-parity helpers and that
    they read/write the same keys the CLI uses."""

    def test_parse_reasoning_effort_matches_cli_semantics(self):
        from api.config import parse_reasoning_effort, VALID_REASONING_EFFORTS
        # Empty → None
        assert parse_reasoning_effort('') is None
        assert parse_reasoning_effort(None) is None
        # none → disabled
        assert parse_reasoning_effort('none') == {'enabled': False}
        # Each valid level → {enabled, effort}
        for level in VALID_REASONING_EFFORTS:
            assert parse_reasoning_effort(level) == {'enabled': True, 'effort': level}
        # Unknown → None (fall back to default)
        assert parse_reasoning_effort('garbage') is None
        # Case-insensitive + trimmed
        assert parse_reasoning_effort('  HIGH  ') == {'enabled': True, 'effort': 'high'}

    def test_valid_reasoning_efforts_matches_hermes_constants(self):
        """Ensure our mirror stays in sync with hermes_constants."""
        from api.config import VALID_REASONING_EFFORTS
        # Snapshot-style assertion: if hermes_constants adds a level, this
        # test will fail fast so we know to update WebUI too.
        assert VALID_REASONING_EFFORTS == (
            'minimal', 'low', 'medium', 'high', 'xhigh', 'max'
        )

    def test_set_reasoning_effort_persists_to_config_yaml(self, tmp_path, monkeypatch):
        """set_reasoning_effort writes agent.reasoning_effort to the active
        profile's config.yaml — the same key the CLI writes."""
        import api.config as cfg
        cfgfile = tmp_path / 'config.yaml'
        monkeypatch.setattr(cfg, '_get_config_path', lambda: cfgfile)
        cfg.set_reasoning_effort('high')
        import yaml as _yaml
        data = _yaml.safe_load(cfgfile.read_text(encoding='utf-8'))
        assert data.get('agent', {}).get('reasoning_effort') == 'high', (
            "agent.reasoning_effort must be persisted to config.yaml"
        )

    def test_set_reasoning_display_persists_to_config_yaml(self, tmp_path, monkeypatch):
        """set_reasoning_display writes display.show_reasoning to the same
        config.yaml the CLI writes."""
        import api.config as cfg
        cfgfile = tmp_path / 'config.yaml'
        monkeypatch.setattr(cfg, '_get_config_path', lambda: cfgfile)
        cfg.set_reasoning_display(False)
        import yaml as _yaml
        data = _yaml.safe_load(cfgfile.read_text(encoding='utf-8'))
        assert data.get('display', {}).get('show_reasoning') is False, (
            "display.show_reasoning must be persisted to config.yaml"
        )
        cfg.set_reasoning_display(True)
        data = _yaml.safe_load(cfgfile.read_text(encoding='utf-8'))
        assert data.get('display', {}).get('show_reasoning') is True

    def test_set_reasoning_effort_rejects_invalid(self, tmp_path, monkeypatch):
        import api.config as cfg
        monkeypatch.setattr(cfg, '_get_config_path', lambda: tmp_path / 'config.yaml')
        import pytest as _pt
        with _pt.raises(ValueError):
            cfg.set_reasoning_effort('garbage')
        with _pt.raises(ValueError):
            cfg.set_reasoning_effort('')

    def test_get_reasoning_status_defaults_to_show_true(self, tmp_path, monkeypatch):
        """When config.yaml has no display section, show_reasoning defaults
        to True (matches CLI default where the setting is opt-in)."""
        import api.config as cfg
        monkeypatch.setattr(cfg, '_get_config_path', lambda: tmp_path / 'config.yaml')
        st = cfg.get_reasoning_status()
        assert st['show_reasoning'] is True
        assert st['reasoning_effort'] == ''
        assert st['profile_reasoning_effort'] == ''
        assert st['session_reasoning_effort'] == ''
        assert st['reasoning_scope'] == 'profile'

    def test_get_reasoning_status_overlays_session_effort(self, tmp_path, monkeypatch):
        import yaml as _yaml
        import api.config as cfg
        cfgfile = tmp_path / 'config.yaml'
        cfgfile.write_text(_yaml.safe_dump({'agent': {'reasoning_effort': 'xhigh'}}), encoding='utf-8')
        monkeypatch.setattr(cfg, '_get_config_path', lambda: cfgfile)

        st = cfg.get_reasoning_status(session_effort='low')
        assert st['reasoning_effort'] == 'low'
        assert st['profile_reasoning_effort'] == 'xhigh'
        assert st['session_reasoning_effort'] == 'low'
        assert st['reasoning_scope'] == 'session'

        inherited = cfg.get_reasoning_status(session_effort='default')
        assert inherited['reasoning_effort'] == 'xhigh'
        assert inherited['session_reasoning_effort'] == ''
        assert inherited['reasoning_scope'] == 'profile'

    def test_normalize_reasoning_effort_value_allows_session_default(self):
        import pytest as _pt
        from api.config import normalize_reasoning_effort_value
        assert normalize_reasoning_effort_value('DEFAULT', allow_default=True) == ''
        assert normalize_reasoning_effort_value(' high ') == 'high'
        assert normalize_reasoning_effort_value('none') == 'none'
        with _pt.raises(ValueError):
            normalize_reasoning_effort_value('default')
        with _pt.raises(ValueError):
            normalize_reasoning_effort_value('bogus', allow_default=True)


# ── api/streaming.py — AIAgent receives reasoning_config ──────────────────────

class TestStreamingReasoningWiring:
    """Confirm api/streaming.py reads profile/session reasoning effort and
    passes parsed reasoning_config to AIAgent."""

    def test_streaming_reads_reasoning_effort_from_session_or_config(self):
        src = read('api/streaming.py')
        assert 'parse_reasoning_effort' in src, (
            "api/streaming.py must import parse_reasoning_effort to translate "
            "config.yaml agent.reasoning_effort into AIAgent reasoning_config"
        )
        assert 'coerce_reasoning_effort_for_model' in src, (
            "api/streaming.py must clamp/drop unsupported model-specific effort "
            "levels before sending reasoning_config to the provider"
        )
        assert "getattr(s, 'reasoning_effort', None)" in src, (
            "streaming must prefer a persisted per-session reasoning override "
            "before falling back to profile config"
        )
        assert "reasoning_config" in src and "'reasoning_config' in _agent_params" in src, (
            "api/streaming.py must guard the reasoning_config kwarg with "
            "inspect.signature so older hermes-agent builds don't TypeError"
        )


# ── api/routes.py — /api/reasoning endpoints ──────────────────────────────────

class TestReasoningRoutes:

    def test_get_api_reasoning_route_exists(self):
        src = read('api/routes.py')
        assert 'parsed.path == "/api/reasoning"' in src, (
            "GET /api/reasoning route must exist"
        )
        assert 'get_reasoning_status' in src, (
            "api/routes.py must import and call get_reasoning_status"
        )

    def test_post_api_reasoning_accepts_display(self):
        src = read('api/routes.py')
        # The POST branch reads 'display' from body and dispatches to
        # set_reasoning_display.
        assert 'set_reasoning_display' in src, (
            "POST /api/reasoning must route display toggles through "
            "set_reasoning_display"
        )

    def test_post_api_reasoning_accepts_effort(self):
        src = read('api/routes.py')
        assert 'set_reasoning_effort' in src, (
            "POST /api/reasoning must still support profile/global effort changes"
        )
        assert 'scope == "session"' in src, (
            "POST /api/reasoning must support session-scoped reasoning effort"
        )
        assert 's.reasoning_effort = normalized or None' in src, (
            "session-scoped default must clear the persisted session override"
        )
        assert 'normalize_reasoning_effort_value(effort, allow_default=True)' in src

    def test_post_api_reasoning_session_effort_does_not_mutate_profile(self, tmp_path, monkeypatch):
        import yaml as _yaml
        from api import config as cfg
        from api import models
        from api import routes

        cfgfile = tmp_path / 'config.yaml'
        cfgfile.write_text(_yaml.safe_dump({'agent': {'reasoning_effort': 'xhigh'}}), encoding='utf-8')
        session_dir = tmp_path / 'sessions'
        session_dir.mkdir()
        monkeypatch.setattr(cfg, '_get_config_path', lambda: cfgfile)
        monkeypatch.setattr(models, 'SESSION_DIR', session_dir)
        monkeypatch.setattr(models, 'SESSION_INDEX_FILE', session_dir / '_index.json')
        with models.LOCK:
            models.SESSIONS.clear()

        session = models.new_session(workspace=str(tmp_path / 'workspace'))
        handler = DummyHandler({'session_id': session.session_id, 'scope': 'session', 'effort': 'low'})
        result = routes.handle_post(
            handler,
            urlparse('/api/reasoning'),
        )
        assert result in (True, None)
        payload = handler.json_payload()
        assert handler.status == 200
        assert payload['reasoning_effort'] == 'low'
        assert payload['profile_reasoning_effort'] == 'xhigh'
        assert payload['session_reasoning_effort'] == 'low'
        assert payload['reasoning_scope'] == 'session'
        assert _yaml.safe_load(cfgfile.read_text(encoding='utf-8'))['agent']['reasoning_effort'] == 'xhigh'
        assert models.get_session(session.session_id).reasoning_effort == 'low'

        handler = DummyHandler({'session_id': session.session_id, 'scope': 'session', 'effort': 'default'})
        result = routes.handle_post(
            handler,
            urlparse('/api/reasoning'),
        )
        assert result in (True, None)
        payload = handler.json_payload()
        assert handler.status == 200
        assert payload['reasoning_effort'] == 'xhigh'
        assert payload['session_reasoning_effort'] == ''
        assert payload['reasoning_scope'] == 'profile'
        assert models.get_session(session.session_id).reasoning_effort is None
        assert _yaml.safe_load(cfgfile.read_text(encoding='utf-8'))['agent']['reasoning_effort'] == 'xhigh'

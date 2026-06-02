import importlib
import os
import sys
from pathlib import Path


def test_profile_switch_clears_previous_profile_env_vars(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    (base / "profiles" / "p1").mkdir(parents=True)
    (base / "profiles" / "p2").mkdir(parents=True)
    (base / "profiles" / "p1" / ".env").write_text(
        "OPENAI_API_KEY=secret-from-p1\nCUSTOM_TOKEN=token-from-p1\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HERMES_BASE_HOME", str(base))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CUSTOM_TOKEN", raising=False)

    # Use monkeypatch so sys.modules is restored after the test, preventing
    # api.profiles from being permanently removed and poisoning subsequent tests.
    monkeypatch.delitem(sys.modules, "api.profiles", raising=False)
    profiles = importlib.import_module("api.profiles")

    profiles.init_profile_state()
    profiles.switch_profile("p1")
    assert os.environ.get("OPENAI_API_KEY") == "secret-from-p1"
    assert os.environ.get("CUSTOM_TOKEN") == "token-from-p1"

    profiles.switch_profile("p2")
    assert os.environ.get("OPENAI_API_KEY") is None
    assert os.environ.get("CUSTOM_TOKEN") is None
    assert profiles.get_active_profile_name() == "p2"


def test_profile_switch_replaces_overlapping_keys(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    (base / "profiles" / "p1").mkdir(parents=True)
    (base / "profiles" / "p2").mkdir(parents=True)
    (base / "profiles" / "p1" / ".env").write_text(
        "OPENAI_API_KEY=secret-from-p1\nONLY_P1=one\n",
        encoding="utf-8",
    )
    (base / "profiles" / "p2" / ".env").write_text(
        "OPENAI_API_KEY=secret-from-p2\nONLY_P2=two\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HERMES_BASE_HOME", str(base))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ONLY_P1", raising=False)
    monkeypatch.delenv("ONLY_P2", raising=False)

    # Use monkeypatch so sys.modules is restored after the test, preventing
    # api.profiles from being permanently removed and poisoning subsequent tests.
    monkeypatch.delitem(sys.modules, "api.profiles", raising=False)
    profiles = importlib.import_module("api.profiles")

    profiles.init_profile_state()
    profiles.switch_profile("p1")
    assert os.environ.get("OPENAI_API_KEY") == "secret-from-p1"
    assert os.environ.get("ONLY_P1") == "one"

    profiles.switch_profile("p2")
    assert os.environ.get("OPENAI_API_KEY") == "secret-from-p2"
    assert os.environ.get("ONLY_P1") is None
    assert os.environ.get("ONLY_P2") == "two"


def test_streaming_sets_context_local_hermes_home_override_for_agent_tools():
    """Direct WebUI chats must not rely on process-global HERMES_HOME during tool calls."""
    src = Path("api/streaming.py").read_text(encoding="utf-8")
    setup_idx = src.index("_thread_env = _build_agent_thread_env(")
    set_idx = src.index("set_hermes_home_override", setup_idx)
    thread_env_idx = src.index("_set_thread_env(**_thread_env)", setup_idx)
    reset_idx = src.index("_reset_hermes_home_override(_hermes_home_override_token)", set_idx)
    clear_idx = src.index("_clear_thread_env()", reset_idx)

    assert set_idx < thread_env_idx
    assert reset_idx < clear_idx


def test_terminal_subprocess_env_prefers_context_hermes_home_override(monkeypatch, tmp_path):
    """Hermes Agent local terminal env should bridge context-local HERMES_HOME to shells."""
    import api.config  # noqa: F401 - ensures hermes-agent is on sys.path
    hermes_constants = importlib.import_module("hermes_constants")
    local_env = importlib.import_module("tools.environments.local")

    reset_hermes_home_override = hermes_constants.reset_hermes_home_override
    set_hermes_home_override = hermes_constants.set_hermes_home_override
    _make_run_env = local_env._make_run_env

    process_home = tmp_path / "profiles" / "summons"
    session_home = tmp_path / "profiles" / "laxlyftet"
    monkeypatch.setenv("HERMES_HOME", str(process_home))

    token = set_hermes_home_override(session_home)
    try:
        run_env = _make_run_env({})
    finally:
        reset_hermes_home_override(token)

    assert run_env["HERMES_HOME"] == str(session_home)

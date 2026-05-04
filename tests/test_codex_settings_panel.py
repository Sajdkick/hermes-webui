import stat
from types import SimpleNamespace

import pytest

from api import codex_settings, routes


def test_codex_config_load_returns_empty_payload_when_missing(tmp_path, monkeypatch):
    config_path = tmp_path / ".codex" / "config.toml"
    monkeypatch.setenv("CODEX_CONFIG_PATH", str(config_path))

    payload = codex_settings.load_codex_config()

    assert payload == {
        "path": str(config_path),
        "content": "",
    }


def test_codex_config_save_normalizes_newlines_and_writes_private_file(tmp_path, monkeypatch):
    config_path = tmp_path / ".codex" / "config.toml"
    monkeypatch.setenv("CODEX_CONFIG_PATH", str(config_path))

    payload = codex_settings.save_codex_config("[profiles]\r\nactive = 'default'")

    assert payload["ok"] is True
    assert payload["path"] == str(config_path)
    assert payload["content"] == "[profiles]\nactive = 'default'\n"
    assert config_path.read_text(encoding="utf-8") == "[profiles]\nactive = 'default'\n"
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600


def test_codex_config_save_rejects_oversized_content(tmp_path, monkeypatch):
    config_path = tmp_path / ".codex" / "config.toml"
    monkeypatch.setenv("CODEX_CONFIG_PATH", str(config_path))

    with pytest.raises(ValueError, match="too large"):
        codex_settings.save_codex_config("x" * (codex_settings.MAX_CODEX_CONFIG_BYTES + 1))


def test_routes_expose_codex_config_get_and_post(monkeypatch):
    responses = []

    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    monkeypatch.setattr(routes, "read_body", lambda _handler: {"content": "[profiles]\nactive='default'\n"})
    monkeypatch.setattr(
        routes,
        "j",
        lambda _handler, payload, status=200: responses.append((status, payload)) or True,
    )
    monkeypatch.setattr(
        codex_settings,
        "load_codex_config",
        lambda: {"path": "/tmp/.codex/config.toml", "content": "foo='bar'\n"},
    )
    monkeypatch.setattr(
        codex_settings,
        "save_codex_config",
        lambda content: {"ok": True, "path": "/tmp/.codex/config.toml", "content": content},
    )

    handler = SimpleNamespace(command="POST", headers={}, host="127.0.0.1")

    assert routes.handle_get(handler, SimpleNamespace(path="/api/codex-config", query="")) is True
    assert routes.handle_post(handler, SimpleNamespace(path="/api/codex-config", query="")) is True
    assert responses == [
        (200, {"path": "/tmp/.codex/config.toml", "content": "foo='bar'\n"}),
        (200, {"ok": True, "path": "/tmp/.codex/config.toml", "content": "[profiles]\nactive='default'\n"}),
    ]

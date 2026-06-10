from pathlib import Path
from urllib.parse import urlparse


def isolate_managed_postgres(monkeypatch, tmp_path: Path):
    from api import managed_postgres

    root = tmp_path / "hermes-state" / "core" / "managed-postgres"
    monkeypatch.setattr(managed_postgres, "MANAGED_POSTGRES_DIR", root)
    monkeypatch.setattr(managed_postgres, "SETTINGS_FILE", root / "settings.json")
    monkeypatch.setattr(managed_postgres, "RUNTIME_FILE", root / "runtime.json")
    monkeypatch.setattr(managed_postgres, "DEFAULT_DATA_DIR", root / "data")
    monkeypatch.setattr(managed_postgres, "DEFAULT_SOCKET_DIR", root / "socket")
    monkeypatch.setattr(managed_postgres, "LOG_FILE", root / "postgres.log")
    return managed_postgres


def test_managed_postgres_settings_are_hermes_owned(monkeypatch, tmp_path):
    managed_postgres = isolate_managed_postgres(monkeypatch, tmp_path)

    settings = managed_postgres.read_settings()

    assert managed_postgres.SETTINGS_FILE == tmp_path / "hermes-state" / "core" / "managed-postgres" / "settings.json"
    assert settings["enabled"] is True
    assert settings["mode"] == "local"
    assert settings["credentials"]["user"] == "hermes_admin"
    assert settings["credentials"]["databasePrefix"] == "hermes"
    assert settings["credentials"]["password"]
    assert managed_postgres.SETTINGS_FILE.exists()


def test_managed_postgres_context_provisions_project_database_env(monkeypatch, tmp_path):
    managed_postgres = isolate_managed_postgres(monkeypatch, tmp_path)
    settings = managed_postgres.read_settings()
    ensured = []
    monkeypatch.setattr(
        managed_postgres,
        "start_local_postgres",
        lambda _settings: {"host": "127.0.0.1", "port": 5544, "pid": 123, "dataDir": str(tmp_path / "data")},
    )
    monkeypatch.setattr(managed_postgres, "_ensure_database_exists", lambda connection, _settings: ensured.append(connection))

    context = managed_postgres.ensure_project_database("Project With Spaces")
    env = context.env

    assert context.enabled is True
    assert context.mode == "local"
    assert ensured and ensured[0]["database"] == "hermes_project_with_spaces"
    assert ensured[0]["user"] == settings["credentials"]["user"]
    assert env["DATASTORE_ADAPTER"] == "postgres"
    assert env["DATABASE_URL"] == ensured[0]["url"]
    assert env["DATASTORE_POSTGRES_URL"] == ensured[0]["url"]
    assert env["NAKAMA_DATABASE_URL"] == ensured[0]["url"]
    assert env["PGHOST"] == "127.0.0.1"
    assert env["PGPORT"] == "5544"
    assert env["PGDATABASE"] == "hermes_project_with_spaces"


def test_managed_postgres_external_mode_keeps_aliases_aligned(monkeypatch, tmp_path):
    managed_postgres = isolate_managed_postgres(monkeypatch, tmp_path)
    settings = managed_postgres.read_settings()
    settings["mode"] = "external"
    settings["external"]["url"] = "postgresql://db-user:db-pass@db.example.com:5432/shared"
    managed_postgres.write_settings(settings)

    context = managed_postgres.ensure_project_database("project-a")
    env = context.env
    parsed = urlparse(context.connection["url"])

    assert context.mode == "external"
    assert parsed.path == "/hermes_project_a"
    assert env["DATABASE_URL"] == context.connection["url"]
    assert env["DATASTORE_POSTGRES_URL"] == context.connection["url"]
    assert env["NAKAMA_DATABASE_URL"] == context.connection["url"]

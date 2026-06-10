"""Hermes-owned managed Postgres runtime for Core/Play workflows."""

from __future__ import annotations

import json
import hashlib
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import parse as urlparse

from api.config import STATE_DIR


DEFAULT_DB_PORT = 5432
DEFAULT_DB_HOST = "127.0.0.1"
DEFAULT_DB_USER = "hermes_admin"
DEFAULT_DB_PREFIX = "hermes"
DEFAULT_PORT_SCAN_RANGE = {"min": 5432, "max": 5499}

MANAGED_POSTGRES_DIR = STATE_DIR / "core" / "managed-postgres"
SETTINGS_FILE = MANAGED_POSTGRES_DIR / "settings.json"
RUNTIME_FILE = MANAGED_POSTGRES_DIR / "runtime.json"
DEFAULT_DATA_DIR = MANAGED_POSTGRES_DIR / "data"
LOG_FILE = MANAGED_POSTGRES_DIR / "postgres.log"

_LOCK = threading.RLock()
_LOCAL_STATE: dict[str, Any] = {
    "process": None,
    "pid": None,
    "host": None,
    "port": None,
    "data_dir": None,
}


class ManagedPostgresError(Exception):
    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class ManagedDatabaseContext:
    enabled: bool
    mode: str
    env: dict[str, str]
    connection: dict[str, Any] | None = None


def _generate_password() -> str:
    return secrets.token_urlsafe(18)


def _default_socket_dir() -> Path:
    digest = hashlib.sha256(str(STATE_DIR).encode("utf-8")).hexdigest()[:12]
    base = Path(os.getenv("XDG_RUNTIME_DIR") or tempfile.gettempdir())
    return base / f"hermes-pg-{digest}"


DEFAULT_SOCKET_DIR = _default_socket_dir()


def _sanitize_identifier(value: str, fallback: str = "db") -> str:
    raw = str(value or "").lower()
    sanitized = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw)
    sanitized = sanitized.strip("_")[:52]
    return sanitized or fallback


def build_database_name(project_id: str, settings: dict | None = None) -> str:
    credentials = settings.get("credentials") if isinstance(settings, dict) else {}
    if not isinstance(credentials, dict):
        credentials = {}
    prefix = _sanitize_identifier(str(credentials.get("databasePrefix") or DEFAULT_DB_PREFIX), DEFAULT_DB_PREFIX)
    suffix = _sanitize_identifier(project_id or "project", "project")
    return f"{prefix}_{suffix}"[:63]


def _normalize_port(value: Any, fallback: int = DEFAULT_DB_PORT) -> int:
    if isinstance(value, str):
        trimmed = value.strip().lower()
        if not trimmed or trimmed == "auto":
            return 0
        try:
            parsed = int(trimmed)
        except ValueError:
            return fallback
        return parsed if parsed > 0 else fallback
    if isinstance(value, int):
        return value if value > 0 else 0
    return fallback


def _create_default_settings() -> dict:
    return {
        "enabled": True,
        "mode": "local",
        "local": {
            "host": DEFAULT_DB_HOST,
            "port": DEFAULT_DB_PORT,
            "dataDir": "",
            "binDir": "",
            "allowPortFallback": True,
        },
        "external": {
            "url": "",
        },
        "credentials": {
            "user": DEFAULT_DB_USER,
            "password": _generate_password(),
            "databasePrefix": DEFAULT_DB_PREFIX,
        },
    }


def _normalize_settings(raw: dict | None) -> dict:
    defaults = _create_default_settings()
    raw = raw if isinstance(raw, dict) else {}
    raw_local = raw.get("local") if isinstance(raw.get("local"), dict) else {}
    raw_external = raw.get("external") if isinstance(raw.get("external"), dict) else {}
    raw_credentials = raw.get("credentials") if isinstance(raw.get("credentials"), dict) else {}
    return {
        "enabled": raw.get("enabled") is not False,
        "mode": "external" if raw.get("mode") == "external" else "local",
        "local": {
            "host": str(raw_local.get("host") or defaults["local"]["host"]).strip() or DEFAULT_DB_HOST,
            "port": _normalize_port(raw_local.get("port"), DEFAULT_DB_PORT),
            "dataDir": str(raw_local.get("dataDir") or "").strip(),
            "binDir": str(raw_local.get("binDir") or "").strip(),
            "allowPortFallback": raw_local.get("allowPortFallback") is not False,
        },
        "external": {
            "url": str(raw_external.get("url") or "").strip(),
        },
        "credentials": {
            "user": str(raw_credentials.get("user") or defaults["credentials"]["user"]).strip() or DEFAULT_DB_USER,
            "password": str(raw_credentials.get("password") or defaults["credentials"]["password"]).strip(),
            "databasePrefix": str(raw_credentials.get("databasePrefix") or defaults["credentials"]["databasePrefix"]).strip()
            or DEFAULT_DB_PREFIX,
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_settings() -> dict:
    with _LOCK:
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            settings = _create_default_settings()
            _write_json(SETTINGS_FILE, settings)
            return settings
        except json.JSONDecodeError as exc:
            raise ManagedPostgresError(f"Managed Postgres settings contain invalid JSON: {SETTINGS_FILE}") from exc
        settings = _normalize_settings(raw)
        if settings != raw:
            _write_json(SETTINGS_FILE, settings)
        return settings


def write_settings(settings: dict) -> dict:
    normalized = _normalize_settings(settings)
    with _LOCK:
        _write_json(SETTINGS_FILE, normalized)
    return normalized


def _resolve_path(value: str, fallback: Path) -> Path:
    return Path(value).expanduser().resolve() if value else fallback


def _resolve_binary(name: str, bin_dir: str = "") -> str:
    if bin_dir:
        candidate = Path(bin_dir).expanduser() / name
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    postgres_root = Path("/usr/lib/postgresql")
    try:
        version_dirs = sorted(postgres_root.iterdir(), key=lambda item: item.name, reverse=True)
    except OSError:
        version_dirs = []
    for version_dir in version_dirs:
        candidate = version_dir / "bin" / name
        if candidate.exists():
            return str(candidate)
    return name


def _binary_available(path: str) -> bool:
    return shutil.which(path) is not None or Path(path).exists()


def _is_process_alive(pid: Any) -> bool:
    try:
        numeric = int(pid)
    except (TypeError, ValueError):
        return False
    if numeric <= 0:
        return False
    try:
        os.kill(numeric, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _is_port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _find_available_port(host: str, minimum: int = 5432, maximum: int = 5499) -> int | None:
    for port in range(int(minimum), int(maximum) + 1):
        if not _is_port_open(host, port):
            return port
    return None


def _build_connection_url(user: str, password: str, host: str, port: int, database: str) -> str:
    return (
        "postgresql://"
        f"{urlparse.quote(user, safe='')}:{urlparse.quote(password, safe='')}@"
        f"{host}:{int(port)}/{urlparse.quote(database, safe='')}"
    )


def _connection_env(connection: dict[str, Any]) -> dict[str, str]:
    port = str(connection["port"])
    url = str(connection["url"])
    password = str(connection["password"])
    return {
        "DATASTORE_ADAPTER": "postgres",
        "DATASTORE_POSTGRES_URL": url,
        "DATABASE_URL": url,
        "NAKAMA_DATABASE_URL": url,
        "PGHOST": str(connection["host"]),
        "PGPORT": port,
        "PGUSER": str(connection["user"]),
        "PGPASSWORD": password,
        "PGDATABASE": str(connection["database"]),
        "DB_HOST": str(connection["host"]),
        "DB_PORT": port,
        "DB_USER": str(connection["user"]),
        "DB_PASSWORD": password,
        "DB_NAME": str(connection["database"]),
        "POSTGRES_HOST": str(connection["host"]),
        "POSTGRES_PORT": port,
        "POSTGRES_USER": str(connection["user"]),
        "POSTGRES_PASSWORD": password,
        "POSTGRES_DB": str(connection["database"]),
    }


def _pg_env(connection: dict[str, Any]) -> dict[str, str]:
    env = dict(os.environ)
    env["PGPASSWORD"] = str(connection.get("password") or "")
    return env


def _run_pg(command: str, args: list[str], connection: dict[str, Any], *, timeout: float = 8) -> subprocess.CompletedProcess:
    return subprocess.run(
        [command, *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_pg_env(connection),
    )


def _quote_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _init_database_if_needed(settings: dict, initdb_path: str, data_dir: Path) -> None:
    if (data_dir / "PG_VERSION").exists():
        return
    data_dir.parent.mkdir(parents=True, exist_ok=True)
    password_file = MANAGED_POSTGRES_DIR / "pg-pass.txt"
    password_file.parent.mkdir(parents=True, exist_ok=True)
    password_file.write_text(settings["credentials"]["password"], encoding="utf-8")
    password_file.chmod(0o600)
    try:
        args = [
            initdb_path,
            "-D",
            str(data_dir),
            "-U",
            settings["credentials"]["user"],
            "--pwfile",
            str(password_file),
            "--auth-host=scram-sha-256",
            "--auth-local=scram-sha-256",
        ]
        completed = subprocess.run(args, check=False, capture_output=True, text=True, timeout=45)
    finally:
        try:
            password_file.unlink()
        except OSError:
            pass
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "initdb exited non-zero"
        raise ManagedPostgresError(f"Managed Postgres initdb failed: {detail}")


def _read_runtime_file() -> dict:
    try:
        parsed = json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _write_runtime_file(runtime: dict) -> None:
    _write_json(RUNTIME_FILE, runtime)


def _read_postmaster_pid(data_dir: Path) -> dict:
    try:
        lines = (data_dir / "postmaster.pid").read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    return {
        "pid": int(lines[0]) if len(lines) > 0 and lines[0].strip().isdigit() else None,
        "port": int(lines[3]) if len(lines) > 3 and lines[3].strip().isdigit() else None,
    }


def _admin_connection(settings: dict, host: str, port: int) -> dict[str, Any]:
    return {
        "url": _build_connection_url(
            settings["credentials"]["user"],
            settings["credentials"]["password"],
            host,
            port,
            "postgres",
        ),
        "host": host,
        "port": int(port),
        "user": settings["credentials"]["user"],
        "password": settings["credentials"]["password"],
        "database": "postgres",
    }


def _probe_ready(settings: dict, host: str, port: int, *, timeout: float = 1.0) -> bool:
    psql_path = _resolve_binary("psql", settings["local"].get("binDir") or "")
    if not _binary_available(psql_path):
        return False
    connection = _admin_connection(settings, host, port)
    try:
        completed = _run_pg(psql_path, ["-X", "-tAc", "select 1", connection["url"]], connection, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return completed.returncode == 0 and completed.stdout.strip() == "1"


def _wait_ready(settings: dict, host: str, port: int, *, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() <= deadline:
        if _probe_ready(settings, host, port, timeout=1.0):
            return
        time.sleep(0.25)
    raise ManagedPostgresError(f"Managed Postgres did not become ready on {host}:{port}.")


def _reuse_existing_runtime(settings: dict, data_dir: Path, host: str) -> dict[str, Any] | None:
    runtime = _read_runtime_file()
    runtime_pid = runtime.get("pid")
    runtime_port = runtime.get("port")
    if runtime.get("dataDir") == str(data_dir) and _is_process_alive(runtime_pid) and runtime_port:
        port = int(runtime_port)
        if _probe_ready(settings, host, port, timeout=1.0):
            return {"host": host, "port": port, "pid": int(runtime_pid), "dataDir": str(data_dir)}

    postmaster = _read_postmaster_pid(data_dir)
    pid = postmaster.get("pid")
    port = postmaster.get("port")
    if pid and port and _is_process_alive(pid) and _probe_ready(settings, host, int(port), timeout=1.0):
        runtime = {"host": host, "port": int(port), "pid": int(pid), "dataDir": str(data_dir)}
        _write_runtime_file(runtime)
        return runtime

    if pid and not _is_process_alive(pid):
        try:
            (data_dir / "postmaster.pid").unlink()
        except OSError:
            pass
    return None


def start_local_postgres(settings: dict | None = None) -> dict[str, Any]:
    settings = settings or read_settings()
    if settings.get("enabled") is False:
        return {}
    if settings.get("mode") != "local":
        raise ManagedPostgresError("Managed Postgres local runtime requested while database mode is external.")

    with _LOCK:
        process = _LOCAL_STATE.get("process")
        state_port = _LOCAL_STATE.get("port")
        state_host = _LOCAL_STATE.get("host")
        if process is not None and process.poll() is None and state_host and state_port:
            if _probe_ready(settings, str(state_host), int(state_port), timeout=1.0):
                return {
                    "host": str(state_host),
                    "port": int(state_port),
                    "pid": int(_LOCAL_STATE.get("pid") or process.pid),
                    "dataDir": str(_LOCAL_STATE.get("data_dir") or ""),
                }

        local = settings["local"]
        host = str(local.get("host") or DEFAULT_DB_HOST)
        data_dir = _resolve_path(local.get("dataDir") or "", DEFAULT_DATA_DIR)
        socket_dir = DEFAULT_SOCKET_DIR
        socket_dir.mkdir(parents=True, exist_ok=True)
        MANAGED_POSTGRES_DIR.mkdir(parents=True, exist_ok=True)

        bin_dir = str(local.get("binDir") or "")
        initdb_path = _resolve_binary("initdb", bin_dir)
        postgres_path = _resolve_binary("postgres", bin_dir)
        if not _binary_available(initdb_path) or not _binary_available(postgres_path):
            raise ManagedPostgresError("PostgreSQL binaries not found (initdb/postgres).")

        _init_database_if_needed(settings, initdb_path, data_dir)
        reused = _reuse_existing_runtime(settings, data_dir, host)
        if reused:
            _LOCAL_STATE.update(
                {"process": None, "pid": reused["pid"], "host": reused["host"], "port": reused["port"], "data_dir": data_dir}
            )
            return reused

        preferred_port = _normalize_port(local.get("port"), DEFAULT_DB_PORT)
        if preferred_port == 0:
            selected_port = _find_available_port(host)
        elif _is_port_open(host, preferred_port):
            if local.get("allowPortFallback") is False:
                raise ManagedPostgresError(f"PostgreSQL port {preferred_port} is already in use.")
            selected_port = _find_available_port(
                host,
                DEFAULT_PORT_SCAN_RANGE["min"],
                DEFAULT_PORT_SCAN_RANGE["max"],
            )
        else:
            selected_port = preferred_port
        if not selected_port:
            raise ManagedPostgresError("Unable to find an available port for managed Postgres.")

        log_handle = LOG_FILE.open("ab")
        try:
            process = subprocess.Popen(
                [
                    postgres_path,
                    "-D",
                    str(data_dir),
                    "-h",
                    host,
                    "-p",
                    str(selected_port),
                    "-k",
                    str(socket_dir),
                ],
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        except Exception:
            log_handle.close()
            raise
        log_handle.close()

        try:
            _wait_ready(settings, host, selected_port)
        except Exception:
            try:
                process.terminate()
            except OSError:
                pass
            raise

        runtime = {"host": host, "port": int(selected_port), "pid": int(process.pid), "dataDir": str(data_dir)}
        _LOCAL_STATE.update(
            {"process": process, "pid": process.pid, "host": host, "port": selected_port, "data_dir": data_dir}
        )
        _write_runtime_file(runtime)
        return runtime


def _expand_external_url(raw_url: str, project_id: str, settings: dict) -> str:
    database = build_database_name(project_id, settings)
    has_project_token = any(token in raw_url for token in ("${project}", "{project}", "${PROJECT_ID}", "{projectId}"))
    expanded = (
        raw_url.replace("${project}", database)
        .replace("{project}", database)
        .replace("${PROJECT_ID}", project_id)
        .replace("{projectId}", project_id)
    )
    try:
        parsed = urlparse.urlparse(expanded)
    except Exception as exc:
        raise ManagedPostgresError("External managed Postgres URL is invalid.") from exc
    if not parsed.scheme or not parsed.netloc:
        raise ManagedPostgresError("External managed Postgres URL is invalid.")
    if not has_project_token or not parsed.path or parsed.path == "/":
        parsed = parsed._replace(path=f"/{database}")
    return urlparse.urlunparse(parsed)


def _parse_connection_url(url: str, fallback_database: str) -> dict[str, Any]:
    parsed = urlparse.urlparse(url)
    return {
        "url": url,
        "host": parsed.hostname or "",
        "port": int(parsed.port or DEFAULT_DB_PORT),
        "user": urlparse.unquote(parsed.username or ""),
        "password": urlparse.unquote(parsed.password or ""),
        "database": (parsed.path or "").lstrip("/") or fallback_database,
    }


def _ensure_database_exists(connection: dict[str, Any], settings: dict) -> None:
    psql_path = _resolve_binary("psql", settings["local"].get("binDir") or "")
    createdb_path = _resolve_binary("createdb", settings["local"].get("binDir") or "")
    if not _binary_available(psql_path) and not _binary_available(createdb_path):
        raise ManagedPostgresError("PostgreSQL utilities (psql or createdb) are required to provision databases.")

    admin = {**connection, "database": "postgres"}
    admin["url"] = _build_connection_url(
        str(connection["user"]),
        str(connection["password"]),
        str(connection["host"]),
        int(connection["port"]),
        "postgres",
    )
    if _binary_available(psql_path):
        probe = _run_pg(
            psql_path,
            [
                "-X",
                "-tAc",
                f"select 1 from pg_database where datname = {_quote_literal(str(connection['database']))}",
                admin["url"],
            ],
            admin,
            timeout=8,
        )
        if probe.returncode != 0:
            detail = probe.stderr.strip() or probe.stdout.strip() or "psql exited non-zero"
            raise ManagedPostgresError(f"Managed Postgres database probe failed: {detail}")
        if probe.stdout.strip() == "1":
            return

    if _binary_available(createdb_path):
        created = _run_pg(
            createdb_path,
            ["-h", str(connection["host"]), "-p", str(connection["port"]), "-U", str(connection["user"]), str(connection["database"])],
            connection,
            timeout=15,
        )
    else:
        created = _run_pg(
            psql_path,
            ["-X", "-v", "ON_ERROR_STOP=1", admin["url"], "-c", f"CREATE DATABASE {_quote_identifier(str(connection['database']))}"],
            admin,
            timeout=15,
        )
    if created.returncode != 0 and "already exists" not in (created.stderr + created.stdout).lower():
        detail = created.stderr.strip() or created.stdout.strip() or "database creation exited non-zero"
        raise ManagedPostgresError(f"Managed Postgres database creation failed: {detail}")


def ensure_project_database(project_id: str) -> ManagedDatabaseContext:
    settings = read_settings()
    if settings.get("enabled") is False:
        return ManagedDatabaseContext(enabled=False, mode=str(settings.get("mode") or "local"), env={}, connection=None)

    database = build_database_name(project_id, settings)
    if settings.get("mode") == "external":
        raw_url = settings.get("external", {}).get("url") or ""
        if not raw_url:
            raise ManagedPostgresError("Managed Postgres is configured for external mode but no external URL is set.")
        url = _expand_external_url(str(raw_url), project_id, settings)
        connection = _parse_connection_url(url, database)
        return ManagedDatabaseContext(enabled=True, mode="external", env=_connection_env(connection), connection=connection)

    runtime = start_local_postgres(settings)
    connection = {
        "url": _build_connection_url(
            settings["credentials"]["user"],
            settings["credentials"]["password"],
            runtime["host"],
            int(runtime["port"]),
            database,
        ),
        "host": runtime["host"],
        "port": int(runtime["port"]),
        "user": settings["credentials"]["user"],
        "password": settings["credentials"]["password"],
        "database": database,
    }
    _ensure_database_exists(connection, settings)
    return ManagedDatabaseContext(enabled=True, mode="local", env=_connection_env(connection), connection=connection)


def ensure_project_database_env(project_id: str) -> dict[str, str]:
    return ensure_project_database(project_id).env

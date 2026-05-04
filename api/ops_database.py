"""Fork-owned database settings and read-only inspection helpers."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from api.config import STATE_DIR
from api import ops_projects


OPS_DATABASE_SETTINGS_FILE = STATE_DIR / "ops" / "database" / "settings.json"
MAX_QUERY_ROWS = 200
_LOCK = threading.RLock()


class OpsDatabaseError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _text(value: Any, *, limit: int = 512) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _read_settings() -> dict:
    try:
        parsed = json.loads(OPS_DATABASE_SETTINGS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise OpsDatabaseError("Database settings contain invalid JSON.", 500) from exc
    return parsed if isinstance(parsed, dict) else {}


def _write_settings(settings: dict) -> None:
    OPS_DATABASE_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OPS_DATABASE_SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OPS_DATABASE_SETTINGS_FILE)


def _settings_store() -> tuple[dict, dict]:
    raw = _read_settings()
    if "global" in raw or "projects" in raw:
        global_settings = raw.get("global") if isinstance(raw.get("global"), dict) else {}
        projects = raw.get("projects") if isinstance(raw.get("projects"), dict) else {}
        return global_settings, {str(key): value for key, value in projects.items() if isinstance(value, dict)}
    return raw, {}


def _write_settings_store(global_settings: dict, projects: dict) -> None:
    if projects:
        _write_settings({"global": global_settings, "projects": projects})
    else:
        _write_settings(global_settings)


def _project_root(project_id: str) -> Path:
    try:
        project = ops_projects.get_ops_project(project_id)
    except ops_projects.OpsProjectError as exc:
        raise OpsDatabaseError(str(exc), exc.status) from exc
    raw_path = str(project.get("resolvedPath") or project.get("path") or "").strip()
    if not raw_path:
        raise OpsDatabaseError("Project path is unavailable.", 404)
    return Path(raw_path).expanduser().resolve()


def _normalize_settings(body: dict | None, *, project_id: str = "") -> dict:
    body = body if isinstance(body, dict) else {}
    kind = _text(body.get("kind") or body.get("type"), limit=64).lower() or "sqlite"
    if kind != "sqlite":
        raise OpsDatabaseError("Only sqlite read-only inspection is currently supported.")
    path = _text(body.get("path") or body.get("databasePath"), limit=4096)
    if not path:
        raise OpsDatabaseError("Database path is required.")
    raw_path = Path(path).expanduser()
    if project_id and not raw_path.is_absolute():
        raw_path = _project_root(project_id) / raw_path
    resolved = raw_path.resolve()
    mode = _text(body.get("mode"), limit=64).lower().replace("_", "-") or "persistent"
    if mode not in {"persistent", "shared", "empty", "copy"}:
        mode = "persistent"
    return {
        "kind": "sqlite",
        "path": str(resolved),
        "label": _text(body.get("label"), limit=128) or resolved.name,
        "readOnly": True,
        "mode": mode,
    }


def get_database_settings() -> dict:
    settings, projects = _settings_store()
    configured = bool(settings.get("path"))
    return {"configured": configured, "settings": settings, "projects": projects}


def save_database_settings(body: dict | None = None) -> dict:
    settings = _normalize_settings(body)
    with _LOCK:
        _global, projects = _settings_store()
        _write_settings_store(settings, projects)
    return {"configured": True, "settings": settings}


def get_project_database_settings(project_id: str) -> dict:
    key = str(project_id or "").strip()
    if not key:
        raise OpsDatabaseError("Project id is required.")
    global_settings, projects = _settings_store()
    settings = projects.get(key) or global_settings
    configured = bool(settings.get("path"))
    return {
        "projectId": key,
        "configured": configured,
        "inherited": key not in projects and bool(global_settings.get("path")),
        "settings": settings,
    }


def save_project_database_settings(project_id: str, body: dict | None = None) -> dict:
    key = str(project_id or "").strip()
    if not key:
        raise OpsDatabaseError("Project id is required.")
    settings = _normalize_settings(body, project_id=key)
    settings["projectId"] = key
    with _LOCK:
        global_settings, projects = _settings_store()
        projects[key] = settings
        _write_settings_store(global_settings, projects)
    return {"projectId": key, "configured": True, "settings": settings}


def _settings_or_body(body: dict | None = None, *, project_id: str = "") -> dict:
    if isinstance(body, dict) and (body.get("path") or body.get("databasePath")):
        return _normalize_settings(body, project_id=project_id)
    settings = get_project_database_settings(project_id)["settings"] if project_id else _settings_store()[0]
    if not settings.get("path"):
        raise OpsDatabaseError("Database settings are not configured.", 404)
    return _normalize_settings(settings, project_id=project_id)


def _connect_readonly(settings: dict) -> sqlite3.Connection:
    path = Path(settings["path"]).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise OpsDatabaseError("Database file does not exist.", 404)
    uri = f"file:{path.as_posix()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=3)
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error as exc:
        raise OpsDatabaseError(f"Unable to open database read-only: {exc}", 502) from exc


def test_database_connection(body: dict | None = None) -> dict:
    settings = _settings_or_body(body)
    with _connect_readonly(settings) as connection:
        row = connection.execute("select 1 as ok").fetchone()
    return {"ok": bool(row and row["ok"] == 1), "settings": settings}


def test_project_database_connection(project_id: str, body: dict | None = None) -> dict:
    settings = _settings_or_body(body, project_id=project_id)
    with _connect_readonly(settings) as connection:
        row = connection.execute("select 1 as ok").fetchone()
    return {"ok": bool(row and row["ok"] == 1), "projectId": project_id, "settings": settings}


def inspect_database_tables(body: dict | None = None) -> dict:
    settings = _settings_or_body(body)
    with _connect_readonly(settings) as connection:
        rows = connection.execute(
            """
            select name, type
            from sqlite_master
            where type in ('table', 'view') and name not like 'sqlite_%'
            order by type, name
            """
        ).fetchall()
        tables = []
        for row in rows:
            columns = connection.execute(f"pragma table_info({_quote_identifier(row['name'])})").fetchall()
            tables.append(
                {
                    "name": row["name"],
                    "type": row["type"],
                    "columns": [
                        {
                            "name": column["name"],
                            "type": column["type"],
                            "notNull": bool(column["notnull"]),
                            "primaryKey": bool(column["pk"]),
                        }
                        for column in columns
                    ],
                }
            )
    return {"settings": settings, "tables": tables}


def inspect_project_database_tables(project_id: str, body: dict | None = None) -> dict:
    settings = _settings_or_body(body, project_id=project_id)
    result = inspect_database_tables(settings)
    return {"projectId": project_id, **result}


def execute_readonly_query(body: dict | None = None) -> dict:
    body = body if isinstance(body, dict) else {}
    settings = _settings_or_body(body)
    query = _text(body.get("query"), limit=20000)
    if not query:
        raise OpsDatabaseError("Query is required.")
    _assert_readonly_query(query)
    try:
        limit = max(1, min(MAX_QUERY_ROWS, int(body.get("limit") or MAX_QUERY_ROWS)))
    except (TypeError, ValueError):
        limit = MAX_QUERY_ROWS
    with _connect_readonly(settings) as connection:
        try:
            cursor = connection.execute(query)
            rows = cursor.fetchmany(limit)
        except sqlite3.Error as exc:
            raise OpsDatabaseError(f"Query failed: {exc}", 400) from exc
    columns = [description[0] for description in (cursor.description or [])]
    return {
        "settings": settings,
        "columns": columns,
        "rows": [[row[column] for column in columns] for row in rows],
        "rowCount": len(rows),
        "limit": limit,
    }


def execute_project_readonly_query(project_id: str, body: dict | None = None) -> dict:
    body = dict(body or {})
    settings = _settings_or_body(body, project_id=project_id)
    body["path"] = settings["path"]
    result = execute_readonly_query(body)
    return {"projectId": project_id, **result}


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _assert_readonly_query(query: str) -> None:
    stripped = query.strip().rstrip(";").strip()
    lowered = stripped.lower()
    if ";" in stripped:
        raise OpsDatabaseError("Only one read-only SQL statement is allowed.")
    allowed = lowered.startswith("select ") or lowered.startswith("with ") or lowered.startswith("pragma ")
    if not allowed:
        raise OpsDatabaseError("Only SELECT, WITH, or PRAGMA read-only queries are allowed.")
    blocked = (" insert ", " update ", " delete ", " drop ", " alter ", " create ", " attach ", " detach ", " replace ", " vacuum ")
    padded = f" {lowered} "
    if any(token in padded for token in blocked):
        raise OpsDatabaseError("Query contains a blocked mutating SQL keyword.")

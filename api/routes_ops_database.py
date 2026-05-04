"""Fork-owned database routes for the clean restart branch."""

from __future__ import annotations

import re
from urllib.parse import unquote

from api.helpers import j
from api import ops_database


_DATABASE_SETTINGS_RE = re.compile(r"^/api/ops/database/settings/?$")
_DATABASE_TEST_RE = re.compile(r"^/api/ops/database/test/?$")
_DATABASE_TABLES_RE = re.compile(r"^/api/ops/database/inspect/tables/?$")
_DATABASE_QUERY_RE = re.compile(r"^/api/ops/database/inspect/query/?$")
_PROJECT_DATABASE_SETTINGS_RE = re.compile(r"^/api/ops/projects/([^/]+)/database/settings/?$")
_PROJECT_DATABASE_TEST_RE = re.compile(r"^/api/ops/projects/([^/]+)/database/test/?$")
_PROJECT_DATABASE_TABLES_RE = re.compile(r"^/api/ops/projects/([^/]+)/database/inspect/tables/?$")
_PROJECT_DATABASE_QUERY_RE = re.compile(r"^/api/ops/projects/([^/]+)/database/inspect/query/?$")


def handle_get(handler, parsed) -> bool:
    try:
        if _DATABASE_SETTINGS_RE.match(parsed.path):
            j(handler, ops_database.get_database_settings())
            return True
        if _DATABASE_TABLES_RE.match(parsed.path):
            j(handler, ops_database.inspect_database_tables())
            return True
        match = _PROJECT_DATABASE_SETTINGS_RE.match(parsed.path)
        if match:
            j(handler, ops_database.get_project_database_settings(unquote(match.group(1))))
            return True
        match = _PROJECT_DATABASE_TABLES_RE.match(parsed.path)
        if match:
            j(handler, ops_database.inspect_project_database_tables(unquote(match.group(1))))
            return True
        return False
    except ops_database.OpsDatabaseError as exc:
        j(handler, {"error": str(exc)}, status=exc.status)
        return True


def handle_post(handler, parsed, body: dict) -> bool:
    try:
        if _DATABASE_SETTINGS_RE.match(parsed.path):
            j(handler, {"ok": True, **ops_database.save_database_settings(body)})
            return True
        if _DATABASE_TEST_RE.match(parsed.path):
            j(handler, ops_database.test_database_connection(body))
            return True
        if _DATABASE_QUERY_RE.match(parsed.path):
            j(handler, ops_database.execute_readonly_query(body))
            return True
        match = _PROJECT_DATABASE_SETTINGS_RE.match(parsed.path)
        if match:
            j(handler, {"ok": True, **ops_database.save_project_database_settings(unquote(match.group(1)), body)})
            return True
        match = _PROJECT_DATABASE_TEST_RE.match(parsed.path)
        if match:
            j(handler, ops_database.test_project_database_connection(unquote(match.group(1)), body))
            return True
        match = _PROJECT_DATABASE_QUERY_RE.match(parsed.path)
        if match:
            j(handler, ops_database.execute_project_readonly_query(unquote(match.group(1)), body))
            return True
        return False
    except ops_database.OpsDatabaseError as exc:
        j(handler, {"error": str(exc)}, status=exc.status)
        return True

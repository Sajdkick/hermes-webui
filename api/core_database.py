"""Core API database facade."""

from __future__ import annotations

from api import ops_database
from api.core_contracts import coerce_core_error, redact_payload

DatabaseCoreError = ops_database.OpsDatabaseError


def _wrap(fn, *args, **kwargs):
    try:
        return redact_payload(fn(*args, **kwargs))
    except ops_database.OpsDatabaseError as exc:
        raise coerce_core_error(exc, code="DATABASE_ERROR") from exc


def get_settings(): return _wrap(ops_database.get_database_settings)
def save_settings(body=None): return _wrap(ops_database.save_database_settings, body or {})
def test_connection(body=None): return _wrap(ops_database.test_database_connection, body or {})
def inspect_tables(body=None): return _wrap(ops_database.inspect_database_tables, body or {})
def execute_readonly_query(body=None): return _wrap(ops_database.execute_readonly_query, body or {})
def get_project_settings(project_id: str): return _wrap(ops_database.get_project_database_settings, project_id)
def save_project_settings(project_id: str, body=None): return _wrap(ops_database.save_project_database_settings, project_id, body or {})
def test_project_connection(project_id: str, body=None): return _wrap(ops_database.test_project_database_connection, project_id, body or {})
def inspect_project_tables(project_id: str, body=None): return _wrap(ops_database.inspect_project_database_tables, project_id, body or {})
def execute_project_readonly_query(project_id: str, body=None): return _wrap(ops_database.execute_project_readonly_query, project_id, body or {})

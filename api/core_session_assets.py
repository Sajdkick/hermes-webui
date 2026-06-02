"""Core API session activity/readable-output facade."""

from __future__ import annotations

from api import session_activity, session_readable_output
from api.core_contracts import coerce_core_error, redact_payload


def list_activity() -> dict:
    try:
        return redact_payload(session_activity.list_session_activity())
    except session_activity.SessionActivityError as exc:
        raise coerce_core_error(exc, code="SESSION_ACTIVITY_ERROR") from exc


def create_activity_group(label: str | None) -> dict:
    try:
        return redact_payload({"success": True, "group": session_activity.create_session_activity_group(label)})
    except session_activity.SessionActivityError as exc:
        raise coerce_core_error(exc, code="SESSION_ACTIVITY_ERROR") from exc


def rename_activity_group(group_id: str, label: str | None) -> dict:
    try:
        return redact_payload({"success": True, "group": session_activity.rename_session_activity_group(group_id, label)})
    except session_activity.SessionActivityError as exc:
        raise coerce_core_error(exc, code="SESSION_ACTIVITY_ERROR") from exc


def delete_activity_group(group_id: str) -> dict:
    try:
        return redact_payload({"success": True, **session_activity.delete_session_activity_group(group_id)})
    except session_activity.SessionActivityError as exc:
        raise coerce_core_error(exc, code="SESSION_ACTIVITY_ERROR") from exc


def set_activity_group_assignment(session_id: str, group_id: str | None) -> dict:
    try:
        return redact_payload({"success": True, **session_activity.set_session_activity_group_assignment(session_id, group_id)})
    except session_activity.SessionActivityError as exc:
        raise coerce_core_error(exc, code="SESSION_ACTIVITY_ERROR") from exc


def get_readable_output(session_id: str) -> dict:
    try:
        return redact_payload(session_readable_output.get_session_readable_output(session_id))
    except session_readable_output.SessionReadableOutputError as exc:
        raise coerce_core_error(exc, code="SESSION_READABLE_OUTPUT_ERROR") from exc

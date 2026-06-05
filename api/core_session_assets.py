"""Core API session activity facade."""

from __future__ import annotations

from api import session_activity
from api.core_contracts import CoreApiError, redact_payload


def coerce_core_error(exc: Exception, *, code: str, status: int | None = None) -> CoreApiError:
    return CoreApiError(
        str(exc),
        status=int(status or getattr(exc, "status", 500) or 500),
        code=code,
    )


def list_activity() -> dict:
    try:
        return redact_payload(session_activity.list_activity_source())
    except session_activity.SessionActivityError as exc:
        raise coerce_core_error(exc, code="SESSION_ACTIVITY_ERROR") from exc


def create_activity_group(label: str) -> dict:
    try:
        return redact_payload(session_activity.create_activity_group(label))
    except session_activity.SessionActivityError as exc:
        raise coerce_core_error(exc, code="SESSION_ACTIVITY_ERROR") from exc


def rename_activity_group(group_id: str, label: str) -> dict:
    try:
        return redact_payload(session_activity.rename_activity_group(group_id, label))
    except session_activity.SessionActivityError as exc:
        raise coerce_core_error(exc, code="SESSION_ACTIVITY_ERROR") from exc


def delete_activity_group(group_id: str) -> dict:
    try:
        return redact_payload(session_activity.delete_activity_group(group_id))
    except session_activity.SessionActivityError as exc:
        raise coerce_core_error(exc, code="SESSION_ACTIVITY_ERROR") from exc


def assign_activity_group(session_id: str, group_id: str | None) -> dict:
    try:
        return redact_payload(session_activity.assign_activity_group(session_id, group_id))
    except session_activity.SessionActivityError as exc:
        raise coerce_core_error(exc, code="SESSION_ACTIVITY_ERROR") from exc

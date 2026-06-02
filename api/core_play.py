"""Core Play API boundary for Hermes Ops.

This module is the stable in-process boundary for Play workflow callers.  It
intentionally delegates to ``api.play_pipeline`` today so the first extraction
slice changes call ownership without changing process, proxy, log, or status
semantics.  Future shared-core/runtime work should preserve this facade and move
implementation details behind it rather than importing ``play_pipeline`` from
Ops modules directly.
"""

from __future__ import annotations

from typing import Any

from api import play_pipeline as _play_pipeline


PlayCoreError = _play_pipeline.PlayPipelineError
# Backwards-compatible name for callers/tests that expect the implementation
# error class shape.  The object identity is preserved so ``except`` behavior and
# the ``status`` attribute stay unchanged.
PlayPipelineError = PlayCoreError


def register_build_failure_repair_handler(handler) -> None:
    """Register the shell-owned repair handoff for failed Play builds."""

    return _play_pipeline.register_build_failure_repair_handler(handler)


def get_project_play_config_file_info(project_id: str) -> dict:
    """Return Play config discovery/validation metadata for a project."""

    return _play_pipeline.get_project_play_config_file_info(project_id)


def get_project_play_config(project_id: str) -> dict:
    """Return the normalized runnable Play config for a project."""

    return _play_pipeline.get_project_play_config(project_id)


def get_project_play_status(project_id: str) -> dict:
    """Return the current Play status payload for a project."""

    return _play_pipeline.build_project_play_status(project_id)


def get_project_play_logs(project_id: str, limit: Any = None) -> dict:
    """Return bounded Play log entries/text for a project."""

    return _play_pipeline.build_project_play_logs(project_id, limit)


def start_project_play(project_id: str, body: dict | None = None) -> dict:
    """Start the project's Play workflow and return its status payload."""

    return _play_pipeline.start_project_play_pipeline(project_id, body)


def restart_project_play(project_id: str, body: dict | None = None) -> dict:
    """Restart the project's Play workflow and return its status payload."""

    return _play_pipeline.restart_project_play_pipeline(project_id, body)


def stop_project_play(project_id: str, *, purge: bool = False) -> dict | None:
    """Stop the project's Play workflow.

    Returns the stopped status when an active pipeline existed, or ``None`` when
    there was no in-memory pipeline.  HTTP callers preserve the historical
    fallback by fetching ``get_project_play_status(project_id)`` when this returns
    ``None``.
    """

    return _play_pipeline.stop_project_play_pipeline(project_id, purge=purge)


def handle_play_proxy_request(handler, project_id: str, target_path: str, parsed, *, method: str = "GET") -> None:
    """Proxy an HTTP/WebSocket request to a ready Play target."""

    return _play_pipeline.handle_play_proxy_request(handler, project_id, target_path, parsed, method=method)

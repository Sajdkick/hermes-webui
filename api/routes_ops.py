"""Fork-owned ops route dispatcher for the clean restart branch."""

from __future__ import annotations

from api import (
    routes_ops_notifications,
    routes_ops_play,
    routes_ops_projects,
    routes_ops_runtime,
    routes_ops_sessions,
    routes_ops_shell,
)


def handle_get(handler, parsed) -> bool:
    if routes_ops_shell.handle_get(handler, parsed):
        return True
    if routes_ops_notifications.handle_get(handler, parsed):
        return True
    if routes_ops_play.handle_get(handler, parsed):
        return True
    if routes_ops_runtime.handle_get(handler, parsed):
        return True
    if routes_ops_sessions.handle_get(handler, parsed):
        return True
    if routes_ops_projects.handle_get(handler, parsed):
        return True
    return False


def handle_post(handler, parsed, body: dict) -> bool:
    if routes_ops_notifications.handle_post(handler, parsed, body):
        return True
    if routes_ops_play.handle_post(handler, parsed, body):
        return True
    if routes_ops_runtime.handle_post(handler, parsed, body):
        return True
    if routes_ops_projects.handle_post(handler, parsed, body):
        return True
    return False

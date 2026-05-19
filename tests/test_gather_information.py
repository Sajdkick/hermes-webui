"""Hermes WebUI gather-report helper coverage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from api import gather


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_gather_report_create_append_show_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(gather, "STATE_DIR", tmp_path)

    created = gather.create_gather_report(
        "Save flow repro",
        session_id="session-123",
        workspace="/workspace/project",
    )

    report = created["report"]
    ingest = created["ingest"]
    assert report["title"] == "Save flow repro"
    assert report["sessionId"] == "session-123"
    assert report["workspace"] == "/workspace/project"
    assert report["eventCount"] == 0
    assert ingest["path"] == f"/api/gather/{report['id']}/events"
    assert ingest["url"] == ingest["path"]
    assert ingest["tokenHeader"] == gather.GATHER_TOKEN_HEADER
    assert (tmp_path / "gather" / f"{report['id']}.json").exists()

    with pytest.raises(gather.GatherError) as bad_token:
        gather.append_gather_event(report["id"], "wrong-token", {"label": "ignored"})
    assert bad_token.value.status == 403

    appended = gather.append_gather_event(
        report["id"],
        ingest["token"],
        {
            "type": "branch",
            "level": "debug",
            "label": "save-click",
            "message": "clicked save",
            "route": "/session/abc",
            "url": "http://localhost/session/abc",
            "data": {"selectedId": "task-1", "pendingCount": 2},
        },
    )
    assert appended["ok"] is True
    assert appended["report"]["eventCount"] == 1

    shown = gather.show_gather_report(report["id"])
    assert "ingest" not in shown
    assert shown["report"]["eventCount"] == 1
    assert shown["report"]["latestEvent"]["label"] == "save-click"
    assert shown["events"][0]["data"] == {"selectedId": "task-1", "pendingCount": 2}


def test_gather_event_route_contract_is_token_scoped_and_csrf_exempt():
    routes = (REPO_ROOT / "api" / "routes.py").read_text(encoding="utf-8")

    assert 'path.startswith("/api/gather/")' in routes
    assert 'path.rstrip("/").endswith("/events")' in routes
    assert 'handler.headers.get("X-Hermes-Gather-Token", "")' in routes
    assert "append_gather_event(gather_report_id, token, body)" in routes
    assert routes.index("gather_report_id = report_id_from_events_path(parsed.path)") < routes.index(
        'if parsed.path == "/api/sessions/activity/groups"'
    )


def test_hermes_gather_cli_create_show_round_trip(tmp_path):
    env = {**os.environ, "HERMES_WEBUI_STATE_DIR": str(tmp_path)}

    create = subprocess.run(
        [
            sys.executable,
            "scripts/hermes-gather.py",
            "create",
            "--title",
            "CLI repro",
            "--json",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(create.stdout)
    report_id = payload["report"]["id"]
    token = payload["ingest"]["token"]

    # Simulate browser/server instrumentation using the same API path the CLI printed.
    append_env_script = (
        "import json; "
        "from api import gather; "
        f"print(json.dumps(gather.append_gather_event({report_id!r}, {token!r}, {{'label': 'cli-event', 'data': {{'ok': True}}}})))"
    )
    subprocess.run(
        [sys.executable, "-c", append_env_script],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    show = subprocess.run(
        [sys.executable, "scripts/hermes-gather.py", "show", report_id, "--json"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    shown = json.loads(show.stdout)
    assert shown["report"]["title"] == "CLI repro"
    assert shown["events"][0]["label"] == "cli-event"

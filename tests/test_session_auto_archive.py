import json

import pytest

from api import session_auto_archive
import api.models as models
from api.models import Session


@pytest.fixture(autouse=True)
def _isolate_session_dir(tmp_path, monkeypatch):
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    index_file = session_dir / "_index.json"
    monkeypatch.setattr(models, "SESSION_DIR", session_dir)
    monkeypatch.setattr(models, "SESSION_INDEX_FILE", index_file)
    models.SESSIONS.clear()
    yield session_dir, index_file
    models.SESSIONS.clear()


def _saved_session(session_id: str, *, updated_at: float, **kwargs) -> Session:
    session = Session(
        session_id=session_id,
        title=kwargs.pop("title", "Old session"),
        messages=kwargs.pop("messages", [{"role": "user", "content": "keep me", "timestamp": updated_at}]),
        created_at=kwargs.pop("created_at", updated_at),
        updated_at=updated_at,
        **kwargs,
    )
    session.save(touch_updated_at=False)
    return session


def test_archive_stale_sessions_preserves_transcript_and_clears_stale_runtime(monkeypatch):
    now = 2_000_000.0
    old = now - (8 * 24 * 60 * 60)
    monkeypatch.setattr(session_auto_archive, "_recent_active_run_aliases", lambda *, cutoff: set())
    session = _saved_session(
        "old_stale",
        updated_at=old,
        active_stream_id="stale-stream",
        pending_user_message="stale pending turn",
        pending_started_at=old,
        pending_attachments=[{"name": "stale.txt"}],
        messages=[{"role": "user", "content": "important transcript", "timestamp": old}],
    )

    result = session_auto_archive.archive_stale_sessions([session.compact()], now=now, force=True)

    assert result["archived"] == 1
    assert result["sessionIds"] == ["old_stale"]
    loaded = Session.load("old_stale")
    assert loaded.archived is True
    assert loaded.messages == [{"role": "user", "content": "important transcript", "timestamp": old}]
    assert loaded.active_stream_id is None
    assert loaded.pending_user_message is None
    assert loaded.pending_attachments == []
    assert loaded.pending_started_at is None
    assert loaded.updated_at == old

    index = json.loads(models.SESSION_INDEX_FILE.read_text(encoding="utf-8"))
    assert index[0]["session_id"] == "old_stale"
    assert index[0]["archived"] is True
    assert index[0]["message_count"] == 1


def test_archive_stale_sessions_skips_pinned_live_recent_and_recent_active_run(monkeypatch):
    now = 2_000_000.0
    old = now - (8 * 24 * 60 * 60)
    recent = now - 60
    monkeypatch.setattr(session_auto_archive, "_recent_active_run_aliases", lambda *, cutoff: {"active_run"})
    pinned = _saved_session("pinned_old", updated_at=old, pinned=True)
    live = _saved_session("live_old", updated_at=old, active_stream_id="live-stream")
    recent_session = _saved_session("recent_session", updated_at=recent)
    active_run = _saved_session("active_run", updated_at=old)

    live_summary = live.compact()
    live_summary["is_streaming"] = True
    summaries = [
        pinned.compact(),
        live_summary,
        recent_session.compact(),
        active_run.compact(),
    ]

    result = session_auto_archive.archive_stale_sessions(summaries, now=now, force=True)

    assert result["archived"] == 0
    assert Session.load("pinned_old").archived is False
    assert Session.load("live_old").archived is False
    assert Session.load("recent_session").archived is False
    assert Session.load("active_run").archived is False


def test_archive_stale_sessions_throttles_non_forced_sweeps(monkeypatch):
    monkeypatch.setattr(session_auto_archive, "_recent_active_run_aliases", lambda *, cutoff: set())
    monkeypatch.setattr(session_auto_archive, "_LAST_SWEEP_AT", 0.0)
    first = session_auto_archive.archive_stale_sessions([], now=1_000.0, force=False)
    second = session_auto_archive.archive_stale_sessions([], now=1_001.0, force=False)

    assert first.get("skipped") != "throttled"
    assert second == {"archived": 0, "checked": 0, "skipped": "throttled"}

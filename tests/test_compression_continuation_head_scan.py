from pathlib import Path
from types import SimpleNamespace

import pytest

import api.models as models


def test_compression_continuation_scan_reads_only_file_head(tmp_path, monkeypatch):
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    parent_sid = "parent_session"
    child_sid = "child_session"

    (session_dir / f"{parent_sid}.json").write_text(
        '{"session_id": "parent_session", "messages": []}',
        encoding="utf-8",
    )
    (session_dir / f"{child_sid}.json").write_text(
        '{"session_id": "child_session", "parent_session_id": "parent_session", '
        '"messages": ["' + ("x" * 200000) + '"]}',
        encoding="utf-8",
    )

    monkeypatch.setattr(models, "SESSION_DIR", session_dir)
    monkeypatch.setattr(models, "SESSION_INDEX_FILE", session_dir / "_index.json")
    models.SESSIONS.clear()

    real_read_text = Path.read_text

    def fail_session_read_text(self, *args, **kwargs):
        if self.parent == session_dir and self.suffix == ".json":
            raise AssertionError("_has_compression_continuation must not read full sidecars")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_session_read_text)

    assert models._has_compression_continuation(SimpleNamespace(session_id=parent_sid)) is True

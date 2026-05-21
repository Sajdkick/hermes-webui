"""Health guards for optional Hermes Agent ``state.db`` reads.

The WebUI treats Hermes Agent's SQLite store as an additive data source for
sidebar/session metadata. A corrupt or partially overwritten DB must not turn
sidebar polling or gateway SSE into repeated expensive failures.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from contextlib import closing
from pathlib import Path

SQLITE_HEADER = b"SQLite format 3\x00"
_WARN_THROTTLE_SECONDS = 300.0
_LAST_WARNED: dict[tuple[str, str, object], float] = {}


def _stat_key(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _warn_once(log, path: Path, reason: str, *, purpose: str = "state.db") -> None:
    logger = log or logging.getLogger(__name__)
    now = time.monotonic()
    key = (str(path), reason, _stat_key(path))
    last = _LAST_WARNED.get(key, 0.0)
    if now - last < _WARN_THROTTLE_SECONDS:
        return
    _LAST_WARNED[key] = now
    logger.warning(
        "%s skipped: Hermes state.db at %s is unavailable (%s). "
        "WebUI will retry when the file changes.",
        purpose,
        path,
        reason,
    )


def state_db_has_sqlite_header(path: Path, *, log=None, purpose: str = "state.db") -> bool:
    db_path = Path(path)
    try:
        with db_path.open("rb") as fh:
            header = fh.read(len(SQLITE_HEADER))
    except FileNotFoundError:
        return False
    except OSError as exc:
        _warn_once(log, db_path, f"cannot read header: {exc}", purpose=purpose)
        return False
    if header == SQLITE_HEADER:
        return True
    if not header:
        _warn_once(log, db_path, "empty file", purpose=purpose)
    else:
        _warn_once(log, db_path, "invalid SQLite header", purpose=purpose)
    return False


def warn_state_db_exception(path: Path, exc: BaseException, *, log=None, purpose: str = "state.db") -> None:
    if isinstance(exc, sqlite3.DatabaseError):
        reason = str(exc) or exc.__class__.__name__
    else:
        reason = exc.__class__.__name__
    _warn_once(log, Path(path), reason, purpose=purpose)


def state_db_readable(path: Path, *, log=None, purpose: str = "state.db") -> bool:
    db_path = Path(path)
    if not db_path.exists():
        return False
    if not state_db_has_sqlite_header(db_path, log=log, purpose=purpose):
        return False
    try:
        with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
            conn.execute("PRAGMA schema_version").fetchone()
        return True
    except Exception as exc:
        warn_state_db_exception(db_path, exc, log=log, purpose=purpose)
        return False

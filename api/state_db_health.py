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
from urllib.parse import quote

SQLITE_HEADER = b"SQLite format 3\x00"
_WARN_THROTTLE_SECONDS = 300.0
_LAST_WARNED: dict[tuple[str, str, object], float] = {}
_UNAVAILABLE: dict[str, tuple[tuple[int, int] | None, str, float | None]] = {}

_PERSISTENT_DATABASE_ERRORS = (
    "database disk image is malformed",
    "file is not a database",
    "not a database",
    "unsupported file format",
    "file is encrypted",
)
_TRANSIENT_UNAVAILABLE_SECONDS = 5.0


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


def _exception_reason(exc: BaseException) -> str:
    text = str(exc).strip()
    return text or exc.__class__.__name__


def _is_persistent_database_error(exc: BaseException) -> bool:
    if not isinstance(exc, sqlite3.DatabaseError):
        return False
    reason = _exception_reason(exc).lower()
    return any(fragment in reason for fragment in _PERSISTENT_DATABASE_ERRORS)


def _readonly_uri(path: Path) -> str:
    return f"file:{quote(str(path), safe='/')}?mode=ro"


def _clear_unavailable(path: Path) -> None:
    _UNAVAILABLE.pop(str(path), None)


def _mark_unavailable(
    path: Path,
    reason: str,
    *,
    persistent: bool,
    log=None,
    purpose: str = "state.db",
) -> None:
    retry_at = None if persistent else time.monotonic() + _TRANSIENT_UNAVAILABLE_SECONDS
    _UNAVAILABLE[str(path)] = (_stat_key(path), reason, retry_at)
    _warn_once(log, path, reason, purpose=purpose)


def state_db_unavailable_reason(path: Path) -> str | None:
    """Return the cached skip reason for the current DB file state, if any.

    Persistent corruption is cached until the file's ``mtime`` or size changes;
    transient errors such as lock/busy states expire after a short backoff.
    """
    db_path = Path(path)
    entry = _UNAVAILABLE.get(str(db_path))
    if not entry:
        return None
    cached_stat, reason, retry_at = entry
    if cached_stat != _stat_key(db_path):
        _clear_unavailable(db_path)
        return None
    if retry_at is not None and time.monotonic() >= retry_at:
        _clear_unavailable(db_path)
        return None
    return reason


def state_db_has_sqlite_header(path: Path, *, log=None, purpose: str = "state.db") -> bool:
    db_path = Path(path)
    cached_reason = state_db_unavailable_reason(db_path)
    if cached_reason:
        _warn_once(log, db_path, cached_reason, purpose=purpose)
        return False
    try:
        with db_path.open("rb") as fh:
            header = fh.read(len(SQLITE_HEADER))
    except FileNotFoundError:
        return False
    except OSError as exc:
        _mark_unavailable(
            db_path,
            f"cannot read header: {exc}",
            persistent=False,
            log=log,
            purpose=purpose,
        )
        return False
    if header == SQLITE_HEADER:
        return True
    reason = "empty file" if not header else "invalid SQLite header"
    _mark_unavailable(db_path, reason, persistent=True, log=log, purpose=purpose)
    return False


def warn_state_db_exception(path: Path, exc: BaseException, *, log=None, purpose: str = "state.db") -> None:
    db_path = Path(path)
    reason = _exception_reason(exc)
    if isinstance(exc, sqlite3.DatabaseError):
        _mark_unavailable(
            db_path,
            reason,
            persistent=_is_persistent_database_error(exc),
            log=log,
            purpose=purpose,
        )
        return
    _warn_once(log, db_path, reason, purpose=purpose)


def connect_state_db_readonly(
    path: Path,
    *,
    log=None,
    purpose: str = "state.db",
    timeout: float = 0.25,
) -> sqlite3.Connection | None:
    """Open a bounded read-only state.db connection, or ``None`` if unavailable.

    Optional Agent state is useful but must not hold high-frequency WebUI paths
    hostage.  This function is the shared boundary for read-only Agent DB access:
    it checks the corruption/backoff cache, verifies the SQLite header, uses
    SQLite read-only mode, and applies a short lock timeout.
    """
    db_path = Path(path)
    if not db_path.exists():
        return None
    if not state_db_has_sqlite_header(db_path, log=log, purpose=purpose):
        return None
    try:
        conn = sqlite3.connect(_readonly_uri(db_path), uri=True, timeout=timeout)
        try:
            conn.execute("PRAGMA query_only = ON")
        except Exception:
            # Some sqlite connection wrappers used in tests only expose cursor(),
            # and older sqlite builds may reject this pragma. Read-only URI mode
            # is still the enforcement boundary, so keep the connection usable.
            pass
        return conn
    except Exception as exc:
        warn_state_db_exception(db_path, exc, log=log, purpose=purpose)
        return None


def state_db_readable(path: Path, *, log=None, purpose: str = "state.db") -> bool:
    db_path = Path(path)
    conn = connect_state_db_readonly(db_path, log=log, purpose=purpose)
    if conn is None:
        return False
    try:
        with closing(conn):
            conn.execute("PRAGMA schema_version").fetchone()
        _clear_unavailable(db_path)
        return True
    except Exception as exc:
        warn_state_db_exception(db_path, exc, log=log, purpose=purpose)
        return False

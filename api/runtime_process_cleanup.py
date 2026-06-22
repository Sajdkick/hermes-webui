"""Helpers for reconciling Hermes-owned runtime processes with OS state."""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


APP_SERVER_COMMAND_MARKER = "packages/server/dist/packages/server/index.js"
TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RuntimeProcessInfo:
    pid: int
    cmdline: str
    environ: dict[str, str]
    cwd: Path | None = None
    pgid: int | None = None


def env_flag_enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in TRUTHY_ENV_VALUES


def path_is_within(path: Path | None, root: Path) -> bool:
    if path is None:
        return False
    try:
        candidate = path.resolve()
        base = root.resolve()
        candidate.relative_to(base)
        return True
    except (OSError, ValueError):
        return False


def _read_process_cmdline(pid: int) -> str:
    try:
        raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()


def _read_process_environ(pid: int) -> dict[str, str]:
    try:
        raw = (Path("/proc") / str(pid) / "environ").read_bytes()
    except OSError:
        return {}
    environ: dict[str, str] = {}
    for entry in raw.split(b"\0"):
        if not entry or b"=" not in entry:
            continue
        key, value = entry.split(b"=", 1)
        name = key.decode("utf-8", errors="replace").strip()
        if not name:
            continue
        environ[name] = value.decode("utf-8", errors="replace")
    return environ


def _read_process_cwd(pid: int) -> Path | None:
    try:
        return (Path("/proc") / str(pid) / "cwd").resolve()
    except OSError:
        return None


def _read_process_pgid(pid: int) -> int | None:
    try:
        return os.getpgid(pid)
    except OSError:
        return None


def iter_runtime_processes() -> Iterator[RuntimeProcessInfo]:
    try:
        entries = list(Path("/proc").iterdir())
    except OSError:
        return
    current_pid = os.getpid()
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == current_pid:
            continue
        cmdline = _read_process_cmdline(pid)
        if not cmdline:
            continue
        yield RuntimeProcessInfo(
            pid=pid,
            cmdline=cmdline,
            environ=_read_process_environ(pid),
            cwd=_read_process_cwd(pid),
            pgid=_read_process_pgid(pid),
        )


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _signal_runtime_process(pid: int, sig: int) -> bool:
    try:
        pgid = os.getpgid(pid)
    except OSError:
        pgid = 0
    if pgid > 1:
        try:
            os.killpg(pgid, sig)
            return True
        except ProcessLookupError:
            pass
        except OSError:
            pass
    try:
        os.kill(pid, sig)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return False


def terminate_process_group(pid: int, *, timeout: float = 4.0) -> bool:
    if not _process_alive(pid):
        return False
    if not _signal_runtime_process(pid, signal.SIGTERM):
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _process_alive(pid):
            return True
        time.sleep(0.05)
    _signal_runtime_process(pid, signal.SIGKILL)
    deadline = time.time() + 1.0
    while time.time() < deadline:
        if not _process_alive(pid):
            return True
        time.sleep(0.05)
    return not _process_alive(pid)

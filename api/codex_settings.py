"""Helpers for the shared Codex CLI configuration file.

This keeps the WebUI-facing Codex settings surface isolated from the rest of
the generic settings handlers so upstream merges stay low-conflict.
"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

DEFAULT_CODEX_CONFIG_PATH = Path.home() / ".codex" / "config.toml"
MAX_CODEX_CONFIG_BYTES = 256 * 1024


def _codex_config_path() -> Path:
    raw = os.environ.get("CODEX_CONFIG_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_CODEX_CONFIG_PATH


def _normalize_content(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def load_codex_config() -> dict[str, str]:
    path = _codex_config_path()
    if path.exists() and not path.is_file():
        raise ValueError("Codex config path is not a file.")
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return {
        "path": str(path),
        "content": content,
    }


def save_codex_config(content: str) -> dict[str, object]:
    if not isinstance(content, str):
        raise ValueError("content must be a string")
    normalized = _normalize_content(content)
    if len(normalized.encode("utf-8")) > MAX_CODEX_CONFIG_BYTES:
        raise ValueError("Codex config is too large.")
    path = _codex_config_path()
    if path.exists() and not path.is_file():
        raise ValueError("Codex config path is not a file.")
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IRUSR | stat.S_IWUSR
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=".config.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(normalized)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    try:
        path.chmod(mode)
    except OSError:
        pass
    return {
        "ok": True,
        "path": str(path),
        "content": normalized,
    }

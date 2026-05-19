"""Fork-owned session readable-output helpers for the clean restart branch."""

from __future__ import annotations

import re
from pathlib import Path

from api.config import STATE_DIR
from api.models import get_session


MAX_READABLE_OUTPUT_BYTES = 512 * 1024
READABLE_OUTPUT_SCOPE_DIRS = (".hermes", ".cloud-terminal")
HERMES_READABLE_OUTPUT_ENV_KEYS = (
    "HERMES_READABLE_OUTPUT_PATH",
    "HERMES_READABLE_OUTPUT_DIR",
    "HERMES_READABLE_OUTPUT_ASSET_DIR",
    # Legacy compatibility for older Cloud Terminal-port skills that have not
    # learned the Hermes-native variable names yet.
    "CLOUD_TERMINAL_READABLE_OUTPUT_PATH",
    "CLOUD_TERMINAL_READABLE_OUTPUT_DIR",
    "CLOUD_TERMINAL_READABLE_OUTPUT_ASSET_DIR",
    "CLOUD_TERMINAL_SESSION_ID",
)


class SessionReadableOutputError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def build_session_readable_output_env(session_id: str) -> dict[str, str]:
    """Return Hermes-native readable-output env vars for an agent run.

    The WebUI owns a session-scoped state directory so the agent does not have
    to guess a project fallback path. Cloud Terminal-compatible aliases are
    included intentionally; old shared skills can keep working while new skills
    prefer the ``HERMES_READABLE_OUTPUT_*`` names.
    """
    key = str(session_id or "").strip()
    if not key:
        return {}
    readable_dir = (STATE_DIR / "readable-output" / key).resolve()
    message_path = readable_dir / "message.md"
    asset_dir = readable_dir / "assets"
    return {
        "HERMES_READABLE_OUTPUT_PATH": str(message_path),
        "HERMES_READABLE_OUTPUT_DIR": str(readable_dir),
        "HERMES_READABLE_OUTPUT_ASSET_DIR": str(asset_dir),
        "CLOUD_TERMINAL_READABLE_OUTPUT_PATH": str(message_path),
        "CLOUD_TERMINAL_READABLE_OUTPUT_DIR": str(readable_dir),
        "CLOUD_TERMINAL_READABLE_OUTPUT_ASSET_DIR": str(asset_dir),
        "CLOUD_TERMINAL_SESSION_ID": key,
    }


def _workspace_root_for_session(session) -> Path | None:
    raw_workspace = str(getattr(session, "workspace", "") or "").strip()
    if not raw_workspace:
        return None
    try:
        return Path(raw_workspace).expanduser().resolve()
    except Exception:
        return None


def _git_root_for_path(path: Path | None) -> Path | None:
    if not isinstance(path, Path):
        return None
    target = path if path.is_dir() else path.parent
    try:
        target = target.expanduser().resolve()
    except Exception:
        return None
    for candidate in (target, *target.parents):
        try:
            if (candidate / ".git").exists():
                return candidate
        except Exception:
            continue
    return None


def _roots_for_session(session) -> list[Path]:
    ordered: list[Path] = []
    for root in (
        _git_root_for_path(_workspace_root_for_session(session)),
        _workspace_root_for_session(session),
        (STATE_DIR / "ops").resolve(),
        Path("/tmp").resolve(),
    ):
        if not isinstance(root, Path):
            continue
        if root not in ordered:
            ordered.append(root)
    return ordered


def _path_within_roots(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.expanduser().resolve()
    except Exception:
        return False
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _readable_output_dir_candidates(session) -> list[Path]:
    session_id = str(getattr(session, "session_id", "") or "").strip()
    if not session_id:
        raise SessionReadableOutputError("Session not found.", 404)
    roots = _roots_for_session(session)
    candidates: list[Path] = []
    for root in (
        _git_root_for_path(_workspace_root_for_session(session)),
        _workspace_root_for_session(session),
    ):
        if isinstance(root, Path):
            for scope_dir in READABLE_OUTPUT_SCOPE_DIRS:
                candidates.append(root / scope_dir / "readable-output" / session_id)
    candidates.append((STATE_DIR / "readable-output" / session_id).resolve())
    candidates.append((STATE_DIR / "ops" / "readable-output" / session_id).resolve())

    seen = set()
    unique: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except Exception:
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if _path_within_roots(resolved, roots):
            unique.append(resolved)
    return unique


def _list_assets(asset_dir: Path) -> list[dict]:
    if not asset_dir.exists() or not asset_dir.is_dir():
        return []
    assets = []
    for path in sorted(asset_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(asset_dir).as_posix()
            stat = path.stat()
        except Exception:
            continue
        assets.append(
            {
                "path": relative,
                "name": path.name,
                "size": stat.st_size,
                "updated_at": stat.st_mtime,
            }
        )
        if len(assets) >= 100:
            break
    return assets


def _readable_output_title(markdown: str) -> str:
    for raw_line in str(markdown or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            line = re.sub(r"^#+\s*", "", line)
        line = line.strip("`*_> -")
        if line:
            return line[:96]
    return "Readable output"


def _resolve_session(session_id: str):
    key = str(session_id or "").strip()
    if not key:
        raise SessionReadableOutputError("Session not found.", 404)
    try:
        return get_session(key, metadata_only=True)
    except KeyError as exc:
        raise SessionReadableOutputError("Session not found.", 404) from exc


def get_session_readable_output(session_id: str) -> dict:
    session = _resolve_session(session_id)
    candidates = _readable_output_dir_candidates(session)
    target = next(
        (
            candidate / "message.md"
            for candidate in candidates
            if (candidate / "message.md").exists() and (candidate / "message.md").is_file()
        ),
        None,
    )
    artifact = {
        "sessionId": session.session_id,
        "exists": False,
        "path": "",
        "assetDir": "",
        "assetBaseUrl": f"/api/ops/sessions/{session.session_id}/readable-output/assets/",
        "markdown": "",
        "size": 0,
        "updated_at": None,
        "assets": [],
        "title": "Readable output",
    }
    if not isinstance(target, Path):
        return {"readableOutput": artifact, "history": []}

    try:
        stat = target.stat()
    except Exception:
        return {"readableOutput": artifact, "history": []}
    if stat.st_size > MAX_READABLE_OUTPUT_BYTES:
        raise SessionReadableOutputError("Readable output is too large.", 413)

    asset_dir = (target.parent / "assets").resolve()
    roots = _roots_for_session(session)
    if not _path_within_roots(asset_dir, roots):
        asset_dir = target.parent.resolve()

    try:
        markdown = target.read_text(encoding="utf-8", errors="replace")
    except PermissionError as exc:
        raise SessionReadableOutputError("Readable output is not readable.", 403) from exc
    except Exception as exc:
        raise SessionReadableOutputError("Could not read readable output.", 500) from exc

    artifact.update(
        {
            "exists": True,
            "path": str(target),
            "assetDir": str(asset_dir),
            "markdown": markdown,
            "size": stat.st_size,
            "updated_at": stat.st_mtime,
            "assets": _list_assets(asset_dir),
            "title": _readable_output_title(markdown),
        }
    )
    return {"readableOutput": artifact, "history": []}


def resolve_session_readable_asset(session_id: str, asset_path: str) -> Path:
    payload = get_session_readable_output(session_id)
    artifact = payload.get("readableOutput") if isinstance(payload, dict) else None
    if not isinstance(artifact, dict) or not artifact.get("exists"):
        raise SessionReadableOutputError("Readable output not found.", 404)
    asset_dir = Path(str(artifact.get("assetDir") or "")).resolve()
    rel = str(asset_path or "").strip().lstrip("/")
    if not rel:
        raise SessionReadableOutputError("Asset path is required.")
    rel_candidates = [rel]
    if rel.startswith("./"):
        rel_candidates.append(rel[2:])
    for prefix in ("assets/", "./assets/"):
        if rel.startswith(prefix):
            rel_candidates.append(rel[len(prefix) :])
    for candidate_rel in rel_candidates:
        if not candidate_rel:
            continue
        try:
            target = (asset_dir / candidate_rel).resolve()
            target.relative_to(asset_dir)
        except Exception as exc:
            raise SessionReadableOutputError("Asset path is invalid.", 400) from exc
        if target.exists() and target.is_file():
            return target
    raise SessionReadableOutputError("Asset not found.", 404)

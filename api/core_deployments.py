"""Shell-neutral deployment facade for Hermes Core API.

This module provides a conservative Python implementation inspired by Cloud
Terminal's deployments domain.  It records deployment state inside the project,
detects common deploy artifacts, exposes provider capability metadata, and keeps
lifecycle operations serialized per project.  It does not copy Cloud Terminal's
Node provider implementation.
"""

from __future__ import annotations

import base64
import hashlib
import http.cookies
import hmac
import json
import os
import re
import signal
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import quote, unquote, urlparse, urlsplit

from api import ops_projects
from api.core_contracts import CoreApiError, coerce_core_error, now_iso, operation_record, project_root, redact_payload, relative_to_project, safe_project_child
from api.helpers import _redact_text
from api.runtime_process_cleanup import RuntimeProcessInfo, env_flag_enabled, iter_runtime_processes, terminate_process_group

DeploymentCoreError = CoreApiError
DEPLOYMENT_DIR = ".hermes/ops/deployments"
DEPLOYMENT_SOURCE_CLOUD_TERMINAL = "cloud-terminal"
CT_DEPLOYMENTS_DIR_NAME = ".deployments"
CT_DEPLOYMENTS_METADATA_FILE = "deployments.json"
CT_DEPLOYMENTS_ITEMS_DIR = "items"
CT_DEPLOYMENT_SOURCE_DIR_NAME = "source"
CT_DEPLOYMENT_PUBLIC_BASE_PATH = "/deploy"
LOG_LIMIT = 100
_COMMAND_TIMEOUT_SECONDS = 15 * 60
_DEPLOY_BUILD_TIMEOUT_SECONDS = 60 * 60
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
_DEPLOYMENT_RUNTIME_LOCK = threading.RLock()
_DEPLOYMENT_RUNTIMES: dict[str, "_DeploymentRuntimeState"] = {}
DEPLOYMENT_PROXY_COOKIE_NAME = "__hermes_deployment"
LEGACY_DEPLOYMENT_PROXY_COOKIE_NAME = "__ct_deployment"
DEPLOYMENT_PROXY_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
PLAY_CONFIG_CANDIDATES = ("project_play.json", "hermes.play.json", "play.json")
SNAPSHOT_SKIP_DIR_NAMES = {
    ".cache",
    ".cloud-terminal",
    ".deployments",
    ".git",
    ".parcel-cache",
    ".pnpm-store",
    ".turbo",
    "node_modules",
}
SNAPSHOT_ALLOW_ENV_SUFFIXES = (".example", ".sample")

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

DEPLOYMENT_COMPATIBILITY_API_EXACT_PATHS = {
    "/api/blob",
    "/api/nakama",
    "/api/trpc",
}
DEPLOYMENT_COMPATIBILITY_API_PREFIXES = (
    "/api/blob/",
    "/api/nakama/",
    "/api/trpc/",
)
DEPLOYMENT_COMPATIBILITY_PATH_PREFIXES = (
    "/assets/",
    "/auth/",
    "/app/",
    "/stream/",
    "/_stcore/",
)
DEPLOYMENT_COMPATIBILITY_EXACT_PATHS = {
    "/app",
    "/login",
    "/logout",
    "/signin",
    "/sign-in",
    "/signout",
    "/sign-out",
    "/manifest.webmanifest",
    "/manifest.json",
    "/favicon.ico",
    "/healthz",
}
LEGACY_PLAY_PROXY_DEPLOYMENT_RE = re.compile(r"^/play-proxy/[^/]+/deploy/([^/]+)(?:/(.*))?$")


@dataclass
class _DeploymentRuntimeState:
    project_id: str
    deployment_id: str | None
    slug: str
    snapshot_path: str
    host: str = "127.0.0.1"
    port: int | None = None
    port_env_var: str = "PORT"
    process: subprocess.Popen | None = None
    running: bool = False
    ready: bool = False
    stop_requested: bool = False
    status: str = "idle"
    error: str | None = None
    inspect_path: str = "/"
    public_base_path: str = ""
    public_path: str = ""
    public_entry_path: str = ""
    started_at: str | None = None
    ready_at: str | None = None
    finished_at: str | None = None
    updated_at: float = field(default_factory=time.time)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

PROVIDERS = [
    {
        "id": "manual",
        "label": "Manual record",
        "description": "Record deploy/rollback/stop events without running infrastructure commands.",
        "capabilities": {
            "record": True,
            "execute": False,
            "scaffold": True,
            "logs": True,
            "rollback": True,
            "stop": True,
            "requiresCommand": False,
        },
    },
    {
        "id": "local",
        "label": "Local command",
        "description": "Run an explicitly confirmed deployment command from the project root.",
        "capabilities": {
            "record": True,
            "execute": True,
            "scaffold": True,
            "logs": True,
            "rollback": True,
            "stop": True,
            "requiresCommand": True,
        },
    },
    {
        "id": "docker",
        "label": "Docker artifact",
        "description": "Use Dockerfile/docker-compose artifacts when present; commands are still explicit in this first Core API slice.",
        "capabilities": {
            "record": True,
            "execute": True,
            "scaffold": True,
            "logs": True,
            "rollback": False,
            "stop": True,
            "requiresCommand": True,
        },
    },
    {
        "id": "local-legacy",
        "label": "Cloud Terminal host (legacy)",
        "description": "Existing Cloud Terminal local deployment metadata; Hermes can redeploy it while preserving the deployment database mode.",
        "capabilities": {
            "record": True,
            "execute": True,
            "scaffold": False,
            "logs": True,
            "rollback": False,
            "stop": True,
            "requiresCommand": True,
            "externalRecord": True,
            "redeploy": True,
            "preservesDatabase": True,
        },
    },
    {
        "id": "container-local",
        "label": "Cloud Terminal container",
        "description": "Existing Cloud Terminal container-local deployment metadata.",
        "capabilities": {
            "record": True,
            "execute": True,
            "scaffold": False,
            "logs": True,
            "rollback": False,
            "stop": True,
            "requiresCommand": True,
            "externalRecord": True,
            "redeploy": True,
            "preservesDatabase": True,
        },
    },
    {
        "id": "google-cloud-run",
        "label": "Google Cloud Run",
        "description": "Existing Cloud Terminal Google Cloud Run deployment metadata.",
        "capabilities": {
            "record": True,
            "execute": True,
            "scaffold": False,
            "logs": True,
            "rollback": False,
            "stop": True,
            "requiresCommand": True,
            "externalRecord": True,
            "redeploy": True,
            "preservesDatabase": True,
        },
    },
]


def _lock_for(project_id: str) -> threading.RLock:
    key = str(project_id or "").strip() or "project"
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[key] = lock
        return lock


def _project(project_id: str) -> dict:
    try:
        return ops_projects.get_ops_project(project_id)
    except ops_projects.OpsProjectError as exc:
        raise coerce_core_error(exc, code="DEPLOYMENT_PROJECT_ERROR") from exc


def _deployment_dir(project: dict) -> Path:
    path = project_root(project) / DEPLOYMENT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _deployment_path(project: dict) -> Path:
    return _deployment_dir(project) / "deployment.json"


def _logs_path(project: dict) -> Path:
    return _deployment_dir(project) / "logs.jsonl"


def _read_json(path: Path, default: Any) -> Any:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default
    return parsed


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(redact_payload(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _text(value: Any, *, limit: int = 4000) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.strip()[:limit]


def _provider_id(value: Any) -> str:
    raw = _text(value, limit=64).lower().replace("_", "-").replace(" ", "-")
    ids = {provider["id"] for provider in PROVIDERS}
    return raw if raw in ids else "manual"


def _status(value: Any, *, default: str = "recorded") -> str:
    raw = _text(value, limit=64).lower().replace("_", "-").replace(" ", "-")
    allowed = {"not-configured", "recorded", "ready", "running", "succeeded", "failed", "rolled-back", "stopped", "published", "publishing", "updating", "starting"}
    return raw if raw in allowed else default


def _cloud_terminal_deployments_dir() -> Path | None:
    explicit = os.getenv("PROJECT_DEPLOYMENTS_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    try:
        return (ops_projects.ops_projects_metadata_path().parent / CT_DEPLOYMENTS_DIR_NAME).resolve()
    except Exception:
        return None


def _cloud_terminal_deployments_path() -> Path | None:
    deployments_dir = _cloud_terminal_deployments_dir()
    if deployments_dir is None:
        return None
    return deployments_dir / CT_DEPLOYMENTS_METADATA_FILE


def _read_cloud_terminal_deployments() -> list[dict]:
    path = _cloud_terminal_deployments_path()
    if path is None:
        return []
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    if not isinstance(parsed, list):
        return []
    return [entry for entry in parsed if isinstance(entry, dict)]


def _write_cloud_terminal_deployments(records: list[dict]) -> None:
    """Write Cloud Terminal metadata without redacting provider-owned state.

    Redaction is correct for Hermes-owned response/log payloads, but this file is
    an external deployment registry. Rewriting it through ``redact_payload``
    would silently destroy providerConfig/providerState values, so this helper
    preserves the records exactly except for explicit lifecycle patches.
    """

    path = _cloud_terminal_deployments_path()
    if path is None:
        raise CoreApiError("Cloud Terminal deployment metadata is unavailable.", 404, code="DEPLOYMENT_METADATA_UNAVAILABLE")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _patch_cloud_terminal_record(project_id: str, patch: dict) -> dict:
    records = _read_cloud_terminal_deployments()
    key = str(project_id or "").strip()
    for index, record in enumerate(records):
        if str(record.get("projectId") or "").strip() == key:
            next_record = {**record, **patch}
            records[index] = next_record
            _write_cloud_terminal_deployments(records)
            return next_record
    raise CoreApiError("Deployment not found.", 404, code="DEPLOYMENT_NOT_FOUND")


def _normalize_deployment_slug(value: Any) -> str:
    raw = _text(value, limit=128).lower()
    cleaned = []
    previous_dash = False
    for char in raw:
        keep = char if (char.isalnum() or char == "-") else "-"
        if keep == "-":
            if previous_dash:
                continue
            previous_dash = True
        else:
            previous_dash = False
        cleaned.append(keep)
    return "".join(cleaned).strip("-")[:63]


def _cloud_terminal_storage_key(record: dict) -> str:
    slug = _normalize_deployment_slug(record.get("slug"))
    if slug:
        return slug
    provider = _text(record.get("provider"), limit=64).lower() or "local-legacy"
    if provider == "local-legacy":
        return ""
    return _text(record.get("id"), limit=128)


def _cloud_terminal_source_path(record: dict) -> Path | None:
    deployments_dir = _cloud_terminal_deployments_dir()
    storage_key = _cloud_terminal_storage_key(record)
    if deployments_dir is None or not storage_key:
        return None
    return deployments_dir / CT_DEPLOYMENTS_ITEMS_DIR / storage_key / CT_DEPLOYMENT_SOURCE_DIR_NAME


def _cloud_terminal_public_url(record: dict) -> str:
    slug = _normalize_deployment_slug(record.get("slug"))
    if not slug:
        return ""
    return f"{CT_DEPLOYMENT_PUBLIC_BASE_PATH}/{quote(slug)}/"


def _cloud_terminal_record_for_project(project_id: str) -> dict | None:
    key = str(project_id or "").strip()
    if not key:
        return None
    for record in _read_cloud_terminal_deployments():
        if str(record.get("projectId") or "").strip() == key:
            return record
    return None


def _cloud_terminal_record_for_public_identifier(identifier: str) -> dict | None:
    key = _normalize_deployment_slug(unquote(str(identifier or "").strip()))
    if not key:
        return None
    for record in _read_cloud_terminal_deployments():
        slug = _normalize_deployment_slug(record.get("slug"))
        if slug and slug == key:
            return record
        record_id = _normalize_deployment_slug(record.get("id"))
        if record_id and record_id == key:
            return record
    return None


def _cloud_terminal_public_base_path(record: dict) -> str:
    slug = _normalize_deployment_slug(record.get("slug"))
    return f"{CT_DEPLOYMENT_PUBLIC_BASE_PATH}/{quote(slug)}" if slug else ""


def _deployment_public_path(record: dict) -> str:
    base = _cloud_terminal_public_base_path(record)
    return f"{base}/" if base else ""


def _deployment_entry_path(public_base_path: str, public_path: str, entry_path: str) -> str:
    base = str(public_base_path or "").rstrip("/")
    public = str(public_path or "")
    entry = str(entry_path or "").strip()
    if not base:
        return entry or public
    if not entry:
        return public or f"{base}/"
    if entry == base or entry.startswith(f"{base}/"):
        return entry
    if not entry.startswith("/"):
        entry = f"/{entry}"
    return f"{base}{entry if entry != '/' else '/'}"


def _parse_cookie_header(raw_cookie: str) -> dict[str, str]:
    cookie = http.cookies.SimpleCookie()
    try:
        cookie.load(raw_cookie or "")
    except http.cookies.CookieError:
        return {}
    return {key: morsel.value for key, morsel in cookie.items()}


def _deployment_slug_from_cookie_header(raw_cookie: str) -> str:
    parsed = _parse_cookie_header(raw_cookie)
    return _normalize_deployment_slug(
        parsed.get(DEPLOYMENT_PROXY_COOKIE_NAME)
        or parsed.get(LEGACY_DEPLOYMENT_PROXY_COOKIE_NAME)
        or ""
    )


def _deployment_slug_from_referer(raw_referer: str) -> str:
    if not raw_referer:
        return ""
    try:
        parsed = urlparse(raw_referer)
    except Exception:
        return ""
    path = parsed.path or ""
    prefix = f"{CT_DEPLOYMENT_PUBLIC_BASE_PATH}/"
    if not path.startswith(prefix):
        return ""
    tail = path[len(prefix):]
    slug = tail.split("/", 1)[0]
    return _normalize_deployment_slug(unquote(slug))


def deployment_slug_from_request_context(handler, parsed=None) -> str:
    """Return the deployment slug implied by a request path, referer, or cookie."""

    path = getattr(parsed, "path", "") if parsed is not None else ""
    prefix = f"{CT_DEPLOYMENT_PUBLIC_BASE_PATH}/"
    if path.startswith(prefix):
        slug = path[len(prefix):].split("/", 1)[0]
        normalized = _normalize_deployment_slug(unquote(slug))
        if normalized:
            return normalized
    legacy_match = LEGACY_PLAY_PROXY_DEPLOYMENT_RE.match(path)
    if legacy_match:
        normalized = _normalize_deployment_slug(unquote(legacy_match.group(1)))
        if normalized:
            return normalized
    headers = getattr(handler, "headers", {}) or {}
    referer_slug = _deployment_slug_from_referer(headers.get("Referer", "") or headers.get("Referrer", ""))
    if referer_slug:
        return referer_slug
    return _deployment_slug_from_cookie_header(headers.get("Cookie", ""))


def _is_deployment_compatibility_path(path: str) -> bool:
    value = str(path or "")
    # Root-relative /api/* compatibility is intentionally narrow. Hermes owns
    # most root API namespaces; deployments can proxy arbitrary APIs through
    # explicit /deploy/{slug}/api/... paths.
    if value in DEPLOYMENT_COMPATIBILITY_API_EXACT_PATHS:
        return True
    if any(value.startswith(prefix) for prefix in DEPLOYMENT_COMPATIBILITY_API_PREFIXES):
        return True
    if value in DEPLOYMENT_COMPATIBILITY_EXACT_PATHS:
        return True
    return any(value.startswith(prefix) for prefix in DEPLOYMENT_COMPATIBILITY_PATH_PREFIXES)


def is_deployment_public_request(handler, parsed) -> bool:
    """Return True for public deployment proxy requests that bypass WebUI auth/CSRF."""

    path = getattr(parsed, "path", "") or ""
    if path == CT_DEPLOYMENT_PUBLIC_BASE_PATH or path.startswith(f"{CT_DEPLOYMENT_PUBLIC_BASE_PATH}/"):
        return True
    if LEGACY_PLAY_PROXY_DEPLOYMENT_RE.match(path):
        return True
    if not _is_deployment_compatibility_path(path):
        return False
    return bool(deployment_slug_from_request_context(handler, parsed))


def _cloud_terminal_snapshot_artifact(record: dict | None) -> dict | None:
    if not record:
        return None
    storage_key = _cloud_terminal_storage_key(record)
    if not storage_key:
        return None
    source_path = _cloud_terminal_source_path(record)
    return {
        "kind": "cloud-terminal-snapshot",
        "relativePath": f"{CT_DEPLOYMENTS_DIR_NAME}/{CT_DEPLOYMENTS_ITEMS_DIR}/{storage_key}/{CT_DEPLOYMENT_SOURCE_DIR_NAME}",
        "path": str(source_path) if source_path else "",
        "providerHints": [_text(record.get("provider"), limit=64) or "local-legacy"],
        "size": None,
        "exists": bool(source_path and source_path.exists()),
        "source": DEPLOYMENT_SOURCE_CLOUD_TERMINAL,
    }


def _cloud_terminal_deployment(project: dict) -> dict | None:
    record = _cloud_terminal_record_for_project(str(project.get("id") or ""))
    if not record:
        return None
    provider = _text(record.get("provider"), limit=64) or "local-legacy"
    slug = _normalize_deployment_slug(record.get("slug"))
    database_mode = _text(record.get("databaseMode"), limit=64) or None
    updated_at = _text(record.get("updatedAt"), limit=128) or _text(record.get("publishedAt"), limit=128) or _text(record.get("createdAt"), limit=128) or None
    status = _status(record.get("status"), default="recorded")
    storage_key = _cloud_terminal_storage_key(record)
    source_path = _cloud_terminal_source_path(record)
    summary_bits = ["Cloud Terminal deployment"]
    if slug:
        summary_bits.append(f"`{slug}`")
    summary_bits.append(f"is {status}.")
    if database_mode:
        summary_bits.append(f"Database mode is {database_mode}; Hermes reads this record without recreating or overwriting that database.")
    deployment_project_id = f"{project['id']}__deployment" if database_mode and database_mode != "shared" else project["id"]
    return {
        **_default_deployment(project),
        "id": _text(record.get("id"), limit=128),
        "projectId": project["id"],
        "source": DEPLOYMENT_SOURCE_CLOUD_TERMINAL,
        "provider": provider,
        "status": status,
        "environment": "production",
        "summary": " ".join(summary_bits),
        "url": _cloud_terminal_public_url(record),
        "slug": slug,
        "databaseMode": database_mode,
        "database": {
            "mode": database_mode,
            "preservesExistingData": database_mode in {"persistent", "shared"},
            "deploymentProjectId": deployment_project_id,
        } if database_mode else None,
        "createdAt": _text(record.get("createdAt"), limit=128) or None,
        "updatedAt": updated_at,
        "publishedAt": _text(record.get("publishedAt"), limit=128) or None,
        "externalRecord": True,
        "cloudTerminal": {
            "storageKey": storage_key,
            "snapshotPath": str(source_path) if source_path else "",
            "metadataPath": str(_cloud_terminal_deployments_path() or ""),
            "databaseMode": database_mode,
        },
    }


def provider_registry() -> dict:
    return {"providers": redact_payload(PROVIDERS), "defaultProvider": "manual"}


def _artifact(project: dict, root: Path, rel: str, kind: str, *, provider_hints: list[str] | None = None) -> dict | None:
    path = root / rel
    if not path.exists():
        return None
    return {
        "kind": kind,
        "relativePath": rel,
        "path": relative_to_project(project, path),
        "providerHints": provider_hints or [],
        "size": path.stat().st_size if path.is_file() else None,
    }


def detect_project_artifacts(project_id: str) -> dict:
    project = _project(project_id)
    root = project_root(project)
    artifacts = []
    candidates = [
        ("Dockerfile", "dockerfile", ["docker"]),
        ("docker-compose.yml", "docker-compose", ["docker"]),
        ("compose.yml", "docker-compose", ["docker"]),
        ("package.json", "node-package", ["local", "docker"]),
        ("pnpm-lock.yaml", "node-lockfile", ["local", "docker"]),
        ("yarn.lock", "node-lockfile", ["local", "docker"]),
        ("requirements.txt", "python-requirements", ["local", "docker"]),
        ("pyproject.toml", "python-project", ["local", "docker"]),
        ("Procfile", "procfile", ["manual", "local"]),
        ("render.yaml", "render-config", ["manual"]),
        ("railway.json", "railway-config", ["manual"]),
        ("fly.toml", "fly-config", ["manual"]),
        (".github/workflows", "github-actions", ["manual"]),
    ]
    for rel, kind, hints in candidates:
        try:
            entry = _artifact(project, root, rel, kind, provider_hints=hints)
        except OSError:
            entry = None
        if entry:
            artifacts.append(entry)
    return redact_payload({"projectId": project["id"], "artifacts": artifacts})


def _read_logs(project: dict, *, limit: int = LOG_LIMIT) -> list[dict]:
    path = _logs_path(project)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    except OSError:
        return []
    logs = []
    for line in lines[-max(1, min(int(limit or LOG_LIMIT), 500)):]:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            logs.append(redact_payload(parsed))
    return logs


def _append_log(project: dict, entry: dict) -> dict:
    payload = redact_payload({
        "timestamp": now_iso(),
        "level": _text(entry.get("level"), limit=32) or "info",
        "action": _text(entry.get("action"), limit=64),
        "message": _redact_text(_text(entry.get("message"), limit=8000)),
        "details": entry.get("details") if isinstance(entry.get("details"), dict) else {},
    })
    path = _logs_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload


def _default_deployment(project: dict) -> dict:
    return {
        "projectId": project["id"],
        "status": "not-configured",
        "provider": "manual",
        "environment": "production",
        "summary": "No deployment has been recorded for this project.",
        "updatedAt": None,
    }


def _read_deployment(project: dict) -> dict:
    payload = _read_json(_deployment_path(project), {})
    if isinstance(payload, dict) and payload:
        return {**_default_deployment(project), **payload, "projectId": project["id"]}
    cloud_terminal = _cloud_terminal_deployment(project)
    if cloud_terminal:
        return cloud_terminal
    return _default_deployment(project)


def _deployment_artifacts(project: dict, deployment: dict) -> list[dict]:
    artifacts = detect_project_artifacts(project["id"])["artifacts"]
    if deployment.get("source") == DEPLOYMENT_SOURCE_CLOUD_TERMINAL:
        artifact = _cloud_terminal_snapshot_artifact(_cloud_terminal_record_for_project(project["id"]))
        if artifact:
            artifacts = [artifact, *artifacts]
    return artifacts


def _deployment_logs(project: dict, deployment: dict, *, limit: int = LOG_LIMIT) -> list[dict]:
    logs = _read_logs(project, limit=limit)
    if logs or deployment.get("source") != DEPLOYMENT_SOURCE_CLOUD_TERMINAL:
        return logs
    return [
        redact_payload({
            "timestamp": deployment.get("updatedAt") or deployment.get("publishedAt") or deployment.get("createdAt"),
            "level": "info",
            "action": "cloud-terminal.metadata",
            "message": "Cloud Terminal deployment metadata loaded read-only; database mode was preserved.",
            "details": {
                "provider": deployment.get("provider"),
                "status": deployment.get("status"),
                "databaseMode": deployment.get("databaseMode"),
            },
        })
    ]


def get_project_deployment(project_id: str, *, log_limit: int = LOG_LIMIT) -> dict:
    project = _project(project_id)
    deployment = _read_deployment(project)
    artifacts = _deployment_artifacts(project, deployment)
    logs = _deployment_logs(project, deployment, limit=log_limit)
    return redact_payload({
        "projectId": project["id"],
        "supported": True,
        "providers": PROVIDERS,
        "deployment": deployment,
        "artifacts": artifacts,
        "logs": logs,
        "summary": deployment.get("summary") or "Deployment status loaded.",
    })


def _snapshot_ignore(_directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        lowered = name.lower()
        if name in SNAPSHOT_SKIP_DIR_NAMES or lowered in SNAPSHOT_SKIP_DIR_NAMES:
            ignored.add(name)
            continue
        if lowered == ".env" or lowered.startswith(".env."):
            if not lowered.endswith(SNAPSHOT_ALLOW_ENV_SUFFIXES):
                ignored.add(name)
    return ignored


def _count_files(root: Path) -> int:
    try:
        return sum(1 for path in root.rglob("*") if path.is_file())
    except OSError:
        return 0


def _normalize_deploy_build_timeout(value: Any) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = 0
    if parsed <= 0:
        try:
            parsed = float(os.getenv("HERMES_WEBUI_CORE_DEPLOY_BUILD_TIMEOUT_SECONDS", "") or 0)
        except Exception:
            parsed = 0
    if parsed <= 0:
        parsed = _DEPLOY_BUILD_TIMEOUT_SECONDS
    return max(1.0, min(parsed, 6 * 60 * 60))


def _normalize_deploy_build_env(value: Any) -> dict[str, str]:
    source = value if isinstance(value, dict) else {}
    env: dict[str, str] = {}
    for key, raw in source.items():
        name = str(key or "").strip()
        if not name or raw is None:
            continue
        env[name] = str(raw)
    return env


def _is_env_name(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value or ""))


def _decode_double_quoted_dotenv_value(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace("\\f", "\f")
        .replace("\\v", "\v")
        .replace("\\b", "\b")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )


def _parse_dotenv_text(source: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    lines = str(source or "").lstrip("\ufeff").splitlines()
    index = 0
    while index < len(lines):
        raw_line = str(lines[index] or "")
        index += 1
        working = raw_line.strip()
        if not working or working.startswith("#"):
            continue
        if working.startswith("export "):
            working = working[len("export ") :].lstrip()
        if "=" not in working:
            continue
        key, raw_value = working.split("=", 1)
        key = key.strip()
        if not _is_env_name(key):
            continue
        raw_value = raw_value.lstrip()
        if not raw_value:
            entries[key] = ""
            continue
        if raw_value[0] in {"'", '"'}:
            quote = raw_value[0]
            remainder = raw_value[1:]
            collected = ""
            while True:
                closing = -1
                for position, char in enumerate(remainder):
                    if char != quote:
                        continue
                    backslashes = 0
                    cursor = position - 1
                    while cursor >= 0 and remainder[cursor] == "\\":
                        backslashes += 1
                        cursor -= 1
                    if backslashes % 2 == 0:
                        closing = position
                        break
                if closing >= 0:
                    collected += remainder[:closing]
                    break
                collected += remainder
                if index >= len(lines):
                    break
                collected += "\n"
                remainder = str(lines[index] or "")
                index += 1
            entries[key] = _decode_double_quoted_dotenv_value(collected) if quote == '"' else collected
            continue
        comment = re.search(r"\s#", raw_value)
        entries[key] = (raw_value[: comment.start()].rstrip() if comment else raw_value.strip())
    return entries


def _read_dotenv_entries(path: Path) -> dict[str, str]:
    try:
        return _parse_dotenv_text(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _read_first_non_comment_line(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        trimmed = line.strip()
        if trimmed and not trimmed.startswith("#"):
            return trimmed
    return ""


def _resolve_stage_env_value(raw_value: str, *sources: dict[str, str]) -> str:
    if not isinstance(raw_value, str):
        return raw_value
    trimmed = raw_value.strip()
    if not (trimmed.startswith("${") and trimmed.endswith("}")):
        return raw_value
    key = trimmed[2:-1].strip()
    if not key:
        return raw_value
    for source in sources:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return raw_value


def _find_nearest_project_dotenv(start_dir: Path, project_path: Path) -> Path | None:
    current = start_dir.resolve()
    root = project_path.resolve()
    while True:
        candidate = current / ".env"
        if candidate.exists():
            return candidate
        if current == root:
            return None
        parent = current.parent
        if parent == current:
            return None
        try:
            parent.relative_to(root)
        except ValueError:
            return None
        current = parent


def _active_app_selections(project_path: Path, baseline_env: dict[str, str]) -> list[str]:
    raw = (
        baseline_env.get("MONOREPO_ACTIVE_APP")
        or baseline_env.get("MONOREPO_DEFAULT_APP")
        or _read_first_non_comment_line(project_path / ".active-app")
        or _read_first_non_comment_line(project_path / ".replit-active-app")
    )
    return [entry.strip() for entry in str(raw or "").split(",") if entry.strip()]


def _resolve_app_directory(project_path: Path, selection: str) -> str:
    normalized = _text(selection, limit=256)
    if not normalized:
        return ""
    direct = project_path / "apps" / normalized
    if direct.exists() and direct.is_dir():
        return normalized
    return normalized


def _runtime_env_defaults(project: dict, cwd: str, explicit_env: dict[str, str]) -> dict[str, str]:
    try:
        root = project_root(project)
    except CoreApiError:
        return {}
    baseline = {key: str(value) for key, value in os.environ.items()}
    baseline.update({key: str(value) for key, value in (explicit_env or {}).items() if value is not None})
    loaded: dict[str, str] = {}
    root_keys: set[str] = set()
    try:
        command_dir = _runtime_cwd(root, cwd)
    except CoreApiError:
        command_dir = root
    root_dotenv = _find_nearest_project_dotenv(command_dir, root)
    if root_dotenv:
        for key, value in _read_dotenv_entries(root_dotenv).items():
            if key in baseline:
                continue
            loaded[key] = _resolve_stage_env_value(value, baseline, loaded)
            root_keys.add(key)

    node_env = baseline.get("NODE_ENV", "").strip()
    app_keys: set[str] = set()
    for selection in _active_app_selections(root, {**baseline, **loaded}):
        app_dir = _resolve_app_directory(root, selection)
        if not app_dir:
            continue
        app_root = root / "apps" / app_dir
        candidates = [app_root / ".env", app_root / ".env.local"]
        if node_env:
            candidates.extend([app_root / f".env.{node_env}", app_root / f".env.{node_env}.local"])
        for candidate in candidates:
            for key, value in _read_dotenv_entries(candidate).items():
                if key in baseline:
                    continue
                loaded[key] = _resolve_stage_env_value(value, baseline, loaded)
                app_keys.add(key)
                if key in root_keys:
                    root_keys.discard(key)
    return loaded


def _normalize_deploy_build_cwd(project: dict, value: Any) -> Path:
    raw = _text(value, limit=512) or "."
    if raw.startswith("/"):
        raise CoreApiError("Deployment build cwd must be relative to the project root.", 400, code="DEPLOYMENT_BUILD_CWD_INVALID")
    cwd = safe_project_child(project, raw)
    if not cwd.exists() or not cwd.is_dir():
        raise CoreApiError("Deployment build cwd is missing on disk.", 404, code="DEPLOYMENT_BUILD_CWD_MISSING", details={"cwd": raw})
    return cwd


def _package_manager_for_project(root: Path) -> str:
    package_json = root / "package.json"
    try:
        package_payload = json.loads(package_json.read_text(encoding="utf-8") or "{}")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        package_payload = {}
    package_manager = _text((package_payload if isinstance(package_payload, dict) else {}).get("packageManager"), limit=128)
    package_manager_name = package_manager.split("@", 1)[0].strip().lower()
    if package_manager_name in {"pnpm", "yarn", "bun", "npm"}:
        return package_manager_name
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        return "bun"
    return "npm"


def _package_script_command(package_manager: str, script: str) -> str:
    script = _text(script, limit=128) or "build"
    if package_manager == "yarn":
        return f"yarn {script}"
    return f"{package_manager} run {script}"


def _timeout_from_play_config(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return float(value) / 1000
    return value


def _read_deploy_build_plan(project: dict) -> dict | None:
    root = project_root(project)
    for filename in PLAY_CONFIG_CANDIDATES:
        path = root / filename
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise CoreApiError("Deployment Play config is invalid JSON.", 400, code="DEPLOYMENT_BUILD_CONFIG_INVALID", details={"path": filename}) from exc
        source: dict[str, Any] = payload if isinstance(payload, dict) else {}
        build_raw = source.get("build")
        build: dict[str, Any] = build_raw if isinstance(build_raw, dict) else {}
        command = _text(build.get("command") or source.get("buildCommand"), limit=4000)
        if not command:
            continue
        return {
            "source": filename,
            "command": command,
            "cwd": _text(build.get("cwd") or source.get("buildCwd"), limit=512) or ".",
            "env": _normalize_deploy_build_env(build.get("env") or source.get("buildEnv")),
            "timeoutSeconds": _normalize_deploy_build_timeout(
                _timeout_from_play_config(build.get("timeoutMs") or source.get("buildTimeoutMs"))
                or build.get("timeoutSeconds")
                or source.get("buildTimeoutSeconds")
            ),
        }

    package_json = root / "package.json"
    if not package_json.exists():
        return None
    try:
        package_payload = json.loads(package_json.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return None
    package_source: dict[str, Any] = package_payload if isinstance(package_payload, dict) else {}
    scripts_raw = package_source.get("scripts")
    scripts: dict[str, Any] = scripts_raw if isinstance(scripts_raw, dict) else {}
    if not _text(scripts.get("build"), limit=4000):
        return None
    package_manager = _package_manager_for_project(root)
    return {
        "source": "package.json",
        "command": _package_script_command(package_manager, "build"),
        "cwd": ".",
        "env": {"CI": "true"},
        "timeoutSeconds": _normalize_deploy_build_timeout(None),
    }


def _run_core_deployment_build(project: dict, payload: dict) -> dict:
    if payload.get("skipBuild") is True:
        return {"skipped": True, "reason": "request"}
    plan = _read_deploy_build_plan(project)
    if not plan:
        return {"skipped": True, "reason": "no-build-command"}
    command = _text(plan.get("command"), limit=4000)
    cwd = _normalize_deploy_build_cwd(project, plan.get("cwd"))
    timeout = _normalize_deploy_build_timeout(plan.get("timeoutSeconds"))
    started = now_iso()
    try:
        completed = subprocess.run(
            ["bash", "-lc", command],
            cwd=str(cwd),
            env={
                **os.environ,
                **_normalize_deploy_build_env(plan.get("env")),
                "HERMES_CORE_DEPLOYMENT_ACTION": "redeploy",
                "HERMES_CORE_DEPLOYMENT_PROVIDER": "local-legacy",
            },
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CoreApiError(
            "Deployment build timed out before snapshot promotion; the existing deployment snapshot was left unchanged.",
            500,
            code="DEPLOYMENT_REDEPLOY_BUILD_TIMEOUT",
            details={
                "command": command,
                "source": plan.get("source"),
                "timeoutSeconds": timeout,
                "stdout": _redact_text(str(exc.stdout or "")[-12000:]),
                "stderr": _redact_text(str(exc.stderr or "")[-12000:]),
            },
        ) from exc
    stdout = _redact_text((completed.stdout or "")[-12000:])
    stderr = _redact_text((completed.stderr or "")[-12000:])
    if completed.returncode != 0:
        raise CoreApiError(
            "Deployment build failed before snapshot promotion; the existing deployment snapshot was left unchanged.",
            500,
            code="DEPLOYMENT_REDEPLOY_BUILD_FAILED",
            details={
                "command": command,
                "source": plan.get("source"),
                "exitCode": completed.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "startedAt": started,
            },
        )
    return {
        "skipped": False,
        "source": plan.get("source"),
        "command": command,
        "cwd": str(cwd),
        "exitCode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "startedAt": started,
    }


def _runtime_dependency_install_candidates(package_manager: str) -> list[dict[str, Any]]:
    if package_manager == "pnpm":
        return [
            {"command": "pnpm install --frozen-lockfile", "continueOnFailure": True},
            {"command": "pnpm install", "continueOnFailure": False},
            {"command": "corepack pnpm install --frozen-lockfile", "continueOnFailure": True},
            {"command": "corepack pnpm install", "continueOnFailure": False},
        ]
    if package_manager == "yarn":
        return [
            {"command": "yarn install --immutable", "continueOnFailure": True},
            {"command": "yarn install", "continueOnFailure": False},
            {"command": "corepack yarn install --immutable", "continueOnFailure": True},
            {"command": "corepack yarn install", "continueOnFailure": False},
        ]
    if package_manager == "bun":
        return [{"command": "bun install", "continueOnFailure": False}]
    return [{"command": "npm install", "continueOnFailure": False}]


def _maybe_install_runtime_dependencies(project: dict, state: _DeploymentRuntimeState, snapshot_path: Path) -> dict:
    package_json = snapshot_path / "package.json"
    if not package_json.exists():
        _append_runtime_log(project, state, stage="dependencies", stream="system", message="No package.json found in the deployment snapshot. Skipping dependency install.")
        return {"skipped": True, "reason": "no-package-json"}
    if (snapshot_path / "node_modules").exists():
        _append_runtime_log(project, state, stage="dependencies", stream="system", message="Using existing node_modules from the deployment snapshot.")
        return {"skipped": True, "reason": "node-modules-present"}

    package_manager = _package_manager_for_project(snapshot_path)
    candidates = _runtime_dependency_install_candidates(package_manager)
    last_result: dict[str, Any] | None = None
    install_env = {
        **os.environ,
        "CI": os.environ.get("CI", "true"),
        "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
        "NO_PROXY": os.environ.get("NO_PROXY", "localhost,127.0.0.1"),
    }
    for candidate in candidates:
        command = str(candidate.get("command") or "").strip()
        if not command:
            continue
        _append_runtime_log(project, state, stage="dependencies", stream="system", message=f"Installing deployment runtime dependencies: {command}")
        completed = subprocess.run(
            ["bash", "-lc", command],
            cwd=str(snapshot_path),
            env=install_env,
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
        stdout = _redact_text((completed.stdout or "")[-8000:])
        stderr = _redact_text((completed.stderr or "")[-8000:])
        last_result = {
            "command": command,
            "packageManager": package_manager,
            "exitCode": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
        if completed.returncode == 0:
            _append_runtime_log(project, state, stage="dependencies", stream="system", message=f"Deployment runtime dependencies installed via {command}.")
            return {"skipped": False, **last_result}
        _append_runtime_log(project, state, stage="dependencies", stream="stderr", message=f"Dependency install command failed with exit code {completed.returncode}: {command}")
        if not candidate.get("continueOnFailure"):
            break

    raise CoreApiError(
        "Deployment runtime dependency install failed before start.",
        500,
        code="DEPLOYMENT_RUNTIME_DEPENDENCY_INSTALL_FAILED",
        details=last_result or {"packageManager": package_manager},
    )


PUBLIC_ASSET_DIR_CANDIDATES = (
    "packages/client/dist/assets",
    "packages/client/dist/lib",
    "dist/assets",
    "build/assets",
    "public/assets",
)


def _copy_missing_public_asset_tree(previous_source: Path, staged_source: Path, rel: str) -> int:
    previous_root = previous_source / rel
    staged_root = staged_source / rel
    if not previous_root.exists() or not previous_root.is_dir():
        return 0
    copied = 0
    for source_path in previous_root.rglob("*"):
        if not source_path.is_file():
            continue
        try:
            relative = source_path.relative_to(previous_root)
        except ValueError:
            continue
        target_path = staged_root / relative
        if target_path.exists():
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        copied += 1
    return copied


def _preserve_previous_public_assets(previous_source: Path, staged_source: Path) -> dict:
    """Carry old hashed browser assets into the new snapshot.

    Vite/Webpack-style builds put content hashes in filenames. During a redeploy,
    an already-open tab can still request the previous hash after Core promotes a
    new snapshot. If we delete those files, the app server's SPA fallback may
    answer with ``index.html`` and browsers report the confusing
    ``text/html``-for-module error. Keeping old immutable asset files alongside
    the new build makes redeploys tolerant of cached/open pages without touching
    the persistent database.
    """

    preserved_by_dir: dict[str, int] = {}
    for rel in PUBLIC_ASSET_DIR_CANDIDATES:
        copied = _copy_missing_public_asset_tree(previous_source, staged_source, rel)
        if copied:
            preserved_by_dir[rel] = copied
    return {
        "preservedFileCount": sum(preserved_by_dir.values()),
        "preservedByDirectory": preserved_by_dir,
    }


def _replace_cloud_terminal_snapshot(project: dict, record: dict, *, retain_backup: bool = False) -> dict:
    deployments_dir = _cloud_terminal_deployments_dir()
    storage_key = _cloud_terminal_storage_key(record)
    if deployments_dir is None or not storage_key:
        raise CoreApiError("Cloud Terminal deployment snapshot path is unavailable.", 404, code="DEPLOYMENT_SNAPSHOT_UNAVAILABLE")

    project_path = project_root(project)
    items_dir = deployments_dir / CT_DEPLOYMENTS_ITEMS_DIR
    temp_dir = deployments_dir / ".tmp"
    target_root = items_dir / storage_key
    target_source = target_root / CT_DEPLOYMENT_SOURCE_DIR_NAME
    items_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    staged_root = Path(tempfile.mkdtemp(prefix=f"{storage_key}-redeploy-", dir=str(temp_dir)))
    staged_source = staged_root / CT_DEPLOYMENT_SOURCE_DIR_NAME
    backup_root: Path | None = None
    promoted = False
    preserved_assets = {"preservedFileCount": 0, "preservedByDirectory": {}}
    try:
        shutil.copytree(project_path, staged_source, ignore=_snapshot_ignore)
        if target_source.exists():
            preserved_assets = _preserve_previous_public_assets(target_source, staged_source)
        if target_root.exists():
            backup_root = Path(tempfile.mkdtemp(prefix=f"{storage_key}-backup-", dir=str(temp_dir)))
            shutil.rmtree(backup_root)
            target_root.rename(backup_root)
        staged_root.rename(target_root)
        promoted = True
        if backup_root and backup_root.exists() and not retain_backup:
            shutil.rmtree(backup_root, ignore_errors=True)
    except Exception as exc:
        if backup_root and backup_root.exists() and not target_root.exists():
            backup_root.rename(target_root)
        if not isinstance(exc, CoreApiError):
            raise CoreApiError("Unable to update deployment snapshot.", 500, code="DEPLOYMENT_SNAPSHOT_UPDATE_FAILED", details={"message": str(exc)}) from exc
        raise
    finally:
        if not promoted and staged_root.exists():
            shutil.rmtree(staged_root, ignore_errors=True)

    return {
        "storageKey": storage_key,
        "snapshotPath": str(target_source),
        "targetRoot": str(target_root),
        "backupRoot": str(backup_root) if backup_root else None,
        "sourceFileCount": _count_files(target_source),
        "preservedAssets": preserved_assets,
    }


def _discard_cloud_terminal_snapshot_backup(snapshot: dict) -> None:
    backup = Path(str((snapshot or {}).get("backupRoot") or ""))
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)


def _restore_cloud_terminal_snapshot_backup(snapshot: dict) -> bool:
    target = Path(str((snapshot or {}).get("targetRoot") or ""))
    backup = Path(str((snapshot or {}).get("backupRoot") or ""))
    if not backup.exists():
        return False
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    backup.rename(target)
    return True


def _read_runtime_play_config(snapshot_path: Path) -> tuple[dict | None, str | None]:
    for filename in PLAY_CONFIG_CANDIDATES:
        path = snapshot_path / filename
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise CoreApiError(
                "Deployment Play config is invalid JSON.",
                400,
                code="DEPLOYMENT_RUNTIME_CONFIG_INVALID",
                details={"path": filename},
            ) from exc
        return payload if isinstance(payload, dict) else {}, filename
    return None, None


def _normalize_runtime_env(value: Any) -> dict[str, str]:
    source = value if isinstance(value, dict) else {}
    env: dict[str, str] = {}
    for key, raw in source.items():
        name = str(key or "").strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            continue
        if raw is None:
            continue
        if isinstance(raw, bool):
            env[name] = "true" if raw else "false"
        else:
            env[name] = str(raw)
    return env


def _runtime_cwd(snapshot_path: Path, value: Any) -> Path:
    raw = _text(value, limit=512) or "."
    if raw.startswith("/"):
        raise CoreApiError("Deployment runtime cwd must be relative to the snapshot root.", 400, code="DEPLOYMENT_RUNTIME_CWD_INVALID")
    cwd = (snapshot_path / raw).resolve()
    try:
        cwd.relative_to(snapshot_path.resolve())
    except ValueError as exc:
        raise CoreApiError("Deployment runtime cwd must stay inside the snapshot root.", 400, code="DEPLOYMENT_RUNTIME_CWD_INVALID") from exc
    if not cwd.exists() or not cwd.is_dir():
        raise CoreApiError("Deployment runtime cwd is missing on disk.", 404, code="DEPLOYMENT_RUNTIME_CWD_MISSING", details={"cwd": raw})
    return cwd


def _normalize_port_range(value: Any) -> dict[str, int]:
    source = value if isinstance(value, dict) else {}
    try:
        minimum = int(source.get("min", 20000))
    except Exception:
        minimum = 20000
    try:
        maximum = int(source.get("max", 29999))
    except Exception:
        maximum = 29999
    minimum = max(1024, minimum)
    maximum = min(65535, maximum)
    if maximum < minimum:
        return {"min": 20000, "max": 29999}
    return {"min": minimum, "max": maximum}


def _is_port_open(host: str, port: int, *, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _allocate_runtime_port(host: str, range_config: Any) -> int:
    port_range = _normalize_port_range(range_config)
    for port in range(port_range["min"], port_range["max"] + 1):
        if not _is_port_open(host, port):
            return port
    raise CoreApiError(
        f"Deployment runtime could not find a free port in range {port_range['min']}-{port_range['max']}.",
        503,
        code="DEPLOYMENT_RUNTIME_PORT_UNAVAILABLE",
    )


def _normalize_runtime_ready_timeout_ms(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = 120000
    return max(5000, min(parsed, 30 * 60 * 1000))


def _normalize_runtime_proxy_path(raw_url: str) -> tuple[str, str]:
    value = str(raw_url or "").strip() or "/"
    try:
        parsed = urlsplit(value if value.startswith("/") or "://" in value else f"/{value}")
    except Exception:
        parsed = urlsplit("/")
    request_path = parsed.path or "/"
    if parsed.query:
        request_path = f"{request_path}?{parsed.query}"
    inspect_path = request_path
    if parsed.fragment:
        inspect_path = f"{inspect_path}#{parsed.fragment}"
    return request_path, inspect_path


def _interpolate_runtime_port(value: str, env_var: str, port: int) -> str:
    return str(value or "").replace(f"${{{env_var}}}", str(port)).replace(f"${env_var}", str(port))


def _runtime_plan(snapshot_path: Path, record: dict) -> dict:
    payload, config_source = _read_runtime_play_config(snapshot_path)
    if payload is None:
        return {"skipped": True, "reason": "no-play-config"}
    source = payload if isinstance(payload, dict) else {}
    start_raw = source.get("start") if isinstance(source.get("start"), dict) else source.get("run")
    start = start_raw if isinstance(start_raw, dict) else {}
    command = _text(start.get("command") or source.get("startCommand") or source.get("runCommand"), limit=4000)
    if not command:
        return {"skipped": True, "reason": "no-start-command", "source": config_source}
    inspect_raw = source.get("inspect") if isinstance(source.get("inspect"), dict) else {}
    inspect = inspect_raw if isinstance(inspect_raw, dict) else {}
    inspect_url = _text(inspect.get("url") or source.get("inspectUrl") or source.get("previewUrl") or source.get("url"), limit=2048) or "/"
    start_port = start.get("port") if isinstance(start.get("port"), dict) else {}
    if str(start_port.get("mode") or "").strip().lower() != "auto":
        raise CoreApiError(
            "Deployment runtime requires Play start.port.mode=auto so Core can proxy the published app.",
            409,
            code="DEPLOYMENT_RUNTIME_PORT_MODE_UNSUPPORTED",
        )
    host = _text(start_port.get("host"), limit=128).lower() or "127.0.0.1"
    if host in {"localhost", "::1"}:
        host = "127.0.0.1"
    if host not in {"127.0.0.1", "0.0.0.0"}:
        raise CoreApiError("Deployment runtime host must be loopback for the Core proxy.", 409, code="DEPLOYMENT_RUNTIME_HOST_UNSUPPORTED")
    env_var = _text(start_port.get("envVar"), limit=128) or "PORT"
    port = _allocate_runtime_port(host, start_port.get("range"))
    env = _normalize_runtime_env(start.get("env") or source.get("startEnv") or source.get("runEnv"))
    env[env_var] = str(port)
    env.setdefault("HERMES_DEPLOYMENT", "true")
    env.setdefault("HERMES_DEPLOYMENT_SLUG", _normalize_deployment_slug(record.get("slug")))
    project_id = _text(record.get("projectId"), limit=128)
    if project_id:
        env.setdefault("HERMES_DEPLOYMENT_PROJECT_ID", project_id)
    if _text(inspect.get("mode"), limit=64).lower() == "proxy":
        env.setdefault("SERVE_CLIENT_BUILD", "true")
    request_path, inspect_path = _normalize_runtime_proxy_path(_interpolate_runtime_port(inspect_url, env_var, port))
    public_base_path = _cloud_terminal_public_base_path(record)
    public_path = _deployment_public_path(record)
    return {
        "skipped": False,
        "source": config_source,
        "command": command,
        "cwd": _text(start.get("cwd") or source.get("startCwd") or source.get("runCwd"), limit=512) or ".",
        "env": env,
        "host": host,
        "port": port,
        "portEnvVar": env_var,
        "readyPattern": _text(inspect.get("readyPattern") or source.get("readyPattern"), limit=1000),
        "readyTimeoutMs": _normalize_runtime_ready_timeout_ms(inspect.get("readyTimeoutMs") or source.get("readyTimeoutMs")),
        "inspectPath": inspect_path,
        "requestPath": request_path,
        "publicBasePath": public_base_path,
        "publicPath": public_path,
        "publicEntryPath": _deployment_entry_path(public_base_path, public_path, inspect_path),
    }


def _append_runtime_log(project: dict, state: _DeploymentRuntimeState, *, stage: str, stream: str, message: str) -> None:
    if not message:
        return
    try:
        _append_log(
            project,
            {
                "action": "runtime",
                "stage": stage,
                "stream": stream,
                "message": _redact_text(message[-4000:]),
                "details": {
                    "deploymentId": state.deployment_id,
                    "slug": state.slug,
                    "port": state.port,
                },
            },
        )
    except Exception:
        pass


def _runtime_reader_thread(project: dict, state: _DeploymentRuntimeState, proc: subprocess.Popen, stream_name: str, ready_regex: re.Pattern | None, ready_event: threading.Event) -> None:
    stream = proc.stdout if stream_name == "stdout" else proc.stderr
    if not stream:
        return
    try:
        for line in stream:
            message = line.rstrip("\n")
            _append_runtime_log(project, state, stage="start", stream=stream_name, message=message)
            if ready_regex and ready_regex.search(message):
                ready_event.set()
    except Exception as exc:
        _append_runtime_log(project, state, stage="start", stream="stderr", message=f"Runtime log reader failed: {exc}")


def _terminate_runtime_process(proc: subprocess.Popen | None, timeout: float = 4.0) -> None:
    if not proc or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            return
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.05)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _deployment_runtime_process_matches(info: RuntimeProcessInfo, *, slug: str, project_id: str) -> bool:
    if not slug:
        return False
    env = info.environ or {}
    if not env_flag_enabled(env.get("HERMES_DEPLOYMENT")):
        return False
    if _normalize_deployment_slug(env.get("HERMES_DEPLOYMENT_SLUG")) != slug:
        return False
    runtime_project_id = str(env.get("HERMES_DEPLOYMENT_PROJECT_ID") or "").strip()
    if runtime_project_id and project_id and runtime_project_id != project_id:
        return False
    return True


def _deployment_runtime_pids(slug: str, project_id: str, *, keep_pid: int | None = None) -> list[int]:
    normalized_slug = _normalize_deployment_slug(slug)
    keep = {int(keep_pid)} if keep_pid else set()
    keep_pgids: set[int] = set()
    if keep_pid:
        try:
            keep_pgids.add(os.getpgid(int(keep_pid)))
        except OSError:
            pass
    pids: list[int] = []
    for info in iter_runtime_processes():
        if info.pid in keep or (info.pgid is not None and info.pgid in keep_pgids):
            continue
        if _deployment_runtime_process_matches(info, slug=normalized_slug, project_id=str(project_id or "")):
            pids.append(info.pid)
    return pids


def _stop_deployment_runtime_pids(slug: str, project_id: str, *, keep_pid: int | None = None) -> list[int]:
    stopped: list[int] = []
    for pid in _deployment_runtime_pids(slug, project_id, keep_pid=keep_pid):
        if terminate_process_group(pid):
            stopped.append(pid)
    return stopped


def _stop_stale_deployment_runtime_processes(project: dict, state: _DeploymentRuntimeState, *, keep_pid: int | None = None) -> list[int]:
    stopped = _stop_deployment_runtime_pids(state.slug, state.project_id, keep_pid=keep_pid)
    if stopped:
        _append_runtime_log(
            project,
            state,
            stage="start",
            stream="system",
            message=f"Stopped {len(stopped)} stale deployment runtime process(es) for slug {state.slug}.",
        )
    return stopped


def _runtime_process_watcher(project: dict, state: _DeploymentRuntimeState, proc: subprocess.Popen) -> None:
    code = proc.wait()
    with state.lock:
        if state.process is proc:
            state.process = None
        state.running = False
        state.ready = False
        state.finished_at = now_iso()
        state.updated_at = time.time()
        if state.stop_requested:
            state.status = "stopped"
        elif code == 0:
            state.status = "stopped"
        else:
            state.status = "failed"
            state.error = f"Deployment runtime exited with code {code}."
    with _DEPLOYMENT_RUNTIME_LOCK:
        if _DEPLOYMENT_RUNTIMES.get(state.project_id) is state:
            _DEPLOYMENT_RUNTIMES.pop(state.project_id, None)
    _append_runtime_log(project, state, stage="start", stream="system", message="Deployment runtime stopped." if code == 0 else f"Deployment runtime exited with code {code}.")


def _stop_runtime_state(project: dict, state: _DeploymentRuntimeState | None) -> None:
    if not state:
        return
    with state.lock:
        state.stop_requested = True
        proc = state.process
    _terminate_runtime_process(proc)
    with state.lock:
        state.process = None
        state.running = False
        state.ready = False
        state.status = "stopped"
        state.finished_at = now_iso()
        state.updated_at = time.time()
    _append_runtime_log(project, state, stage="start", stream="system", message="Deployment runtime stopped by Core.")


def _stop_project_runtime(project: dict) -> None:
    project_id = str(project.get("id") or "")
    with _DEPLOYMENT_RUNTIME_LOCK:
        state = _DEPLOYMENT_RUNTIMES.pop(project_id, None)
    _stop_runtime_state(project, state)
    slug = state.slug if state else ""
    if not slug:
        record = _cloud_terminal_record_for_project(project_id)
        slug = _normalize_deployment_slug((record or {}).get("slug"))
    if slug:
        _stop_deployment_runtime_pids(slug, project_id)


def _start_local_legacy_runtime(project: dict, record: dict, snapshot_path: Path, *, replace_existing: bool = True) -> dict:
    plan = _runtime_plan(snapshot_path, record)
    if plan.get("skipped"):
        return plan

    project_id = str(project.get("id") or "")
    state = _DeploymentRuntimeState(
        project_id=project_id,
        deployment_id=_text(record.get("id"), limit=128) or None,
        slug=_normalize_deployment_slug(record.get("slug")),
        snapshot_path=str(snapshot_path),
        host=plan["host"],
        port=int(plan["port"]),
        port_env_var=plan["portEnvVar"],
        status="starting",
        public_base_path=plan["publicBasePath"],
        public_path=plan["publicPath"],
        public_entry_path=plan["publicEntryPath"],
        inspect_path=plan["inspectPath"],
        started_at=now_iso(),
    )
    ready_event = threading.Event()
    ready_pattern = plan.get("readyPattern") or ""
    ready_regex = re.compile(str(ready_pattern), re.I) if ready_pattern else None
    env_defaults = _runtime_env_defaults(project, plan["cwd"], plan["env"])
    env = {**os.environ, **env_defaults, **plan["env"]}
    for key in ("TERMINAL_SU_PASSWORD", "SU_PASSWORD", "TERMINAL_SU_USER", "SU_USER"):
        env.pop(key, None)
    cwd = _runtime_cwd(snapshot_path, plan["cwd"])
    dependencies = _maybe_install_runtime_dependencies(project, state, snapshot_path)
    proc = subprocess.Popen(
        ["bash", "-lc", plan["command"]],
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    with state.lock:
        state.process = proc
        state.running = True
    _append_runtime_log(project, state, stage="start", stream="system", message=f"Running deployment runtime: {plan['command']}")
    _append_runtime_log(project, state, stage="start", stream="system", message=f"Deployment public entry path: {state.public_entry_path}")
    threads = [
        threading.Thread(target=_runtime_reader_thread, args=(project, state, proc, "stdout", ready_regex, ready_event), daemon=True),
        threading.Thread(target=_runtime_reader_thread, args=(project, state, proc, "stderr", ready_regex, ready_event), daemon=True),
    ]
    for thread in threads:
        thread.start()

    deadline = time.time() + (int(plan["readyTimeoutMs"]) / 1000)
    while time.time() <= deadline:
        code = proc.poll()
        if code is not None:
            raise CoreApiError(
                f"Deployment runtime exited before ready (exit code {code}).",
                500,
                code="DEPLOYMENT_REDEPLOY_START_FAILED",
            )
        if ready_event.is_set() or _is_port_open(state.host, int(state.port or 0)):
            break
        time.sleep(0.2)
    else:
        _terminate_runtime_process(proc)
        raise CoreApiError(
            f"Deployment runtime did not become ready within {round(int(plan['readyTimeoutMs']) / 1000)}s.",
            500,
            code="DEPLOYMENT_REDEPLOY_START_FAILED",
        )

    with state.lock:
        state.status = "ready"
        state.ready = True
        state.running = True
        state.ready_at = now_iso()
        state.updated_at = time.time()
    previous: _DeploymentRuntimeState | None = None
    with _DEPLOYMENT_RUNTIME_LOCK:
        previous = _DEPLOYMENT_RUNTIMES.get(project_id)
        if replace_existing or previous is None:
            _DEPLOYMENT_RUNTIMES[project_id] = state
    if previous is not None and previous is not state and replace_existing:
        _stop_runtime_state(project, previous)
    _stop_stale_deployment_runtime_processes(project, state, keep_pid=proc.pid)
    threading.Thread(target=_runtime_process_watcher, args=(project, state, proc), daemon=True).start()
    _append_runtime_log(project, state, stage="start", stream="system", message="Deployment runtime is ready.")
    return {
        "skipped": False,
        "source": plan.get("source"),
        "host": state.host,
        "port": state.port,
        "publicBasePath": state.public_base_path,
        "publicPath": state.public_path,
        "publicEntryPath": state.public_entry_path,
        "inspectPath": state.inspect_path,
        "dependencies": dependencies,
        "pid": int(proc.pid),
    }


def _active_runtime_state(project_id: str) -> _DeploymentRuntimeState | None:
    with _DEPLOYMENT_RUNTIME_LOCK:
        state = _DEPLOYMENT_RUNTIMES.get(str(project_id or ""))
    if not state:
        return None
    with state.lock:
        proc = state.process
        usable = bool(state.running and state.ready and state.port and proc and proc.poll() is None)
    if usable:
        return state
    with _DEPLOYMENT_RUNTIME_LOCK:
        if _DEPLOYMENT_RUNTIMES.get(str(project_id or "")) is state:
            _DEPLOYMENT_RUNTIMES.pop(str(project_id or ""), None)
    return None


def _ensure_local_legacy_runtime(project: dict, record: dict) -> _DeploymentRuntimeState | None:
    project_id = str(project.get("id") or record.get("projectId") or "")
    state = _active_runtime_state(project_id)
    if state:
        return state
    source_path = _cloud_terminal_source_path(record)
    if not source_path or not source_path.exists():
        raise CoreApiError("Deployment snapshot is missing on disk.", 503, code="DEPLOYMENT_RUNTIME_SNAPSHOT_MISSING")
    with _lock_for(project_id):
        state = _active_runtime_state(project_id)
        if state:
            return state
        runtime = _start_local_legacy_runtime(project, record, source_path, replace_existing=True)
        if runtime.get("skipped"):
            return None
        return _active_runtime_state(project_id)


def _proxy_error(handler, status: int, message: str) -> bool:
    body = str(message or "Deployment proxy error.").encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
    return True


def _deployment_proxy_cookie(slug: str) -> str:
    normalized = _normalize_deployment_slug(slug)
    return f"{DEPLOYMENT_PROXY_COOKIE_NAME}={quote(normalized)}; Path=/; HttpOnly; SameSite=Lax; Max-Age={DEPLOYMENT_PROXY_COOKIE_MAX_AGE_SECONDS}"


def _send_deployment_redirect(handler, location: str, slug: str, status: int = 302) -> bool:
    handler.send_response(status)
    handler.send_header("Location", location)
    handler.send_header("Set-Cookie", _deployment_proxy_cookie(slug))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", "0")
    handler.end_headers()
    return True


def _normalize_proxy_target_path(target_path: str, parsed) -> str:
    path = str(target_path or "") or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    query = getattr(parsed, "query", "") or ""
    if query and "?" not in path:
        path = f"{path}?{query}"
    return path


def _rewrite_deployment_public_url(value: str, state: _DeploymentRuntimeState) -> str:
    raw = str(value or "")
    if not raw or raw.startswith("#") or raw.startswith("//"):
        return raw
    if re.match(r"^[a-zA-Z][a-zA-Z\d+.-]*:", raw):
        try:
            parsed = urlparse(raw)
        except Exception:
            return raw
        if parsed.hostname not in {state.host, "localhost", "127.0.0.1"} or int(parsed.port or 80) != int(state.port or 0):
            return raw
        raw = f"{parsed.path or '/'}{('?' + parsed.query) if parsed.query else ''}{('#' + parsed.fragment) if parsed.fragment else ''}"
    base = state.public_base_path.rstrip("/")
    if not base:
        return raw
    if raw == base or raw.startswith(f"{base}/") or raw.startswith(f"{CT_DEPLOYMENT_PUBLIC_BASE_PATH}/"):
        return raw
    if not raw.startswith("/"):
        raw = f"/{raw}"
    return f"{base}{raw if raw != '/' else '/'}"


def _rewrite_deployment_html(body: bytes, state: _DeploymentRuntimeState) -> bytes:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body
    rewritten = re.sub(
        r"\b(src|href|action|poster)\s*=\s*([\"'])([^\"'<>]+)\2",
        lambda match: f"{match.group(1)}={match.group(2)}{_rewrite_deployment_public_url(match.group(3), state)}{match.group(2)}",
        text,
        flags=re.I,
    )
    return rewritten.encode("utf-8")


def _rewrite_deployment_location(location: str, state: _DeploymentRuntimeState) -> str:
    return _rewrite_deployment_public_url(location, state)


def _proxy_to_deployment_runtime(handler, state: _DeploymentRuntimeState, target_path: str, parsed, *, method: str = "GET") -> bool:
    if not state.port or not state.running or not state.ready:
        return _proxy_error(handler, 503, "Deployment is not running.")
    path = _normalize_proxy_target_path(target_path, parsed)
    upstream_url = f"http://{state.host}:{int(state.port)}{path}"
    body = None
    upper_method = method.upper()
    if upper_method not in {"GET", "HEAD"}:
        raw_body = getattr(handler, "_raw_body", None)
        if isinstance(raw_body, bytes):
            body = raw_body
        else:
            length = int(handler.headers.get("Content-Length", 0) or 0)
            body = handler.rfile.read(length) if length else b""
    headers = {}
    for key, value in handler.headers.items():
        lowered = key.lower()
        if lowered in HOP_BY_HOP_HEADERS or lowered in {"host", "content-length", "accept-encoding"}:
            continue
        headers[key] = value
    request = urlrequest.Request(upstream_url, data=body, headers=headers, method=upper_method)
    try:
        response = urlrequest.urlopen(request, timeout=30)
        status = response.status
        response_headers = response.headers
        response_body = response.read()
    except urlerror.HTTPError as exc:
        status = exc.code
        response_headers = exc.headers
        response_body = exc.read()
    except Exception as exc:
        return _proxy_error(handler, 502, f"Deployment proxy request failed: {exc}")

    content_type = response_headers.get("Content-Type", "")
    is_html = "text/html" in content_type.lower()
    if is_html and upper_method != "HEAD":
        response_body = _rewrite_deployment_html(response_body, state)

    handler.send_response(status)
    for key, value in response_headers.items():
        lowered = key.lower()
        if lowered in HOP_BY_HOP_HEADERS or lowered in {"content-length", "content-encoding"}:
            continue
        if lowered == "location":
            value = _rewrite_deployment_location(value, state)
        handler.send_header(key, value)
    handler.send_header("Set-Cookie", _deployment_proxy_cookie(state.slug))
    handler.send_header("Content-Length", str(len(response_body)))
    handler.end_headers()
    if upper_method != "HEAD":
        handler.wfile.write(response_body)
    return True


def _resolve_deployment_proxy_state(handler, parsed, slug: str) -> tuple[dict, _DeploymentRuntimeState] | None:
    record = _cloud_terminal_record_for_public_identifier(slug)
    if not record:
        return None
    if record.get("provider") != "local-legacy":
        raise CoreApiError("This deployment provider is not served by the native Core local proxy.", 503, code="DEPLOYMENT_PROXY_PROVIDER_UNSUPPORTED")
    project = _project(str(record.get("projectId") or ""))
    state = _ensure_local_legacy_runtime(project, record)
    if not state:
        raise CoreApiError("Deployment runtime is not configured for this snapshot.", 503, code="DEPLOYMENT_RUNTIME_NOT_CONFIGURED")
    return project, state


def handle_deployment_proxy_request(handler, slug: str, target_path: str, parsed, *, method: str = "GET") -> bool:
    try:
        resolved = _resolve_deployment_proxy_state(handler, parsed, slug)
    except CoreApiError as exc:
        return _proxy_error(handler, exc.status, str(exc))
    if not resolved:
        return _proxy_error(handler, 404, "Deployment not found.")
    _project_payload, state = resolved
    normalized_target = _normalize_proxy_target_path(target_path or "/", parsed)
    request_path_only = normalized_target.split("?", 1)[0]
    if request_path_only in {"", "/"} and state.public_entry_path and state.public_entry_path != state.public_path:
        return _send_deployment_redirect(handler, state.public_entry_path, state.slug)
    return _proxy_to_deployment_runtime(handler, state, target_path or "/", parsed, method=method)


def handle_legacy_play_proxy_deployment_request(handler, parsed, *, method: str = "GET") -> bool:
    """Serve Cloud Terminal-shaped play-proxy deployment URLs from Core.

    Older/stale Cloud Terminal gateways can forward no-referrer deployment API
    calls to Hermes as `/play-proxy/<run>/deploy/<slug>/...`.  Core owns the
    native deployment proxy, so strip the legacy play-proxy prefix and proxy the
    request as `/deploy/<slug>/...` instead of returning Hermes' generic 404.
    """

    path = getattr(parsed, "path", "") or ""
    match = LEGACY_PLAY_PROXY_DEPLOYMENT_RE.match(path)
    if not match:
        return False
    slug = _normalize_deployment_slug(unquote(match.group(1)))
    if not slug:
        return False
    remainder = match.group(2) or ""
    target_path = f"/{remainder}" if remainder else "/"
    return handle_deployment_proxy_request(handler, slug, target_path, parsed, method=method)


def handle_deployment_compatibility_proxy_request(handler, parsed, *, method: str = "GET") -> bool:
    path = getattr(parsed, "path", "") or ""
    if not _is_deployment_compatibility_path(path):
        return False
    slug = deployment_slug_from_request_context(handler, parsed)
    if not slug:
        return False
    return handle_deployment_proxy_request(handler, slug, path, parsed, method=method)


def _request_header(request_headers: Any, name: str) -> str:
    if not request_headers:
        return ""
    getter = getattr(request_headers, "get", None)
    if callable(getter):
        return str(getter(name, "") or getter(name.lower(), "") or "").strip()
    if isinstance(request_headers, dict):
        lowered = {str(key).lower(): value for key, value in request_headers.items()}
        return str(lowered.get(name.lower()) or "").strip()
    return ""


def _cloud_terminal_api_base_url() -> str:
    explicit = (os.getenv("HERMES_WEBUI_CLOUD_TERMINAL_API_BASE_URL") or os.getenv("CLOUD_TERMINAL_API_BASE_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    runtime_api = os.getenv("CLOUD_TERMINAL_RUNTIME_API_BASE_URL", "").strip()
    marker = "/agent/"
    if marker in runtime_api:
        return runtime_api.split(marker, 1)[0].rstrip("/")
    if os.getenv("PROJECTS_DIR", "").strip():
        return "http://127.0.0.1:5001"
    return ""


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _create_cloud_terminal_service_token() -> str:
    """Mint a Cloud Terminal-compatible session token for local Core-to-CT calls."""
    secret = os.getenv("SESSION_SECRET", "").strip()
    if not secret:
        return ""
    now_ms = int(time.time() * 1000)
    payload = {
        "v": 2,
        "iat": now_ms,
        "exp": now_ms + 60 * 60 * 1000,
        "nonce": secrets.token_hex(16),
        "user": {"id": "hermes-core", "label": "Hermes Core"},
    }
    encoded_payload = _base64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("utf-8"), hashlib.sha256).digest()
    return f"{encoded_payload}.{_base64url(signature)}"


def _cloud_terminal_api_is_loopback(base_url: str) -> bool:
    try:
        parsed = urlparse(base_url)
    except ValueError:
        return False
    host = (parsed.hostname or "").strip().lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def _delegate_cloud_terminal_redeploy(project_id: str, deployment: dict, request_headers: Any, body: dict) -> dict | None:
    base_url = _cloud_terminal_api_base_url()
    if not base_url:
        return None

    payload = {
        "provider": deployment.get("provider") or "local-legacy",
        "databaseMode": deployment.get("databaseMode") or (deployment.get("database") or {}).get("mode"),
    }
    provider_config = body.get("providerConfig") if isinstance(body.get("providerConfig"), dict) else None
    if provider_config:
        payload["providerConfig"] = provider_config
    raw = json.dumps({key: value for key, value in payload.items() if value}).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    for name in ("Authorization", "X-Session-Token", "X-CSRF-Token", "X-Hermes-CSRF-Token", "X-Cloud-Terminal-CSRF-Token"):
        value = _request_header(request_headers, name)
        if value:
            headers[name] = value
    if "Authorization" not in headers and "X-Session-Token" not in headers and _cloud_terminal_api_is_loopback(base_url):
        service_token = _create_cloud_terminal_service_token()
        if service_token:
            headers["Authorization"] = f"Bearer {service_token}"
            headers["X-Session-Token"] = service_token
            headers["X-Cloud-Terminal-Internal"] = "hermes-core"
    if "Authorization" not in headers and "X-Session-Token" not in headers:
        return None
    req = urlrequest.Request(f"{base_url}/api/projects/{quote(project_id)}/deployment/update", data=raw, headers=headers, method="POST")
    timeout = max(1.0, float(os.getenv("HERMES_WEBUI_CLOUD_TERMINAL_DEPLOY_TIMEOUT", "900") or 900))
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(text) if text.strip() else {}
            return parsed if isinstance(parsed, dict) else {"response": parsed}
    except urlerror.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError:
            parsed = {}
        message = parsed.get("error") if isinstance(parsed, dict) else ""
        if exc.code in {401, 403, 404} and not headers.get("X-Cloud-Terminal-Internal"):
            return None
        raise CoreApiError(
            f"Cloud Terminal redeploy failed: {message or exc.reason or exc.code}",
            502 if exc.code >= 500 else exc.code,
            code="DEPLOYMENT_REDEPLOY_DELEGATE_FAILED",
            details={"status": exc.code},
        ) from exc
    except (urlerror.URLError, TimeoutError, OSError) as exc:
        raise CoreApiError(
            "Cloud Terminal local deployment runtime is unavailable; Core could not run the provider update pipeline.",
            503,
            code="DEPLOYMENT_REDEPLOY_RUNTIME_UNAVAILABLE",
            details={"message": str(exc)},
        ) from exc


def redeploy_project_deployment(project_id: str, body: dict | None = None, *, request_headers: Any = None) -> dict:
    payload = body if isinstance(body, dict) else {}
    confirm = _text(payload.get("confirm"), limit=64).lower()
    if confirm != "redeploy":
        raise CoreApiError("Deployment redeploy requires confirm=redeploy.", 409, code="DEPLOYMENT_REDEPLOY_CONFIRM_REQUIRED")

    project = _project(project_id)
    with _lock_for(project["id"]):
        deployment = _read_deployment(project)
        if deployment.get("source") != DEPLOYMENT_SOURCE_CLOUD_TERMINAL:
            raise CoreApiError("Only existing Cloud Terminal deployment records can be redeployed with this action.", 409, code="DEPLOYMENT_REDEPLOY_UNSUPPORTED")
        database_mode = _text(deployment.get("databaseMode") or (deployment.get("database") or {}).get("mode"), limit=64)
        requested_database_mode = _text(payload.get("databaseMode"), limit=64)
        if requested_database_mode and database_mode and requested_database_mode != database_mode:
            raise CoreApiError("Redeploy keeps the existing deployment database mode; publish a new deployment to change it.", 409, code="DEPLOYMENT_DATABASE_MODE_CHANGE_REJECTED")

        if deployment.get("provider") == "local-legacy":
            record = _cloud_terminal_record_for_project(project["id"])
            if not record:
                raise CoreApiError("Deployment not found.", 404, code="DEPLOYMENT_NOT_FOUND")
            build = _run_core_deployment_build(project, payload)
            snapshot = _replace_cloud_terminal_snapshot(project, record, retain_backup=True)
            runtime = {"skipped": True, "reason": "not-started"}
            try:
                runtime = _start_local_legacy_runtime(
                    project,
                    record,
                    Path(str(snapshot.get("snapshotPath") or "")),
                    replace_existing=True,
                )
                _discard_cloud_terminal_snapshot_backup(snapshot)
            except CoreApiError as exc:
                restored = _restore_cloud_terminal_snapshot_backup(snapshot)
                timestamp = now_iso()
                try:
                    _patch_cloud_terminal_record(
                        project["id"],
                        {
                            "status": "published" if restored else "failed",
                            "updatedAt": timestamp,
                            "lastError": str(exc),
                        },
                    )
                except CoreApiError:
                    pass
                raise CoreApiError(
                    "Deployment runtime failed after snapshot promotion; Core restored the previous snapshot." if restored else "Deployment runtime failed after snapshot promotion.",
                    exc.status,
                    code=exc.code or "DEPLOYMENT_REDEPLOY_START_FAILED",
                    details={"restoredPreviousSnapshot": restored, "snapshot": snapshot},
                ) from exc
            except Exception as exc:
                restored = _restore_cloud_terminal_snapshot_backup(snapshot)
                timestamp = now_iso()
                try:
                    _patch_cloud_terminal_record(
                        project["id"],
                        {
                            "status": "published" if restored else "failed",
                            "updatedAt": timestamp,
                            "lastError": str(exc),
                        },
                    )
                except CoreApiError:
                    pass
                raise CoreApiError(
                    "Deployment runtime failed after snapshot promotion; Core restored the previous snapshot." if restored else "Deployment runtime failed after snapshot promotion.",
                    500,
                    code="DEPLOYMENT_REDEPLOY_START_FAILED",
                    details={"restoredPreviousSnapshot": restored, "snapshot": snapshot},
                ) from exc
            timestamp = now_iso()
            updated_record = _patch_cloud_terminal_record(
                project["id"],
                {
                    "status": "published",
                    "updatedAt": timestamp,
                    "publishedAt": timestamp,
                    "lastError": None,
                },
            )
            summary = f"Deployment redeploy completed in Hermes Core; database mode {database_mode or 'unchanged'} was preserved."
            details = {
                "provider": deployment.get("provider"),
                "databaseMode": database_mode,
                "delegated": False,
                "coreSnapshot": True,
                "build": build,
                "snapshot": snapshot,
                "runtime": runtime,
                "deploymentId": updated_record.get("id"),
            }
            _append_log(project, {"action": "redeploy", "message": summary, "details": details})
            return {
                **get_project_deployment(project["id"]),
                "operation": operation_record("deployment.redeploy", project["id"], summary=summary, details=details),
            }

        delegated = _delegate_cloud_terminal_redeploy(project["id"], deployment, request_headers, payload)
        if delegated is not None:
            summary = f"Deployment redeploy completed through Core's local Cloud Terminal provider bridge; database mode {database_mode or 'unchanged'} was preserved."
            _append_log(project, {"action": "redeploy", "message": summary, "details": {"provider": deployment.get("provider"), "databaseMode": database_mode, "delegated": True}})
            return {**get_project_deployment(project["id"]), "operation": operation_record("deployment.redeploy", project["id"], summary=summary, details={"delegated": True, "databaseMode": database_mode, "response": delegated})}

        raise CoreApiError("This Cloud Terminal deployment provider requires the local Cloud Terminal provider runtime to redeploy.", 409, code="DEPLOYMENT_REDEPLOY_PROVIDER_REQUIRES_DELEGATE")


def record_project_deployment(project_id: str, body: dict | None = None, *, action: str = "deploy") -> dict:
    payload = body if isinstance(body, dict) else {}
    requested_action = _text(action or payload.get("action") or "deploy", limit=64).lower().replace("_", "-").replace(" ", "-") or "deploy"
    if requested_action in {"redeploy", "update"}:
        raise CoreApiError(
            "Redeploy/update is a first-class deployment operation; use /deployment/redeploy instead of recording a lifecycle action.",
            409,
            code="DEPLOYMENT_REDEPLOY_RESERVED_ACTION",
        )
    project = _project(project_id)
    normalized_action = _text(action or payload.get("action"), limit=64).lower().replace("_", "-").replace(" ", "-") or "deploy"
    provider = _provider_id(payload.get("provider"))
    status_default = "rolled-back" if normalized_action == "rollback" else "stopped" if normalized_action == "stop" else "recorded"
    base_record = _read_deployment(project)
    if base_record.get("source") == DEPLOYMENT_SOURCE_CLOUD_TERMINAL:
        # Manual Hermes records should not copy Cloud Terminal compatibility
        # metadata into the native record file; the external record remains
        # read-only and authoritative until the user explicitly creates a
        # Hermes-owned deployment record.
        base_record = _default_deployment(project)
    record = {
        **base_record,
        "projectId": project["id"],
        "provider": provider,
        "environment": _text(payload.get("environment"), limit=128) or "production",
        "status": _status(payload.get("status"), default=status_default),
        "summary": _redact_text(_text(payload.get("summary"), limit=4000) or f"Deployment {normalized_action} recorded."),
        "action": normalized_action,
        "url": _text(payload.get("url"), limit=2048),
        "updatedAt": now_iso(),
    }
    with _lock_for(project["id"]):
        _write_json(_deployment_path(project), record)
        _append_log(project, {"action": normalized_action, "message": record["summary"], "details": {"provider": provider, "status": record["status"]}})
    return get_project_deployment(project["id"])


def scaffold_project_deployment(project_id: str, body: dict | None = None) -> dict:
    payload = body if isinstance(body, dict) else {}
    project = _project(project_id)
    dockerfile = safe_project_child(project, "Dockerfile")
    overwrite = bool(payload.get("overwrite"))
    created = False
    with _lock_for(project["id"]):
        if dockerfile.exists() and not overwrite:
            summary = "Dockerfile already exists; scaffold left unchanged."
        else:
            package_json = safe_project_child(project, "package.json")
            pyproject = safe_project_child(project, "pyproject.toml")
            requirements = safe_project_child(project, "requirements.txt")
            if package_json.exists():
                content = "FROM node:22-slim\nWORKDIR /app\nCOPY package*.json ./\nRUN npm install --omit=dev || npm install\nCOPY . .\nEXPOSE 3000\nCMD [\"npm\", \"start\"]\n"
            elif pyproject.exists() or requirements.exists():
                content = "FROM python:3.12-slim\nWORKDIR /app\nCOPY requirements.txt ./\nRUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi\nCOPY . .\nEXPOSE 8000\nCMD [\"python\", \"-m\", \"http.server\", \"8000\"]\n"
            else:
                content = "FROM alpine:3.20\nWORKDIR /app\nCOPY . .\nCMD [\"sh\", \"-c\", \"ls -la && echo Configure your deployment command\"]\n"
            dockerfile.write_text(content, encoding="utf-8")
            created = True
            summary = "Dockerfile scaffold created."
        _append_log(project, {"action": "scaffold", "message": summary, "details": {"created": created}})
    return {**get_project_deployment(project["id"]), "operation": operation_record("deployment.scaffold", project["id"], summary=summary, details={"created": created})}


def execute_project_deployment(project_id: str, body: dict | None = None) -> dict:
    payload = body if isinstance(body, dict) else {}
    action = _text(payload.get("action"), limit=64).lower() or "deploy"
    confirm = _text(payload.get("confirm"), limit=64).lower()
    if confirm != action:
        raise CoreApiError("Deployment execution requires confirm to match the requested action.", 409, code="DEPLOYMENT_CONFIRM_REQUIRED")
    project = _project(project_id)
    command = _text(payload.get("command"), limit=4000)
    provider = _provider_id(payload.get("provider"))
    if not command:
        raise CoreApiError("Deployment execution requires an explicit command in this Core API slice.", 400, code="DEPLOYMENT_COMMAND_REQUIRED")
    with _lock_for(project["id"]):
        start = now_iso()
        try:
            completed = subprocess.run(
                command,
                cwd=str(project_root(project)),
                shell=True,
                capture_output=True,
                text=True,
                timeout=_COMMAND_TIMEOUT_SECONDS,
                env={**os.environ, "HERMES_CORE_DEPLOYMENT_ACTION": action, "HERMES_CORE_DEPLOYMENT_PROVIDER": provider},
                check=False,
            )
            stdout = _redact_text((completed.stdout or "")[-8000:])
            stderr = _redact_text((completed.stderr or "")[-8000:])
            ok = completed.returncode == 0
            summary = f"Deployment command {'succeeded' if ok else 'failed'} with exit code {completed.returncode}."
            details = {"exitCode": completed.returncode, "stdout": stdout, "stderr": stderr, "startedAt": start}
        except subprocess.TimeoutExpired as exc:
            ok = False
            summary = "Deployment command timed out."
            details = {"exitCode": None, "stdout": _redact_text(exc.stdout or ""), "stderr": _redact_text(exc.stderr or ""), "startedAt": start, "timedOut": True}
        status = "succeeded" if ok else "failed"
        record_project_deployment(project["id"], {"provider": provider, "status": status, "summary": summary}, action=action)
        log_entry = _append_log(project, {"level": "info" if ok else "error", "action": action, "message": summary, "details": details})
    return {**get_project_deployment(project["id"]), "operation": operation_record("deployment.execute", project["id"], status=status, summary=summary, details={"log": log_entry, **details})}

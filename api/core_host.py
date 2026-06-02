"""Core API host/proxy health descriptors."""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from api.config import REPO_ROOT, STATE_DIR
from api.core_contracts import CORE_API_VERSION, getenv_descriptor, now_iso, redact_payload


def host_health() -> dict:
    return redact_payload({
        "ok": True,
        "coreApiVersion": CORE_API_VERSION,
        "timestamp": now_iso(),
        "process": {"pid": os.getpid(), "python": sys.version.split()[0], "executable": sys.executable},
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "paths": {"repoRoot": str(REPO_ROOT), "stateDir": str(STATE_DIR)},
    })


def proxy_descriptors() -> dict:
    return redact_payload({
        "routes": {
            "opsShell": "/",
            "chatShell": "/index.html",
            "coreApi": "/api/core",
            "opsApi": "/api/ops",
            "playProjectProxy": "/play-project/{projectId}/{path}",
        },
        "environment": [
            getenv_descriptor("HERMES_WEBUI_HOST"),
            getenv_descriptor("HERMES_WEBUI_PORT"),
            getenv_descriptor("HERMES_RUNTIME_BIN"),
        ],
        "repoRootExists": Path(REPO_ROOT).exists(),
        "stateDirExists": Path(STATE_DIR).exists(),
    })

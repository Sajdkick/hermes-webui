"""Regression tests for localStorage quota failures in in-flight tracking.

A full localStorage can throw from the small `hermes-webui-inflight` marker write
and prevent message submission. The marker write should be best-effort and should
clear bulky in-flight state snapshots before retrying.
"""

import json
import re
import subprocess
import textwrap
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
UI_JS = REPO / "static" / "ui.js"


def _inflight_source_block() -> str:
    src = UI_JS.read_text(encoding="utf-8")
    start = src.index("const INFLIGHT_KEY = 'hermes-webui-inflight';")
    end = src.index("function showReconnectBanner", start)
    return src[start:end]


def test_mark_inflight_uses_best_effort_quota_safe_storage_writer():
    src = _inflight_source_block()
    mark = re.search(r"function markInflight\(sid, streamId\) \{(?P<body>.*?)\n\}", src, re.S)
    assert mark, "markInflight() block not found"
    body = mark.group("body")
    assert "_setInflightStorageItem(INFLIGHT_KEY" in body
    assert "localStorage.setItem" not in body
    assert "function _isInflightStorageQuotaError" in src
    assert "function _setInflightStorageItem" in src
    assert "localStorage.removeItem(INFLIGHT_STATE_KEY)" in src


def test_mark_inflight_recovers_when_storage_is_full(tmp_path):
    src = _inflight_source_block()
    script = tmp_path / "probe.js"
    script.write_text(
        textwrap.dedent(
            f"""
            const vm = require('vm');
            const src = {json.dumps(src)};
            const store = new Map([['hermes-webui-inflight-state', 'large snapshot']]);
            const calls = [];
            let firstSet = true;
            const localStorage = {{
              getItem(key) {{ return store.has(key) ? store.get(key) : null; }},
              setItem(key, value) {{
                calls.push(['set', key, value]);
                if (firstSet) {{
                  firstSet = false;
                  const error = new Error("Setting the value of 'hermes-webui-inflight' exceeded the quota.");
                  error.name = 'QuotaExceededError';
                  error.code = 22;
                  throw error;
                }}
                store.set(key, value);
              }},
              removeItem(key) {{
                calls.push(['remove', key]);
                store.delete(key);
              }},
            }};
            const context = {{ localStorage, Date: {{ now: () => 12345 }} }};
            vm.createContext(context);
            vm.runInContext(src + '\\nthis.markInflight = markInflight;', context);
            context.markInflight('sid-1', 'stream-1');
            const marker = JSON.parse(store.get('hermes-webui-inflight'));
            if (marker.sid !== 'sid-1' || marker.streamId !== 'stream-1' || marker.ts !== 12345) {{
              throw new Error('in-flight marker was not persisted after quota retry');
            }}
            if (store.has('hermes-webui-inflight-state')) {{
              throw new Error('bulky in-flight snapshot state should be cleared before retry');
            }}
            if (!calls.some((entry) => entry[0] === 'remove' && entry[1] === 'hermes-webui-inflight-state')) {{
              throw new Error('quota recovery did not remove in-flight snapshot state');
            }}
            """
        ),
        encoding="utf-8",
    )
    subprocess.run(["node", str(script)], check=True, cwd=REPO)

"""Regression coverage for workspace panel editor save safety."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_JS = ROOT / "static" / "workspace.js"
BOOT_JS = (ROOT / "static" / "boot.js").read_text(encoding="utf-8")
PANELS_JS = (ROOT / "static" / "panels.js").read_text(encoding="utf-8")


def _run_workspace_js_scenario(scenario: str) -> None:
    script = f"""
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync({str(WORKSPACE_JS)!r}, 'utf8');

class Element {{
  constructor(id) {{
    this.id = id;
    this.style = {{ display: '' }};
    this.textContent = '';
    this.innerHTML = '';
    this.value = '';
    this.alt = '';
    this.src = '';
    this.title = '';
    this.children = [];
    this.className = '';
    this.dataset = {{}};
    this.classList = {{
      add: () => {{}},
      remove: () => {{}},
      toggle: () => {{}},
      contains: () => false,
    }};
  }}
  appendChild(child) {{ this.children.push(child); return child; }}
  addEventListener() {{}}
  querySelectorAll() {{ return []; }}
  closest() {{ return null; }}
  contains() {{ return false; }}
  setAttribute(name, value) {{ this[name] = value; }}
  removeAttribute(name) {{ delete this[name]; }}
  focus() {{ this.focused = true; }}
}}

function createHarness(options = {{}}) {{
  const elements = new Map();
  const calls = {{ saveBodies: [], toasts: [], statuses: [] }};
  const location = {{ href: 'http://127.0.0.1/', pathname: '/', search: '' }};
  function $(id) {{
    if (!elements.has(id)) elements.set(id, new Element(id));
    return elements.get(id);
  }}
  const document = {{
    baseURI: location.href,
    createElement: (tag) => new Element(tag),
    body: new Element('body'),
    querySelector: () => null,
    querySelectorAll: () => [],
  }};
  const translations = {{
    save: 'Save', edit: 'Edit', saved: 'Saved', save_title: 'Save file',
    edit_title: 'Edit file', save_failed: 'Save failed: ', file_open_failed: 'File open failed',
    image_load_failed: 'Image load failed', downloading: (name) => `Downloading ${{name}}`,
  }};
  const context = {{
    console,
    URL,
    TypeError,
    Promise,
    setTimeout,
    clearTimeout,
    document,
    location,
    window: {{ location, open: () => {{}} }},
    localStorage: {{ getItem: () => null, setItem: () => {{}}, removeItem: () => {{}} }},
    S: {{ session: {{ session_id: 'session-1' }}, currentDir: '.', entries: [] }},
    $,
    renderMd: (value) => `<p>${{value}}</p>`,
    renderKatexBlocks: () => {{}},
    renderBreadcrumb: () => {{}},
    syncWorkspacePanelUI: () => {{}},
    openWorkspacePanel: () => {{}},
    _mediaPlayerHtml: null,
    _applyMediaPlaybackPreferences: () => {{}},
    requestAnimationFrame: (fn) => fn(),
    t: (key, ...args) => {{
      const value = translations[key];
      if (typeof value === 'function') return value(...args);
      return value || key;
    }},
    showToast: (...args) => calls.toasts.push(args),
    setStatus: (...args) => calls.statuses.push(args.join('')),
  }};
  context.fetch = async (url, opts = {{}}) => {{
    const method = (opts.method || 'GET').toUpperCase();
    if (String(url).includes('/api/file/save') || String(url).includes('api/file/save')) {{
      calls.saveBodies.push(opts.body);
      if (options.saveReject) {{
        return {{
          ok: false,
          status: 500,
          statusText: 'Server Error',
          headers: {{ get: () => 'application/json' }},
          text: async () => JSON.stringify({{ error: options.saveReject }}),
        }};
      }}
      if (options.deferSave) {{
        await options.deferSave.promise;
      }}
      return {{ ok: true, status: 200, headers: {{ get: () => 'application/json' }}, json: async () => ({{ ok: true }}) }};
    }}
    if (String(url).includes('/api/file') || String(url).includes('api/file')) {{
      assert.strictEqual(method, 'GET');
      return {{
        ok: true,
        status: 200,
        headers: {{ get: () => 'application/json' }},
        json: async () => ({{ content: options.initialContent || 'original content' }}),
      }};
    }}
    throw new Error('unexpected fetch: ' + url);
  }};
  vm.createContext(context);
  const expose = `\nthis.__workspaceApi = {{ openFile, toggleEditMode, cancelEditMode, setPreviewState(path, mode, content) {{ _previewCurrentPath=path; _previewCurrentMode=mode; _previewRawContent=content; $("previewPathText").textContent=path; showPreview(mode); if(mode==="code") $("previewCode").textContent=content; else $("previewMd").innerHTML=renderMd(content); }} }};`;
  vm.runInContext(source + expose, context);
  return {{ context, elements, calls }};
}}

function deferred() {{
  let resolve;
  const promise = new Promise((r) => {{ resolve = r; }});
  return {{ promise, resolve }};
}}

(async () => {{
{scenario}
}})().catch((err) => {{
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
}});
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_workspace_editor_save_posts_latest_textarea_buffer():
    _run_workspace_js_scenario(
        """
  const { context, elements, calls } = createHarness({ initialContent: 'original content' });
  context.__workspaceApi.setPreviewState('notes.txt', 'code', 'original content');
  await context.__workspaceApi.toggleEditMode();
  elements.get('previewEditArea').value = 'latest long edit';
  await context.__workspaceApi.toggleEditMode();
  assert.strictEqual(JSON.parse(calls.saveBodies[0]).content, 'latest long edit');
  assert.strictEqual(elements.get('previewCode').textContent, 'latest long edit');
  assert.strictEqual(elements.get('previewEditArea').style.display, 'none');
        """
    )


def test_workspace_editor_failed_save_keeps_unsaved_buffer_visible():
    _run_workspace_js_scenario(
        """
  const { context, elements, calls } = createHarness({ saveReject: 'disk full' });
  context.__workspaceApi.setPreviewState('notes.txt', 'code', 'original content');
  await context.__workspaceApi.toggleEditMode();
  elements.get('previewEditArea').value = 'keep my unsaved changes';
  await context.__workspaceApi.toggleEditMode();
  assert.strictEqual(JSON.parse(calls.saveBodies[0]).content, 'keep my unsaved changes');
  assert.strictEqual(elements.get('previewEditArea').value, 'keep my unsaved changes');
  assert.notStrictEqual(elements.get('previewEditArea').style.display, 'none');
  assert.strictEqual(elements.get('previewCode').style.display, 'none');
  assert.ok(calls.statuses.some((line) => line.includes('Save failed: disk full')));
        """
    )


def test_workspace_editor_save_inflight_keeps_newer_edits_dirty():
    _run_workspace_js_scenario(
        """
  const gate = deferred();
  const { context, elements, calls } = createHarness({ deferSave: gate });
  context.__workspaceApi.setPreviewState('notes.txt', 'code', 'original content');
  await context.__workspaceApi.toggleEditMode();
  elements.get('previewEditArea').value = 'snapshot that was saved';
  const savePromise = context.__workspaceApi.toggleEditMode();
  elements.get('previewEditArea').value = 'newer unsaved edit after click';
  gate.resolve();
  await savePromise;
  assert.strictEqual(JSON.parse(calls.saveBodies[0]).content, 'snapshot that was saved');
  assert.strictEqual(elements.get('previewCode').textContent, 'snapshot that was saved');
  assert.strictEqual(elements.get('previewEditArea').value, 'newer unsaved edit after click');
  assert.notStrictEqual(elements.get('previewEditArea').style.display, 'none');
  assert.ok(calls.toasts.some((args) => String(args[0]).includes('newer unsaved edits')));
        """
    )


def test_workspace_clear_preview_refuses_dirty_editor_without_force():
    assert "if(!force&&typeof _previewDirty!=='undefined'&&_previewDirty)" in BOOT_JS
    assert "return false;" in BOOT_JS
    assert "clearPreview({force:true})" in BOOT_JS
    assert "clearPreview({force:true})" in PANELS_JS


def test_workspace_editor_source_keeps_buffer_on_save_error_and_newer_edits():
    src = WORKSPACE_JS.read_text(encoding="utf-8")
    assert "const content=area.value" in src
    assert "area.value===content" in src
    assert "Saved. You have newer unsaved edits." in src
    assert "area.style.display=''" in src
    assert "_previewRawContent=content" in src

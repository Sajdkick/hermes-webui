async function api(path,opts={}){
  // Strip leading slash so URL resolves relative to location.href (supports subpath mounts)
  const rel = path.startsWith('/') ? path.slice(1) : path;
  const url=new URL(rel,document.baseURI||location.href);
  const timeoutMs=Object.prototype.hasOwnProperty.call(opts,'timeoutMs')?opts.timeoutMs:30000;
  const timeoutToast=opts.timeoutToast!==false;
  // Retry up to 2 times on network errors (e.g. stale keep-alive after long idle).
  // Server errors (4xx/5xx) and client-side timeouts are NOT retried.
  let lastErr;
  for(let attempt=0;attempt<3;attempt++){
    let controller=null;
    let timeoutId=null;
    let didTimeout=false;
    let upstreamSignal=null;
    let upstreamAbort=null;
    try{
      const fetchOpts={...opts};
      delete fetchOpts.timeoutMs;
      delete fetchOpts.timeoutToast;

      const useTimeout=Number.isFinite(Number(timeoutMs))&&Number(timeoutMs)>0;
      if(useTimeout&&typeof AbortController!=='undefined'){
        controller=new AbortController();
        upstreamSignal=fetchOpts.signal||null;
        if(upstreamSignal){
          upstreamAbort=()=>controller.abort(upstreamSignal.reason);
          if(upstreamSignal.aborted) upstreamAbort();
          else upstreamSignal.addEventListener('abort',upstreamAbort,{once:true});
        }
        fetchOpts.signal=controller.signal;
      }
      const requestPromise=(async()=>{
        const res=await fetch(url.href,{credentials:'include',headers:{'Content-Type':'application/json'},...fetchOpts});
        if(!res.ok){
          // 401 means the auth session expired. Redirect to login so the user can
          // re-authenticate. This is especially important for iOS PWA (standalone mode)
          // and for subpath mounts like /hermes/, where /login escapes to the site root.
          if(res.status===401){window.location.href='login?next='+encodeURIComponent(window.location.pathname+window.location.search);return;}
          const text=await res.text();
          // Parse JSON error body and surface the human-readable message,
          // rather than showing raw JSON like {"error":"Profile 'x' does not exist."}
          let message=text;
          try{const j=JSON.parse(text);message=j.error||j.message||text;}catch(e){}
          // Attach the raw HTTP context so callers can branch on status (404 stale-session
          // cleanup, 401 redirect, 503 retry, etc.) without re-parsing the message string.
          const err=new Error(message);
          err.status=res.status;
          err.statusText=res.statusText;
          err.body=text;
          throw err;
        }
        const ct=res.headers.get('content-type')||'';
        return ct.includes('application/json')?await res.json():await res.text();
      })();
      return useTimeout?await Promise.race([
        requestPromise,
        new Promise((_,reject)=>{
          timeoutId=setTimeout(()=>{
            didTimeout=true;
            if(controller) controller.abort();
            const err=new Error('Request timed out. Please try again.');
            err.name='TimeoutError';
            err.timeout=true;
            reject(err);
          },Number(timeoutMs));
        })
      ]):await requestPromise;
    }catch(e){
      lastErr=e;
      const isTimeout=didTimeout||(e&&(e.timeout===true||e.name==='TimeoutError'));
      if(isTimeout){
        const err=(e&&e.name==='TimeoutError')?e:new Error('Request timed out. Please try again.');
        err.name='TimeoutError';
        err.timeout=true;
        if(timeoutToast&&typeof showToast==='function') showToast('Request timed out. Please try again.',5000,'error');
        throw err;
      }
      // Only retry on network errors (TypeError from fetch), not on HTTP errors
      // that were already thrown above. Re-throw 401 redirects immediately.
      if(e.message&&/401/.test(e.message)) throw e;
      if(attempt<2 && e instanceof TypeError) continue;
      throw e;
    }finally{
      if(timeoutId) clearTimeout(timeoutId);
      if(upstreamSignal&&upstreamAbort) upstreamSignal.removeEventListener('abort',upstreamAbort);
    }
  }
  throw lastErr;
}

function recordClientSSEError(source, details={}){
  try{
    const payload={
      event:'sse_error',
      source:String(source||'unknown'),
      ready_state:details.ready_state,
      session_id:details.session_id||null,
      stream_id:details.stream_id||null,
      visibility_state:(typeof document!=='undefined'&&document.visibilityState)||'unknown',
      online:(typeof navigator!=='undefined'&&typeof navigator.onLine==='boolean')?navigator.onLine:null,
      url_path:(typeof location!=='undefined'&&location.pathname)||'/',
      reason:details.reason||'EventSource.onerror',
    };
    void api('/api/client-events/log',{method:'POST',body:JSON.stringify(payload),timeoutMs:3000,timeoutToast:false}).catch(()=>{});
  }catch(_){}
}

// Persist/restore expanded directory state per workspace in localStorage
function _wsExpandKey(){
  const ws=S.session&&S.session.workspace;
  return ws?'hermes-webui-expanded:'+ws:null;
}
function _saveExpandedDirs(){
  const key=_wsExpandKey();if(!key)return;
  try{localStorage.setItem(key,JSON.stringify([...(S._expandedDirs||new Set())]));}catch(e){}
}
function _restoreExpandedDirs(){
  const key=_wsExpandKey();
  if(!key){S._expandedDirs=new Set();return;}
  try{
    const raw=localStorage.getItem(key);
    S._expandedDirs=raw?new Set(JSON.parse(raw)):new Set();
  }catch(e){S._expandedDirs=new Set();}
}

let _workspacePanelActiveTab = 'files';
let _renderSessionArtifactsTimer = null;

function _setWorkspacePanelTabDataset(){
  const panel = document.querySelector('.rightpanel');
  if(panel) panel.dataset.activeTab = _workspacePanelActiveTab;
}

function scheduleRenderSessionArtifacts(){
  if(_renderSessionArtifactsTimer) clearTimeout(_renderSessionArtifactsTimer);
  _renderSessionArtifactsTimer = setTimeout(()=>{
    _renderSessionArtifactsTimer = null;
    renderSessionArtifacts();
  }, 100);
}

if(typeof document !== 'undefined'){
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _setWorkspacePanelTabDataset, {once:true});
  else _setWorkspacePanelTabDataset();
}

function switchWorkspacePanelTab(tab){
  _workspacePanelActiveTab = tab === 'artifacts' ? 'artifacts' : 'files';
  _setWorkspacePanelTabDataset();
  const filesTab = $('workspaceFilesTab');
  const artifactsTab = $('workspaceArtifactsTab');
  if(filesTab){
    filesTab.classList.toggle('active', _workspacePanelActiveTab === 'files');
    filesTab.setAttribute('aria-selected', _workspacePanelActiveTab === 'files' ? 'true' : 'false');
  }
  if(artifactsTab){
    artifactsTab.classList.toggle('active', _workspacePanelActiveTab === 'artifacts');
    artifactsTab.setAttribute('aria-selected', _workspacePanelActiveTab === 'artifacts' ? 'true' : 'false');
  }
  const artifacts = $('workspaceArtifacts');
  if(artifacts) artifacts.hidden = _workspacePanelActiveTab !== 'artifacts';
  if(_workspacePanelActiveTab === 'artifacts') renderSessionArtifacts();
}

const ARTIFACT_IGNORE_RE = /(^|\/)(?:\.git|\.hg|\.svn|node_modules|\.venv|venv|__pycache__|dist|build|\.next|\.cache)(?:\/|$)/;
// Canonical Hermes mutators plus MCP filesystem aliases that can create/edit files.
const ARTIFACT_MUTATION_TOOLS = new Set(['write_file','patch','edit_file','create_file','mcp_filesystem_write_file','mcp_filesystem_edit_file']);

function _normalizeArtifactPath(path){
  if(!path) return '';
  path = String(path).trim().replace(/[\`"'<>),.;:]+$/g,'').replace(/^[\`"'(<]+/g,'');
  if(!path || path.length > 240 || path.includes('://')) return '';
  // Canonicalize workspace-relative prefixes so a file-tree open ("foo.md") and a
  // tool arg recorded as "./foo.md" or "~/foo.md" compare equal for mutation
  // tracking; otherwise an agent edit via a ./-prefixed path leaves the open
  // preview stale (#3262 / pre-release regression-gate finding).
  path = path.replace(/^~\//,'').replace(/^(?:\.\/)+/,'');
  if(!path) return '';
  if(ARTIFACT_IGNORE_RE.test(path)) return '';
  if(!/[./]/.test(path)) return '';
  return path;
}

function _artifactCandidatesFromText(text){
  if(!text || typeof text !== 'string') return [];
  const out = [];
  const seen = new Set();
  const add = (path) => {
    path = _normalizeArtifactPath(path);
    if(!path || seen.has(path)) return;
    seen.add(path); out.push({path, kind:'diff'});
  };
  // Fallback text mining is intentionally narrow: only diff/patch fences imply
  // the session changed a file. Prose mentions such as "edited package.json" are
  // too noisy for an Artifacts list that should track write/edit outputs.
  const fenced = /```(?:diff|patch)\s*\n[\s\S]*?```/gi;
  let m;
  while((m = fenced.exec(text))){
    const block = m[0];
    const fm = block.match(/(?:^|\n)(?:\+\+\+|---)\s+(?:[ab]\/)?([^\n\t]+)/);
    if(fm) add(fm[1].trim());
  }
  return out;
}

function _artifactCandidatesFromToolCall(tc){
  if(!tc) return [];
  const name = String(tc.name || '').replace(/^functions\./,'');
  const args = tc.arguments || tc.args || tc.input || {};
  const result = tc.result || tc.output || tc.snippet || '';
  const out = [];
  const add = (path, source=name || 'tool') => {
    path = _normalizeArtifactPath(path);
    if(path) out.push({path, kind:source});
  };
  if(ARTIFACT_MUTATION_TOOLS.has(name) && args && typeof args === 'object'){
    for(const key of ['path','file_path','source','destination']) add(args[key]);
    if(Array.isArray(args.paths)) args.paths.forEach(p=>add(p));
    if(Array.isArray(args.edits)) args.edits.forEach(e=>add(e&&e.path));
  }
  const resultText = typeof result === 'string' ? result : (result ? JSON.stringify(result) : '');
  // Tool results may include unified diffs from patch-style tools; scan those
  // narrowly after structured args so diff headers can still contribute paths.
  for(const a of _artifactCandidatesFromText(resultText)) out.push(a);
  if(!out.length && ARTIFACT_MUTATION_TOOLS.has(name)){
    const argsText = typeof args === 'string' ? args : JSON.stringify(args || {});
    for(const a of _artifactCandidatesFromText(argsText)) out.push(a);
  }
  return out;
}

const _turnMutatedPreviewPaths = new Set();

function resetTurnWorkspaceMutations(){
  _turnMutatedPreviewPaths.clear();
}

function noteWorkspaceMutationsFromToolCall(tc){
  for(const a of _artifactCandidatesFromToolCall(tc)){
    const path=_normalizeArtifactPath(a.path);
    if(path) _turnMutatedPreviewPaths.add(path);
  }
}

function noteWorkspaceMutationsFromToolCalls(toolCalls){
  if(!Array.isArray(toolCalls)) return;
  for(const tc of toolCalls) noteWorkspaceMutationsFromToolCall(tc);
}

function _isOpenPreviewPathMutated(){
  if(!_previewCurrentPath) return false;
  const current=_normalizeArtifactPath(_previewCurrentPath);
  return !!(current&&_turnMutatedPreviewPaths.has(current));
}

async function refreshOpenPreviewIfMutated(){
  if(typeof _previewDirty!=='undefined'&&_previewDirty) return;
  if(!_isOpenPreviewPathMutated()) return;
  if(!_previewCurrentPath||!S.session) return;
  await openFile(_previewCurrentPath, { bustCache: true });
}

function collectSessionArtifacts(){
  const items = [];
  const seen = new Set();
  const push = (path, source) => {
    path = _normalizeArtifactPath(path);
    if(!path || seen.has(path)) return;
    seen.add(path); items.push({path, source});
  };
  // Source 1: session-level tool call summaries (may be empty when messages
  // carry their own tool metadata — see _syncToolCallsForLoadedMessages).
  for(const tc of (S.toolCalls || [])){
    for(const a of _artifactCandidatesFromToolCall(tc)) push(a.path, a.kind || tc.name || 'tool');
  }
  // Source 2 & 3: message-level data — both text-mined diffs and structured
  // tool_calls / tool_use content blocks that survive the S.toolCalls clear.
  for(const msg of (S.messages || [])){
    if(!msg) continue;
    const text = msg.content || msg.text || msg.message || '';
    // Text-mined diff/patch fences (existing path).
    if(typeof text === 'string'){
      for(const a of _artifactCandidatesFromText(text)) push(a.path, a.kind);
    }
    // Structured tool_calls array (OpenAI format: {function:{name,arguments}}).
    if(Array.isArray(msg.tool_calls)){
      for(const tc of msg.tool_calls){
        if(!tc || typeof tc !== 'object') continue;
        const fn = (tc.function && typeof tc.function === 'object') ? tc.function : tc;
        const name = fn.name || tc.name || '';
        let args = fn.arguments || tc.arguments || tc.args || tc.input || {};
        if(typeof args === 'string'){ try{ args = JSON.parse(args); }catch(_){} }
        const fakeTc = {name, args, result: tc.result || tc.output || ''};
        for(const a of _artifactCandidatesFromToolCall(fakeTc)) push(a.path, a.kind || name || 'tool');
      }
    }
    // Structured content array with tool_use blocks (Anthropic format).
    if(Array.isArray(msg.content)){
      for(const block of msg.content){
        if(!block || block.type !== 'tool_use') continue;
        let inp = block.input || {};
        if(typeof inp === 'string'){ try{ inp = JSON.parse(inp); }catch(_){} }
        const fakeTc = {name: block.name || '', args: inp, result: block.result || ''};
        for(const a of _artifactCandidatesFromToolCall(fakeTc)) push(a.path, a.kind || block.name || 'tool');
      }
    }
  }
  return items.slice(0, 50);
}

function renderSessionArtifacts(){
  const root = $('workspaceArtifacts');
  const count = $('workspaceArtifactsCount');
  if(!root) return;
  const items = collectSessionArtifacts();
  if(count) count.textContent = String(items.length);
  if(!S.session){
    root.innerHTML = '<div class="workspace-artifact-empty">Open a conversation to see files changed in this session.</div>';
    return;
  }
  if(!items.length){
    root.innerHTML = '<div class="workspace-artifact-empty">No artifacts detected yet. Files created or edited during this session will appear here.</div>';
    return;
  }
  // Strip workspace prefix for display so long absolute paths don't clutter the list.
  const ws = S.session && S.session.workspace;
  const normWs = ws ? ws.replace(/\/+$/,'') + '/' : '';
  const displayPath = (p) => {
    if(normWs && p.startsWith(normWs)) return p.slice(normWs.length);
    return p;
  };
  root.innerHTML = items.map(item => `<button type="button" class="workspace-artifact-item" data-artifact-path="${esc(item.path)}" onclick="openArtifactPath(this.dataset.artifactPath)"><div class="workspace-artifact-path">${esc(displayPath(item.path))}</div><div class="workspace-artifact-meta">${esc(item.source || 'session')}</div></button>`).join('');
}

async function _workspacePathExists(path){
  if(!S.session||!path) return false;
  const parts=String(path).split('/').filter(Boolean);
  const name=parts.pop();
  if(!name) return false;
  const dir=parts.length?parts.join('/'):'.';
  const data=await api(`/api/list?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(dir)}`);
  return (data.entries||[]).some(entry=>entry&&((entry.path===path)||entry.name===name));
}

async function openArtifactPath(path){
  if(!path) return;
  switchWorkspacePanelTab('files');
  let rel = path.replace(/^~\//,'').replace(/^\.\/+/,'');
  // Strip workspace prefix so /api/list receives a workspace-relative path.
  const ws = S.session && S.session.workspace;
  if(ws){
    const normWs = ws.replace(/\/+$/,'') + '/';
    if(rel.startsWith(normWs)) rel = rel.slice(normWs.length);
    else if(rel === ws.replace(/\/+$/,'')) rel = '.';
  }
  if(!rel) rel = '.';
  try{
    if(!(await _workspacePathExists(rel))){
      setStatus(t('file_open_failed'));
      return;
    }
  }catch(_){
    setStatus(t('file_open_failed'));
    return;
  }
  openFile(rel);
}

async function loadDir(path, opts={}){
  const preservePreview=!!(opts&&opts.preservePreview);
  if(!S.session)return;
  const sessionId=S.session.session_id;
  try{
    if(!path||path==='.'){
      S._dirCache={};
      _restoreExpandedDirs();  // restore per-workspace expanded state on root load
    }
    S.currentDir=path||'.';
    const data=await api(`/api/list?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(path)}`);
    if(!S.session||S.session.session_id!==sessionId)return;
    S.entries=data.entries||[];renderBreadcrumb();renderFileTree();
    // #2673 — refresh Artifacts tab when its source data (the file tree) updates.
    if(typeof renderSessionArtifacts==='function') renderSessionArtifacts();
    // Pre-fetch contents of restored expanded dirs so they render without a second click
    // (parallelized — avoids serial waterfall when multiple dirs are expanded)
    if(!path||path==='.'){
      const expanded=S._expandedDirs||new Set();
      const pending=[...expanded].filter(dirPath=>!S._dirCache[dirPath]);
      if(pending.length){
        const results=await Promise.all(pending.map(dirPath=>
          api(`/api/list?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(dirPath)}`)
            .then(dc=>({dirPath,entries:dc.entries||[]}))
            .catch(()=>({dirPath,entries:[]}))
        ));
        if(!S.session||S.session.session_id!==sessionId)return;
        for(const {dirPath,entries} of results) S._dirCache[dirPath]=entries;
      }
      if(expanded.size>0)renderFileTree();
    }
    if(!preservePreview&&typeof clearPreview==='function'){
      if(typeof _previewDirty!=='undefined'&&_previewDirty){
        showConfirmDialog({title:t('unsaved_confirm'),message:'',confirmLabel:'Discard',danger:true,focusCancel:true}).then(ok=>{if(ok)clearPreview({keepPanelOpen:true,force:true});});
      }else{
        clearPreview({keepPanelOpen:true});
      }
    }else if(preservePreview){
      await refreshOpenPreviewIfMutated();
    }
    // Fetch git info for workspace root (non-blocking)
    if(!path||path==='.') _refreshGitBadge();
  }catch(e){console.warn('loadDir',e);}
}

async function _refreshGitBadge(){
  const badge=$('gitBadge');
  if(!badge||!S.session)return;
  const sessionId=S.session.session_id;
  try{
    const data=await api(`/api/git-info?session_id=${encodeURIComponent(sessionId)}`);
    if(!S.session||S.session.session_id!==sessionId)return;
    if(data.git&&data.git.is_git){
      const g=data.git;
      let text=g.branch||'git';
      if(g.dirty>0) text+=` \u00b7 ${g.dirty}\u2206`; // middot + delta
      if(g.behind>0) text+=` \u2193${g.behind}`;
      if(g.ahead>0) text+=` \u2191${g.ahead}`;
      badge.textContent=text;
      badge.className='git-badge'+(g.dirty>0?' dirty':'');
      badge.style.display='';
    } else {
      badge.style.display='none';
      badge.textContent='';
    }
  }catch(e){
    if(!S.session||S.session.session_id!==sessionId)return;
    badge.style.display='none';
  }
}

function navigateUp(){
  if(!S.session||S.currentDir==='.')return;
  const parts=S.currentDir.split('/');
  parts.pop();
  loadDir(parts.length?parts.join('/'):'.');
}

// File extension sets for preview routing (must match server-side sets)
const IMAGE_EXTS  = new Set(['.png','.jpg','.jpeg','.gif','.svg','.webp','.ico','.bmp']);
const MD_EXTS     = new Set(['.md','.markdown','.mdown']);
const HTML_EXTS   = new Set(['.html','.htm']);
const PDF_EXTS    = new Set(['.pdf']);
const AUDIO_EXTS  = new Set(['.mp3','.wav','.m4a','.aac','.ogg','.oga','.opus','.flac']);
const VIDEO_EXTS  = new Set(['.mp4','.mov','.m4v','.webm','.ogv','.avi','.mkv']);
const MD_PREVIEW_RICH_RENDER_MAX_BYTES = 256 * 1024;
const MD_PREVIEW_RICH_RENDER_MAX_LINES = 5000;
// Binary formats that should download rather than preview
const DOWNLOAD_EXTS = new Set([
  '.docx','.doc','.xlsx','.xls','.pptx','.ppt','.odt','.ods','.odp',
  '.zip','.tar','.gz','.bz2','.7z','.rar',
  '.exe','.dmg','.pkg','.deb','.rpm',
  '.woff','.woff2','.ttf','.otf','.eot',
  '.bin','.dat','.db','.sqlite','.pyc','.class','.so','.dylib','.dll',
]);

function fileExt(p){ const i=p.lastIndexOf('.'); return i>=0?p.slice(i).toLowerCase():''; }

function markdownPreviewByteLength(content){
  const text=String(content||'');
  if(typeof Blob==='function') return new Blob([text]).size;
  if(typeof TextEncoder==='function') return new TextEncoder().encode(text).length;
  return unescape(encodeURIComponent(text)).length;
}

function markdownPreviewLineCount(content){
  const text=String(content||'');
  if(!text) return 1;
  return text.split('\n').length;
}

function shouldRenderMarkdownPreviewAsPlainText(content){
  return markdownPreviewByteLength(content)>MD_PREVIEW_RICH_RENDER_MAX_BYTES
    || markdownPreviewLineCount(content)>MD_PREVIEW_RICH_RENDER_MAX_LINES;
}

function largeMarkdownPlainTextStatus(content){
  const bytes=markdownPreviewByteLength(content);
  const lines=markdownPreviewLineCount(content);
  const sizeLabel=bytes>=1024?`${Math.round(bytes/1024)} KB`:`${bytes} B`;
  return `Large markdown file (${sizeLabel}, ${lines} lines) shown as plain text. Click "Render as markdown anyway" to force rich rendering, or Edit to view raw.`;
}

function setLargeMarkdownForceRenderVisible(visible){
  const btn=$('btnRenderMarkdownAnyway');
  if(btn) btn.style.display=visible?'inline-flex':'none';
}

function renderMarkdownPreviewContent(data){
  showPreview('md');
  $('previewMd').innerHTML=renderMd(data.content);
  requestAnimationFrame(()=>{if(typeof renderKatexBlocks==='function')renderKatexBlocks();});
}

function forceRenderMarkdownPreview(){
  // #3378 review (Codex): don't force-render from a dirty/open editor — the
  // cached raw content would not reflect the unsaved edit. Require a saved,
  // non-dirty state and cached content that belongs to the current file.
  if(_previewDirty || $('previewEditArea').style.display!=='none') return;
  if(!_previewRawContent || _previewRawContentPath!==_previewCurrentPath) return;
  openFile(_previewCurrentPath,{forceRichMarkdown:true});
  setStatus('Markdown rendered for this file.');
}

let _previewCurrentPath = '';  // relative path of currently previewed file
let _previewCurrentMode = '';  // 'code' | 'md' | 'image' | 'html' | 'pdf' | 'audio' | 'video'
let _previewDirty = false;     // true when edits are unsaved
let _previewSaving = false;    // true while a file-save request is in flight
let _previewLoadSeq = 0;       // invalidates stale async openFile() completions
let _previewSaveSeq = 0;       // invalidates stale async save completions
let _previewRawContent = '';   // raw text for md files (and last saved editor text)
let _previewRawContentPath = '';  // path that _previewRawContent belongs to (#3378 force-render cache guard)

function _previewEditArea(){return $('previewEditArea');}

function _previewIsEditing(){
  const area=_previewEditArea();
  return !!(area&&area.style.display!=='none');
}

function _previewText(key,fallback){
  const value=typeof t==='function'?t(key):key;
  return value&&value!==key?value:fallback;
}

async function _confirmDiscardPreviewEdits(messageKey='unsaved_confirm'){
  if(!_previewDirty&&!_previewIsEditing())return true;
  if(typeof showConfirmDialog!=='function')return false;
  return !!(await showConfirmDialog({
    title:_previewText('discard_file_edits_title','Discard file edits?'),
    message:_previewText(messageKey,'You have unsaved changes in the preview. Discard them?'),
    confirmLabel:_previewText('discard','Discard'),
    danger:true,
    focusCancel:true
  }));
}

function _setPreviewSaving(saving){
  _previewSaving=!!saving;
  updateEditBtn();
}

function showPreview(mode){
  // mode: 'code' | 'image' | 'md' | 'html' | 'pdf' | 'audio' | 'video'
  $('previewCode').style.display     = mode==='code'  ? '' : 'none';
  $('previewImgWrap').style.display  = mode==='image' ? '' : 'none';
  const mediaWrap=$('previewMediaWrap'); if(mediaWrap) mediaWrap.style.display = (mode==='audio'||mode==='video') ? '' : 'none';
  const pdfWrap=$('previewPdfWrap'); if(pdfWrap) pdfWrap.style.display = mode==='pdf' ? '' : 'none';
  $('previewMd').style.display       = mode==='md'    ? '' : 'none';
  $('previewHtmlWrap').style.display = mode==='html'  ? '' : 'none';
  $('previewEditArea').style.display = 'none';  // start in read-only
  const badge=$('previewBadge');
  badge.className='preview-badge '+mode;
  badge.textContent = mode==='image'?'image':mode==='audio'?'audio':mode==='video'?'video':mode==='pdf'?'pdf':mode==='md'?'md':mode==='html'?'html':fileExt($('previewPathText').textContent)||'text';
  _previewCurrentMode = mode;
  _previewDirty = false;
  updateEditBtn();
  // Show "Open in browser" button for iframe-backed document previews
  const openBtn=$('btnOpenInBrowser');
  if(openBtn) openBtn.style.display = (mode==='html'||mode==='pdf')?'inline-flex':'none';
  setLargeMarkdownForceRenderVisible(false);
}

function updateEditBtn(){
  const btn=$('btnEditFile');
  if(!btn)return;
  const editable = _previewCurrentMode==='code'||_previewCurrentMode==='md';
  btn.style.display = editable?'':'none';
  btn.disabled = !!_previewSaving;
  const editing = $('previewEditArea').style.display!=='none';
  if(_previewSaving){
    btn.innerHTML = `&#128190; ${_previewText('saving','Saving…')}`;
    btn.title = _previewText('saving','Saving…');
  }else{
    btn.innerHTML = editing ? `&#128190; ${t('save')}` : `&#9998; ${t('edit')}`;
    btn.title = editing ? t('save_title') : t('edit_title');
  }
  btn.style.color = editing ? 'var(--blue)' : '';
  if(_previewDirty&&!_previewSaving) btn.innerHTML = `&#128190; ${_previewText('save','Save')}*`;
}

async function toggleEditMode(){
  const editing = $('previewEditArea').style.display!=='none';
  if(editing){
    // Save
    if(_previewSaving)return;
    if(!S.session||!_previewCurrentPath)return;
    const area=$('previewEditArea');
    const path=_previewCurrentPath;
    const mode=_previewCurrentMode;
    const content=area.value;
    const saveSeq=++_previewSaveSeq;
    _setPreviewSaving(true);
    try{
      await api('/api/file/save',{method:'POST',body:JSON.stringify({
        session_id:S.session.session_id, path, content
      })});
      // Ignore completions for a previous file/save if the user has already
      // navigated elsewhere. This prevents late async responses from replacing
      // or hiding a newer editor buffer.
      if(saveSeq!==_previewSaveSeq||_previewCurrentPath!==path||_previewCurrentMode!==mode)return;
      // Update read-only views AND the cached raw content so a later
      // "Render as markdown anyway" force-render reflects the just-saved text.
      _previewRawContent=content;
      _previewRawContentPath=path;
      if(mode==='code') $('previewCode').textContent=content;
      else renderMarkdownPreviewContent({content});
      if(area.value===content){
        _previewDirty=false;
        area.style.display='none';
        area.onkeydown=null;
        if(mode==='code') $('previewCode').style.display='';
        else $('previewMd').style.display='';
        showToast(t('saved'));
      }else{
        // The user typed while the save request was in flight. Keep the editor
        // open and dirty; only the captured snapshot above was written to disk.
        _previewDirty=true;
        showToast(_previewText('saved_newer_edits_pending','Saved. You have newer unsaved edits.'),5000,'warning');
      }
    }catch(e){
      if(saveSeq===_previewSaveSeq&&_previewCurrentPath===path&&_previewCurrentMode===mode){
        _previewDirty=true;
        area.style.display='';
        if(mode==='code') $('previewCode').style.display='none';
        else $('previewMd').style.display='none';
        setStatus(t('save_failed')+(e&&e.message?e.message:e));
        if(typeof showToast==='function')showToast(t('save_failed')+(e&&e.message?e.message:e),6000,'error');
      }
    }finally{
      if(saveSeq===_previewSaveSeq)_setPreviewSaving(false);
    }
  }else{
    // Enter edit mode: populate textarea with current content
    const currentText = _previewCurrentMode==='code'
      ? $('previewCode').textContent
      : _previewRawContent||'';
    $('previewEditArea').value=currentText;
    $('previewEditArea').style.display='';
    if(_previewCurrentMode==='code') $('previewCode').style.display='none';
    else $('previewMd').style.display='none';
    // Escape cancels the edit without saving
    $('previewEditArea').onkeydown=e=>{
      if(e.key==='Escape'){e.preventDefault();cancelEditMode();}
    };
  }
  updateEditBtn();
}

function cancelEditMode(){
  // Discard changes and return to read-only view
  $('previewEditArea').style.display='none';
  $('previewEditArea').onkeydown=null;
  if(_previewCurrentMode==='code') $('previewCode').style.display='';
  else $('previewMd').style.display='';
  _previewDirty=false;
  updateEditBtn();
}

// Map file extensions to Prism.js language identifiers.
// Prism autoloader fetches missing language components from CDN on demand.
const _PRISM_LANG_MAP={
  js:'javascript',mjs:'javascript',jsx:'jsx',ts:'typescript',tsx:'tsx',
  py:'python',pyw:'python',pyi:'python',
  rb:'ruby',go:'go',rs:'rust',java:'java',kt:'kotlin',kts:'kotlin',
  c:'c',h:'c',cpp:'cpp',cxx:'cpp',hpp:'cpp',cc:'cpp',
  cs:'csharp',swift:'swift',scala:'scala',
  php:'php',pl:'perl',pm:'perl',r:'r',lua:'lua',
  sh:'bash',bash:'bash',zsh:'bash',fish:'bash',
  ps1:'powershell',psm1:'powershell',
  sql:'sql',graphql:'graphql',
  json:'json',yaml:'yaml',yml:'yaml',toml:'toml',xml:'xml',
  html:'markup',htm:'markup',svg:'markup',vue:'markup',
  css:'css',scss:'scss',sass:'sass',less:'less',
  md:'markdown',markdown:'markdown',
  dockerfile:'docker',makefile:'makefile',cmake:'cmake',
  ini:'ini',cfg:'ini',conf:'ini',properties:'properties',
  diff:'diff',patch:'diff',
  txt:'',log:'',csv:'',tsv:'',
};
const _PRISM_BASENAME_LANG_MAP={
  'dockerfile':'docker','makefile':'makefile','gnumakefile':'makefile',
  'cmakelists.txt':'cmake',
  '.gitignore':'ignore','.dockerignore':'ignore',
};
function _prismLanguageForPath(path){
  const base=String(path||'').split(/[\\/]/).pop().toLowerCase();
  if(base.startsWith('dockerfile.')) return 'docker';
  if(_PRISM_BASENAME_LANG_MAP[base]!==undefined) return _PRISM_BASENAME_LANG_MAP[base];
  const ext=fileExt(path).replace(/^\./,'');
  return _PRISM_LANG_MAP[ext]!==undefined?_PRISM_LANG_MAP[ext]:'plaintext';
}

async function openFile(path, opts={}){
  if(!S.session)return;
  if(_previewSaving){showToast(_previewText('save_in_progress','Save in progress…'),4000,'warning');return;}
  if((_previewDirty||_previewIsEditing())&&path===_previewCurrentPath){
    if(_previewIsEditing()){
      const area=_previewEditArea();
      if(area)area.focus();
    }
    return;
  }
  if(_previewDirty||_previewIsEditing()){
    const discard=await _confirmDiscardPreviewEdits('unsaved_confirm');
    if(!discard)return;
    if(typeof cancelEditMode==='function')cancelEditMode();
  }
  const loadSeq=++_previewLoadSeq;
  const ext=fileExt(path);
  const bustCache=!!(opts&&opts.bustCache);
  const forceRichMarkdown=!!(opts&&opts.forceRichMarkdown);
  const cacheBust=bustCache?`&_=${Date.now()}`:'';

  // Binary/download-only formats: trigger browser download, don't preview
  if(DOWNLOAD_EXTS.has(ext)){
    downloadFile(path);
    return;
  }

  $('previewPathText').textContent=path;
  $('previewArea').classList.add('visible');
  $('fileTree').style.display='none';

  _previewCurrentPath = path;
  renderFileBreadcrumb(path);
  if(IMAGE_EXTS.has(ext)){
    // Image: load via raw endpoint, show as <img>
    showPreview('image');
    const url=`api/file/raw?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(path)}${cacheBust}`;
    $('previewImg').alt=path;
    $('previewImg').src=url;
    $('previewImg').onerror=()=>setStatus(t('image_load_failed'));
  } else if(AUDIO_EXTS.has(ext)||VIDEO_EXTS.has(ext)){
    const mode=VIDEO_EXTS.has(ext)?'video':'audio';
    showPreview(mode);
    const url=`api/file/raw?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(path)}&inline=1${cacheBust}`;
    const wrap=$('previewMediaWrap');
    if(wrap){
      wrap.innerHTML=(typeof _mediaPlayerHtml==='function')
        ? _mediaPlayerHtml(mode,url,path.split('/').pop()||path)
        : `<${mode} src="${url.replace(/"/g,'%22')}" controls preload="metadata"></${mode}>`;
      if(typeof _applyMediaPlaybackPreferences==='function') _applyMediaPlaybackPreferences(wrap);
    }
  } else if(PDF_EXTS.has(ext)){
    showPreview('pdf');
    const url=`api/file/raw?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(path)}&inline=1${cacheBust}`;
    const frame=$('previewPdfFrame');
    if(frame){
      frame.src=''; // clear first to avoid stale content
      frame.src=url;
      frame.title=`PDF preview: ${path.split('/').pop()||path}`;
    }
  } else if(MD_EXTS.has(ext)){
    // Markdown: fetch text, render with renderMd, display as formatted HTML
    try{
      // #3378 review (Codex): only reuse cached raw content when it actually
      // belongs to the requested path.
      const data=forceRichMarkdown&&path===_previewRawContentPath&&_previewRawContent
        ? {content:_previewRawContent}
        : await api(`/api/file?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(path)}`);
      if(loadSeq!==_previewLoadSeq||_previewCurrentPath!==path)return;
      _previewRawContent = data.content;
      _previewRawContentPath = path;
      if(!forceRichMarkdown && shouldRenderMarkdownPreviewAsPlainText(data.content)){
        showPreview('code');
        $('previewCode').textContent=data.content;
        setLargeMarkdownForceRenderVisible(true);
        setStatus(largeMarkdownPlainTextStatus(data.content));
        return;
      }
      renderMarkdownPreviewContent(data);
    }catch(e){if(loadSeq===_previewLoadSeq&&_previewCurrentPath===path)setStatus(t('file_open_failed'));}
  } else if(HTML_EXTS.has(ext)){
    // HTML: render in sandboxed iframe via raw endpoint.
    // SECURITY TRADEOFF: We use sandbox="allow-scripts" which lets inline JS run
    // but prevents access to the parent frame (origin isolation). This is a
    // deliberate choice — the user is previewing their own workspace files, so
    // blocking scripts entirely would break most HTML documents. The sandbox
    // still prevents the preview from navigating the parent, accessing cookies,
    // or reading other origin data. If a stricter mode is needed, remove
    // allow-scripts (or add sandbox="") to disable all JS execution.
    showPreview('html');
    const url=`api/file/raw?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(path)}&inline=1${cacheBust}`;
    const iframe=$('previewHtmlIframe');
    if(iframe){
      iframe.src=''; // clear first to avoid stale content
      iframe.src=url;
    }
  } else {
    // Plain code / text -- but fall back to download if server signals binary
    try{
      const data=await api(`/api/file?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(path)}`);
      if(loadSeq!==_previewLoadSeq||_previewCurrentPath!==path)return;
      if(data.binary){
        // Server flagged this as binary content
        downloadFile(path);
        return;
      }
      showPreview('code');
      _previewRawContent = data.content;
      _previewRawContentPath = path;
      // Syntax highlighting with Prism.js (already loaded on the page).
      const codeEl=document.createElement('code');
      codeEl.textContent=data.content;
      const lang=_prismLanguageForPath(path);
      if(lang) codeEl.className='language-'+lang;
      const pre=$('previewCode');
      pre.textContent='';
      // Prism.highlightElement() propagates the language-* class onto the
      // parent <pre>, so strip inherited language-* tokens before each render.
      pre.className=pre.className.replace(/\blanguage-\S+/g,'').replace(/\s+/g,' ').trim();
      pre.appendChild(codeEl);
      // Only invoke Prism when we actually assigned a language.
      if(lang&&typeof Prism!=='undefined'&&typeof Prism.highlightElement==='function'){
        Prism.highlightElement(codeEl);
      }
    }catch(e){
      // If it's a 400/too-large error, offer download instead
      if(loadSeq===_previewLoadSeq&&_previewCurrentPath===path)downloadFile(path);
    }
  }
}

function downloadFile(path){
  if(!S.session)return;
  // Trigger browser download via the raw file endpoint with content-disposition attachment
  const url=`api/file/raw?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(path)}&download=1`;
  const filename=path.split('/').pop();
  const a=document.createElement('a');
  a.href=url;a.download=filename;
  document.body.appendChild(a);a.click();
  setTimeout(()=>document.body.removeChild(a),100);
  showToast(t('downloading',filename),2000);
}


// ── Render breadcrumb for file preview mode ──────────────────────────────────
function renderFileBreadcrumb(filePath) {
  const bar = $('breadcrumbBar');
  if (!bar) return;
  bar.style.display = 'flex';
  const upBtn = $('btnUpDir');
  if (upBtn) upBtn.style.display = '';

  bar.innerHTML = '';
  // Root
  const root = document.createElement('span');
  root.className = 'breadcrumb-seg breadcrumb-link';
  root.textContent = '~';
  root.onclick = () => { loadDir('.'); };
  bar.appendChild(root);

  const parts = filePath.split('/');
  let accumulated = '';
  for (let i = 0; i < parts.length; i++) {
    const sep = document.createElement('span');
    sep.className = 'breadcrumb-sep';
    sep.textContent = '/';
    bar.appendChild(sep);

    accumulated += (accumulated ? '/' : '') + parts[i];
    const seg = document.createElement('span');
    seg.textContent = parts[i];
    if (i < parts.length - 1) {
      seg.className = 'breadcrumb-seg breadcrumb-link';
      const target = accumulated;
      seg.onclick = () => { loadDir(target); };
    } else {
      seg.className = 'breadcrumb-seg breadcrumb-current';
    }
    bar.appendChild(seg);
  }
}

function _workspaceDragHasLocalFiles(e){
  const dt=e&&e.dataTransfer;if(!dt)return false;
  const types=Array.from(dt.types||[]);
  return types.includes('Files')&&!types.includes('application/ws-path');
}

function _workspaceParentPath(path){
  const raw=String(path||'.');
  const idx=raw.lastIndexOf('/');
  return idx>0?raw.slice(0,idx):'.';
}

function _workspaceUploadTargetDir(e){
  const target=e&&e.target;
  const row=target&&target.closest?target.closest('.file-item[data-ws-path]'):null;
  if(row&&row.closest('.rightpanel')){
    const path=row.dataset.wsPath||'.';
    return row.dataset.wsType==='dir'?path:_workspaceParentPath(path);
  }
  const preview=$('previewArea');
  if(preview&&preview.classList.contains('visible')&&target&&preview.contains(target)&&_previewCurrentPath){
    return _workspaceParentPath(_previewCurrentPath);
  }
  return S.currentDir||'.';
}

function _workspaceCleanDroppedRelPath(path,name){
  const raw=String(path||name||'').replace(/\\/g,'/').replace(/^\/+/, '');
  const parts=[];
  for(const part of raw.split('/')){
    const p=part.trim();
    if(!p||p==='.')continue;
    if(p==='..')return '';
    parts.push(p);
  }
  return parts.join('/');
}

function _workspaceJoinDroppedPath(base,rel){
  const b=_workspaceCleanDroppedRelPath(base,'.')||'.';
  const r=_workspaceCleanDroppedRelPath(rel,'');
  return b==='.'?r:(r?b+'/'+r:b);
}

function _workspaceFormatBytes(bytes){
  const n=Number(bytes||0);
  if(n>=1024*1024)return `${(n/1024/1024).toFixed(n>=10*1024*1024?0:1)} MB`;
  if(n>=1024)return `${Math.ceil(n/1024)} KB`;
  return `${n} B`;
}

function _workspaceUploadIndicatorUpdate(title,detail,percent,state='active'){
  const el=$('workspaceUploadIndicator');if(!el)return;
  const titleEl=$('workspaceUploadTitle'),detailEl=$('workspaceUploadDetail'),percentEl=$('workspaceUploadPercent'),fill=$('workspaceUploadFill');
  const pct=Math.max(0,Math.min(100,Math.round(Number(percent)||0)));
  el.hidden=false;el.dataset.state=state;
  if(titleEl)titleEl.textContent=title||t('workspace_upload_indicator_title');
  if(detailEl)detailEl.textContent=detail||'';
  if(percentEl)percentEl.textContent=`${pct}%`;
  if(fill)fill.style.width=`${pct}%`;
}

function _workspaceUploadIndicatorFinish(title,detail,state){
  _workspaceUploadIndicatorUpdate(title,detail,100,state);
  const el=$('workspaceUploadIndicator');if(!el)return;
  const token=Date.now()+Math.random();
  S._workspaceUploadIndicatorToken=token;
  setTimeout(()=>{if(S._workspaceUploadIndicatorToken===token)el.hidden=true;},state==='error'?12000:3500);
}

function _readDroppedFileEntry(entry){
  return new Promise((resolve,reject)=>entry.file(resolve,reject));
}

function _readDroppedDirectoryEntries(reader){
  return new Promise((resolve,reject)=>{
    const all=[];
    const read=()=>reader.readEntries(batch=>{
      if(!batch.length){resolve(all);return;}
      all.push(...batch);read();
    },reject);
    read();
  });
}

async function _collectDroppedWorkspaceEntry(entry,prefix=''){
  if(entry.isFile){
    const file=await _readDroppedFileEntry(entry);
    const relPath=_workspaceCleanDroppedRelPath(prefix+file.name,file.name);
    return relPath?{files:[{file,relPath}],dirs:[]}:{files:[],dirs:[]};
  }
  if(entry.isDirectory){
    const dirPath=_workspaceCleanDroppedRelPath(prefix+entry.name,entry.name);
    const children=await _readDroppedDirectoryEntries(entry.createReader());
    const result={files:[],dirs:dirPath?[dirPath]:[]};
    for(const child of children){
      const nested=await _collectDroppedWorkspaceEntry(child,dirPath?dirPath+'/':prefix);
      result.files.push(...nested.files);result.dirs.push(...nested.dirs);
    }
    return result;
  }
  return {files:[],dirs:[]};
}

async function _workspaceDroppedPayload(dt){
  const items=Array.from((dt&&dt.items)||[]);
  const entries=items.map(item=>item&&item.webkitGetAsEntry?item.webkitGetAsEntry():null).filter(Boolean);
  const result={files:[],dirs:[]};
  if(entries.length){
    for(const entry of entries){
      const nested=await _collectDroppedWorkspaceEntry(entry,'');
      result.files.push(...nested.files);result.dirs.push(...nested.dirs);
    }
  }else{
    for(const file of Array.from((dt&&dt.files)||[])){
      const relPath=_workspaceCleanDroppedRelPath(file.webkitRelativePath||file.name,file.name);
      if(relPath)result.files.push({file,relPath});
    }
  }
  const seenFiles=new Set();
  result.files=result.files.filter(item=>{if(seenFiles.has(item.relPath))return false;seenFiles.add(item.relPath);return true;});
  result.dirs=[...new Set(result.dirs)].sort((a,b)=>a.length-b.length);
  return result;
}

async function _workspaceCreateDroppedDir(targetDir,relDir){
  const path=_workspaceJoinDroppedPath(targetDir,relDir);
  if(!path)return false;
  try{
    await api('/api/file/create-dir',{method:'POST',body:JSON.stringify({session_id:S.session.session_id,path})});
    return true;
  }catch(e){
    if(e&&/already exists/i.test(e.message||''))return false;
    throw e;
  }
}

const WORKSPACE_UPLOAD_CHUNK_BYTES=512*1024;
const WORKSPACE_UPLOAD_RESTART_MESSAGE='Chunked workspace upload endpoint is not available yet. Restart Hermes WebUI and hard refresh the page, then try again.';

function _workspaceChunkUploadsAvailable(){
  const cfg=window.__HERMES_CONFIG__||{};
  return cfg.workspaceChunkUploads===true;
}

function _workspaceUploadRequest(path,formData,fileSize,onProgress,progressOffset=0){
  const url=new URL(path,document.baseURI||location.href).href;
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();
    xhr.open('POST',url,true);
    xhr.withCredentials=true;
    const csrf=window.__HERMES_CONFIG__&&window.__HERMES_CONFIG__.csrfToken;
    if(csrf)xhr.setRequestHeader('X-Hermes-CSRF-Token',csrf);
    xhr.upload.onprogress=(ev)=>{
      if(typeof onProgress==='function'){
        const loaded=progressOffset+(ev.lengthComputable?ev.loaded:0);
        onProgress(Math.min(fileSize||0,loaded),fileSize||ev.total||0);
      }
    };
    xhr.onerror=()=>reject(new Error('Network error while uploading'));
    xhr.ontimeout=()=>reject(new Error('Upload timed out'));
    xhr.onload=()=>{
      const text=xhr.responseText||'';let data=null;
      try{data=text?JSON.parse(text):{};}catch(_e){}
      if(xhr.status===401){window.location.href='login?next='+encodeURIComponent(window.location.pathname+window.location.search);reject(new Error('Authentication required'));return;}
      if(xhr.status<200||xhr.status>=300){
        let message=(data&&(data.error||data.message))||text||`HTTP ${xhr.status}`;
        if(xhr.status===404&&/chunk$/.test(new URL(path,document.baseURI||location.href).pathname)&&/not found/i.test(message))message=WORKSPACE_UPLOAD_RESTART_MESSAGE;
        if(xhr.status===413&&/<html[\s>]/i.test(text))message='HTTP 413 Request Entity Too Large from the reverse proxy';
        reject(new Error(message));return;
      }
      if(data&&data.error){reject(new Error(data.error));return;}
      resolve(data||{});
    };
    xhr.send(formData);
  });
}

async function _workspaceUploadDroppedFileChunked(targetDir,item,onProgress){
  const file=item.file;
  const fileSize=(file&&file.size)||0;
  const chunkCount=Math.max(1,Math.ceil(fileSize/WORKSPACE_UPLOAD_CHUNK_BYTES));
  const uploadId=`${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${chunkCount}`;
  let result={};
  for(let chunkIndex=0;chunkIndex<chunkCount;chunkIndex++){
    const start=chunkIndex*WORKSPACE_UPLOAD_CHUNK_BYTES;
    const end=Math.min(fileSize,start+WORKSPACE_UPLOAD_CHUNK_BYTES);
    const chunk=file.slice(start,end);
    const fd=new FormData();
    fd.append('session_id',S.session.session_id);
    fd.append('dir',targetDir||'.');
    fd.append('rel_path',item.relPath);
    fd.append('upload_id',uploadId);
    fd.append('chunk_index',String(chunkIndex));
    fd.append('chunk_count',String(chunkCount));
    fd.append('chunk_start',String(start));
    fd.append('total_size',String(fileSize));
    fd.append('file',chunk,file.name);
    result=await _workspaceUploadRequest('api/file/upload/chunk',fd,fileSize,onProgress,start);
    if(typeof onProgress==='function')onProgress(end,fileSize);
  }
  return result;
}

async function _workspaceUploadDroppedFile(targetDir,item,onProgress){
  if(item.file&&item.file.size>MAX_UPLOAD_BYTES)throw new Error(_uploadTooLargeMessage(item.file));
  if(item.file&&item.file.size>WORKSPACE_UPLOAD_CHUNK_BYTES){
    if(!_workspaceChunkUploadsAvailable())throw new Error(WORKSPACE_UPLOAD_RESTART_MESSAGE);
    return _workspaceUploadDroppedFileChunked(targetDir,item,onProgress);
  }
  const fd=new FormData();
  fd.append('session_id',S.session.session_id);
  fd.append('dir',targetDir||'.');
  fd.append('rel_path',item.relPath);
  fd.append('file',item.file,item.file.name);
  return _workspaceUploadRequest('api/file/upload',fd,(item.file&&item.file.size)||0,onProgress,0);
}

async function _handleWorkspacePanelFileDrop(e){
  if(!S.session||!S.session.session_id){showToast(t('no_workspace'),4000,'error');return;}
  const targetDir=_workspaceUploadTargetDir(e);
  let payload;
  try{payload=await _workspaceDroppedPayload(e.dataTransfer);}catch(err){showToast(t('upload_failed')+(err.message||err),6000,'error');return;}
  if(!payload.files.length&&!payload.dirs.length){showToast(t('workspace_upload_no_files'),4000,'warning');return;}
  const displayDir=targetDir==='.'?'~':targetDir;
  const uploadTitle=t('workspace_uploading',payload.files.length,displayDir);
  const totalBytes=payload.files.reduce((sum,item)=>sum+((item.file&&item.file.size)||0),0);
  let completedBytes=0;
  setStatus(uploadTitle);
  _workspaceUploadIndicatorUpdate(uploadTitle,t('workspace_upload_preparing',payload.files.length,payload.dirs.length,displayDir),0);
  let createdDirs=0,uploaded=0,failures=0,firstFailure='';
  for(let d=0;d<payload.dirs.length;d++){
    const dir=payload.dirs[d];
    _workspaceUploadIndicatorUpdate(uploadTitle,t('workspace_upload_creating_dirs',d+1,payload.dirs.length),0);
    try{if(await _workspaceCreateDroppedDir(targetDir,dir))createdDirs++;}
    catch(err){failures++;if(!firstFailure)firstFailure=`${dir}: ${err.message||err}`;console.warn('workspace create dropped dir failed',dir,err);}
  }
  for(let i=0;i<payload.files.length;i++){
    const item=payload.files[i];
    const fileSize=(item.file&&item.file.size)||0;
    const updateProgress=(loaded,total)=>{
      const currentTotal=total||fileSize||1;
      const filePct=Math.max(0,Math.min(1,(loaded||0)/currentTotal));
      const overallPct=totalBytes?((completedBytes+(loaded||0))/totalBytes*100):(((i+filePct)/Math.max(1,payload.files.length))*100);
      const detail=t('workspace_upload_progress',i+1,payload.files.length,item.relPath,Math.round(overallPct),`${_workspaceFormatBytes(loaded||0)} / ${_workspaceFormatBytes(currentTotal)}`);
      _workspaceUploadIndicatorUpdate(uploadTitle,detail,Math.min(99,overallPct));
    };
    updateProgress(0,fileSize);
    try{await _workspaceUploadDroppedFile(targetDir,item,updateProgress);uploaded++;}
    catch(err){failures++;if(!firstFailure)firstFailure=`${item.relPath}: ${err.message||err}`;setStatus(`\u274c ${t('upload_failed')}${item.relPath} \u2014 ${err.message||err}`);}
    finally{completedBytes+=fileSize;}
  }
  if((uploaded||createdDirs)&&targetDir&&targetDir!=='.'){
    if(S._expandedDirs){S._expandedDirs.add(targetDir);if(typeof _saveExpandedDirs==='function')_saveExpandedDirs();}
    delete S._dirCache[targetDir];
    try{
      const data=await api(`/api/list?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(targetDir)}`);
      S._dirCache[targetDir]=data.entries||[];
    }catch(_err){}
  }
  if(uploaded||createdDirs)await loadDir(S.currentDir||'.');
  if((uploaded||createdDirs)&&!failures){
    const msg=t('workspace_upload_complete',uploaded,createdDirs,displayDir);
    _workspaceUploadIndicatorFinish(msg,'', 'success');
    showToast(msg,4000,'success');
  }else if(uploaded||createdDirs){
    const msg=t('workspace_upload_partial',uploaded,createdDirs,failures);
    _workspaceUploadIndicatorFinish(msg,firstFailure||'', failures?'error':'success');
    showToast(msg+(firstFailure?`: ${firstFailure}`:''),6000,failures?'warning':'success');
  }else if(failures){
    const msg=t('all_uploads_failed',failures);
    _workspaceUploadIndicatorFinish(msg,firstFailure||'', 'error');
    showToast(`${msg}${firstFailure?`: ${firstFailure}`:''}`,6000,'error');
  }
}

function _setupWorkspacePanelUploadDrop(){
  const panel=document.querySelector('.rightpanel');
  if(!panel||panel.dataset.workspaceUploadDropBound)return;
  panel.dataset.workspaceUploadDropBound='1';
  const clear=()=>{panel.classList.remove('workspace-drop-over');panel.querySelectorAll('.workspace-drop-target').forEach(el=>el.classList.remove('workspace-drop-target'));};
  const mark=e=>{
    if(!_workspaceDragHasLocalFiles(e))return;
    e.preventDefault();e.stopPropagation();
    if(e.dataTransfer)e.dataTransfer.dropEffect='copy';
    panel.classList.add('workspace-drop-over');
    panel.querySelectorAll('.workspace-drop-target').forEach(el=>el.classList.remove('workspace-drop-target'));
    const row=e.target&&e.target.closest?e.target.closest('.file-item[data-ws-path]'):null;
    if(row&&row.closest('.rightpanel')&&row.dataset.wsType==='dir')row.classList.add('workspace-drop-target');
  };
  panel.addEventListener('dragenter',mark);
  panel.addEventListener('dragover',mark);
  panel.addEventListener('dragleave',e=>{if(!panel.contains(e.relatedTarget))clear();});
  panel.addEventListener('drop',async e=>{
    if(!_workspaceDragHasLocalFiles(e))return;
    e.preventDefault();e.stopPropagation();clear();
    await _handleWorkspacePanelFileDrop(e);
  });
}

_setupWorkspacePanelUploadDrop();

function openInBrowser(){
  if(!_previewCurrentPath||!S.session) return;
  const url=`api/file/raw?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(_previewCurrentPath)}&inline=1`;
  window.open(url,'_blank','noopener');
}

// ── Workspace upload ──────────────────────────────────────────────────
function triggerWorkspaceUpload() {
  const input = $('workspaceFileInput');
  if (!input) return;
  input.value = '';
  input.onchange = async () => {
    const files = input.files;
    if (!files || !files.length) return;
    for (const file of files) {
      await uploadToWorkspace(file, S.currentDir || '.');
    }
    if (S.session) loadDir(S.currentDir);
  };
  input.click();
}

async function uploadToWorkspace(file, dir) {
  if (!S.session) return;
  const formData = new FormData();
  formData.append('session_id', S.session.session_id);
  formData.append('path', dir || '.');
  formData.append('file', file, file.name);
  try {
    showToast(t('uploading') || 'Uploading\u2026', 2000);
    const data = await api('/api/workspace/upload', {
      method: 'POST',
      body: formData,
      headers: {},
      timeoutMs: 120000,
    });
    if (data && data.error) {
      showToast(data.error, 5000, 'error');
    } else if (data && (data.extract_error || (Array.isArray(data.files) && data.files.some(function(f){return f && f.extract_error;})))) {
      // Archive was rejected (zip-slip / zip-bomb / corrupt / too-many-members):
      // the file uploaded but extraction failed. Surface it as an error instead
      // of a misleading "Uploaded" success toast.
      var msg = data.extract_error
        || (data.files.find(function(f){return f && f.extract_error;}) || {}).extract_error
        || 'Archive extraction failed';
      showToast(msg, 5000, 'error');
    } else {
      showToast(t('uploaded') || ('Uploaded ' + (data.filename || file.name)), 2000);
    }
  } catch (e) {
    showToast(t('upload_failed') || ('Upload failed: ' + e.message), 5000, 'error');
  }
}

function _isOsFilesDrag(e) {
  return !!(e.dataTransfer && e.dataTransfer.types && e.dataTransfer.types.includes('Files'));
}

function _joinWorkspacePath(base, rel) {
  const b = base || '.';
  const r = (rel || '').replace(/^\/+|\/+$/g, '');
  if (!r) return b;
  return b === '.' ? r : `${b}/${r}`;
}

function _targetDirForRelDir(destDir, relDir) {
  const dirPart = (relDir || '').replace(/\/+$/, '');
  if (!dirPart) return destDir || '.';
  return _joinWorkspacePath(destDir, dirPart);
}

async function _readAllDirectoryEntries(reader) {
  const entries = [];
  while (true) {
    const batch = await new Promise((resolve, reject) => {
      reader.readEntries(resolve, reject);
    });
    if (!batch.length) break;
    entries.push(...batch);
  }
  return entries;
}

async function _collectFilesFromEntry(entry, relPrefix) {
  if (entry.isFile) {
    const file = await new Promise((resolve, reject) => {
      entry.file(resolve, reject);
    });
    return [{ file, relDir: relPrefix || '' }];
  }
  if (!entry.isDirectory) return [];
  const reader = entry.createReader();
  const children = await _readAllDirectoryEntries(reader);
  const dirPrefix = `${relPrefix || ''}${entry.name}/`;
  let out = [];
  for (const child of children) {
    out = out.concat(await _collectFilesFromEntry(child, dirPrefix));
  }
  return out;
}

async function _collectOsDropUploads(dataTransfer) {
  const out = [];
  const items = dataTransfer.items ? [...dataTransfer.items] : [];
  if (items.length && typeof items[0].webkitGetAsEntry === 'function') {
    for (const item of items) {
      if (item.kind !== 'file') continue;
      const entry = item.webkitGetAsEntry();
      if (!entry) continue;
      out.push(...await _collectFilesFromEntry(entry, ''));
    }
    if (out.length) return out;
  }
  for (const file of dataTransfer.files) {
    out.push({ file, relDir: '' });
  }
  return out;
}

async function uploadOsDropToWorkspace(dataTransfer, destDir) {
  if (!S.session || !dataTransfer) return;
  const uploads = await _collectOsDropUploads(dataTransfer);
  for (const { file, relDir } of uploads) {
    await uploadToWorkspace(file, _targetDirForRelDir(destDir, relDir));
  }
  if (S.session) await loadDir(S.currentDir);
}

function _clearWorkspaceOsUploadDragOver() {
  document.querySelectorAll('.file-item.drag-over-upload,.breadcrumb-seg.drag-over-upload').forEach((el) => {
    el.classList.remove('drag-over-upload');
  });
}

function _bindWorkspaceOsUploadDropTarget(el, destDir) {
  // Use addEventListener (not on-property assignment) so these OS-upload
  // handlers COMPOSE with the workspace tree-MOVE handlers bound by
  // _bindWorkspaceMoveDropTarget() on the same element. A property assignment
  // for the drop handler here would overwrite the move handler, and a
  // workspace-file drag would fall through to the document drop (inserting
  // @path into the composer) instead of moving the file. Each handler gates on
  // its own drag type (_isOsFilesDrag vs _isWorkspaceTreeMoveDrag), so only the
  // matching one acts.
  el.addEventListener('dragenter', (e) => {
    if (!_isOsFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    el.classList.add('drag-over-upload');
  });
  el.addEventListener('dragover', (e) => {
    if (!_isOsFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'copy';
    el.classList.add('drag-over-upload');
  });
  el.addEventListener('dragleave', (e) => {
    if (el.contains(e.relatedTarget)) return;
    el.classList.remove('drag-over-upload');
  });
  el.addEventListener('drop', async (e) => {
    if (!_isOsFilesDrag(e)) return;
    e.preventDefault();
    e.stopPropagation();
    el.classList.remove('drag-over-upload');
    await uploadOsDropToWorkspace(e.dataTransfer, destDir);
  });
}

// Drag-and-drop files onto workspace file tree
if (typeof document !== 'undefined') {
  const _wsUploadInit = () => {
    const tree = $('fileTree');
    if (!tree) return;
    tree.addEventListener('dragenter', (e) => {
      if (e.dataTransfer && e.dataTransfer.types && e.dataTransfer.types.includes('Files')) {
        e.preventDefault();
        e.stopPropagation();
      }
    });
    tree.addEventListener('dragover', (e) => {
      if (e.dataTransfer && e.dataTransfer.types && e.dataTransfer.types.includes('Files')) {
        e.preventDefault();
        e.stopPropagation();
        if (e.target.closest('.file-item[data-ws-type="dir"],.breadcrumb-seg')) return;
        e.dataTransfer.dropEffect = 'copy';
        tree.classList.add('drag-over-upload');
      }
    });
    tree.addEventListener('dragleave', (e) => {
      if (tree.contains(e.relatedTarget)) return;
      tree.classList.remove('drag-over-upload');
    });
    tree.addEventListener('drop', async (e) => {
      tree.classList.remove('drag-over-upload');
      if (!e.dataTransfer || !e.dataTransfer.types || !e.dataTransfer.types.includes('Files')) return;
      if (e.target.closest('.file-item[data-ws-type="dir"],.breadcrumb-seg')) return;
      e.preventDefault();
      e.stopPropagation();
      await uploadOsDropToWorkspace(e.dataTransfer, S.currentDir || '.');
    });
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _wsUploadInit, {once: true});
  } else {
    _wsUploadInit();
  }
}

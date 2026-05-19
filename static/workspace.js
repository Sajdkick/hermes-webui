async function api(path,opts={}){
  // Strip leading slash so URL resolves relative to location.href (supports subpath mounts)
  const rel = path.startsWith('/') ? path.slice(1) : path;
  const url=new URL(rel,document.baseURI||location.href);
  // Retry up to 2 times on network errors (e.g. stale keep-alive after long idle).
  // Server errors (4xx/5xx) are NOT retried — only connection failures.
  let lastErr;
  for(let attempt=0;attempt<3;attempt++){
    try{
      const res=await fetch(url.href,{credentials:'include',headers:{'Content-Type':'application/json'},...opts});
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
      return ct.includes('application/json')?res.json():res.text();
    }catch(e){
      lastErr=e;
      // Only retry on network errors (TypeError from fetch), not on HTTP errors
      // that were already thrown above. Re-throw 401 redirects immediately.
      if(e.message&&/401/.test(e.message)) throw e;
      if(attempt<2 && e instanceof TypeError) continue;
      throw e;
    }
  }
  throw lastErr;
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

async function loadDir(path){
  if(!S.session)return;
  try{
    if(!path||path==='.'){
      S._dirCache={};
      _restoreExpandedDirs();  // restore per-workspace expanded state on root load
    }
    S.currentDir=path||'.';
    const data=await api(`/api/list?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(path)}`);
    S.entries=data.entries||[];renderBreadcrumb();renderFileTree();
    // Pre-fetch contents of restored expanded dirs so they render without a second click
    // (parallelized — avoids serial waterfall when multiple dirs are expanded)
    if(!path||path==='.'){
      const expanded=S._expandedDirs||new Set();
      const pending=[...expanded].filter(dirPath=>!S._dirCache[dirPath]);
      if(pending.length){
        const results=await Promise.all(pending.map(dirPath=>
          api(`/api/list?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(dirPath)}`)
            .then(dc=>({dirPath,entries:dc.entries||[]}))
            .catch(()=>({dirPath,entries:[]}))
        ));
        for(const {dirPath,entries} of results) S._dirCache[dirPath]=entries;
      }
      if(expanded.size>0)renderFileTree();
    }
    if(typeof clearPreview==='function'){
      if(typeof _previewDirty!=='undefined'&&_previewDirty){
        showConfirmDialog({title:t('unsaved_confirm'),message:'',confirmLabel:'Discard',danger:true,focusCancel:true}).then(ok=>{if(ok)clearPreview({keepPanelOpen:true});});
      }else{
        clearPreview({keepPanelOpen:true});
      }
    }
    // Fetch git info for workspace root (non-blocking)
    if(!path||path==='.') _refreshGitBadge();
  }catch(e){console.warn('loadDir',e);}
}

async function _refreshGitBadge(){
  const badge=$('gitBadge');
  if(!badge||!S.session)return;
  try{
    const data=await api(`/api/git-info?session_id=${encodeURIComponent(S.session.session_id)}`);
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
  }catch(e){badge.style.display='none';}
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
// Binary formats that should download rather than preview
const DOWNLOAD_EXTS = new Set([
  '.docx','.doc','.xlsx','.xls','.pptx','.ppt','.odt','.ods','.odp',
  '.zip','.tar','.gz','.bz2','.7z','.rar',
  '.exe','.dmg','.pkg','.deb','.rpm',
  '.woff','.woff2','.ttf','.otf','.eot',
  '.bin','.dat','.db','.sqlite','.pyc','.class','.so','.dylib','.dll',
]);

function fileExt(p){ const i=p.lastIndexOf('.'); return i>=0?p.slice(i).toLowerCase():''; }

let _previewCurrentPath = '';  // relative path of currently previewed file
let _previewCurrentMode = '';  // 'code' | 'md' | 'image' | 'html' | 'pdf' | 'audio' | 'video'
let _previewDirty = false;     // true when edits are unsaved

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
}

function updateEditBtn(){
  const btn=$('btnEditFile');
  if(!btn)return;
  const editable = _previewCurrentMode==='code'||_previewCurrentMode==='md';
  btn.style.display = editable?'':'none';
  const editing = $('previewEditArea').style.display!=='none';
  btn.innerHTML = editing ? `&#128190; ${t('save')}` : `&#9998; ${t('edit')}`;
  btn.title = editing ? t('save_title') : t('edit_title');
  btn.style.color = editing ? 'var(--blue)' : '';
  if(_previewDirty) btn.innerHTML = '&#128190; Save*';
}

async function toggleEditMode(){
  const editing = $('previewEditArea').style.display!=='none';
  if(editing){
    // Save
    if(!S.session||!_previewCurrentPath)return;
    const content=$('previewEditArea').value;
    try{
      await api('/api/file/save',{method:'POST',body:JSON.stringify({
        session_id:S.session.session_id, path:_previewCurrentPath, content
      })});
      _previewDirty=false;
      // Update read-only views
      if(_previewCurrentMode==='code') $('previewCode').textContent=content;
      else { $('previewMd').innerHTML=renderMd(content); requestAnimationFrame(()=>{if(typeof renderKatexBlocks==='function')renderKatexBlocks();}); }
      $('previewEditArea').style.display='none';
      if(_previewCurrentMode==='code') $('previewCode').style.display='';
      else $('previewMd').style.display='';
      showToast(t('saved'));
    }catch(e){setStatus(t('save_failed')+e.message);}
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

let _previewRawContent = '';  // raw text for md files (to populate editor)

function cancelEditMode(){
  // Discard changes and return to read-only view
  $('previewEditArea').style.display='none';
  $('previewEditArea').onkeydown=null;
  if(_previewCurrentMode==='code') $('previewCode').style.display='';
  else $('previewMd').style.display='';
  _previewDirty=false;
  updateEditBtn();
}

async function openFile(path){
  if(!S.session)return;
  const ext=fileExt(path);

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
    const url=`api/file/raw?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(path)}`;
    $('previewImg').alt=path;
    $('previewImg').src=url;
    $('previewImg').onerror=()=>setStatus(t('image_load_failed'));
  } else if(AUDIO_EXTS.has(ext)||VIDEO_EXTS.has(ext)){
    const mode=VIDEO_EXTS.has(ext)?'video':'audio';
    showPreview(mode);
    const url=`api/file/raw?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(path)}&inline=1`;
    const wrap=$('previewMediaWrap');
    if(wrap){
      wrap.innerHTML=(typeof _mediaPlayerHtml==='function')
        ? _mediaPlayerHtml(mode,url,path.split('/').pop()||path)
        : `<${mode} src="${url.replace(/"/g,'%22')}" controls preload="metadata"></${mode}>`;
      if(typeof _applyMediaPlaybackPreferences==='function') _applyMediaPlaybackPreferences(wrap);
    }
  } else if(PDF_EXTS.has(ext)){
    showPreview('pdf');
    const url=`api/file/raw?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(path)}&inline=1`;
    const frame=$('previewPdfFrame');
    if(frame){
      frame.src=''; // clear first to avoid stale content
      frame.src=url;
      frame.title=`PDF preview: ${path.split('/').pop()||path}`;
    }
  } else if(MD_EXTS.has(ext)){
    // Markdown: fetch text, render with renderMd, display as formatted HTML
    try{
      const data=await api(`/api/file?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(path)}`);
      showPreview('md');
      _previewRawContent = data.content;
      $('previewMd').innerHTML=renderMd(data.content);
      requestAnimationFrame(()=>{if(typeof renderKatexBlocks==='function')renderKatexBlocks();});
    }catch(e){setStatus(t('file_open_failed'));}
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
    const url=`api/file/raw?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(path)}&inline=1`;
    const iframe=$('previewHtmlIframe');
    if(iframe){
      iframe.src=''; // clear first to avoid stale content
      iframe.src=url;
    }
  } else {
    // Plain code / text -- but fall back to download if server signals binary
    try{
      const data=await api(`/api/file?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(path)}`);
      if(data.binary){
        // Server flagged this as binary content
        downloadFile(path);
        return;
      }
      showPreview('code');
      $('previewCode').textContent=data.content;
    }catch(e){
      // If it's a 400/too-large error, offer download instead
      downloadFile(path);
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

async function _workspaceUploadDroppedFile(targetDir,item,onProgress){
  if(item.file&&item.file.size>MAX_UPLOAD_BYTES)throw new Error(_uploadTooLargeMessage(item.file));
  const fd=new FormData();
  fd.append('session_id',S.session.session_id);
  fd.append('dir',targetDir||'.');
  fd.append('rel_path',item.relPath);
  fd.append('file',item.file,item.file.name);
  const url=new URL('api/file/upload',document.baseURI||location.href).href;
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();
    xhr.open('POST',url,true);
    xhr.withCredentials=true;
    const csrf=window.__HERMES_CONFIG__&&window.__HERMES_CONFIG__.csrfToken;
    if(csrf)xhr.setRequestHeader('X-Hermes-CSRF-Token',csrf);
    xhr.upload.onprogress=(ev)=>{
      if(typeof onProgress==='function')onProgress(ev.lengthComputable?ev.loaded:0,ev.lengthComputable?ev.total:((item.file&&item.file.size)||0));
    };
    xhr.onerror=()=>reject(new Error('Network error while uploading'));
    xhr.ontimeout=()=>reject(new Error('Upload timed out'));
    xhr.onload=()=>{
      const text=xhr.responseText||'';let data=null;
      try{data=text?JSON.parse(text):{};}catch(_e){}
      if(xhr.status===401){window.location.href='login?next='+encodeURIComponent(window.location.pathname+window.location.search);reject(new Error('Authentication required'));return;}
      if(xhr.status<200||xhr.status>=300){reject(new Error((data&&(data.error||data.message))||text||`HTTP ${xhr.status}`));return;}
      if(data&&data.error){reject(new Error(data.error));return;}
      resolve(data||{});
    };
    xhr.send(fd);
  });
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
  const url=`api/file/raw?session_id=${encodeURIComponent(S.session.session_id)}&path=${encodeURIComponent(_previewCurrentPath)}`;
  window.open(url,'_blank');
}

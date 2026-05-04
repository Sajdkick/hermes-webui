(function(){
  const S = {
    session: null,
    messages: [],
    entries: [],
    busy: false,
    pendingFiles: [],
    toolCalls: [],
    activeStreamId: null,
    currentDir: '.',
    activeProfile: 'default',
  };

  function $(id){
    return document.getElementById(id);
  }

  function esc(value){
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function appUrl(path){
    const raw = String(path || '').trim();
    if(!raw){
      return document.baseURI || window.location.href;
    }
    if(/^[a-z]+:/i.test(raw) || raw.startsWith('//')){
      return raw;
    }
    const normalized = raw.startsWith('/') ? raw.slice(1) : raw;
    return new URL(normalized, document.baseURI || window.location.href).href;
  }

  async function api(path, options){
    const opts = options && typeof options === 'object' ? {...options} : {};
    const headers = new Headers(opts.headers || {});
    if(opts.body != null && typeof opts.body === 'string' && !headers.has('Content-Type')){
      headers.set('Content-Type', 'application/json');
    }
    const response = await fetch(appUrl(path), {
      credentials: 'include',
      ...opts,
      headers,
    });
    const contentType = String(response.headers.get('Content-Type') || '').toLowerCase();
    let payload = null;
    if(contentType.includes('application/json')){
      payload = await response.json().catch(() => ({}));
    }else{
      const text = await response.text().catch(() => '');
      payload = text ? {error: text} : {};
    }
    if(!response.ok || (payload && payload.error)){
      throw new Error((payload && payload.error) || ('Request failed (' + response.status + ')'));
    }
    return payload;
  }

  let toastTimer = null;
  function showToast(message, ms){
    const toast = $('toast');
    if(!toast)return;
    toast.textContent = String(message || '').trim();
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.remove('show');
    }, Number.isFinite(Number(ms)) ? Number(ms) : 2600);
  }

  const appPromptDialog = typeof window.showPromptDialog === 'function'
    ? window.showPromptDialog.bind(window)
    : (window.parent && window.parent !== window && typeof window.parent.showPromptDialog === 'function'
      ? window.parent.showPromptDialog.bind(window.parent)
      : null);
  const appConfirmDialog = typeof window.showConfirmDialog === 'function'
    ? window.showConfirmDialog.bind(window)
    : (window.parent && window.parent !== window && typeof window.parent.showConfirmDialog === 'function'
      ? window.parent.showConfirmDialog.bind(window.parent)
      : null);

  async function showPromptDialog(options){
    if(appPromptDialog){
      return appPromptDialog(options);
    }
    showToast('Input dialog is unavailable', 3200);
    return null;
  }

  async function showConfirmDialog(options){
    if(appConfirmDialog){
      return appConfirmDialog(options);
    }
    showToast('Confirmation dialog is unavailable', 3200);
    return false;
  }

  function sessionUrlForSid(sid){
    const encoded = encodeURIComponent(String(sid || '').trim());
    const next = new URL('session/' + encoded, document.baseURI || window.location.href);
    return next.pathname + next.search + next.hash;
  }

  function projectUrl(projectId, suffix){
    const id = encodeURIComponent(String(projectId || '').trim());
    return '/api/ops/projects/' + id + String(suffix || '');
  }

  function renderTray(){
    const tray = $('pendingFileTray');
    if(!tray)return;
    if(!S.pendingFiles.length){
      tray.hidden = true;
      tray.textContent = '';
      return;
    }
    tray.hidden = false;
    tray.textContent = S.pendingFiles.map((file) => String(file && file.name || 'upload.bin')).join(', ');
  }

  function addFiles(files){
    Array.from(files || []).forEach((file) => {
      if(!file || !file.name)return;
      if(!S.pendingFiles.find((entry) => entry && entry.name === file.name)){
        S.pendingFiles.push(file);
      }
    });
    renderTray();
  }

  function clearPersistedSessionId(){
    try{
      window.localStorage.removeItem('hermes-webui-session');
    }catch(_error){}
  }

  function clearSessionReadableOutput(){}
  function renderSessionList(){ return Promise.resolve(); }
  function syncTopbar(){}

  async function loadSession(sessionLike){
    const sid = window.AgentBridge && window.AgentBridge.sessions && typeof window.AgentBridge.sessions.resolveId === 'function'
      ? await window.AgentBridge.sessions.resolveId(sessionLike)
      : String((sessionLike && sessionLike.session_id) || sessionLike || '').trim();
    if(!sid){
      throw new Error('Session id is required.');
    }
    const data = await api('/api/session?session_id=' + encodeURIComponent(sid) + '&messages=0&resolve_model=0');
    S.session = data && data.session ? data.session : {session_id: sid};
    S.messages = Array.isArray(data && data.messages) ? data.messages : [];
    S.activeStreamId = String(S.session && S.session.active_stream_id || '').trim() || null;
    try{
      window.localStorage.setItem('hermes-webui-session', S.session.session_id);
    }catch(_error){}
    return S.session;
  }

  async function uploadPendingFiles(){
    if(!S.pendingFiles.length || !S.session || !S.session.session_id){
      return [];
    }
    const uploads = [];
    for(const file of S.pendingFiles){
      const fd = new FormData();
      fd.append('session_id', S.session.session_id);
      fd.append('file', file, file && file.name ? file.name : 'upload.bin');
      const response = await fetch(appUrl('api/upload'), {
        method: 'POST',
        credentials: 'include',
        body: fd,
      });
      const payload = await response.json().catch(async() => {
        const text = await response.text().catch(() => '');
        return text ? {error: text} : {};
      });
      if(!response.ok || (payload && payload.error)){
        throw new Error((payload && payload.error) || ('Upload failed (' + response.status + ')'));
      }
      uploads.push({
        name: payload && payload.filename ? payload.filename : (file && file.name) || 'upload.bin',
        path: payload && payload.path ? payload.path : ((file && file.name) || 'upload.bin'),
      });
    }
    S.pendingFiles = [];
    renderTray();
    return uploads;
  }

  function autoResize(){
    const msg = $('msg');
    if(!msg)return;
    msg.style.height = 'auto';
    msg.style.height = Math.min(msg.scrollHeight || 0, 280) + 'px';
  }

  async function send(){
    if(!S.session || !S.session.session_id){
      throw new Error('No active session loaded.');
    }
    const msg = $('msg');
    const text = String(msg && msg.value || '').trim();
    const uploaded = await uploadPendingFiles();
    const attached = uploaded.map((item) => item && (item.path || item.name)).filter(Boolean);
    const message = attached.length
      ? (text ? text + '\n\n' : '') + '[Attached files: ' + attached.join(', ') + ']'
      : text;
    if(!message){
      window.location.assign(sessionUrlForSid(S.session.session_id));
      return null;
    }
    const payload = {
      session_id: S.session.session_id,
      message,
      model: String(S.session && S.session.model || '').trim(),
      model_provider: S.session && S.session.model_provider || null,
      profile: String(S.activeProfile || 'default').trim() || 'default',
    };
    const data = await window.AgentBridge.streams.start(payload);
    S.activeStreamId = data && data.stream_id ? data.stream_id : S.activeStreamId;
    if(msg){
      msg.value = '';
      autoResize();
    }
    window.location.assign(sessionUrlForSid(S.session.session_id));
    return data;
  }

  function closeOpsDashboard(){
    if(S.session && S.session.session_id){
      window.location.assign(sessionUrlForSid(S.session.session_id));
      return;
    }
    window.location.assign(appUrl('./'));
  }

  window.S = S;
  window.$ = $;
  window.esc = esc;
  window.api = api;
  window.projectUrl = projectUrl;
  window.showToast = showToast;
  window.showPromptDialog = showPromptDialog;
  window.showConfirmDialog = showConfirmDialog;
  window.syncTopbar = syncTopbar;
  window.clearSessionReadableOutput = clearSessionReadableOutput;
  window.clearPersistedSessionId = clearPersistedSessionId;
  window.renderSessionList = renderSessionList;
  window.loadSession = loadSession;
  window.addFiles = addFiles;
  window.renderTray = renderTray;
  window.autoResize = autoResize;
  window.send = send;
  window.closeOpsDashboard = closeOpsDashboard;
  window.__OPS_LEGACY_STANDALONE__ = true;
  window.__opsLegacyAppUrl = appUrl;
  window.__opsLegacySessionUrlForSid = sessionUrlForSid;
  window._botName = 'Hermes';

  document.addEventListener('DOMContentLoaded', () => {
    autoResize();
    if(typeof window.openOpsDashboard === 'function'){
      window.openOpsDashboard();
    }
  });
})();

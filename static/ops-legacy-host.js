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

  const LOCAL_DIALOG = {
    resolve: null,
    kind: 'confirm',
    lastFocus: null,
  };

  function ensureToast(){
    let toast = $('toast');
    if(toast)return toast;
    toast = document.createElement('div');
    toast.className = 'toast';
    toast.id = 'toast';
    document.body.appendChild(toast);
    return toast;
  }

  let toastTimer = null;
  function showToast(message, ms){
    const toast = ensureToast();
    if(!toast)return;
    toast.textContent = String(message || '').trim();
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.remove('show');
    }, Number.isFinite(Number(ms)) ? Number(ms) : 2600);
  }

  function ensureLocalDialog(){
    let overlay = $('appDialogOverlay');
    if(overlay)return overlay;
    overlay = document.createElement('div');
    overlay.className = 'app-dialog-overlay';
    overlay.id = 'appDialogOverlay';
    overlay.style.display = 'none';
    overlay.setAttribute('aria-hidden', 'true');
    overlay.innerHTML = [
      '<div class="app-dialog" id="appDialog" role="dialog" aria-modal="true" aria-labelledby="appDialogTitle" aria-describedby="appDialogDesc">',
      '<div class="app-dialog-header">',
      '<div class="app-dialog-title" id="appDialogTitle">Confirm action</div>',
      '<button class="app-dialog-close" id="appDialogClose" type="button" aria-label="Close dialog">',
      '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
      '</button>',
      '</div>',
      '<div class="app-dialog-desc" id="appDialogDesc"></div>',
      '<input class="app-dialog-input" id="appDialogInput" type="text" style="display:none">',
      '<div class="app-dialog-actions">',
      '<button class="app-dialog-btn" id="appDialogCancel" type="button">Cancel</button>',
      '<button class="app-dialog-btn confirm" id="appDialogConfirm" type="button">Confirm</button>',
      '</div>',
      '</div>',
    ].join('');
    document.body.appendChild(overlay);

    function finishDialog(result, restoreFocus){
      const nextRestore = restoreFocus !== false;
      const resolver = LOCAL_DIALOG.resolve;
      const lastFocus = LOCAL_DIALOG.lastFocus;
      LOCAL_DIALOG.resolve = null;
      LOCAL_DIALOG.lastFocus = null;
      LOCAL_DIALOG.kind = 'confirm';
      overlay.style.display = 'none';
      overlay.setAttribute('aria-hidden', 'true');
      if(nextRestore && lastFocus && typeof lastFocus.focus === 'function'){
        try{lastFocus.focus({preventScroll:true});}catch(_error){}
      }
      if(typeof resolver === 'function')resolver(result);
    }

    function focusableNodes(){
      const selectors = [
        '#appDialogClose',
        '#appDialogCancel',
        '#appDialogConfirm',
        '#appDialogInput',
      ];
      return selectors
        .map(selector=>overlay.querySelector(selector))
        .filter(node=>node && node.offsetParent !== null && !node.disabled);
    }

    overlay.addEventListener('click', event => {
      if(event.target === overlay){
        finishDialog(LOCAL_DIALOG.kind === 'prompt' ? null : false);
      }
    });
    overlay.querySelector('#appDialogClose').addEventListener('click', () => {
      finishDialog(LOCAL_DIALOG.kind === 'prompt' ? null : false);
    });
    overlay.querySelector('#appDialogCancel').addEventListener('click', () => {
      finishDialog(LOCAL_DIALOG.kind === 'prompt' ? null : false);
    });
    overlay.querySelector('#appDialogConfirm').addEventListener('click', () => {
      const input = $('appDialogInput');
      if(LOCAL_DIALOG.kind === 'prompt'){
        finishDialog(input ? input.value : '');
        return;
      }
      finishDialog(true);
    });
    overlay.addEventListener('keydown', event => {
      if(event.key === 'Escape'){
        event.preventDefault();
        finishDialog(LOCAL_DIALOG.kind === 'prompt' ? null : false);
        return;
      }
      if(event.key === 'Enter'){
        const input = $('appDialogInput');
        if(LOCAL_DIALOG.kind === 'prompt' && document.activeElement === input){
          event.preventDefault();
          finishDialog(input ? input.value : '');
          return;
        }
      }
      if(event.key === 'Tab'){
        const nodes = focusableNodes();
        if(!nodes.length)return;
        const currentIndex = nodes.indexOf(document.activeElement);
        const nextIndex = event.shiftKey
          ? (currentIndex <= 0 ? nodes.length - 1 : currentIndex - 1)
          : (currentIndex === -1 || currentIndex === nodes.length - 1 ? 0 : currentIndex + 1);
        event.preventDefault();
        nodes[nextIndex].focus();
      }
    });
    return overlay;
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
    const opts = options && typeof options === 'object' ? options : {};
    const overlay = ensureLocalDialog();
    const dialog = $('appDialog');
    const title = $('appDialogTitle');
    const desc = $('appDialogDesc');
    const input = $('appDialogInput');
    const cancelBtn = $('appDialogCancel');
    const confirmBtn = $('appDialogConfirm');
    if(LOCAL_DIALOG.resolve)LOCAL_DIALOG.resolve(null);
    LOCAL_DIALOG.kind = 'prompt';
    LOCAL_DIALOG.lastFocus = document.activeElement;
    if(title)title.textContent = opts.title || 'Enter value';
    if(desc)desc.textContent = opts.message || '';
    if(input){
      input.type = opts.inputType || 'text';
      input.style.display = '';
      input.value = opts.value || '';
      input.placeholder = opts.placeholder || '';
      input.autocomplete = 'off';
      input.spellcheck = false;
    }
    if(cancelBtn)cancelBtn.textContent = opts.cancelLabel || 'Cancel';
    if(confirmBtn){
      confirmBtn.textContent = opts.confirmLabel || 'Confirm';
      confirmBtn.classList.remove('danger');
    }
    if(dialog)dialog.setAttribute('role', 'dialog');
    overlay.style.display = 'flex';
    overlay.setAttribute('aria-hidden', 'false');
    return new Promise(resolve => {
      LOCAL_DIALOG.resolve = resolve;
      setTimeout(() => {
        if(input && input.style.display !== 'none'){
          input.focus();
          input.select();
        }else if(confirmBtn){
          confirmBtn.focus();
        }
      }, 0);
    });
  }

  async function showConfirmDialog(options){
    if(appConfirmDialog){
      return appConfirmDialog(options);
    }
    const opts = options && typeof options === 'object' ? options : {};
    const overlay = ensureLocalDialog();
    const dialog = $('appDialog');
    const title = $('appDialogTitle');
    const desc = $('appDialogDesc');
    const input = $('appDialogInput');
    const cancelBtn = $('appDialogCancel');
    const confirmBtn = $('appDialogConfirm');
    if(LOCAL_DIALOG.resolve)LOCAL_DIALOG.resolve(false);
    LOCAL_DIALOG.kind = 'confirm';
    LOCAL_DIALOG.lastFocus = document.activeElement;
    if(title)title.textContent = opts.title || 'Confirm action';
    if(desc)desc.textContent = opts.message || '';
    if(input){
      input.style.display = 'none';
      input.value = '';
    }
    if(cancelBtn)cancelBtn.textContent = opts.cancelLabel || 'Cancel';
    if(confirmBtn){
      confirmBtn.textContent = opts.confirmLabel || 'Confirm';
      confirmBtn.classList.toggle('danger', !!opts.danger);
    }
    if(dialog)dialog.setAttribute('role', opts.danger ? 'alertdialog' : 'dialog');
    overlay.style.display = 'flex';
    overlay.setAttribute('aria-hidden', 'false');
    return new Promise(resolve => {
      LOCAL_DIALOG.resolve = resolve;
      setTimeout(() => ((opts.focusCancel ? cancelBtn : confirmBtn) || confirmBtn || cancelBtn).focus(), 0);
    });
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

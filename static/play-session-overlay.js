(function(){
  const script=document.currentScript;
  if(!script||script.dataset.hermesPlayOverlay==='disabled')return;

  function text(value){
    return String(value||'').trim();
  }

  function appUrl(path){
    const raw=text(path)||'/';
    try{
      return new URL(raw, window.location.origin).href;
    }catch(_error){
      return raw;
    }
  }

  const sessionId=text(script.dataset.hermesPlaySessionId);
  if(!sessionId)return;
  const projectId=text(script.dataset.hermesPlayProjectId);
  const taskId=text(script.dataset.hermesPlayTaskId);
  const runId=text(script.dataset.hermesPlayRunId);
  const sessionUrl=appUrl(script.dataset.hermesPlaySessionUrl||('/session/'+encodeURIComponent(sessionId)));
  const storageKey='hermes-play-session-overlay:'+[projectId,runId,taskId,sessionId].filter(Boolean).join(':');

  function escapeHtml(value){
    return text(value).replace(/[&<>"']/g,(char)=>({
      '&':'&amp;',
      '<':'&lt;',
      '>':'&gt;',
      '"':'&quot;',
      "'":'&#39;'
    }[char]));
  }

  function readCollapsed(){
    try{
      return window.sessionStorage.getItem(storageKey)==='collapsed';
    }catch(_error){
      return false;
    }
  }

  function writeCollapsed(collapsed){
    try{
      window.sessionStorage.setItem(storageKey,collapsed?'collapsed':'open');
    }catch(_error){}
  }

  function installStyles(){
    if(document.getElementById('hermes-play-session-overlay-styles'))return;
    const style=document.createElement('style');
    style.id='hermes-play-session-overlay-styles';
    style.textContent=`
      .hermes-play-session-overlay{position:fixed;right:18px;bottom:18px;z-index:2147483647;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#f8fafc;}
      .hermes-play-session-overlay *{box-sizing:border-box;}
      .hermes-play-session-toggle{display:none;align-items:center;gap:8px;min-width:52px;min-height:52px;border:1px solid rgba(148,163,184,.45);border-radius:999px;padding:0 16px;background:linear-gradient(135deg,#4f46e5,#0f172a);box-shadow:0 20px 45px rgba(15,23,42,.34);color:#fff;font:700 14px/1.2 inherit;cursor:pointer;}
      .hermes-play-session-toggle:hover{transform:translateY(-1px);box-shadow:0 24px 52px rgba(15,23,42,.42);}
      .hermes-play-session-toggle-icon{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:rgba(255,255,255,.18);font-weight:800;}
      .hermes-play-session-panel{display:flex;flex-direction:column;width:min(440px,calc(100vw - 32px));height:min(680px,calc(100vh - 96px));min-height:320px;overflow:hidden;border:1px solid rgba(148,163,184,.36);border-radius:18px;background:rgba(15,23,42,.96);box-shadow:0 24px 72px rgba(15,23,42,.48);backdrop-filter:blur(16px);}
      .hermes-play-session-header{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 12px 10px 14px;border-bottom:1px solid rgba(148,163,184,.22);background:linear-gradient(135deg,rgba(30,41,59,.98),rgba(15,23,42,.96));}
      .hermes-play-session-title{display:flex;flex-direction:column;gap:2px;min-width:0;}
      .hermes-play-session-title strong{font-size:14px;letter-spacing:.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
      .hermes-play-session-title span{font-size:12px;color:#cbd5e1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
      .hermes-play-session-actions{display:flex;align-items:center;gap:8px;}
      .hermes-play-session-action{border:1px solid rgba(148,163,184,.35);border-radius:999px;background:rgba(15,23,42,.72);color:#f8fafc;padding:7px 10px;font:700 12px/1 inherit;text-decoration:none;cursor:pointer;}
      .hermes-play-session-action:hover{background:rgba(79,70,229,.42);}
      .hermes-play-session-frame{flex:1;width:100%;border:0;background:#fff;}
      .hermes-play-session-overlay.is-collapsed .hermes-play-session-panel{display:none;}
      .hermes-play-session-overlay.is-collapsed .hermes-play-session-toggle{display:inline-flex;}
      @media (max-width:760px){
        .hermes-play-session-overlay{right:12px;bottom:12px;}
        .hermes-play-session-panel{width:calc(100vw - 24px);height:min(620px,calc(100vh - 72px));}
        .hermes-play-session-action.open-label{display:none;}
      }
    `;
    document.head.appendChild(style);
  }

  function createOverlay(){
    if(document.getElementById('hermes-play-session-overlay'))return;
    installStyles();
    const root=document.createElement('aside');
    root.id='hermes-play-session-overlay';
    root.className='hermes-play-session-overlay';
    root.setAttribute('aria-label','Hermes session access for this Play inspection');
    if(readCollapsed())root.classList.add('is-collapsed');

    const summary=[
      projectId?`Project ${projectId}`:'Play inspection',
      taskId?`Task ${taskId}`:'',
    ].filter(Boolean).join(' • ');

    root.innerHTML=`
      <button class="hermes-play-session-toggle" type="button" aria-expanded="false" title="Open Hermes session">
        <span class="hermes-play-session-toggle-icon">H</span><span>Session</span>
      </button>
      <section class="hermes-play-session-panel" aria-label="Hermes session panel">
        <div class="hermes-play-session-header">
          <div class="hermes-play-session-title">
            <strong>Hermes session</strong>
            <span>${escapeHtml(summary||sessionId)}</span>
          </div>
          <div class="hermes-play-session-actions">
            <a class="hermes-play-session-action open-label" href="${escapeHtml(sessionUrl)}" target="_blank" rel="noopener noreferrer">Open full</a>
            <button class="hermes-play-session-action" type="button" data-hermes-play-collapse>Hide</button>
          </div>
        </div>
        <iframe class="hermes-play-session-frame" src="${escapeHtml(sessionUrl)}" title="Hermes session ${escapeHtml(sessionId)}" loading="lazy"></iframe>
      </section>
    `;
    const toggle=root.querySelector('.hermes-play-session-toggle');
    const collapse=root.querySelector('[data-hermes-play-collapse]');
    function setCollapsed(collapsed){
      root.classList.toggle('is-collapsed',collapsed);
      if(toggle)toggle.setAttribute('aria-expanded',collapsed?'false':'true');
      writeCollapsed(collapsed);
    }
    if(toggle)toggle.addEventListener('click',()=>setCollapsed(false));
    if(collapse)collapse.addEventListener('click',()=>setCollapsed(true));
    document.body.appendChild(root);
    setCollapsed(root.classList.contains('is-collapsed'));
  }

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',createOverlay,{once:true});
  }else{
    createOverlay();
  }
})();

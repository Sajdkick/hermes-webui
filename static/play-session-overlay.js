(function(){
  function overlayScript(){
    const current=document.currentScript;
    if(current&&current.dataset&&current.dataset.hermesPlayOverlay)return current;
    try{
      const scripts=Array.from(document.querySelectorAll('script[data-hermes-play-overlay]'));
      return scripts[scripts.length-1]||current||null;
    }catch(_error){
      return current||null;
    }
  }

  const script=overlayScript();
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

  function sessionInspectUrl(path){
    const href=appUrl(path);
    try{
      const url=new URL(href, window.location.origin);
      url.searchParams.set('opsSessionInspect','1');
      url.searchParams.set('opsSessionInspectSource','play');
      return url.href;
    }catch(_error){
      const separator=href.indexOf('?')>=0?'&':'?';
      return href+separator+'opsSessionInspect=1&opsSessionInspectSource=play';
    }
  }

  const sessionId=text(script.dataset.hermesPlaySessionId);
  if(!sessionId)return;
  const projectId=text(script.dataset.hermesPlayProjectId);
  const taskId=text(script.dataset.hermesPlayTaskId);
  const runId=text(script.dataset.hermesPlayRunId);
  const fullSessionUrl=appUrl(script.dataset.hermesPlaySessionUrl||('/session/'+encodeURIComponent(sessionId)));
  const sessionUrl=sessionInspectUrl(fullSessionUrl);
  const overlayKey=[projectId,runId,taskId,sessionId].filter(Boolean).join(':')||sessionId;

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
    return false;
  }

  function writeCollapsed(_collapsed){
    // Collapse state is intentionally page-local. Persisting it in sessionStorage
    // made desktop notification opens look like the popup never appeared after a
    // previous hide, while fresh mobile browsers still showed it.
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
      .hermes-play-session-frame-wrap{position:relative;display:flex;flex:1;min-height:0;background:#fff;}
      .hermes-play-session-frame{flex:1;width:100%;border:0;background:#fff;}
      .hermes-play-session-frame.is-pending{visibility:hidden;}
      .hermes-play-session-frame[hidden]{display:none;}
      .hermes-play-session-frame-status{position:absolute;inset:auto 12px 12px 12px;display:flex;align-items:center;justify-content:space-between;gap:10px;border:1px solid rgba(148,163,184,.28);border-radius:12px;background:rgba(15,23,42,.92);color:#f8fafc;padding:10px 12px;font-size:12px;box-shadow:0 14px 30px rgba(15,23,42,.28);}
      .hermes-play-session-frame-status[hidden]{display:none;}
      .hermes-play-session-frame-status a{color:#bfdbfe;font-weight:800;text-decoration:none;white-space:nowrap;}
      .hermes-play-session-frame-status a:hover{text-decoration:underline;}
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
    const existing=document.getElementById('hermes-play-session-overlay');
    if(existing){
      if(existing.dataset&&existing.dataset.hermesPlayOverlayKey===overlayKey){
        existing.classList.remove('is-collapsed');
        const frame=existing.querySelector('.hermes-play-session-frame');
        if(frame&&frame.getAttribute('src')!==sessionUrl)frame.setAttribute('src',sessionUrl);
        const fullLink=existing.querySelector('[data-hermes-play-full-session]');
        if(fullLink)fullLink.setAttribute('href',fullSessionUrl);
        return;
      }
      existing.remove();
    }
    installStyles();
    const root=document.createElement('aside');
    root.id='hermes-play-session-overlay';
    root.className='hermes-play-session-overlay';
    root.dataset.hermesPlayOverlayKey=overlayKey;
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
            <a class="hermes-play-session-action open-label" data-hermes-play-full-session href="${escapeHtml(fullSessionUrl)}" target="_blank" rel="noopener noreferrer">Open full</a>
            <button class="hermes-play-session-action" type="button" data-hermes-play-collapse>Hide</button>
          </div>
        </div>
        <div class="hermes-play-session-frame-wrap">
          <iframe class="hermes-play-session-frame" src="${escapeHtml(sessionUrl)}" title="Hermes session ${escapeHtml(sessionId)}" loading="lazy"></iframe>
          <div class="hermes-play-session-frame-status" data-hermes-play-session-loading>Loading linked Hermes session…</div>
          <div class="hermes-play-session-frame-status" data-hermes-play-session-frame-fallback hidden>
            <span>Session preview did not finish loading here.</span>
            <a href="${escapeHtml(fullSessionUrl)}" target="_blank" rel="noopener noreferrer">Open full session</a>
          </div>
        </div>
      </section>
    `;
    const toggle=root.querySelector('.hermes-play-session-toggle');
    const collapse=root.querySelector('[data-hermes-play-collapse]');
    const frame=root.querySelector('.hermes-play-session-frame');
    const loading=root.querySelector('[data-hermes-play-session-loading]');
    const fallback=root.querySelector('[data-hermes-play-session-frame-fallback]');
    let frameLoadSeen=false;
    let fallbackTimer=null;
    let verifyTimer=null;
    function hideLoading(){
      if(loading)loading.hidden=true;
    }
    function clearFrameTimers(){
      if(fallbackTimer){
        clearTimeout(fallbackTimer);
        fallbackTimer=null;
      }
      if(verifyTimer){
        clearTimeout(verifyTimer);
        verifyTimer=null;
      }
    }
    function frameInspectReady(){
      try{
        const doc=frame&&(frame.contentDocument||(frame.contentWindow&&frame.contentWindow.document));
        if(!doc||!doc.body)return false;
        return !!(doc.body.classList&&doc.body.classList.contains('ops-session-inspect'));
      }catch(_error){
        return false;
      }
    }
    function markFrameReady(){
      clearFrameTimers();
      hideLoading();
      if(frame){
        frame.hidden=false;
        frame.classList.remove('is-pending');
      }
      if(fallback)fallback.hidden=true;
    }
    function showFallback(){
      clearFrameTimers();
      hideLoading();
      if(frame)frame.hidden=true;
      if(fallback)fallback.hidden=false;
    }
    function scheduleFrameVerification(){
      const started=Date.now();
      const check=()=>{
        if(frameInspectReady()){
          markFrameReady();
          return;
        }
        if(Date.now()-started>=6000){
          showFallback();
          return;
        }
        verifyTimer=setTimeout(check,250);
      };
      check();
    }
    if(frame){
      frame.classList.add('is-pending');
      frame.addEventListener('load',()=>{
        frameLoadSeen=true;
        if(fallbackTimer){
          clearTimeout(fallbackTimer);
          fallbackTimer=null;
        }
        scheduleFrameVerification();
      });
      frame.addEventListener('error',showFallback);
      fallbackTimer=setTimeout(()=>{
        if(!frameLoadSeen)showFallback();
      },8000);
    }
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

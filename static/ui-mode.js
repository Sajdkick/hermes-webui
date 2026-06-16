(function(){
  'use strict';

  var root=document.querySelector('[data-ui-mode-root]');
  if(!root)return;

  var params=new URLSearchParams(window.location.search||'');
  var state={
    projectId:String(params.get('projectId')||params.get('project_id')||params.get('id')||'').trim(),
    sessionId:String(params.get('sessionId')||params.get('session_id')||'').trim(),
    project:null,
    status:null,
    pollTimer:null,
    logsVisible:false,
    autoStartDone:false,
    chatCreating:false,
    sessionVerified:false,
    cacheToken:String(Date.now()),
    controlsCollapsed:false,
    chatCollapsed:false,
    inspectEnabled:false,
    pageContext:null,
    selectedElement:null,
    selectedElements:[],
    layoutStorageKey:'hermes-ui-mode-layout-v1',
  };

  var els={
    projectLabel:root.querySelector('[data-project-label]'),
    statusDot:root.querySelector('[data-status-dot]'),
    statusText:root.querySelector('[data-status-text]'),
    previewFrame:root.querySelector('[data-preview-frame]'),
    previewEmpty:root.querySelector('[data-preview-empty]'),
    previewMeta:root.querySelector('[data-preview-meta]'),
    currentPage:root.querySelector('[data-current-page]'),
    selectedElement:root.querySelector('[data-selected-element]'),
    contextSyncStatus:root.querySelector('[data-context-sync-status]'),
    chatFrame:root.querySelector('[data-chat-frame]'),
    chatPane:root.querySelector('[data-chat-pane]'),
    chatEmpty:root.querySelector('[data-chat-empty]'),
    chatMeta:root.querySelector('[data-chat-meta]'),
    logs:root.querySelector('[data-logs]'),
    errorBanner:root.querySelector('[data-error-banner]'),
  };

  function appUrl(path){
    var text=String(path||'').trim();
    if(!text)return new URL('.',document.baseURI||window.location.href).href;
    if(/^[a-z][a-z0-9+.-]*:/i.test(text))return text;
    return new URL(text.replace(/^\/+/,''),document.baseURI||window.location.href).href;
  }

  function csrfHeaders(){
    var token=String(window.__HERMES_CSRF_TOKEN__||'').trim();
    return token?{'X-Hermes-CSRF-Token':token}:{};
  }

  function setError(message){
    var text=String(message||'').trim();
    if(!els.errorBanner)return;
    els.errorBanner.textContent=text;
    els.errorBanner.classList.toggle('show',!!text);
  }

  function setBusy(action,busy){
    root.querySelectorAll('[data-action="'+action+'"]').forEach(function(button){
      button.disabled=!!busy;
    });
  }

  function loadLayoutState(){
    try{
      var raw=window.localStorage&&window.localStorage.getItem(state.layoutStorageKey);
      if(!raw)return;
      var saved=JSON.parse(raw);
      state.controlsCollapsed=!!(saved&&saved.controlsCollapsed);
      state.chatCollapsed=!!(saved&&saved.chatCollapsed);
    }catch(_){/* best effort */}
  }

  function saveLayoutState(){
    try{
      if(!window.localStorage)return;
      window.localStorage.setItem(state.layoutStorageKey,JSON.stringify({
        controlsCollapsed:!!state.controlsCollapsed,
        chatCollapsed:!!state.chatCollapsed
      }));
    }catch(_){/* best effort */}
  }

  function updateToggleButtons(){
    root.querySelectorAll('[data-chrome-toggle]').forEach(function(button){
      button.textContent=state.controlsCollapsed?'Show controls':'Hide controls';
      button.setAttribute('aria-expanded',String(!state.controlsCollapsed));
    });
    root.querySelectorAll('[data-chat-toggle]').forEach(function(button){
      button.textContent=state.chatCollapsed?'Show chat':'Hide chat';
      button.setAttribute('aria-expanded',String(!state.chatCollapsed));
    });
    root.querySelectorAll('[data-action="show-controls"]').forEach(function(button){
      button.setAttribute('aria-hidden',String(!state.controlsCollapsed));
    });
    root.querySelectorAll('[data-action="show-chat"]').forEach(function(button){
      button.setAttribute('aria-hidden',String(!state.chatCollapsed));
    });
    if(els.chatPane)els.chatPane.setAttribute('aria-hidden',String(!!state.chatCollapsed));
    updateInspectButtons();
  }

  function applyLayoutState(persist){
    root.classList.toggle('chrome-collapsed',!!state.controlsCollapsed);
    root.classList.toggle('chat-collapsed',!!state.chatCollapsed);
    updateToggleButtons();
    if(persist!==false)saveLayoutState();
  }

  function setControlsCollapsed(collapsed){
    state.controlsCollapsed=!!collapsed;
    applyLayoutState();
  }

  function setChatCollapsed(collapsed){
    state.chatCollapsed=!!collapsed;
    applyLayoutState();
  }

  function focusPreview(){
    state.controlsCollapsed=true;
    state.chatCollapsed=true;
    applyLayoutState();
  }

  function trimText(value,max){
    var text=String(value||'').replace(/\s+/g,' ').trim();
    var limit=max||160;
    return text.length>limit?text.slice(0,limit-1)+'…':text;
  }

  function previewAppPathFromUrl(raw){
    var text=String(raw||'').trim();
    if(!text)return '';
    try{
      var url=new URL(text,window.location.href);
      var path=url.pathname||'/';
      var prefix='/ui-project/'+encodeURIComponent(state.projectId||'');
      var decodedPrefix='/ui-project/'+String(state.projectId||'');
      if(path===prefix||path.indexOf(prefix+'/')===0)path=path.slice(prefix.length)||'/';
      else if(path===decodedPrefix||path.indexOf(decodedPrefix+'/')===0)path=path.slice(decodedPrefix.length)||'/';
      return path+url.search+url.hash;
    }catch(_){return text;}
  }

  function normalizePageContext(payload){
    var data=payload||{};
    var url=String(data.url||'').trim();
    var appPath=String(data.appPath||'').trim()||previewAppPathFromUrl(url||data.path||'');
    return {
      title:trimText(data.title||'',120),
      url:url,
      path:String(data.path||'').trim(),
      appPath:appPath,
      reason:String(data.reason||'').trim(),
      readyState:String(data.readyState||'').trim(),
      updatedAt:Date.now()
    };
  }

  function pageContextSummary(){
    var page=state.pageContext;
    if(!page)return 'Waiting for preview…';
    var title=page.title||'Untitled page';
    var path=page.appPath||previewAppPathFromUrl(page.url)||page.path||'';
    return trimText(path&&path!=='/'?title+' — '+path:title,180);
  }

  function selectedElementsList(){
    return Array.isArray(state.selectedElements)?state.selectedElements.filter(Boolean):(state.selectedElement?[state.selectedElement]:[]);
  }

  function selectedElementSummary(element){
    var el=element||selectedElementsList()[0];
    if(!el)return 'None';
    var tag=String(el.tag||'element').toLowerCase();
    var label=trimText(el.text||el.ariaLabel||el.selector||'',96);
    var bits=[tag];
    if(el.id)bits.push('#'+el.id);
    if(label)bits.push('“'+label+'”');
    return trimText(bits.join(' '),160);
  }

  function normalizeSelectedElements(payload){
    var data=payload||{};
    var raw=Array.isArray(data.elements)?data.elements:(data.element?[data.element]:[]);
    var elements=[];
    for(var i=0;i<raw.length&&elements.length<24;i++){
      if(raw[i]&&typeof raw[i]==='object')elements.push(raw[i]);
    }
    return elements;
  }

  function uiProjectLabel(){
    var project=state.project||{};
    return project.fullName||project.name||project.slug||state.projectId||'Unknown project';
  }

  function projectSourceWorkspace(){
    var project=state.project||{};
    return String(project.resolvedPath||project.path||'').trim();
  }

  function currentPreviewContextMetadata(){
    var page=state.pageContext||{};
    var status=state.status||{};
    return {
      projectId:state.projectId||'',
      projectLabel:uiProjectLabel(),
      projectSourceWorkspace:projectSourceWorkspace(),
      previewPath:page.appPath||previewAppPathFromUrl(page.url)||page.path||'',
      previewUrl:page.url||'',
      previewTitle:page.title||'',
      workflowSource:String(status.workflowSource||status.configSource||'').trim(),
      statusSummary:String(status.statusSummary||status.summary||status.title||'').trim(),
      buildCommand:String(status.buildCommand||'').trim(),
      runtimeCommand:String(status.command||'').trim()
    };
  }

  function renderPreviewContext(){
    if(els.currentPage)els.currentPage.textContent=pageContextSummary();
    if(els.selectedElement){
      var selected=selectedElementsList();
      els.selectedElement.textContent=selected.length>1?(selected.length+' elements'):selectedElementSummary(selected[0]);
    }
    if(els.contextSyncStatus){
      els.contextSyncStatus.textContent=state.inspectEnabled?'Click preview element to highlight':'Auto-sent to chat';
    }
    updateInspectButtons();
    syncChatContext();
  }

  function updateInspectButtons(){
    root.classList.toggle('inspect-active',!!state.inspectEnabled);
    var count=selectedElementsList().length;
    root.querySelectorAll('[data-inspect-toggle]').forEach(function(button){
      button.textContent=state.inspectEnabled?(count?('Highlight ('+count+')'):'Stop highlight'):'Highlight';
      button.setAttribute('aria-pressed',String(!!state.inspectEnabled));
      button.title=state.inspectEnabled?'Click preview elements to toggle them in the multi-selection':'Highlight and select multiple elements in the live preview';
    });
    root.querySelectorAll('[data-highlight-clear]').forEach(function(button){
      button.disabled=count===0;
      button.title=count?('Clear '+count+' highlighted '+(count===1?'element':'elements')):'No highlighted elements to clear';
      button.setAttribute('aria-disabled',String(count===0));
    });
  }

  function postPreviewMessage(type,payload){
    if(!els.previewFrame||!els.previewFrame.contentWindow)return;
    var message=Object.assign({hermesUiMode:1,type:type},payload||{});
    try{els.previewFrame.contentWindow.postMessage(message,window.location.origin);}catch(_){/* best effort */}
  }

  function requestPreviewContext(){
    postPreviewMessage('hermes-ui-request-context',{});
  }

  function setInspectEnabled(enabled,options){
    state.inspectEnabled=!!enabled;
    updateInspectButtons();
    renderPreviewContext();
    if(!(options&&options.silent))postPreviewMessage('hermes-ui-inspector-toggle',{enabled:!!state.inspectEnabled});
  }

  function clearHighlights(options){
    state.selectedElement=null;
    state.selectedElements=[];
    renderPreviewContext();
    if(!(options&&options.silent))postPreviewMessage('hermes-ui-clear-highlights',{});
  }

  function formatUiContext(){
    var page=state.pageContext||{};
    var meta=currentPreviewContextMetadata();
    var path=meta.previewPath||'Unknown';
    var lines=['[UI Mode context]','Mode: UI Mode live preview','Project: '+meta.projectLabel];
    if(meta.projectId)lines.push('Project ID: '+meta.projectId);
    if(meta.projectSourceWorkspace)lines.push('Project source workspace: '+meta.projectSourceWorkspace);
    if(meta.workflowSource)lines.push('Runtime workflow source: '+meta.workflowSource);
    if(meta.statusSummary)lines.push('Runtime status: '+meta.statusSummary);
    if(meta.buildCommand)lines.push('Runtime build command: '+trimText(meta.buildCommand,300));
    if(meta.runtimeCommand)lines.push('Runtime start command: '+trimText(meta.runtimeCommand,300));
    lines.push('Current page path: '+path);
    if(page.title)lines.push('Current page title: '+page.title);
    if(page.url)lines.push('Preview URL: '+page.url);
    var selected=selectedElementsList();
    if(selected.length){
      lines.push('Highlighted/selected elements: '+selected.length);
      for(var i=0;i<selected.length;i++){
        var el=selected[i];
        var prefix='Element '+(i+1);
        lines.push(prefix+': '+selectedElementSummary(el));
        if(el.selector)lines.push(prefix+' selector: '+el.selector);
        if(el.role)lines.push(prefix+' role: '+el.role);
        if(el.ariaLabel)lines.push(prefix+' accessible label: '+trimText(el.ariaLabel,200));
        if(el.text)lines.push(prefix+' visible text: '+trimText(el.text,260));
        if(el.href)lines.push(prefix+' href: '+el.href);
        if(el.src)lines.push(prefix+' source: '+el.src);
        if(el.rect)lines.push(prefix+' bounds: x='+Math.round(el.rect.x||0)+', y='+Math.round(el.rect.y||0)+', width='+Math.round(el.rect.width||0)+', height='+Math.round(el.rect.height||0));
      }
    }else{
      lines.push('Highlighted/selected elements: none');
    }
    return lines.join('\n');
  }

  function postChatMessage(type,payload){
    if(!els.chatFrame||!els.chatFrame.contentWindow||!els.chatFrame.getAttribute('src'))return false;
    var message=Object.assign({hermesUiMode:1,type:type},payload||{});
    try{els.chatFrame.contentWindow.postMessage(message,window.location.origin);return true;}catch(_){return false;}
  }

  function syncChatContext(){
    var meta=currentPreviewContextMetadata();
    postChatMessage('hermes-ui-mode-context-update',{context:formatUiContext(),page:state.pageContext,selection:state.selectedElement,selections:selectedElementsList(),project:{id:meta.projectId,label:meta.projectLabel,workspace:meta.projectSourceWorkspace},runtime:{workflowSource:meta.workflowSource,statusSummary:meta.statusSummary,buildCommand:meta.buildCommand,runtimeCommand:meta.runtimeCommand}});
  }

  function handlePreviewMessage(event){
    if(event.origin!==window.location.origin)return;
    var data=event.data||{};
    if(!data||data.hermesUiMode!==1)return;
    if(data.type==='hermes-ui-preview-context'){
      state.pageContext=normalizePageContext(data);
      renderPreviewContext();
    }else if(data.type==='hermes-ui-element-selected'){
      state.selectedElements=normalizeSelectedElements(data);
      state.selectedElement=state.selectedElements.length?state.selectedElements[state.selectedElements.length-1]:null;
      if(data.page)state.pageContext=normalizePageContext(data.page);
      renderPreviewContext();
    }else if(data.type==='hermes-ui-inspector-state'){
      setInspectEnabled(!!data.enabled,{silent:true});
    }
  }

  function freshUrl(url,token){
    var fresh=new URL(url,window.location.href);
    fresh.searchParams.set('__hermesUiModeTs',String(token||state.cacheToken||Date.now()));
    return fresh.href;
  }

  async function api(path,options){
    var opts=options||{};
    var headers=Object.assign({'Accept':'application/json'},opts.headers||{});
    if(opts.body!==undefined){
      headers['Content-Type']='application/json';
      Object.assign(headers,csrfHeaders());
    }
    Object.assign(headers,{'Cache-Control':'no-store','Pragma':'no-cache'});
    var response=await fetch(freshUrl(appUrl(path),Date.now()),Object.assign({},opts,{headers:headers,credentials:'include',cache:'no-store'}));
    var text=await response.text();
    var payload={};
    if(text){
      try{payload=JSON.parse(text);}catch(_){payload={error:text};}
    }
    if(!response.ok){
      var error=new Error(payload.error||payload.message||('Request failed with '+response.status));
      error.status=response.status;
      error.payload=payload;
      throw error;
    }
    return payload;
  }

  function statusKind(status){
    var kind=String(status&&status.kind||'').trim().toLowerCase();
    if(kind)return kind;
    var value=String(status&&status.status||'idle').trim().toLowerCase();
    if(value==='ready')return 'ready';
    if(value==='starting'||value==='building')return 'warning';
    if(value==='failed')return 'error';
    return 'idle';
  }

  function setFrameSource(frame,url,token){
    if(!frame)return;
    var next=String(url||'').trim();
    if(!next){
      frame.removeAttribute('src');
      return;
    }
    var resolved=freshUrl(appUrl(next),token);
    if(frame.getAttribute('src')!==resolved)frame.setAttribute('src',resolved);
  }

  function renderStatus(status){
    state.status=status||{};
    var label=status&&status.label||status&&status.status||'Idle';
    var summary=status&&status.statusSummary||status&&status.summary||'';
    var kind=statusKind(status);
    if(els.statusDot){
      els.statusDot.className='dot';
      if(kind==='ready'||kind==='warning'||kind==='error')els.statusDot.classList.add(kind);
    }
    if(els.statusText)els.statusText.textContent=summary||label;
    if(els.previewMeta){
      els.previewMeta.textContent=status&&status.previewUrl?status.previewUrl:(status&&status.configAvailable?'Ready to start':'No UI workflow');
    }
    var canStart=!!(status&&status.canStart);
    root.querySelectorAll('[data-action="start"],[data-action="restart"]').forEach(function(button){
      button.disabled=!state.projectId||!canStart;
    });
    root.querySelectorAll('[data-action="stop"]').forEach(function(button){
      button.disabled=!state.projectId||!(status&&status.running);
    });
    if(status&&status.ready&&status.previewUrl){
      setFrameSource(els.previewFrame,status.previewUrl);
      if(!state.pageContext){
        state.pageContext=normalizePageContext({url:appUrl(status.previewUrl),appPath:previewAppPathFromUrl(status.previewUrl),reason:'status'});
        renderPreviewContext();
      }
      if(els.previewEmpty)els.previewEmpty.style.display='none';
    }else if(els.previewEmpty){
      els.previewEmpty.style.display='grid';
      if(state.pageContext||state.selectedElement||selectedElementsList().length){
        state.pageContext=null;
        state.selectedElement=null;
        state.selectedElements=[];
        renderPreviewContext();
      }
    }
    if(status&&status.error)setError(status.error); else setError('');
  }

  function renderLogs(payload){
    if(!els.logs)return;
    var text=String(payload&&payload.text||'').trim();
    els.logs.textContent=text||'No UI runtime logs yet.';
    els.logs.classList.toggle('show',state.logsVisible);
  }

  async function loadProject(){
    if(!state.projectId){
      if(els.projectLabel)els.projectLabel.textContent='Open UI Mode from an Ops project or add ?projectId=...';
      if(els.chatMeta)els.chatMeta.textContent='No project selected';
      return;
    }
    var payload=await api('api/core/projects/'+encodeURIComponent(state.projectId));
    state.project=payload.project||null;
    var project=state.project||{};
    var label=project.fullName||project.name||project.slug||state.projectId;
    if(els.projectLabel)els.projectLabel.textContent=label;
    renderPreviewContext();
  }

  async function refreshStatus(){
    if(!state.projectId)return null;
    var status=await api('api/core/projects/'+encodeURIComponent(state.projectId)+'/ui/status');
    renderStatus(status);
    if(state.logsVisible){
      try{renderLogs(await api('api/core/projects/'+encodeURIComponent(state.projectId)+'/ui/logs?limit=400'));}catch(_){/* best effort */}
    }
    schedulePoll(status);
    return status;
  }

  function schedulePoll(status){
    if(state.pollTimer)window.clearTimeout(state.pollTimer);
    var shouldPoll=status&&((status.running&&!status.ready)||status.status==='building'||status.status==='starting'||status.status==='ready');
    if(shouldPoll){
      state.pollTimer=window.setTimeout(function(){refreshStatus().catch(function(error){setError(error.message);});},2000);
    }
  }

  async function refreshLogs(){
    if(!state.projectId)return;
    renderLogs(await api('api/core/projects/'+encodeURIComponent(state.projectId)+'/ui/logs?limit=500'));
  }

  async function startRuntime(restart){
    if(!state.projectId)return;
    setBusy(restart?'restart':'start',true);
    try{
      await ensureChatSession();
      var action=restart?'restart':'start';
      var payload=await api('api/core/projects/'+encodeURIComponent(state.projectId)+'/ui/'+action,{method:'POST',body:JSON.stringify({sessionId:state.sessionId||''})});
      var status=payload.status||payload;
      renderStatus(status);
      schedulePoll(status);
      state.logsVisible=true;
      if(els.logs)els.logs.classList.add('show');
      await refreshLogs().catch(function(){});
    }catch(error){
      setError(error.message);
    }finally{
      setBusy(restart?'restart':'start',false);
    }
  }

  async function stopRuntime(){
    if(!state.projectId)return;
    setBusy('stop',true);
    try{
      var payload=await api('api/core/projects/'+encodeURIComponent(state.projectId)+'/ui/stop',{method:'POST',body:JSON.stringify({})});
      var status=payload.status||payload;
      renderStatus(status);
      schedulePoll(status);
      await refreshLogs().catch(function(){});
    }catch(error){
      setError(error.message);
    }finally{
      setBusy('stop',false);
    }
  }

  function clearChatSessionFromUrl(){
    try{
      var url=new URL(window.location.href);
      url.searchParams.delete('sessionId');
      url.searchParams.delete('session_id');
      window.history.replaceState({},'',url.toString());
    }catch(_){/* best effort */}
  }

  async function ensureChatSession(){
    if(state.sessionId){
      if(!state.sessionVerified){
        var existingId=state.sessionId;
        try{
          await api('api/session?session_id='+encodeURIComponent(existingId)+'&messages=0&resolve_model=0');
          state.sessionVerified=true;
        }catch(error){
          if(error&&error.status===404){
            state.sessionId='';
            state.sessionVerified=false;
            clearChatSessionFromUrl();
            if(els.chatMeta)els.chatMeta.textContent='Recreating session…';
          }else{
            throw error;
          }
        }
      }
      if(state.sessionId){
        openChatFrame(state.sessionId);
        return state.sessionId;
      }
    }
    if(state.chatCreating)return '';
    state.chatCreating=true;
    if(els.chatMeta)els.chatMeta.textContent='Creating session…';
    try{
      if(!state.project)await loadProject();
      var project=state.project||{};
      var meta=currentPreviewContextMetadata();
      var body={
        project_id:state.projectId,
        projectId:state.projectId,
        session_mode:'ui_mode',
        surface:'ui_mode',
        ui_project_id:meta.projectId,
        ui_project_label:meta.projectLabel,
        ui_preview_path:meta.previewPath,
        ui_preview_url:meta.previewUrl,
        ui_preview_title:meta.previewTitle,
        ui_workflow_source:meta.workflowSource,
        ui_status_summary:meta.statusSummary,
        ui_build_command:meta.buildCommand,
        ui_runtime_command:meta.runtimeCommand
      };
      var workspace=projectSourceWorkspace();
      if(workspace)body.workspace=workspace;
      if(project.profile)body.profile=project.profile;
      var payload=await api('api/session/new',{method:'POST',body:JSON.stringify(body)});
      var session=payload.session||{};
      state.sessionId=String(session.session_id||session.sessionId||session.id||'').trim();
      if(!state.sessionId)throw new Error('Session was created without an id.');
      state.sessionVerified=true;
      var url=new URL(window.location.href);
      url.searchParams.set('projectId',state.projectId);
      url.searchParams.set('sessionId',state.sessionId);
      window.history.replaceState({},'',url.toString());
      openChatFrame(state.sessionId);
      return state.sessionId;
    }catch(error){
      if(els.chatMeta)els.chatMeta.textContent='Open chat failed';
      setError(error.message);
      return '';
    }finally{
      state.chatCreating=false;
    }
  }

  function openChatFrame(sessionId){
    var sid=String(sessionId||'').trim();
    if(!sid)return;
    var meta=currentPreviewContextMetadata();
    var chatUrl=new URL('session/'+encodeURIComponent(sid),window.location.href);
    chatUrl.searchParams.set('inspect','simplified');
    chatUrl.searchParams.set('projectId',state.projectId||'');
    chatUrl.searchParams.set('sessionMode','ui_mode');
    if(meta.projectId)chatUrl.searchParams.set('uiProjectId',meta.projectId);
    if(meta.projectLabel)chatUrl.searchParams.set('uiProjectLabel',meta.projectLabel);
    if(meta.previewPath)chatUrl.searchParams.set('uiPreviewPath',meta.previewPath);
    if(meta.previewUrl)chatUrl.searchParams.set('uiPreviewUrl',meta.previewUrl);
    if(meta.previewTitle)chatUrl.searchParams.set('uiPreviewTitle',meta.previewTitle);
    if(meta.workflowSource)chatUrl.searchParams.set('uiWorkflowSource',meta.workflowSource);
    if(meta.statusSummary)chatUrl.searchParams.set('uiStatusSummary',meta.statusSummary);
    if(meta.projectSourceWorkspace)chatUrl.searchParams.set('uiProjectWorkspace',meta.projectSourceWorkspace);
    setFrameSource(els.chatFrame,chatUrl.href);
    if(els.chatEmpty)els.chatEmpty.style.display='none';
    if(els.chatMeta)els.chatMeta.textContent='Session '+sid;
    window.setTimeout(syncChatContext,250);
  }

  function reloadPreview(){
    if(els.previewFrame&&els.previewFrame.getAttribute('src')){
      state.cacheToken=String(Date.now());
      var src=els.previewFrame.getAttribute('src');
      setFrameSource(els.previewFrame,src,state.cacheToken);
    }
  }

  root.addEventListener('click',function(event){
    var button=event.target&&event.target.closest?event.target.closest('[data-action]'):null;
    if(!button||!root.contains(button))return;
    var action=button.getAttribute('data-action');
    if(action==='start')startRuntime(false);
    else if(action==='restart')startRuntime(true);
    else if(action==='stop')stopRuntime();
    else if(action==='refresh')refreshStatus().catch(function(error){setError(error.message);});
    else if(action==='reload-preview')reloadPreview();
    else if(action==='toggle-chrome')setControlsCollapsed(!state.controlsCollapsed);
    else if(action==='show-controls')setControlsCollapsed(false);
    else if(action==='toggle-chat')setChatCollapsed(!state.chatCollapsed);
    else if(action==='show-chat')setChatCollapsed(false);
    else if(action==='focus-preview')focusPreview();
    else if(action==='toggle-inspect')setInspectEnabled(!state.inspectEnabled);
    else if(action==='clear-highlights')clearHighlights();
    else if(action==='toggle-logs'){
      state.logsVisible=!state.logsVisible;
      if(els.logs)els.logs.classList.toggle('show',state.logsVisible);
      if(state.logsVisible)refreshLogs().catch(function(error){setError(error.message);});
    }else if(action==='open-chat'){
      ensureChatSession();
    }
  });

  async function init(){
    try{
      await loadProject();
      if(state.sessionId||state.projectId)await ensureChatSession();
      var status=await refreshStatus();
      var autoStart=String(params.get('autostart')||params.get('autoStart')||'').trim().toLowerCase();
      if(!state.autoStartDone&&['1','true','yes','on'].indexOf(autoStart)>=0&&status&&status.canStart&&!status.running&&!status.ready){
        state.autoStartDone=true;
        startRuntime(false);
      }
    }catch(error){
      setError(error.message);
    }
  }

  loadLayoutState();
  applyLayoutState(false);
  renderPreviewContext();
  window.addEventListener('message',handlePreviewMessage);
  if(els.previewFrame){
    els.previewFrame.addEventListener('load',function(){
      requestPreviewContext();
      if(state.inspectEnabled)window.setTimeout(function(){postPreviewMessage('hermes-ui-inspector-toggle',{enabled:true});},100);
    });
  }
  if(els.chatFrame)els.chatFrame.addEventListener('load',function(){window.setTimeout(syncChatContext,100);});
  init();
})();

(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};
  const playPollTimers=new Map();

  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const api=ctx&&ctx.api;
    const projectUrl=ctx&&ctx.projectUrl;
    const renderCurrentOpsView=ctx&&ctx.renderCurrentOpsView;
    const showToast=ctx&&ctx.showToast;
    const esc=ctx&&ctx.esc;
    const svg=ctx&&ctx.svg;
    const AgentBridgeRef=ctx&&ctx.AgentBridge;
    const loadNotifications=ctx&&ctx.loadNotifications;
    const playInspectOverlayUrl=ctx&&ctx.playInspectOverlayUrl;
    const openProjectDetail=ctx&&ctx.openProjectDetail;
    const notificationById=ctx&&ctx.notificationById;
    const notificationTarget=ctx&&ctx.notificationTarget;
    const playNotificationFallbackError=ctx&&ctx.playNotificationFallbackError;
    const windowRef=(ctx&&ctx.windowRef)||window;
    if(!OPS||typeof api!=='function'||typeof projectUrl!=='function'||typeof renderCurrentOpsView!=='function'||typeof showToast!=='function'||typeof esc!=='function'||!svg||!AgentBridgeRef||!AgentBridgeRef.play||!AgentBridgeRef.runtime){
      return {};
    }

    function playStatusFor(projectId){
      return OPS.playStatusByProject[projectId]||{
        projectId,
        status:'idle',
        configured:false,
        configValid:false,
        configAvailable:false,
        running:false,
        ready:false,
        logsAvailable:false,
        kind:'idle',
        label:'No Play config',
        title:'Play status unavailable.',
        summary:'Play status unavailable.',
      };
    }

    function isPlayRunning(status){
      const state=String((status&&status.status)||'').toLowerCase();
      return !!(status&&(status.running||['queued','building','starting','ready'].includes(state)));
    }

    function shouldPollPlayStatus(status){
      const state=String((status&&status.status)||'').toLowerCase();
      return !!(status&&(['queued','building','starting'].includes(state)||(status.running&&!status.ready)));
    }

    function playStatusKind(status){
      return String(status&&status.kind||'idle');
    }

    function playStatusLabel(status){
      return String(status&&status.label||'Play status unavailable.');
    }

    function playStatusTitle(status){
      return String(status&&status.title||'Play status unavailable.');
    }

    function playStatusSummary(status){
      return String(status&&status.summary||'Play status unavailable.');
    }

    function schedulePlayStatusPoll(projectId){
      if(playPollTimers.has(projectId))return;
      const timer=setTimeout(async()=>{
        playPollTimers.delete(projectId);
        try{
          const status=await refreshProjectPlayStatus(projectId,{render:true});
          if(status&&status.ready&&typeof loadNotifications==='function')await loadNotifications().catch(()=>{});
          if(shouldPollPlayStatus(status))schedulePlayStatusPoll(projectId);
        }catch(e){
          // Keep polling quiet; explicit controls surface errors.
        }
      },2000);
      playPollTimers.set(projectId,timer);
    }

    function clearPlayStatusPoll(projectId){
      const timer=playPollTimers.get(projectId);
      if(!timer)return;
      clearTimeout(timer);
      playPollTimers.delete(projectId);
    }

    function stopPlayStatusPolling(){
      playPollTimers.forEach(timer=>clearTimeout(timer));
      playPollTimers.clear();
    }

    async function refreshProjectPlayStatus(projectId,options){
      const id=String(projectId||'').trim();
      if(!id)return null;
      const status=await AgentBridgeRef.play.status(id);
      OPS.playStatusByProject[id]=status;
      if(shouldPollPlayStatus(status))schedulePlayStatusPoll(id);
      else clearPlayStatusPoll(id);
      if(!options||options.render!==false)renderCurrentOpsView();
      return status;
    }

    function playConfigFor(projectId){
      return OPS.playConfigByProject[projectId]||null;
    }

    async function loadProjectPlayConfig(projectId){
      const id=String(projectId||'').trim();
      if(!id)return null;
      const data=await AgentBridgeRef.play.config(id);
      OPS.playConfigByProject[id]=data;
      return data;
    }

    async function showProjectPlayConfig(projectId){
      const id=String(projectId||'').trim();
      if(!id)return;
      OPS.playConfigEditingProjectId=id;
      if(!playConfigFor(id))await loadProjectPlayConfig(id);
      renderCurrentOpsView();
    }

    function closeProjectPlayConfig(){
      OPS.playConfigEditingProjectId='';
      renderCurrentOpsView();
    }

    function renderProjectPlayConfigEditor(project){
      if(!project||OPS.playConfigEditingProjectId!==project.id)return '';
      const doc=playConfigFor(project.id);
      const loading=!doc;
      const content=loading?'':String(doc.content||'');
      const target=loading?'Loading Play config...':String(doc.targetPath||doc.info&&doc.info.path||'');
      return `
        <form class="tasks-card ops-play-config-panel" data-ops-submit="play-config" data-project-id="${esc(project.id)}">
          <div class="tasks-card-header ops-play-config-header">
            <div>
              <div class="tasks-card-title">Play config</div>
              <div class="tasks-card-subtitle">${esc(target)}</div>
            </div>
            <div class="tasks-card-actions">
              <button class="menu-action-btn secondary small" type="button" data-ops-action="close-play-config">${svg.close}<span>Close</span></button>
            </div>
          </div>
          <div class="tasks-card-body ops-play-config-body">
            <textarea name="content" rows="14" spellcheck="false" ${loading?'disabled':''}>${esc(content)}</textarea>
            <div class="tasks-card-actions ops-form-actions">
              <button class="menu-action-btn small" type="submit" ${loading?'disabled':''}>${svg.check}<span>Save Play config</span></button>
              <button class="menu-action-btn secondary small" type="button" data-ops-action="reload-play-config" data-project-id="${esc(project.id)}">${svg.refresh}<span>Reload</span></button>
            </div>
          </div>
        </form>
      `;
    }

    function renderProjectPlayControls(project,options){
      if(!project||!project.id)return '';
      const status=playStatusFor(project.id);
      const busy=!!OPS.playBusyByProject[project.id];
      const running=isPlayRunning(status);
      const state=String(status.status||'idle').toLowerCase();
      const canStart=!!(status.configAvailable&&status.configValid&&!running&&!busy);
      const canStop=!!(running&&!busy);
      const canRestart=!!(status.configAvailable&&status.configValid&&!busy&&(running||state==='failed'||state==='stopped'));
      const canOpen=!!(status.inspectUrl&&(status.ready||String(status.status||'')==='ready'));
      const canSnapshot=!!(status.inspectUrl&&status.ready&&!busy);
      const canScreenshot=!!(status.inspectUrl&&status.ready&&!busy);
      const canLogs=!!(status.logsAvailable||running||status.status==='failed'||OPS.playLogsByProject[project.id]);
      const className=options&&options.detail?'ops-play-controls detail':'ops-play-controls';
      const blockClass=options&&options.detail?'ops-play-block detail':'ops-play-block';
      const primaryButtonClass=options&&options.detail?'menu-action-btn small':'ops-btn primary';
      const secondaryButtonClass=options&&options.detail?'menu-action-btn secondary small':'ops-btn';
      const startTitle=status.configAvailable?playStatusTitle(status):'Add project_play.json or .cloud-terminal/play.json to enable Play.';
      const summary=playStatusSummary(status);
      return `
        <div class="${blockClass}">
          <div class="${className}">
            <span class="ops-play-status ${esc(playStatusKind(status))}" title="${esc(playStatusTitle(status))}">${esc(playStatusLabel(status))}</span>
            <button class="${secondaryButtonClass}" type="button" data-ops-action="show-play-config" data-project-id="${esc(project.id)}">${svg.edit}<span>Configure</span></button>
            <button class="${primaryButtonClass}" type="button" data-ops-action="start-play" data-project-id="${esc(project.id)}" title="${esc(startTitle)}" ${canStart?'':'disabled'}>${svg.play}<span>${busy&&OPS.playBusyByProject[project.id]==='start'?'Starting...':'Start'}</span></button>
            ${canOpen?`<button class="${primaryButtonClass}" type="button" data-ops-action="open-play" data-project-id="${esc(project.id)}">${svg.play}<span>Open</span></button>`:''}
            ${canSnapshot?`<button class="${secondaryButtonClass}" type="button" data-ops-action="snapshot-play" data-project-id="${esc(project.id)}">${svg.folder}<span>${busy&&OPS.playBusyByProject[project.id]==='snapshot'?'Capturing...':'Snapshot'}</span></button>`:''}
            ${canScreenshot?`<button class="${secondaryButtonClass}" type="button" data-ops-action="screenshot-play" data-project-id="${esc(project.id)}">${svg.folder}<span>${busy&&OPS.playBusyByProject[project.id]==='screenshot'?'Capturing...':'Screenshot'}</span></button>`:''}
            ${canRestart?`<button class="${secondaryButtonClass}" type="button" data-ops-action="restart-play" data-project-id="${esc(project.id)}">${svg.refresh}<span>${busy&&OPS.playBusyByProject[project.id]==='restart'?'Restarting...':'Restart'}</span></button>`:''}
            ${canStop?`<button class="${secondaryButtonClass}" type="button" data-ops-action="stop-play" data-project-id="${esc(project.id)}">${svg.close}<span>Stop</span></button>`:''}
            ${canLogs?`<button class="${secondaryButtonClass}" type="button" data-ops-action="show-play-logs" data-project-id="${esc(project.id)}">Logs</button>`:''}
          </div>
          ${summary?`<div class="ops-play-summary ${esc(playStatusKind(status))}">${esc(summary)}</div>`:''}
        </div>
      `;
    }

    function renderProjectPlayLogs(projectId){
      const entry=OPS.playLogsByProject[projectId];
      if(!entry)return '';
      const text=typeof entry==='string'?entry:(entry.text||'');
      const lineCount=(text.match(/\n/g)||[]).length+(text?1:0);
      return `
        <section class="tasks-card ops-play-log-panel">
          <div class="tasks-card-header ops-play-log-header">
            <div>
              <div class="tasks-card-title">Play logs</div>
              <div class="tasks-card-subtitle">${esc(lineCount?`${lineCount} line${lineCount===1?'':'s'} captured`:'No Play logs yet')}</div>
            </div>
            <div class="tasks-card-actions">
              <button class="menu-action-btn secondary small" type="button" data-ops-action="show-play-logs" data-project-id="${esc(projectId)}">${svg.refresh}<span>Refresh</span></button>
            </div>
          </div>
          <div class="tasks-card-body">
            <pre class="ops-play-logs">${esc(text||'No Play logs yet.')}</pre>
          </div>
        </section>
      `;
    }

    function renderProjectRuntimeSnapshot(projectId){
      const snapshot=OPS.playSnapshotsByProject[projectId];
      if(!snapshot)return '';
      const path=String(snapshot.bodyPath||'');
      const href=path?`/api/media?path=${encodeURIComponent(path)}`:'';
      const label=[
        snapshot.statusCode?`HTTP ${snapshot.statusCode}`:'',
        snapshot.contentType||'',
        snapshot.size?`${snapshot.size} bytes`:'',
      ].filter(Boolean).join(' | ');
      return `
        <section class="tasks-card ops-play-snapshot-panel">
          <div class="tasks-card-header">
            <div>
              <div class="tasks-card-title">Runtime snapshot</div>
              <div class="tasks-card-subtitle">${esc(label||'Captured runtime response')}</div>
            </div>
            <div class="tasks-card-actions">
              ${href?`<a class="menu-action-btn secondary small" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${svg.folder}<span>Open</span></a>`:''}
            </div>
          </div>
        </section>
      `;
    }

    function renderProjectRuntimeScreenshot(projectId){
      const screenshot=OPS.playScreenshotsByProject[projectId];
      if(!screenshot)return '';
      const path=String(screenshot.screenshotPath||'');
      const href=path?`/api/media?path=${encodeURIComponent(path)}`:'';
      const label=[
        screenshot.selector?`Selector ${screenshot.selector}`:'Full page',
        screenshot.size?`${screenshot.size} bytes`:'',
        screenshot.createdAt||'',
      ].filter(Boolean).join(' | ');
      return `
        <section class="tasks-card ops-play-snapshot-panel">
          <div class="tasks-card-header">
            <div>
              <div class="tasks-card-title">Runtime screenshot</div>
              <div class="tasks-card-subtitle">${esc(label||'Captured browser screenshot')}</div>
            </div>
            <div class="tasks-card-actions">
              ${href?`<a class="menu-action-btn secondary small" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${svg.folder}<span>Open</span></a>`:''}
            </div>
          </div>
        </section>
      `;
    }

    async function startProjectPlay(projectId){
      const id=String(projectId||'').trim();
      if(!id)return;
      OPS.playBusyByProject[id]='start';
      renderCurrentOpsView();
      try{
        const res=await AgentBridgeRef.play.start(id,{});
        if(res&&res.status)OPS.playStatusByProject[id]=res.status;
        delete OPS.playLogsByProject[id];
        schedulePlayStatusPoll(id);
        showToast('Play pipeline started',2400);
      }finally{
        delete OPS.playBusyByProject[id];
        renderCurrentOpsView();
      }
    }

    async function stopProjectPlay(projectId){
      const id=String(projectId||'').trim();
      if(!id)return;
      OPS.playBusyByProject[id]='stop';
      renderCurrentOpsView();
      try{
        const res=await AgentBridgeRef.play.stop(id);
        if(res&&res.status)OPS.playStatusByProject[id]=res.status;
        clearPlayStatusPoll(id);
        showToast('Play pipeline stopped',2200);
      }finally{
        delete OPS.playBusyByProject[id];
        renderCurrentOpsView();
      }
    }

    async function restartProjectPlay(projectId){
      const id=String(projectId||'').trim();
      if(!id)return;
      OPS.playBusyByProject[id]='restart';
      renderCurrentOpsView();
      try{
        const res=await AgentBridgeRef.play.restart(id,{});
        if(res&&res.status)OPS.playStatusByProject[id]=res.status;
        delete OPS.playLogsByProject[id];
        schedulePlayStatusPoll(id);
        renderCurrentOpsView();
      }finally{
        delete OPS.playBusyByProject[id];
        renderCurrentOpsView();
      }
    }

    async function saveProjectPlayConfig(projectId,content){
      const id=String(projectId||'').trim();
      if(!id)return;
      const data=await AgentBridgeRef.play.saveConfig(id,{content:String(content||'')});
      OPS.playConfigByProject[id]={
        ...(OPS.playConfigByProject[id]||{}),
        ...(data||{}),
        content:String(content||''),
      };
      const status=await refreshProjectPlayStatus(id,{render:false}).catch(()=>null);
      if(status)OPS.playStatusByProject[id]=status;
      renderCurrentOpsView();
      showToast('Play config saved',2200);
    }

    async function captureProjectRuntimeSnapshot(projectId){
      const id=String(projectId||'').trim();
      if(!id)return;
      OPS.playBusyByProject[id]='snapshot';
      renderCurrentOpsView();
      try{
        const data=await api(projectUrl(id,'/runtime/snapshot'),{method:'POST',body:JSON.stringify({})});
        if(data&&data.snapshot)OPS.playSnapshotsByProject[id]=data.snapshot;
        renderCurrentOpsView();
        showToast('Runtime snapshot captured',2400);
      }finally{
        delete OPS.playBusyByProject[id];
        renderCurrentOpsView();
      }
    }

    async function captureProjectRuntimeScreenshot(projectId){
      const id=String(projectId||'').trim();
      if(!id)return;
      OPS.playBusyByProject[id]='screenshot';
      renderCurrentOpsView();
      try{
        const data=await AgentBridgeRef.runtime.screenshot(id,{fullPage:true});
        if(data&&data.screenshot)OPS.playScreenshotsByProject[id]=data.screenshot;
        renderCurrentOpsView();
        showToast('Runtime screenshot captured',2400);
      }finally{
        delete OPS.playBusyByProject[id];
        renderCurrentOpsView();
      }
    }

    function openProjectPlay(projectId){
      const status=playStatusFor(projectId);
      const url=typeof playInspectOverlayUrl==='function'?playInspectOverlayUrl({inspectUrl:status.inspectUrl}):'';
      if(!url){
        showToast('No Play inspect URL found for this project.',3000);
        return;
      }
      windowRef.location.assign(url);
    }

    async function showProjectPlayLogs(projectId){
      const id=String(projectId||'').trim();
      if(!id)return;
      const data=await AgentBridgeRef.play.logs(id,1200);
      OPS.playLogsByProject[id]=data||{text:''};
      renderCurrentOpsView();
    }

    function openPlayNotification(notificationId){
      const id=String(notificationId||'').trim();
      const note=typeof notificationById==='function'?notificationById(id):null;
      const url=typeof playInspectOverlayUrl==='function'?playInspectOverlayUrl(note||{}):'';
      if(!url){
        showToast('No Play inspect URL found for this notification.',3000);
        return Promise.resolve();
      }
      windowRef.location.assign(url);
      return Promise.resolve();
    }

    async function repairPlayNotification(notificationId){
      const id=String(notificationId||'').trim();
      const note=typeof notificationById==='function'?notificationById(id):null;
      if(!note){
        showToast('Notification was not found.',2600);
        return;
      }
      const target=typeof notificationTarget==='function'?notificationTarget(note):{};
      const projectId=String(target.projectId||'').trim();
      if(!projectId){
        showToast('Project metadata is missing for this Play repair request.',3200);
        return;
      }
      const fallbackError=typeof playNotificationFallbackError==='function'
        ? playNotificationFallbackError(note)
        : String(note&&note.playFallbackError||'').trim();
      if(typeof openProjectDetail==='function')await openProjectDetail(projectId);
      await showProjectPlayLogs(projectId).catch(()=>null);
      await showProjectPlayConfig(projectId).catch(()=>null);
      if(fallbackError){
        showToast(`Play handoff error: ${fallbackError}`,4200);
      }
    }

    return {
      playStatusFor,
      isPlayRunning,
      shouldPollPlayStatus,
      playStatusKind,
      playStatusLabel,
      playStatusTitle,
      playStatusSummary,
      schedulePlayStatusPoll,
      clearPlayStatusPoll,
      stopPlayStatusPolling,
      refreshProjectPlayStatus,
      loadProjectPlayConfig,
      showProjectPlayConfig,
      closeProjectPlayConfig,
      renderProjectPlayConfigEditor,
      renderProjectPlayControls,
      renderProjectPlayLogs,
      renderProjectRuntimeSnapshot,
      renderProjectRuntimeScreenshot,
      startProjectPlay,
      stopProjectPlay,
      restartProjectPlay,
      saveProjectPlayConfig,
      captureProjectRuntimeSnapshot,
      captureProjectRuntimeScreenshot,
      openProjectPlay,
      showProjectPlayLogs,
      openPlayNotification,
      repairPlayNotification,
    };
  }

  window.HermesOpsModules.play={
    name:'play',
    routes:[
      '/play',
      '/play/config',
      '/play/logs',
      '/play-config-file',
      '/runtime/snapshot',
      '/runtime/screenshot',
    ],
    actions:[
      'show-play-config',
      'close-play-config',
      'reload-play-config',
      'start-play',
      'restart-play',
      'stop-play',
      'open-play',
      'show-play-logs',
      'snapshot-play',
      'screenshot-play',
      'repair-play-notification',
      'open-play-notification',
    ],
    bindDashboard,
  };
})();

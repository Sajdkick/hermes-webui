(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};
  const playPollTimers=new Map();
  const playLogPollTimers=new Map();

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
      const status=OPS.playStatusByProject[projectId]||{
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
      return mergeStatusWithReadyNotification(projectId,status);
    }

    function playStatusConfigured(status){
      return !!(status&&(status.configAvailable===true||status.configExists===true||status.configured===true));
    }

    function playStatusValid(status){
      return !!(status&&(status.configValid===true||status.valid===true));
    }

    function playNotificationProjectId(note){
      const target=typeof notificationTarget==='function'?notificationTarget(note):{};
      return String(target&&target.projectId||note&&note.project_id||note&&note.projectId||note&&note.project&&note.project.id||'').trim();
    }

    function playNotificationInspectTarget(note){
      if(!note||note.kind!=='play')return '';
      if(note.playNeedsRepair===true)return '';
      const playState=String(note.playStatus||'ready').trim().toLowerCase();
      if(playState==='failed'||playState==='stale')return '';
      return typeof playInspectOverlayUrl==='function'?playInspectOverlayUrl(note):String(note.inspectUrl||'').trim();
    }

    function clearProjectPlayNotifications(projectId){
      const id=String(projectId||'').trim();
      if(!id||!Array.isArray(OPS.notifications))return;
      OPS.notifications=OPS.notifications.filter(note=>!(note&&note.kind==='play'&&playNotificationProjectId(note)===id));
    }

    async function refreshProjectPlayNotifications(projectId){
      const id=String(projectId||'').trim();
      if(!id||typeof loadNotifications!=='function')return [];
      clearProjectPlayNotifications(id);
      const notes=await loadNotifications().catch(()=>[]);
      renderCurrentOpsView();
      return notes;
    }

    function readyPlayNotificationForProject(projectId){
      const id=String(projectId||'').trim();
      if(!id)return null;
      const notes=Array.isArray(OPS.notifications)?OPS.notifications:[];
      return notes.find(note=>playNotificationProjectId(note)===id&&!!playNotificationInspectTarget(note))||null;
    }

    function mergeStatusWithReadyNotification(projectId,status){
      const current=status&&typeof status==='object'?status:{};
      if(current.inspectUrl&&(current.ready===true||String(current.status||'').toLowerCase()==='ready'))return current;
      const note=readyPlayNotificationForProject(projectId);
      const inspectUrl=playNotificationInspectTarget(note);
      if(!inspectUrl)return current;
      const message=String(note&&note.message||'Play app is ready for inspection.').trim();
      return {
        ...current,
        projectId:String(projectId||current.projectId||''),
        status:'ready',
        kind:current.kind||'ready',
        label:current.label||'Play ready',
        title:current.title||message,
        summary:current.summary||current.statusSummary||message,
        configured:true,
        valid:true,
        configExists:true,
        configAvailable:true,
        configValid:true,
        running:current.running===true,
        ready:true,
        inspectUrl,
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
          if(status&&(shouldPollPlayStatus(status)||status.ready||String(status.status||'').toLowerCase()==='failed')){
            await refreshProjectPlayNotifications(projectId);
          }
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

    function clearPlayLogsPoll(projectId){
      const timer=playLogPollTimers.get(projectId);
      if(!timer)return;
      clearTimeout(timer);
      playLogPollTimers.delete(projectId);
    }

    function schedulePlayLogsPoll(projectId,status){
      const id=String(projectId||'').trim();
      if(!id||!OPS.playLogsByProject[id])return;
      if(!shouldPollPlayStatus(status)){
        clearPlayLogsPoll(id);
        return;
      }
      if(playLogPollTimers.has(id))return;
      const timer=setTimeout(async()=>{
        playLogPollTimers.delete(id);
        if(!OPS.playLogsByProject[id])return;
        try{
          await showProjectPlayLogs(id,{render:true});
          schedulePlayLogsPoll(id,playStatusFor(id));
        }catch(e){
          // Leave the current logs visible; explicit refresh can surface failures.
        }
      },2500);
      playLogPollTimers.set(id,timer);
    }

    function stopPlayStatusPolling(){
      playPollTimers.forEach(timer=>clearTimeout(timer));
      playPollTimers.clear();
      playLogPollTimers.forEach(timer=>clearTimeout(timer));
      playLogPollTimers.clear();
    }

    async function refreshProjectPlayStatus(projectId,options){
      const id=String(projectId||'').trim();
      if(!id)return null;
      const status=await AgentBridgeRef.play.status(id);
      OPS.playStatusByProject[id]=status;
      if(shouldPollPlayStatus(status))schedulePlayStatusPoll(id);
      else clearPlayStatusPoll(id);
      if(OPS.playLogsByProject[id])schedulePlayLogsPoll(id,status);
      if(!options||options.render!==false)renderCurrentOpsView();
      return status;
    }

    function renderProjectPlayControls(project,options){
      if(!project||!project.id)return '';
      const status=playStatusFor(project.id);
      const busy=!!OPS.playBusyByProject[project.id];
      const running=isPlayRunning(status);
      const state=String(status.status||'idle').toLowerCase();
      const configured=playStatusConfigured(status);
      const valid=playStatusValid(status);
      const canStart=!!(configured&&valid&&!running&&!busy);
      const canStop=!!(running&&!busy);
      const canRestart=!!(configured&&valid&&!busy&&(running||state==='failed'||state==='stopped'));
      const canOpen=!!(status.inspectUrl&&(status.ready||String(status.status||'')==='ready'));
      const canSnapshot=!!(status.inspectUrl&&status.ready&&!busy);
      const canScreenshot=!!(status.inspectUrl&&status.ready&&!busy);
      const canLogs=!!(status.logsAvailable||running||status.status==='failed'||OPS.playLogsByProject[project.id]);
      const projectCard=!!(options&&options.projectCard);
      const detail=!!(options&&options.detail);
      const className=detail||projectCard?'ops-play-controls detail':'ops-play-controls';
      const blockClass=detail||projectCard?'ops-play-block detail':'ops-play-block';
      const primaryButtonClass=detail||projectCard?'menu-action-btn small':'ops-btn primary';
      const secondaryButtonClass=detail||projectCard?'menu-action-btn secondary small':'ops-btn';
      const startTitle=configured?playStatusTitle(status):'Add project_play.json or .cloud-terminal/play.json to enable Build.';
      const summary=playStatusSummary(status);
      const startLabel=busy&&OPS.playBusyByProject[project.id]==='start'?'Building...':'Build';
      const openLabel='Play';
      return `
        <div class="${blockClass}">
          <div class="${className}">
            <span class="ops-play-status ${esc(playStatusKind(status))}" title="${esc(playStatusTitle(status))}">${esc(playStatusLabel(status))}</span>
            <button class="${primaryButtonClass}" type="button" data-ops-action="start-play" data-project-id="${esc(project.id)}" title="${esc(startTitle)}" ${canStart?'':'disabled'}>${svg.play}<span>${startLabel}</span></button>
            ${canOpen?`<button class="${primaryButtonClass}" type="button" data-ops-action="open-play" data-project-id="${esc(project.id)}">${svg.play}<span>${openLabel}</span></button>`:''}
            ${canSnapshot&&!projectCard?`<button class="${secondaryButtonClass}" type="button" data-ops-action="snapshot-play" data-project-id="${esc(project.id)}">${svg.folder}<span>${busy&&OPS.playBusyByProject[project.id]==='snapshot'?'Capturing...':'Snapshot'}</span></button>`:''}
            ${canScreenshot&&!projectCard?`<button class="${secondaryButtonClass}" type="button" data-ops-action="screenshot-play" data-project-id="${esc(project.id)}">${svg.folder}<span>${busy&&OPS.playBusyByProject[project.id]==='screenshot'?'Capturing...':'Screenshot'}</span></button>`:''}
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
        clearProjectPlayNotifications(id);
        OPS.playLogsByProject[id]={text:'Loading Play logs...'};
        schedulePlayStatusPoll(id);
        schedulePlayLogsPoll(id,playStatusFor(id));
        await refreshProjectPlayNotifications(id);
        void showProjectPlayLogs(id,{render:true}).catch(()=>{});
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
        clearProjectPlayNotifications(id);
        OPS.playLogsByProject[id]={text:'Loading Play logs...'};
        schedulePlayStatusPoll(id);
        schedulePlayLogsPoll(id,playStatusFor(id));
        await refreshProjectPlayNotifications(id);
        void showProjectPlayLogs(id,{render:true}).catch(()=>{});
        renderCurrentOpsView();
      }finally{
        delete OPS.playBusyByProject[id];
        renderCurrentOpsView();
      }
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

    function playOpenDelay(ms){
      return new Promise(resolve=>{
        const timer=(windowRef&&windowRef.setTimeout)||setTimeout;
        timer(resolve,ms);
      });
    }

    function playStatusReadyUrl(status){
      const url=typeof playInspectOverlayUrl==='function'?playInspectOverlayUrl({inspectUrl:status&&status.inspectUrl}):'';
      const state=String(status&&status.status||'').toLowerCase();
      return url&&(status&&status.ready===true||state==='ready')?url:'';
    }

    function playStatusCanBuild(status){
      if(!status)return false;
      return playStatusConfigured(status)&&playStatusValid(status);
    }

    function playNotificationStartPayload(note,target){
      const cleanTarget={
        projectId:String(target&&target.projectId||''),
        runId:String(target&&target.runId||''),
        taskId:String(target&&target.taskId||''),
        sessionId:String(target&&target.sessionId||''),
      };
      return {
        runId:cleanTarget.runId,
        taskId:cleanTarget.taskId,
        sessionId:cleanTarget.sessionId,
        terminalTarget:cleanTarget,
        notificationId:String(note&&note.id||''),
      };
    }

    async function waitForPlayReadyUrl(projectId,initialStatus){
      let status=initialStatus||null;
      for(let attempt=0;attempt<90;attempt+=1){
        const url=playStatusReadyUrl(status);
        if(url)return url;
        const state=String(status&&status.status||'').toLowerCase();
        if(status&&(state==='failed'||state==='stopped'))return '';
        if(attempt>0)await playOpenDelay(2000);
        status=await refreshProjectPlayStatus(projectId,{render:true});
      }
      return '';
    }

    async function showPlayOpenFailure(projectId,status){
      const state=String(status&&status.status||'').toLowerCase();
      if(state==='failed'){
        await showProjectPlayLogs(projectId).catch(()=>null);
        showToast('Play build failed. Opened logs for details.',3600);
      }else{
        showToast('Play is still building. Open it from the project when it is ready.',3600);
      }
    }

    async function openPlayNotification(notificationId){
      const id=String(notificationId||'').trim();
      const note=typeof notificationById==='function'?notificationById(id):null;
      const directUrl=typeof playInspectOverlayUrl==='function'?playInspectOverlayUrl(note||{}):'';
      if(directUrl){
        windowRef.location.assign(directUrl);
        return;
      }
      const target=typeof notificationTarget==='function'?notificationTarget(note):{};
      const projectId=String(target&&target.projectId||note&&note.project_id||'').trim();
      if(!projectId){
        showToast('Project metadata is missing for this Play notification.',3200);
        return;
      }
      let status=await refreshProjectPlayStatus(projectId,{render:true});
      let url=playStatusReadyUrl(status);
      if(url){
        windowRef.location.assign(url);
        return;
      }
      if(!playStatusCanBuild(status)){
        if(typeof openProjectDetail==='function')await openProjectDetail(projectId);
        showToast('Play is not configured correctly for this project. Add or fix the project Play config in the repository, then try Build again.',4200);
        return;
      }
      const state=String(status&&status.status||'').toLowerCase();
      const running=!!(status&&(status.running||['queued','building','starting'].includes(state)));
      if(!running){
        OPS.playBusyByProject[projectId]='start';
        renderCurrentOpsView();
        try{
          const res=await AgentBridgeRef.play.start(projectId,playNotificationStartPayload(note,target));
          if(res&&res.status){
            status=res.status;
            OPS.playStatusByProject[projectId]=status;
          }
          clearProjectPlayNotifications(projectId);
          OPS.playLogsByProject[projectId]={text:'Loading Play logs...'};
          schedulePlayLogsPoll(projectId,playStatusFor(projectId));
          await refreshProjectPlayNotifications(projectId);
          void showProjectPlayLogs(projectId,{render:true}).catch(()=>{});
          showToast('Play pipeline started. Opening when ready…',2600);
        }finally{
          delete OPS.playBusyByProject[projectId];
          renderCurrentOpsView();
        }
      }else{
        showToast('Play is building. Opening when ready…',2600);
      }
      url=await waitForPlayReadyUrl(projectId,status);
      if(url){
        windowRef.location.assign(url);
        return;
      }
      const latest=await refreshProjectPlayStatus(projectId,{render:true}).catch(()=>status);
      await showPlayOpenFailure(projectId,latest||status);
    }

    async function showProjectPlayLogs(projectId,options){
      const id=String(projectId||'').trim();
      if(!id)return;
      const data=await AgentBridgeRef.play.logs(id,1200);
      OPS.playLogsByProject[id]=data||{text:''};
      if(data&&data.status)OPS.playStatusByProject[id]=data.status;
      schedulePlayLogsPoll(id,playStatusFor(id));
      if(!options||options.render!==false)renderCurrentOpsView();
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
      if(fallbackError){
        showToast(`Play handoff error: ${fallbackError}`,4200);
      }else{
        showToast('Review the Play logs and update the repository Play config if needed.',3600);
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
      renderProjectPlayControls,
      renderProjectPlayLogs,
      renderProjectRuntimeSnapshot,
      renderProjectRuntimeScreenshot,
      startProjectPlay,
      stopProjectPlay,
      restartProjectPlay,
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
      '/play/logs',
      '/play-config-file',
      '/runtime/snapshot',
      '/runtime/screenshot',
    ],
    actions:[
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

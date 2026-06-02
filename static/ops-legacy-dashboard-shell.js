(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};

  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const root=ctx&&ctx.root;
    const layout=ctx&&ctx.layout;
    const navBtn=ctx&&ctx.navBtn;
    const esc=ctx&&ctx.esc;
    const documentRef=(ctx&&ctx.documentRef)||document;
    const windowRef=(ctx&&ctx.windowRef)||window;
    const syncTopbarRef=ctx&&ctx.syncTopbarRef;
    const renderHomeRef=ctx&&ctx.renderHomeRef;
    const loadDashboardHomeRef=ctx&&ctx.loadDashboardHomeRef;
    const renderProjectsRef=ctx&&ctx.renderProjectsRef;
    const renderProjectDetailRef=ctx&&ctx.renderProjectDetailRef;
    const renderDeploymentsRef=ctx&&ctx.renderDeploymentsRef;
    const startNotificationPollingRef=ctx&&ctx.startNotificationPollingRef;
    const stopNotificationPollingRef=ctx&&ctx.stopNotificationPollingRef;
    const stopPlayStatusPollingRef=ctx&&ctx.stopPlayStatusPollingRef;
    const stopQuickTaskDictationRef=ctx&&ctx.stopQuickTaskDictationRef;
    const setBusy=ctx&&ctx.setBusy;
    const OPS_HISTORY_MARKER='hermesOpsLegacyDashboard';
    if(!OPS||typeof root!=='function'||typeof layout!=='function'||typeof navBtn!=='function'||typeof esc!=='function'){
      return {};
    }

    function standaloneHistoryEnabled(){
      return !!(
        windowRef
        && windowRef.__OPS_LEGACY_STANDALONE__
        && windowRef.history
        && typeof windowRef.history.replaceState==='function'
      );
    }

    function normalizeHistoryState(state){
      if(!state||state[OPS_HISTORY_MARKER]!==true)return null;
      const view=String(state.view||'').trim();
      if(view==='project-detail'){
        const projectId=String(state.projectId||'').trim();
        if(!projectId)return {view:'projects',projectId:''};
        return {view,projectId};
      }
      if(view==='projects'||view==='deployments')return {view,projectId:''};
      return {view:'home',projectId:''};
    }

    function currentHistoryUrl(){
      if(!windowRef||!windowRef.location)return '';
      return String(windowRef.location.pathname||'')
        + String(windowRef.location.search||'')
        + String(windowRef.location.hash||'');
    }

    function syncHistoryState(view,projectId,options){
      if(!standaloneHistoryEnabled())return null;
      const opts=options&&typeof options==='object'?options:{};
      const rawView=String(view||'').trim();
      const normalizedView=rawView==='project-detail'
        ? 'project-detail'
        : (rawView==='projects'||rawView==='deployments'?rawView:'home');
      const normalizedProjectId=normalizedView==='project-detail'?String(projectId||'').trim():'';
      const nextState={
        [OPS_HISTORY_MARKER]:true,
        view:normalizedView,
        projectId:normalizedProjectId,
      };
      const current=normalizeHistoryState(windowRef.history.state);
      const mode=opts.mode==='push'?'push':'replace';
      if(current&&current.view===nextState.view&&current.projectId===nextState.projectId){
        if(mode==='replace'){
          windowRef.history.replaceState(nextState,'',currentHistoryUrl());
        }
        return nextState;
      }
      if(mode==='push'&&typeof windowRef.history.pushState==='function'){
        windowRef.history.pushState(nextState,'',currentHistoryUrl());
      }else{
        windowRef.history.replaceState(nextState,'',currentHistoryUrl());
      }
      return nextState;
    }

    if(windowRef){
      windowRef.__opsLegacyReadHistoryState=normalizeHistoryState;
      windowRef.__opsLegacySyncHistoryState=syncHistoryState;
      if(!windowRef.__opsLegacyHistoryListenerBound&&typeof windowRef.addEventListener==='function'){
        windowRef.addEventListener('popstate',event=>{
          if(typeof windowRef.__opsLegacyHandleHistoryState!=='function')return;
          const state=normalizeHistoryState(event&&event.state);
          if(!state)return;
          try{
            const result=windowRef.__opsLegacyHandleHistoryState(state);
            if(result&&typeof result.catch==='function')result.catch(()=>{});
          }catch(_error){}
        });
        windowRef.__opsLegacyHistoryListenerBound=true;
      }
    }

    function setDashboardTopbar(title,meta){
      const titleEl=documentRef&&documentRef.getElementById?documentRef.getElementById('topbarTitle'):null;
      const metaEl=documentRef&&documentRef.getElementById?documentRef.getElementById('topbarMeta'):null;
      if(titleEl)titleEl.textContent=title;
      if(metaEl)metaEl.textContent=meta||'';
      if(documentRef)documentRef.title=title+' - '+((windowRef&&windowRef._botName)||'Hermes');
    }

    function setActiveNav(){
      if(!documentRef||typeof documentRef.querySelectorAll!=='function')return;
      const active=navBtn();
      documentRef.querySelectorAll('.nav-tab').forEach((tab)=>tab.classList.toggle('active',tab===active));
    }

    function openOpsDashboard(options){
      const opts=options&&typeof options==='object'?options:{};
      if(standaloneHistoryEnabled()&&opts.historyMode!=='skip'){
        const mode=opts.historyMode==='push'
          ? 'push'
          : (windowRef&&windowRef._opsDashboardOpen?'push':'replace');
        syncHistoryState('home','',{mode});
      }
      OPS.view='home';
      OPS.showCreate=false;
      OPS.currentProject=null;
      OPS.taskData=null;
      OPS.taskDataByProject={};
      OPS.runs=[];
      OPS.runsByProject={};
      OPS.selectedRunId='';
      OPS.runDetail=null;
      OPS.runReadableOutput=null;
      OPS.runEvents=null;
      OPS.runRequests=null;
      OPS.runArtifacts=null;
      OPS.runLogs=null;
      OPS.artifactHealth=null;
      OPS.artifactHealthBusy=false;
      windowRef._opsDashboardOpen=true;
      const layoutEl=layout();
      if(layoutEl)layoutEl.classList.add('ops-dashboard-active');
      const el=root();
      if(el)el.hidden=false;
      setActiveNav();
      if(typeof setBusy==='function')setBusy(true);
      const renderHome=typeof renderHomeRef==='function'?renderHomeRef():null;
      if(typeof renderHome==='function')renderHome();
      const startNotificationPolling=typeof startNotificationPollingRef==='function'?startNotificationPollingRef():null;
      if(typeof startNotificationPolling==='function')startNotificationPolling();
      const loadDashboardHome=typeof loadDashboardHomeRef==='function'?loadDashboardHomeRef():null;
      if(typeof loadDashboardHome==='function')void loadDashboardHome();
    }

    function closeOpsDashboard(){
      if(
        windowRef
        && windowRef.__OPS_LEGACY_STANDALONE__
        && windowRef.S
        && windowRef.S.session
        && windowRef.S.session.session_id
        && typeof windowRef.__opsLegacySessionUrlForSid==='function'
      ){
        try{windowRef.sessionStorage.setItem('hermes-webui-ops-session-inspect', String(windowRef.S.session.session_id));}catch(_){}
        windowRef.location.assign(windowRef.__opsLegacySessionUrlForSid(windowRef.S.session.session_id));
        return;
      }
      if(
        windowRef
        && windowRef.__OPS_LEGACY_STANDALONE__
        && typeof windowRef.__opsLegacyAppUrl==='function'
      ){
        windowRef.location.assign(windowRef.__opsLegacyAppUrl('./'));
        return;
      }
      windowRef._opsDashboardOpen=false;
      const layoutEl=layout();
      if(layoutEl)layoutEl.classList.remove('ops-dashboard-active');
      const el=root();
      if(el)el.hidden=true;
      const tab=navBtn();
      if(tab)tab.classList.remove('active');
      const syncTopbar=typeof syncTopbarRef==='function'?syncTopbarRef():null;
      if(typeof syncTopbar==='function')syncTopbar();
      const stopNotificationPolling=typeof stopNotificationPollingRef==='function'?stopNotificationPollingRef():null;
      if(typeof stopNotificationPolling==='function')stopNotificationPolling();
      const stopPlayStatusPolling=typeof stopPlayStatusPollingRef==='function'?stopPlayStatusPollingRef():null;
      if(typeof stopPlayStatusPolling==='function')stopPlayStatusPolling();
      if(OPS.quickTaskDictationActive||OPS.quickTaskDictationRecorder||OPS.quickTaskDictationStream){
        const stopQuickTaskDictation=typeof stopQuickTaskDictationRef==='function'?stopQuickTaskDictationRef():null;
        if(typeof stopQuickTaskDictation==='function'){
          stopQuickTaskDictation({updateStatus:false,discard:true});
        }
      }
    }

    function renderCurrentOpsView(){
      if(!windowRef._opsDashboardOpen)return;
      if(OPS.view==='home'){
        const renderHome=typeof renderHomeRef==='function'?renderHomeRef():null;
        if(typeof renderHome==='function')renderHome();
      }else if(OPS.view==='projects'){
        const renderProjects=typeof renderProjectsRef==='function'?renderProjectsRef():null;
        if(typeof renderProjects==='function')renderProjects();
      }else if(OPS.view==='deployments'){
        const renderDeployments=typeof renderDeploymentsRef==='function'?renderDeploymentsRef():null;
        if(typeof renderDeployments==='function')renderDeployments();
      }else if(OPS.view==='project-detail'){
        const renderProjectDetail=typeof renderProjectDetailRef==='function'?renderProjectDetailRef():null;
        if(typeof renderProjectDetail==='function')renderProjectDetail();
      }
    }

    function renderLoading(label){
      const el=root();
      if(el)el.innerHTML=`<div class="ops-dashboard"><div class="ops-empty">${esc(label||'Loading...')}</div></div>`;
    }

    return {
      setDashboardTopbar,
      setActiveNav,
      openOpsDashboard,
      closeOpsDashboard,
      renderCurrentOpsView,
      renderLoading,
    };
  }

  window.HermesOpsModules.dashboardShell={bindDashboard};
})();

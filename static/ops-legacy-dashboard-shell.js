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
    const startNotificationPollingRef=ctx&&ctx.startNotificationPollingRef;
    const stopNotificationPollingRef=ctx&&ctx.stopNotificationPollingRef;
    const stopPlayStatusPollingRef=ctx&&ctx.stopPlayStatusPollingRef;
    const stopQuickTaskDictationRef=ctx&&ctx.stopQuickTaskDictationRef;
    const setBusy=ctx&&ctx.setBusy;
    if(!OPS||typeof root!=='function'||typeof layout!=='function'||typeof navBtn!=='function'||typeof esc!=='function'){
      return {};
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

    function openOpsDashboard(){
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
      OPS.playConfigEditingProjectId='';
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

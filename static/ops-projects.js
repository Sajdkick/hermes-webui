(function(){
  const apiBase='/api/ops/projects';

  function escapeHtml(value){
    return String(value||'')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  function appUrl(path){
    const raw=String(path||'').trim();
    const base=(typeof document!=='undefined' && document.baseURI)
      || (typeof location!=='undefined' && location.href)
      || '';
    if(!raw) return base || '/';
    if(/^[a-z]+:/i.test(raw) || raw.startsWith('//')) return raw;
    const rel=raw.startsWith('/') ? raw.slice(1) : raw;
    if(!base) return raw.startsWith('/') ? raw : '/'+raw;
    try{return new URL(rel, base).href;}catch(_error){return raw.startsWith('/') ? raw : '/'+raw;}
  }

  function captureLogScrollState(container){
    const snapshot={};
    if(!container||typeof container.querySelectorAll!=='function')return snapshot;
    container.querySelectorAll('[data-ops-log-scroll-key]').forEach(function(node){
      const key=String(node && node.dataset && node.dataset.opsLogScrollKey || '').trim();
      if(!key)return;
      const maxScroll=Math.max(0,(node.scrollHeight||0)-(node.clientHeight||0));
      snapshot[key]={top:Number(node.scrollTop)||0,atBottom:maxScroll-(Number(node.scrollTop)||0)<=8};
    });
    return snapshot;
  }

  function restoreLogScrollState(container,snapshot){
    if(!container||!snapshot||typeof container.querySelectorAll!=='function')return;
    const apply=function(){
      container.querySelectorAll('[data-ops-log-scroll-key]').forEach(function(node){
        const key=String(node && node.dataset && node.dataset.opsLogScrollKey || '').trim();
        const entry=key?snapshot[key]:null;
        if(!entry)return;
        const maxScroll=Math.max(0,(node.scrollHeight||0)-(node.clientHeight||0));
        node.scrollTop=entry.atBottom?maxScroll:Math.min(Number(entry.top)||0,maxScroll);
      });
    };
    apply();
    if(typeof requestAnimationFrame==='function')requestAnimationFrame(apply);
  }

  function mount(root,shellPayload){
    const state={
      shellPayload:shellPayload||{},
      projectsOpen:false,
      loadingProjects:false,
      creatingProject:false,
      loadingRuns:false,
      runs:[],
      runsError:'',
      loadingDatabaseSettings:false,
      databaseSettings:null,
      databaseTables:[],
      databaseQueryResult:null,
      databaseError:'',
      databaseBusyAction:'',
      loadingGitHubStatus:false,
      githubStatus:null,
      loadingGitHubRepos:false,
      githubRepos:[],
      githubBranchesByRepo:{},
      githubError:'',
      githubQuery:'',
      githubLoadingBranchesKey:'',
      githubImportingRepoKey:'',
      githubLastImport:null,
      loadingProfiles:false,
      availableProfiles:[],
      profilesError:'',
      savingProjectDefaults:false,
      projects:[],
      error:'',
      selectedProjectId:'',
      loadingTasks:false,
      tasksData:null,
      filterText:'',
      filterStatus:'all',
      filterGrade:'all',
      launchingTaskId:'',
      loadingRuntimeSummary:false,
      runtimeSummary:null,
      runtimeError:'',
      loadingGitStatus:false,
      gitStatus:null,
      gitError:'',
      loadingProjectDatabase:false,
      projectDatabase:null,
      projectDatabaseTables:[],
      projectDatabaseQueryResult:null,
      projectDatabaseError:'',
      projectDatabaseBusyAction:'',
      loadingUpstreamSync:false,
      upstreamSync:null,
      upstreamSyncRecords:[],
      upstreamSyncError:'',
      upstreamSyncBusyAction:'',
      inspectError:'',
      inspectBusyAction:'',
      playLogs:null,
      loadingPlayLogs:false,
      playError:'',
      playBusyAction:'',
      showPlayLogs:false,
      loadingNotifications:false,
      notifications:[],
      notificationsError:'',
      respondingNotificationKey:'',
      taskAutomationBusyAction:'',
    };

    root.addEventListener('click',function(event){
      const action=event.target.closest('[data-ops-action]');
      if(!action)return;
      const kind=action.getAttribute('data-ops-action');
      if(kind==='toggle-projects'){
        state.projectsOpen=!state.projectsOpen;
        render(root,state);
        if(state.projectsOpen){
          if(!state.projects.length)loadProjects(root,state);
          if(!state.availableProfiles.length && !state.loadingProfiles)loadProfiles(root,state);
        }
        return;
      }
      if(kind==='close-projects'){
        state.projectsOpen=false;
        render(root,state);
        return;
      }
      if(kind==='select-project'){
        state.selectedProjectId=action.getAttribute('data-project-id')||'';
        state.gitStatus=null;
        state.gitError='';
        state.playLogs=null;
        state.playError='';
        state.projectDatabase=null;
        state.projectDatabaseTables=[];
        state.projectDatabaseQueryResult=null;
        state.projectDatabaseError='';
        state.projectDatabaseBusyAction='';
        state.upstreamSync=null;
        state.upstreamSyncRecords=[];
        state.upstreamSyncError='';
        state.upstreamSyncBusyAction='';
        state.inspectError='';
        state.inspectBusyAction='';
        state.showPlayLogs=false;
        loadTasks(root,state);
        loadGitStatus(root,state);
        loadProjectDatabase(root,state);
        loadUpstreamSync(root,state);
        loadRuntimeSummary(root,state);
        return;
      }
      if(kind==='refresh-projects'){
        loadProjects(root,state,true);
        return;
      }
      if(kind==='execute-ready-tasks'){
        executeReadyTasks(root,state);
        return;
      }
      if(kind==='refresh-runs'){
        if(!(window.HermesOpsRuns && typeof window.HermesOpsRuns.renderSection==='function'))return;
        loadRuns(root,state);
        return;
      }
      if(kind==='refresh-database'){
        loadDatabaseSettings(root,state);
        return;
      }
      if(kind==='test-database'){
        testDatabase(root,state);
        return;
      }
      if(kind==='inspect-database'){
        inspectDatabaseTables(root,state);
        return;
      }
      if(kind==='refresh-project-database'){
        loadProjectDatabase(root,state);
        return;
      }
      if(kind==='test-project-database'){
        testProjectDatabase(root,state);
        return;
      }
      if(kind==='inspect-project-database'){
        inspectProjectDatabase(root,state);
        return;
      }
      if(kind==='refresh-github-status'){
        loadGitHubStatus(root,state);
        return;
      }
      if(kind==='github-load-branches'){
        loadGitHubBranches(root,state,action.getAttribute('data-owner')||'',action.getAttribute('data-repo')||'');
        return;
      }
      if(kind==='github-import-repo'){
        importGitHubRepository(root,state,{
          owner:action.getAttribute('data-owner')||'',
          repo:action.getAttribute('data-repo')||'',
          branch:action.getAttribute('data-branch')||'',
          projectName:action.getAttribute('data-project-name')||'',
        });
        return;
      }
      if(kind==='refresh-notifications'){
        loadNotifications(root,state);
        return;
      }
      if(kind==='refresh-upstream-sync'){
        loadUpstreamSync(root,state);
        return;
      }
      if(kind==='start-upstream-sync'){
        startUpstreamSync(root,state);
        return;
      }
      if(kind==='apply-upstream-sync'){
        applyUpstreamSync(root,state);
        return;
      }
      if(kind==='refresh-runtime'){
        loadRuntimeSummary(root,state);
        return;
      }
      if(kind==='refresh-git-status'){
        loadGitStatus(root,state);
        return;
      }
      if(kind==='run-inspect-url'){
        runInspectSnapshot(root,state,false);
        return;
      }
      if(kind==='reset-inspect-state'){
        runInspectSnapshot(root,state,true);
        return;
      }
      if(kind==='refresh-play'){
        loadRuntimeSummary(root,state);
        return;
      }
      if(kind==='show-play-logs'){
        loadPlayLogs(root,state,true);
        return;
      }
      if(kind==='close-play-logs'){
        state.showPlayLogs=false;
        render(root,state);
        return;
      }
      if(kind==='start-play' || kind==='restart-play' || kind==='stop-play'){
        runPlayAction(root,state,kind.replace('-play',''));
        return;
      }
      if(kind==='open-play'){
        openPlay(root,state);
        return;
      }
      if(kind==='launch-task-session'){
        launchTaskSession(root,state,action.getAttribute('data-task-id')||'');
        return;
      }
      if(kind==='respond-notification'){
        respondNotification(root,state,{
          notificationKey:action.getAttribute('data-notification-key')||'',
          kind:action.getAttribute('data-notification-kind')||'',
          sessionId:action.getAttribute('data-session-id')||'',
          approvalId:action.getAttribute('data-approval-id')||'',
          choice:action.getAttribute('data-choice')||'',
          response:action.getAttribute('data-response')||'',
        });
        return;
      }
    });

    root.addEventListener('submit',function(event){
      const form=event.target;
      if(!(form instanceof HTMLFormElement))return;
      if(form.matches('[data-ops-form="create-project"]')){
        event.preventDefault();
        createProject(root,state,new FormData(form));
        return;
      }
      if(form.matches('[data-ops-form="project-defaults"]')){
        event.preventDefault();
        saveProjectDefaults(root,state,new FormData(form));
        return;
      }
      if(form.matches('[data-ops-form="database-settings"]')){
        event.preventDefault();
        saveDatabaseSettings(root,state,new FormData(form));
        return;
      }
      if(form.matches('[data-ops-form="database-query"]')){
        event.preventDefault();
        runDatabaseQuery(root,state,new FormData(form));
        return;
      }
      if(form.matches('[data-ops-form="project-database-settings"]')){
        event.preventDefault();
        saveProjectDatabaseSettings(root,state,new FormData(form));
        return;
      }
      if(form.matches('[data-ops-form="project-database-query"]')){
        event.preventDefault();
        runProjectDatabaseQuery(root,state,new FormData(form));
        return;
      }
      if(form.matches('[data-ops-form="github-search"]')){
        event.preventDefault();
        searchGitHubRepos(root,state,new FormData(form));
        return;
      }
      if(form.matches('[data-ops-form="create-epic"]')){
        event.preventDefault();
        createEpic(root,state,new FormData(form));
        return;
      }
      if(form.matches('[data-ops-form="create-task"]')){
        event.preventDefault();
        createTask(root,state,new FormData(form));
        return;
      }
      if(form.matches('[data-ops-form="quick-task"]')){
        event.preventDefault();
        createQuickTask(root,state,new FormData(form));
        return;
      }
      if(form.matches('[data-ops-form="clarify-response"]')){
        event.preventDefault();
        const formData=new FormData(form);
        respondNotification(root,state,{
          notificationKey:formData.get('notificationKey'),
          kind:'clarify',
          sessionId:formData.get('sessionId'),
          response:formData.get('response'),
        });
        return;
      }
      if(form.matches('[data-ops-form="runtime-screenshot"]')){
        event.preventDefault();
        runInspectScreenshot(root,state,new FormData(form));
        return;
      }
      if(form.matches('[data-ops-form="runtime-action"]')){
        event.preventDefault();
        runInspectAction(root,state,new FormData(form));
      }
    });

    root.addEventListener('change',function(event){
      const target=event.target;
      if(!(target instanceof HTMLElement))return;
      if(target.matches('[data-ops-task-toggle]') && target instanceof HTMLInputElement){
        updateTask(root,state,target.getAttribute('data-task-id')||'',{done:target.checked});
        return;
      }
      if(target.matches('[data-ops-filter="status"]') || target.matches('[data-ops-filter="grade"]')){
        state.filterStatus=getFilterValue(root,'status','all');
        state.filterGrade=getFilterValue(root,'grade','all');
        render(root,state);
      }
    });

    root.addEventListener('input',function(event){
      const target=event.target;
      if(!(target instanceof HTMLElement))return;
      if(target.matches('[data-ops-filter="text"]')){
        state.filterText=getFilterValue(root,'text','');
        render(root,state);
      }
    });

    render(root,state);
    loadNotifications(root,state);
    if(window.HermesOpsRuns && typeof window.HermesOpsRuns.renderSection==='function'){
      loadRuns(root,state);
    }
    if(window.HermesOpsDatabase && typeof window.HermesOpsDatabase.renderGlobalSection==='function'){
      loadDatabaseSettings(root,state);
    }
    if(window.HermesOpsGitHubAdmin && typeof window.HermesOpsGitHubAdmin.renderSection==='function'){
      loadGitHubStatus(root,state);
    }
  }

  async function api(path,options){
    const requestOptions={credentials:'same-origin',headers:{}};
    if(options && options.method)requestOptions.method=options.method;
    if(options && options.body!==undefined){
      requestOptions.headers['Content-Type']='application/json';
      requestOptions.body=JSON.stringify(options.body||{});
    }
    const response=await fetch(appUrl(path),requestOptions);
    const payload=await response.json().catch(function(){return {};});
    if(!response.ok){
      const message=payload && payload.error ? payload.error : 'Request failed with status '+response.status;
      throw new Error(message);
    }
    return payload;
  }

  async function loadProjects(root,state,keepSelection){
    state.loadingProjects=true;
    state.error='';
    render(root,state);
    try{
      const payload=await api(apiBase);
      state.projects=Array.isArray(payload.projects)?payload.projects:[];
      if(!keepSelection || !state.projects.some(function(project){return project.id===state.selectedProjectId;})){
        state.selectedProjectId=state.projects.length ? String(state.projects[0].id||'') : '';
      }
      state.loadingProjects=false;
      render(root,state);
      if(state.selectedProjectId){
        loadTasks(root,state);
        loadGitStatus(root,state);
        loadProjectDatabase(root,state);
        loadUpstreamSync(root,state);
        loadRuntimeSummary(root,state);
      }
    }catch(error){
      state.loadingProjects=false;
      state.error=error && error.message ? error.message : 'Could not load projects.';
      render(root,state);
    }
  }

  async function loadProfiles(root,state){
    state.loadingProfiles=true;
    state.profilesError='';
    render(root,state);
    try{
      const payload=await api('/api/profiles');
      state.availableProfiles=Array.isArray(payload.profiles)?payload.profiles:[];
    }catch(error){
      state.profilesError=error && error.message ? error.message : 'Could not load profiles.';
    }finally{
      state.loadingProfiles=false;
      render(root,state);
    }
  }

  async function loadRuns(root,state){
    state.loadingRuns=true;
    state.runsError='';
    render(root,state);
    try{
      const payload=await api('/api/ops/runs');
      state.runs=Array.isArray(payload.runs)?payload.runs:[];
    }catch(error){
      state.runs=[];
      state.runsError=error && error.message ? error.message : 'Could not load run activity.';
    }finally{
      state.loadingRuns=false;
      render(root,state);
    }
  }

  async function loadDatabaseSettings(root,state){
    state.loadingDatabaseSettings=true;
    state.databaseBusyAction='refresh';
    state.databaseError='';
    render(root,state);
    try{
      const payload=await api('/api/ops/database/settings');
      state.databaseSettings=payload;
    }catch(error){
      state.databaseSettings=null;
      state.databaseError=error && error.message ? error.message : 'Could not load database settings.';
    }finally{
      state.loadingDatabaseSettings=false;
      state.databaseBusyAction='';
      render(root,state);
    }
  }

  async function saveDatabaseSettings(root,state,formData){
    state.databaseBusyAction='save';
    state.databaseError='';
    render(root,state);
    try{
      await api('/api/ops/database/settings',{
        method:'POST',
        body:{
          path:formData.get('path'),
          label:formData.get('label'),
          mode:formData.get('mode'),
        },
      });
      await loadDatabaseSettings(root,state);
    }catch(error){
      state.databaseBusyAction='';
      state.databaseError=error && error.message ? error.message : 'Could not save database settings.';
      render(root,state);
    }
  }

  async function testDatabase(root,state){
    state.databaseBusyAction='test';
    state.databaseError='';
    render(root,state);
    try{
      await api('/api/ops/database/test',{method:'POST',body:{}});
    }catch(error){
      state.databaseError=error && error.message ? error.message : 'Could not test database connection.';
    }finally{
      state.databaseBusyAction='';
      render(root,state);
    }
  }

  async function inspectDatabaseTables(root,state){
    state.databaseBusyAction='inspect';
    state.databaseError='';
    render(root,state);
    try{
      const payload=await api('/api/ops/database/inspect/tables');
      state.databaseTables=Array.isArray(payload.tables)?payload.tables:[];
    }catch(error){
      state.databaseTables=[];
      state.databaseError=error && error.message ? error.message : 'Could not inspect database tables.';
    }finally{
      state.databaseBusyAction='';
      render(root,state);
    }
  }

  async function runDatabaseQuery(root,state,formData){
    state.databaseBusyAction='query';
    state.databaseError='';
    render(root,state);
    try{
      state.databaseQueryResult=await api('/api/ops/database/inspect/query',{
        method:'POST',
        body:{
          query:formData.get('query'),
          limit:formData.get('limit'),
        },
      });
    }catch(error){
      state.databaseQueryResult=null;
      state.databaseError=error && error.message ? error.message : 'Could not run the database query.';
    }finally{
      state.databaseBusyAction='';
      render(root,state);
    }
  }

  async function loadTasks(root,state){
    if(!state.selectedProjectId)return;
    state.loadingTasks=true;
    state.error='';
    render(root,state);
    try{
      state.tasksData=await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/tasks');
    }catch(error){
      state.error=error && error.message ? error.message : 'Could not load project tasks.';
    }finally{
      state.loadingTasks=false;
      render(root,state);
    }
  }

  async function loadRuntimeSummary(root,state){
    if(!state.selectedProjectId){
      state.runtimeSummary=null;
      state.runtimeError='';
      state.loadingRuntimeSummary=false;
      render(root,state);
      return;
    }
    state.loadingRuntimeSummary=true;
    state.runtimeError='';
    render(root,state);
    try{
      state.runtimeSummary=await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/runtime/summary');
      state.playError='';
      state.inspectError='';
    }catch(error){
      state.runtimeSummary=null;
      state.runtimeError=error && error.message ? error.message : 'Could not load runtime evidence.';
    }finally{
      state.loadingRuntimeSummary=false;
      render(root,state);
    }
  }

  async function loadGitStatus(root,state){
    if(!state.selectedProjectId){
      state.gitStatus=null;
      state.gitError='';
      state.loadingGitStatus=false;
      render(root,state);
      return;
    }
    state.loadingGitStatus=true;
    state.gitStatus=null;
    state.gitError='';
    render(root,state);
    try{
      const payload=await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/git/status');
      state.gitStatus=payload && payload.git ? payload.git : payload;
    }catch(error){
      state.gitStatus=null;
      state.gitError=error && error.message ? error.message : 'Could not load project git status.';
    }finally{
      state.loadingGitStatus=false;
      render(root,state);
    }
  }

  async function loadProjectDatabase(root,state){
    if(!state.selectedProjectId){
      state.projectDatabase=null;
      state.projectDatabaseTables=[];
      state.projectDatabaseQueryResult=null;
      state.projectDatabaseError='';
      state.loadingProjectDatabase=false;
      render(root,state);
      return;
    }
    state.loadingProjectDatabase=true;
    state.projectDatabaseBusyAction='refresh';
    state.projectDatabaseError='';
    render(root,state);
    try{
      state.projectDatabase=await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/database/settings');
    }catch(error){
      state.projectDatabase=null;
      state.projectDatabaseError=error && error.message ? error.message : 'Could not load project database settings.';
    }finally{
      state.loadingProjectDatabase=false;
      state.projectDatabaseBusyAction='';
      render(root,state);
    }
  }

  async function saveProjectDatabaseSettings(root,state,formData){
    if(!state.selectedProjectId)return;
    state.projectDatabaseBusyAction='save';
    state.projectDatabaseError='';
    render(root,state);
    try{
      await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/database/settings',{
        method:'POST',
        body:{
          path:formData.get('path'),
          label:formData.get('label'),
          mode:formData.get('mode'),
        },
      });
      await loadProjectDatabase(root,state);
    }catch(error){
      state.projectDatabaseBusyAction='';
      state.projectDatabaseError=error && error.message ? error.message : 'Could not save project database settings.';
      render(root,state);
    }
  }

  async function testProjectDatabase(root,state){
    if(!state.selectedProjectId)return;
    state.projectDatabaseBusyAction='test';
    state.projectDatabaseError='';
    render(root,state);
    try{
      await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/database/test',{method:'POST',body:{}});
    }catch(error){
      state.projectDatabaseError=error && error.message ? error.message : 'Could not test the project database.';
    }finally{
      state.projectDatabaseBusyAction='';
      render(root,state);
    }
  }

  async function inspectProjectDatabase(root,state){
    if(!state.selectedProjectId)return;
    state.projectDatabaseBusyAction='inspect';
    state.projectDatabaseError='';
    render(root,state);
    try{
      const payload=await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/database/inspect/tables');
      state.projectDatabaseTables=Array.isArray(payload.tables)?payload.tables:[];
    }catch(error){
      state.projectDatabaseTables=[];
      state.projectDatabaseError=error && error.message ? error.message : 'Could not inspect the project database.';
    }finally{
      state.projectDatabaseBusyAction='';
      render(root,state);
    }
  }

  async function runProjectDatabaseQuery(root,state,formData){
    if(!state.selectedProjectId)return;
    state.projectDatabaseBusyAction='query';
    state.projectDatabaseError='';
    render(root,state);
    try{
      state.projectDatabaseQueryResult=await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/database/inspect/query',{
        method:'POST',
        body:{
          query:formData.get('query'),
          limit:formData.get('limit'),
        },
      });
    }catch(error){
      state.projectDatabaseQueryResult=null;
      state.projectDatabaseError=error && error.message ? error.message : 'Could not run the project database query.';
    }finally{
      state.projectDatabaseBusyAction='';
      render(root,state);
    }
  }

  async function loadGitHubStatus(root,state){
    state.loadingGitHubStatus=true;
    state.githubError='';
    render(root,state);
    try{
      state.githubStatus=await api('/api/ops/github/status');
    }catch(error){
      state.githubStatus=null;
      state.githubError=error && error.message ? error.message : 'Could not load GitHub status.';
    }finally{
      state.loadingGitHubStatus=false;
      render(root,state);
    }
  }

  async function searchGitHubRepos(root,state,formData){
    state.loadingGitHubRepos=true;
    state.githubError='';
    state.githubQuery=String(formData.get('query')||'').trim();
    render(root,state);
    try{
      const query=encodeURIComponent(state.githubQuery);
      const limit=encodeURIComponent(String(formData.get('limit')||'10').trim()||'10');
      const payload=await api('/api/ops/github/repos?q='+query+'&limit='+limit);
      state.githubRepos=Array.isArray(payload.repositories)?payload.repositories:[];
    }catch(error){
      state.githubRepos=[];
      state.githubError=error && error.message ? error.message : 'Could not search GitHub repositories.';
    }finally{
      state.loadingGitHubRepos=false;
      render(root,state);
    }
  }

  async function loadGitHubBranches(root,state,owner,repo){
    const key=String(owner||'').trim()+'/'+String(repo||'').trim();
    if(!owner || !repo)return;
    state.githubLoadingBranchesKey=key;
    state.githubError='';
    state.githubBranchesByRepo[key]={loading:true,branches:[]};
    render(root,state);
    try{
      const payload=await api('/api/ops/github/repos/'+encodeURIComponent(owner)+'/'+encodeURIComponent(repo)+'/branches?limit=20');
      state.githubBranchesByRepo[key]={loading:false,branches:Array.isArray(payload.branches)?payload.branches:[]};
    }catch(error){
      state.githubBranchesByRepo[key]={loading:false,branches:[],error:error && error.message ? error.message : 'Could not load repository branches.'};
    }finally{
      state.githubLoadingBranchesKey='';
      render(root,state);
    }
  }

  async function importGitHubRepository(root,state,payload){
    const owner=String(payload && payload.owner || '').trim();
    const repo=String(payload && payload.repo || '').trim();
    const branch=String(payload && payload.branch || '').trim();
    const key=owner+'/'+repo+':'+branch;
    if(!owner || !repo || !branch)return;
    state.githubImportingRepoKey=key;
    state.githubError='';
    render(root,state);
    try{
      const result=await api('/api/ops/github/import',{
        method:'POST',
        body:{
          owner:owner,
          repo:repo,
          branch:branch,
          defaultBranch:branch,
          projectName:String(payload && payload.projectName || repo).trim() || repo,
        },
      });
      state.githubLastImport=result;
      state.projectsOpen=true;
      await loadProjects(root,state,true);
    }catch(error){
      state.githubError=error && error.message ? error.message : 'Could not import the GitHub repository.';
      state.githubImportingRepoKey='';
      render(root,state);
      return;
    }
    state.githubImportingRepoKey='';
    render(root,state);
  }

  async function loadUpstreamSync(root,state){
    if(!state.selectedProjectId){
      state.upstreamSync=null;
      state.upstreamSyncRecords=[];
      state.upstreamSyncError='';
      state.loadingUpstreamSync=false;
      render(root,state);
      return;
    }
    state.loadingUpstreamSync=true;
    state.upstreamSyncBusyAction='refresh';
    state.upstreamSyncError='';
    render(root,state);
    try{
      const payload=await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/upstream-sync');
      state.upstreamSync=payload && payload.sync ? payload.sync : null;
      state.upstreamSyncRecords=Array.isArray(payload.records)?payload.records:[];
    }catch(error){
      state.upstreamSync=null;
      state.upstreamSyncRecords=[];
      state.upstreamSyncError=error && error.message ? error.message : 'Could not load maintenance sync status.';
    }finally{
      state.loadingUpstreamSync=false;
      state.upstreamSyncBusyAction='';
      render(root,state);
    }
  }

  async function startUpstreamSync(root,state){
    if(!state.selectedProjectId)return;
    state.upstreamSyncBusyAction='start';
    state.upstreamSyncError='';
    render(root,state);
    try{
      await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/upstream-sync/start',{
        method:'POST',
        body:{},
      });
      await loadUpstreamSync(root,state);
    }catch(error){
      state.upstreamSyncBusyAction='';
      state.upstreamSyncError=error && error.message ? error.message : 'Could not start the maintenance session.';
      render(root,state);
    }
  }

  async function applyUpstreamSync(root,state){
    if(!state.selectedProjectId || !state.upstreamSync || !state.upstreamSync.recordId)return;
    state.upstreamSyncBusyAction='apply';
    state.upstreamSyncError='';
    render(root,state);
    try{
      await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/upstream-sync/apply',{
        method:'POST',
        body:{recordId:state.upstreamSync.recordId},
      });
      await loadUpstreamSync(root,state);
      await loadGitStatus(root,state);
    }catch(error){
      state.upstreamSyncBusyAction='';
      state.upstreamSyncError=error && error.message ? error.message : 'Could not apply the maintenance sync.';
      render(root,state);
    }
  }

  async function loadPlayLogs(root,state,showPanel){
    if(!state.selectedProjectId)return;
    state.loadingPlayLogs=true;
    if(showPanel)state.showPlayLogs=true;
    state.playError='';
    render(root,state);
    try{
      state.playLogs=await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/play/logs?limit=200');
    }catch(error){
      state.playError=error && error.message ? error.message : 'Could not load Play logs.';
    }finally{
      state.loadingPlayLogs=false;
      render(root,state);
    }
  }

  async function runInspectSnapshot(root,state,resetState){
    if(!state.selectedProjectId)return;
    state.inspectBusyAction=resetState ? 'reset-state' : 'inspect-url';
    state.inspectError='';
    render(root,state);
    try{
      await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/runtime/inspect/snapshot',{
        method:'POST',
        body:resetState ? {resetState:true} : {},
      });
      await loadRuntimeSummary(root,state);
    }catch(error){
      state.inspectError=error && error.message ? error.message : 'Could not resolve the inspect runtime state.';
      state.inspectBusyAction='';
      render(root,state);
      return;
    }
    state.inspectBusyAction='';
    render(root,state);
  }

  async function runInspectScreenshot(root,state,formData){
    if(!state.selectedProjectId)return;
    state.inspectBusyAction='screenshot';
    state.inspectError='';
    render(root,state);
    try{
      await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/runtime/inspect/screenshot',{
        method:'POST',
        body:{
          url:formData.get('url'),
          selector:formData.get('selector'),
          fileName:formData.get('fileName'),
        },
      });
      await loadRuntimeSummary(root,state);
    }catch(error){
      state.inspectError=error && error.message ? error.message : 'Could not capture a runtime screenshot.';
      state.inspectBusyAction='';
      render(root,state);
      return;
    }
    state.inspectBusyAction='';
    render(root,state);
  }

  async function runInspectAction(root,state,formData){
    if(!state.selectedProjectId)return;
    state.inspectBusyAction='action';
    state.inspectError='';
    render(root,state);
    try{
      await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/runtime/inspect/action',{
        method:'POST',
        body:{
          url:formData.get('url'),
          fileName:formData.get('fileName'),
          captureScreenshot:Boolean(formData.get('captureScreenshot')),
          script:formData.get('script'),
        },
      });
      await loadRuntimeSummary(root,state);
    }catch(error){
      state.inspectError=error && error.message ? error.message : 'Could not run runtime inspect actions.';
      state.inspectBusyAction='';
      render(root,state);
      return;
    }
    state.inspectBusyAction='';
    render(root,state);
  }

  async function runPlayAction(root,state,action){
    if(!state.selectedProjectId)return;
    state.playBusyAction=String(action||'');
    state.playError='';
    render(root,state);
    try{
      await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/play/'+encodeURIComponent(action),{
        method:'POST',
        body:{},
      });
      await loadRuntimeSummary(root,state);
      if(action==='start'||action==='restart'){
        await loadNotifications(root,state);
      }
      if(state.showPlayLogs && action!=='stop'){
        loadPlayLogs(root,state,false);
      }
    }catch(error){
      state.playError=error && error.message ? error.message : 'Could not update Play state.';
      state.playBusyAction='';
      render(root,state);
      return;
    }
    state.playBusyAction='';
    render(root,state);
  }

  function openPlay(root,state){
    const summary=state.runtimeSummary && state.runtimeSummary.play ? state.runtimeSummary.play : null;
    const target=summary && summary.inspectUrl ? String(summary.inspectUrl) : '';
    if(!target)return;
    if(typeof window!=='undefined' && window.location){
      const normalized=appUrl(target);
      if(typeof window.location.assign==='function'){
        window.location.assign(normalized);
        return;
      }
      window.location.href=normalized;
    }
  }

  async function createProject(root,state,formData){
    state.creatingProject=true;
    state.error='';
    render(root,state);
    try{
      await api(apiBase,{
        method:'POST',
        body:{
          name:formData.get('name'),
          path:formData.get('path'),
          coreBranch:formData.get('coreBranch'),
          profile:formData.get('profile'),
        }
      });
      state.creatingProject=false;
      loadProjects(root,state,true);
    }catch(error){
      state.creatingProject=false;
      state.error=error && error.message ? error.message : 'Could not create project.';
      render(root,state);
    }
  }

  async function saveProjectDefaults(root,state,formData){
    if(!state.selectedProjectId)return;
    state.savingProjectDefaults=true;
    state.error='';
    render(root,state);
    try{
      await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/update',{
        method:'POST',
        body:{
          profile:formData.get('profile'),
          defaultModel:formData.get('defaultModel'),
          defaultModelProvider:formData.get('defaultModelProvider'),
        }
      });
      state.savingProjectDefaults=false;
      loadProjects(root,state,true);
    }catch(error){
      state.savingProjectDefaults=false;
      state.error=error && error.message ? error.message : 'Could not save project defaults.';
      render(root,state);
    }
  }

  async function createEpic(root,state,formData){
    if(!state.selectedProjectId)return;
    state.error='';
    render(root,state);
    try{
      await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/epics',{
        method:'POST',
        body:{title:formData.get('title')}
      });
      loadTasks(root,state);
    }catch(error){
      state.error=error && error.message ? error.message : 'Could not create epic.';
      render(root,state);
    }
  }

  async function createTask(root,state,formData){
    if(!state.selectedProjectId)return;
    state.error='';
    render(root,state);
    try{
      await createTaskRequest(root,state,{
        epicId:formData.get('epicId'),
        text:formData.get('text'),
        grade:formData.get('grade'),
        markers:parseCsv(formData.get('markers')),
        flags:parseCsv(formData.get('flags')),
      });
    }catch(error){
      state.error=error && error.message ? error.message : 'Could not create task.';
      render(root,state);
    }
  }

  async function createQuickTask(root,state,formData){
    if(!state.selectedProjectId)return;
    state.error='';
    render(root,state);
    try{
      const quickEpicId=await ensureQuickTaskEpic(root,state);
      await createTaskRequest(root,state,{
        epicId:quickEpicId,
        text:formData.get('text'),
        grade:formData.get('grade') || 'green',
        markers:parseCsv(formData.get('markers')),
        flags:[],
      });
    }catch(error){
      state.error=error && error.message ? error.message : 'Could not create quick task.';
      render(root,state);
    }
  }

  async function ensureQuickTaskEpic(root,state){
    return ensureProjectEpic(state,'Quick tasks');
  }

  async function ensureProjectEpic(state,title){
    const tasksData=state.tasksData && Array.isArray(state.tasksData.epics) ? state.tasksData : null;
    const normalizedTitle=String(title||'').trim().toLowerCase();
    const existing=tasksData && tasksData.epics.find(function(epic){
      return String(epic.title||'').trim().toLowerCase()===normalizedTitle;
    });
    if(existing && existing.id)return existing.id;
    const created=await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/epics',{
      method:'POST',
      body:{title:title}
    });
    const epicId=created && created.epic ? created.epic.id : '';
    if(!epicId)throw new Error('Could not create the '+String(title||'task').trim()+' epic.');
    return epicId;
  }

  async function createTaskRequest(root,state,payload){
    await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/tasks',{
      method:'POST',
      body:payload,
    });
    loadTasks(root,state);
  }

  async function updateTask(root,state,taskId,updates){
    if(!state.selectedProjectId || !taskId)return;
    state.error='';
    try{
      await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/tasks/'+encodeURIComponent(taskId)+'/update',{
        method:'POST',
        body:updates,
      });
      loadTasks(root,state);
    }catch(error){
      state.error=error && error.message ? error.message : 'Could not update task.';
      render(root,state);
    }
  }

  function normalizeTaskQaStatus(value){
    return String(value||'').trim().toLowerCase().replace(/[\s_]+/g,'-');
  }

  function buildTaskLookup(tasksData){
    const lookup={};
    const epics=tasksData && Array.isArray(tasksData.epics) ? tasksData.epics : [];
    epics.forEach(function(epic){
      const tasks=Array.isArray(epic && epic.tasks) ? epic.tasks : [];
      tasks.forEach(function(task){
        const id=String(task && task.id || '').trim();
        if(id)lookup[id]=task;
      });
    });
    return lookup;
  }

  function taskIsBlocked(task,taskById){
    if(!task || task.done || task.archived)return false;
    const dependencies=Array.isArray(task.dependencies) ? task.dependencies : [];
    return dependencies.some(function(dependencyId){
      const dependency=taskById[String(dependencyId||'').trim()];
      return !!(dependency && !dependency.done);
    });
  }

  function isActionableTask(task,taskById){
    if(!task || task.done || task.archived || task.inProgress)return false;
    if(taskIsBlocked(task,taskById))return false;
    const qaStatus=normalizeTaskQaStatus(task.qaStatus);
    return qaStatus==='needs-more-work' || !qaStatus;
  }

  function actionableTaskCount(tasksData){
    const taskById=buildTaskLookup(tasksData);
    return Object.keys(taskById).reduce(function(count,taskId){
      return count + (isActionableTask(taskById[taskId],taskById) ? 1 : 0);
    },0);
  }

  function buildTaskBatchExecutionPrompt(tasksData){
    const lines=['Analyze the current project task file and execute the ready tasks with AI.'];
    lines.push('Follow the project task file as the source of truth for execution order and status updates.');
    if(tasksData && tasksData.branch){
      lines.push('Branch: '+String(tasksData.branch));
    }
    if(tasksData && (tasksData.tasksFilePath || tasksData.tasksFile)){
      lines.push('Tasks JSON file for this branch: '+String(tasksData.tasksFilePath || tasksData.tasksFile));
    }
    lines.push('Read and update that JSON file directly for this branch.');
    lines.push('Process tasks sequentially with no user prompts.');
    lines.push('Actionable tasks are only:');
    lines.push('- ready: not done, not blocked by dependencies, no qaStatus, and not inProgress.');
    lines.push('- needs-more-work: qaStatus is "needs-more-work".');
    lines.push('Execution loop for each actionable task:');
    lines.push('1) Reload task JSON and choose the next actionable task.');
    lines.push('2) Implement the task in the codebase.');
    lines.push('3) Immediately update the task JSON before moving on.');
    lines.push('If you discover new follow-up work while executing, add it as a new ready task with done=false, no qaStatus, and no inProgress.');
    lines.push('Never set qaStatus="ready-for-test" on newly created follow-up tasks; that status is only for actionable tasks you just executed.');
    lines.push('4) If task is completed, keep done=false, set qaStatus="ready-for-test", and clear moreWork/inProgress/sessionId/lastSessionAt when present.');
    lines.push('5) If task cannot be completed now, keep done=false, set qaStatus="needs-more-work", and write a clear moreWork note.');
    lines.push('6) Save the JSON and continue to the next actionable task until none remain.');
    return lines.join('\n');
  }

  async function executeReadyTasks(root,state){
    if(!state.selectedProjectId)return;
    const tasksData=state.tasksData && state.tasksData.project && state.tasksData.project.id===state.selectedProjectId
      ? state.tasksData
      : await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/tasks');
    const actionableCountValue=actionableTaskCount(tasksData);
    if(!actionableCountValue){
      state.error='No ready tasks are available to execute.';
      render(root,state);
      return;
    }
    state.taskAutomationBusyAction='execute-ready';
    state.error='';
    render(root,state);
    try{
      const epicId=await ensureProjectEpic(state,'AI automation');
      const created=await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/tasks',{
        method:'POST',
        body:{
          epicId:epicId,
          text:buildTaskBatchExecutionPrompt(tasksData),
          grade:'green',
        },
      });
      const createdTaskId=created && created.task ? String(created.task.id||'').trim() : '';
      if(!createdTaskId)throw new Error('Could not create the AI automation task.');
      state.tasksData=tasksData;
      const payload=await api(
        apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/tasks/'+encodeURIComponent(createdTaskId)+'/sessions/launch',
        {method:'POST',body:{}}
      );
      const target=payload && payload.sessionUrl ? String(payload.sessionUrl) : '';
      if(target && typeof window!=='undefined' && window.location){
        const normalized=appUrl(target);
        if(typeof window.location.assign==='function'){
          window.location.assign(normalized);
          return;
        }
        window.location.href=normalized;
        return;
      }
      await loadTasks(root,state);
    }catch(error){
      state.error=error && error.message ? error.message : 'Could not start the AI automation task.';
      state.taskAutomationBusyAction='';
      render(root,state);
      return;
    }
    state.taskAutomationBusyAction='';
    render(root,state);
  }

  async function loadNotifications(root,state){
    state.loadingNotifications=true;
    state.notificationsError='';
    render(root,state);
    try{
      const payload=await api('/api/ops/notifications/pending');
      state.notifications=Array.isArray(payload.notifications)?payload.notifications:[];
      state.loadingNotifications=false;
      render(root,state);
    }catch(error){
      state.loadingNotifications=false;
      state.notificationsError=error && error.message ? error.message : 'Could not load workflow notifications.';
      render(root,state);
    }
  }

  async function respondNotification(root,state,payload){
    const key=notificationKey(payload);
    state.respondingNotificationKey=key;
    state.notificationsError='';
    render(root,state);
    try{
      await api('/api/ops/notifications/respond',{
        method:'POST',
        body:payload,
      });
      state.respondingNotificationKey='';
      loadNotifications(root,state);
    }catch(error){
      state.respondingNotificationKey='';
      state.notificationsError=error && error.message ? error.message : 'Could not respond to the workflow notification.';
      render(root,state);
    }
  }

  async function launchTaskSession(root,state,taskId){
    if(!state.selectedProjectId || !taskId)return;
    state.launchingTaskId=taskId;
    state.error='';
    render(root,state);
    try{
      const payload=await api(
        apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/tasks/'+encodeURIComponent(taskId)+'/sessions/launch',
        {method:'POST',body:{}}
      );
      const target=payload && payload.sessionUrl ? String(payload.sessionUrl) : '';
      if(target && typeof window!=='undefined' && window.location){
        const normalized=appUrl(target);
        if(typeof window.location.assign==='function'){
          window.location.assign(normalized);
          return;
        }
        window.location.href=normalized;
        return;
      }
      state.launchingTaskId='';
      loadTasks(root,state);
    }catch(error){
      state.launchingTaskId='';
      state.error=error && error.message ? error.message : 'Could not launch a task session.';
      render(root,state);
    }
  }

  function render(root,state){
    const logScrollState=captureLogScrollState(root);
    const projectsButtonLabel=state.projectsOpen ? 'Hide projects' : 'Projects';
    const selectedProject=state.projects.find(function(project){return project.id===state.selectedProjectId;}) || null;
    const tasksData=state.tasksData && state.tasksData.project && state.tasksData.project.id===state.selectedProjectId ? state.tasksData : null;
    const projectSection=state.projectsOpen ? renderProjectsSection(state,selectedProject,tasksData) : '';
    const notificationsSection=renderNotificationsSection(state);
    const runsSection=state.projectsOpen ? '' : renderRunsSection(state);
    const githubSection=renderGitHubSection(state);
    const databaseSection=renderDatabaseSection(state);
    root.innerHTML=[
      '<div class="ops-shell-status">',
      '<span class="ops-shell-status-badge">Ready for clean project, task, runtime, admin, database, and maintenance-session work</span>',
      '<div class="ops-shell-grid">',
      '<div class="ops-shell-card"><strong>Phase</strong><span>'+escapeHtml(state.shellPayload.phase||'phase-7')+'</span></div>',
      '<div class="ops-shell-card"><strong>Route</strong><span>'+escapeHtml(state.shellPayload.route||'/ops')+'</span></div>',
      '<div class="ops-shell-card"><strong>API base</strong><span>'+escapeHtml(state.shellPayload.apiBase||'/api/ops')+'</span></div>',
      '<div class="ops-shell-card"><strong>Version</strong><span>'+escapeHtml(state.shellPayload.version||'')+'</span></div>',
      '</div>',
      '<div class="ops-projects-shell">',
      notificationsSection,
      runsSection,
      githubSection,
      databaseSection,
      '<div class="ops-project-toolbar">',
      '<button class="ops-shell-link primary" type="button" data-ops-action="toggle-projects">'+escapeHtml(projectsButtonLabel)+'</button>',
      '<button class="ops-shell-link" type="button" data-ops-action="refresh-projects">Refresh</button>',
      '</div>',
      state.error?'<p class="ops-shell-error">'+escapeHtml(state.error)+'</p>':'',
      projectSection,
      '</div>',
      '</div>'
    ].join('');
    restoreLogScrollState(root,logScrollState);
  }

  function renderNotificationsSection(state){
    if(window.HermesOpsNotifications && typeof window.HermesOpsNotifications.renderSection==='function'){
      return window.HermesOpsNotifications.renderSection(state);
    }
    return '';
  }

  function renderRunsSection(state){
    if(window.HermesOpsRuns && typeof window.HermesOpsRuns.renderSection==='function'){
      return window.HermesOpsRuns.renderSection(state);
    }
    return '';
  }

  function renderGitHubSection(state){
    if(window.HermesOpsGitHubAdmin && typeof window.HermesOpsGitHubAdmin.renderSection==='function'){
      return window.HermesOpsGitHubAdmin.renderSection(state);
    }
    return '';
  }

  function renderDatabaseSection(state){
    if(window.HermesOpsDatabase && typeof window.HermesOpsDatabase.renderGlobalSection==='function'){
      return window.HermesOpsDatabase.renderGlobalSection(state);
    }
    return '';
  }

  function renderProjectsSection(state,selectedProject,tasksData){
    const projects=state.projects;
    const projectRows=projects.length ? projects.map(function(project){
      const selected=project.id===state.selectedProjectId ? ' selected' : '';
      const subtitle=[project.tasksBranch ? 'Branch: '+project.tasksBranch : '', project.taskCount+' tasks'].filter(Boolean).join(' • ');
      return [
        '<button class="ops-project-row'+selected+'" type="button" data-ops-action="select-project" data-project-id="'+escapeHtml(project.id||'')+'">',
        '<strong>'+escapeHtml(project.name||project.fullName||project.slug||project.id||'Project')+'</strong>',
        '<span>'+escapeHtml(subtitle)+'</span>',
        '</button>'
      ].join('');
    }).join('') : '<p class="ops-shell-loading">No projects registered yet.</p>';

    return [
      '<div class="ops-project-layout">',
      renderProfileDatalist(state),
      '<section class="ops-project-column">',
      '<div class="ops-project-column-header"><h2>Projects</h2><span>'+(state.loadingProjects?'Loading…':escapeHtml(String(projects.length)+' loaded'))+'</span></div>',
      renderCreateProjectForm(state),
      '<div class="ops-project-list">'+projectRows+'</div>',
      '</section>',
      '<section class="ops-project-column detail">',
      renderProjectDetail(state,selectedProject,tasksData),
      '</section>',
      '</div>'
    ].join('');
  }

  function renderCreateProjectForm(state){
    return [
      '<form class="ops-inline-form" data-ops-form="create-project">',
      '<label><span>Name</span><input name="name" type="text" placeholder="Hermes Web UI"></label>',
      '<label><span>Path</span><input name="path" type="text" placeholder="/home/ubuntu/cloud-terminal-data/projects/hermes-webui"></label>',
      '<label><span>Core branch</span><input name="coreBranch" type="text" placeholder="main"></label>',
      '<label><span>Profile</span><input name="profile" type="text" list="ops-project-profile-list" placeholder="default"></label>',
      '<button class="ops-shell-link primary" type="submit"'+(state.creatingProject?' disabled':'')+'>'+(state.creatingProject?'Creating…':'Create project')+'</button>',
      '</form>'
    ].join('');
  }

  function renderProjectDetail(state,selectedProject,tasksData){
    if(!selectedProject){
      return '<div class="ops-project-column-header"><h2>Project detail</h2><span>Select a project</span></div><p class="ops-shell-loading">Choose a project to inspect branch-scoped tasks.</p>';
    }
    const epics=tasksData && Array.isArray(tasksData.epics) ? tasksData.epics : [];
    const executeReadyCount=actionableTaskCount(tasksData);
    const executeReadyBusy=state.taskAutomationBusyAction==='execute-ready';
    const epicRows=state.loadingTasks
      ? '<p class="ops-shell-loading">Loading tasks…</p>'
      : epics.length
        ? epics.map(function(epic){return renderEpicCard(epic,state);}).join('')
        : '<p class="ops-shell-loading">No epics yet for this branch.</p>';
    return [
      '<div class="ops-project-column-header">',
      '<div class="ops-project-column-copy"><h2>'+escapeHtml(selectedProject.name||'Project')+'</h2><span>'+escapeHtml(selectedProject.tasksBranch||selectedProject.coreBranch||'')+'</span></div>',
      '<button class="ops-shell-link" type="button" data-ops-action="close-projects">Back to ops dashboard</button>',
      '</div>',
      '<div class="ops-project-meta">',
      '<span><strong>Path</strong>'+escapeHtml(selectedProject.path||'')+'</span>',
      '<span><strong>Tasks file</strong>'+escapeHtml(selectedProject.tasksFilePath||'')+'</span>',
      '<span><strong>Profile</strong>'+escapeHtml(selectedProject.profile||'default')+'</span>',
      '<span><strong>Default model</strong>'+escapeHtml(selectedProject.defaultModel||'profile default')+'</span>',
      '</div>',
      renderProjectDefaultsForm(state,selectedProject),
      renderGitStatusSection(state,selectedProject),
      renderUpstreamSyncSection(state,selectedProject),
      renderProjectDatabaseSection(state,selectedProject),
      renderRuntimeSection(state,selectedProject),
      '<div class="ops-runtime-actions">',
      '<button class="ops-shell-link" type="button" data-ops-action="execute-ready-tasks"'+(!executeReadyCount && !executeReadyBusy ? ' disabled' : '')+' title="Ask Codex to execute ready and needs-more-work tasks in sequence.">'+(executeReadyBusy ? 'Starting…' : 'Execute ready tasks with AI')+(!executeReadyBusy && executeReadyCount ? ' ('+String(executeReadyCount)+')' : '')+'</button>',
      '</div>',
      renderQuickTaskForm(),
      renderFilterForm(state),
      '<form class="ops-inline-form compact" data-ops-form="create-epic">',
      '<label><span>New epic</span><input name="title" type="text" placeholder="Quick tasks"></label>',
      '<button class="ops-shell-link primary" type="submit">Add epic</button>',
      '</form>',
      '<div class="ops-epic-list">'+epicRows+'</div>'
    ].join('');
  }

  function renderProfileDatalist(state){
    const profiles=Array.isArray(state.availableProfiles)?state.availableProfiles:[];
    const options=['<option value="default"></option>'].concat(profiles.map(function(profile){
      return '<option value="'+escapeHtml(profile && profile.name || '')+'"></option>';
    }));
    return '<datalist id="ops-project-profile-list">'+options.join('')+'</datalist>';
  }

  function renderProjectDefaultsForm(state,selectedProject){
    const currentProfile=findProfileEntry(state,selectedProject.profile);
    const profileHint=currentProfile
      ? [currentProfile.model ? 'Model '+currentProfile.model : '', currentProfile.provider ? 'Provider '+currentProfile.provider : ''].filter(Boolean).join(' • ')
      : '';
    return [
      '<form class="ops-inline-form compact project-defaults-form" data-ops-form="project-defaults">',
      '<div class="ops-epic-header"><h3>Launch defaults</h3><span>Task sessions inherit these values</span></div>',
      '<label><span>Profile</span><input name="profile" type="text" list="ops-project-profile-list" value="'+escapeHtml(selectedProject.profile||'')+'" placeholder="default"></label>',
      '<label><span>Default model</span><input name="defaultModel" type="text" value="'+escapeHtml(selectedProject.defaultModel||'')+'" placeholder="leave blank to use the profile default"></label>',
      '<label><span>Model provider</span><input name="defaultModelProvider" type="text" value="'+escapeHtml(selectedProject.defaultModelProvider||'')+'" placeholder="optional provider hint"></label>',
      profileHint?'<p class="ops-runtime-note">Selected profile defaults: '+escapeHtml(profileHint)+'</p>':'',
      state.profilesError?'<p class="ops-runtime-note">'+escapeHtml(state.profilesError)+'</p>':'',
      '<div class="ops-runtime-actions">',
      '<button class="ops-shell-link primary" type="submit"'+(state.savingProjectDefaults?' disabled':'')+'>'+(state.savingProjectDefaults?'Saving…':'Save defaults')+'</button>',
      '</div>',
      '</form>'
    ].join('');
  }

  function findProfileEntry(state,name){
    const key=String(name||'').trim();
    if(!key)return null;
    const profiles=Array.isArray(state.availableProfiles)?state.availableProfiles:[];
    for(let index=0;index<profiles.length;index+=1){
      const profile=profiles[index];
      if(profile && String(profile.name||'').trim()===key)return profile;
    }
    return null;
  }

  function renderRuntimeSection(state,selectedProject){
    if(window.HermesOpsRuntime && typeof window.HermesOpsRuntime.renderSection==='function'){
      return window.HermesOpsRuntime.renderSection({
        selectedProject:selectedProject,
        selectedProjectId:state.selectedProjectId,
        loadingRuntimeSummary:state.loadingRuntimeSummary,
        runtimeSummary:state.runtimeSummary,
        runtimeError:state.runtimeError,
        inspectError:state.inspectError,
        inspectBusyAction:state.inspectBusyAction,
        playLogs:state.playLogs,
        loadingPlayLogs:state.loadingPlayLogs,
        playError:state.playError,
        playBusyAction:state.playBusyAction,
        showPlayLogs:state.showPlayLogs,
      });
    }
    return '';
  }

  function renderGitStatusSection(state,selectedProject){
    if(window.HermesOpsGit && typeof window.HermesOpsGit.renderSection==='function'){
      return window.HermesOpsGit.renderSection({
        selectedProject:selectedProject,
        loadingGitStatus:state.loadingGitStatus,
        gitStatus:state.gitStatus,
        gitError:state.gitError,
      });
    }
    return '';
  }

  function renderProjectDatabaseSection(state,selectedProject){
    if(window.HermesOpsDatabase && typeof window.HermesOpsDatabase.renderProjectSection==='function'){
      return window.HermesOpsDatabase.renderProjectSection({
        selectedProject:selectedProject,
        projectDatabase:state.projectDatabase,
        projectDatabaseTables:state.projectDatabaseTables,
        projectDatabaseQueryResult:state.projectDatabaseQueryResult,
        projectDatabaseError:state.projectDatabaseError,
        projectDatabaseBusyAction:state.projectDatabaseBusyAction,
      });
    }
    return '';
  }

  function renderUpstreamSyncSection(state,selectedProject){
    if(window.HermesOpsUpstreamSync && typeof window.HermesOpsUpstreamSync.renderSection==='function'){
      return window.HermesOpsUpstreamSync.renderSection({
        selectedProject:selectedProject,
        loadingUpstreamSync:state.loadingUpstreamSync,
        upstreamSync:state.upstreamSync,
        upstreamSyncRecords:state.upstreamSyncRecords,
        upstreamSyncError:state.upstreamSyncError,
        upstreamSyncBusyAction:state.upstreamSyncBusyAction,
      });
    }
    return '';
  }

  function renderQuickTaskForm(){
    return [
      '<form class="ops-inline-form quick-task-form" data-ops-form="quick-task">',
      '<label><span>Quick task</span><input name="text" type="text" placeholder="Add a task to the Quick tasks epic"></label>',
      '<label><span>Grade</span><select name="grade"><option value="green">green</option><option value="orange">orange</option><option value="red">red</option></select></label>',
      '<label><span>Labels</span><input name="markers" type="text" placeholder="migration, ui"></label>',
      '<button class="ops-shell-link primary" type="submit">Add quick task</button>',
      '</form>'
    ].join('');
  }

  function renderFilterForm(state){
    return [
      '<div class="ops-inline-form compact filters">',
      '<label><span>Filter text</span><input data-ops-filter="text" type="text" value="'+escapeHtml(state.filterText||'')+'" placeholder="Search tasks"></label>',
      '<label><span>Status</span><select data-ops-filter="status"><option value="all"'+selectedAttr(state.filterStatus,'all')+'>all</option><option value="open"'+selectedAttr(state.filterStatus,'open')+'>open</option><option value="done"'+selectedAttr(state.filterStatus,'done')+'>done</option></select></label>',
      '<label><span>Grade</span><select data-ops-filter="grade"><option value="all"'+selectedAttr(state.filterGrade,'all')+'>all</option><option value="green"'+selectedAttr(state.filterGrade,'green')+'>green</option><option value="orange"'+selectedAttr(state.filterGrade,'orange')+'>orange</option><option value="red"'+selectedAttr(state.filterGrade,'red')+'>red</option></select></label>',
      '</div>'
    ].join('');
  }

  function renderEpicCard(epic,state){
    const tasks=Array.isArray(epic.tasks)?epic.tasks:[];
    const visibleTasks=tasks.filter(function(task){return taskMatchesFilters(task,state);});
    const taskRows=visibleTasks.length ? visibleTasks.map(function(task){
      const labels=renderLabelChips(task.markers,'label');
      const flags=renderLabelChips(task.flags,'flag');
      const linkedSessions=renderLinkedSessions(task.linkedSessions);
      const taskActions=renderTaskActions(task,state);
      return [
        '<div class="ops-task-row">',
        '<label class="ops-task-toggle">',
        '<input type="checkbox" data-ops-task-toggle data-task-id="'+escapeHtml(task.id||'')+'"'+(task.done?' checked':'')+'>',
        '</label>',
        '<span class="ops-task-copy'+(task.done?' done':'')+'">',
        '<strong>'+escapeHtml(task.text||'')+'</strong>',
        '<em>'+escapeHtml(task.grade||'green')+'</em>',
        labels || flags ? '<span class="ops-task-chips">'+labels+flags+'</span>' : '',
        taskActions,
        linkedSessions,
        '</span>',
        '</div>'
      ].join('');
    }).join('') : '<p class="ops-shell-loading">No tasks match the current filters.</p>';
    return [
      '<article class="ops-epic-card">',
      '<div class="ops-epic-header"><h3>'+escapeHtml(epic.title||'Epic')+'</h3><span>'+escapeHtml(String(visibleTasks.length)+' / '+String(tasks.length)+' tasks')+'</span></div>',
      '<div class="ops-task-list">'+taskRows+'</div>',
      '<form class="ops-inline-form compact" data-ops-form="create-task">',
      '<input type="hidden" name="epicId" value="'+escapeHtml(epic.id||'')+'">',
      '<label><span>Task</span><input name="text" type="text" placeholder="Describe the task"></label>',
      '<label><span>Grade</span><select name="grade"><option value="green">green</option><option value="orange">orange</option><option value="red">red</option></select></label>',
      '<label><span>Labels</span><input name="markers" type="text" placeholder="migration, ui"></label>',
      '<label><span>Flags</span><input name="flags" type="text" placeholder="blocked"></label>',
      '<button class="ops-shell-link" type="submit">Add task</button>',
      '</form>',
      '</article>'
    ].join('');
  }

  function taskMatchesFilters(task,state){
    const text=String(task.text||'').toLowerCase();
    const filterText=String(state.filterText||'').trim().toLowerCase();
    if(filterText && text.indexOf(filterText)===-1){
      const markerText=[].concat(task.markers||[],task.flags||[]).join(' ').toLowerCase();
      if(markerText.indexOf(filterText)===-1)return false;
    }
    if(state.filterStatus==='open' && task.done)return false;
    if(state.filterStatus==='done' && !task.done)return false;
    if(state.filterGrade!=='all' && String(task.grade||'green')!==state.filterGrade)return false;
    return true;
  }

  function renderLabelChips(values,kind){
    const items=Array.isArray(values)?values:[];
    return items.map(function(value){
      return '<span class="ops-task-chip '+escapeHtml(kind||'label')+'">'+escapeHtml(value)+'</span>';
    }).join('');
  }

  function renderLinkedSessions(values){
    const items=Array.isArray(values)?values:[];
    if(!items.length){
      return '<span class="ops-task-session-link empty">No linked session yet</span>';
    }
    return items.map(function(item){
      const session=item && item.session ? item.session : {};
      const title=session.title || item.sessionId || 'Session';
      const count=session.message_count;
      const suffix=count===undefined || count===null ? '' : ' • '+count+' msgs';
      const href=item && item.sessionUrl ? String(item.sessionUrl) : sessionUrlFor(item && item.sessionId);
      if(item && item.available===false){
        return '<span class="ops-task-session-link unavailable">'+escapeHtml(title+' unavailable')+'</span>';
      }
      return '<a class="ops-task-session-link" href="'+escapeHtml(appUrl(href))+'">'+escapeHtml(title+suffix)+'</a>';
    }).join('');
  }

  function renderTaskActions(task,state){
    const linkedSessions=Array.isArray(task.linkedSessions)?task.linkedSessions:[];
    const latest=linkedSessions.find(function(item){
      return item && item.available!==false && item.sessionId;
    });
    const launching=String(state.launchingTaskId||'')===String(task.id||'');
    return [
      '<span class="ops-task-actions">',
      '<button class="ops-shell-link'+(launching?' disabled':'')+'" type="button" data-ops-action="launch-task-session" data-task-id="'+escapeHtml(task.id||'')+'"'+(launching?' disabled':'')+'>'+(launching?'Opening…':'New session')+'</button>',
      latest ? '<a class="ops-shell-link" href="'+escapeHtml(appUrl(String(latest.sessionUrl||sessionUrlFor(latest.sessionId))))+'">Resume latest</a>' : '',
      '</span>'
    ].join('');
  }

  function parseCsv(value){
    return String(value||'')
      .split(',')
      .map(function(item){return item.trim();})
      .filter(Boolean);
  }

  function selectedAttr(current,value){
    return String(current||'')===String(value||'') ? ' selected' : '';
  }

  function sessionUrlFor(sessionId){
    const sid=String(sessionId||'').trim();
    return sid ? appUrl('session/'+encodeURIComponent(sid)) : appUrl('./');
  }

  function notificationKey(payload){
    if(payload && payload.notificationKey){
      return String(payload.notificationKey);
    }
    const kind=String(payload&&payload.kind||payload&&payload['data-notification-kind']||'').trim();
    const sessionId=String(payload&&payload.sessionId||payload&&payload['data-session-id']||'').trim();
    const approvalId=String(payload&&payload.approvalId||payload&&payload['data-approval-id']||'').trim();
    const response=String(payload&&payload.response||payload&&payload['data-response']||payload&&payload.choice||payload&&payload['data-choice']||'').trim();
    return kind+':'+sessionId+':'+approvalId+':'+response;
  }

  function getFilterValue(root,name,fallback){
    const field=root.querySelector('[data-ops-filter="'+name+'"]');
    if(field && 'value' in field){
      return String(field.value||fallback||'');
    }
    return fallback;
  }

  window.HermesOpsProjects={mount:mount};
})();

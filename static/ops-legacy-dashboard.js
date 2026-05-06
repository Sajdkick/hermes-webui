(function(){
  const TASK_QA_STATUS_VALUES=['ready-for-test','needs-more-work','not-synced'];
  const TASK_FILTER_STATUS_VALUES=['active','ready','in-progress','ready-for-test','needs-more-work','not-synced','blocked','done','archived'];
  const TASK_GRADE_VALUES=['green','orange','red'];
  const RUN_STATUS_VALUES=['queued','starting','running','waiting-input','waiting-approval','succeeded','failed','stopped','stale'];
  const RUN_ACTIVE_STATUS_VALUES=['queued','starting','running','waiting-input','waiting-approval'];
  const RUN_ATTENTION_STATUS_VALUES=['waiting-input','waiting-approval','failed','stale'];
  const RUN_REQUEST_STATUS_VALUES=['pending','responded','dismissed','resolved','expired'];
  const RUN_ARTIFACT_TYPE_VALUES=['file','image','screenshot','temp-input','readable-output','log','report','link','other'];
  const RUN_LOG_STREAM_VALUES=['stdout','stderr','system','agent','tool','browser','test','other'];
  const RUN_LOG_LEVEL_VALUES=['debug','info','warning','error'];
  const TASK_EXECUTION_PREFACE='Execute on this task from the user';
  const TASK_EXECUTION_INSTRUCTIONS='but before doing so you must first read the contents of AGENTS.md. Once you have done that you have all the context you need to decide how to move forward with the task.';
  const TASK_BATCH_EXECUTION_PROMPT='Analyze the current project task file and execute the ready tasks with AI.';
  const TASK_BATCH_INSTRUCTIONS='Follow the project task file as the source of truth for execution order and status updates.';
  const EPIC_ACCENT_PALETTE=[
    {accent:'#34d399',soft:'rgba(52,211,153,.12)',border:'rgba(52,211,153,.35)'},
    {accent:'#38bdf8',soft:'rgba(56,189,248,.12)',border:'rgba(56,189,248,.35)'},
    {accent:'#f59e0b',soft:'rgba(245,158,11,.12)',border:'rgba(245,158,11,.35)'},
    {accent:'#f87171',soft:'rgba(248,113,113,.12)',border:'rgba(248,113,113,.35)'},
    {accent:'#a3e635',soft:'rgba(163,230,53,.12)',border:'rgba(163,230,53,.35)'},
    {accent:'#22d3ee',soft:'rgba(34,211,238,.12)',border:'rgba(34,211,238,.35)'},
  ];
  const OPS_MODULES=window.HermesOpsModules||{};
  const OPS_SESSION_GROUP_COLLAPSE_STORAGE_KEY='hermes-webui-ops-session-group-collapse';
  const OPS_SESSION_ACTIVITY_COLLAPSE_STORAGE_KEY='hermes-webui-ops-session-activity-collapse';
  const OPS_EPIC_COLLAPSE_STORAGE_KEY='hermes-webui-ops-epic-collapse';
  const TASK_DICTATION_PROMPT='Transcribe short project task entries and software terms. Preserve filenames, acronyms, and numbers.';
  const TASK_DICTATION_AUDIO_BITS_PER_SECOND=128000;

  function readDashboardStoredJson(key,fallback){
    try{
      if(typeof window==='undefined'||!window.localStorage)return fallback;
      const raw=window.localStorage.getItem(key);
      if(!raw)return fallback;
      const parsed=JSON.parse(raw);
      return parsed&&typeof parsed==='object'?parsed:fallback;
    }catch(e){
      return fallback;
    }
  }

  function writeDashboardStoredJson(key,value){
    try{
      if(typeof window==='undefined'||!window.localStorage)return;
      window.localStorage.setItem(key,JSON.stringify(value));
    }catch(e){}
  }

  function normalizeRunStatus(value){
    const normalized=String(value||'').trim().toLowerCase().replace(/[\s_]+/g,'-');
    return RUN_STATUS_VALUES.includes(normalized)?normalized:'stale';
  }

  function runStatusLabel(status){
    switch(normalizeRunStatus(status)){
      case 'queued': return 'Queued';
      case 'starting': return 'Starting';
      case 'running': return 'Running';
      case 'waiting-input': return 'Waiting input';
      case 'waiting-approval': return 'Waiting approval';
      case 'succeeded': return 'Succeeded';
      case 'failed': return 'Failed';
      case 'stopped': return 'Stopped';
      default: return 'Stale';
    }
  }

  function runStatusKind(status){
    const normalized=normalizeRunStatus(status);
    if(['failed','stale'].includes(normalized))return 'error';
    if(['waiting-input','waiting-approval'].includes(normalized))return 'attention';
    if(normalized==='succeeded')return 'success';
    if(normalized==='stopped')return 'stopped';
    if(RUN_ACTIVE_STATUS_VALUES.includes(normalized))return 'running';
    return 'stale';
  }

  const OPS={
    view:'home',
    projects:[],
    profiles:[],
    sessions:[],
    sessionGroups:null,
    sessionActivity:[],
    sessionActivityGroups:[],
    sessionActivityCollapsed:readDashboardStoredJson(OPS_SESSION_ACTIVITY_COLLAPSE_STORAGE_KEY,{}),
    sessionActivityInitialized:{},
    sessionActivityBusy:false,
    sessionActivityExpanded:true,
    sessionActivityLastRefreshedAt:0,
    sessionActivityError:'',
    sessionActivityFocusGroupId:'',
    sessionGroupCollapsed:readDashboardStoredJson(OPS_SESSION_GROUP_COLLAPSE_STORAGE_KEY,{}),
    epicCollapsed:readDashboardStoredJson(OPS_EPIC_COLLAPSE_STORAGE_KEY,{}),
    runs:[],
    runsByProject:{},
    selectedRunId:'',
    runDetail:null,
    runReadableOutput:null,
    runEvents:null,
    runRequests:null,
    runArtifacts:null,
    runLogs:null,
    notifications:[],
    notificationSettings:null,
    notificationMonitor:null,
    notificationLogs:[],
    notificationPushSubscriptions:[],
    notificationPushStatus:null,
    notificationBrowserPush:null,
    notificationAutoApprovalPolicy:null,
    notificationBusy:false,
    migrationHealth:null,
    migrationHealthBusy:false,
    artifactHealth:null,
    artifactHealthBusy:false,
    taskDataByProject:{},
    playStatusByProject:{},
    playLogsByProject:{},
    playBusyByProject:{},
    playConfigByProject:{},
    playConfigEditingProjectId:'',
    playSnapshotsByProject:{},
    playScreenshotsByProject:{},
    gitStatusByProject:{},
    gitBusyByProject:{},
    gitPlansByProject:{},
    gitOperationsByProject:{},
    githubStatus:null,
    githubRepos:[],
    githubBranchesByRepo:{},
    githubBusy:false,
    githubQuery:'',
    githubError:'',
    gatherReportsByProject:{},
    gatherBusyByProject:{},
    reviewRequestsByProject:{},
    reviewBusyByProject:{},
    deploymentsByProject:{},
    deploymentBusyByProject:{},
    projectHealthByProject:{},
    projectHealthBusyByProject:{},
    databaseSettings:null,
    databaseTables:[],
    databaseBusy:false,
    databaseError:'',
    projectDatabaseByProject:{},
    projectDatabaseBusyByProject:{},
    counts:{},
    currentProject:null,
    taskData:null,
    taskAutomationBusyByProject:{},
    showCreate:false,
    showArchived:false,
    taskCreateCollapsed:false,
    taskFiltersCollapsed:true,
    taskFilters:{status:'active',grade:'',token:''},
    taskFilterFocusedField:'',
    taskFilterSelectionStart:null,
    taskFilterSelectionEnd:null,
    taskFormDraft:null,
    createEpicDraftTitle:'',
    taskFormFocusedForm:'',
    taskFormFocusedField:'',
    taskFormSelectionStart:null,
    taskFormSelectionEnd:null,
    editingTask:null,
    loading:false,
    quickTaskProjectId:'',
    quickTaskText:'',
    quickTaskGoalMode:false,
    quickTaskBusy:false,
    quickTaskStatus:'',
    quickTaskStatusKind:'info',
    quickTaskImages:[],
    quickTaskDictationSupported:!!(window.navigator&&window.navigator.mediaDevices&&window.navigator.mediaDevices.getUserMedia&&typeof window.MediaRecorder!=='undefined'),
    quickTaskDictationActive:false,
    quickTaskDictationBusy:false,
    quickTaskDictationStatus:'',
    quickTaskDictationStatusKind:'info',
    quickTaskDictationStream:null,
    quickTaskDictationRecorder:null,
    quickTaskDictationChunks:[],
    quickTaskDictationDiscard:false,
    quickTaskDictationBaseText:'',
    quickTaskFocusedField:'',
    quickTaskSelectionStart:null,
    quickTaskSelectionEnd:null,
  };
  const DASHBOARD_SHARED=OPS_MODULES.dashboardShared&&typeof OPS_MODULES.dashboardShared.bindDashboard==='function'
    ? OPS_MODULES.dashboardShared.bindDashboard({
      OPS,
      esc:typeof esc==='function'?esc:(value=>String(value??'')),
      projectPath:typeof projectPath==='function'?projectPath:null,
      writeStoredJson:typeof writeDashboardStoredJson==='function'?writeDashboardStoredJson:null,
      root:typeof root==='function'?root:null,
      SRef:()=>typeof S!=='undefined'?S:null,
      requestAnimationFrameRef:typeof requestAnimationFrame==='function'?requestAnimationFrame:(cb=>setTimeout(cb,0)),
      epicAccentPalette:EPIC_ACCENT_PALETTE,
      epicCollapseStorageKey:OPS_EPIC_COLLAPSE_STORAGE_KEY,
    })
    : {};
  const projectRepositoryLabel=DASHBOARD_SHARED.projectRepositoryLabel||function(project){
    return String(project&&project.fullName||project&&project.name||project&&project.slug||project&&project.id||'Project').trim()||'Project';
  };
  const projectBranchLabel=DASHBOARD_SHARED.projectBranchLabel||function(project){
    return String(project&&project.coreBranch||project&&project.branch||'').trim();
  };
  const projectFolderLabel=DASHBOARD_SHARED.projectFolderLabel||function(project){
    const path=normalizePath(projectPath(project));
    if(path){
      const parts=path.split('/').filter(Boolean);
      return parts[parts.length-1]||'';
    }
    return String(project&&project.slug||'').trim();
  };
  const projectUsesBranchTitle=DASHBOARD_SHARED.projectUsesBranchTitle||function(project,projectList){
    if(!project||typeof project!=='object')return false;
    const branch=projectBranchLabel(project);
    if(!branch)return false;
    const worktreeRole=String(project&&project.worktree&&project.worktree.role||'').trim().toLowerCase();
    if(worktreeRole==='base'||worktreeRole==='linked')return true;
    const repoLabel=projectRepositoryLabel(project);
    if(!repoLabel)return false;
    const source=Array.isArray(projectList)?projectList:OPS.projects;
    let duplicateCount=0;
    source.forEach(entry=>{
      if(!entry||typeof entry!=='object')return;
      if(projectRepositoryLabel(entry)!==repoLabel)return;
      duplicateCount+=1;
    });
    return duplicateCount>1;
  };
  const projectCardTitle=DASHBOARD_SHARED.projectCardTitle||function(project,projectList){
    const branch=projectBranchLabel(project);
    if(projectUsesBranchTitle(project,projectList)&&branch)return branch;
    return projectRepositoryLabel(project);
  };
  const projectContextLabel=DASHBOARD_SHARED.projectContextLabel||function(project,projectList){
    if(!project||typeof project!=='object')return '';
    const parts=[];
    const repoLabel=projectRepositoryLabel(project);
    const branch=projectBranchLabel(project);
    if(projectUsesBranchTitle(project,projectList)){
      if(repoLabel)parts.push(repoLabel);
    }else if(branch){
      parts.push(`Branch ${branch}`);
    }
    const folder=projectFolderLabel(project);
    if(folder&&folder!==projectCardTitle(project,projectList)&&folder!==repoLabel){
      parts.push(`Folder ${folder}`);
    }
    return parts.join(' • ');
  };
  const projectAccentStyle=DASHBOARD_SHARED.projectAccentStyle||function(project,index,prefix){
    const seed=project&&((project.id||'')||(project.fullName||'')||(project.path||''))||index||0;
    return '';
  };
  const sessionAccentStyle=DASHBOARD_SHARED.sessionAccentStyle||function(){return '';};
  const sessionGroupAccentStyle=DASHBOARD_SHARED.sessionGroupAccentStyle||function(){return '';};
  const projectProfileLabel=DASHBOARD_SHARED.projectProfileLabel||function(project){
    const profile=String(project&&project.profile||'').trim();
    return profile||'No assigned profile';
  };
  const renderProjectProfileOptions=DASHBOARD_SHARED.renderProjectProfileOptions||function(){return '';};
  const formatOpsDateTime=DASHBOARD_SHARED.formatOpsDateTime||function(value,fallback){return fallback||String(value||'Unknown');};
  const setEpicCollapsed=DASHBOARD_SHARED.setEpicCollapsed||function(){};
  const isEpicCollapsed=DASHBOARD_SHARED.isEpicCollapsed||function(){return false;};
  const syncEpicCollapseState=DASHBOARD_SHARED.syncEpicCollapseState||function(){};
  const rememberTaskFilterFocus=DASHBOARD_SHARED.rememberTaskFilterFocus||function(){};
  const restoreTaskFilterFocus=DASHBOARD_SHARED.restoreTaskFilterFocus||function(){};

  const svg={
    grid:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
    folder:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
    plus:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
    arrow:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M19 12H5"/><path d="m12 19-7-7 7-7"/></svg>',
    refresh:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>',
    check:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="m20 6-11 11-5-5"/></svg>',
    chevron:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>',
    edit:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>',
    trash:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>',
    chat:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
    git:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="6" cy="6" r="2"/><circle cx="18" cy="18" r="2"/><circle cx="6" cy="18" r="2"/><path d="M6 8v8"/><path d="M8 6h3a4 4 0 0 1 4 4v6"/></svg>',
    play:'<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>',
    close:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
  };
  const DASHBOARD_SHELL=OPS_MODULES.dashboardShell&&typeof OPS_MODULES.dashboardShell.bindDashboard==='function'
    ? OPS_MODULES.dashboardShell.bindDashboard({
      OPS,
      root:()=>typeof $==='function'?$('opsDashboardRoot'):null,
      layout:()=>typeof document!=='undefined'?document.querySelector('.layout'):null,
      navBtn:()=>typeof $==='function'?$('opsDashboardNavBtn'):null,
      esc:typeof esc==='function'?esc:(value=>String(value??'')),
      documentRef:typeof document!=='undefined'?document:null,
      windowRef:typeof window!=='undefined'?window:null,
      syncTopbarRef:()=>typeof syncTopbar==='function'?syncTopbar:null,
      renderHomeRef:()=>renderHome,
      loadDashboardHomeRef:()=>loadDashboardHome,
      renderProjectsRef:()=>renderProjects,
      renderProjectDetailRef:()=>renderProjectDetail,
      startNotificationPollingRef:()=>startNotificationPolling,
      stopNotificationPollingRef:()=>stopNotificationPolling,
      stopPlayStatusPollingRef:()=>stopPlayStatusPolling,
      stopQuickTaskDictationRef:()=>stopQuickTaskDictation,
      setBusy:typeof setBusy==='function'?setBusy:()=>{},
    })
    : {};
  const setDashboardTopbar=DASHBOARD_SHELL.setDashboardTopbar||function(title,meta){
    const titleEl=typeof $==='function'?$('topbarTitle'):null;
    const metaEl=typeof $==='function'?$('topbarMeta'):null;
    if(titleEl)titleEl.textContent=title;
    if(metaEl)metaEl.textContent=meta||'';
    if(typeof document!=='undefined')document.title=title+' - '+(window._botName||'Hermes');
  };
  const setActiveNav=DASHBOARD_SHELL.setActiveNav||function(){
    document.querySelectorAll('.nav-tab').forEach(tab=>tab.classList.toggle('active',tab===(typeof $==='function'?$('opsDashboardNavBtn'):null)));
  };
  const openOpsDashboardView=DASHBOARD_SHELL.openOpsDashboard||function(){};
  const closeOpsDashboard=DASHBOARD_SHELL.closeOpsDashboard||function(){};
  const renderCurrentOpsView=DASHBOARD_SHELL.renderCurrentOpsView||function(){};
  const renderLoading=DASHBOARD_SHELL.renderLoading||function(label){
    const el=typeof $==='function'?$('opsDashboardRoot'):null;
    if(el)el.innerHTML=`<div class="ops-dashboard"><div class="ops-empty">${esc(label||'Loading...')}</div></div>`;
  };

  function readStandaloneOpsHistoryState(state){
    if(
      typeof window==='undefined'
      || !window.__OPS_LEGACY_STANDALONE__
      || typeof window.__opsLegacyReadHistoryState!=='function'
    ){
      return null;
    }
    return window.__opsLegacyReadHistoryState(state===undefined&&window.history?window.history.state:state);
  }

  function normalizeStandaloneOpsHistoryState(state){
    if(state&&typeof state==='object'&&typeof state.view==='string'&&!('hermesOpsLegacyDashboard' in state)){
      return {
        view:String(state.view||'').trim()||'home',
        projectId:String(state.projectId||'').trim(),
      };
    }
    return readStandaloneOpsHistoryState(state);
  }

  async function restoreStandaloneOpsHistoryState(state){
    const normalized=normalizeStandaloneOpsHistoryState(state);
    if(!normalized)return null;
    if(typeof window!=='undefined'&&window.__OPS_LEGACY_STANDALONE__&&!window._opsDashboardOpen){
      openOpsDashboardView({historyMode:'skip'});
    }
    if(normalized.view==='project-detail'&&normalized.projectId){
      return DASHBOARD_PROJECTS.openProjectDetail(normalized.projectId,{historyMode:'skip'});
    }
    if(normalized.view==='projects'){
      return DASHBOARD_PROJECTS.openProjects({historyMode:'skip'});
    }
    return openOpsDashboardView({historyMode:'skip'});
  }

  function openOpsDashboard(options){
    const opts=options&&typeof options==='object'?options:{};
    if(!opts.skipStoredState){
      const restored=readStandaloneOpsHistoryState();
      if(restored&&restored.view!=='home'){
        return restoreStandaloneOpsHistoryState(restored);
      }
    }
    return openOpsDashboardView(opts);
  }
  const DASHBOARD_DATABASE=OPS_MODULES.database&&typeof OPS_MODULES.database.bindDashboard==='function'
    ? OPS_MODULES.database.bindDashboard({
      OPS,
      api:typeof api==='function'?api:null,
      projectUrl,
      renderCurrentOpsView,
      showToast:typeof showToast==='function'?showToast:()=>{},
      esc:typeof esc==='function'?esc:(value=>String(value??'')),
      svg,
    })
    : {};
  const DASHBOARD_HEALTH=OPS_MODULES.health&&typeof OPS_MODULES.health.bindDashboard==='function'
    ? OPS_MODULES.health.bindDashboard({
      OPS,
      api:typeof api==='function'?api:null,
      projectUrl,
      renderCurrentOpsView,
      showToast:typeof showToast==='function'?showToast:()=>{},
      showConfirmDialog:typeof showConfirmDialog==='function'?showConfirmDialog:(async()=>false),
      esc:typeof esc==='function'?esc:(value=>String(value??'')),
      svg,
      nameOf:typeof nameOf==='function'?nameOf:(project=>String(project&&project.name||project&&project.id||'Project')),
      findProject:typeof findProject==='function'?findProject:null,
      openProjects:typeof openProjects==='function'?openProjects:null,
      renderProjectProfileOptions:typeof renderProjectProfileOptions==='function'?renderProjectProfileOptions:null,
      mergeProjectUpdate:typeof mergeProjectUpdate==='function'?mergeProjectUpdate:null,
      AgentBridge:typeof AgentBridge!=='undefined'?AgentBridge:null,
    })
    : {};
  const DASHBOARD_HOME=OPS_MODULES.home&&typeof OPS_MODULES.home.bindDashboard==='function'
    ? OPS_MODULES.home.bindDashboard({
      OPS,
      AgentBridge:typeof AgentBridge!=='undefined'?AgentBridge:null,
      renderCurrentOpsView,
      root:typeof root==='function'?root:null,
      esc:typeof esc==='function'?esc:(value=>String(value??'')),
      svg,
      showError:typeof showError==='function'?showError:()=>{},
      setBusy:typeof setBusy==='function'?setBusy:()=>{},
      setDashboardTopbar:typeof setDashboardTopbar==='function'?setDashboardTopbar:()=>{},
      renderNotifications:()=>renderNotifications(),
      normalizedAutoApprovalPolicy:()=>normalizedAutoApprovalPolicy(),
      loadProjects:()=>loadProjects(),
      openProjectDetail:(projectId)=>openProjectDetail(projectId),
      loadNotifications:()=>loadNotifications(),
      loadOpsRuns:(filters)=>loadOpsRuns(filters),
      loadNotificationDiagnostics:(options)=>loadNotificationDiagnostics(options),
      findProject:typeof findProject==='function'?findProject:null,
      projectUsesBranchTitle:typeof projectUsesBranchTitle==='function'?projectUsesBranchTitle:null,
      projectBranchLabel:typeof projectBranchLabel==='function'?projectBranchLabel:null,
      projectCardTitle:typeof projectCardTitle==='function'?projectCardTitle:null,
      projectRepositoryLabel:typeof projectRepositoryLabel==='function'?projectRepositoryLabel:null,
      normalizeRunStatus:(value)=>normalizeRunStatus(value),
      runStatusLabel:(value)=>runStatusLabel(value),
      runStatusKind:(value)=>runStatusKind(value),
      formatOpsDateTime:typeof formatOpsDateTime==='function'?formatOpsDateTime:null,
      renderProjectGitQuickAction:(project)=>renderProjectGitQuickAction(project),
      renderProjectPlayQuickAction:(project)=>renderProjectPlayQuickAction(project),
      renderProjectActivityQuickAction:(project)=>renderProjectActivityQuickAction(project),
      sessionAccentStyle:typeof sessionAccentStyle==='function'?sessionAccentStyle:null,
      sessionGroupAccentStyle:typeof sessionGroupAccentStyle==='function'?sessionGroupAccentStyle:null,
      sessionRefValue:typeof sessionRefValue==='function'?sessionRefValue:null,
      canonicalTaskSessions:typeof canonicalTaskSessions==='function'?canonicalTaskSessions:null,
      projectSessionsFor:typeof projectSessionsFor==='function'?projectSessionsFor:null,
      isSessionForProject:typeof isSessionForProject==='function'?isSessionForProject:null,
      taskImageLabel:(ref)=>DASHBOARD_PROJECT_DETAIL.taskImageLabel(ref),
      writeStoredJson:typeof writeDashboardStoredJson==='function'?writeDashboardStoredJson:null,
      sessionActivityStorageKey:OPS_SESSION_ACTIVITY_COLLAPSE_STORAGE_KEY,
      navigatorRef:typeof navigator!=='undefined'?navigator:null,
      windowRef:typeof window!=='undefined'?window:null,
      documentRef:typeof document!=='undefined'?document:null,
      URLRef:typeof URL!=='undefined'?URL:null,
      MediaRecorderRef:typeof MediaRecorder!=='undefined'?MediaRecorder:null,
      FileRef:typeof File!=='undefined'?File:null,
      showPromptDialog:typeof showPromptDialog==='function'?showPromptDialog:(async()=>null),
      showConfirmDialog:typeof showConfirmDialog==='function'?showConfirmDialog:(async()=>false),
      openOpsSession:(sessionId)=>openOpsSession(sessionId),
      requestAnimationFrameRef:typeof requestAnimationFrame==='function'?requestAnimationFrame:(cb=>setTimeout(cb,0)),
      taskDictationPrompt:TASK_DICTATION_PROMPT,
      taskDictationAudioBitsPerSecond:TASK_DICTATION_AUDIO_BITS_PER_SECOND,
      runActiveStatusValues:RUN_ACTIVE_STATUS_VALUES,
    })
    : {};
  const DASHBOARD_DEPLOYMENTS=OPS_MODULES.deployments&&typeof OPS_MODULES.deployments.bindDashboard==='function'
    ? OPS_MODULES.deployments.bindDashboard({
      OPS,
      api:typeof api==='function'?api:null,
      projectUrl,
      renderCurrentOpsView,
      showToast:typeof showToast==='function'?showToast:()=>{},
      showPromptDialog:typeof showPromptDialog==='function'?showPromptDialog:(async()=>null),
      showConfirmDialog:typeof showConfirmDialog==='function'?showConfirmDialog:(async()=>false),
      esc:typeof esc==='function'?esc:(value=>String(value??'')),
      svg,
    })
    : {};
  const DASHBOARD_GIT=OPS_MODULES.git&&typeof OPS_MODULES.git.bindDashboard==='function'
    ? OPS_MODULES.git.bindDashboard({
      OPS,
      api:typeof api==='function'?api:null,
      projectUrl,
      renderCurrentOpsView,
      showToast:typeof showToast==='function'?showToast:()=>{},
      showConfirmDialog:typeof showConfirmDialog==='function'?showConfirmDialog:(async()=>false),
      esc:typeof esc==='function'?esc:(value=>String(value??'')),
      svg,
      nameOf:typeof nameOf==='function'?nameOf:(project=>String(project&&project.name||project&&project.id||'Project')),
      findProject:typeof findProject==='function'?findProject:null,
      newChatInProject:(project)=>newChatInProject(project),
      domLookup:typeof $==='function'?$:null,
      sendTurn:typeof send==='function'?send:null,
      autoResize:typeof autoResize==='function'?autoResize:null,
      getCurrentProject:()=>OPS.currentProject||null,
      loadProjects:typeof loadProjects==='function'?loadProjects:null,
      openProjectDetail:typeof openProjectDetail==='function'?openProjectDetail:null,
      renderProjects:typeof renderProjects==='function'?renderProjects:null,
    })
    : {};
  const DASHBOARD_NOTIFICATIONS=OPS_MODULES.notifications&&typeof OPS_MODULES.notifications.bindDashboard==='function'
    ? OPS_MODULES.notifications.bindDashboard({
      OPS,
      AgentBridge:typeof AgentBridge!=='undefined'?AgentBridge:null,
      renderCurrentOpsView,
      showToast:typeof showToast==='function'?showToast:()=>{},
      esc:typeof esc==='function'?esc:(value=>String(value??'')),
      svg,
      openProjectDetail:(projectId)=>openProjectDetail(projectId),
      openOpsSession:(sessionId)=>openOpsSession(sessionId),
      openRunTarget:(runId)=>openRunTarget(runId),
      loadRunDetail:(runId)=>loadRunDetail(runId),
      loadOpsRuns:(filters)=>loadOpsRuns(filters),
      windowRef:typeof window!=='undefined'?window:null,
      documentRef:typeof document!=='undefined'?document:null,
      NotificationRef:typeof Notification!=='undefined'?Notification:null,
      navigatorRef:typeof navigator!=='undefined'?navigator:null,
    })
    : {};
  const renderNotifications=DASHBOARD_NOTIFICATIONS.renderNotifications||function(){return '';};
  const loadNotifications=DASHBOARD_NOTIFICATIONS.loadNotifications||(async function(){return [];});
  const loadNotificationDiagnostics=DASHBOARD_NOTIFICATIONS.loadNotificationDiagnostics||(async function(){return null;});
  const startNotificationPolling=DASHBOARD_NOTIFICATIONS.startNotificationPolling||function(){};
  const stopNotificationPolling=DASHBOARD_NOTIFICATIONS.stopNotificationPolling||function(){};
  const toggleNotificationSetting=DASHBOARD_NOTIFICATIONS.toggleNotificationSetting||(async function(){return null;});
  const normalizedAutoApprovalPolicy=DASHBOARD_NOTIFICATIONS.normalizedAutoApprovalPolicy||function(){return {enabled:false,rules:[]};};
  const toggleAutoApprovalPolicy=DASHBOARD_NOTIFICATIONS.toggleAutoApprovalPolicy||(async function(){return null;});
  const deleteAutoApprovalRule=DASHBOARD_NOTIFICATIONS.deleteAutoApprovalRule||(async function(){return null;});
  const createAutoApprovalRule=DASHBOARD_NOTIFICATIONS.createAutoApprovalRule||(async function(){return null;});
  const clearNotificationLogs=DASHBOARD_NOTIFICATIONS.clearNotificationLogs||(async function(){return null;});
  const deletePushSubscription=DASHBOARD_NOTIFICATIONS.deletePushSubscription||(async function(){return null;});
  const subscribeBrowserPush=DASHBOARD_NOTIFICATIONS.subscribeBrowserPush||(async function(){return null;});
  const unsubscribeBrowserPush=DASHBOARD_NOTIFICATIONS.unsubscribeBrowserPush||(async function(){return null;});
  const sendTestPushNotification=DASHBOARD_NOTIFICATIONS.sendTestPushNotification||(async function(){return null;});
  const renderNotificationDiagnostics=DASHBOARD_NOTIFICATIONS.renderNotificationDiagnostics||function(){return '';};
  const notificationTitle=DASHBOARD_NOTIFICATIONS.notificationTitle||function(note){return String(note&&note.id||'Notification');};
  const notificationProjectLabel=DASHBOARD_NOTIFICATIONS.notificationProjectLabel||function(){return '';};
  const notificationTarget=DASHBOARD_NOTIFICATIONS.notificationTarget||function(){return {runId:'',sessionId:'',projectId:'',taskId:''};};
  const notificationHasRunTarget=DASHBOARD_NOTIFICATIONS.notificationHasRunTarget||function(){return false;};
  const notificationHasProjectTarget=DASHBOARD_NOTIFICATIONS.notificationHasProjectTarget||function(){return false;};
  const notificationMatchesRun=DASHBOARD_NOTIFICATIONS.notificationMatchesRun||function(){return false;};
  const pendingNotificationsForRun=DASHBOARD_NOTIFICATIONS.pendingNotificationsForRun||function(){return [];};
  const renderNotification=DASHBOARD_NOTIFICATIONS.renderNotification||function(){return '';};
  const playInspectOverlayUrl=DASHBOARD_NOTIFICATIONS.playInspectOverlayUrl||function(){return '';};
  const playNotificationFallbackError=DASHBOARD_NOTIFICATIONS.playNotificationFallbackError||function(){return '';};
  const respondNotification=DASHBOARD_NOTIFICATIONS.respondNotification||(async function(){return null;});
  const dismissNotification=DASHBOARD_NOTIFICATIONS.dismissNotification||(async function(){return null;});
  const notificationById=DASHBOARD_NOTIFICATIONS.notificationById||function(){return null;};
  const openSessionTargetOrProject=DASHBOARD_NOTIFICATIONS.openSessionTargetOrProject||(async function(){return false;});
  const openNotificationTarget=DASHBOARD_NOTIFICATIONS.openNotificationTarget||(async function(){return null;});
  const formatQuickTaskProjectOptionLabel=DASHBOARD_HOME.formatQuickTaskProjectOptionLabel||function(project){
    if(!project||typeof project!=='object')return 'Project';
    const name=String(project.name||project.fullName||project.slug||project.id||'Project').trim();
    return name||'Project';
  };
  const DASHBOARD_RUNS=OPS_MODULES.runs&&typeof OPS_MODULES.runs.bindDashboard==='function'
    ? OPS_MODULES.runs.bindDashboard({
      OPS,
      AgentBridge:typeof AgentBridge!=='undefined'?AgentBridge:null,
      renderCurrentOpsView,
      showToast:typeof showToast==='function'?showToast:()=>{},
      esc:typeof esc==='function'?esc:(value=>String(value??'')),
      svg,
      findProject:typeof findProject==='function'?findProject:null,
      formatProjectLabel:typeof formatQuickTaskProjectOptionLabel==='function'?formatQuickTaskProjectOptionLabel:null,
      findTaskInData:typeof findTaskInData==='function'?findTaskInData:null,
      renderNotification:(note)=>renderNotification(note),
      pendingNotificationsForRun:(run)=>pendingNotificationsForRun(run),
      openSessionTargetOrProject:(sessionId,projectId)=>openSessionTargetOrProject(sessionId,projectId),
      renderMd:typeof renderMd==='function'?renderMd:null,
    })
    : {};
  const loadOpsRuns=DASHBOARD_RUNS.loadOpsRuns||(async function(){return [];});
  const scanStaleRuns=DASHBOARD_RUNS.scanStaleRuns||(async function(){return null;});
  const renderProjectRunActivity=DASHBOARD_RUNS.renderProjectRunActivity||function(){return '';};
  const renderRunDetailPanel=DASHBOARD_RUNS.renderRunDetailPanel||function(){return '';};
  const loadRunDetail=DASHBOARD_RUNS.loadRunDetail||(async function(){return null;});
  const openRunDetail=DASHBOARD_RUNS.openRunDetail||(async function(){return null;});
  const closeRunDetail=DASHBOARD_RUNS.closeRunDetail||function(){};
  const setRunStatus=DASHBOARD_RUNS.setRunStatus||(async function(){return null;});
  const completeRun=DASHBOARD_RUNS.completeRun||(async function(){return null;});
  const respondRunRequest=DASHBOARD_RUNS.respondRunRequest||(async function(){return null;});
  const createRunArtifact=DASHBOARD_RUNS.createRunArtifact||(async function(){return null;});
  const openRunTarget=DASHBOARD_RUNS.openRunTarget||(async function(){return null;});
  const DASHBOARD_PLAY=OPS_MODULES.play&&typeof OPS_MODULES.play.bindDashboard==='function'
    ? OPS_MODULES.play.bindDashboard({
      OPS,
      api:typeof api==='function'?api:null,
      projectUrl,
      renderCurrentOpsView,
      showToast:typeof showToast==='function'?showToast:()=>{},
      esc:typeof esc==='function'?esc:(value=>String(value??'')),
      svg,
      AgentBridge:typeof AgentBridge!=='undefined'?AgentBridge:null,
      loadNotifications:(typeof loadNotifications==='function'?loadNotifications:null),
      playInspectOverlayUrl:(typeof playInspectOverlayUrl==='function'?playInspectOverlayUrl:null),
      openProjectDetail:typeof openProjectDetail==='function'?openProjectDetail:null,
      notificationById:typeof notificationById==='function'?notificationById:null,
      notificationTarget:typeof notificationTarget==='function'?notificationTarget:null,
      playNotificationFallbackError:typeof playNotificationFallbackError==='function'?playNotificationFallbackError:null,
      windowRef:typeof window!=='undefined'?window:null,
    })
    : {};
  const loadDatabaseSettings=DASHBOARD_DATABASE.loadDatabaseSettings||(async function(){return null;});
  const inspectDatabaseTables=DASHBOARD_DATABASE.inspectDatabaseTables||(async function(){return null;});
  const loadProjectDatabase=DASHBOARD_DATABASE.loadProjectDatabase||(async function(){return null;});
  const inspectProjectDatabase=DASHBOARD_DATABASE.inspectProjectDatabase||(async function(){return null;});
  const testProjectDatabase=DASHBOARD_DATABASE.testProjectDatabase||(async function(){return null;});
  const renderDatabasePanel=DASHBOARD_DATABASE.renderDatabasePanel||function(){return '';};
  const renderProjectDatabase=DASHBOARD_DATABASE.renderProjectDatabase||function(){return '';};
  const loadMigrationHealth=DASHBOARD_HEALTH.loadMigrationHealth||(async function(){return null;});
  const loadArtifactHealth=DASHBOARD_HEALTH.loadArtifactHealth||(async function(){return null;});
  const renderMigrationHealthPanel=DASHBOARD_HEALTH.renderMigrationHealthPanel||function(){return '';};
  const renderArtifactHealthPanel=DASHBOARD_HEALTH.renderArtifactHealthPanel||function(){return '';};
  const loadProjectDependencyStatus=DASHBOARD_HEALTH.loadProjectDependencyStatus||(async function(){return null;});
  const scanProjectInodes=DASHBOARD_HEALTH.scanProjectInodes||(async function(){return null;});
  const setProjectActivity=DASHBOARD_HEALTH.setProjectActivity||(async function(){return null;});
  const installProjectDependencies=DASHBOARD_HEALTH.installProjectDependencies||(async function(){return null;});
  const cleanupProjectNodeModules=DASHBOARD_HEALTH.cleanupProjectNodeModules||(async function(){return null;});
  const deleteProject=DASHBOARD_HEALTH.deleteProject||(async function(){return null;});
  const loadProjectGatherReports=DASHBOARD_HEALTH.loadProjectGatherReports||(async function(){return [];});
  const loadProjectReviewRequests=DASHBOARD_HEALTH.loadProjectReviewRequests||(async function(){return [];});
  const renderProjectGatherReports=DASHBOARD_HEALTH.renderProjectGatherReports||function(){return '';};
  const renderProjectReviewRequests=DASHBOARD_HEALTH.renderProjectReviewRequests||function(){return '';};
  const renderProjectHealth=DASHBOARD_HEALTH.renderProjectHealth||function(){return '';};
  const renderProjectSettings=DASHBOARD_HEALTH.renderProjectSettings||function(){return '';};
  const saveProjectSettings=DASHBOARD_HEALTH.saveProjectSettings||(async function(){return null;});
  const DASHBOARD_PROJECT_DETAIL=OPS_MODULES.projectDetail&&typeof OPS_MODULES.projectDetail.bindDashboard==='function'
    ? OPS_MODULES.projectDetail.bindDashboard({
      OPS,
      root:typeof root==='function'?root:null,
      esc:typeof esc==='function'?esc:(value=>String(value??'')),
      svg,
      setDashboardTopbar:typeof setDashboardTopbar==='function'?setDashboardTopbar:()=>{},
      showError:typeof showError==='function'?showError:()=>{},
      documentRef:typeof document!=='undefined'?document:null,
      windowRef:typeof window!=='undefined'?window:null,
      URLRef:typeof URL!=='undefined'?URL:null,
      taskQaStatusValues:TASK_QA_STATUS_VALUES,
      taskFilterStatusValues:TASK_FILTER_STATUS_VALUES,
      taskGradeValues:TASK_GRADE_VALUES,
      epicAccentPalette:EPIC_ACCENT_PALETTE,
      summarizeEpics:typeof summarizeEpics==='function'?summarizeEpics:null,
      nameOf:typeof nameOf==='function'?nameOf:null,
      projectPath:typeof projectPath==='function'?projectPath:null,
      projectProfileLabel:typeof projectProfileLabel==='function'?projectProfileLabel:null,
      rememberTaskFilterFocus:typeof rememberTaskFilterFocus==='function'?rememberTaskFilterFocus:null,
      restoreTaskFilterFocus:typeof restoreTaskFilterFocus==='function'?restoreTaskFilterFocus:null,
      syncEpicCollapseState:typeof syncEpicCollapseState==='function'?syncEpicCollapseState:null,
      isEpicCollapsed:typeof isEpicCollapsed==='function'?isEpicCollapsed:null,
      renderProjectPlayControls:(project,options)=>renderProjectPlayControls(project,options),
      renderProjectSettings:(project)=>renderProjectSettings(project),
      renderProjectHealth:(project)=>renderProjectHealth(project),
      renderProjectGitStatus:(project,options)=>renderProjectGitStatus(project,options),
      renderProjectPlayConfigEditor:(project)=>renderProjectPlayConfigEditor(project),
      renderProjectRuntimeSnapshot:(projectId)=>renderProjectRuntimeSnapshot(projectId),
      renderProjectRuntimeScreenshot:(projectId)=>renderProjectRuntimeScreenshot(projectId),
      renderProjectPlayLogs:(projectId)=>renderProjectPlayLogs(projectId),
      renderProjectGatherReports:(project)=>renderProjectGatherReports(project),
      renderProjectReviewRequests:(project)=>renderProjectReviewRequests(project),
      renderProjectDeployment:(project)=>renderProjectDeployment(project),
      renderProjectDatabase:(project)=>renderProjectDatabase(project),
      renderProjectRunActivity:(project)=>renderProjectRunActivity(project),
      renderRunDetailPanel:(options)=>renderRunDetailPanel(options),
      resolvedTaskSession:typeof resolvedTaskSession==='function'?resolvedTaskSession:null,
      sessionRefValue:typeof sessionRefValue==='function'?sessionRefValue:null,
      updateTaskGrade:(taskId,grade)=>updateTaskGrade(taskId,grade),
    })
    : {};
  const splitImageRefs=(value)=>DASHBOARD_PROJECT_DETAIL.splitImageRefs(value);
  const currentTaskFilters=()=>DASHBOARD_PROJECT_DETAIL.currentTaskFilters();
  const setTaskFilterStatus=(status)=>DASHBOARD_PROJECT_DETAIL.setTaskFilterStatus(status);
  const resetTaskFilters=()=>DASHBOARD_PROJECT_DETAIL.resetTaskFilters();
  const buildTaskLookup=(epics)=>DASHBOARD_PROJECT_DETAIL.buildTaskLookup(epics);
  const taskImageLabel=(ref)=>DASHBOARD_PROJECT_DETAIL.taskImageLabel(ref);
  const actionableTaskCount=(summary)=>DASHBOARD_PROJECT_DETAIL.actionableTaskCount(summary);
  const summarizeTaskFilters=(epics,taskById,filters)=>DASHBOARD_PROJECT_DETAIL.summarizeTaskFilters(epics,taskById,filters);
  const normalizeTaskQaStatus=(value)=>DASHBOARD_PROJECT_DETAIL.normalizeTaskQaStatus(value);
  const normalizeTaskGrade=(value)=>DASHBOARD_PROJECT_DETAIL.normalizeTaskGrade(value);
  const getTaskQaStatus=(task)=>DASHBOARD_PROJECT_DETAIL.getTaskQaStatus(task);
  const getTaskMoreWork=(task)=>DASHBOARD_PROJECT_DETAIL.getTaskMoreWork(task);
  const renderProjectDetail=()=>DASHBOARD_PROJECT_DETAIL.renderProjectDetail();
  const handleTaskFilterField=(event)=>DASHBOARD_PROJECT_DETAIL.handleTaskFilterField(event);
  const handleTaskRowField=(event)=>DASHBOARD_PROJECT_DETAIL.handleTaskRowField(event);
  const handleTaskFormField=(event)=>DASHBOARD_PROJECT_DETAIL.handleTaskFormField(event);
  const DASHBOARD_TASK_ACTIONS=OPS_MODULES.taskActions&&typeof OPS_MODULES.taskActions.bindDashboard==='function'
    ? OPS_MODULES.taskActions.bindDashboard({
      OPS,
      AgentBridge:typeof AgentBridge!=='undefined'?AgentBridge:null,
      api:typeof api==='function'?api:null,
      projectUrl,
      projectPath:typeof projectPath==='function'?projectPath:null,
      nameOf:typeof nameOf==='function'?nameOf:null,
      findProject:typeof findProject==='function'?findProject:null,
      findTask:typeof findTask==='function'?findTask:null,
      findTaskInData:typeof findTaskInData==='function'?findTaskInData:null,
      allTasks:typeof allTasks==='function'?allTasks:null,
      findSession:typeof findSession==='function'?findSession:null,
      sessionTaskId:typeof sessionTaskId==='function'?sessionTaskId:null,
      latestSessionForTask:typeof latestSessionForTask==='function'?latestSessionForTask:null,
      sessionRefValue:typeof sessionRefValue==='function'?sessionRefValue:null,
      normalizeTaskGrade:(value)=>normalizeTaskGrade(value),
      getTaskQaStatus:(task)=>getTaskQaStatus(task),
      getTaskMoreWork:(task)=>getTaskMoreWork(task),
      actionableTaskCount:(summary)=>actionableTaskCount(summary),
      summarizeTaskFilters:(epics,taskById,filters)=>summarizeTaskFilters(epics,taskById,filters),
      buildTaskLookup:(epics)=>buildTaskLookup(epics),
      renderProjectDetail:()=>renderProjectDetail(),
      loadProjectDetail:typeof loadProjectDetail==='function'?loadProjectDetail:null,
      refreshOpsSessions:typeof refreshOpsSessions==='function'?refreshOpsSessions:null,
      reloadProjectTasks:typeof reloadProjectTasks==='function'?reloadProjectTasks:null,
      loadProjects:typeof loadProjects==='function'?loadProjects:null,
      renderProjects:typeof renderProjects==='function'?renderProjects:null,
      renderHome:()=>renderHome(),
      loadSession:typeof loadSession==='function'?loadSession:null,
      renderSessionList:typeof renderSessionList==='function'?renderSessionList:null,
      closeOpsDashboard:typeof closeOpsDashboard==='function'?closeOpsDashboard:()=>{},
      showToast:typeof showToast==='function'?showToast:()=>{},
      showPromptDialog:typeof showPromptDialog==='function'?showPromptDialog:(async()=>null),
      showConfirmDialog:typeof showConfirmDialog==='function'?showConfirmDialog:(async()=>false),
      setBusy:typeof setBusy==='function'?setBusy:()=>{},
      domLookup:typeof $==='function'?$:null,
      documentRef:typeof document!=='undefined'?document:null,
      windowRef:typeof window!=='undefined'?window:null,
      FileReaderRef:typeof FileReader!=='undefined'?FileReader:null,
      SRef:()=>typeof S!=='undefined'?S:null,
      addFiles:typeof addFiles==='function'?addFiles:null,
      renderTray:typeof renderTray==='function'?renderTray:null,
      clearSessionReadableOutput:typeof clearSessionReadableOutput==='function'?clearSessionReadableOutput:null,
      clearPersistedSessionId:typeof clearPersistedSessionId==='function'?clearPersistedSessionId:null,
      sendTurn:typeof send==='function'?send:null,
      autoResize:typeof autoResize==='function'?autoResize:null,
      clearQuickTaskImages:()=>clearQuickTaskImages(),
      taskExecutionPreface:TASK_EXECUTION_PREFACE,
      taskExecutionInstructions:TASK_EXECUTION_INSTRUCTIONS,
      taskBatchExecutionPrompt:TASK_BATCH_EXECUTION_PROMPT,
      taskBatchInstructions:TASK_BATCH_INSTRUCTIONS,
    })
    : {};
  const uploadTaskImage=(taskId)=>DASHBOARD_TASK_ACTIONS.uploadTaskImage(taskId);
  const updateTaskGrade=(taskId,grade)=>DASHBOARD_TASK_ACTIONS.updateTaskGrade(taskId,grade);
  const markTaskNeedsMoreWork=(taskId)=>DASHBOARD_TASK_ACTIONS.markTaskNeedsMoreWork(taskId);
  const refreshDetail=()=>DASHBOARD_TASK_ACTIONS.refreshDetail();
  const newChatInProject=(projectOverride)=>DASHBOARD_TASK_ACTIONS.newChatInProject(projectOverride);
  const openOpsSession=(sessionId)=>DASHBOARD_TASK_ACTIONS.openOpsSession(sessionId);
  const setOpsSessionClosed=(sessionId,closed,projectId)=>DASHBOARD_TASK_ACTIONS.setOpsSessionClosed(sessionId,closed,projectId);
  const executeTask=(taskId,options)=>DASHBOARD_TASK_ACTIONS.executeTask(taskId,options);
  const executeReadyTasksWithAi=(projectId)=>DASHBOARD_TASK_ACTIONS.executeReadyTasksWithAi(projectId);
  const createQuickTask=(projectId,text)=>DASHBOARD_TASK_ACTIONS.createQuickTask(projectId,text);
  const clearQuickTaskImages=DASHBOARD_HOME.clearQuickTaskImages||function(){OPS.quickTaskImages=[];};
  const stopQuickTaskDictation=DASHBOARD_HOME.stopQuickTaskDictation||function(){};
  const renderHome=DASHBOARD_HOME.renderHome||function(){};
  const loadDashboardHome=DASHBOARD_HOME.loadDashboardHome||(async function(){return null;});
  const normalizeQuickTaskProjectSelection=DASHBOARD_HOME.normalizeQuickTaskProjectSelection||function(){
    const current=String(OPS.quickTaskProjectId||'').trim();
    return current;
  };
  const activeProjectSessionsFor=DASHBOARD_HOME.activeProjectSessionsFor||function(project){
    return projectSessionsFor(project,OPS.sessions);
  };
  const activeUngroupedSessions=DASHBOARD_HOME.activeUngroupedSessions||function(){
    return [];
  };
  const pendingRequestCountForSessions=DASHBOARD_HOME.pendingRequestCountForSessions||function(){
    return 0;
  };
  const renderSessionWorkspaceActions=DASHBOARD_HOME.renderSessionWorkspaceActions||function(){return '';};
  const renderSessionWorkspaceRow=DASHBOARD_HOME.renderSessionWorkspaceRow||function(){return '';};
  const renderHomeSessionOverview=DASHBOARD_HOME.renderHomeSessionOverview||function(){return '';};
  const renderProjectSessionRows=DASHBOARD_HOME.renderProjectSessionRows||function(){return '';};
  const renderProjectSessionRow=DASHBOARD_HOME.renderProjectSessionRow||function(){return '';};
  const renderGenericSessionRow=DASHBOARD_HOME.renderGenericSessionRow||function(){return '';};
  const handleHomeAction=DASHBOARD_HOME.handleHomeAction||(async function(){return false;});
  const handleHomeClick=DASHBOARD_HOME.handleHomeClick||function(){return false;};
  const handleHomeKeydown=DASHBOARD_HOME.handleHomeKeydown||function(){return false;};
  const handleQuickTaskField=DASHBOARD_HOME.handleQuickTaskField||function(){return false;};
  const loadProjectDeployment=DASHBOARD_DEPLOYMENTS.loadProjectDeployment||(async function(){return null;});
  const recordProjectDeployment=DASHBOARD_DEPLOYMENTS.recordProjectDeployment||(async function(){return null;});
  const executeProjectDeployment=DASHBOARD_DEPLOYMENTS.executeProjectDeployment||(async function(){return null;});
  const scaffoldProjectDeployment=DASHBOARD_DEPLOYMENTS.scaffoldProjectDeployment||(async function(){return null;});
  const renderProjectDeployment=DASHBOARD_DEPLOYMENTS.renderProjectDeployment||function(){return '';};
  const gitStatusFor=DASHBOARD_GIT.gitStatusFor||function(){return null;};
  const refreshProjectGitStatus=DASHBOARD_GIT.refreshProjectGitStatus||(async function(){return null;});
  const executeProjectGitOperation=DASHBOARD_GIT.executeProjectGitOperation||(async function(){return null;});
  const gitStatusKind=DASHBOARD_GIT.gitStatusKind||function(){return 'idle';};
  const gitStatusLabel=DASHBOARD_GIT.gitStatusLabel||function(){return 'Git status';};
  const gitStatusSummary=DASHBOARD_GIT.gitStatusSummary||function(){return 'Git status unavailable.';};
  const gitQuickBadgeState=DASHBOARD_GIT.gitQuickBadgeState||function(){return {label:'Branch',name:'...',title:'Git status',badgeClass:'inactive'};};
  const gitPrimaryActionState=DASHBOARD_GIT.gitPrimaryActionState||function(){return {mode:'loading',label:'Checking...',title:'Checking branch status...',action:'',icon:svg.refresh,disabled:true,badgeClass:'state-loading',statusLabel:'Checking',statusKind:'idle'};};
  const renderProjectGitQuickAction=DASHBOARD_GIT.renderProjectGitQuickAction||function(){return '';};
  const renderProjectGitStatus=DASHBOARD_GIT.renderProjectGitStatus||function(){return '';};
  const startGitConflictResolution=DASHBOARD_GIT.startGitConflictResolution||(async function(){return null;});
  const loadGitHubStatus=DASHBOARD_GIT.loadGitHubStatus||(async function(){return null;});
  const searchGitHubRepositories=DASHBOARD_GIT.searchGitHubRepositories||(async function(){return [];});
  const loadGitHubBranches=DASHBOARD_GIT.loadGitHubBranches||(async function(){return [];});
  const importGitHubRepository=DASHBOARD_GIT.importGitHubRepository||(async function(){return null;});
  const renderGitHubDiscovery=DASHBOARD_GIT.renderGitHubDiscovery||function(){return '';};
  const playStatusFor=DASHBOARD_PLAY.playStatusFor||function(projectId){return OPS.playStatusByProject[projectId]||null;};
  const isPlayRunning=DASHBOARD_PLAY.isPlayRunning||function(status){return !!(status&&status.running);};
  const shouldPollPlayStatus=DASHBOARD_PLAY.shouldPollPlayStatus||function(){return false;};
  const playStatusKind=DASHBOARD_PLAY.playStatusKind||function(){return 'idle';};
  const playStatusLabel=DASHBOARD_PLAY.playStatusLabel||function(){return 'Play status unavailable.';};
  const playStatusTitle=DASHBOARD_PLAY.playStatusTitle||function(){return 'Play status unavailable.';};
  const playStatusSummary=DASHBOARD_PLAY.playStatusSummary||function(){return 'Play status unavailable.';};
  const stopPlayStatusPolling=DASHBOARD_PLAY.stopPlayStatusPolling||function(){};
  const refreshProjectPlayStatus=DASHBOARD_PLAY.refreshProjectPlayStatus||(async function(){return null;});
  const showProjectPlayConfig=DASHBOARD_PLAY.showProjectPlayConfig||(async function(){return null;});
  const closeProjectPlayConfig=DASHBOARD_PLAY.closeProjectPlayConfig||function(){};
  const renderProjectPlayConfigEditor=DASHBOARD_PLAY.renderProjectPlayConfigEditor||function(){return '';};
  const renderProjectPlayControls=DASHBOARD_PLAY.renderProjectPlayControls||function(){return '';};
  const renderProjectPlayLogs=DASHBOARD_PLAY.renderProjectPlayLogs||function(){return '';};
  const renderProjectRuntimeSnapshot=DASHBOARD_PLAY.renderProjectRuntimeSnapshot||function(){return '';};
  const renderProjectRuntimeScreenshot=DASHBOARD_PLAY.renderProjectRuntimeScreenshot||function(){return '';};
  const startProjectPlay=DASHBOARD_PLAY.startProjectPlay||(async function(){return null;});
  const stopProjectPlay=DASHBOARD_PLAY.stopProjectPlay||(async function(){return null;});
  const restartProjectPlay=DASHBOARD_PLAY.restartProjectPlay||(async function(){return null;});
  const saveProjectPlayConfig=DASHBOARD_PLAY.saveProjectPlayConfig||(async function(){return null;});
  const captureProjectRuntimeSnapshot=DASHBOARD_PLAY.captureProjectRuntimeSnapshot||(async function(){return null;});
  const captureProjectRuntimeScreenshot=DASHBOARD_PLAY.captureProjectRuntimeScreenshot||(async function(){return null;});
  const openProjectPlay=DASHBOARD_PLAY.openProjectPlay||function(){return null;};
  const showProjectPlayLogs=DASHBOARD_PLAY.showProjectPlayLogs||(async function(){return null;});
  const openPlayNotification=DASHBOARD_PLAY.openPlayNotification||function(){return null;};
  const repairPlayNotification=DASHBOARD_PLAY.repairPlayNotification||(async function(){return null;});
  const DASHBOARD_QUICK_ACTIONS=OPS_MODULES.dashboardQuickActions&&typeof OPS_MODULES.dashboardQuickActions.bindDashboard==='function'
    ? OPS_MODULES.dashboardQuickActions.bindDashboard({
      OPS,
      esc:typeof esc==='function'?esc:(value=>String(value??'')),
      svg,
      playStatusFor:typeof playStatusFor==='function'?playStatusFor:null,
      isPlayRunning:typeof isPlayRunning==='function'?isPlayRunning:null,
      playStatusTitle:typeof playStatusTitle==='function'?playStatusTitle:null,
      playStatusLabel:typeof playStatusLabel==='function'?playStatusLabel:null,
    })
    : {};
  const DASHBOARD_PROJECTS=OPS_MODULES.projects&&typeof OPS_MODULES.projects.bindDashboard==='function'
    ? OPS_MODULES.projects.bindDashboard({
      OPS,
      api:typeof api==='function'?api:null,
      AgentBridge:typeof AgentBridge!=='undefined'?AgentBridge:null,
      root:typeof root==='function'?root:null,
      esc:typeof esc==='function'?esc:(value=>String(value??'')),
      svg,
      nameOf:typeof nameOf==='function'?nameOf:null,
      projectPath:typeof projectPath==='function'?projectPath:null,
      projectUrl:typeof projectUrl==='function'?projectUrl:null,
      projectProfileLabel:typeof projectProfileLabel==='function'?projectProfileLabel:null,
      renderProjectProfileOptions:typeof renderProjectProfileOptions==='function'?renderProjectProfileOptions:null,
      projectUsesBranchTitle:typeof projectUsesBranchTitle==='function'?projectUsesBranchTitle:null,
      projectCardTitle:typeof projectCardTitle==='function'?projectCardTitle:null,
      projectContextLabel:typeof projectContextLabel==='function'?projectContextLabel:null,
      projectAccentStyle:typeof projectAccentStyle==='function'?projectAccentStyle:null,
      setDashboardTopbar:typeof setDashboardTopbar==='function'?setDashboardTopbar:null,
      renderLoading:typeof renderLoading==='function'?renderLoading:null,
      renderGitHubDiscovery:typeof renderGitHubDiscovery==='function'?renderGitHubDiscovery:null,
      renderSessionWorkspaceActions:typeof renderSessionWorkspaceActions==='function'?renderSessionWorkspaceActions:null,
      renderProjectSessionRows:typeof renderProjectSessionRows==='function'?renderProjectSessionRows:null,
      showToast:typeof showToast==='function'?showToast:()=>{},
      resetTaskFilters:typeof resetTaskFilters==='function'?resetTaskFilters:null,
      renderProjectDetail:typeof renderProjectDetail==='function'?renderProjectDetail:null,
      refreshProjectPlayStatus:typeof refreshProjectPlayStatus==='function'?refreshProjectPlayStatus:null,
      refreshProjectGitStatus:typeof refreshProjectGitStatus==='function'?refreshProjectGitStatus:null,
      playStatusFor:typeof playStatusFor==='function'?playStatusFor:null,
      playStatusKind:typeof playStatusKind==='function'?playStatusKind:null,
      playStatusLabel:typeof playStatusLabel==='function'?playStatusLabel:null,
      loadOpsRuns:typeof loadOpsRuns==='function'?loadOpsRuns:null,
      loadProjectDependencyStatus:typeof loadProjectDependencyStatus==='function'?loadProjectDependencyStatus:null,
      loadProjectGatherReports:typeof loadProjectGatherReports==='function'?loadProjectGatherReports:null,
      loadProjectReviewRequests:typeof loadProjectReviewRequests==='function'?loadProjectReviewRequests:null,
      loadProjectDeployment:typeof loadProjectDeployment==='function'?loadProjectDeployment:null,
      loadProjectDatabase:typeof loadProjectDatabase==='function'?loadProjectDatabase:null,
    })
    : {};
  const DASHBOARD_ACTIONS=OPS_MODULES.dashboardActions&&typeof OPS_MODULES.dashboardActions.bindDashboard==='function'
    ? OPS_MODULES.dashboardActions.bindDashboard({
      OPS,
      root:typeof root==='function'?root:null,
      showError:typeof showError==='function'?showError:()=>{},
      setBusy:typeof setBusy==='function'?setBusy:()=>{},
      handleHomeAction:(action,btn)=>handleHomeAction(action,btn),
      loadMigrationHealth:typeof loadMigrationHealth==='function'?loadMigrationHealth:null,
      loadArtifactHealth:typeof loadArtifactHealth==='function'?loadArtifactHealth:null,
      scanStaleRuns:typeof scanStaleRuns==='function'?scanStaleRuns:null,
      loadNotificationDiagnostics:typeof loadNotificationDiagnostics==='function'?loadNotificationDiagnostics:null,
      toggleNotificationSetting:typeof toggleNotificationSetting==='function'?toggleNotificationSetting:null,
      clearNotificationLogs:typeof clearNotificationLogs==='function'?clearNotificationLogs:null,
      deletePushSubscription:typeof deletePushSubscription==='function'?deletePushSubscription:null,
      subscribeBrowserPush:typeof subscribeBrowserPush==='function'?subscribeBrowserPush:null,
      unsubscribeBrowserPush:typeof unsubscribeBrowserPush==='function'?unsubscribeBrowserPush:null,
      sendTestPushNotification:typeof sendTestPushNotification==='function'?sendTestPushNotification:null,
      toggleAutoApprovalPolicy:typeof toggleAutoApprovalPolicy==='function'?toggleAutoApprovalPolicy:null,
      deleteAutoApprovalRule:typeof deleteAutoApprovalRule==='function'?deleteAutoApprovalRule:null,
      loadDatabaseSettings:typeof loadDatabaseSettings==='function'?loadDatabaseSettings:null,
      inspectDatabaseTables:typeof inspectDatabaseTables==='function'?inspectDatabaseTables:null,
      loadProjects:typeof loadProjects==='function'?loadProjects:null,
      renderProjects:typeof renderProjects==='function'?renderProjects:null,
      loadGitHubStatus:typeof loadGitHubStatus==='function'?loadGitHubStatus:null,
      searchGitHubRepositories:typeof searchGitHubRepositories==='function'?searchGitHubRepositories:null,
      loadGitHubBranches:typeof loadGitHubBranches==='function'?loadGitHubBranches:null,
      importGitHubRepository:typeof importGitHubRepository==='function'?importGitHubRepository:null,
      openProjects:typeof openProjects==='function'?openProjects:null,
      openOpsDashboard:typeof openOpsDashboard==='function'?openOpsDashboard:null,
      openProjectDetail:typeof openProjectDetail==='function'?openProjectDetail:null,
      refreshDetail:typeof refreshDetail==='function'?refreshDetail:null,
      deleteProject:typeof deleteProject==='function'?deleteProject:null,
      setTaskFilterStatus:typeof setTaskFilterStatus==='function'?setTaskFilterStatus:null,
      renderProjectDetail:typeof renderProjectDetail==='function'?renderProjectDetail:null,
      executeReadyTasksWithAi:typeof executeReadyTasksWithAi==='function'?executeReadyTasksWithAi:null,
      setEpicCollapsed:typeof setEpicCollapsed==='function'?setEpicCollapsed:null,
      isEpicCollapsed:typeof isEpicCollapsed==='function'?isEpicCollapsed:null,
      executeTask:typeof executeTask==='function'?executeTask:null,
      showToast:typeof showToast==='function'?showToast:()=>{},
      markTaskNeedsMoreWork:typeof markTaskNeedsMoreWork==='function'?markTaskNeedsMoreWork:null,
      resetTaskFilters:typeof resetTaskFilters==='function'?resetTaskFilters:null,
      findTask:typeof findTask==='function'?findTask:null,
      uploadTaskImage:typeof uploadTaskImage==='function'?uploadTaskImage:null,
      newChatInProject:typeof newChatInProject==='function'?newChatInProject:null,
      findProject:typeof findProject==='function'?findProject:null,
      openOpsSession:typeof openOpsSession==='function'?openOpsSession:null,
      openRunTarget:typeof openRunTarget==='function'?openRunTarget:null,
      openRunDetail:typeof openRunDetail==='function'?openRunDetail:null,
      closeRunDetail:typeof closeRunDetail==='function'?closeRunDetail:null,
      setRunStatus:typeof setRunStatus==='function'?setRunStatus:null,
      completeRun:typeof completeRun==='function'?completeRun:null,
      setOpsSessionClosed:typeof setOpsSessionClosed==='function'?setOpsSessionClosed:null,
      repairPlayNotification:typeof repairPlayNotification==='function'?repairPlayNotification:null,
      startProjectPlay:typeof startProjectPlay==='function'?startProjectPlay:null,
      showProjectPlayConfig:typeof showProjectPlayConfig==='function'?showProjectPlayConfig:null,
      closeProjectPlayConfig:typeof closeProjectPlayConfig==='function'?closeProjectPlayConfig:null,
      refreshProjectGitStatus:typeof refreshProjectGitStatus==='function'?refreshProjectGitStatus:null,
      loadProjectDependencyStatus:typeof loadProjectDependencyStatus==='function'?loadProjectDependencyStatus:null,
      scanProjectInodes:typeof scanProjectInodes==='function'?scanProjectInodes:null,
      setProjectActivity:typeof setProjectActivity==='function'?setProjectActivity:null,
      installProjectDependencies:typeof installProjectDependencies==='function'?installProjectDependencies:null,
      cleanupProjectNodeModules:typeof cleanupProjectNodeModules==='function'?cleanupProjectNodeModules:null,
      startGitConflictResolution:typeof startGitConflictResolution==='function'?startGitConflictResolution:null,
      executeProjectGitOperation:typeof executeProjectGitOperation==='function'?executeProjectGitOperation:null,
      loadProjectGatherReports:typeof loadProjectGatherReports==='function'?loadProjectGatherReports:null,
      loadProjectReviewRequests:typeof loadProjectReviewRequests==='function'?loadProjectReviewRequests:null,
      loadProjectDeployment:typeof loadProjectDeployment==='function'?loadProjectDeployment:null,
      scaffoldProjectDeployment:typeof scaffoldProjectDeployment==='function'?scaffoldProjectDeployment:null,
      recordProjectDeployment:typeof recordProjectDeployment==='function'?recordProjectDeployment:null,
      executeProjectDeployment:typeof executeProjectDeployment==='function'?executeProjectDeployment:null,
      loadProjectDatabase:typeof loadProjectDatabase==='function'?loadProjectDatabase:null,
      testProjectDatabase:typeof testProjectDatabase==='function'?testProjectDatabase:null,
      inspectProjectDatabase:typeof inspectProjectDatabase==='function'?inspectProjectDatabase:null,
      captureProjectRuntimeSnapshot:typeof captureProjectRuntimeSnapshot==='function'?captureProjectRuntimeSnapshot:null,
      captureProjectRuntimeScreenshot:typeof captureProjectRuntimeScreenshot==='function'?captureProjectRuntimeScreenshot:null,
      restartProjectPlay:typeof restartProjectPlay==='function'?restartProjectPlay:null,
      stopProjectPlay:typeof stopProjectPlay==='function'?stopProjectPlay:null,
      openProjectPlay:typeof openProjectPlay==='function'?openProjectPlay:null,
      showProjectPlayLogs:typeof showProjectPlayLogs==='function'?showProjectPlayLogs:null,
      openPlayNotification:typeof openPlayNotification==='function'?openPlayNotification:null,
      openNotificationTarget:typeof openNotificationTarget==='function'?openNotificationTarget:null,
      dismissNotification:typeof dismissNotification==='function'?dismissNotification:null,
      respondNotification:typeof respondNotification==='function'?respondNotification:null,
      respondRunRequest:typeof respondRunRequest==='function'?respondRunRequest:null,
      resolvedTaskSession:typeof resolvedTaskSession==='function'?resolvedTaskSession:null,
      sessionRefValue:typeof sessionRefValue==='function'?sessionRefValue:null,
      AgentBridge:typeof AgentBridge!=='undefined'?AgentBridge:null,
      refreshOpsSessions:typeof refreshOpsSessions==='function'?refreshOpsSessions:null,
      api:typeof api==='function'?api:null,
      projectUrl:typeof projectUrl==='function'?projectUrl:null,
      showConfirmDialog:typeof showConfirmDialog==='function'?showConfirmDialog:(async()=>false),
      createRunArtifact:typeof createRunArtifact==='function'?createRunArtifact:null,
      saveProjectPlayConfig:typeof saveProjectPlayConfig==='function'?saveProjectPlayConfig:null,
      createQuickTask:typeof createQuickTask==='function'?createQuickTask:null,
      createAutoApprovalRule:typeof createAutoApprovalRule==='function'?createAutoApprovalRule:null,
      saveProjectSettings:typeof saveProjectSettings==='function'?saveProjectSettings:null,
      splitList:typeof splitList==='function'?splitList:null,
      splitImageRefs:typeof splitImageRefs==='function'?splitImageRefs:null,
    })
    : {};

  function root(){return $('opsDashboardRoot');}
  function layout(){return document.querySelector('.layout');}
  function navBtn(){return $('opsDashboardNavBtn');}
  function getNavigatorRef(){
    if(typeof navigator!=='undefined')return navigator;
    if(typeof window!=='undefined'&&window&&typeof window.navigator!=='undefined')return window.navigator;
    return null;
  }
  function nameOf(project){return (project&&(project.fullName||project.name||project.slug||project.id))||'Project';}
  function projectPath(project){return (project&&(project.resolvedPath||project.path))||'';}
  function normalizePath(value){return String(value||'').replace(/\/+$/,'');}
  function splitList(value){return String(value||'').split(/[,\s]+/).map(v=>v.trim()).filter(Boolean);}
  function projectUrl(projectId,suffix){return `/api/ops/projects/${encodeURIComponent(projectId)}${suffix||''}`;}
  function setBusy(busy){OPS.loading=busy;const el=root();if(el)el.classList.toggle('is-loading',!!busy);}
  function showError(err){showToast(err&&err.message?err.message:String(err||'Failed'),4200);}

  function renderProjectPlayQuickAction(project){return DASHBOARD_QUICK_ACTIONS.renderProjectPlayQuickAction(project);}

  function renderProjectActivityQuickAction(project){return DASHBOARD_QUICK_ACTIONS.renderProjectActivityQuickAction(project);}

  function openProjects(options){return DASHBOARD_PROJECTS.openProjects(options);}
  async function loadProjects(){return DASHBOARD_PROJECTS.loadProjects();}
  function mergeProjectUpdate(project){return DASHBOARD_PROJECTS.mergeProjectUpdate(project);}
  function summarizeEpics(epics){return DASHBOARD_PROJECTS.summarizeEpics(epics);}
  function sessionProjectId(session){return DASHBOARD_PROJECTS.sessionProjectId(session);}
  function sessionTaskId(session){return DASHBOARD_PROJECTS.sessionTaskId(session);}
  function sessionRecencyValue(session){return DASHBOARD_PROJECTS.sessionRecencyValue(session);}
  function isSessionForProject(session,project){return DASHBOARD_PROJECTS.isSessionForProject(session,project);}
  function canonicalTaskSessions(sessions,projectId){return DASHBOARD_PROJECTS.canonicalTaskSessions(sessions,projectId);}
  function projectSessionsFor(project,sessions){return DASHBOARD_PROJECTS.projectSessionsFor(project,sessions);}
  function latestSessionForTask(taskId,projectId,sessionsOverride){return DASHBOARD_PROJECTS.latestSessionForTask(taskId,projectId,sessionsOverride);}
  function resolvedTaskSession(task,projectId,sessionsOverride){return DASHBOARD_PROJECTS.resolvedTaskSession(task,projectId,sessionsOverride);}
  function projectWorkspaceMeta(project,counts){return DASHBOARD_PROJECTS.projectWorkspaceMeta(project,counts);}
  function renderProjectWorkspaceCard(project,index){return DASHBOARD_PROJECTS.renderProjectWorkspaceCard(project,index);}
  function renderProjects(){return DASHBOARD_PROJECTS.renderProjects();}
  async function openProjectDetail(projectId,options){return DASHBOARD_PROJECTS.openProjectDetail(projectId,options);}
  async function loadProjectDetail(projectId){return DASHBOARD_PROJECTS.loadProjectDetail(projectId);}
  function allTasks(projectId){return DASHBOARD_PROJECTS.allTasks(projectId);}
  function findTask(taskId){return DASHBOARD_PROJECTS.findTask(taskId);}
  function findTaskInData(data,taskId){return DASHBOARD_PROJECTS.findTaskInData(data,taskId);}
  async function reloadProjectTasks(projectId){return DASHBOARD_PROJECTS.reloadProjectTasks(projectId);}

  function sessionRefValue(sessionLike){
    if(!sessionLike)return '';
    if(typeof sessionLike==='string')return String(sessionLike).trim();
    return String(sessionLike.sessionKey||sessionLike.session_id||sessionLike.sessionId||sessionLike.id||'').trim();
  }

  function findSession(sessionId){
    const sid=sessionRefValue(sessionId);
    return (OPS.sessions||[]).find(session=>sessionRefValue(session)===sid)||null;
  }

  async function refreshOpsSessions(){return DASHBOARD_PROJECTS.refreshOpsSessions();}

  function formatSessionTime(session){
    const stamp=(Number(session&&session.updated_at)||Number(session&&session.created_at)||0)*1000;
    if(!stamp)return 'No activity yet';
    try{
      return new Intl.DateTimeFormat(undefined,{
        month:'short',
        day:'numeric',
        hour:'numeric',
        minute:'2-digit',
      }).format(new Date(stamp));
    }catch(e){
      return new Date(stamp).toLocaleString();
    }
  }

  function findProject(projectId){
    return (OPS.projects||[]).find(project=>project.id===projectId)||null;
  }
  function handleHomeClickEvent(event){return handleHomeClick(event);}
  function handleHomeKeydownEvent(event){return handleHomeKeydown(event);}
  async function handleClick(event){return DASHBOARD_ACTIONS.handleClick(event);}
  async function handleSubmit(event){return DASHBOARD_ACTIONS.handleSubmit(event);}

  document.addEventListener('click',handleHomeClickEvent);
  document.addEventListener('keydown',handleHomeKeydownEvent);
  document.addEventListener('click',handleClick);
  document.addEventListener('submit',handleSubmit);
  document.addEventListener('input',handleQuickTaskField);
  document.addEventListener('input',handleTaskFilterField);
  document.addEventListener('input',handleTaskFormField);
  document.addEventListener('change',handleTaskFilterField);
  document.addEventListener('change',handleTaskFormField);
  document.addEventListener('change',handleTaskRowField);
  document.addEventListener('change',handleQuickTaskField);

  if(typeof window!=='undefined'){
    window.__opsLegacyHandleHistoryState=(state)=>restoreStandaloneOpsHistoryState(state);
  }
  window.openOpsDashboard=openOpsDashboard;
  window.closeOpsDashboard=closeOpsDashboard;
})();

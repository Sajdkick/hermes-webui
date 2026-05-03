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

  function mount(root,shellPayload){
    const state={
      shellPayload:shellPayload||{},
      projectsOpen:false,
      loadingProjects:false,
      creatingProject:false,
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
      inspectError:'',
      inspectBusyAction:'',
      loadingPlayConfig:false,
      playConfigDoc:null,
      savingPlayConfig:false,
      playLogs:null,
      loadingPlayLogs:false,
      playError:'',
      playBusyAction:'',
      showPlayConfig:false,
      showPlayLogs:false,
      loadingNotifications:false,
      notifications:[],
      notificationsError:'',
      respondingNotificationKey:'',
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
      if(kind==='select-project'){
        state.selectedProjectId=action.getAttribute('data-project-id')||'';
        state.gitStatus=null;
        state.gitError='';
        state.playConfigDoc=null;
        state.playLogs=null;
        state.playError='';
        state.inspectError='';
        state.inspectBusyAction='';
        state.showPlayConfig=false;
        state.showPlayLogs=false;
        loadTasks(root,state);
        loadGitStatus(root,state);
        loadRuntimeSummary(root,state);
        return;
      }
      if(kind==='refresh-projects'){
        loadProjects(root,state,true);
        return;
      }
      if(kind==='refresh-notifications'){
        loadNotifications(root,state);
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
      if(kind==='show-play-config'){
        loadPlayConfig(root,state,true);
        return;
      }
      if(kind==='close-play-config'){
        state.showPlayConfig=false;
        render(root,state);
        return;
      }
      if(kind==='reload-play-config'){
        loadPlayConfig(root,state,true);
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
      if(form.matches('[data-ops-form="play-config"]')){
        event.preventDefault();
        savePlayConfig(root,state,new FormData(form));
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
  }

  async function api(path,options){
    const requestOptions={credentials:'same-origin',headers:{}};
    if(options && options.method)requestOptions.method=options.method;
    if(options && options.body!==undefined){
      requestOptions.headers['Content-Type']='application/json';
      requestOptions.body=JSON.stringify(options.body||{});
    }
    const response=await fetch(path,requestOptions);
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

  async function loadPlayConfig(root,state,showPanel){
    if(!state.selectedProjectId)return;
    state.loadingPlayConfig=true;
    if(showPanel)state.showPlayConfig=true;
    state.playError='';
    render(root,state);
    try{
      state.playConfigDoc=await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/play/config');
    }catch(error){
      state.playError=error && error.message ? error.message : 'Could not load Play config.';
    }finally{
      state.loadingPlayConfig=false;
      render(root,state);
    }
  }

  async function savePlayConfig(root,state,formData){
    if(!state.selectedProjectId)return;
    state.savingPlayConfig=true;
    state.playError='';
    render(root,state);
    try{
      const payload=await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/play/config',{
        method:'POST',
        body:{content:formData.get('content')},
      });
      if(payload){
        state.playConfigDoc={
          ...(state.playConfigDoc||{}),
          ...payload,
          content:String(formData.get('content')||''),
        };
      }
      await loadRuntimeSummary(root,state);
    }catch(error){
      state.playError=error && error.message ? error.message : 'Could not save Play config.';
      state.savingPlayConfig=false;
      render(root,state);
      return;
    }
    state.savingPlayConfig=false;
    render(root,state);
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
      if(typeof window.location.assign==='function'){
        window.location.assign(target);
        return;
      }
      window.location.href=target;
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
    const tasksData=state.tasksData && Array.isArray(state.tasksData.epics) ? state.tasksData : null;
    const existing=tasksData && tasksData.epics.find(function(epic){
      return String(epic.title||'').trim().toLowerCase()==='quick tasks';
    });
    if(existing && existing.id)return existing.id;
    const created=await api(apiBase+'/'+encodeURIComponent(state.selectedProjectId)+'/epics',{
      method:'POST',
      body:{title:'Quick tasks'}
    });
    const epicId=created && created.epic ? created.epic.id : '';
    if(!epicId)throw new Error('Could not create the Quick tasks epic.');
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
        if(typeof window.location.assign==='function'){
          window.location.assign(target);
          return;
        }
        window.location.href=target;
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
    const projectsButtonLabel=state.projectsOpen ? 'Hide projects' : 'Projects';
    const selectedProject=state.projects.find(function(project){return project.id===state.selectedProjectId;}) || null;
    const tasksData=state.tasksData && state.tasksData.project && state.tasksData.project.id===state.selectedProjectId ? state.tasksData : null;
    const projectSection=state.projectsOpen ? renderProjectsSection(state,selectedProject,tasksData) : '';
    const notificationsSection=renderNotificationsSection(state);
    root.innerHTML=[
      '<div class="ops-shell-status">',
      '<span class="ops-shell-status-badge">Ready for clean project, task, session, readable-output, workflow inbox, and runtime evidence work</span>',
      '<div class="ops-shell-grid">',
      '<div class="ops-shell-card"><strong>Phase</strong><span>'+escapeHtml(state.shellPayload.phase||'phase-7')+'</span></div>',
      '<div class="ops-shell-card"><strong>Route</strong><span>'+escapeHtml(state.shellPayload.route||'/ops')+'</span></div>',
      '<div class="ops-shell-card"><strong>API base</strong><span>'+escapeHtml(state.shellPayload.apiBase||'/api/ops')+'</span></div>',
      '<div class="ops-shell-card"><strong>Version</strong><span>'+escapeHtml(state.shellPayload.version||'')+'</span></div>',
      '</div>',
      '<div class="ops-projects-shell">',
      notificationsSection,
      '<div class="ops-project-toolbar">',
      '<button class="ops-shell-link primary" type="button" data-ops-action="toggle-projects">'+escapeHtml(projectsButtonLabel)+'</button>',
      '<button class="ops-shell-link" type="button" data-ops-action="refresh-projects">Refresh</button>',
      '</div>',
      state.error?'<p class="ops-shell-error">'+escapeHtml(state.error)+'</p>':'',
      projectSection,
      '</div>',
      '</div>'
    ].join('');
  }

  function renderNotificationsSection(state){
    if(window.HermesOpsNotifications && typeof window.HermesOpsNotifications.renderSection==='function'){
      return window.HermesOpsNotifications.renderSection(state);
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
    const epicRows=state.loadingTasks
      ? '<p class="ops-shell-loading">Loading tasks…</p>'
      : epics.length
        ? epics.map(function(epic){return renderEpicCard(epic,state);}).join('')
        : '<p class="ops-shell-loading">No epics yet for this branch.</p>';
    return [
      '<div class="ops-project-column-header"><h2>'+escapeHtml(selectedProject.name||'Project')+'</h2><span>'+escapeHtml(selectedProject.tasksBranch||selectedProject.coreBranch||'')+'</span></div>',
      '<div class="ops-project-meta">',
      '<span><strong>Path</strong>'+escapeHtml(selectedProject.path||'')+'</span>',
      '<span><strong>Tasks file</strong>'+escapeHtml(selectedProject.tasksFilePath||'')+'</span>',
      '<span><strong>Profile</strong>'+escapeHtml(selectedProject.profile||'default')+'</span>',
      '<span><strong>Default model</strong>'+escapeHtml(selectedProject.defaultModel||'profile default')+'</span>',
      '</div>',
      renderProjectDefaultsForm(state,selectedProject),
      renderGitStatusSection(state,selectedProject),
      renderRuntimeSection(state,selectedProject),
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
        loadingPlayConfig:state.loadingPlayConfig,
        playConfigDoc:state.playConfigDoc,
        savingPlayConfig:state.savingPlayConfig,
        playLogs:state.playLogs,
        loadingPlayLogs:state.loadingPlayLogs,
        playError:state.playError,
        playBusyAction:state.playBusyAction,
        showPlayConfig:state.showPlayConfig,
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
      return '<a class="ops-task-session-link" href="'+escapeHtml(href)+'">'+escapeHtml(title+suffix)+'</a>';
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
      latest ? '<a class="ops-shell-link" href="'+escapeHtml(String(latest.sessionUrl||sessionUrlFor(latest.sessionId)))+'">Resume latest</a>' : '',
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
    return sid ? '/session/'+encodeURIComponent(sid) : '/';
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

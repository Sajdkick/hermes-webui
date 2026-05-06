(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};

  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const api=ctx&&ctx.api;
    const AgentBridgeRef=ctx&&ctx.AgentBridge;
    const root=ctx&&ctx.root;
    const esc=ctx&&ctx.esc;
    const svg=ctx&&ctx.svg;
    const nameOf=ctx&&ctx.nameOf;
    const projectPath=ctx&&ctx.projectPath;
    const projectUrl=ctx&&ctx.projectUrl;
    const projectProfileLabel=ctx&&ctx.projectProfileLabel;
    const renderProjectProfileOptions=ctx&&ctx.renderProjectProfileOptions;
    const projectUsesBranchTitle=ctx&&ctx.projectUsesBranchTitle;
    const projectCardTitle=ctx&&ctx.projectCardTitle;
    const projectContextLabel=ctx&&ctx.projectContextLabel;
    const projectAccentStyle=ctx&&ctx.projectAccentStyle;
    const setDashboardTopbar=ctx&&ctx.setDashboardTopbar;
    const renderLoading=ctx&&ctx.renderLoading;
    const renderGitHubDiscovery=ctx&&ctx.renderGitHubDiscovery;
    const renderSessionWorkspaceActions=ctx&&ctx.renderSessionWorkspaceActions;
    const renderProjectSessionRows=ctx&&ctx.renderProjectSessionRows;
    const showToast=ctx&&ctx.showToast;
    const resetTaskFilters=ctx&&ctx.resetTaskFilters;
    const renderProjectDetail=ctx&&ctx.renderProjectDetail;
    const refreshProjectPlayStatus=ctx&&ctx.refreshProjectPlayStatus;
    const refreshProjectGitStatus=ctx&&ctx.refreshProjectGitStatus;
    const playStatusFor=ctx&&ctx.playStatusFor;
    const playStatusKind=ctx&&ctx.playStatusKind;
    const playStatusLabel=ctx&&ctx.playStatusLabel;
    const loadOpsRuns=ctx&&ctx.loadOpsRuns;
    const loadProjectDependencyStatus=ctx&&ctx.loadProjectDependencyStatus;
    const loadProjectGatherReports=ctx&&ctx.loadProjectGatherReports;
    const loadProjectReviewRequests=ctx&&ctx.loadProjectReviewRequests;
    const loadProjectDeployment=ctx&&ctx.loadProjectDeployment;
    const loadProjectDatabase=ctx&&ctx.loadProjectDatabase;
    const windowRef=(ctx&&ctx.windowRef)||window;
    if(
      !OPS
      || typeof api!=='function'
      || !AgentBridgeRef
      || !AgentBridgeRef.sessions
      || !AgentBridgeRef.profiles
      || typeof root!=='function'
      || typeof esc!=='function'
      || !svg
      || typeof nameOf!=='function'
      || typeof projectPath!=='function'
      || typeof projectUrl!=='function'
      || typeof projectProfileLabel!=='function'
      || typeof renderProjectProfileOptions!=='function'
      || typeof projectUsesBranchTitle!=='function'
      || typeof projectCardTitle!=='function'
      || typeof projectContextLabel!=='function'
      || typeof projectAccentStyle!=='function'
      || typeof setDashboardTopbar!=='function'
      || typeof renderLoading!=='function'
      || typeof renderGitHubDiscovery!=='function'
      || typeof renderSessionWorkspaceActions!=='function'
      || typeof renderProjectSessionRows!=='function'
      || typeof showToast!=='function'
      || typeof resetTaskFilters!=='function'
      || typeof renderProjectDetail!=='function'
      || typeof refreshProjectPlayStatus!=='function'
      || typeof refreshProjectGitStatus!=='function'
      || typeof playStatusFor!=='function'
      || typeof playStatusKind!=='function'
      || typeof playStatusLabel!=='function'
      || typeof loadOpsRuns!=='function'
      || typeof loadProjectDependencyStatus!=='function'
      || typeof loadProjectGatherReports!=='function'
      || typeof loadProjectReviewRequests!=='function'
      || typeof loadProjectDeployment!=='function'
      || typeof loadProjectDatabase!=='function'
    ){
      return {};
    }

    let activeProjectsLoadToken=0;

    function syncStandaloneOpsHistory(view,projectId){
      if(!windowRef||typeof windowRef.__opsLegacySyncHistoryState!=='function')return;
      const current=typeof windowRef.__opsLegacyReadHistoryState==='function'
        ? windowRef.__opsLegacyReadHistoryState(windowRef.history&&windowRef.history.state)
        : null;
      windowRef.__opsLegacySyncHistoryState(view,projectId,{mode:current?'push':'replace'});
    }

    function normalizePath(value){
      return String(value||'').replace(/\/+$/,'');
    }

    function currentProjectCounts(projectId){
      const key=String(projectId||'').trim();
      const value=key&&OPS.counts&&OPS.counts[key];
      return value&&typeof value==='object'?value:{};
    }

    function numericProjectCount(summary,key){
      const value=Number(summary&&summary[key]);
      return Number.isFinite(value)?value:null;
    }

    function visibleProjectsView(){
      return OPS.view==='projects'&&!!root();
    }

    function rerenderProjectsView(){
      if(visibleProjectsView())renderProjects();
    }

    function setProjectsHydrationPending(count){
      const normalized=Math.max(0,Number(count)||0);
      OPS.projectsHydrationPending=normalized;
      OPS.projectsHydrating=normalized>0;
    }

    function consumeProjectsHydrationPending(token){
      if(token!==activeProjectsLoadToken)return;
      setProjectsHydrationPending((Number(OPS.projectsHydrationPending)||0)-1);
    }

    function projectSessionCount(project){
      return projectSessionsFor(project,OPS.sessions).length;
    }

    function seedProjectHydrationState(projects){
      const existingTaskData=OPS.taskDataByProject&&typeof OPS.taskDataByProject==='object'?OPS.taskDataByProject:{};
      const nextTaskData={};
      const nextCounts={};
      (projects||[]).forEach(project=>{
        if(!project||!project.id)return;
        const current=currentProjectCounts(project.id);
        if(existingTaskData[project.id])nextTaskData[project.id]=existingTaskData[project.id];
        nextCounts[project.id]={
          ...current,
          sessions:numericProjectCount(current,'sessions') ?? projectSessionCount(project),
          loading:true,
        };
      });
      OPS.counts=nextCounts;
      OPS.taskDataByProject=nextTaskData;
      setProjectsHydrationPending((projects||[]).length+1);
    }

    async function hydrateProjectSessions(projects,token){
      try{
        const groupsData=await AgentBridgeRef.sessions.grouped();
        if(token!==activeProjectsLoadToken)return;
        OPS.sessionGroups=groupsData;
        OPS.sessions=Array.isArray(groupsData&&groupsData.sessions)?groupsData.sessions:[];
      }catch(e){
        if(token!==activeProjectsLoadToken)return;
        OPS.sessionGroups=null;
        try{
          const sessionsData=await AgentBridgeRef.sessions.list();
          if(token!==activeProjectsLoadToken)return;
          OPS.sessions=Array.isArray(sessionsData&&sessionsData.sessions)?sessionsData.sessions:[];
        }catch(err){
          if(token!==activeProjectsLoadToken)return;
          OPS.sessions=[];
        }
      }finally{
        if(token!==activeProjectsLoadToken)return;
        (projects||[]).forEach(project=>{
          if(!project||!project.id)return;
          OPS.counts[project.id]={
            ...currentProjectCounts(project.id),
            sessions:projectSessionCount(project),
          };
        });
        consumeProjectsHydrationPending(token);
        rerenderProjectsView();
      }
    }

    async function hydrateProjectWorkspace(project,token){
      const projectId=String(project&&project.id||'').trim();
      if(!projectId){
        consumeProjectsHydrationPending(token);
        return;
      }
      const playResult=refreshProjectPlayStatus(projectId,{render:false});
      const gitResult=refreshProjectGitStatus(projectId,{render:false});
      try{
        const tasks=await api(projectUrl(projectId,'/tasks'));
        if(token!==activeProjectsLoadToken)return;
        OPS.taskDataByProject[projectId]=tasks;
        OPS.counts[projectId]={
          ...currentProjectCounts(projectId),
          ...summarizeEpics(tasks.epics||[]),
          sessions:numericProjectCount(currentProjectCounts(projectId),'sessions') ?? projectSessionCount(project),
          error:'',
          loading:false,
        };
      }catch(e){
        if(token!==activeProjectsLoadToken)return;
        OPS.counts[projectId]={
          ...currentProjectCounts(projectId),
          active:0,
          done:0,
          archived:0,
          total:0,
          epics:0,
          sessions:numericProjectCount(currentProjectCounts(projectId),'sessions') ?? projectSessionCount(project),
          error:e.message||'Unavailable',
          loading:false,
        };
      }finally{
        await Promise.allSettled([playResult,gitResult]);
        if(token!==activeProjectsLoadToken)return;
        consumeProjectsHydrationPending(token);
        rerenderProjectsView();
      }
    }

    function projectSessionRefValue(sessionLike){
      if(!sessionLike)return '';
      if(typeof sessionLike==='string')return String(sessionLike).trim();
      return String(sessionLike.sessionKey||sessionLike.session_id||sessionLike.sessionId||'').trim();
    }

    function summarizeEpics(epics){
      const counts={epics:epics.length,active:0,done:0,archived:0,total:0};
      epics.forEach(epic=>(epic.tasks||[]).forEach(task=>{
        counts.total++;
        if(task.archived)counts.archived++;
        else if(task.done)counts.done++;
        else counts.active++;
      }));
      return counts;
    }

    function mergeProjectUpdate(project){
      if(!project||!project.id)return project;
      OPS.projects=(OPS.projects||[]).map(entry=>entry&&entry.id===project.id?{...entry,...project}:entry);
      if(OPS.currentProject&&OPS.currentProject.id===project.id)OPS.currentProject={...OPS.currentProject,...project};
      if(OPS.taskData&&OPS.taskData.project&&OPS.taskData.project.id===project.id){
        OPS.taskData={...OPS.taskData,project:{...OPS.taskData.project,...project}};
      }
      return project;
    }

    function findProject(projectId){
      return (OPS.projects||[]).find(project=>project&&project.id===projectId)||null;
    }

    function isNotFoundError(error){
      return String(error&&error.message||'').trim().toLowerCase()==='not found';
    }

    function sessionProjectId(session){
      return String(session&&session.ops_project_id||session&&session.projectId||'').trim();
    }

    function sessionTaskId(session){
      return String(session&&session.ops_task_id||session&&session.opsTaskId||session&&session.task_id||session&&session.taskId||'').trim();
    }

    function sessionRecencyValue(session){
      return Math.max(
        Number(session&&session.lastActivityAt)||0,
        Number(session&&session.lastOutputAt)||0,
        Number(session&&session.updated_at)||0,
        Number(session&&session.created_at)||0
      );
    }

    function isSessionForProject(session,project){
      if(!session||!project)return false;
      if(session.ops_project_id===project.id)return true;
      if(session.project_id===project.id)return true;
      const sessionWorkspace=normalizePath(session.workspace);
      const currentPath=normalizePath(projectPath(project));
      return !!currentPath&&!session.ops_project_id&&!session.project_id&&sessionWorkspace===currentPath;
    }

    function canonicalTaskSessions(sessions,projectId){
      const pid=String(projectId||'').trim();
      const taskBuckets=new Map();
      const passthrough=[];
      (sessions||[]).forEach(session=>{
        if(!session||session.archived)return;
        const taskId=sessionTaskId(session);
        const sessionProject=sessionProjectId(session);
        if(taskId&&(!pid||sessionProject===pid)){
          const key=`${sessionProject}:${taskId}`;
          const current=taskBuckets.get(key);
          if(!current||sessionRecencyValue(session)>sessionRecencyValue(current)){
            taskBuckets.set(key,session);
          }
          return;
        }
        passthrough.push(session);
      });
      return [...taskBuckets.values(),...passthrough].sort((left,right)=>sessionRecencyValue(right)-sessionRecencyValue(left));
    }

    function projectSessionsFor(project,sessions){
      const seen=new Set();
      return canonicalTaskSessions((sessions||[]).filter(session=>!session||session.archived?false:isSessionForProject(session,project)),project&&project.id)
        .filter(session=>{
          const key=projectSessionRefValue(session);
          if(!key)return true;
          if(seen.has(key))return false;
          seen.add(key);
          return true;
        })
        .sort((a,b)=>sessionRecencyValue(b)-sessionRecencyValue(a));
    }

    function latestSessionForTask(taskId,projectId,sessionsOverride){
      const tid=String(taskId||'').trim();
      const pid=String(projectId||'').trim();
      if(!tid||!pid)return null;
      const sessions=(Array.isArray(sessionsOverride)?sessionsOverride:(OPS.sessions||[]))
        .filter(session=>session&&!session.archived&&sessionProjectId(session)===pid&&sessionTaskId(session)===tid)
        .sort((left,right)=>sessionRecencyValue(right)-sessionRecencyValue(left));
      return sessions[0]||null;
    }

    function resolvedTaskSession(task,projectId,sessionsOverride){
      return latestSessionForTask(task&&task.id,projectId,sessionsOverride);
    }

    function projectWorkspaceMeta(project,counts){
      const summary=counts||{};
      const sessions=numericProjectCount(summary,'sessions');
      const active=numericProjectCount(summary,'active');
      const epics=numericProjectCount(summary,'epics');
      const done=numericProjectCount(summary,'done');
      const values=[
        sessions==null?(summary.loading?'Loading sessions...':''):`${sessions} active session${sessions===1?'':'s'}`,
        active==null?(summary.loading?'Loading task counts...':''):`${active} active task${active===1?'':'s'}`,
        epics==null?'':`Epics ${epics}`,
        done==null?'':`Done ${done}`,
        `Profile ${projectProfileLabel(project)}`,
        project&&project.active===false?'Inactive':'',
        summary.error?'Task data unavailable':'',
      ].filter(Boolean);
      return values.join(' • ');
    }

    function renderProjectWorkspaceCard(project,index){
      const counts=OPS.counts[project.id]||{};
      const branch=String(project&&project.coreBranch||'').trim();
      const title=projectCardTitle(project,OPS.projects);
      const context=projectContextLabel(project,OPS.projects);
      const showBranchBadge=!!(branch&&!projectUsesBranchTitle(project,OPS.projects));
      const playStatus=playStatusFor(project.id);
      const style=projectAccentStyle(project,index,'ops-card');
      const sessionsHtml=renderProjectSessionRows(project);
      return `
        <section class="quick-response-project-card ${project.active===false?'project-inactive':''}" ${style?`style="${esc(style)}"`:''}>
          <div class="quick-response-project-header">
            <div class="quick-response-project-main">
              <button class="ops-project-open ops-project-open-group" type="button" data-ops-action="open-project" data-project-id="${esc(project.id)}">
                <div class="quick-response-project-title-block">
                  <div class="quick-response-project-title-line">
                    <span class="quick-response-project-title">${esc(title)}</span>
                    ${showBranchBadge?`<span class="menu-session-activity-badge quick-response-project-branch">${esc(`Branch: ${branch}`)}</span>`:''}
                    ${playStatus?`<span class="menu-session-activity-badge ${esc(playStatusKind(playStatus))}">${esc(playStatusLabel(playStatus))}</span>`:''}
                  </div>
                  ${context?`<div class="quick-response-project-repo">${esc(context)}</div>`:''}
                  <div class="quick-response-project-meta">${esc(projectWorkspaceMeta(project,counts))}</div>
                </div>
              </button>
            </div>
            <div class="quick-response-project-actions">
              ${renderSessionWorkspaceActions({projectId:project.id,project})}
            </div>
          </div>
          ${sessionsHtml}
        </section>
      `;
    }

    function renderProjects(){
      setDashboardTopbar('Projects',`${OPS.projects.length} project${OPS.projects.length===1?'':'s'}`);
      const createForm=OPS.showCreate?`
        <section class="repo-panel">
          <div class="menu-notification-header">
            <div class="menu-notification-header-copy">
              <div class="quick-response-title">Create project</div>
              <div class="menu-notification-header-help">Register a local repo so the restored ops shell can manage tasks, sessions, and upstream maintenance against it.</div>
            </div>
          </div>
          <form class="ops-inline-form" data-ops-submit="create-project">
            <label><span>Name</span><input name="name" id="opsProjectName" autocomplete="off" required></label>
            <label><span>Path</span><input name="path" autocomplete="off" required placeholder="/path/to/project"></label>
            <label><span>Core branch</span><input name="coreBranch" autocomplete="off" value="main"></label>
            <label><span>Profile</span><select name="profile">${renderProjectProfileOptions('',{allowBlank:false})}</select></label>
            <div class="ops-form-actions">
              <button class="ops-btn primary" type="submit">${svg.plus}<span>Create</span></button>
              <button class="ops-btn" type="button" data-ops-action="cancel-create">Cancel</button>
            </div>
          </form>
        </section>
      `:'';
      const rows=OPS.projects.length?OPS.projects.map((project,index)=>renderProjectWorkspaceCard(project,index)).join(''):`<div class="repo-empty">No projects.</div>`;
      const el=root();
      if(!el)return '';
      el.innerHTML=`
        <div class="ops-dashboard ops-projects-dashboard project-page-content">
          <h2>Projects</h2>
          <p class="menu-description">Create projects, monitor active sessions, and reply when the agent asks for input.</p>
          <section class="quick-response-panel list-view" aria-live="polite">
            <div class="quick-response-header">
              <div>
                <div class="quick-response-title">Project workspace</div>
                <div class="quick-response-subtitle">${esc(OPS.projects.length+' loaded'+(OPS.projectsHydrating?' • syncing workspace status...':''))}</div>
              </div>
              <div class="quick-response-nav">
                <button class="menu-action-btn secondary small" type="button" data-ops-action="back-home">Menu</button>
                <button class="menu-action-btn secondary small" type="button" data-ops-action="refresh-projects">Refresh projects</button>
                <button class="menu-action-btn secondary small" type="button" data-ops-action="show-create">Create project</button>
              </div>
            </div>
            <div class="quick-response-body">
              ${createForm}
              <details class="ops-project-secondary-panels">
                <summary>Import from GitHub</summary>
                <div class="ops-project-secondary-panels-body">
                  ${renderGitHubDiscovery()}
                </div>
              </details>
              <div class="quick-response-projects">${rows}</div>
            </div>
          </section>
        </div>
      `;
      if(OPS.showCreate&&document.getElementById('opsProjectName'))document.getElementById('opsProjectName').focus();
      return rows;
    }

    async function loadProjects(){
      const token=++activeProjectsLoadToken;
      const [data,profileData]=await Promise.all([
        api('/api/ops/projects'),
        AgentBridgeRef.profiles.list().catch(()=>null),
      ]);
      if(token!==activeProjectsLoadToken)return OPS.projects;
      OPS.projects=Array.isArray(data.projects)?data.projects:[];
      OPS.profiles=Array.isArray(profileData&&profileData.profiles)?profileData.profiles:[];
      seedProjectHydrationState(OPS.projects);
      rerenderProjectsView();
      void hydrateProjectSessions(OPS.projects,token);
      (OPS.projects||[]).forEach(project=>{
        void hydrateProjectWorkspace(project,token);
      });
      return OPS.projects;
    }

    async function openProjects(options){
      const opts=options&&typeof options==='object'?options:{};
      if(opts.historyMode!=='skip')syncStandaloneOpsHistory('projects','');
      OPS.view='projects';
      OPS.currentProject=null;
      OPS.taskData=null;
      OPS.showCreate=false;
      setDashboardTopbar('Projects','');
      renderLoading('Loading projects...');
      await loadProjects();
      return renderProjects();
    }

    async function loadProjectDetail(projectId){
      const [data,sessionsData]=await Promise.all([
        api(projectUrl(projectId,'/tasks')),
        AgentBridgeRef.sessions.list().catch(()=>({sessions:[]})),
        loadOpsRuns({projectId}).catch(()=>[]),
        refreshProjectPlayStatus(projectId,{render:false}).catch(()=>null),
        refreshProjectGitStatus(projectId,{render:false}).catch(()=>null),
        loadProjectDependencyStatus(projectId,{render:false}).catch(()=>null),
        loadProjectGatherReports(projectId,{render:false}).catch(()=>null),
        loadProjectReviewRequests(projectId,{render:false}).catch(()=>null),
        loadProjectDeployment(projectId,{render:false}).catch(()=>null),
        loadProjectDatabase(projectId,{render:false}).catch(()=>null),
      ]);
      OPS.taskData=data;
      OPS.sessions=Array.isArray(sessionsData.sessions)?sessionsData.sessions:[];
      OPS.taskDataByProject[projectId]=data;
      OPS.currentProject=data.project||OPS.currentProject||findProject(projectId);
      return OPS.taskData;
    }

    async function openProjectDetail(projectId,options){
      const opts=options&&typeof options==='object'?options:{};
      if(opts.historyMode!=='skip')syncStandaloneOpsHistory('project-detail',projectId);
      const project=findProject(projectId);
      OPS.view='project-detail';
      OPS.currentProject=project;
      OPS.editingTask=null;
      OPS.taskFormDraft=null;
      OPS.createEpicDraftTitle='';
      OPS.taskFormFocusedForm='';
      OPS.taskFormFocusedField='';
      OPS.taskFormSelectionStart=null;
      OPS.taskFormSelectionEnd=null;
      OPS.selectedRunId='';
      OPS.runDetail=null;
      OPS.runReadableOutput=null;
      OPS.runEvents=null;
      OPS.runRequests=null;
      OPS.runArtifacts=null;
      OPS.runLogs=null;
      OPS.playConfigEditingProjectId='';
      resetTaskFilters();
      setDashboardTopbar(project?nameOf(project):'Project','Loading...');
      renderLoading('Loading project...');
      try{
        await api(projectUrl(projectId,'/ensure-workspace'),{method:'POST',body:JSON.stringify({})});
      }catch(e){
        if(!isNotFoundError(e)){
          showToast(e.message||'Workspace sync failed',3600);
        }
      }
      await loadProjectDetail(projectId);
      return renderProjectDetail();
    }

    function allTasks(projectId){
      const data=projectId
        ? (OPS.currentProject&&OPS.currentProject.id===projectId?OPS.taskData:OPS.taskDataByProject[projectId])
        : OPS.taskData;
      const epics=(data&&data.epics)||[];
      const rows=[];
      epics.forEach(epic=>(epic.tasks||[]).forEach(task=>rows.push({epic,task})));
      return rows;
    }

    function findTaskInData(data,taskId){
      for(const epic of ((data&&data.epics)||[])){
        const task=(epic.tasks||[]).find(t=>t.id===taskId);
        if(task)return {epic,task};
      }
      return null;
    }

    function findTask(taskId){
      return findTaskInData(OPS.taskData,taskId);
    }

    async function reloadProjectTasks(projectId){
      const data=await api(projectUrl(projectId,'/tasks'));
      OPS.taskDataByProject[projectId]=data;
      if(OPS.currentProject&&OPS.currentProject.id===projectId){
        OPS.taskData=data;
        OPS.currentProject=data.project||OPS.currentProject;
      }
      return data;
    }

    async function refreshOpsSessions(){
      const data=await AgentBridgeRef.sessions.list().catch(()=>({sessions:[]}));
      OPS.sessions=Array.isArray(data&&data.sessions)?data.sessions:[];
      return OPS.sessions;
    }

    return {
      summarizeEpics,
      mergeProjectUpdate,
      findProject,
      sessionProjectId,
      sessionTaskId,
      sessionRecencyValue,
      isSessionForProject,
      canonicalTaskSessions,
      projectSessionsFor,
      latestSessionForTask,
      resolvedTaskSession,
      projectWorkspaceMeta,
      renderProjectWorkspaceCard,
      renderProjects,
      loadProjects,
      openProjects,
      loadProjectDetail,
      openProjectDetail,
      allTasks,
      findTaskInData,
      findTask,
      reloadProjectTasks,
      refreshOpsSessions,
    };
  }

  window.HermesOpsModules.projects={bindDashboard};
})();

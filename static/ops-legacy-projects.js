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

    function normalizePath(value){
      return String(value||'').replace(/\/+$/,'');
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
      const values=[
        `${Number(summary.sessions)||0} active session${Number(summary.sessions)===1?'':'s'}`,
        `${Number(summary.active)||0} active task${Number(summary.active)===1?'':'s'}`,
        `Epics ${Number(summary.epics)||0}`,
        `Done ${Number(summary.done)||0}`,
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
      return `
        <section class="ops-project-card ops-session-group-card ${project.active===false?'inactive':''}" ${style?`style="${esc(style)}"`:''}>
          <div class="ops-session-group-header">
            <div class="ops-session-group-main">
              <button class="ops-project-open ops-project-open-group" type="button" data-ops-action="open-project" data-project-id="${esc(project.id)}">
                <div class="ops-session-group-title-block">
                  <div class="ops-session-group-title-line">
                    <span class="ops-session-group-title">${esc(title)}</span>
                    ${showBranchBadge?`<span class="ops-session-group-badge">${esc(`Branch: ${branch}`)}</span>`:''}
                    ${playStatus?`<span class="ops-session-group-badge ${esc(playStatusKind(playStatus))}">${esc(playStatusLabel(playStatus))}</span>`:''}
                  </div>
                  ${context?`<div class="ops-session-group-context">${esc(context)}</div>`:''}
                  <div class="ops-session-group-meta">${esc(projectWorkspaceMeta(project,counts))}</div>
                </div>
              </button>
            </div>
            ${renderSessionWorkspaceActions({projectId:project.id,project})}
          </div>
          ${renderProjectSessionRows(project)}
        </section>
      `;
    }

    function renderProjects(){
      setDashboardTopbar('Projects',`${OPS.projects.length} project${OPS.projects.length===1?'':'s'}`);
      const createForm=OPS.showCreate?`
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
      `:'';
      const rows=OPS.projects.length?OPS.projects.map((project,index)=>renderProjectWorkspaceCard(project,index)).join(''):`<div class="ops-empty">No projects</div>`;
      const el=root();
      if(!el)return '';
      el.innerHTML=`
        <div class="ops-dashboard">
          <div class="ops-toolbar">
            <button class="ops-icon-btn" type="button" data-ops-action="back-home" title="Back">${svg.arrow}</button>
            <div class="ops-title-block"><h2>Projects</h2><span>${esc(OPS.projects.length+' loaded')}</span></div>
            <div class="ops-toolbar-actions">
              <button class="ops-btn" type="button" data-ops-action="refresh-projects">${svg.refresh}<span>Refresh</span></button>
              <button class="ops-btn primary" type="button" data-ops-action="show-create">${svg.plus}<span>New project</span></button>
            </div>
          </div>
          ${createForm}
          <details class="ops-project-secondary-panels">
            <summary>Import from GitHub</summary>
            <div class="ops-project-secondary-panels-body">
              ${renderGitHubDiscovery()}
            </div>
          </details>
          <div class="ops-project-list">${rows}</div>
        </div>
      `;
      if(OPS.showCreate&&document.getElementById('opsProjectName'))document.getElementById('opsProjectName').focus();
      return rows;
    }

    async function loadProjects(){
      const [data,profileData]=await Promise.all([
        api('/api/ops/projects'),
        AgentBridgeRef.profiles.list().catch(()=>null),
      ]);
      OPS.projects=Array.isArray(data.projects)?data.projects:[];
      OPS.profiles=Array.isArray(profileData&&profileData.profiles)?profileData.profiles:[];
      OPS.counts={};
      OPS.taskDataByProject={};
      try{
        const groupsData=await AgentBridgeRef.sessions.grouped();
        OPS.sessionGroups=groupsData;
        OPS.sessions=Array.isArray(groupsData.sessions)?groupsData.sessions:[];
      }catch(e){
        OPS.sessionGroups=null;
        try{
          const sessionsData=await AgentBridgeRef.sessions.list();
          OPS.sessions=Array.isArray(sessionsData.sessions)?sessionsData.sessions:[];
        }catch(err){
          OPS.sessions=[];
        }
      }
      await Promise.all((OPS.projects||[]).map(async(project)=>{
        const sessionsCount=projectSessionsFor(project,OPS.sessions).length;
        const tasksResult=api(projectUrl(project.id,'/tasks'));
        const playResult=refreshProjectPlayStatus(project.id,{render:false});
        const gitResult=refreshProjectGitStatus(project.id,{render:false});
        try{
          const tasks=await tasksResult;
          OPS.taskDataByProject[project.id]=tasks;
          OPS.counts[project.id]={
            ...summarizeEpics(tasks.epics||[]),
            sessions:sessionsCount,
          };
        }catch(e){
          OPS.counts[project.id]={
            active:0,
            done:0,
            archived:0,
            sessions:sessionsCount,
            error:e.message||'Unavailable',
          };
        }
        await playResult.catch(()=>{});
        await gitResult.catch(()=>{});
      }));
      return OPS.projects;
    }

    async function openProjects(){
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

    async function openProjectDetail(projectId){
      const project=findProject(projectId);
      OPS.view='project-detail';
      OPS.currentProject=project;
      OPS.editingTask=null;
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
        showToast(e.message||'Workspace sync failed',3600);
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

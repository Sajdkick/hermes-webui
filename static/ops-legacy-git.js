(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};
  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const api=ctx&&ctx.api;
    const projectUrl=ctx&&ctx.projectUrl;
    const renderCurrentOpsView=ctx&&ctx.renderCurrentOpsView;
    const showToast=ctx&&ctx.showToast;
    const esc=ctx&&ctx.esc;
    const svg=ctx&&ctx.svg;
    const nameOf=ctx&&ctx.nameOf;
    const findProject=ctx&&ctx.findProject;
    const newChatInProject=ctx&&ctx.newChatInProject;
    const domLookup=ctx&&ctx.domLookup;
    const sendTurn=ctx&&ctx.sendTurn;
    const autoResize=ctx&&ctx.autoResize;
    const getCurrentProject=ctx&&ctx.getCurrentProject;
    const loadProjects=ctx&&ctx.loadProjects;
    const openProjectDetail=ctx&&ctx.openProjectDetail;
    const refreshDetail=ctx&&ctx.refreshDetail;
    const renderProjects=ctx&&ctx.renderProjects;
    if(!OPS||typeof api!=='function'||typeof projectUrl!=='function'||typeof renderCurrentOpsView!=='function'||typeof showToast!=='function'||typeof esc!=='function'||!svg){
      return {};
    }

    function gitStatusFor(projectId){
      return OPS.gitStatusByProject[projectId]||null;
    }

    function gitBusyMode(projectId){
      const value=OPS.gitBusyByProject[projectId];
      if(value===true)return 'operation';
      return String(value||'').trim();
    }

    function gitOperationBusyMode(projectId){
      const mode=gitBusyMode(projectId);
      if(!mode||mode==='status'||mode==='refresh')return '';
      return mode;
    }

    async function refreshProjectGitStatus(projectId,options){
      const id=String(projectId||'').trim();
      if(!id)return null;
      OPS.gitBusyByProject[id]='status';
      try{
        const data=await api(projectUrl(id,'/git/status'));
        const status=data.git||data;
        OPS.gitStatusByProject[id]=status;
        return status;
      }catch(e){
        OPS.gitStatusByProject[id]={projectId:id,status:'unavailable',isGitRepo:false,error:e.message||'Git status unavailable.'};
        throw e;
      }finally{
        delete OPS.gitBusyByProject[id];
        if(!options||options.render!==false)renderCurrentOpsView();
      }
    }

    async function executeProjectGitOperation(projectId,operation){
      const id=String(projectId||'').trim();
      const op=String(operation||'').trim().toLowerCase();
      if(!id||!['push','sync'].includes(op))return null;
      const label=op==='push'?'Push':'Sync';
      OPS.gitBusyByProject[id]=op;
      renderCurrentOpsView();
      try{
        delete OPS.gitPlansByProject[id];
        const data=await api(projectUrl(id,`/git/${op}`),{
          method:'POST',
          body:JSON.stringify({
            confirm:op,
            message:`Sync changes from Codex Terminal (${new Date().toISOString()})`,
          }),
        });
        const operationRecord=data.operation||data;
        OPS.gitOperationsByProject[id]=operationRecord;
        if(operationRecord.finalStatus)OPS.gitStatusByProject[id]=operationRecord.finalStatus;
        if(typeof loadProjects==='function'){
          await loadProjects().catch(()=>null);
        }
        const currentProject=typeof getCurrentProject==='function'?getCurrentProject():null;
        if(
          currentProject
          && currentProject.id===id
          && Number(operationRecord.taskUpdates||0)>0
          && typeof refreshDetail==='function'
        ){
          await refreshDetail().catch(()=>null);
        }
        showToast(operationRecord.summary||`${label} finished`,3200);
        return operationRecord;
      }finally{
        delete OPS.gitBusyByProject[id];
        renderCurrentOpsView();
      }
    }

    function gitStatusKind(status,project){
      const primary=gitPrimaryActionState(project||null,status);
      return primary.statusKind||'idle';
    }

    function gitStatusLabel(status,project){
      const primary=gitPrimaryActionState(project||null,status);
      return primary.statusLabel||'Git status';
    }

    function gitStatusSummary(status){
      if(!status)return 'Git status has not loaded yet.';
      if(status.error)return String(status.error);
      if(status.isGitRepo===false||status.status==='not-git')return 'This project path is not inside a Git repository.';
      const parts=[];
      if(status.branch)parts.push(`Branch ${status.branch}`);
      if(status.detached&&status.headShortSha)parts.push(`Detached ${status.headShortSha}`);
      if(status.mergeInProgress)parts.push('Merge in progress');
      else if(status.rebaseInProgress)parts.push('Rebase in progress');
      else if(status.cherryPickInProgress)parts.push('Cherry-pick in progress');
      else if(status.revertInProgress)parts.push('Revert in progress');
      if(status.upstream)parts.push(`Upstream ${status.upstream}`);
      if(status.ahead)parts.push(`ahead ${status.ahead}`);
      if(status.behind)parts.push(`behind ${status.behind}`);
      const counts=status.counts||{};
      if(status.conflicts||counts.conflicts)parts.push(`${status.conflicts||counts.conflicts} conflicts`);
      if(counts.files)parts.push(`${counts.files} changed`);
      if(counts.untracked)parts.push(`${counts.untracked} untracked`);
      if(status.lastCommit&&status.lastCommit.shortSha){
        const subject=status.lastCommit.subject?` ${status.lastCommit.subject}`:'';
        parts.push(`${status.lastCommit.shortSha}${subject}`);
      }
      return parts.join(' | ')||'Working tree clean.';
    }

    function gitQuickBadgeState(project,status){
      const primary=gitPrimaryActionState(project||null,status);
      const coreBranch=String((status&&status.coreBranch)||(project&&project.coreBranch)||'main').trim()||'main';
      const originBranch=`origin/${coreBranch}`;
      const branch=String(status&&status.branch||project&&project.coreBranch||'').trim()||'...';
      const remoteModes=new Set(['push','sync','in-sync']);
      return {
        label:primary.statusLabel||'Branch',
        name:remoteModes.has(primary.mode)?originBranch:branch,
        title:primary.title||'Git status',
        badgeClass:primary.badgeClass||'inactive',
      };
    }

    function gitPrimaryActionState(project,status){
      const coreBranch=String((status&&status.coreBranch)||(project&&project.coreBranch)||'main').trim()||'main';
      const originBranch=`origin/${coreBranch}`;
      const counts=status&&status.counts||{};
      const conflicts=Number((status&&status.conflicts)||counts.conflicts||0);
      const mergeInProgress=!!(status&&status.mergeInProgress);
      const rebaseInProgress=!!(status&&status.rebaseInProgress);
      const cherryPickInProgress=!!(status&&status.cherryPickInProgress);
      const revertInProgress=!!(status&&status.revertInProgress);
      const behind=Number(status&&status.behind||0);
      const ahead=Number(status&&status.ahead||0);
      const diverged=behind>0&&ahead>0;
      if(!status){
        return { mode:'loading', label:'Checking...', title:'Checking branch status...', action:'', icon:svg.refresh, disabled:true, badgeClass:'state-loading', statusLabel:'Checking', statusKind:'idle' };
      }
      if(status.error||status.status==='unavailable'){
        return { mode:'unavailable', label:'Git unavailable', title:String(status.error||'Git is unavailable for this project.'), action:'', icon:svg.git, disabled:true, badgeClass:'inactive', statusLabel:'Git unavailable', statusKind:'error' };
      }
      if(status.isGitRepo===false||status.status==='not-git'){
        return { mode:'missing', label:'No Git repo', title:'This project path is not inside a Git repository.', action:'', icon:svg.git, disabled:true, badgeClass:'inactive', statusLabel:'No Git repo', statusKind:'missing' };
      }
      if(mergeInProgress||rebaseInProgress||cherryPickInProgress||revertInProgress||conflicts>0){
        let title='Merge conflicts detected. Resolve them before syncing.';
        let statusLabel='Conflicts';
        if(mergeInProgress){
          title='A merge is already in progress. Finish resolving it before syncing.';
          statusLabel='Merge in progress';
        }else if(rebaseInProgress){
          title='A rebase is already in progress. Finish resolving it before syncing.';
          statusLabel='Rebase in progress';
        }else if(cherryPickInProgress){
          title='A cherry-pick is already in progress. Finish resolving it before syncing.';
          statusLabel='Cherry-pick in progress';
        }else if(revertInProgress){
          title='A revert is already in progress. Finish resolving it before syncing.';
          statusLabel='Revert in progress';
        }
        return { mode:'conflict', label:'Fix Conflicts', title, action:'git-fix-conflicts', icon:svg.refresh, disabled:false, badgeClass:'state-conflict', statusLabel, statusKind:'error' };
      }
      if(behind>0){
        return {
          mode:'sync',
          label:`Sync with ${coreBranch}`,
          title:diverged?`Branch has diverged from ${originBranch}.`:`Branch is behind ${originBranch}.`,
          action:'git-sync-execute',
          icon:svg.refresh,
          disabled:false,
          badgeClass:diverged?'state-diverged':'state-behind',
          statusLabel:diverged?'Diverged':'Behind',
          statusKind:'warning',
        };
      }
      if(ahead>0||status.dirty){
        return {
          mode:'push',
          label:'Push changes',
          title:`Changes have not been pushed to ${originBranch}.`,
          action:'git-push-execute',
          icon:svg.git,
          disabled:false,
          badgeClass:'state-ahead',
          statusLabel:'Needs push',
          statusKind:'warning',
        };
      }
      return { mode:'in-sync', label:'In sync', title:`${originBranch} is up to date.`, action:'', icon:svg.check, disabled:true, badgeClass:'state-in-sync', statusLabel:'In sync', statusKind:'ready' };
    }

    function renderProjectGitQuickAction(project){
      if(!project||!project.id)return '';
      const status=gitStatusFor(project.id);
      const primary=gitPrimaryActionState(project,status);
      const badge=gitQuickBadgeState(project,status);
      const busy=gitOperationBusyMode(project.id);
      const label=busy==='push'
        ? 'Pushing...'
        : busy==='sync'
          ? 'Syncing...'
          : primary.mode==='loading'
            ? 'Checking...'
            : primary.label;
      const disabled=!!busy||primary.disabled;
      const title=busy==='push'
        ? 'Pushing the current project changes and waiting for Git to finish.'
        : busy==='sync'
          ? 'Syncing the project with the remote branch.'
          : primary.title;
      return `
        <div class="ops-project-sync-action">
          <button class="ops-btn ${!disabled?'primary':''}" type="button" data-ops-action="${esc(primary.action||'git-noop')}" data-project-id="${esc(project.id)}" ${disabled?'disabled':''} title="${esc(title)}">${primary.icon}<span>${esc(label)}</span></button>
          <span class="ops-project-sync-badge ${esc(badge.badgeClass||'inactive')}" title="${esc(badge.title)}">
            <span class="ops-project-sync-dot" aria-hidden="true"></span>
            <span class="ops-project-sync-label">${esc(badge.label)}</span>
            <span class="ops-project-sync-name">${esc(badge.name)}</span>
          </span>
        </div>
      `;
    }

    function renderProjectGitStatus(project,options){
      if(!project||!project.id)return '';
      const status=gitStatusFor(project.id);
      const primary=gitPrimaryActionState(project,status);
      const operation=OPS.gitOperationsByProject[project.id]||null;
      const kind=gitStatusKind(status,project);
      const busyMode=gitBusyMode(project.id);
      const operationBusy=gitOperationBusyMode(project.id);
      const primaryLabel=operationBusy==='push'
        ? 'Pushing...'
        : operationBusy==='sync'
          ? 'Syncing...'
          : primary.label;
      const primaryTitle=operationBusy==='push'
        ? 'Pushing the current project changes and waiting for Git to finish.'
        : operationBusy==='sync'
          ? 'Syncing the project with the remote branch.'
          : primary.title;
      const primaryDisabled=!!operationBusy||primary.disabled;
      const refreshLabel=operationBusy?'Busy...':busyMode?'Refreshing...':'Refresh';
      const summary=gitStatusSummary(status);
      const remote=status&&status.remoteUrl?String(status.remoteUrl):'';
      const last=status&&status.lastCommit&&status.lastCommit.subject?String(status.lastCommit.subject):'';
      const detail=options&&options.detail;
      return `
        <div class="ops-git-panel ${esc(kind)} ${detail?'detail':''}">
          <div class="ops-git-main">
            <span class="ops-git-status ${esc(kind)}">${svg.git}<span>${esc(gitStatusLabel(status,project))}</span></span>
            <small>${esc(summary)}</small>
            ${detail&&remote?`<small>${esc(remote)}</small>`:''}
            ${detail&&last?`<small>${esc(last)}</small>`:''}
            ${operation?`
              <div class="ops-git-operation ${esc(operation.status||'')}">
                <strong>${esc(operation.summary||'Git operation')}</strong>
                <span>${esc(`${operation.operation||'git'} | ${operation.status||'unknown'} | ${operation.updatedAt||operation.createdAt||''}`)}</span>
                ${operation.error?`<span class="error">${esc(operation.error)}</span>`:''}
                ${operation.operationPath?`<a href="/api/media?path=${encodeURIComponent(operation.operationPath)}" target="_blank" rel="noopener noreferrer">Operation record</a>`:''}
              </div>
            `:''}
          </div>
          <div class="ops-git-actions">
            <button class="ops-btn" type="button" data-ops-action="refresh-git-status" data-project-id="${esc(project.id)}" ${busyMode?'disabled':''}>${svg.refresh}<span>${refreshLabel}</span></button>
            <button class="ops-btn ${!primaryDisabled?'primary':''}" type="button" data-ops-action="${esc(primary.action||'git-noop')}" data-project-id="${esc(project.id)}" ${primaryDisabled?'disabled':''} title="${esc(primaryTitle)}">${primary.icon}<span>${esc(primaryLabel)}</span></button>
          </div>
        </div>
      `;
    }

    function buildGitConflictPrompt(project){
      const label=typeof nameOf==='function'?nameOf(project):String(project&&project.name||project&&project.id||'project');
      return `Analyze the repository for ${label} and resolve all merge conflicts on the current branch. Keep the work scoped to this project, leave the branch in a clean state, and explain any blocker you cannot fix automatically.`;
    }

    async function startGitConflictResolution(projectId){
      const project=(typeof findProject==='function'&&findProject(projectId))||(typeof getCurrentProject==='function'&&getCurrentProject())||null;
      if(!project)return;
      if(typeof newChatInProject==='function')await newChatInProject(project);
      const msg=typeof domLookup==='function'?domLookup('msg'):null;
      if(msg&&typeof sendTurn==='function'){
        msg.value=buildGitConflictPrompt(project);
        if(typeof autoResize==='function')autoResize();
        await sendTurn();
        showToast('Conflict resolution started',2600);
        return;
      }
      showToast('Opened project chat',2200);
    }

    function githubStatusKind(status){
      if(!status)return 'idle';
      if(status.authenticated)return 'ready';
      if(status.tokenPresent)return 'error';
      return 'missing';
    }

    function githubStatusLabel(status){
      if(!status)return 'Not checked';
      if(status.authenticated){
        const login=status.user&&status.user.login?` as ${status.user.login}`:'';
        return `Connected${login}`;
      }
      if(status.tokenPresent)return 'Token failed';
      return 'No token';
    }

    function githubRepoKey(owner,repo){
      return `${String(owner||'').trim()}/${String(repo||'').trim()}`;
    }

    async function loadGitHubStatus(options){
      OPS.githubBusy=true;
      OPS.githubError='';
      try{
        OPS.githubStatus=await api('/api/ops/github/status');
        return OPS.githubStatus;
      }catch(e){
        OPS.githubStatus={authenticated:false,tokenPresent:true,message:e.message||'GitHub unavailable.'};
        OPS.githubError=e.message||'GitHub unavailable.';
        throw e;
      }finally{
        OPS.githubBusy=false;
        if(!options||options.render!==false)renderCurrentOpsView();
      }
    }

    async function searchGitHubRepositories(query,options){
      const trimmed=String(query||'').trim();
      OPS.githubQuery=trimmed;
      OPS.githubBusy=true;
      OPS.githubError='';
      try{
        const params=new URLSearchParams();
        if(trimmed)params.set('q',trimmed);
        params.set('limit','20');
        const data=await api(`/api/ops/github/repos?${params}`);
        OPS.githubRepos=Array.isArray(data.repositories)?data.repositories:[];
        if(data.authenticated)OPS.githubStatus={...(OPS.githubStatus||{}),authenticated:true,tokenPresent:true,tokenSource:data.tokenSource||''};
        return OPS.githubRepos;
      }catch(e){
        OPS.githubError=e.message||'GitHub repository discovery failed.';
        throw e;
      }finally{
        OPS.githubBusy=false;
        if(!options||options.render!==false)renderCurrentOpsView();
      }
    }

    async function loadGitHubBranches(owner,repo,options){
      const cleanOwner=String(owner||'').trim();
      const cleanRepo=String(repo||'').trim();
      if(!cleanOwner||!cleanRepo)return [];
      const key=githubRepoKey(cleanOwner,cleanRepo);
      OPS.githubBusy=true;
      OPS.githubError='';
      try{
        const data=await api(`/api/ops/github/repos/${encodeURIComponent(cleanOwner)}/${encodeURIComponent(cleanRepo)}/branches?limit=100`);
        OPS.githubBranchesByRepo[key]=Array.isArray(data.branches)?data.branches:[];
        return OPS.githubBranchesByRepo[key];
      }catch(e){
        OPS.githubError=e.message||'GitHub branch discovery failed.';
        throw e;
      }finally{
        OPS.githubBusy=false;
        if(!options||options.render!==false)renderCurrentOpsView();
      }
    }

    async function importGitHubRepository(owner,repo,branch){
      const cleanOwner=String(owner||'').trim();
      const cleanRepo=String(repo||'').trim();
      const cleanBranch=String(branch||'').trim();
      if(!cleanOwner||!cleanRepo)return showToast('Repository metadata is missing.',3200);
      const suffix=cleanBranch?` (${cleanBranch})`:'';
      const ok=await ctx.showConfirmDialog({
        title:'Import GitHub repository',
        message:`Clone ${cleanOwner}/${cleanRepo}${suffix} and create a Hermes project.`,
        confirmLabel:'Import',
        focusCancel:true,
      });
      if(!ok)return;
      OPS.githubBusy=true;
      OPS.githubError='';
      renderCurrentOpsView();
      try{
        const data=await api('/api/ops/github/import',{
          method:'POST',
          body:JSON.stringify({owner:cleanOwner,repo:cleanRepo,branch:cleanBranch,defaultBranch:cleanBranch||'main'}),
        });
        showToast('Project imported',2600);
        if(typeof loadProjects==='function')await loadProjects();
        if(data.project&&data.project.id&&typeof openProjectDetail==='function')return await openProjectDetail(data.project.id);
        if(typeof renderProjects==='function')return renderProjects();
        return data;
      }catch(e){
        OPS.githubError=e.message||'GitHub import failed.';
        throw e;
      }finally{
        OPS.githubBusy=false;
        renderCurrentOpsView();
      }
    }

    function renderGitHubRepoBranches(repo){
      const owner=repo&&repo.owner||'';
      const name=repo&&repo.name||'';
      const key=githubRepoKey(owner,name);
      const branches=OPS.githubBranchesByRepo[key];
      if(!Array.isArray(branches))return '';
      if(!branches.length)return '<div class="ops-github-branches"><span>No branches found.</span></div>';
      return `
        <div class="ops-github-branches">
          ${branches.slice(0,12).map(branch=>`
            <button type="button" title="${esc(branch.commitSha||'')}" data-ops-action="import-github-repo" data-github-owner="${esc(owner)}" data-github-repo="${esc(name)}" data-github-branch="${esc(branch.name||'')}">${esc(branch.name||'Branch')}${branch.protected?' protected':''}</button>
          `).join('')}
        </div>
      `;
    }

    function renderGitHubRepo(repo){
      const owner=repo&&repo.owner||'';
      const name=repo&&repo.name||'';
      const defaultBranch=repo&&repo.defaultBranch||'main';
      const meta=[
        repo&&repo.private?'Private':'Public',
        repo&&repo.defaultBranch?`Default ${repo.defaultBranch}`:'',
        repo&&repo.language?repo.language:'',
        repo&&repo.updatedAt?`Updated ${repo.updatedAt}`:'',
      ].filter(Boolean).join(' | ');
      const badges=[
        repo&&repo.fork?'Fork':'',
        repo&&repo.archived?'Archived':'',
        repo&&repo.disabled?'Disabled':'',
      ].filter(Boolean);
      const githubLink=repo&&repo.htmlUrl
        ? `<a class="ops-btn" href="${esc(repo.htmlUrl)}" target="_blank" rel="noopener">GitHub</a>`
        : '';
      return `
        <div class="ops-github-repo">
          <div class="ops-github-repo-row">
            <div class="ops-github-main">
              <div class="ops-github-title-row">
                <span class="ops-github-title">${esc(repo&&repo.fullName||githubRepoKey(owner,name)||'Repository')}</span>
                ${badges.map(badge=>`<span class="ops-github-badge">${esc(badge)}</span>`).join('')}
              </div>
              <div class="ops-github-meta">${esc(meta||'Repository metadata unavailable')}</div>
              ${repo&&repo.description?`<div class="ops-github-description">${esc(repo.description)}</div>`:''}
            </div>
            <div class="ops-github-actions">
              <button class="ops-btn" type="button" data-ops-action="list-github-branches" data-github-owner="${esc(owner)}" data-github-repo="${esc(name)}" ${owner&&name?'':'disabled'}>${svg.git}<span>Branches</span></button>
              <button class="ops-btn primary" type="button" data-ops-action="import-github-repo" data-github-owner="${esc(owner)}" data-github-repo="${esc(name)}" data-github-branch="${esc(defaultBranch)}" ${owner&&name?'':'disabled'}>${svg.plus}<span>Import</span></button>
              ${githubLink}
            </div>
          </div>
          ${renderGitHubRepoBranches(repo)}
        </div>
      `;
    }

    function renderGitHubDiscovery(){
      const status=OPS.githubStatus;
      const statusKind=githubStatusKind(status);
      const statusText=status&&status.message&&!status.authenticated?status.message:githubStatusLabel(status);
      const repoRows=OPS.githubRepos.length
        ? OPS.githubRepos.map(renderGitHubRepo).join('')
        : `<div class="ops-empty">${OPS.githubQuery?'No repositories matched the search.':'No repositories loaded.'}</div>`;
      const error=OPS.githubError?`<div class="ops-status error">${esc(OPS.githubError)}</div>`:'';
      return `
        <section class="ops-panel ops-github-panel">
          <div class="ops-panel-header">
            <div>
              <h2>GitHub</h2>
              <span>Read-only repository discovery.</span>
            </div>
            <button class="ops-btn" type="button" data-ops-action="refresh-github-status" ${OPS.githubBusy?'disabled':''}>${svg.refresh}<span>Check</span></button>
          </div>
          <form class="ops-github-search" data-ops-submit="github-search">
            <label>
              <span>Repository</span>
              <input name="query" autocomplete="off" value="${esc(OPS.githubQuery)}" placeholder="owner/name or repository name" ${OPS.githubBusy?'disabled':''}>
            </label>
            <button class="ops-btn primary" type="submit" ${OPS.githubBusy?'disabled':''}>${svg.git}<span>${OPS.githubBusy?'Loading...':'Search'}</span></button>
          </form>
          <div class="ops-github-status-row">
            <span class="ops-github-status ${esc(statusKind)}">${esc(githubStatusLabel(status))}</span>
            <small>${esc(statusText)}</small>
          </div>
          ${error}
          <div class="ops-github-repo-list">${repoRows}</div>
        </section>
      `;
    }

    return {
      gitStatusFor,
      refreshProjectGitStatus,
      executeProjectGitOperation,
      gitStatusKind,
      gitStatusLabel,
      gitStatusSummary,
      gitQuickBadgeState,
      gitPrimaryActionState,
      renderProjectGitQuickAction,
      renderProjectGitStatus,
      buildGitConflictPrompt,
      startGitConflictResolution,
      githubStatusKind,
      githubStatusLabel,
      githubRepoKey,
      loadGitHubStatus,
      searchGitHubRepositories,
      loadGitHubBranches,
      importGitHubRepository,
      renderGitHubRepoBranches,
      renderGitHubRepo,
      renderGitHubDiscovery,
    };
  }

  window.HermesOpsModules.git={
    name:'git',
    routes:[
      '/git/status',
      '/git/push/plan',
      '/git/sync/plan',
      '/git/push',
      '/git/sync',
      '/api/ops/github/status',
      '/api/ops/github/repos',
      '/api/ops/github/import',
    ],
    actions:[
      'refresh-git-status',
      'git-noop',
      'git-fix-conflicts',
      'git-push-plan',
      'git-sync-plan',
      'git-push-execute',
      'git-sync-execute',
      'refresh-github-status',
      'list-github-branches',
      'import-github-repo',
    ],
    bindDashboard,
  };
})();

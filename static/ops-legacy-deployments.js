(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};
  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const api=ctx&&ctx.api;
    const projectUrl=ctx&&ctx.projectUrl;
    const coreUrl=ctx&&ctx.coreUrl;
    const coreProjectUrl=ctx&&ctx.coreProjectUrl;
    const root=(ctx&&typeof ctx.root==='function')?ctx.root:function(){return null;};
    const renderCurrentOpsView=ctx&&ctx.renderCurrentOpsView;
    const showToast=ctx&&ctx.showToast;
    const showPromptDialog=ctx&&ctx.showPromptDialog;
    const showConfirmDialog=ctx&&ctx.showConfirmDialog;
    const esc=ctx&&ctx.esc;
    const svg=ctx&&ctx.svg;
    const nameOf=ctx&&ctx.nameOf;
    const projectPath=(ctx&&typeof ctx.projectPath==='function')
      ? ctx.projectPath
      : function(project){return String(project&&project.path||project&&project.worktree||project&&project.root||'').trim();};
    const setDashboardTopbar=(ctx&&typeof ctx.setDashboardTopbar==='function')?ctx.setDashboardTopbar:function(){};
    const renderLoading=(ctx&&typeof ctx.renderLoading==='function')?ctx.renderLoading:function(){};
    const loadProjects=(ctx&&typeof ctx.loadProjects==='function')?ctx.loadProjects:async function(){return Array.isArray(OPS&&OPS.projects)?OPS.projects:[];};
    const openProjectDetail=ctx&&ctx.openProjectDetail;
    const windowRef=(ctx&&ctx.windowRef)||(typeof window!=='undefined'?window:null);
    if(!OPS||typeof api!=='function'||typeof renderCurrentOpsView!=='function'||typeof showToast!=='function'||typeof showPromptDialog!=='function'||typeof showConfirmDialog!=='function'||typeof esc!=='function'||!svg||typeof nameOf!=='function'){
      return {};
    }

    const DEFAULT_PROJECT_CAPABILITIES={
      deployment:true,
    };

    let activeDeploymentsLoadToken=0;

    function ensureDeploymentState(){
      if(!OPS.deploymentsByProject||typeof OPS.deploymentsByProject!=='object')OPS.deploymentsByProject={};
      if(!OPS.deploymentBusyByProject||typeof OPS.deploymentBusyByProject!=='object')OPS.deploymentBusyByProject={};
      if(!OPS.deploymentProgressByProject||typeof OPS.deploymentProgressByProject!=='object')OPS.deploymentProgressByProject={};
      if(!Array.isArray(OPS.deploymentProviders))OPS.deploymentProviders=[];
    }

    function coreApiUrl(path){
      const suffix=String(path||'');
      if(typeof coreUrl==='function')return coreUrl(suffix);
      return `/api/core${suffix.startsWith('/')?suffix:`/${suffix}`}`;
    }

    function deploymentProjectUrl(projectId,suffix){
      const id=encodeURIComponent(String(projectId||'').trim());
      const tail=String(suffix||'');
      if(typeof coreProjectUrl==='function')return coreProjectUrl(projectId,tail);
      if(typeof projectUrl==='function'){
        const candidate=projectUrl(projectId,tail);
        if(String(candidate||'').startsWith('/api/core/'))return candidate;
      }
      return `/api/core/projects/${id}${tail.startsWith('/')?tail:`/${tail}`}`;
    }

    function providerList(){
      ensureDeploymentState();
      return Array.isArray(OPS.deploymentProviders)?OPS.deploymentProviders:[];
    }

    function providerById(providerId){
      const id=String(providerId||'').trim().toLowerCase();
      return providerList().find(provider=>String(provider&&provider.id||'').trim().toLowerCase()===id)||null;
    }

    function providerLabel(providerId){
      const provider=providerById(providerId);
      return provider&&provider.label?provider.label:String(providerId||'manual');
    }

    function providerCapabilities(providerId){
      const provider=providerById(providerId);
      return provider&&provider.capabilities&&typeof provider.capabilities==='object'?provider.capabilities:{};
    }

    function deploymentCanRedeploy(deployment){
      if(!deployment)return false;
      const capabilities=providerCapabilities(deployment.provider);
      return !!(capabilities.redeploy||deployment.redeploySupported||deployment.source==='cloud-terminal');
    }

    function readCloudTerminalSessionToken(){
      if(!windowRef||!windowRef.localStorage)return '';
      const keys=['cloudTerminalSessionToken','sessionToken'];
      for(const key of keys){
        try{
          const value=String(windowRef.localStorage.getItem(key)||'').trim();
          if(value)return value;
        }catch(_){ }
      }
      return '';
    }

    async function loadDeploymentProviders(options){
      ensureDeploymentState();
      const opts=options&&typeof options==='object'?options:{};
      try{
        const data=await api(coreApiUrl('/deployments/providers'));
        OPS.deploymentProviders=Array.isArray(data&&data.providers)?data.providers:[];
        OPS.defaultDeploymentProvider=String(data&&data.defaultProvider||'manual');
        return OPS.deploymentProviders;
      }finally{
        if(opts.render!==false&&deploymentsVisible())renderDeployments();
      }
    }

    function syncStandaloneOpsHistory(view){
      if(!windowRef||typeof windowRef.__opsLegacySyncHistoryState!=='function')return;
      const current=typeof windowRef.__opsLegacyReadHistoryState==='function'
        ? windowRef.__opsLegacyReadHistoryState(windowRef.history&&windowRef.history.state)
        : null;
      windowRef.__opsLegacySyncHistoryState(view,'',{mode:current?'push':'replace'});
    }

    function deploymentsVisible(){
      return OPS.view==='deployments'&&!!root();
    }

    function projectCapabilities(projectId){
      const id=String(projectId||'').trim();
      const project=(OPS.projects||[]).find(entry=>entry&&entry.id===id)
        || (OPS.currentProject&&OPS.currentProject.id===id?OPS.currentProject:null)
        || null;
      const caps=project&&project.opsCapabilities&&typeof project.opsCapabilities==='object'
        ? project.opsCapabilities
        : {};
      return {...DEFAULT_PROJECT_CAPABILITIES,...caps};
    }

    function deploymentCapabilities(projectId){
      const capabilities=projectCapabilities(projectId);
      if(OPS.view==='deployments')return {...capabilities,deployment:true};
      return capabilities;
    }

    async function loadProjectDeployment(projectId,options){
      ensureDeploymentState();
      const id=String(projectId||'').trim();
      if(!id)return null;
      const capabilities=deploymentCapabilities(id);
      if(!capabilities.deployment){
        const data={
          supported:false,
          summary:'Deployment tools are not available in this restart branch yet.',
          artifacts:[],
          logs:[],
          deployment:null,
        };
        OPS.deploymentsByProject[id]=data;
        if(!options||options.render!==false)renderCurrentOpsView();
        return data;
      }
      OPS.deploymentBusyByProject[id]=true;
      try{
        const data=await api(deploymentProjectUrl(id,'/deployment'));
        OPS.deploymentsByProject[id]=data;
        return data;
      }finally{
        delete OPS.deploymentBusyByProject[id];
        if(!options||options.render!==false)renderCurrentOpsView();
      }
    }

    async function recordProjectDeployment(projectId,action){
      ensureDeploymentState();
      const id=String(projectId||'').trim();
      const capabilities=deploymentCapabilities(id);
      if(!capabilities.deployment){
        showToast('Deployment tools are not available in this restart branch yet.',2600);
        return null;
      }
      const normalized=String(action||'deploy').trim().toLowerCase();
      const path=normalized==='deploy'?'/deployment':`/deployment/${normalized}`;
      OPS.deploymentBusyByProject[id]=true;
      try{
        await api(deploymentProjectUrl(id,path),{
          method:'POST',
          body:JSON.stringify({provider:'manual',summary:`Deployment ${normalized} recorded from the ops dashboard.`}),
        });
        showToast('Deployment record updated',2600);
        return await loadProjectDeployment(id,{render:false});
      }finally{
        delete OPS.deploymentBusyByProject[id];
        renderCurrentOpsView();
      }
    }

    async function executeProjectDeployment(projectId,action){
      ensureDeploymentState();
      const id=String(projectId||'').trim();
      const normalized=String(action||'deploy').trim().toLowerCase();
      if(!id)return null;
      const capabilities=deploymentCapabilities(id);
      if(!capabilities.deployment){
        showToast('Deployment tools are not available in this restart branch yet.',2600);
        return null;
      }
      const data=OPS.deploymentsByProject[id]||{};
      const artifacts=Array.isArray(data.artifacts)?data.artifacts:[];
      const hasDockerfile=artifacts.some(artifact=>artifact&&artifact.kind==='dockerfile');
      const deployment=data.deployment||{};
      const configuredProvider=String(deployment.provider||'').trim().toLowerCase();
      const command=await showPromptDialog({
        title:'Execute deployment',
        message:'Deployment command to run from the project root. Leave blank to use the Dockerfile build default when available.',
        value:'',
        confirmLabel:'Continue',
        cancelLabel:'Cancel',
      });
      if(command===null)return null;
      const provider=command.trim()
        ? (configuredProvider&&configuredProvider!=='manual'?configuredProvider:'local')
        : (configuredProvider&&configuredProvider!=='manual'?configuredProvider:hasDockerfile?'docker':'local');
      const body={action:normalized,confirm:normalized,provider};
      if(command.trim())body.command=command.trim();
      const ok=await showConfirmDialog({
        title:'Execute deployment',
        message:'Run this deployment command on the Hermes server. Hermes will record stdout, stderr, status, and recovery metadata.',
        confirmLabel:'Execute',
        focusCancel:true,
      });
      if(!ok)return null;
      OPS.deploymentBusyByProject[id]=true;
      try{
        const result=await api(deploymentProjectUrl(id,'/deployment/execute'),{method:'POST',body:JSON.stringify(body)});
        if(result.operation)showToast(`Deployment ${result.operation.status}`,3200);
        return await loadProjectDeployment(id,{render:false});
      }finally{
        delete OPS.deploymentBusyByProject[id];
        renderCurrentOpsView();
      }
    }

    async function redeployProjectDeployment(projectId){
      ensureDeploymentState();
      const id=String(projectId||'').trim();
      if(!id)return null;
      const capabilities=deploymentCapabilities(id);
      if(!capabilities.deployment){
        showToast('Deployment tools are not available in this restart branch yet.',2600);
        return null;
      }
      const data=OPS.deploymentsByProject[id]||{};
      const deployment=data.deployment||null;
      if(!deployment||!deploymentCanRedeploy(deployment)){
        showToast('Redeploy is not available for this deployment provider yet.',3200);
        return null;
      }
      const databaseMode=String(deployment.databaseMode||(deployment.database&&deployment.database.mode)||'').trim();
      const slug=String(deployment.slug||'').trim();
      const ok=await showConfirmDialog({
        title:'Redeploy deployment',
        message:`Update ${slug?`/${slug}`:'this deployment'} with the current project code while preserving the existing${databaseMode?` ${databaseMode}`:''} deployment database.`,
        confirmLabel:'Redeploy',
        focusCancel:true,
      });
      if(!ok)return null;
      OPS.deploymentBusyByProject[id]=true;
      OPS.deploymentProgressByProject[id]={
        label:'Preparing redeploy',
        detail:'Hermes Core is starting the build/publish workflow and preserving the existing deployment database.',
      };
      renderCurrentOpsView();
      showToast('Redeploy started. Core is rebuilding the deployment and will keep the existing data/database.',6000);
      try{
        OPS.deploymentProgressByProject[id]={
          label:'Redeploy in progress',
          detail:'Building current code, preserving previous hashed browser assets, then promoting the new snapshot atomically.',
        };
        renderCurrentOpsView();
        const body={confirm:'redeploy',preserveDatabase:true};
        if(databaseMode)body.databaseMode=databaseMode;
        const headers={};
        const sessionToken=readCloudTerminalSessionToken();
        if(sessionToken)headers['X-Session-Token']=sessionToken;
        const result=await api(deploymentProjectUrl(id,'/deployment/redeploy'),{method:'POST',headers,body:JSON.stringify(body)});
        const status=result&&result.operation&&result.operation.status?result.operation.status:'completed';
        showToast(`Deployment redeploy ${status}. Reload the deployment page if your browser was on an older cached build.`,6000);
        return await loadProjectDeployment(id,{render:false});
      }catch(error){
        OPS.deploymentProgressByProject[id]={
          label:'Redeploy failed',
          detail:error&&error.message?error.message:'Unable to redeploy deployment.',
        };
        renderCurrentOpsView();
        showToast(`Redeploy failed: ${error&&error.message?error.message:'Unable to redeploy deployment.'}`,8000);
        throw error;
      }finally{
        delete OPS.deploymentBusyByProject[id];
        delete OPS.deploymentProgressByProject[id];
        renderCurrentOpsView();
      }
    }

    async function scaffoldProjectDeployment(projectId){
      ensureDeploymentState();
      const id=String(projectId||'').trim();
      const capabilities=deploymentCapabilities(id);
      if(!capabilities.deployment){
        showToast('Deployment tools are not available in this restart branch yet.',2600);
        return null;
      }
      OPS.deploymentBusyByProject[id]=true;
      try{
        await api(deploymentProjectUrl(id,'/deployment/artifacts/scaffold'),{
          method:'POST',
          body:JSON.stringify({provider:'manual'}),
        });
        showToast('Deployment scaffold created',2600);
        return await loadProjectDeployment(id,{render:false});
      }finally{
        delete OPS.deploymentBusyByProject[id];
        renderCurrentOpsView();
      }
    }

    function renderProjectDeployment(project){
      if(!project||!project.id)return '';
      ensureDeploymentState();
      const data=OPS.deploymentsByProject[project.id]||{};
      const capabilities=deploymentCapabilities(project.id);
      const deployment=data.deployment||null;
      const artifacts=Array.isArray(data.artifacts)?data.artifacts:[];
      const logs=Array.isArray(data.logs)?data.logs:[];
      const busy=!!OPS.deploymentBusyByProject[project.id];
      const progress=OPS.deploymentProgressByProject&&OPS.deploymentProgressByProject[project.id]&&typeof OPS.deploymentProgressByProject[project.id]==='object'
        ? OPS.deploymentProgressByProject[project.id]
        : null;
      const progressLabel=progress&&progress.label?String(progress.label):busy?'Working on deployment':'';
      const progressDetail=progress&&progress.detail?String(progress.detail):busy?'Deployment operation is still running. You can leave this page open; the panel will refresh when it completes.':'';
      const status=capabilities.deployment
        ? (deployment&&deployment.status?deployment.status:'not configured')
        : 'unsupported';
      const summary=capabilities.deployment
        ? (deployment&&deployment.summary?deployment.summary:'No deployment has been recorded for this project.')
        : (data.summary||'Deployment tools are not available in this restart branch yet.');
      const artifactText=artifacts.length
        ? artifacts.slice(0,5).map(artifact=>artifact.relativePath||artifact.kind).join(' | ')
        : (capabilities.deployment?'No deployment artifacts detected.':'No deployment artifacts are available in this restart branch.');
      const latestLog=logs.length?logs[logs.length-1].message:'No deployment logs yet.';
      const deploymentSource=deployment&&deployment.source==='cloud-terminal'?'Cloud Terminal':'Hermes';
      const deploymentSlug=deployment&&deployment.slug?String(deployment.slug).trim():'';
      const deploymentDatabaseMode=deployment&&(deployment.databaseMode||(deployment.database&&deployment.database.mode))?String(deployment.databaseMode||(deployment.database&&deployment.database.mode)).trim():'';
      const canRedeploy=deploymentCanRedeploy(deployment);
      const recordHref=deployment&&deployment.recordPath?`/api/media?path=${encodeURIComponent(deployment.recordPath)}`:'';
      return `
        <section class="tasks-card ops-deployment-panel">
          <div class="tasks-card-header ops-deployment-header">
            <div>
              <div class="tasks-card-title">Deployment</div>
              <div class="tasks-card-subtitle">${esc(status)}</div>
            </div>
            <div class="tasks-card-actions ops-deployment-actions">
              <button class="menu-action-btn secondary small" type="button" data-ops-action="refresh-deployment" data-project-id="${esc(project.id)}" ${busy||!capabilities.deployment?'disabled':''}>${svg.refresh}<span>${busy?'Refreshing...':'Refresh'}</span></button>
              <button class="menu-action-btn secondary small" type="button" data-ops-action="scaffold-deployment" data-project-id="${esc(project.id)}" ${busy||!capabilities.deployment?'disabled':''}>${svg.plus}<span>Scaffold</span></button>
              <button class="menu-action-btn small" type="button" data-ops-action="redeploy-deployment" data-project-id="${esc(project.id)}" ${busy||!capabilities.deployment||!canRedeploy?'disabled':''}>${svg.refresh}<span>${busy?'Redeploying...':'Redeploy'}</span></button>
              <button class="menu-action-btn small" type="button" data-ops-action="record-deployment" data-deployment-action="deploy" data-project-id="${esc(project.id)}" ${busy||!capabilities.deployment?'disabled':''}>${svg.check}<span>Record</span></button>
              <button class="menu-action-btn small" type="button" data-ops-action="execute-deployment" data-deployment-action="deploy" data-project-id="${esc(project.id)}" ${busy||!capabilities.deployment?'disabled':''}>${svg.play}<span>Execute</span></button>
            </div>
          </div>
          <div class="tasks-card-body ops-deployment-body">
          ${busy?`
            <div class="ops-deployment-progress" role="status" aria-live="polite">
              <div class="ops-deployment-progress-head">
                <strong>${esc(progressLabel)}</strong>
                <span>Building and publishing…</span>
              </div>
              <div class="ops-deployment-progress-track" aria-hidden="true"><span></span></div>
              <div class="ops-deployment-progress-detail">${esc(progressDetail)}</div>
            </div>
          `:''}
          <div class="ops-deployment-summary">${esc(summary)}</div>
<div class="ops-deployment-meta">
              <span>${esc(providerLabel(deployment&&deployment.provider?deployment.provider:'manual'))}</span>
              <span>${esc(deploymentSource)}</span>
              ${deploymentSlug?`<span>${esc(deploymentSlug)}</span>`:''}
              ${deploymentDatabaseMode?`<span>${esc(`${deploymentDatabaseMode} database`)}</span>`:''}
              <span>${esc(deployment&&deployment.environment?deployment.environment:'production')}</span>
              ${deployment&&deployment.url?`<a href="${esc(deployment.url)}" target="_blank" rel="noopener noreferrer">${esc(deployment.url)}</a>`:''}
              ${recordHref?`<a href="${esc(recordHref)}" target="_blank" rel="noopener noreferrer">Record</a>`:''}
            </div>
            <div class="ops-deployment-summary">${esc(artifactText)}</div>
            <div class="ops-deployment-summary">${esc(latestLog)}</div>
          </div>
        </section>
      `;
    }

    function renderDeploymentProjectCard(project,index){
      if(!project||!project.id)return '';
      const capabilities=deploymentCapabilities(project.id);
      const data=OPS.deploymentsByProject[project.id]||{};
      const deployment=data.deployment||null;
      const status=capabilities.deployment
        ? (deployment&&deployment.status?deployment.status:'not configured')
        : 'unsupported';
      const path=projectPath(project);
      const repoLabel=project.fullName||project.repository||project.repo||project.name||project.id;
      const title=nameOf(project);
      const meta=[path,repoLabel&&repoLabel!==title?repoLabel:'',project.coreBranch||project.branch||'']
        .map(value=>String(value||'').trim())
        .filter(Boolean)
        .join(' • ');
      const busy=!!OPS.deploymentBusyByProject[project.id];
      return `
        <article class="quick-response-project-card ops-deployment-project-card ${capabilities.deployment?'':'project-inactive'}" data-project-id="${esc(project.id)}">
          <div class="quick-response-project-header">
            <div class="quick-response-project-main">
              <div class="quick-response-project-index">${esc(String((Number(index)||0)+1))}</div>
              <div class="quick-response-project-title-block">
                <div class="quick-response-project-title-line">
                  <div class="quick-response-project-title">${esc(title)}</div>
                  <span class="menu-session-activity-badge play-status-badge ${capabilities.deployment?'state-ready':'state-stopped'}" title="Deployment status">${esc(status)}</span>
                </div>
                <div class="quick-response-project-repo">${esc(meta||project.id)}</div>
              </div>
            </div>
            <div class="quick-response-project-actions">
              <button class="menu-action-btn secondary small" type="button" data-ops-action="open-project" data-project-id="${esc(project.id)}">Open project</button>
              <button class="menu-action-btn secondary small" type="button" data-ops-action="refresh-deployment" data-project-id="${esc(project.id)}" ${busy?'disabled':''}>${svg.refresh}<span>${busy?'Refreshing...':'Refresh'}</span></button>
            </div>
          </div>
          <div class="ops-deployment-project-body">
            ${renderProjectDeployment(project)}
          </div>
        </article>
      `;
    }

    function renderDeployments(){
      const el=root();
      if(!el)return '';
      ensureDeploymentState();
      const projects=Array.isArray(OPS.projects)?OPS.projects:[];
      const supportedCount=projects.filter(project=>project&&project.id&&deploymentCapabilities(project.id).deployment).length;
      const providers=providerList();
      const providerText=providers.length
        ? `${providers.length} provider${providers.length===1?'':'s'}: ${providers.map(provider=>provider&&provider.label||provider&&provider.id||'Provider').slice(0,4).join(', ')}`
        : 'Loading provider metadata...';
      const rows=projects.length
        ? projects.map((project,index)=>renderDeploymentProjectCard(project,index)).join('')
        : '<div class="repo-empty">No projects available yet.</div>';
      const statusText=projects.length
        ? `${projects.length} project${projects.length===1?'':'s'} loaded • ${supportedCount} deployment-enabled`
        : 'No projects available yet.';
      setDashboardTopbar('Deployments',projects.length?`${projects.length} projects`:'');
      el.innerHTML=`
        <div class="ops-dashboard ops-deployments-dashboard project-page-content deployments-page-content">
          <h2>Deployments</h2>
          <p class="menu-description">Publish isolated project builds, review deployment artifacts, and record or execute deployment operations.</p>
          <section class="quick-response-panel list-view ops-deployments-panel" aria-live="polite">
            <div class="quick-response-header">
              <div>
                <div class="quick-response-title">Deployment projects</div>
                <div class="quick-response-subtitle">${esc(statusText)}</div>
                <div class="quick-response-subtitle">${esc(providerText)}</div>
              </div>
              <div class="quick-response-nav">
                <button class="menu-action-btn secondary small" type="button" data-ops-action="back-home">Menu</button>
                <button class="menu-action-btn secondary small" type="button" data-ops-action="open-projects">Projects</button>
                <button class="menu-action-btn secondary small" type="button" data-ops-action="refresh-deployments">${svg.refresh}<span>Refresh deployments</span></button>
              </div>
            </div>
            <div class="quick-response-body">
              <div class="ops-deployments-list">${rows}</div>
            </div>
          </section>
        </div>
      `;
      return el.innerHTML;
    }

    async function loadDeployments(options){
      ensureDeploymentState();
      const opts=options&&typeof options==='object'?options:{};
      const token=++activeDeploymentsLoadToken;
      const [providersResult,projects]=await Promise.all([
        loadDeploymentProviders({render:false}).catch(()=>[]),
        loadProjects(),
      ]);
      if(Array.isArray(providersResult))OPS.deploymentProviders=providersResult;
      if(Array.isArray(projects))OPS.projects=projects;
      if(token!==activeDeploymentsLoadToken)return OPS.projects||[];
      const projectIds=(OPS.projects||[])
        .map(project=>String(project&&project.id||'').trim())
        .filter(Boolean);
      await Promise.allSettled(projectIds.map(projectId=>loadProjectDeployment(projectId,{render:false}).catch(()=>null)));
      if(token===activeDeploymentsLoadToken&&opts.render!==false&&deploymentsVisible())renderDeployments();
      return OPS.projects||[];
    }

    async function openDeployments(options){
      const opts=options&&typeof options==='object'?options:{};
      if(opts.historyMode!=='skip')syncStandaloneOpsHistory('deployments');
      OPS.view='deployments';
      OPS.currentProject=null;
      OPS.taskData=null;
      OPS.showCreate=false;
      setDashboardTopbar('Deployments','');
      renderLoading('Loading deployments...');
      await loadDeployments({render:false});
      return renderDeployments();
    }

    async function refreshDeployments(){
      return await loadDeployments();
    }

    return {
      openDeployments,
      refreshDeployments,
      renderDeployments,
      loadDeployments,
      loadDeploymentProviders,
      loadProjectDeployment,
      recordProjectDeployment,
      executeProjectDeployment,
      redeployProjectDeployment,
      scaffoldProjectDeployment,
      renderProjectDeployment,
    };
  }

  window.HermesOpsModules.deployments={
    name:'deployments',
    routes:[
      '/api/core/deployments/providers',
      '/deployment',
      '/deployment/config',
      '/deployment/logs',
      '/deployment/artifacts',
      '/deployment/artifacts/scaffold',
      '/deployment/redeploy',
      '/deployment/update',
    ],
    actions:[
      'refresh-deployments',
      'refresh-deployment',
      'scaffold-deployment',
      'record-deployment',
      'execute-deployment',
      'redeploy-deployment',
    ],
    bindDashboard,
  };
})();

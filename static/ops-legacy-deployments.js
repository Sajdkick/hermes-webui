(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};
  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const api=ctx&&ctx.api;
    const projectUrl=ctx&&ctx.projectUrl;
    const renderCurrentOpsView=ctx&&ctx.renderCurrentOpsView;
    const showToast=ctx&&ctx.showToast;
    const showPromptDialog=ctx&&ctx.showPromptDialog;
    const showConfirmDialog=ctx&&ctx.showConfirmDialog;
    const esc=ctx&&ctx.esc;
    const svg=ctx&&ctx.svg;
    if(!OPS||typeof api!=='function'||typeof projectUrl!=='function'||typeof renderCurrentOpsView!=='function'||typeof showToast!=='function'||typeof showPromptDialog!=='function'||typeof showConfirmDialog!=='function'||typeof esc!=='function'||!svg){
      return {};
    }

    const DEFAULT_PROJECT_CAPABILITIES={
      deployment:false,
    };

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

    async function loadProjectDeployment(projectId,options){
      const id=String(projectId||'').trim();
      if(!id)return null;
      const capabilities=projectCapabilities(id);
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
        const data=await api(projectUrl(id,'/deployment'));
        OPS.deploymentsByProject[id]=data;
        return data;
      }finally{
        delete OPS.deploymentBusyByProject[id];
        if(!options||options.render!==false)renderCurrentOpsView();
      }
    }

    async function recordProjectDeployment(projectId,action){
      const id=String(projectId||'').trim();
      const capabilities=projectCapabilities(id);
      if(!capabilities.deployment){
        showToast('Deployment tools are not available in this restart branch yet.',2600);
        return null;
      }
      const normalized=String(action||'deploy').trim().toLowerCase();
      const path=normalized==='deploy'?'/deployment':`/deployment/${normalized}`;
      OPS.deploymentBusyByProject[id]=true;
      try{
        await api(projectUrl(id,path),{
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
      const id=String(projectId||'').trim();
      const normalized=String(action||'deploy').trim().toLowerCase();
      if(!id)return null;
      const capabilities=projectCapabilities(id);
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
        const result=await api(projectUrl(id,'/deployment/execute'),{method:'POST',body:JSON.stringify(body)});
        if(result.operation)showToast(`Deployment ${result.operation.status}`,3200);
        return await loadProjectDeployment(id,{render:false});
      }finally{
        delete OPS.deploymentBusyByProject[id];
        renderCurrentOpsView();
      }
    }

    async function scaffoldProjectDeployment(projectId){
      const id=String(projectId||'').trim();
      const capabilities=projectCapabilities(id);
      if(!capabilities.deployment){
        showToast('Deployment tools are not available in this restart branch yet.',2600);
        return null;
      }
      OPS.deploymentBusyByProject[id]=true;
      try{
        await api(projectUrl(id,'/deployment/artifacts/scaffold'),{
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
      const data=OPS.deploymentsByProject[project.id]||{};
      const capabilities=projectCapabilities(project.id);
      const deployment=data.deployment||null;
      const artifacts=Array.isArray(data.artifacts)?data.artifacts:[];
      const logs=Array.isArray(data.logs)?data.logs:[];
      const busy=!!OPS.deploymentBusyByProject[project.id];
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
              <button class="menu-action-btn small" type="button" data-ops-action="record-deployment" data-deployment-action="deploy" data-project-id="${esc(project.id)}" ${busy||!capabilities.deployment?'disabled':''}>${svg.check}<span>Record</span></button>
              <button class="menu-action-btn small" type="button" data-ops-action="execute-deployment" data-deployment-action="deploy" data-project-id="${esc(project.id)}" ${busy||!capabilities.deployment?'disabled':''}>${svg.play}<span>Execute</span></button>
            </div>
          </div>
          <div class="tasks-card-body ops-deployment-body">
            <div class="ops-deployment-summary">${esc(summary)}</div>
            <div class="ops-deployment-meta">
              <span>${esc(deployment&&deployment.provider?deployment.provider:'manual')}</span>
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

    return {
      loadProjectDeployment,
      recordProjectDeployment,
      executeProjectDeployment,
      scaffoldProjectDeployment,
      renderProjectDeployment,
    };
  }

  window.HermesOpsModules.deployments={
    name:'deployments',
    routes:[
      '/api/ops/deployments/providers',
      '/deployment',
      '/deployment/config',
      '/deployment/logs',
      '/deployment/artifacts',
      '/deployment/artifacts/scaffold',
    ],
    actions:[
      'refresh-deployment',
      'scaffold-deployment',
      'record-deployment',
      'execute-deployment',
    ],
    bindDashboard,
  };
})();

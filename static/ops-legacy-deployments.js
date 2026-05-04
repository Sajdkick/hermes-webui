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

    async function loadProjectDeployment(projectId,options){
      const id=String(projectId||'').trim();
      if(!id)return null;
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
      const deployment=data.deployment||null;
      const artifacts=Array.isArray(data.artifacts)?data.artifacts:[];
      const logs=Array.isArray(data.logs)?data.logs:[];
      const busy=!!OPS.deploymentBusyByProject[project.id];
      const status=deployment&&deployment.status?deployment.status:'not configured';
      const summary=deployment&&deployment.summary?deployment.summary:'No deployment has been recorded for this project.';
      const artifactText=artifacts.length
        ? artifacts.slice(0,5).map(artifact=>artifact.relativePath||artifact.kind).join(' | ')
        : 'No deployment artifacts detected.';
      const latestLog=logs.length?logs[logs.length-1].message:'No deployment logs yet.';
      const recordHref=deployment&&deployment.recordPath?`/api/media?path=${encodeURIComponent(deployment.recordPath)}`:'';
      return `
        <section class="ops-deployment-panel">
          <div class="ops-deployment-header">
            <div>
              <h3>Deployment</h3>
              <span>${esc(status)}</span>
            </div>
            <div class="ops-deployment-actions">
              <button class="ops-btn" type="button" data-ops-action="refresh-deployment" data-project-id="${esc(project.id)}" ${busy?'disabled':''}>${svg.refresh}<span>${busy?'Refreshing...':'Refresh'}</span></button>
              <button class="ops-btn" type="button" data-ops-action="scaffold-deployment" data-project-id="${esc(project.id)}" ${busy?'disabled':''}>${svg.plus}<span>Scaffold</span></button>
              <button class="ops-btn primary" type="button" data-ops-action="record-deployment" data-deployment-action="deploy" data-project-id="${esc(project.id)}" ${busy?'disabled':''}>${svg.check}<span>Record</span></button>
              <button class="ops-btn primary" type="button" data-ops-action="execute-deployment" data-deployment-action="deploy" data-project-id="${esc(project.id)}" ${busy?'disabled':''}>${svg.play}<span>Execute</span></button>
            </div>
          </div>
          <div class="ops-deployment-body">
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

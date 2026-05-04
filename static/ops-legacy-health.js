(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};
  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const api=ctx&&ctx.api;
    const projectUrl=ctx&&ctx.projectUrl;
    const renderCurrentOpsView=ctx&&ctx.renderCurrentOpsView;
    const showToast=ctx&&ctx.showToast;
    const showConfirmDialog=ctx&&ctx.showConfirmDialog;
    const esc=ctx&&ctx.esc;
    const svg=ctx&&ctx.svg;
    const nameOf=ctx&&ctx.nameOf;
    const findProject=ctx&&ctx.findProject;
    const openProjects=ctx&&ctx.openProjects;
    const renderProjectProfileOptions=ctx&&ctx.renderProjectProfileOptions;
    const mergeProjectUpdate=ctx&&ctx.mergeProjectUpdate;
    const AgentBridgeRef=ctx&&ctx.AgentBridge;
    const runtimeApi=AgentBridgeRef&&AgentBridgeRef.runtime;
    if(!OPS||typeof api!=='function'||typeof projectUrl!=='function'||typeof renderCurrentOpsView!=='function'||typeof showToast!=='function'||typeof esc!=='function'||!svg){
      return {};
    }

    const DEFAULT_PROJECT_CAPABILITIES={
      ensureWorkspace:true,
      projectSettings:true,
      projectActivity:true,
      projectDeletion:true,
      dependencyHealth:false,
      dependencyInstall:false,
      inodeScan:false,
      inodeCleanup:false,
      deployment:false,
    };

    function projectCapabilities(projectId){
      const id=String(projectId||'').trim();
      const project=(typeof findProject==='function'&&findProject(id))
        || (OPS.currentProject&&OPS.currentProject.id===id?OPS.currentProject:null)
        || null;
      const caps=project&&project.opsCapabilities&&typeof project.opsCapabilities==='object'
        ? project.opsCapabilities
        : {};
      return {...DEFAULT_PROJECT_CAPABILITIES,...caps};
    }

    async function loadMigrationHealth(options){
      OPS.migrationHealthBusy=true;
      try{
        OPS.migrationHealth=await api('/api/ops/migration/health');
        return OPS.migrationHealth;
      }finally{
        OPS.migrationHealthBusy=false;
        if(!options||options.render!==false)renderCurrentOpsView();
      }
    }

    async function loadArtifactHealth(options){
      OPS.artifactHealthBusy=true;
      try{
        OPS.artifactHealth=await api('/api/ops/artifacts/health');
        return OPS.artifactHealth;
      }finally{
        OPS.artifactHealthBusy=false;
        if(!options||options.render!==false)renderCurrentOpsView();
      }
    }

    function migrationHealthKind(status){
      const normalized=String(status||'').toLowerCase();
      if(normalized==='ready')return 'ready';
      if(normalized==='blocked')return 'error';
      return 'warning';
    }

    function migrationHealthLabel(status){
      const normalized=String(status||'').toLowerCase();
      if(normalized==='ready')return 'Ready';
      if(normalized==='blocked')return 'Blocked';
      return 'Needs attention';
    }

    function artifactHealthKind(health){
      const issues=Number(health&&health.issueCount||0);
      return issues>0?'warning':'ready';
    }

    function artifactIssueLabel(issue){
      const kind=String(issue&&issue.issue||'issue').replace(/-/g,' ');
      return kind.charAt(0).toUpperCase()+kind.slice(1);
    }

    function renderMigrationHealthPanel(){
      const health=OPS.migrationHealth&&typeof OPS.migrationHealth==='object'?OPS.migrationHealth:null;
      const busy=OPS.migrationHealthBusy;
      if(!health&&busy){
        return `
          <section class="ops-panel ops-migration-health-panel">
            <div class="ops-panel-header">
              <div>
                <h2>Migration health</h2>
                <span>Checking Cloud Terminal retirement readiness.</span>
              </div>
            </div>
            <div class="ops-empty">Loading migration health...</div>
          </section>
        `;
      }
      if(!health){
        return `
          <section class="ops-panel ops-migration-health-panel">
            <div class="ops-panel-header">
              <div>
                <h2>Migration health</h2>
                <span>Cloud Terminal retirement readiness.</span>
              </div>
              <button class="ops-btn" type="button" data-ops-action="refresh-migration-health">${svg.refresh}<span>Refresh</span></button>
            </div>
            <div class="ops-empty">Migration health has not been loaded yet.</div>
          </section>
        `;
      }
      const checks=Array.isArray(health.checks)?health.checks:[];
      const counts=health.counts&&typeof health.counts==='object'?health.counts:{};
      const countItems=[
        ['Projects',counts.projects],
        ['Tasks',counts.tasks],
        ['Active runs',counts.activeRuns],
        ['Artifacts',counts.artifacts],
        ['Artifact issues',counts.artifactIssues],
        ['Open notifications',counts.openNotifications],
        ['Legacy paths',counts.legacyDataPaths],
        ['Git conflicts',counts.gitConflicts],
        ['Play running',counts.playRunning],
      ].filter(([,value])=>value!==undefined&&value!==null);
      const countRows=countItems.length
        ? countItems.map(([label,value])=>`<span><strong>${esc(value)}</strong>${esc(label)}</span>`).join('')
        : '<span><strong>0</strong>Signals</span>';
      const checkRows=checks.length
        ? checks.map(check=>{
            const kind=migrationHealthKind(check.status);
            const action=check.nextAction
              ? `<em class="ops-migration-health-action">${esc(check.nextAction)}</em>`
              : '';
            return `
              <div class="ops-migration-health-check ${esc(kind)}">
                <div>
                  <strong>${esc(check.title||check.id||'Check')}</strong>
                  <span>${esc(check.summary||'No summary available.')}</span>
                  ${action}
                </div>
                <span class="ops-git-status ${esc(kind)}">${esc(migrationHealthLabel(check.status))}</span>
              </div>
            `;
          }).join('')
        : '<div class="ops-migration-health-check empty"><span>No migration checks were returned.</span></div>';
      return `
        <section class="ops-panel ops-migration-health-panel ${esc(migrationHealthKind(health.status))}">
          <div class="ops-panel-header">
            <div>
              <h2>Migration health</h2>
              <span>${esc(health.summary||'Cloud Terminal retirement readiness.')}</span>
            </div>
            <button class="ops-btn" type="button" data-ops-action="refresh-migration-health" ${busy?'disabled':''}>${svg.refresh}<span>${busy?'Refreshing...':'Refresh'}</span></button>
          </div>
          <div class="ops-migration-health-counts">${countRows}</div>
          <div class="ops-migration-health-checks">${checkRows}</div>
        </section>
      `;
    }

    function renderArtifactHealthPanel(){
      const health=OPS.artifactHealth&&typeof OPS.artifactHealth==='object'?OPS.artifactHealth:null;
      const busy=OPS.artifactHealthBusy;
      if(!health&&busy){
        return `
          <section class="ops-panel ops-artifact-health-panel">
            <div class="ops-panel-header">
              <div>
                <h2>Artifact health</h2>
                <span>Checking native run artifact recoverability.</span>
              </div>
            </div>
            <div class="ops-empty">Loading artifact health...</div>
          </section>
        `;
      }
      if(!health){
        return `
          <section class="ops-panel ops-artifact-health-panel">
            <div class="ops-panel-header">
              <div>
                <h2>Artifact health</h2>
                <span>Native run artifact recoverability.</span>
              </div>
              <button class="ops-btn" type="button" data-ops-action="refresh-artifact-health">${svg.refresh}<span>Refresh</span></button>
            </div>
            <div class="ops-empty">Artifact health has not been loaded yet.</div>
          </section>
        `;
      }
      const issueCount=Number(health.issueCount||0);
      const countItems=[
        ['Artifacts',health.artifactCount],
        ['File refs',health.fileReferenceCount],
        ['URL refs',health.urlReferenceCount],
        ['Missing files',health.missingFileCount],
        ['Orphan metadata',health.orphanArtifactCount],
        ['Issues',health.issueCount],
      ].filter(([,value])=>value!==undefined&&value!==null);
      const countRows=countItems.length
        ? countItems.map(([label,value])=>`<span><strong>${esc(value)}</strong>${esc(label)}</span>`).join('')
        : '<span><strong>0</strong>Artifacts</span>';
      const issues=Array.isArray(health.issues)?health.issues:[];
      const issueRows=issues.length
        ? issues.slice(0,6).map(issue=>{
            const title=String(issue&&issue.title||issue&&issue.artifactId||'Artifact');
            const runId=String(issue&&issue.runId||'');
            const path=String(issue&&issue.path||'');
            return `
              <div class="ops-artifact-health-issue">
                <strong>${esc(artifactIssueLabel(issue))}</strong>
                <span>${esc(title)}${runId?` (${esc(runId)})`:''}</span>
                ${path?`<em>${esc(path)}</em>`:''}
              </div>
            `;
          }).join('')
        : `<div class="ops-artifact-health-issue empty"><span>${issueCount?'No issue details were returned.':'No broken artifact references recorded.'}</span></div>`;
      const truncated=Number(health.truncatedIssues||0);
      const truncatedRow=truncated?`<div class="ops-artifact-health-more">${esc(String(truncated))} more issue(s)</div>`:'';
      return `
        <section class="ops-panel ops-artifact-health-panel ${esc(artifactHealthKind(health))}">
          <div class="ops-panel-header">
            <div>
              <h2>Artifact health</h2>
              <span>${esc(issueCount?`${issueCount} artifact issue(s) need attention.`:'Native run artifacts are recoverable.')}</span>
            </div>
            <button class="ops-btn" type="button" data-ops-action="refresh-artifact-health" ${busy?'disabled':''}>${svg.refresh}<span>${busy?'Refreshing...':'Refresh'}</span></button>
          </div>
          <div class="ops-artifact-health-counts">${countRows}</div>
          <div class="ops-artifact-health-issues">${issueRows}${truncatedRow}</div>
        </section>
      `;
    }

    function projectHealthFor(projectId){
      return OPS.projectHealthByProject[projectId]||{};
    }

    async function loadProjectDependencyStatus(projectId,options){
      const id=String(projectId||'').trim();
      if(!id)return null;
      const capabilities=projectCapabilities(id);
      if(!capabilities.dependencyHealth){
        const unsupported={
          supported:false,
          status:'unsupported',
          message:'Dependency health is not available in this restart branch yet.',
          installCommandText:'Dependency health is not available in this restart branch yet.',
        };
        OPS.projectHealthByProject[id]={...(OPS.projectHealthByProject[id]||{}),dependencies:unsupported};
        if(!options||options.render!==false)renderCurrentOpsView();
        return unsupported;
      }
      OPS.projectHealthBusyByProject[id]='dependencies';
      try{
        const data=await api(projectUrl(id,'/dependencies'));
        OPS.projectHealthByProject[id]={...(OPS.projectHealthByProject[id]||{}),dependencies:data.dependencies||data};
        if(data.project&&typeof mergeProjectUpdate==='function')mergeProjectUpdate(data.project);
        return data;
      }finally{
        delete OPS.projectHealthBusyByProject[id];
        if(!options||options.render!==false)renderCurrentOpsView();
      }
    }

    async function scanProjectInodes(projectId,options){
      const id=String(projectId||'').trim();
      if(!id)return null;
      const capabilities=projectCapabilities(id);
      if(!capabilities.inodeScan){
        const unsupported={
          supported:false,
          status:'unsupported',
          message:'node_modules inode scanning is not available in this restart branch yet.',
        };
        OPS.projectHealthByProject[id]={...(OPS.projectHealthByProject[id]||{}),inodeScan:unsupported};
        if(!options||options.render!==false)renderCurrentOpsView();
        return unsupported;
      }
      OPS.projectHealthBusyByProject[id]='inodes';
      try{
        const data=await api(projectUrl(id,'/inodes'));
        OPS.projectHealthByProject[id]={...(OPS.projectHealthByProject[id]||{}),inodeScan:data.inodeScan||data};
        if(data.project&&typeof mergeProjectUpdate==='function')mergeProjectUpdate(data.project);
        return data;
      }finally{
        delete OPS.projectHealthBusyByProject[id];
        if(!options||options.render!==false)renderCurrentOpsView();
      }
    }

    async function setProjectActivity(projectId,active){
      const id=String(projectId||'').trim();
      if(!id)return null;
      const capabilities=projectCapabilities(id);
      if(!capabilities.projectActivity){
        showToast('Project activation is not available in this restart branch yet.',2600);
        return null;
      }
      OPS.projectHealthBusyByProject[id]='activity';
      try{
        const data=await api(projectUrl(id,'/activity'),{method:'POST',body:JSON.stringify({active:!!active})});
        if(data.project&&typeof mergeProjectUpdate==='function')mergeProjectUpdate(data.project);
        OPS.projectHealthByProject[id]={...(OPS.projectHealthByProject[id]||{}),activity:data.activity||null};
        showToast(active?'Project activated':'Project deactivated',2200);
        return data;
      }finally{
        delete OPS.projectHealthBusyByProject[id];
        renderCurrentOpsView();
      }
    }

    async function installProjectDependencies(projectId){
      const id=String(projectId||'').trim();
      if(!id)return null;
      const capabilities=projectCapabilities(id);
      if(!capabilities.dependencyInstall){
        showToast('Dependency install is not available in this restart branch yet.',2600);
        return null;
      }
      const ok=await (typeof showConfirmDialog==='function'
        ? showConfirmDialog({
            title:'Install dependencies',
            message:'Run the detected dependency install command in this project. Hermes will record the command output and status.',
            confirmLabel:'Install',
            focusCancel:true,
          })
        : Promise.resolve(false));
      if(!ok)return null;
      OPS.projectHealthBusyByProject[id]='install';
      try{
        const data=await api(projectUrl(id,'/dependencies/install'),{method:'POST',body:JSON.stringify({confirm:'install'})});
        if(data.project&&typeof mergeProjectUpdate==='function')mergeProjectUpdate(data.project);
        OPS.projectHealthByProject[id]={...(OPS.projectHealthByProject[id]||{}),dependencies:data.dependencies||null,dependencyOperation:data.operation||null};
        const status=(data.operation&&data.operation.status)||'finished';
        showToast(`Dependency install ${status}`,3200);
        return data;
      }finally{
        delete OPS.projectHealthBusyByProject[id];
        renderCurrentOpsView();
      }
    }

    async function cleanupProjectNodeModules(projectId){
      const id=String(projectId||'').trim();
      if(!id)return null;
      const capabilities=projectCapabilities(id);
      if(!capabilities.inodeCleanup){
        showToast('node_modules cleanup is not available in this restart branch yet.',2600);
        return null;
      }
      const ok=await (typeof showConfirmDialog==='function'
        ? showConfirmDialog({
            title:'Clean node_modules',
            message:'Delete node_modules directories inside this project only. Hermes will record what was removed and refresh the inode scan.',
            confirmLabel:'Clean',
            focusCancel:true,
          })
        : Promise.resolve(false));
      if(!ok)return null;
      OPS.projectHealthBusyByProject[id]='cleanup';
      try{
        const data=await api(projectUrl(id,'/inodes/cleanup'),{method:'POST',body:JSON.stringify({confirm:'cleanup-node-modules'})});
        if(data.project&&typeof mergeProjectUpdate==='function')mergeProjectUpdate(data.project);
        OPS.projectHealthByProject[id]={...(OPS.projectHealthByProject[id]||{}),inodeScan:data.inodeScan||null,cleanup:data.cleanup||null};
        const removed=(data.cleanup&&Array.isArray(data.cleanup.removed))?data.cleanup.removed.length:0;
        showToast(`Removed ${removed} node_modules director${removed===1?'y':'ies'}`,3200);
        return data;
      }finally{
        delete OPS.projectHealthBusyByProject[id];
        renderCurrentOpsView();
      }
    }

    async function deleteProject(projectId){
      const id=String(projectId||'').trim();
      const project=(typeof findProject==='function'&&findProject(id))||OPS.currentProject||{};
      if(!id)return null;
      const capabilities=projectCapabilities(id);
      if(!capabilities.projectDeletion){
        showToast('Project deletion is not available in this restart branch yet.',2600);
        return null;
      }
      const ok=await (typeof showConfirmDialog==='function'
        ? showConfirmDialog({
            title:'Delete project',
            message:`Remove ${nameOf(project)} from the Hermes project list. The project files stay on disk and Hermes records an audit entry.`,
            confirmLabel:'Delete',
            focusCancel:true,
          })
        : Promise.resolve(false));
      if(!ok)return null;
      OPS.projectHealthBusyByProject[id]='delete';
      try{
        const data=await api(projectUrl(id,'/delete'),{method:'POST',body:JSON.stringify({confirm:'delete-project'})});
        OPS.projects=Array.isArray(data.projects)?data.projects:(OPS.projects||[]).filter(entry=>entry&&entry.id!==id);
        delete OPS.counts[id];
        delete OPS.taskDataByProject[id];
        delete OPS.gitStatusByProject[id];
        delete OPS.playStatusByProject[id];
        delete OPS.projectHealthByProject[id];
        showToast('Project removed from Hermes',2800);
        return typeof openProjects==='function'?openProjects():data;
      }finally{
        delete OPS.projectHealthBusyByProject[id];
      }
    }

    function gatherReportsFor(projectId){
      return OPS.gatherReportsByProject[projectId]||[];
    }

    async function loadProjectGatherReports(projectId,options){
      const id=String(projectId||'').trim();
      if(!id)return [];
      OPS.gatherBusyByProject[id]=true;
      try{
        const data=runtimeApi&&typeof runtimeApi.gatherReports==='function'
          ? await runtimeApi.gatherReports(id,{limit:5})
          : {reports:[]};
        const reports=Array.isArray(data.reports)?data.reports:[];
        OPS.gatherReportsByProject[id]=reports;
        return reports;
      }finally{
        delete OPS.gatherBusyByProject[id];
        if(!options||options.render!==false)renderCurrentOpsView();
      }
    }

    function gatherStatusKind(status){
      const value=String(status||'created').toLowerCase();
      if(value==='succeeded')return 'ready';
      if(value==='failed')return 'error';
      if(value==='running')return 'running';
      return 'idle';
    }

    function gatherStatusLabel(status){
      const value=String(status||'created').toLowerCase();
      if(value==='succeeded')return 'Succeeded';
      if(value==='failed')return 'Failed';
      if(value==='running')return 'Running';
      return 'Created';
    }

    function reviewRequestsFor(projectId){
      return OPS.reviewRequestsByProject[projectId]||[];
    }

    async function loadProjectReviewRequests(projectId,options){
      const id=String(projectId||'').trim();
      if(!id)return [];
      OPS.reviewBusyByProject[id]=true;
      try{
        const data=runtimeApi&&typeof runtimeApi.reviewRequests==='function'
          ? await runtimeApi.reviewRequests(id,{limit:5})
          : {reviews:[]};
        const reviews=Array.isArray(data.reviews)?data.reviews:[];
        OPS.reviewRequestsByProject[id]=reviews;
        return reviews;
      }finally{
        delete OPS.reviewBusyByProject[id];
        if(!options||options.render!==false)renderCurrentOpsView();
      }
    }

    function reviewStatusKind(status){
      const value=String(status||'requested').toLowerCase();
      if(value==='succeeded')return 'ready';
      if(value==='failed'||value==='canceled')return 'error';
      if(value==='running')return 'running';
      return 'idle';
    }

    function reviewStatusLabel(status){
      const value=String(status||'requested').toLowerCase();
      if(value==='succeeded')return 'Succeeded';
      if(value==='failed')return 'Failed';
      if(value==='canceled')return 'Canceled';
      if(value==='running')return 'Running';
      return 'Requested';
    }

    function formatIsoTime(value){
      const text=String(value||'').trim();
      if(!text)return 'No timestamp';
      const stamp=Date.parse(text);
      if(!Number.isFinite(stamp))return text;
      try{
        return new Date(stamp).toLocaleString();
      }catch(e){
        return text;
      }
    }

    function renderProjectGatherReports(project){
      if(!project||!project.id)return '';
      const reports=gatherReportsFor(project.id);
      const busy=!!OPS.gatherBusyByProject[project.id];
      const rows=reports.length?reports.map(report=>{
        const kind=gatherStatusKind(report.status);
        const latest=report.latestEvent&&report.latestEvent.message?report.latestEvent.message:(report.summary||'No summary recorded.');
        const meta=[
          formatIsoTime(report.updatedAt||report.createdAt),
          report.eventsCount?`${report.eventsCount} events`:'',
          report.runId?`Run ${report.runId}`:'',
        ].filter(Boolean).join(' | ');
        const href=report.reportPath?`/api/media?path=${encodeURIComponent(report.reportPath)}`:'';
        return `
          <div class="ops-gather-report">
            <div class="ops-gather-main">
              <div class="ops-gather-title-row">
                <span class="ops-gather-status ${esc(kind)}">${esc(gatherStatusLabel(report.status))}</span>
                <span class="ops-gather-title">${esc(report.title||'Runtime gather report')}</span>
              </div>
              <div class="ops-gather-meta">${esc(meta)}</div>
              <div class="ops-gather-summary">${esc(latest)}</div>
            </div>
            ${href?`<a class="ops-btn" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${svg.folder}<span>Open</span></a>`:''}
          </div>
        `;
      }).join(''):`<div class="ops-project-session-empty">No runtime gather reports for this project.</div>`;
      return `
        <section class="ops-gather-panel">
          <div class="ops-gather-header">
            <div>
              <h3>Runtime reports</h3>
              <span>${esc(reports.length?`${reports.length} latest report${reports.length===1?'':'s'}`:'No reports yet')}</span>
            </div>
            <button class="ops-btn" type="button" data-ops-action="refresh-gather-reports" data-project-id="${esc(project.id)}" ${busy?'disabled':''}>${svg.refresh}<span>${busy?'Refreshing...':'Refresh'}</span></button>
          </div>
          <div class="ops-gather-list">${rows}</div>
        </section>
      `;
    }

    function renderProjectReviewRequests(project){
      if(!project||!project.id)return '';
      const reviews=reviewRequestsFor(project.id);
      const busy=!!OPS.reviewBusyByProject[project.id];
      const rows=reviews.length?reviews.map(review=>{
        const kind=reviewStatusKind(review.status);
        const latest=review.summary||review.latestEvent&&review.latestEvent.message||review.prompt||'No review result recorded.';
        const meta=[
          formatIsoTime(review.updatedAt||review.createdAt),
          review.kind||'visual',
          review.eventsCount?`${review.eventsCount} events`:'',
          review.runId?`Run ${review.runId}`:'',
        ].filter(Boolean).join(' | ');
        const href=review.reviewPath?`/api/media?path=${encodeURIComponent(review.reviewPath)}`:'';
        return `
          <div class="ops-gather-report">
            <div class="ops-gather-main">
              <div class="ops-gather-title-row">
                <span class="ops-gather-status ${esc(kind)}">${esc(reviewStatusLabel(review.status))}</span>
                <span class="ops-gather-title">${esc(review.title||'Runtime review')}</span>
              </div>
              <div class="ops-gather-meta">${esc(meta)}</div>
              <div class="ops-gather-summary">${esc(latest)}</div>
            </div>
            ${href?`<a class="ops-btn" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${svg.folder}<span>Open</span></a>`:''}
          </div>
        `;
      }).join(''):`<div class="ops-project-session-empty">No runtime reviews for this project.</div>`;
      return `
        <section class="ops-gather-panel">
          <div class="ops-gather-header">
            <div>
              <h3>Runtime reviews</h3>
              <span>${esc(reviews.length?`${reviews.length} latest review${reviews.length===1?'':'s'}`:'No reviews yet')}</span>
            </div>
            <button class="ops-btn" type="button" data-ops-action="refresh-review-requests" data-project-id="${esc(project.id)}" ${busy?'disabled':''}>${svg.refresh}<span>${busy?'Refreshing...':'Refresh'}</span></button>
          </div>
          <div class="ops-gather-list">${rows}</div>
        </section>
      `;
    }

    function compactBytes(value){
      const number=Number(value)||0;
      if(number<1024)return `${number} B`;
      const units=['KB','MB','GB','TB'];
      let amount=number/1024;
      let index=0;
      while(amount>=1024&&index<units.length-1){
        amount/=1024;
        index++;
      }
      return `${amount>=10?amount.toFixed(0):amount.toFixed(1)} ${units[index]}`;
    }

    function renderProjectHealth(project){
      const health=projectHealthFor(project.id);
      const capabilities=projectCapabilities(project.id);
      const dependencies=health.dependencies||{};
      const inodeScan=health.inodeScan||null;
      const cleanup=health.cleanup||null;
      const operation=health.dependencyOperation||(project.lastDependencyInstall||null);
      const busy=OPS.projectHealthBusyByProject[project.id]||'';
      const active=project.active!==false;
      const manager=capabilities.dependencyHealth?(dependencies.manager||'none'):'unavailable';
      const dependencyStatus=capabilities.dependencyHealth?(dependencies.status||'unknown'):'unsupported';
      const command=capabilities.dependencyHealth
        ? (dependencies.installCommandText||'No supported install command detected')
        : (dependencies.message||'Dependency health is not available in this restart branch yet.');
      const totalInodes=inodeScan?inodeScan.totalInodes:project.lastNodeModulesInodes;
      const totalBytes=inodeScan?inodeScan.totalBytes:project.lastNodeModulesBytes;
      const directories=inodeScan&&Array.isArray(inodeScan.directories)?inodeScan.directories:[];
      const directorySummary=!capabilities.inodeScan
        ? 'node_modules scan is not available in this restart branch yet.'
        : directories.length
          ? `${directories.length} node_modules director${directories.length===1?'y':'ies'}`
          : totalInodes?'Stored scan data':'No node_modules scan loaded';
      const installSummary=operation
        ? `${operation.status||'unknown'} ${operation.updatedAt||operation.finishedAt||''}`.trim()
        : (capabilities.dependencyInstall?'No install operation recorded':'Install is unavailable in this restart branch.');
      const cleanupSummary=!capabilities.inodeCleanup
        ? 'Cleanup is unavailable in this restart branch.'
        : cleanup
          ? `${cleanup.status||'unknown'} | removed ${Array.isArray(cleanup.removed)?cleanup.removed.length:0}`
          : (project.lastNodeModulesCleanup?`${project.lastNodeModulesCleanup.status||'cleanup'} | removed ${project.lastNodeModulesCleanup.removedCount||0}`:'No cleanup recorded');
      return `
        <section class="ops-project-health-panel ${active?'active':'inactive'}">
          <div class="ops-project-health-header">
            <div>
              <span class="ops-panel-title">Project health</span>
              <small>${esc(active?'Active project':'Inactive project')}</small>
            </div>
            <div class="ops-project-health-actions">
              <button class="ops-btn" type="button" data-ops-action="toggle-project-activity" data-project-id="${esc(project.id)}" data-project-active="${active?'false':'true'}" ${busy==='activity'||!capabilities.projectActivity?'disabled':''}>${active?svg.close:svg.check}<span>${active?'Deactivate':'Activate'}</span></button>
              <button class="ops-btn" type="button" data-ops-action="refresh-project-health" data-project-id="${esc(project.id)}" ${busy||!capabilities.dependencyHealth?'disabled':''}>${svg.refresh}<span>Refresh</span></button>
              <button class="ops-btn" type="button" data-ops-action="scan-project-inodes" data-project-id="${esc(project.id)}" ${busy||!capabilities.inodeScan?'disabled':''}>${svg.grid}<span>Scan</span></button>
            </div>
          </div>
          <div class="ops-project-health-grid">
            <div>
              <span>Dependencies</span>
              <strong>${esc(manager)} ${esc(dependencyStatus)}</strong>
              <small>${esc(command)}</small>
              <small>${esc(installSummary)}</small>
              <button class="ops-btn" type="button" data-ops-action="install-project-dependencies" data-project-id="${esc(project.id)}" ${busy||!capabilities.dependencyInstall||!dependencies.supported?'disabled':''}>${svg.play}<span>${busy==='install'?'Installing...':'Install'}</span></button>
            </div>
            <div>
              <span>node_modules</span>
              <strong>${esc(totalInodes!=null?`${totalInodes} inodes`:'Not scanned')}</strong>
              <small>${esc(totalBytes!=null?compactBytes(totalBytes):directorySummary)}</small>
              <small>${esc(cleanupSummary)}</small>
              <button class="ops-btn danger" type="button" data-ops-action="cleanup-project-inodes" data-project-id="${esc(project.id)}" ${busy||!capabilities.inodeCleanup||!directories.length?'disabled':''}>${svg.trash}<span>${busy==='cleanup'?'Cleaning...':'Clean'}</span></button>
            </div>
          </div>
        </section>
      `;
    }

    function renderProjectSettings(project){
      if(!project||!project.id)return '';
      return `
        <section class="ops-panel">
          <div class="ops-panel-header">
            <div>
              <h2>Project profile</h2>
              <span>New chats and task sessions activate this profile and use its memories, skills, and default model.</span>
            </div>
          </div>
          <form class="ops-inline-form" data-ops-submit="project-settings" data-project-id="${esc(project.id)}">
            <label>
              <span>Assigned profile</span>
              <select name="profile">${typeof renderProjectProfileOptions==='function'?renderProjectProfileOptions(project.profile,{allowBlank:true,blankLabel:'No assigned profile'}):''}</select>
            </label>
            <div class="ops-form-actions">
              <button class="ops-btn primary" type="submit">${svg.check}<span>Save</span></button>
            </div>
          </form>
        </section>
      `;
    }

    async function saveProjectSettings(projectId,data){
      const id=String(projectId||'').trim();
      if(!id)return null;
      const capabilities=projectCapabilities(id);
      if(!capabilities.projectSettings){
        showToast('Project settings are not available in this restart branch yet.',2600);
        return null;
      }
      const response=await api(projectUrl(id,'/settings'),{
        method:'POST',
        body:JSON.stringify({profile:String(data&&data.profile||'').trim()}),
      });
      if(response&&response.project&&typeof mergeProjectUpdate==='function')mergeProjectUpdate(response.project);
      showToast('Project profile saved',2400);
      return response;
    }

    return {
      loadMigrationHealth,
      loadArtifactHealth,
      renderMigrationHealthPanel,
      renderArtifactHealthPanel,
      loadProjectDependencyStatus,
      scanProjectInodes,
      setProjectActivity,
      installProjectDependencies,
      cleanupProjectNodeModules,
      deleteProject,
      loadProjectGatherReports,
      loadProjectReviewRequests,
      renderProjectGatherReports,
      renderProjectReviewRequests,
      renderProjectHealth,
      renderProjectSettings,
      saveProjectSettings,
    };
  }

  window.HermesOpsModules.health={
    name:'health',
    routes:[
      '/api/ops/migration/health',
      '/api/ops/artifacts/health',
      '/dependencies',
      '/dependencies/install',
      '/inodes',
      '/inodes/cleanup',
      '/activity',
      '/delete',
      '/settings',
    ],
    actions:[
      'refresh-migration-health',
      'refresh-artifact-health',
      'refresh-project-health',
      'scan-project-inodes',
      'toggle-project-activity',
      'install-project-dependencies',
      'cleanup-project-inodes',
      'delete-project',
      'refresh-gather-reports',
      'refresh-review-requests',
    ],
    bindDashboard,
  };
})();

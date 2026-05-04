(function(){
  function escapeHtml(value){
    return String(value||'')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  function statusMeta(value){
    const status=String(value||'running').trim().toLowerCase();
    if(status==='succeeded')return { label:'Succeeded', kind:'ready' };
    if(status==='failed' || status==='stopped' || status==='stale')return { label:status[0].toUpperCase()+status.slice(1), kind:'error' };
    if(status==='waiting-approval')return { label:'Waiting approval', kind:'warning' };
    if(status==='waiting-input')return { label:'Waiting input', kind:'warning' };
    if(status==='queued')return { label:'Queued', kind:'idle' };
    if(status==='starting')return { label:'Starting', kind:'idle' };
    return { label:'Running', kind:'idle' };
  }

  function formatTime(value){
    const raw=String(value||'').trim();
    if(!raw)return 'No activity yet';
    try{
      return new Date(raw).toLocaleString();
    }catch(_error){
      return raw;
    }
  }

  function renderSection(state){
    const selectedProjectId=String(state && state.selectedProjectId || '').trim();
    const loading=!!(state && state.loadingRuns);
    const error=String(state && state.runsError || '').trim();
    const allRuns=Array.isArray(state && state.runs) ? state.runs.slice() : [];
    const matching=selectedProjectId
      ? allRuns.filter(function(run){ return String(run && run.projectId || '')===selectedProjectId; })
      : allRuns;
    const runs=matching.length || selectedProjectId ? matching : allRuns;
    const rows=runs.length ? runs.map(function(run){
      const meta=statusMeta(run && run.status);
      const project=run && run.project ? run.project : null;
      const task=run && run.task ? run.task : null;
      const readableOutput=run && run.readableOutput ? run.readableOutput : null;
      const pendingCount=Number(run && run.pendingRequestCount || 0);
      const sessionUrl=String(run && run.sessionUrl || '').trim();
      const readableUrl=String(readableOutput && readableOutput.available && readableOutput.url || '').trim();
      return [
        '<article class="ops-run-card">',
        '<div class="ops-run-copy">',
        '<div class="ops-run-title-row">',
        '<strong>'+escapeHtml(run && run.title || 'Run')+'</strong>',
        '<span class="ops-run-status '+escapeHtml(meta.kind)+'">'+escapeHtml(meta.label)+'</span>',
        '</div>',
        '<p class="ops-run-meta">'+escapeHtml([
          project && project.name ? project.name : '',
          task && task.text ? task.text : '',
          pendingCount ? String(pendingCount)+' pending request'+(pendingCount===1?'':'s') : '',
          formatTime(run && (run.updatedAt || run.createdAt))
        ].filter(Boolean).join(' • '))+'</p>',
        '</div>',
        '<div class="ops-task-actions">',
        sessionUrl ? '<a class="ops-shell-link" href="'+escapeHtml(sessionUrl)+'">Open session</a>' : '',
        readableUrl ? '<a class="ops-shell-link" href="'+escapeHtml(readableUrl)+'">Readable output</a>' : '',
        '</div>',
        '</article>'
      ].join('');
    }).join('') : '<p class="ops-shell-loading">'+escapeHtml(loading ? 'Loading runs…' : 'No task-linked runs yet.')+'</p>';
    return [
      '<section class="ops-run-panel">',
      '<div class="ops-notification-toolbar">',
      '<div>',
      '<h2>Run activity</h2>',
      '<p class="ops-notification-copy">Recent task-linked Hermes sessions, readable output, and pending requests.</p>',
      '</div>',
      '<button class="ops-shell-link" type="button" data-ops-action="refresh-runs"'+(loading?' disabled':'')+'>'+(loading?'Refreshing…':'Refresh runs')+'</button>',
      '</div>',
      error ? '<p class="ops-shell-error">'+escapeHtml(error)+'</p>' : '',
      '<div class="ops-run-list">'+rows+'</div>',
      '</section>'
    ].join('');
  }

  window.HermesOpsRuns={renderSection:renderSection};
})();

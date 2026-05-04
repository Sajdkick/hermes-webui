(function(){
  function escapeHtml(value){
    return String(value||'')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  function appUrl(path){
    const raw=String(path||'').trim();
    const base=(typeof document!=='undefined' && document.baseURI)
      || (typeof location!=='undefined' && location.href)
      || '';
    if(!raw) return base || '/';
    if(/^[a-z]+:/i.test(raw) || raw.startsWith('//')) return raw;
    const rel=raw.startsWith('/') ? raw.slice(1) : raw;
    if(!base) return raw.startsWith('/') ? raw : '/'+raw;
    try{return new URL(rel, base).href;}catch(_error){return raw.startsWith('/') ? raw : '/'+raw;}
  }

  function syncMeta(sync,error,loading){
    if(error){
      return { kind:'error', label:'Unavailable', summary:error };
    }
    if(loading){
      return { kind:'idle', label:'Checking', summary:'Loading maintenance sync state.' };
    }
    if(!sync){
      return { kind:'idle', label:'No sync yet', summary:'Start a maintenance session to create a clean upstream-sync worktree.' };
    }
    if(sync.applied){
      return { kind:'ready', label:'Applied', summary:sync.message||'The reviewed sync has already been applied.' };
    }
    if(sync.canApply){
      return { kind:'ready', label:'Ready', summary:sync.message||'Ready to fast-forward the source checkout.' };
    }
    if(String(sync.state||'').trim()==='blocked'){
      return { kind:'error', label:'Blocked', summary:sync.message||'Maintenance sync is blocked.' };
    }
    return { kind:'warning', label:'In review', summary:sync.message||'Maintenance session is still in progress.' };
  }

  function renderHistory(records){
    const items=Array.isArray(records) ? records : [];
    if(!items.length) return '';
    return [
      '<div class="ops-admin-history">',
      items.slice(0,4).map(function(item){
        return '<div class="ops-admin-history-row"><strong>'+escapeHtml(item.syncBranch||item.recordId||'sync')+'</strong><span>'+escapeHtml(item.state||'')+'</span></div>';
      }).join(''),
      '</div>'
    ].join('');
  }

  function renderSection(payload){
    const sync=payload && payload.upstreamSync ? payload.upstreamSync : null;
    const records=payload && payload.upstreamSyncRecords ? payload.upstreamSyncRecords : [];
    const error=String(payload && payload.upstreamSyncError || '').trim();
    const loading=!!(payload && payload.loadingUpstreamSync);
    const busyAction=String(payload && payload.upstreamSyncBusyAction || '').trim();
    const meta=syncMeta(sync,error,loading);
    const openSession=sync && sync.sessionUrl ? String(sync.sessionUrl) : '';
    return [
      '<section class="ops-admin-panel ops-upstream-sync-panel">',
      '<div class="ops-git-header">',
      '<div class="ops-git-copy">',
      '<div class="ops-epic-header"><h3>Maintenance sync</h3><span>Project-scoped upstream worktree and review session</span></div>',
      '<span class="ops-git-status '+escapeHtml(meta.kind)+'">'+escapeHtml(meta.label)+'</span>',
      '<p class="ops-git-summary">'+escapeHtml(meta.summary)+'</p>',
      sync?'<p class="ops-runtime-note">Source '+escapeHtml(sync.sourceBranch||'')+' · Upstream '+escapeHtml(sync.upstreamRef||'')+' · Worktree '+escapeHtml(sync.worktreePath||'')+'</p>':'',
      '</div>',
      '<div class="ops-runtime-actions">',
      '<button class="ops-shell-link" type="button" data-ops-action="refresh-upstream-sync"'+(loading?' disabled':'')+'>'+(loading?'Refreshing…':'Refresh sync')+'</button>',
      '<button class="ops-shell-link primary" type="button" data-ops-action="start-upstream-sync"'+(busyAction==='start'?' disabled':'')+'>'+(busyAction==='start'?'Starting…':'Start maintenance session')+'</button>',
      '<button class="ops-shell-link" type="button" data-ops-action="apply-upstream-sync"'+(busyAction==='apply' || !(sync && sync.canApply)?' disabled':'')+'>'+(busyAction==='apply'?'Applying…':'Apply reviewed sync')+'</button>',
      openSession?'<a class="ops-shell-link" href="'+escapeHtml(appUrl(openSession))+'">Open session</a>':'',
      '</div>',
      '</div>',
      sync && Array.isArray(sync.blockers) && sync.blockers.length ? '<p class="ops-shell-error">'+escapeHtml(sync.blockers.join(' | '))+'</p>' : '',
      renderHistory(records),
      '</section>'
    ].join('');
  }

  window.HermesOpsUpstreamSync={
    renderSection:renderSection,
  };
})();

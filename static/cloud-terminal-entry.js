(function(){
  async function loadShell(){
    const root=document.querySelector('[data-ops-shell]');
    if(!root)return;
    try{
      const response=await fetch('/api/ops/shell',{credentials:'same-origin'});
      if(!response.ok)throw new Error('Shell request failed with status '+response.status);
      const payload=await response.json();
      if(window.HermesOpsProjects && typeof window.HermesOpsProjects.mount==='function'){
        window.HermesOpsProjects.mount(root,payload);
        return;
      }
      root.innerHTML=[
        '<div class="ops-shell-status">',
        '<span class="ops-shell-status-badge">Project shell module unavailable</span>',
        '<div class="ops-shell-grid">',
        '<div class="ops-shell-card"><strong>Phase</strong><span>'+escapeHtml(payload.phase||'unknown')+'</span></div>',
        '<div class="ops-shell-card"><strong>Route</strong><span>'+escapeHtml(payload.route||'')+'</span></div>',
        '<div class="ops-shell-card"><strong>API base</strong><span>'+escapeHtml(payload.apiBase||'')+'</span></div>',
        '<div class="ops-shell-card"><strong>Version</strong><span>'+escapeHtml(payload.version||'')+'</span></div>',
        '</div>',
        '</div>'
      ].join('');
    }catch(error){
      root.innerHTML='<p class="ops-shell-error">'+escapeHtml(error && error.message ? error.message : 'Could not load shell metadata.')+'</p>';
    }
  }

  function escapeHtml(value){
    return String(value||'')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',loadShell,{once:true});
  }else{
    loadShell();
  }
})();

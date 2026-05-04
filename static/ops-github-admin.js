(function(){
  function escapeHtml(value){
    return String(value||'')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  function renderStatus(status,error){
    if(error){
      return '<p class="ops-shell-error">'+escapeHtml(error)+'</p>';
    }
    if(!status){
      return '<p class="ops-runtime-note">Loading GitHub status…</p>';
    }
    if(status.authenticated && status.user){
      return '<p class="ops-runtime-note">Authenticated as '+escapeHtml(status.user.login||status.user.name||'GitHub user')+' via '+escapeHtml(status.tokenSource||'configured token')+'.</p>';
    }
    return '<p class="ops-runtime-note">'+escapeHtml(status.message||'No GitHub token is configured.')+'</p>';
  }

  function repoKey(owner,name){
    return String(owner||'').trim()+'/'+String(name||'').trim();
  }

  function renderBranches(state,repo){
    const key=repoKey(repo && repo.owner, repo && repo.name);
    const branchesByRepo=state && state.githubBranchesByRepo && typeof state.githubBranchesByRepo==='object' ? state.githubBranchesByRepo : {};
    const branchState=branchesByRepo[key] || null;
    if(!branchState) return '';
    if(branchState.loading){
      return '<p class="ops-runtime-note">Loading branches…</p>';
    }
    if(branchState.error){
      return '<p class="ops-shell-error">'+escapeHtml(branchState.error)+'</p>';
    }
    const branches=Array.isArray(branchState.branches) ? branchState.branches : [];
    if(!branches.length){
      return '<p class="ops-runtime-note">No branches returned.</p>';
    }
    return [
      '<div class="ops-admin-chip-list">',
      branches.slice(0,12).map(function(branch){
        const branchName=String(branch && branch.name || '').trim();
        const importing=state && state.githubImportingRepoKey===key+':'+branchName;
        return [
          '<button class="ops-admin-chip" type="button" data-ops-action="github-import-repo" data-owner="'+escapeHtml(repo && repo.owner || '')+'" data-repo="'+escapeHtml(repo && repo.name || '')+'" data-branch="'+escapeHtml(branchName)+'" data-project-name="'+escapeHtml(repo && repo.name || '')+'"'+(importing?' disabled':'')+'>',
          '<strong>'+escapeHtml(branchName)+'</strong>',
          '<span>'+(importing?'Importing…':'Import branch')+'</span>',
          '</button>'
        ].join('');
      }).join(''),
      '</div>'
    ].join('');
  }

  function renderRepositories(state){
    const repos=Array.isArray(state && state.githubRepos) ? state.githubRepos : [];
    if(state && state.loadingGitHubRepos){
      return '<p class="ops-runtime-note">Loading repositories…</p>';
    }
    if(!repos.length){
      return '<p class="ops-runtime-note">Search GitHub repositories to import them as clean projects.</p>';
    }
    return repos.slice(0,12).map(function(repo){
      const key=repoKey(repo.owner, repo.name);
      const loadingBranches=state && state.githubLoadingBranchesKey===key;
      const importingDefault=state && state.githubImportingRepoKey===key+':'+String(repo.defaultBranch||'');
      return [
        '<article class="ops-admin-card">',
        '<div class="ops-admin-card-copy">',
        '<strong>'+escapeHtml(repo.fullName||key)+'</strong>',
        '<p class="ops-runtime-note">'+escapeHtml(repo.description||'No description provided.')+'</p>',
        '<p class="ops-runtime-note">Default branch: '+escapeHtml(repo.defaultBranch||'main')+'</p>',
        '</div>',
        '<div class="ops-runtime-actions">',
        '<button class="ops-shell-link" type="button" data-ops-action="github-load-branches" data-owner="'+escapeHtml(repo.owner||'')+'" data-repo="'+escapeHtml(repo.name||'')+'"'+(loadingBranches?' disabled':'')+'>'+(loadingBranches?'Loading…':'Load branches')+'</button>',
        '<button class="ops-shell-link primary" type="button" data-ops-action="github-import-repo" data-owner="'+escapeHtml(repo.owner||'')+'" data-repo="'+escapeHtml(repo.name||'')+'" data-branch="'+escapeHtml(repo.defaultBranch||'main')+'" data-project-name="'+escapeHtml(repo.name||'')+'"'+(importingDefault?' disabled':'')+'>'+(importingDefault?'Importing…':'Import default')+'</button>',
        '</div>',
        renderBranches(state,repo),
        '</article>'
      ].join('');
    }).join('');
  }

  function renderSection(state){
    const query=String(state && state.githubQuery || '').trim();
    const lastImport=state && state.githubLastImport ? state.githubLastImport : null;
    return [
      '<section class="ops-admin-panel ops-github-panel">',
      '<div class="ops-project-column-header"><h2>GitHub admin</h2><span>Discovery and import</span></div>',
      renderStatus(state && state.githubStatus, state && state.githubError),
      '<div class="ops-runtime-actions">',
      '<button class="ops-shell-link" type="button" data-ops-action="refresh-github-status"'+(state && state.loadingGitHubStatus?' disabled':'')+'>'+(state && state.loadingGitHubStatus?'Refreshing…':'Refresh status')+'</button>',
      '</div>',
      '<form class="ops-inline-form compact" data-ops-form="github-search">',
      '<label class="ops-wide-field"><span>Repository search</span><input name="query" type="text" value="'+escapeHtml(query)+'" placeholder="hermes-webui"></label>',
      '<label><span>Limit</span><input name="limit" type="number" min="1" max="100" value="10"></label>',
      '<button class="ops-shell-link primary" type="submit"'+(state && state.loadingGitHubRepos?' disabled':'')+'>'+(state && state.loadingGitHubRepos?'Searching…':'Search GitHub')+'</button>',
      '</form>',
      lastImport?'<p class="ops-runtime-note">Imported '+escapeHtml(lastImport.project && lastImport.project.name || lastImport.repo || 'repository')+' at '+escapeHtml(lastImport.targetPath||'')+'.</p>':'',
      '<div class="ops-admin-list">',
      renderRepositories(state),
      '</div>',
      '</section>'
    ].join('');
  }

  window.HermesOpsGitHubAdmin={
    renderSection:renderSection,
  };
})();

(function(){
  function escapeHtml(value){
    return String(value||'')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  function statusState(project,status,error){
    if(error){
      return {
        kind:'error',
        label:'Git unavailable',
        summary:error,
      };
    }
    if(!status){
      return {
        kind:'idle',
        label:'Checking',
        summary:'Loading project git status.',
      };
    }
    if(status.isGitRepo===false || status.status==='not-git'){
      return {
        kind:'missing',
        label:'No Git repo',
        summary:'This project path is not inside a Git repository.',
      };
    }
    if(status.conflicts || status.mergeInProgress || status.rebaseInProgress || status.cherryPickInProgress || status.revertInProgress){
      return {
        kind:'error',
        label:'Conflicts',
        summary:statusSummary(project,status),
      };
    }
    if(Number(status.behind||0)>0 && Number(status.ahead||0)>0){
      return {
        kind:'warning',
        label:'Diverged',
        summary:statusSummary(project,status),
      };
    }
    if(Number(status.behind||0)>0){
      return {
        kind:'warning',
        label:'Behind core',
        summary:statusSummary(project,status),
      };
    }
    if(Number(status.ahead||0)>0 || status.dirty){
      return {
        kind:'warning',
        label:'Needs push',
        summary:statusSummary(project,status),
      };
    }
    return {
      kind:'ready',
      label:'In sync',
      summary:statusSummary(project,status),
    };
  }

  function statusSummary(project,status){
    if(!status)return 'Git status has not loaded yet.';
    if(status.isGitRepo===false || status.status==='not-git'){
      return 'This project path is not inside a Git repository.';
    }
    const parts=[];
    const branch=String(status.branch||'').trim();
    const upstream=String(status.upstream||'').trim();
    const coreBranch=String((status&&status.coreBranch)||(project&&project.coreBranch)||'main').trim()||'main';
    if(branch)parts.push(`Branch ${branch}`);
    if(upstream)parts.push(`Sync target ${upstream}`);
    else if(coreBranch)parts.push(`Core branch ${coreBranch}`);
    if(status.detached && status.headShortSha)parts.push(`Detached ${status.headShortSha}`);
    if(Number(status.ahead||0)>0)parts.push(`ahead ${Number(status.ahead||0)}`);
    if(Number(status.behind||0)>0)parts.push(`behind ${Number(status.behind||0)}`);
    const counts=status.counts||{};
    if(Number(status.conflicts||counts.conflicts||0)>0)parts.push(`${Number(status.conflicts||counts.conflicts||0)} conflicts`);
    if(Number(counts.files||0)>0)parts.push(`${Number(counts.files||0)} changed`);
    if(Number(counts.untracked||0)>0)parts.push(`${Number(counts.untracked||0)} untracked`);
    const lastCommit=status.lastCommit||null;
    if(lastCommit && lastCommit.shortSha){
      parts.push(lastCommit.subject ? `${lastCommit.shortSha} ${lastCommit.subject}` : String(lastCommit.shortSha));
    }
    return parts.join(' | ') || 'Working tree clean.';
  }

  function renderSection(payload){
    const project=payload && payload.selectedProject ? payload.selectedProject : null;
    const loading=!!(payload && payload.loadingGitStatus);
    const status=payload ? payload.gitStatus : null;
    const error=payload ? payload.gitError : '';
    const derived=statusState(project,status,error);
    const repoRoot=status && status.repositoryRoot ? String(status.repositoryRoot) : '';
    const coreBranch=String((status&&status.coreBranch)||(project&&project.coreBranch)||'main').trim()||'main';
    const buttonLabel=loading ? 'Refreshing…' : 'Refresh git';
    return [
      '<section class="ops-git-panel">',
      '<div class="ops-git-header">',
      '<div class="ops-git-copy">',
      '<div class="ops-epic-header"><h3>Git status</h3><span>Track the current branch against '+escapeHtml(coreBranch)+'</span></div>',
      '<span class="ops-git-status '+escapeHtml(derived.kind)+'">'+escapeHtml(derived.label)+'</span>',
      '<p class="ops-git-summary">'+escapeHtml(derived.summary)+'</p>',
      repoRoot?'<p class="ops-runtime-note">Repository root: '+escapeHtml(repoRoot)+'</p>':'',
      '</div>',
      '<div class="ops-runtime-actions">',
      '<button class="ops-shell-link" type="button" data-ops-action="refresh-git-status"'+(loading?' disabled':'')+'>'+escapeHtml(buttonLabel)+'</button>',
      '</div>',
      '</div>',
      '</section>'
    ].join('');
  }

  window.HermesOpsGit={
    renderSection:renderSection,
    statusSummary:statusSummary,
    statusState:statusState,
  };
})();

(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};

  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const esc=ctx&&ctx.esc;
    const projectPath=ctx&&ctx.projectPath;
    const writeStoredJson=ctx&&ctx.writeStoredJson;
    const root=ctx&&ctx.root;
    const SRef=ctx&&ctx.SRef;
    const requestAnimationFrameRef=ctx&&ctx.requestAnimationFrameRef;
    const epicAccentPalette=Array.isArray(ctx&&ctx.epicAccentPalette)&&ctx.epicAccentPalette.length
      ? ctx.epicAccentPalette.slice()
      : [
          {accent:'#34d399',soft:'rgba(52,211,153,.12)',border:'rgba(52,211,153,.35)'},
          {accent:'#38bdf8',soft:'rgba(56,189,248,.12)',border:'rgba(56,189,248,.35)'},
          {accent:'#f59e0b',soft:'rgba(245,158,11,.12)',border:'rgba(245,158,11,.35)'},
          {accent:'#f87171',soft:'rgba(248,113,113,.12)',border:'rgba(248,113,113,.35)'},
          {accent:'#a3e635',soft:'rgba(163,230,53,.12)',border:'rgba(163,230,53,.35)'},
          {accent:'#22d3ee',soft:'rgba(34,211,238,.12)',border:'rgba(34,211,238,.35)'},
        ];
    const epicCollapseStorageKey=String(ctx&&ctx.epicCollapseStorageKey||'').trim();
    if(
      !OPS
      || typeof esc!=='function'
      || typeof projectPath!=='function'
      || typeof writeStoredJson!=='function'
      || typeof root!=='function'
      || typeof SRef!=='function'
      || typeof requestAnimationFrameRef!=='function'
      || !epicCollapseStorageKey
    ){
      return {};
    }

    function dashboardActiveProfileName(){
      return String((SRef()&&SRef().activeProfile)||'default').trim()||'default';
    }

    function projectRepositoryLabel(project){
      return String(project&&project.fullName||project&&project.name||project&&project.slug||project&&project.id||'Project').trim()||'Project';
    }

    function projectBranchLabel(project){
      return String(project&&project.coreBranch||project&&project.branch||'').trim();
    }

    function normalizePath(value){
      return String(value||'').replace(/\/+$/,'');
    }

    function projectFolderLabel(project){
      const path=normalizePath(projectPath(project));
      if(path){
        const parts=path.split('/').filter(Boolean);
        return parts[parts.length-1]||'';
      }
      return String(project&&project.slug||'').trim();
    }

    function projectUsesBranchTitle(project,projectList){
      if(!project||typeof project!=='object')return false;
      const branch=projectBranchLabel(project);
      if(!branch)return false;
      const worktreeRole=String(project&&project.worktree&&project.worktree.role||'').trim().toLowerCase();
      if(worktreeRole==='base'||worktreeRole==='linked')return true;
      const repoLabel=projectRepositoryLabel(project);
      if(!repoLabel)return false;
      const source=Array.isArray(projectList)?projectList:OPS.projects;
      let duplicateCount=0;
      source.forEach(entry=>{
        if(!entry||typeof entry!=='object')return;
        if(projectRepositoryLabel(entry)!==repoLabel)return;
        duplicateCount+=1;
      });
      return duplicateCount>1;
    }

    function projectCardTitle(project,projectList){
      const branch=projectBranchLabel(project);
      if(projectUsesBranchTitle(project,projectList)&&branch)return branch;
      return projectRepositoryLabel(project);
    }

    function projectContextLabel(project,projectList){
      if(!project||typeof project!=='object')return '';
      const parts=[];
      const repoLabel=projectRepositoryLabel(project);
      const branch=projectBranchLabel(project);
      if(projectUsesBranchTitle(project,projectList)){
        if(repoLabel)parts.push(repoLabel);
      }else if(branch){
        parts.push(`Branch ${branch}`);
      }
      const folder=projectFolderLabel(project);
      if(folder&&folder!==projectCardTitle(project,projectList)&&folder!==repoLabel){
        parts.push(`Folder ${folder}`);
      }
      return parts.join(' • ');
    }

    function accentIndexForSeed(seed){
      const text=String(seed||'').trim();
      if(!text)return 0;
      let hash=0;
      for(let index=0;index<text.length;index+=1){
        hash=((hash<<5)-hash)+text.charCodeAt(index);
        hash|=0;
      }
      return Math.abs(hash)%epicAccentPalette.length;
    }

    function accentForSeed(seed,fallbackIndex){
      const index=Number.isFinite(Number(fallbackIndex))?Number(fallbackIndex):0;
      return epicAccentPalette[accentIndexForSeed(seed||index)];
    }

    function accentStyle(prefix,accent){
      if(!prefix||!accent)return '';
      return [
        `--${prefix}-accent:${accent.accent}`,
        `--${prefix}-accent-soft:${accent.soft}`,
        `--${prefix}-accent-border:${accent.border}`,
      ].join(';');
    }

    function projectAccentStyle(project,index,prefix){
      const seed=project&&((project.id||'')||(project.fullName||'')||(project.path||''))||index||0;
      return accentStyle(prefix||'ops-card',accentForSeed(seed,index));
    }

    function sessionAccentStyle(session,index,prefix){
      const seed=String(session&&session.ops_project_id||session&&session.projectId||session&&session.repositoryLabel||session&&session.session_id||index||'').trim();
      return accentStyle(prefix||'ops-session-row',accentForSeed(seed,index));
    }

    function sessionGroupAccentStyle(group,index,prefix){
      if(group&&group.isUngrouped)return '';
      const seed=String(group&&group.groupId||group&&group.key||group&&group.label||index||'').trim();
      return accentStyle(prefix||'ops-session-group',accentForSeed(seed,index));
    }

    function availableProjectProfiles(){
      const seen=new Set();
      const profiles=[];
      const activeName=dashboardActiveProfileName();
      const source=Array.isArray(OPS.profiles)&&OPS.profiles.length
        ? OPS.profiles
        : [{name:activeName,isActive:true,isDefault:activeName==='default'}];
      source.forEach(profile=>{
        const name=String(profile&&profile.name||'').trim();
        if(!name||seen.has(name))return;
        seen.add(name);
        profiles.push(profile);
      });
      if(!seen.has(activeName)){
        profiles.unshift({name:activeName,isActive:true,isDefault:activeName==='default'});
      }
      return profiles;
    }

    function projectProfileLabel(project){
      const profile=String(project&&project.profile||'').trim();
      return profile||'No assigned profile';
    }

    function renderProjectProfileOptions(selected,options){
      const settings=options||{};
      const activeName=dashboardActiveProfileName();
      const current=String(selected||'').trim()||(settings.allowBlank?'':activeName);
      const rows=[];
      if(settings.allowBlank){
        rows.push(`<option value="" ${current?'':'selected'}>${esc(settings.blankLabel||'No assigned profile')}</option>`);
      }
      availableProjectProfiles().forEach(profile=>{
        const name=String(profile&&profile.name||'').trim();
        if(!name)return;
        const label=name===activeName?`${name} (active)`:name;
        rows.push(`<option value="${esc(name)}" ${name===current?'selected':''}>${esc(label)}</option>`);
      });
      return rows.join('');
    }

    function formatOpsDateTime(value,fallback){
      let stamp=0;
      if(typeof value==='number'&&Number.isFinite(value)){
        stamp=value>1e12?value:value*1000;
      }else if(typeof value==='string'&&value.trim()){
        const parsed=Date.parse(value);
        stamp=Number.isFinite(parsed)?parsed:0;
      }
      if(!stamp)return fallback||'Unknown';
      try{
        return new Intl.DateTimeFormat(undefined,{
          month:'short',
          day:'numeric',
          hour:'numeric',
          minute:'2-digit',
        }).format(new Date(stamp));
      }catch(e){
        return new Date(stamp).toLocaleString();
      }
    }

    function epicCollapseMap(projectId){
      const pid=String(projectId||'').trim();
      if(!pid)return {};
      const map=OPS.epicCollapsed&&OPS.epicCollapsed[pid];
      return map&&typeof map==='object'?map:{};
    }

    function isEpicCollapsed(projectId,epicId){
      const pid=String(projectId||'').trim();
      const eid=String(epicId||'').trim();
      if(!pid||!eid)return false;
      return !!epicCollapseMap(pid)[eid];
    }

    function setEpicCollapsed(projectId,epicId,collapsed){
      const pid=String(projectId||'').trim();
      const eid=String(epicId||'').trim();
      if(!pid||!eid)return;
      const projectMap={...epicCollapseMap(pid),[eid]:!!collapsed};
      if(!collapsed)delete projectMap[eid];
      OPS.epicCollapsed={...(OPS.epicCollapsed||{}),[pid]:projectMap};
      if(!Object.keys(projectMap).length)delete OPS.epicCollapsed[pid];
      writeStoredJson(epicCollapseStorageKey,OPS.epicCollapsed);
    }

    function syncEpicCollapseState(projectId,epics){
      const pid=String(projectId||'').trim();
      if(!pid)return;
      const activeIds=new Set((epics||[]).map(epic=>String(epic&&epic.id||'').trim()).filter(Boolean));
      const next={};
      Object.entries(epicCollapseMap(pid)).forEach(([key,value])=>{
        if(activeIds.has(key)&&value)next[key]=true;
      });
      OPS.epicCollapsed={...(OPS.epicCollapsed||{}),[pid]:next};
      if(!Object.keys(next).length)delete OPS.epicCollapsed[pid];
      writeStoredJson(epicCollapseStorageKey,OPS.epicCollapsed);
    }

    function rememberTaskFilterFocus(){
      const active=document.activeElement;
      if(!active||typeof active.closest!=='function'){
        OPS.taskFilterFocusedField='';
        OPS.taskFilterSelectionStart=null;
        OPS.taskFilterSelectionEnd=null;
        return;
      }
      const field=active.closest('[data-ops-filter]');
      if(!field||!root()||!root().contains(field)){
        OPS.taskFilterFocusedField='';
        OPS.taskFilterSelectionStart=null;
        OPS.taskFilterSelectionEnd=null;
        return;
      }
      OPS.taskFilterFocusedField=field.dataset.opsFilter||'';
      OPS.taskFilterSelectionStart=typeof field.selectionStart==='number'?field.selectionStart:null;
      OPS.taskFilterSelectionEnd=typeof field.selectionEnd==='number'?field.selectionEnd:null;
    }

    function restoreTaskFilterFocus(){
      if(!OPS.taskFilterFocusedField)return;
      const field=root()&&root().querySelector(`[data-ops-filter="${OPS.taskFilterFocusedField}"]`);
      if(!field||field.disabled)return;
      requestAnimationFrameRef(()=>{
        if(!root()||!root().contains(field)||field.disabled)return;
        field.focus({preventScroll:true});
        if(typeof field.setSelectionRange==='function'&&OPS.taskFilterFocusedField==='token'){
          const start=typeof OPS.taskFilterSelectionStart==='number'?OPS.taskFilterSelectionStart:field.value.length;
          const end=typeof OPS.taskFilterSelectionEnd==='number'?OPS.taskFilterSelectionEnd:start;
          field.setSelectionRange(start,end);
        }
      });
    }

    return {
      dashboardActiveProfileName,
      projectRepositoryLabel,
      projectBranchLabel,
      projectFolderLabel,
      projectUsesBranchTitle,
      projectCardTitle,
      projectContextLabel,
      projectAccentStyle,
      sessionAccentStyle,
      sessionGroupAccentStyle,
      availableProjectProfiles,
      projectProfileLabel,
      renderProjectProfileOptions,
      formatOpsDateTime,
      setEpicCollapsed,
      isEpicCollapsed,
      syncEpicCollapseState,
      rememberTaskFilterFocus,
      restoreTaskFilterFocus,
    };
  }

  window.HermesOpsModules.dashboardShared={bindDashboard};
})();

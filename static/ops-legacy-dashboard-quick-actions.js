(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};

  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const esc=ctx&&ctx.esc;
    const svg=ctx&&ctx.svg;
    const playStatusFor=ctx&&ctx.playStatusFor;
    const isPlayRunning=ctx&&ctx.isPlayRunning;
    const playStatusTitle=ctx&&ctx.playStatusTitle;
    const playStatusLabel=ctx&&ctx.playStatusLabel;
    if(
      !OPS
      || typeof esc!=='function'
      || !svg
      || typeof playStatusFor!=='function'
      || typeof isPlayRunning!=='function'
      || typeof playStatusTitle!=='function'
      || typeof playStatusLabel!=='function'
    ){
      return {};
    }

    function playStatusCanBuild(status){
      if(!status)return false;
      if(status.canBuild===true||status.buildAvailable===true||status.playBuildAvailable===true)return true;
      if(status.canBuild===false||status.buildAvailable===false||status.playBuildAvailable===false)return false;
      return !!(status&&(status.configAvailable===true||status.configExists===true||status.configured===true)&&(status.configValid===true||status.valid===true));
    }

    function renderProjectPlayQuickAction(project){
      if(!project||!project.id)return '';
      const status=playStatusFor(project.id);
      const busy=String(OPS.playBusyByProject[project.id]||'').trim();
      const state=String(status&&status.status||'idle').toLowerCase();
      const canBuild=playStatusCanBuild(status);
      let action='start-play';
      let label='Build';
      let title=playStatusTitle(status);
      let disabled=true;
      let primary=false;
      if(canBuild){
        if(status.ready&&status.inspectUrl){
          action='open-play';
          label='Play';
          disabled=!!busy;
          primary=true;
        }else if(isPlayRunning(status)){
          action='start-play';
          label=busy&&busy==='start'?'Building...':playStatusLabel(status);
          disabled=true;
        }else if(state==='failed'||state==='stopped'){
          action='restart-play';
          label=busy&&busy==='restart'?'Restarting...':'Restart';
          disabled=!!busy;
        }else{
          action='start-play';
          label=busy&&busy==='start'?'Building...':'Build';
          disabled=!!busy;
        }
      }
      return `<button class="ops-btn ${primary&&!disabled?'primary':''}" type="button" data-ops-action="${esc(action)}" data-project-id="${esc(project.id)}" ${disabled?'disabled':''} title="${esc(title)}">${svg.play}<span>${esc(label)}</span></button>`;
    }

    function renderProjectActivityQuickAction(project){
      if(!project||!project.id)return '';
      const busy=OPS.projectHealthBusyByProject[project.id]==='activity';
      const activate=project.active===false;
      const label=busy?'Working...':(activate?'Activate':'Deactivate');
      const title=activate
        ? 'Activate this project and install dependencies when needed.'
        : 'Deactivate this project to move it out of the primary active workflow.';
      return `<button class="ops-btn ${activate&&!busy?'primary':''}" type="button" data-ops-action="toggle-project-activity" data-project-id="${esc(project.id)}" data-project-active="${activate?'true':'false'}" ${busy?'disabled':''} title="${esc(title)}">${activate?svg.check:svg.close}<span>${esc(label)}</span></button>`;
    }

    return {
      renderProjectPlayQuickAction,
      renderProjectActivityQuickAction,
    };
  }

  window.HermesOpsModules.dashboardQuickActions={bindDashboard};
})();

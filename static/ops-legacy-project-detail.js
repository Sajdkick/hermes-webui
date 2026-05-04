(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};

  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const root=ctx&&ctx.root;
    const esc=ctx&&ctx.esc;
    const svg=ctx&&ctx.svg;
    const setDashboardTopbar=ctx&&ctx.setDashboardTopbar;
    const showError=ctx&&ctx.showError;
    const windowRef=(ctx&&ctx.windowRef)||(typeof window!=='undefined'?window:null);
    const URLRef=(ctx&&ctx.URLRef)||(typeof URL!=='undefined'?URL:null);
    const summarizeEpics=ctx&&ctx.summarizeEpics;
    const nameOf=ctx&&ctx.nameOf;
    const projectPath=ctx&&ctx.projectPath;
    const projectProfileLabel=ctx&&ctx.projectProfileLabel;
    const rememberTaskFilterFocus=ctx&&ctx.rememberTaskFilterFocus;
    const restoreTaskFilterFocus=ctx&&ctx.restoreTaskFilterFocus;
    const syncEpicCollapseState=ctx&&ctx.syncEpicCollapseState;
    const isEpicCollapsed=ctx&&ctx.isEpicCollapsed;
    const renderProjectPlayControls=ctx&&ctx.renderProjectPlayControls;
    const renderProjectSettings=ctx&&ctx.renderProjectSettings;
    const renderProjectHealth=ctx&&ctx.renderProjectHealth;
    const renderProjectGitStatus=ctx&&ctx.renderProjectGitStatus;
    const renderProjectPlayConfigEditor=ctx&&ctx.renderProjectPlayConfigEditor;
    const renderProjectRuntimeSnapshot=ctx&&ctx.renderProjectRuntimeSnapshot;
    const renderProjectRuntimeScreenshot=ctx&&ctx.renderProjectRuntimeScreenshot;
    const renderProjectPlayLogs=ctx&&ctx.renderProjectPlayLogs;
    const renderProjectGatherReports=ctx&&ctx.renderProjectGatherReports;
    const renderProjectReviewRequests=ctx&&ctx.renderProjectReviewRequests;
    const renderProjectDeployment=ctx&&ctx.renderProjectDeployment;
    const renderProjectDatabase=ctx&&ctx.renderProjectDatabase;
    const renderProjectRunActivity=ctx&&ctx.renderProjectRunActivity;
    const renderRunDetailPanel=ctx&&ctx.renderRunDetailPanel;
    const resolvedTaskSession=ctx&&ctx.resolvedTaskSession;
    const sessionRefValue=ctx&&ctx.sessionRefValue;
    const updateTaskGrade=ctx&&ctx.updateTaskGrade;
    if(
      !OPS
      || typeof root!=='function'
      || typeof esc!=='function'
      || !svg
      || typeof setDashboardTopbar!=='function'
      || typeof summarizeEpics!=='function'
      || typeof nameOf!=='function'
      || typeof projectPath!=='function'
      || typeof projectProfileLabel!=='function'
      || typeof rememberTaskFilterFocus!=='function'
      || typeof restoreTaskFilterFocus!=='function'
      || typeof syncEpicCollapseState!=='function'
      || typeof isEpicCollapsed!=='function'
      || typeof resolvedTaskSession!=='function'
      || typeof sessionRefValue!=='function'
      || typeof updateTaskGrade!=='function'
    ){
      return {};
    }

    const TASK_QA_STATUS_VALUES=Array.isArray(ctx&&ctx.taskQaStatusValues)&&ctx.taskQaStatusValues.length
      ? ctx.taskQaStatusValues.slice()
      : ['ready-for-test','needs-more-work','not-synced'];
    const TASK_FILTER_STATUS_VALUES=Array.isArray(ctx&&ctx.taskFilterStatusValues)&&ctx.taskFilterStatusValues.length
      ? ctx.taskFilterStatusValues.slice()
      : ['active','ready','in-progress','ready-for-test','needs-more-work','not-synced','blocked','done','archived'];
    const TASK_GRADE_VALUES=Array.isArray(ctx&&ctx.taskGradeValues)&&ctx.taskGradeValues.length
      ? ctx.taskGradeValues.slice()
      : ['green','orange','red'];
    const EPIC_ACCENT_PALETTE=Array.isArray(ctx&&ctx.epicAccentPalette)&&ctx.epicAccentPalette.length
      ? ctx.epicAccentPalette.slice()
      : [
          {accent:'#34d399',soft:'rgba(52,211,153,.12)',border:'rgba(52,211,153,.35)'},
          {accent:'#38bdf8',soft:'rgba(56,189,248,.12)',border:'rgba(56,189,248,.35)'},
          {accent:'#f59e0b',soft:'rgba(245,158,11,.12)',border:'rgba(245,158,11,.35)'},
          {accent:'#f87171',soft:'rgba(248,113,113,.12)',border:'rgba(248,113,113,.35)'},
          {accent:'#a3e635',soft:'rgba(163,230,53,.12)',border:'rgba(163,230,53,.35)'},
          {accent:'#22d3ee',soft:'rgba(34,211,238,.12)',border:'rgba(34,211,238,.35)'},
        ];

    function splitImageRefs(value){
      return Array.from(new Set(
        String(value||'')
          .split(/[\n,]+/)
          .map(item=>item.trim())
          .filter(Boolean)
      ));
    }

    function normalizeTaskFilterStatus(value){
      const normalized=String(value||'').trim().toLowerCase().replace(/[\s_]+/g,'-');
      return TASK_FILTER_STATUS_VALUES.includes(normalized)?normalized:'active';
    }

    function normalizeTaskGradeFilter(value){
      const normalized=String(value||'').trim().toLowerCase();
      return ['green','orange','red'].includes(normalized)?normalized:'';
    }

    function normalizeTaskTokenFilter(value){
      return String(value||'').trim().toLowerCase();
    }

    function currentTaskFilters(){
      const filters=OPS.taskFilters||{};
      const normalized={
        status:normalizeTaskFilterStatus(filters.status),
        grade:normalizeTaskGradeFilter(filters.grade),
        token:normalizeTaskTokenFilter(filters.token),
      };
      OPS.taskFilters=normalized;
      OPS.showArchived=normalized.status==='archived';
      return normalized;
    }

    function setTaskFilterStatus(status){
      const filters=currentTaskFilters();
      OPS.taskFilters={...filters,status:normalizeTaskFilterStatus(status)};
      OPS.showArchived=OPS.taskFilters.status==='archived';
    }

    function resetTaskFilters(){
      OPS.taskFilters={status:'active',grade:'',token:''};
      OPS.taskFiltersCollapsed=true;
      OPS.showArchived=false;
    }

    function taskFilterPanelActive(filters){
      const current=filters||currentTaskFilters();
      return !!(normalizeTaskGradeFilter(current.grade)||normalizeTaskTokenFilter(current.token));
    }

    function buildTaskLookup(epics){
      const lookup={};
      (epics||[]).forEach(epic=>(epic.tasks||[]).forEach(task=>{
        if(task&&task.id)lookup[task.id]=task;
      }));
      return lookup;
    }

    function taskDependencyBlocked(task,taskById){
      if(!task||task.done||task.archived)return false;
      const deps=Array.isArray(task.dependencies)?task.dependencies:[];
      return deps.some(dep=>{
        const dependency=taskById&&taskById[dep];
        return !!(dependency&&!dependency.done);
      });
    }

    function normalizeTaskQaStatus(value){
      if(typeof value!=='string')return '';
      const normalized=value.trim().toLowerCase().replace(/[\s_]+/g,'-');
      return TASK_QA_STATUS_VALUES.includes(normalized)?normalized:'';
    }

    function taskStatusKey(task,taskById){
      if(task&&task.archived)return 'archived';
      if(task&&task.done)return 'done';
      if(taskDependencyBlocked(task,taskById))return 'blocked';
      if(task&&task.inProgress)return 'in-progress';
      const qaStatus=normalizeTaskQaStatus(task&&task.qaStatus);
      if(qaStatus)return qaStatus;
      return 'ready';
    }

    function taskFilterLabel(status){
      switch(normalizeTaskFilterStatus(status)){
        case 'ready': return 'Ready';
        case 'in-progress': return 'In progress';
        case 'ready-for-test': return 'Ready for test';
        case 'needs-more-work': return 'Needs work';
        case 'not-synced': return 'Not synced';
        case 'blocked': return 'Blocked';
        case 'done': return 'Done';
        case 'archived': return 'Archived';
        default: return 'Active';
      }
    }

    function taskMarkerFlagText(task){
      const flags=Array.isArray(task&&task.flags)?task.flags:[];
      const markers=Array.isArray(task&&task.markers)?task.markers:[];
      return [...flags,...markers]
        .map(value=>String(value||'').toLowerCase())
        .join(' ');
    }

    function taskImageRefs(task){
      return splitImageRefs(task&&task.images);
    }

    function taskImageLabel(ref){
      const value=String(ref||'').trim();
      if(!value)return 'Image';
      if(URLRef&&windowRef&&windowRef.location){
        try{
          const parsed=new URLRef(value,windowRef.location.origin);
          const name=parsed.pathname.split('/').filter(Boolean).pop();
          return decodeURIComponent(name||parsed.hostname||'Image');
        }catch(e){}
      }
      const normalized=value.replace(/\\/g,'/');
      return normalized.split('/').filter(Boolean).pop()||value;
    }

    function taskImageHref(ref){
      const value=String(ref||'').trim();
      if(!value||/[\r\n]/.test(value))return '';
      if(/^https?:\/\//i.test(value))return value;
      if(value.startsWith('/api/')||value.startsWith('static/'))return value;
      if(value.startsWith('/'))return `/api/media?path=${encodeURIComponent(value)}`;
      return '';
    }

    function renderTaskImages(task){
      const images=taskImageRefs(task);
      if(!images.length)return '';
      return `
        <div class="ops-task-images" aria-label="Task images">
          ${images.slice(0,4).map(ref=>{
            const href=taskImageHref(ref);
            const label=taskImageLabel(ref);
            return href
              ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer" title="${esc(ref)}">${svg.folder}<span>${esc(label)}</span></a>`
              : `<span title="${esc(ref)}">${svg.folder}<span>${esc(label)}</span></span>`;
          }).join('')}
          ${images.length>4?`<span title="${esc(images.slice(4).join('\n'))}">+${images.length-4} more</span>`:''}
        </div>
      `;
    }

    function taskMatchesFilter(task,taskById,filters){
      const activeFilters=filters||{};
      const status=normalizeTaskFilterStatus(activeFilters.status);
      const grade=normalizeTaskGradeFilter(activeFilters.grade);
      const token=normalizeTaskTokenFilter(activeFilters.token);
      const statusKey=taskStatusKey(task,taskById);
      if(status==='active'){
        if(task&&task.archived)return false;
      }else if(statusKey!==status){
        return false;
      }
      if(grade&&String((task&&task.grade)||'green').toLowerCase()!==grade)return false;
      if(token&&!taskMarkerFlagText(task).includes(token))return false;
      return true;
    }

    function taskVisibleCount(summary,filters){
      const status=normalizeTaskFilterStatus(filters&&filters.status);
      if(status==='archived')return Number(summary&&summary.archived||0);
      if(status==='active')return Number(summary&&summary.active||0)+Number(summary&&summary.done||0);
      return Number(summary&&summary[status]||0);
    }

    function taskWorkspaceCountText(summary,filters){
      const status=normalizeTaskFilterStatus(filters&&filters.status);
      const visibleCount=taskVisibleCount(summary,filters);
      if(status==='archived')return `${visibleCount} archived`;
      if(!visibleCount)return '0 active';
      return `${Number(summary&&summary.done||0)}/${visibleCount} done`;
    }

    function actionableTaskCount(summary){
      return Number(summary&&summary.ready||0)+Number(summary&&summary['needs-more-work']||0);
    }

    function hashDashboardString(value){
      const text=String(value||'');
      let hash=0;
      for(let index=0;index<text.length;index+=1){
        hash=((hash<<5)-hash)+text.charCodeAt(index);
        hash|=0;
      }
      return Math.abs(hash);
    }

    function epicAccent(index,epic){
      const key=String(epic&&epic.id||epic&&epic.title||index||'').trim();
      const paletteIndex=hashDashboardString(key)%EPIC_ACCENT_PALETTE.length;
      return EPIC_ACCENT_PALETTE[paletteIndex]||EPIC_ACCENT_PALETTE[0];
    }

    function epicAccentStyle(index,epic){
      const accent=epicAccent(index,epic);
      return `--ops-epic-accent:${accent.accent};--ops-epic-accent-soft:${accent.soft};--ops-epic-accent-border:${accent.border};`;
    }

    function taskEmptyStateText(epics,summary,filters){
      if(!(epics||[]).length)return 'No epics yet. Add one above.';
      const status=normalizeTaskFilterStatus(filters&&filters.status);
      const filterActive=taskFilterPanelActive(filters);
      if(filterActive){
        return status==='archived'
          ? 'No archived tasks match the current filters.'
          : 'No active tasks match the current filters.';
      }
      if(status==='archived')return 'No archived tasks yet.';
      if(taskVisibleCount(summary,filters)===0&&Number(summary&&summary.archived||0)>0){
        return 'No active tasks. Switch to Archived to view completed work.';
      }
      return 'No active tasks yet.';
    }

    function summarizeTaskFilters(epics,taskById,filters){
      const summary={total:0,filtered:0,active:0,ready:0,'in-progress':0,'ready-for-test':0,'needs-more-work':0,'not-synced':0,blocked:0,done:0,archived:0};
      (epics||[]).forEach(epic=>(epic.tasks||[]).forEach(task=>{
        summary.total++;
        if(task&&!task.archived&&!task.done)summary.active++;
        const status=taskStatusKey(task,taskById);
        summary[status]=(summary[status]||0)+1;
        if(taskMatchesFilter(task,taskById,filters))summary.filtered++;
      }));
      return summary;
    }

    function renderTaskFilters(summary){
      const filters=currentTaskFilters();
      const archived=filters.status==='archived';
      const doneCount=Number(summary&&summary.done||0);
      const actionableCount=actionableTaskCount(summary);
      const projectId=String(OPS.currentProject&&OPS.currentProject.id||'').trim();
      const executeReadyBusy=projectId&&OPS.taskAutomationBusyByProject[projectId]==='execute-ready';
      const createExpanded=!OPS.taskCreateCollapsed;
      const filtersExpanded=!OPS.taskFiltersCollapsed;
      const filterActive=taskFilterPanelActive(filters);
      return `
        <div class="ops-task-workspace ops-task-filters">
          <div class="ops-task-filter-primary">
            <div class="ops-task-filter-segments" role="tablist" aria-label="Task list view">
              <button class="ops-segment ${archived?'':'active'}" type="button" role="tab" aria-selected="${archived?'false':'true'}" data-ops-action="show-active">
                Active ${taskVisibleCount(summary,{status:'active'})}
              </button>
              <button class="ops-segment ${archived?'active':''}" type="button" role="tab" aria-selected="${archived?'true':'false'}" data-ops-action="show-archived">
                Archived ${taskVisibleCount(summary,{status:'archived'})}
              </button>
            </div>
            <div class="ops-task-filter-actions">
              <span class="ops-task-filter-count">${esc(taskWorkspaceCountText(summary,filters))}</span>
              <button class="ops-btn primary" type="button" data-ops-action="execute-ready-tasks" ${archived||!projectId||(!actionableCount&&!executeReadyBusy)?'disabled':''} title="${archived?'Switch to Active to execute ready tasks.':'Ask Codex to execute ready and needs-more-work tasks in sequence.'}">
                ${svg.play}<span>${executeReadyBusy?'Starting...':'Execute ready tasks with AI'}${!executeReadyBusy&&actionableCount?` (${actionableCount})`:''}</span>
              </button>
              ${archived?'':`<button class="ops-btn" type="button" data-ops-action="archive-completed" ${doneCount?'':'disabled'}>${svg.folder}<span>Archive completed${doneCount?` (${doneCount})`:''}</span></button>`}
              <button class="ops-btn" type="button" data-ops-action="toggle-task-create" aria-expanded="${createExpanded?'true':'false'}">${svg.plus}<span>${createExpanded?'Hide create fields':'New epic/task'}</span></button>
              <button class="ops-btn" type="button" data-ops-action="toggle-task-filters" aria-expanded="${filtersExpanded?'true':'false'}">${svg.grid}<span>${filtersExpanded?'Hide filters':'Show filters'}</span></button>
            </div>
          </div>
          ${filtersExpanded?`
            <div class="ops-task-filter-fields">
              <label>
                <span>Grade</span>
                <select data-ops-filter="grade">
                  <option value="">Any grade</option>
                  ${['green','orange','red'].map(grade=>`<option value="${grade}" ${filters.grade===grade?'selected':''}>${grade}</option>`).join('')}
                </select>
              </label>
              <label>
                <span>Marker or flag</span>
                <input data-ops-filter="token" autocomplete="off" value="${esc(filters.token)}" placeholder="ui, backend, ai suggestion">
              </label>
              <div class="ops-form-actions">
                <button class="ops-btn" type="button" data-ops-action="reset-task-filters" ${filterActive?'':'disabled'}>${svg.close}<span>Reset</span></button>
              </div>
            </div>
          `:''}
        </div>
      `;
    }

    function normalizeTaskGrade(value){
      const normalized=String(value||'').trim().toLowerCase();
      return TASK_GRADE_VALUES.includes(normalized)?normalized:'green';
    }

    function getTaskQaStatus(task){
      return normalizeTaskQaStatus(task&&task.qaStatus);
    }

    function getTaskMoreWork(task){
      if(typeof (task&&task.moreWork)!=='string')return '';
      return task.moreWork.trim();
    }

    function parseTaskTimestamp(value){
      if(typeof value!=='string')return null;
      const parsed=Date.parse(value.trim());
      if(!Number.isFinite(parsed))return null;
      return new Date(parsed);
    }

    function formatTaskTimestamp(value){
      const parsed=parseTaskTimestamp(value);
      if(!parsed)return 'Not set';
      return parsed.toLocaleString();
    }

    function taskSessionActive(session){
      return !!(session&&!session.archived&&session.closed!==true);
    }

    function taskHasSessionHistory(task,session){
      if(String(session&&session.session_id||'').trim())return true;
      return !!String(task&&(
        task.lastSessionAt||
        task.startedAt||
        task.completedAt
      )||'').trim();
    }

    function taskPrimaryActionState(task,session,isBlocked){
      if(task&&task.done){
        return {label:'Done',action:'done',disabled:true};
      }
      if(isBlocked){
        return {
          label:'Blocked',
          action:'blocked',
          disabled:true,
          title:'Complete dependencies to unlock this task.',
        };
      }
      const activeSessionId=sessionRefValue(session);
      const hasSessionHistory=taskHasSessionHistory(task,session);
      if(activeSessionId&&taskSessionActive(session)){
        return {label:'Go to session',action:'open-session',disabled:false,sessionKey:activeSessionId};
      }
      if(getTaskQaStatus(task)==='needs-more-work'&&!(task&&task.inProgress)){
        return {label:'Execute',action:'execute',disabled:false};
      }
      if(hasSessionHistory){
        return {label:'New session',action:'new-session',disabled:false};
      }
      if(task&&task.inProgress){
        return {label:'In progress',action:'in-progress',disabled:true};
      }
      if(getTaskQaStatus(task)==='not-synced'){
        return {label:'Not synced',action:'not-synced',disabled:true};
      }
      if(getTaskQaStatus(task)==='ready-for-test'){
        return {label:'Ready for test',action:'ready-for-test',disabled:true};
      }
      return {label:'Execute',action:'execute',disabled:false};
    }

    function taskMetaText(task,session,isBlocked){
      let metaText='Ready to run';
      const hasSessionHistory=taskHasSessionHistory(task,session);
      if(task&&task.done){
        metaText='Completed';
      }else if(task&&task.inProgress){
        metaText=hasSessionHistory
          ? (taskSessionActive(session)?'In progress (session active)':'In progress (session ended)')
          : 'In progress';
      }else if(getTaskQaStatus(task)==='not-synced'){
        metaText=hasSessionHistory
          ? (taskSessionActive(session)?'Not synced (session active)':'Not synced (session ended)')
          : 'Not synced';
      }else if(getTaskQaStatus(task)==='ready-for-test'){
        metaText='Ready for test';
      }else if(getTaskQaStatus(task)==='needs-more-work'){
        metaText='Needs more work';
      }else if(hasSessionHistory){
        metaText=taskSessionActive(session)?'Session active':'Session ended';
      }else if(isBlocked){
        metaText='Blocked by dependencies';
      }
      if(task&&task.archived){
        metaText=task.done?'Completed (archived)':`${metaText} (archived)`;
      }
      return metaText;
    }

    function taskMarkerList(task){
      return Array.isArray(task&&task.markers)?task.markers.map(value=>String(value||'').trim()).filter(Boolean):[];
    }

    function taskFlagList(task){
      return Array.isArray(task&&task.flags)?task.flags.map(value=>String(value||'').trim()).filter(Boolean):[];
    }

    function formatTaskDependencyLabel(taskId,taskById){
      const dependency=taskById&&taskById[taskId];
      const text=String(dependency&&dependency.text||taskId||'').replace(/\s+/g,' ').trim();
      return text||'Unknown task';
    }

    function renderProjectDetail(){
      const project=OPS.currentProject;
      const epics=(OPS.taskData&&OPS.taskData.epics)||[];
      const counts=summarizeEpics(epics);
      const taskLookup=buildTaskLookup(epics);
      const filters=currentTaskFilters();
      const filterSummary=summarizeTaskFilters(epics,taskLookup,filters);
      rememberTaskFilterFocus();
      setDashboardTopbar(nameOf(project),`${counts.active} active | ${counts.done} done | ${OPS.taskData.branch||project.coreBranch||'main'}`);
      const edit=OPS.editingTask;
      const showCreateBand=!OPS.taskCreateCollapsed||!!edit;
      const selectedEpicId=edit?edit.epic.id:(epics[0]&&epics[0].id)||'';
      const epicOptions=epics.map(epic=>`<option value="${esc(epic.id)}" ${epic.id===selectedEpicId?'selected':''}>${esc(epic.title)}</option>`).join('');
      const taskForm=epics.length?`
        <form class="ops-task-form" data-ops-submit="save-task">
          <input type="hidden" name="taskId" value="${edit?esc(edit.task.id):''}">
          <label class="wide"><span>Task</span><input name="text" autocomplete="off" required value="${edit?esc(edit.task.text):''}"></label>
          <label><span>Epic</span><select name="epicId">${epicOptions}</select></label>
          <label><span>Grade</span><select name="grade">
            ${['green','orange','red'].map(grade=>`<option value="${grade}" ${(edit&&edit.task.grade===grade)?'selected':''}>${grade}</option>`).join('')}
          </select></label>
          <label><span>Flags</span><input name="flags" autocomplete="off" value="${edit?esc((edit.task.flags||[]).join(', ')):''}"></label>
          <label><span>Markers</span><input name="markers" autocomplete="off" value="${edit?esc((edit.task.markers||[]).join(', ')):''}"></label>
          <label><span>Images</span><input name="images" autocomplete="off" value="${edit?esc(taskImageRefs(edit.task).join(', ')):''}" placeholder="path or URL"></label>
          <div class="ops-form-actions">
            <button class="ops-btn primary" type="submit">${edit?svg.check:svg.plus}<span>${edit?'Save task':'Add task'}</span></button>
            ${edit?'<button class="ops-btn" type="button" data-ops-action="cancel-edit">Cancel</button>':''}
          </div>
        </form>
      `:'';
      const visibleEpics=epics
        .map(epic=>({
          epic,
          tasks:(epic.tasks||[]).filter(task=>taskMatchesFilter(task,taskLookup,filters)),
        }))
        .filter(entry=>entry.tasks.length);
      syncEpicCollapseState(project.id,visibleEpics.map(entry=>entry.epic));
      const emptyState=taskEmptyStateText(epics,filterSummary,filters);
      const epicList=visibleEpics.length
        ? visibleEpics.map((entry,index)=>renderEpic(project,entry.epic,entry.tasks,taskLookup,index)).join('')
        : `<div class="ops-empty">${esc(emptyState)}</div>`;
      const secondaryPanels=[
        renderProjectSettings(project),
        renderProjectHealth(project),
        renderProjectGitStatus(project,{detail:true}),
        renderProjectPlayConfigEditor(project),
        renderProjectRuntimeSnapshot(project.id),
        renderProjectRuntimeScreenshot(project.id),
        renderProjectPlayLogs(project.id),
        renderProjectGatherReports(project),
        renderProjectReviewRequests(project),
        renderProjectDeployment(project),
        renderProjectDatabase(project),
        renderProjectRunActivity(project),
        renderRunDetailPanel({hideProject:true}),
      ].filter(Boolean).join('');

      root().innerHTML=`
        <div class="ops-dashboard ops-project-detail">
          <div class="ops-toolbar">
            <button class="ops-icon-btn" type="button" data-ops-action="back-projects" title="Back">${svg.arrow}</button>
            <div class="ops-title-block">
              <h2>${esc(nameOf(project))}</h2>
              <span>${esc(projectPath(project))}</span>
            </div>
            <div class="ops-toolbar-actions">
              ${renderProjectPlayControls(project,{detail:true})}
              <button class="ops-btn" type="button" data-ops-action="refresh-detail">${svg.refresh}<span>Refresh</span></button>
              <button class="ops-btn danger" type="button" data-ops-action="delete-project" data-project-id="${esc(project.id)}">${svg.trash}<span>Delete</span></button>
            </div>
          </div>
          <div class="ops-summary-strip">
            <span>Branch ${esc(OPS.taskData.branch||project.coreBranch||'main')}</span>
            <span>Profile ${esc(projectProfileLabel(project))}</span>
            <span>${project.active===false?'Inactive':'Active'}</span>
            <span>${counts.epics} epics</span>
            <span>${counts.active} active</span>
            <span>${counts.done} done</span>
          </div>
          ${renderTaskFilters(filterSummary)}
          ${showCreateBand?`
            <div class="ops-create-band">
              <form class="ops-epic-form" data-ops-submit="create-epic">
                <input name="title" autocomplete="off" placeholder="Epic title" required>
                <button class="ops-btn primary" type="submit">${svg.plus}<span>Epic</span></button>
              </form>
              ${taskForm}
            </div>
          `:''}
          <div class="ops-epic-list">${epicList}</div>
          <details class="ops-project-secondary-panels">
            <summary>Project tools</summary>
            <div class="ops-project-secondary-panels-body">
              ${secondaryPanels||'<div class="ops-empty">No secondary tools for this project.</div>'}
            </div>
          </details>
        </div>
      `;
      restoreTaskFilterFocus();
    }

    function renderEpic(project,epic,tasks,taskById,index){
      const allEpicTasks=epic.tasks||[];
      const projectId=String(project&&project.id||OPS.currentProject&&OPS.currentProject.id||'').trim();
      const epicId=String(epic&&epic.id||'').trim();
      const doneCount=allEpicTasks.filter(task=>task&&task.done).length;
      const markers=taskMarkerList(epic);
      const collapsed=isEpicCollapsed(projectId,epicId);
      const visibleCount=tasks.length;
      const totalCount=allEpicTasks.length;
      const rows=tasks.map(task=>renderTask(epic,task,taskById)).join('');
      return `
        <section class="ops-epic ${collapsed?'collapsed':''}" data-epic-id="${esc(epicId)}" style="${epicAccentStyle(index,epic)}">
          <div class="ops-epic-header">
            <div class="ops-epic-header-main">
              <button class="ops-epic-toggle" type="button" data-ops-action="toggle-epic" data-epic-id="${esc(epicId)}" aria-expanded="${collapsed?'false':'true'}" title="${collapsed?'Expand epic':'Collapse epic'}">
                <span class="ops-epic-caret" aria-hidden="true">${svg.chevron}</span>
              </button>
              <div class="ops-epic-title-block">
                <div class="ops-epic-title-line">
                  <h3>${esc(epic.title)}</h3>
                  ${markers.map(marker=>`<span class="ops-epic-marker ${String(marker).trim().toLowerCase()==='ai suggestion'?'ai-suggestion':''}">${esc(marker)}</span>`).join('')}
                </div>
              </div>
            </div>
            <div class="ops-epic-header-actions">
              <span class="ops-epic-meta">${totalCount?`${doneCount}/${totalCount} done${visibleCount!==totalCount?` • ${visibleCount} shown`:''}`:'No tasks yet'}</span>
              <button class="ops-btn danger" type="button" data-ops-action="delete-epic" data-epic-id="${esc(epic.id)}">Delete</button>
            </div>
          </div>
          <div class="ops-task-list">${rows}</div>
        </section>
      `;
    }

    function renderTask(epic,task,taskById){
      const markers=taskMarkerList(task);
      const flags=taskFlagList(task);
      const dependencies=(Array.isArray(task&&task.dependencies)?task.dependencies:[])
        .map(depId=>formatTaskDependencyLabel(depId,taskById))
        .filter(Boolean);
      const session=resolvedTaskSession(task,OPS.currentProject&&OPS.currentProject.id);
      const isBlocked=taskDependencyBlocked(task,taskById);
      const statusKey=taskStatusKey(task,taskById);
      const qaStatus=getTaskQaStatus(task);
      const grade=normalizeTaskGrade(task&&task.grade);
      const actionState=taskPrimaryActionState(task,session,isBlocked);
      const metaText=taskMetaText(task,session,isBlocked);
      const imageRefs=taskImageRefs(task);
      const imageTitle=imageRefs.map(ref=>taskImageLabel(ref)).join('\n');
      const moreWork=getTaskMoreWork(task);
      const editing=!!(OPS.editingTask&&OPS.editingTask.task&&OPS.editingTask.task.id===task.id);
      const stampEntries=[
        ['Created',formatTaskTimestamp(task&&task.createdAt)],
        ['Started',formatTaskTimestamp(task&&task.startedAt)],
        ['Completed',formatTaskTimestamp(task&&task.completedAt)],
      ];
      if(task&&task.archived)stampEntries.push(['Archived',formatTaskTimestamp(task&&task.archivedAt)]);
      const taskClasses=['ops-task',statusKey];
      if(task&&task.done)taskClasses.push('done');
      if(task&&task.archived)taskClasses.push('archived');
      return `
        <div class="${taskClasses.join(' ')}">
          <div class="ops-task-body">
            <div class="ops-task-title-row">
              <span class="ops-task-grade-badge grade-${esc(grade)}">${esc(grade)}</span>
              <span class="ops-task-status-badge ${esc(statusKey)}">${esc(taskFilterLabel(statusKey))}</span>
              <div class="ops-task-text">${esc(task.text)}</div>
              ${markers.map(marker=>`<span class="ops-task-chip">${esc(marker)}</span>`).join('')}
            </div>
            <div class="ops-task-meta"><span>${esc(metaText)}</span></div>
            <div class="ops-task-stamps">
              ${stampEntries.map(([label,value])=>`
                <span class="ops-task-stamp">
                  <span class="ops-task-stamp-label">${esc(label)}:</span>
                  <span class="ops-task-stamp-value">${esc(value)}</span>
                </span>
              `).join('')}
            </div>
            ${dependencies.length?`<div class="ops-task-detail">Depends on: ${esc(dependencies.join(', '))}</div>`:''}
            ${flags.length?`<div class="ops-task-detail">Flags: ${esc(flags.join(', '))}</div>`:''}
            ${imageRefs.length?`<div class="ops-task-detail" title="${esc(imageTitle)}">Images: ${esc(String(imageRefs.length))}</div>`:''}
            ${qaStatus==='needs-more-work'||moreWork?`<div class="ops-task-detail ops-task-more-work">Needs more work: ${esc(moreWork||'No details provided.')}</div>`:''}
          </div>
          ${task.archived?'':`
            <div class="ops-task-actions">
              <select class="ops-task-select ops-task-grade-select grade-${esc(grade)}" data-ops-task-grade="${esc(task.id)}" aria-label="Task grade">
                ${TASK_GRADE_VALUES.map(value=>`<option value="${value}" ${value===grade?'selected':''}>${value.charAt(0).toUpperCase()+value.slice(1)}</option>`).join('')}
              </select>
              <button class="ops-btn primary" type="button" data-ops-action="task-primary" data-task-id="${esc(task.id)}" data-task-mode="${esc(actionState.action)}" ${actionState.sessionKey?`data-session-key="${esc(actionState.sessionKey)}"`:''} ${actionState.disabled?'disabled':''} ${actionState.title?`title="${esc(actionState.title)}"`:''}>${esc(actionState.label)}</button>
              ${qaStatus==='ready-for-test'&&!task.done?`<button class="ops-btn danger" type="button" data-ops-action="task-needs-more-work" data-task-id="${esc(task.id)}">Needs more work</button>`:''}
              ${qaStatus==='ready-for-test'&&!task.done?`<button class="ops-btn" type="button" data-ops-action="complete-task" data-task-id="${esc(task.id)}" ${isBlocked?'disabled title="Complete dependencies to unlock this task."':''}>Complete</button>`:''}
              <button class="ops-btn" type="button" data-ops-action="edit-task" data-task-id="${esc(task.id)}" ${editing?'disabled':''}>${editing?'Editing':'Edit'}</button>
              <button class="ops-btn danger" type="button" data-ops-action="delete-task" data-task-id="${esc(task.id)}">Delete</button>
            </div>
          `}
        </div>
      `;
    }

    function handleTaskFilterField(event){
      const field=event.target.closest('[data-ops-filter]');
      if(!field||!root()||!root().contains(field)||OPS.view!=='project-detail')return;
      const filters=currentTaskFilters();
      const filterName=field.dataset.opsFilter;
      let nextFilters=filters;
      if(filterName==='grade'){
        nextFilters={...filters,grade:normalizeTaskGradeFilter(field.value)};
      }else if(filterName==='token'){
        nextFilters={...filters,token:normalizeTaskTokenFilter(field.value)};
      }else{
        return;
      }
      if(
        nextFilters.status===filters.status&&
        nextFilters.grade===filters.grade&&
        nextFilters.token===filters.token
      )return;
      OPS.taskFilters=nextFilters;
      OPS.taskFiltersCollapsed=!taskFilterPanelActive(nextFilters);
      renderProjectDetail();
    }

    function handleTaskRowField(event){
      const field=event.target.closest('[data-ops-task-grade]');
      if(!field||!root()||!root().contains(field)||OPS.view!=='project-detail')return;
      const taskId=String(field.dataset.opsTaskGrade||'').trim();
      if(!taskId)return;
      const grade=normalizeTaskGrade(field.value);
      field.classList.remove('grade-green','grade-orange','grade-red');
      field.classList.add(`grade-${grade}`);
      updateTaskGrade(taskId,grade).catch(showError);
    }

    return {
      splitImageRefs,
      normalizeTaskFilterStatus,
      normalizeTaskGradeFilter,
      normalizeTaskTokenFilter,
      currentTaskFilters,
      setTaskFilterStatus,
      resetTaskFilters,
      taskFilterPanelActive,
      buildTaskLookup,
      taskDependencyBlocked,
      taskStatusKey,
      taskFilterLabel,
      taskMarkerFlagText,
      taskImageRefs,
      taskImageLabel,
      taskImageHref,
      renderTaskImages,
      taskMatchesFilter,
      taskVisibleCount,
      taskWorkspaceCountText,
      actionableTaskCount,
      hashDashboardString,
      epicAccent,
      epicAccentStyle,
      taskEmptyStateText,
      summarizeTaskFilters,
      renderTaskFilters,
      renderProjectDetail,
      renderEpic,
      renderTask,
      normalizeTaskQaStatus,
      normalizeTaskGrade,
      getTaskQaStatus,
      getTaskMoreWork,
      parseTaskTimestamp,
      formatTaskTimestamp,
      taskSessionActive,
      taskHasSessionHistory,
      taskPrimaryActionState,
      taskMetaText,
      taskMarkerList,
      taskFlagList,
      formatTaskDependencyLabel,
      handleTaskFilterField,
      handleTaskRowField,
    };
  }

  window.HermesOpsModules.projectDetail={bindDashboard};
})();

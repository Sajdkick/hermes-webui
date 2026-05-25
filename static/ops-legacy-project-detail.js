(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};

  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const root=ctx&&ctx.root;
    const esc=ctx&&ctx.esc;
    const svg=ctx&&ctx.svg;
    const setDashboardTopbar=ctx&&ctx.setDashboardTopbar;
    const showError=ctx&&ctx.showError;
    const documentRef=(ctx&&ctx.documentRef)||(typeof document!=='undefined'?document:null);
    const windowRef=(ctx&&ctx.windowRef)||(typeof window!=='undefined'?window:null);
    const URLRef=(ctx&&ctx.URLRef)||(typeof URL!=='undefined'?URL:null);
    const VoiceInputRef=ctx&&ctx.voiceInput;
    const AgentBridgeRef=ctx&&ctx.AgentBridge;
    const navigatorRef=ctx&&ctx.navigatorRef;
    const MediaRecorderRef=ctx&&ctx.MediaRecorderRef;
    const FileRef=ctx&&ctx.FileRef;
    const BlobRef=ctx&&ctx.BlobRef;
    const taskDictationPrompt=ctx&&ctx.taskDictationPrompt;
    const taskDictationAudioBitsPerSecond=ctx&&ctx.taskDictationAudioBitsPerSecond;
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

    function captureLogScrollState(container){
      const snapshot={};
      if(!container||typeof container.querySelectorAll!=='function')return snapshot;
      container.querySelectorAll('[data-ops-log-scroll-key]').forEach(node=>{
        const key=String(node&&node.dataset&&node.dataset.opsLogScrollKey||'').trim();
        if(!key)return;
        const maxScroll=Math.max(0,(node.scrollHeight||0)-(node.clientHeight||0));
        snapshot[key]={top:Number(node.scrollTop)||0,atBottom:maxScroll-(Number(node.scrollTop)||0)<=8};
      });
      return snapshot;
    }

    function restoreLogScrollState(container,snapshot){
      if(!container||!snapshot||typeof container.querySelectorAll!=='function')return;
      const apply=()=>{
        container.querySelectorAll('[data-ops-log-scroll-key]').forEach(node=>{
          const key=String(node&&node.dataset&&node.dataset.opsLogScrollKey||'').trim();
          const entry=key?snapshot[key]:null;
          if(!entry)return;
          const maxScroll=Math.max(0,(node.scrollHeight||0)-(node.clientHeight||0));
          node.scrollTop=entry.atBottom?maxScroll:Math.min(Number(entry.top)||0,maxScroll);
        });
      };
      apply();
      if(windowRef&&typeof windowRef.requestAnimationFrame==='function')windowRef.requestAnimationFrame(apply);
    }

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

    let taskFormDictationController=null;

    function taskFormVoiceSupported(){
      return !!(VoiceInputRef&&typeof VoiceInputRef.isSupported==='function'&&VoiceInputRef.isSupported({
        windowRef,
        navigatorRef,
        MediaRecorderRef,
      }));
    }

    function refreshTaskFormDictationSupport(){
      const supported=taskFormVoiceSupported();
      OPS.taskFormDictationSupported=supported;
      return supported;
    }

    function setTaskFormMicStatus(message,type){
      OPS.taskFormDictationStatus=String(message||'').trim();
      OPS.taskFormDictationStatusKind=type==='error'||type==='success'?type:'info';
    }

    function taskFormCanDictate(){
      return !!refreshTaskFormDictationSupport();
    }

    function taskFormMicButtonState(){
      refreshTaskFormDictationSupport();
      let label='Record';
      let title='Record task text by voice';
      if(OPS.taskFormDictationBusy){
        label='Transcribing';
        title='Transcribing audio...';
      }else if(OPS.taskFormDictationActive){
        label='Stop';
        title='Stop recording';
      }else if(!taskFormCanDictate()){
        title='Voice dictation is not supported in this browser.';
      }
      return {
        label,
        title,
        disabled:OPS.taskFormDictationBusy||(!OPS.taskFormDictationActive&&!taskFormCanDictate()),
        listening:OPS.taskFormDictationActive,
      };
    }

    function ensureTaskFormDraftText(value){
      const draft=OPS.taskFormDraft&&typeof OPS.taskFormDraft==='object'?OPS.taskFormDraft:{};
      OPS.taskFormDraft={
        taskId:String(draft.taskId||''),
        text:String(value||''),
        epicId:String(draft.epicId||''),
        grade:normalizeTaskGrade(draft.grade||'green'),
        flags:String(draft.flags||''),
        markers:String(draft.markers||''),
        images:String(draft.images||''),
      };
    }

    function syncTaskFormDictationText(value){
      ensureTaskFormDraftText(value);
      const field=root()&&root().querySelector('form[data-ops-submit="save-task"] input[name="text"]');
      if(field&&field.value!==OPS.taskFormDraft.text)field.value=OPS.taskFormDraft.text;
    }

    function renderTaskFormDictationState(){
      if(OPS.view==='project'){
        renderProjectDetail();
        restoreTaskFormFocus();
      }
    }

    function ensureTaskFormDictationController(){
      if(taskFormDictationController)return taskFormDictationController;
      if(!VoiceInputRef||typeof VoiceInputRef.createController!=='function')return null;
      taskFormDictationController=VoiceInputRef.createController({
        windowRef,
        navigatorRef,
        MediaRecorderRef,
        getText:()=>OPS.taskFormDraft&&typeof OPS.taskFormDraft==='object'?OPS.taskFormDraft.text:'',
        setText:value=>syncTaskFormDictationText(value),
        canStart:()=>taskFormCanDictate(),
        onActiveChange:on=>{
          OPS.taskFormDictationActive=!!on;
          renderTaskFormDictationState();
        },
        onBusyChange:on=>{
          OPS.taskFormDictationBusy=!!on;
          renderTaskFormDictationState();
        },
        onStatus:(message,type)=>{
          setTaskFormMicStatus(message,type);
          renderTaskFormDictationState();
        },
        onCommit:(transcript)=>{
          if(String(transcript||'').trim())setTaskFormMicStatus('Transcription added.','success');
          renderTaskFormDictationState();
        },
        onNoSpeech:()=>{
          setTaskFormMicStatus('No speech detected.','error');
          renderTaskFormDictationState();
        },
        messages:{
          requesting:'Requesting microphone access...',
          listening:'Listening...',
          transcribing:'Transcribing...',
          micDenied:'Microphone access was denied.',
          micNetwork:'Unable to access microphone.',
          noSpeech:'No speech detected.',
          noAudio:'No audio captured.',
          unsupported:'Voice dictation is not supported in this browser.',
          transcriptionFailed:'Unable to transcribe audio.',
        },
      });
      return taskFormDictationController;
    }

    function stopTaskFormDictation(options){
      const settings=options||{};
      const controller=ensureTaskFormDictationController();
      if(controller){
        controller.stop(settings);
        if(settings.discard&&settings.updateStatus!==false){
          setTaskFormMicStatus('Dictation canceled.','info');
          renderTaskFormDictationState();
        }
        return;
      }
      OPS.taskFormDictationActive=false;
      OPS.taskFormDictationBusy=false;
      if(settings.updateStatus!==false){
        setTaskFormMicStatus(settings.discard?'Dictation canceled.':'Recording stopped.',settings.discard?'info':'success');
      }
      renderTaskFormDictationState();
    }

    async function startTaskFormDictation(){
      if(OPS.taskFormDictationActive||OPS.taskFormDictationBusy)return;
      if(!taskFormCanDictate()){
        setTaskFormMicStatus('Voice dictation is not supported in this browser.','error');
        renderTaskFormDictationState();
        return;
      }
      OPS.taskFormDictationDiscard=false;
      setTaskFormMicStatus('','info');
      const controller=ensureTaskFormDictationController();
      if(!controller){
        setTaskFormMicStatus('Voice dictation is not supported in this browser.','error');
        renderTaskFormDictationState();
        return;
      }
      await controller.start();
    }

    async function toggleTaskFormDictation(){
      if(OPS.taskFormDictationActive)return stopTaskFormDictation();
      return await startTaskFormDictation();
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

    const TASK_FORM_SELECTOR='form[data-ops-submit="save-task"], form[data-ops-submit="create-epic"]';

    function clearTaskFormFocusState(){
      OPS.taskFormFocusedForm='';
      OPS.taskFormFocusedField='';
      OPS.taskFormSelectionStart=null;
      OPS.taskFormSelectionEnd=null;
    }

    function captureTaskFormFocus(field,form){
      if(!field||!form)return false;
      OPS.taskFormFocusedForm=form.dataset.opsSubmit||'';
      OPS.taskFormFocusedField=field.getAttribute('name')||'';
      OPS.taskFormSelectionStart=typeof field.selectionStart==='number'?field.selectionStart:null;
      OPS.taskFormSelectionEnd=typeof field.selectionEnd==='number'?field.selectionEnd:null;
      return !!(OPS.taskFormFocusedForm&&OPS.taskFormFocusedField);
    }

    function isTransientProjectDetailFocus(active){
      if(!documentRef)return false;
      if(!active)return true;
      if(active===documentRef.body||active===documentRef.documentElement)return true;
      if(active.isConnected===false)return true;
      return false;
    }

    function rememberTaskFormFocus(){
      if(!documentRef){
        clearTaskFormFocusState();
        return;
      }
      const active=documentRef.activeElement;
      if(active&&typeof active.closest==='function'){
        const form=active.closest(TASK_FORM_SELECTOR);
        const field=active.closest('[name]');
        if(form&&field&&root()&&root().contains(form)){
          captureTaskFormFocus(field,form);
          return;
        }
      }
      // Some project-detail refresh paths briefly clear the old DOM before this
      // renderer runs, leaving document.activeElement on <body>. Keep the last
      // explicit task-form focus in that transient state so the 5s refresh loop
      // does not deselect the new-task input while the user is typing.
      if(isTransientProjectDetailFocus(active))return;
      clearTaskFormFocusState();
    }

    function restoreTaskFormFocus(){
      if(!OPS.taskFormFocusedForm||!OPS.taskFormFocusedField)return;
      const selector=`form[data-ops-submit="${OPS.taskFormFocusedForm}"] [name="${OPS.taskFormFocusedField}"]`;
      const field=root()&&root().querySelector(selector);
      if(!field||field.disabled)return;
      const start=typeof OPS.taskFormSelectionStart==='number'?OPS.taskFormSelectionStart:null;
      const end=typeof OPS.taskFormSelectionEnd==='number'?OPS.taskFormSelectionEnd:start;
      const requestFrame=windowRef&&typeof windowRef.requestAnimationFrame==='function'
        ? windowRef.requestAnimationFrame.bind(windowRef)
        : (cb=>setTimeout(cb,0));
      requestFrame(()=>{
        if(!root()||!root().contains(field)||field.disabled)return;
        if(typeof field.focus==='function')field.focus({preventScroll:true});
        if(typeof field.setSelectionRange==='function'&&start!==null){
          field.setSelectionRange(start,end===null?start:end);
        }
      });
    }

    function projectDetailScrollEntries(container){
      const entries=[];
      if(!container)return entries;
      const canQuery=typeof container.querySelector==='function';
      [
        ['root',container],
        ['controls',canQuery?container.querySelector('.tasks-controls'):null],
        ['content',canQuery?container.querySelector('.tasks-content'):null],
        ['page',canQuery?container.querySelector('.project-page-content'):null],
        ['create-card',canQuery?container.querySelector('.tasks-card-create'):null],
        ['form-area',canQuery?container.querySelector('.tasks-form-area'):null],
        ['secondary-panels-body',canQuery?container.querySelector('.ops-project-secondary-panels-body'):null],
      ].forEach(([key,node])=>{
        if(!node)return;
        entries.push({key,node,top:Number(node.scrollTop)||0,left:Number(node.scrollLeft)||0});
      });
      return entries;
    }

    function rememberProjectDetailLocalState(){
      const container=root();
      const detailState={
        windowX:windowRef&&typeof windowRef.scrollX==='number'?windowRef.scrollX:null,
        windowY:windowRef&&typeof windowRef.scrollY==='number'?windowRef.scrollY:null,
        scrolls:projectDetailScrollEntries(container).map(entry=>({key:entry.key,top:entry.top,left:entry.left})),
        details:[],
      };
      if(container&&typeof container.querySelectorAll==='function'){
        detailState.details=Array.from(container.querySelectorAll('details')).map((detail,index)=>{
          const summary=detail.querySelector('summary');
          return {
            index,
            open:!!detail.open,
            summary:String(summary&&summary.textContent||'').replace(/\s+/g,' ').trim(),
            className:String(detail.className||''),
          };
        });
      }
      return detailState;
    }

    function restoreProjectDetailLocalState(state){
      if(!state||!root())return;
      const requestFrame=windowRef&&typeof windowRef.requestAnimationFrame==='function'
        ? windowRef.requestAnimationFrame.bind(windowRef)
        : (cb=>setTimeout(cb,0));
      const apply=()=>{
        const container=root();
        if(!container)return;
        if(Array.isArray(state.details)&&state.details.length&&typeof container.querySelectorAll==='function'){
          const details=Array.from(container.querySelectorAll('details'));
          state.details.forEach(saved=>{
            const match=details.find((detail,index)=>{
              const summary=detail.querySelector('summary');
              const summaryText=String(summary&&summary.textContent||'').replace(/\s+/g,' ').trim();
              return index===saved.index || (summaryText&&summaryText===saved.summary&&String(detail.className||'')===saved.className);
            });
            if(match)match.open=!!saved.open;
          });
        }
        const scrolls=Array.isArray(state.scrolls)?state.scrolls:[];
        const byKey=scrolls.reduce((acc,entry)=>{acc[entry.key]=entry;return acc;},{});
        projectDetailScrollEntries(container).forEach(entry=>{
          const saved=byKey[entry.key];
          if(!saved)return;
          entry.node.scrollTop=Number(saved.top)||0;
          entry.node.scrollLeft=Number(saved.left)||0;
        });
        if(windowRef&&typeof windowRef.scrollTo==='function'&&state.windowY!==null){
          windowRef.scrollTo(Number(state.windowX)||0,Number(state.windowY)||0);
        }
      };
      requestFrame(()=>requestFrame(apply));
    }

    function normalizeTaskFormDraft(epics,edit){
      const epicIds=(epics||[]).map(epic=>String(epic&&epic.id||'').trim()).filter(Boolean);
      const fallbackEpicId=epicIds[0]||'';
      const existing=OPS.taskFormDraft&&typeof OPS.taskFormDraft==='object'?OPS.taskFormDraft:{};
      if(edit&&edit.task){
        const taskId=String(edit.task.id||'').trim();
        const sameTask=String(existing.taskId||'').trim()===taskId;
        const selectedEpicId=sameTask&&epicIds.includes(String(existing.epicId||'').trim())
          ? String(existing.epicId||'').trim()
          : String(edit.epic&&edit.epic.id||fallbackEpicId).trim();
        OPS.taskFormDraft={
          taskId,
          text:sameTask?String(existing.text||''):String(edit.task.text||''),
          epicId:selectedEpicId,
          grade:normalizeTaskGrade(sameTask?existing.grade:edit.task.grade),
          flags:sameTask?String(existing.flags||''):String((edit.task.flags||[]).join(', ')),
          markers:sameTask?String(existing.markers||''):String((edit.task.markers||[]).join(', ')),
          images:sameTask?String(existing.images||''):String(taskImageRefs(edit.task).join(', ')),
        };
        return OPS.taskFormDraft;
      }
      const selectedEpicId=epicIds.includes(String(existing.epicId||'').trim())
        ? String(existing.epicId||'').trim()
        : fallbackEpicId;
      OPS.taskFormDraft={
        taskId:'',
        text:String(existing.taskId?'':existing.text||''),
        epicId:selectedEpicId,
        grade:normalizeTaskGrade(existing.taskId?'green':existing.grade),
        flags:String(existing.taskId?'':existing.flags||''),
        markers:String(existing.taskId?'':existing.markers||''),
        images:String(existing.taskId?'':existing.images||''),
      };
      return OPS.taskFormDraft;
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
      const filtersExpanded=!OPS.taskFiltersCollapsed;
      const filterActive=taskFilterPanelActive(filters);
      return `
        <div class="tasks-card tasks-card-filters">
          <div class="tasks-card-header">
            <div>
              <div class="tasks-card-title">Filter and sort</div>
              <div class="tasks-card-subtitle">Focus on the work that matters right now.</div>
            </div>
          </div>
          ${filtersExpanded?`
            <div class="tasks-filters">
              <div class="tasks-filter-group">
                <div class="tasks-filter-title">Task filters</div>
                <div class="tasks-filter-row">
                  <label class="tasks-field">
                    <span class="tasks-field-label">Grade</span>
                    <select class="task-select task-filter-select" data-ops-filter="grade">
                      <option value="">Any grade</option>
                      ${['green','orange','red'].map(grade=>`<option value="${grade}" ${filters.grade===grade?'selected':''}>${grade}</option>`).join('')}
                    </select>
                  </label>
                  <label class="tasks-field">
                    <span class="tasks-field-label">Marker or flag</span>
                    <input class="task-input" data-ops-filter="token" autocomplete="off" value="${esc(filters.token)}" placeholder="ui, backend, ai suggestion">
                  </label>
                  <div class="tasks-form-actions">
                    <button class="menu-action-btn secondary small" type="button" data-ops-action="reset-task-filters" ${filterActive?'':'disabled'}>${svg.close}<span>Reset</span></button>
                  </div>
                </div>
              </div>
            </div>
          `:`<div class="repo-empty">Filters are hidden.</div>`}
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
      rememberTaskFormFocus();
      const localState=rememberProjectDetailLocalState();
      const rootEl=root();
      const logScrollState=captureLogScrollState(rootEl);
      setDashboardTopbar(nameOf(project),`${counts.active} active | ${counts.done} done | ${OPS.taskData.branch||project.coreBranch||'main'}`);
      const edit=OPS.editingTask;
      const showCreateBand=!OPS.taskCreateCollapsed||!!edit;
      const filtersExpanded=!OPS.taskFiltersCollapsed;
      const taskDraft=normalizeTaskFormDraft(epics,edit);
      const taskMicState=taskFormMicButtonState();
      const selectedEpicId=String(taskDraft.epicId||'').trim();
      const epicOptions=epics.map(epic=>`<option value="${esc(epic.id)}" ${epic.id===selectedEpicId?'selected':''}>${esc(epic.title)}</option>`).join('');
      const taskForm=epics.length?`
        <form class="tasks-form" data-ops-submit="save-task">
          <input type="hidden" name="taskId" value="${esc(taskDraft.taskId||'')}">
          <label class="tasks-field tasks-field-text">
            <span class="tasks-field-label">${edit?'Task text':'New task'}</span>
            <span class="task-input-row task-input-row-with-mic">
              <input class="task-input" name="text" autocomplete="off" required value="${esc(taskDraft.text||'')}" placeholder="Add a task for this epic">
              <button class="menu-action-btn secondary task-mic-btn task-input-mic ${taskMicState.listening?'listening':''}" type="button" data-ops-action="toggle-task-dictation" title="${esc(taskMicState.title)}" aria-pressed="${taskMicState.listening?'true':'false'}" ${taskMicState.disabled?'disabled':''}>
                ${svg.mic||'🎙️'}<span>${esc(taskMicState.label)}</span>
              </button>
            </span>
          </label>
          <label class="tasks-field">
            <span class="tasks-field-label">Epic</span>
            <select class="task-select" name="epicId">${epicOptions}</select>
          </label>
          <label class="tasks-field">
            <span class="tasks-field-label">Grade</span>
            <select class="task-select task-grade-select" name="grade">
            ${['green','orange','red'].map(grade=>`<option value="${grade}" ${taskDraft.grade===grade?'selected':''}>${grade}</option>`).join('')}
            </select>
          </label>
          <label class="tasks-field task-field-flags">
            <span class="tasks-field-label">Flags</span>
            <input class="task-input" name="flags" autocomplete="off" value="${esc(taskDraft.flags||'')}" placeholder="Comma-separated, e.g. search">
          </label>
          <label class="tasks-field">
            <span class="tasks-field-label">Markers</span>
            <input class="task-input" name="markers" autocomplete="off" value="${esc(taskDraft.markers||'')}" placeholder="Comma-separated markers">
          </label>
          <label class="tasks-field task-field-images">
            <span class="tasks-field-label">Images</span>
            <input class="task-input" name="images" autocomplete="off" value="${esc(taskDraft.images||'')}" placeholder="path or URL">
          </label>
          <div class="tasks-form-actions">
            <button class="task-add-btn" type="submit">${edit?'Save task':'Add task'}</button>
            ${edit?'<button class="menu-action-btn secondary" type="button" data-ops-action="cancel-edit">Cancel edit</button>':''}
          </div>
          ${OPS.taskFormDictationStatus?`<div class="task-mic-status ${esc(OPS.taskFormDictationStatusKind||'info')}">${esc(OPS.taskFormDictationStatus)}</div>`:''}
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
        renderProjectRuntimeSnapshot(project.id),
        renderProjectRuntimeScreenshot(project.id),
        renderProjectPlayLogs(project.id),
        renderProjectGatherReports(project),
        renderProjectReviewRequests(project),
        renderProjectDeployment(project),
        renderProjectDatabase(project),
      ].filter(Boolean).join('');
      const archived=filters.status==='archived';
      const doneCount=Number(filterSummary&&filterSummary.done||0);
      const actionableCount=actionableTaskCount(filterSummary);
      const projectId=String(OPS.currentProject&&OPS.currentProject.id||'').trim();
      const executeReadyBusy=projectId&&OPS.taskAutomationBusyByProject[projectId]==='execute-ready';
      const archivedCount=taskVisibleCount(filterSummary,{status:'archived'});
      const activeScopedTotal=Math.max(0,Number(filterSummary.total||0)-archivedCount);
      const heroCount=archived?`${archivedCount} archived`:`${Math.min(doneCount,activeScopedTotal)}/${activeScopedTotal} done`;

      rootEl.innerHTML=`
        <div class="ops-dashboard ops-project-detail project-page-content">
          <div class="tasks-wrapper show" aria-label="Project epics">
            <div class="tasks-hero">
              <div>
                <div class="tasks-title">Project epics</div>
                <div class="tasks-subtitle">${esc(`${nameOf(project)} • ${OPS.taskData.branch||project.coreBranch||'main'} • ${projectPath(project)}`)}</div>
              </div>
              <div class="tasks-hero-actions">
                <div class="tasks-count">${esc(heroCount)}</div>
                <div class="tasks-view-tabs" role="tablist" aria-label="Task list view">
                  <button class="tasks-view-tab ${archived?'':'active'}" type="button" role="tab" aria-selected="${archived?'false':'true'}" data-ops-action="show-active">
                    Active
                  </button>
                  <button class="tasks-view-tab ${archived?'active':''}" type="button" role="tab" aria-selected="${archived?'true':'false'}" data-ops-action="show-archived">
                    Archived
                  </button>
                </div>
                <button class="menu-action-btn secondary small" type="button" data-ops-action="back-home">Ops dashboard</button>
                <button class="menu-action-btn secondary small" type="button" data-ops-action="back-projects">Projects</button>
                <button class="tasks-archive-btn" type="button" data-ops-action="archive-completed" ${archived||!doneCount?'disabled':''}>Archive completed</button>
                <button class="tasks-form-toggle" type="button" data-ops-action="toggle-task-create" aria-expanded="${showCreateBand?'true':'false'}">
                  ${showCreateBand?'Hide create fields':'Show create fields'}
                </button>
                <button class="tasks-filters-toggle" type="button" data-ops-action="toggle-task-filters" aria-expanded="${filtersExpanded?'true':'false'}">
                  ${filtersExpanded?'Hide filters':'Show filters'}
                </button>
                <button class="menu-action-btn secondary small" type="button" data-ops-action="refresh-detail">${svg.refresh}<span>Refresh</span></button>
              </div>
            </div>
            <div class="tasks-layout">
              <section class="tasks-controls">
                ${showCreateBand?`
                  <div class="tasks-card tasks-card-create">
                    <div class="tasks-card-header">
                      <div>
                        <div class="tasks-card-title">Create</div>
                        <div class="tasks-card-subtitle">Add an epic or drop tasks into an epic.</div>
                      </div>
                    </div>
                    <div class="tasks-form-area">
                      <form class="tasks-form" data-ops-submit="create-epic">
                        <label class="tasks-field">
                          <span class="tasks-field-label">New epic</span>
                          <input class="task-input" name="title" autocomplete="off" value="${esc(OPS.createEpicDraftTitle||'')}" placeholder="Clean up the UI" required>
                        </label>
                        <div class="tasks-form-actions">
                          <button class="task-add-btn" type="submit">Add epic</button>
                        </div>
                      </form>
                      ${taskForm}
                    </div>
                  </div>
                `:''}
                ${renderTaskFilters(filterSummary)}
                <div class="tasks-card tasks-card-tools">
                  <div class="tasks-card-header">
                    <div>
                      <div class="tasks-card-title">Project tools</div>
                      <div class="tasks-card-subtitle">${esc(`Profile ${projectProfileLabel(project)} • ${project.active===false?'Inactive':'Active'} • ${counts.epics} epics`)}</div>
                    </div>
                  </div>
                  <div class="tasks-card-body">
                    <div class="tasks-card-actions">
                      ${renderProjectPlayControls(project,{detail:true})}
                      <button class="menu-action-btn danger small" type="button" data-ops-action="delete-project" data-project-id="${esc(project.id)}">Delete project</button>
                    </div>
                    ${!archived?`<button class="menu-action-btn secondary small" type="button" data-ops-action="execute-ready-tasks" ${!projectId||(!actionableCount&&!executeReadyBusy)?'disabled':''} title="Ask Codex to execute ready and needs-more-work tasks in sequence.">${executeReadyBusy?'Starting...':'Execute ready tasks with AI'}${!executeReadyBusy&&actionableCount?` (${actionableCount})`:''}</button>`:''}
                    ${secondaryPanels?`
                      <details class="ops-project-secondary-panels">
                        <summary>Advanced project tools</summary>
                        <div class="ops-project-secondary-panels-body">
                          ${secondaryPanels}
                        </div>
                      </details>
                    `:'<div class="repo-empty">No secondary tools for this project.</div>'}
                  </div>
                </div>
              </section>
              <section class="tasks-content">
                <div class="tasks-list">${epicList}</div>
              </section>
            </div>
          </div>
        </div>
      `;
      restoreTaskFilterFocus();
      restoreTaskFormFocus();
      restoreProjectDetailLocalState(localState);
      restoreLogScrollState(rootEl,logScrollState);
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
        <section class="epic-card ${collapsed?'collapsed':''}" data-epic-id="${esc(epicId)}" style="${epicAccentStyle(index,epic)}">
          <div class="epic-header">
            <div class="epic-header-main">
              <button class="epic-toggle" type="button" data-ops-action="toggle-epic" data-epic-id="${esc(epicId)}" aria-expanded="${collapsed?'false':'true'}" title="${collapsed?'Expand epic':'Collapse epic'}">
                <span class="epic-caret" aria-hidden="true"></span>
              </button>
              <div class="epic-title">
                <span>${esc(epic.title)}</span>
                ${markers.length?`<span class="task-markers">${markers.map(marker=>`<span class="task-marker ${String(marker).trim().toLowerCase()==='ai suggestion'?'ai-suggestion':''}">${esc(marker)}</span>`).join('')}</span>`:''}
              </div>
            </div>
            <div class="epic-header-actions">
              <span class="epic-meta">${totalCount?`${doneCount}/${totalCount} done${visibleCount!==totalCount?` • ${visibleCount} shown`:''}`:'No tasks yet'}</span>
              <button class="menu-action-btn danger small" type="button" data-ops-action="delete-epic" data-epic-id="${esc(epic.id)}">Delete</button>
            </div>
          </div>
          <div class="epic-tasks">${rows || '<div class="epic-empty">No tasks yet. Add one above.</div>'}</div>
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
      const taskClasses=['task-item',statusKey];
      if(editing)taskClasses.push('editing');
      if(task&&task.done)taskClasses.push('done');
      if(task&&task.archived)taskClasses.push('archived');
      return `
        <div class="${taskClasses.join(' ')}">
          <div class="task-title-row">
            <span class="task-grade-badge grade-${esc(grade)}">${esc(grade)}</span>
            <div class="task-text">${esc(task.text)}</div>
            ${markers.length?`<span class="task-markers">${markers.map(marker=>`<span class="task-marker ${String(marker).trim().toLowerCase()==='ai suggestion'?'ai-suggestion':''}">${esc(marker)}</span>`).join('')}</span>`:''}
          </div>
          <div class="task-meta"><span>${esc(metaText)}</span></div>
          <div class="task-stamps">
              ${stampEntries.map(([label,value])=>`
                <span class="task-stamp">
                  <span class="task-stamp-label">${esc(label)}:</span>
                  <span class="task-stamp-value">${esc(value)}</span>
                </span>
              `).join('')}
          </div>
          ${dependencies.length?`<div class="task-dependencies">Depends on: ${esc(dependencies.join(', '))}</div>`:''}
          ${flags.length?`<div class="task-flags">Flags: ${esc(flags.join(', '))}</div>`:''}
          ${imageRefs.length?`<div class="task-images" title="${esc(imageTitle)}">Images: ${esc(String(imageRefs.length))}</div>`:''}
          ${qaStatus==='needs-more-work'||moreWork?`<div class="task-more-work">Needs more work: ${esc(moreWork||'No details provided.')}</div>`:''}
          ${task.archived?'':`
            <div class="task-actions">
              <select class="task-select task-grade-select grade-${esc(grade)}" data-ops-task-grade="${esc(task.id)}" aria-label="Task grade">
                ${TASK_GRADE_VALUES.map(value=>`<option value="${value}" ${value===grade?'selected':''}>${value.charAt(0).toUpperCase()+value.slice(1)}</option>`).join('')}
              </select>
              <button class="menu-action-btn small" type="button" data-ops-action="task-primary" data-task-id="${esc(task.id)}" data-task-mode="${esc(actionState.action)}" ${actionState.sessionKey?`data-session-key="${esc(actionState.sessionKey)}"`:''} ${actionState.disabled?'disabled':''} ${actionState.title?`title="${esc(actionState.title)}"`:''}>${esc(actionState.label)}</button>
              ${qaStatus==='ready-for-test'&&!task.done?`<button class="menu-action-btn danger small" type="button" data-ops-action="task-needs-more-work" data-task-id="${esc(task.id)}">Needs more work</button>`:''}
              ${qaStatus==='ready-for-test'&&!task.done?`<button class="menu-action-btn secondary small" type="button" data-ops-action="complete-task" data-task-id="${esc(task.id)}" ${isBlocked?'disabled title="Complete dependencies to unlock this task."':''}>Complete</button>`:''}
              <button class="menu-action-btn secondary small" type="button" data-ops-action="edit-task" data-task-id="${esc(task.id)}" ${editing?'disabled':''}>${editing?'Editing':'Edit'}</button>
              <button class="menu-action-btn danger small" type="button" data-ops-action="delete-task" data-task-id="${esc(task.id)}">Delete</button>
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

    function handleTaskFormFocus(event){
      const target=event&&event.target;
      const form=target&&typeof target.closest==='function'
        ? target.closest(TASK_FORM_SELECTOR)
        : null;
      const field=target&&typeof target.closest==='function'
        ? target.closest('[name]')
        : null;
      if(!form||!field||!root()||!root().contains(form)||OPS.view!=='project-detail')return;
      captureTaskFormFocus(field,form);
    }

    function handleTaskFormField(event){
      const form=event.target&&typeof event.target.closest==='function'
        ? event.target.closest(TASK_FORM_SELECTOR)
        : null;
      if(!form||!root()||!root().contains(form)||OPS.view!=='project-detail')return;
      const field=event.target&&typeof event.target.closest==='function'
        ? event.target.closest('[name]')
        : null;
      if(field)captureTaskFormFocus(field,form);
      const data=Object.fromEntries(new FormData(form).entries());
      if(form.dataset.opsSubmit==='create-epic'){
        OPS.createEpicDraftTitle=String(data.title||'');
        return;
      }
      if(form.dataset.opsSubmit!=='save-task')return;
      OPS.taskFormDraft={
        taskId:String(data.taskId||''),
        text:String(data.text||''),
        epicId:String(data.epicId||''),
        grade:normalizeTaskGrade(data.grade||'green'),
        flags:String(data.flags||''),
        markers:String(data.markers||''),
        images:String(data.images||''),
      };
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
      rememberTaskFormFocus,
      restoreTaskFormFocus,
      normalizeTaskFormDraft,
      toggleTaskFormDictation,
      handleTaskFilterField,
      handleTaskRowField,
      handleTaskFormFocus,
      handleTaskFormField,
    };
  }

  window.HermesOpsModules.projectDetail={bindDashboard};
})();

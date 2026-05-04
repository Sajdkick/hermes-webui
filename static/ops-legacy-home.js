(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};

  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const AgentBridgeRef=ctx&&ctx.AgentBridge;
    const renderCurrentOpsView=ctx&&ctx.renderCurrentOpsView;
    const root=ctx&&ctx.root;
    const esc=ctx&&ctx.esc;
    const svg=ctx&&ctx.svg;
    const showError=ctx&&ctx.showError;
    const setBusy=ctx&&ctx.setBusy;
    const setDashboardTopbar=ctx&&ctx.setDashboardTopbar;
    const renderNotifications=ctx&&ctx.renderNotifications;
    const normalizedAutoApprovalPolicy=ctx&&ctx.normalizedAutoApprovalPolicy;
    const loadProjects=ctx&&ctx.loadProjects;
    const loadNotifications=ctx&&ctx.loadNotifications;
    const loadOpsRuns=ctx&&ctx.loadOpsRuns;
    const loadNotificationDiagnostics=ctx&&ctx.loadNotificationDiagnostics;
    const findProject=ctx&&ctx.findProject;
    const projectUsesBranchTitle=ctx&&ctx.projectUsesBranchTitle;
    const projectBranchLabel=ctx&&ctx.projectBranchLabel;
    const projectCardTitle=ctx&&ctx.projectCardTitle;
    const projectRepositoryLabel=ctx&&ctx.projectRepositoryLabel;
    const normalizeRunStatus=ctx&&ctx.normalizeRunStatus;
    const runStatusLabel=ctx&&ctx.runStatusLabel;
    const runStatusKind=ctx&&ctx.runStatusKind;
    const formatOpsDateTime=ctx&&ctx.formatOpsDateTime;
    const renderProjectGitQuickAction=ctx&&ctx.renderProjectGitQuickAction;
    const renderProjectPlayQuickAction=ctx&&ctx.renderProjectPlayQuickAction;
    const renderProjectActivityQuickAction=ctx&&ctx.renderProjectActivityQuickAction;
    const sessionAccentStyle=ctx&&ctx.sessionAccentStyle;
    const sessionGroupAccentStyle=ctx&&ctx.sessionGroupAccentStyle;
    const sessionRefValue=ctx&&ctx.sessionRefValue;
    const canonicalTaskSessions=ctx&&ctx.canonicalTaskSessions;
    const projectSessionsFor=ctx&&ctx.projectSessionsFor;
    const isSessionForProject=ctx&&ctx.isSessionForProject;
    const taskImageLabel=ctx&&ctx.taskImageLabel;
    const writeStoredJson=ctx&&ctx.writeStoredJson;
    const sessionGroupStorageKey=ctx&&ctx.sessionGroupStorageKey;
    const navigatorRef=ctx&&ctx.navigatorRef;
    const windowRef=ctx&&ctx.windowRef;
    const documentRef=ctx&&ctx.documentRef;
    const URLRef=ctx&&ctx.URLRef;
    const MediaRecorderRef=ctx&&ctx.MediaRecorderRef;
    const FileRef=ctx&&ctx.FileRef;
    const requestAnimationFrameRef=ctx&&ctx.requestAnimationFrameRef;
    const taskDictationPrompt=ctx&&ctx.taskDictationPrompt;
    const taskDictationAudioBitsPerSecond=ctx&&ctx.taskDictationAudioBitsPerSecond;
    const runActiveStatusValues=Array.isArray(ctx&&ctx.runActiveStatusValues)?ctx.runActiveStatusValues:[];
    if(
      !OPS
      || !AgentBridgeRef
      || !AgentBridgeRef.sessions
      || typeof renderCurrentOpsView!=='function'
      || typeof root!=='function'
      || typeof esc!=='function'
      || !svg
      || typeof loadProjects!=='function'
      || typeof loadNotifications!=='function'
      || typeof loadOpsRuns!=='function'
      || typeof findProject!=='function'
      || typeof projectUsesBranchTitle!=='function'
      || typeof projectBranchLabel!=='function'
      || typeof projectCardTitle!=='function'
      || typeof projectRepositoryLabel!=='function'
      || typeof normalizeRunStatus!=='function'
      || typeof runStatusLabel!=='function'
      || typeof runStatusKind!=='function'
      || typeof formatOpsDateTime!=='function'
      || typeof renderProjectGitQuickAction!=='function'
      || typeof renderProjectPlayQuickAction!=='function'
      || typeof renderProjectActivityQuickAction!=='function'
      || typeof sessionAccentStyle!=='function'
      || typeof sessionGroupAccentStyle!=='function'
      || typeof sessionRefValue!=='function'
      || typeof canonicalTaskSessions!=='function'
      || typeof projectSessionsFor!=='function'
      || typeof isSessionForProject!=='function'
      || typeof taskImageLabel!=='function'
      || typeof writeStoredJson!=='function'
    ){
      return {};
    }

    function quickTaskProjectName(project){
      if(!project||typeof project!=='object')return 'Project';
      const name=String(project.name||project.fullName||project.slug||project.id||'Project').trim();
      return name||'Project';
    }

    function quickTaskProjectBranch(project){
      const branch=projectBranchLabel(project);
      return branch||'';
    }

    function formatQuickTaskProjectOptionLabel(project){
      const name=quickTaskProjectName(project);
      const branch=quickTaskProjectBranch(project);
      if(projectUsesBranchTitle(project,OPS.projects)&&branch&&name)return `${branch} (${name})`;
      return name;
    }

    function appendTranscriptText(current,next){
      const trimmed=String(next||'').trim();
      if(!trimmed)return String(current||'').trim();
      const existing=String(current||'').trim();
      return existing?`${existing} ${trimmed}`:trimmed;
    }

    function normalizeDictationLanguage(tag){
      if(typeof tag!=='string')return '';
      const trimmed=tag.trim();
      if(!trimmed)return '';
      const primary=trimmed.toLowerCase().split(/[-_]/)[0];
      return primary.length>=2&&primary.length<=3?primary:'';
    }

    function getPreferredAudioMimeType(){
      if(typeof MediaRecorderRef==='undefined')return '';
      const candidates=['audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus','audio/ogg'];
      return candidates.find(type=>MediaRecorderRef.isTypeSupported&&MediaRecorderRef.isTypeSupported(type))||'';
    }

    function getDictationLanguage(){
      const language=Array.isArray(navigatorRef&&navigatorRef.languages)&&navigatorRef.languages.length
        ? navigatorRef.languages[0]
        : navigatorRef&&navigatorRef.language;
      return normalizeDictationLanguage(language);
    }

    function getDictationPrompt(language){
      if(language&&language!=='en')return '';
      return taskDictationPrompt;
    }

    function getDictationAudioConstraints(){
      const supported=navigatorRef&&navigatorRef.mediaDevices&&typeof navigatorRef.mediaDevices.getSupportedConstraints==='function'
        ? navigatorRef.mediaDevices.getSupportedConstraints()
        : {};
      const audio={};
      if(supported.echoCancellation)audio.echoCancellation=true;
      if(supported.noiseSuppression)audio.noiseSuppression=true;
      if(supported.autoGainControl)audio.autoGainControl=true;
      if(supported.channelCount)audio.channelCount={ideal:1};
      if(supported.sampleRate)audio.sampleRate={ideal:48000};
      if(supported.sampleSize)audio.sampleSize={ideal:16};
      return Object.keys(audio).length?audio:true;
    }

    function createDictationRecorder(stream,mimeType){
      const options={};
      if(mimeType)options.mimeType=mimeType;
      if(Number.isFinite(taskDictationAudioBitsPerSecond))options.audioBitsPerSecond=taskDictationAudioBitsPerSecond;
      try{
        return new MediaRecorderRef(stream,Object.keys(options).length?options:undefined);
      }catch(error){
        if('audioBitsPerSecond' in options){
          const fallback={...options};
          delete fallback.audioBitsPerSecond;
          return new MediaRecorderRef(stream,Object.keys(fallback).length?fallback:undefined);
        }
        throw error;
      }
    }

    function quickTaskImageId(){
      return `quick-task-image-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,8)}`;
    }

    function quickTaskImageSignature(file){
      if(!file)return '';
      return [String(file.name||''),String(file.size||0),String(file.lastModified||0)].join(':');
    }

    function revokeQuickTaskImagePreview(entry){
      const url=String(entry&&entry.previewUrl||'').trim();
      if(!url||!URLRef||typeof URLRef.revokeObjectURL!=='function')return;
      try{URLRef.revokeObjectURL(url);}catch(_){}
    }

    function clearQuickTaskImages(){
      (OPS.quickTaskImages||[]).forEach(revokeQuickTaskImagePreview);
      OPS.quickTaskImages=[];
    }

    function addQuickTaskImages(files){
      const next=[...(OPS.quickTaskImages||[])];
      const seen=new Set(next.map(entry=>quickTaskImageSignature(entry&&entry.file)));
      Array.from(files||[]).forEach(file=>{
        if(!file||!String(file.type||'').startsWith('image/'))return;
        const signature=quickTaskImageSignature(file);
        if(!signature||seen.has(signature))return;
        seen.add(signature);
        let previewUrl='';
        if(URLRef&&typeof URLRef.createObjectURL==='function'){
          try{previewUrl=URLRef.createObjectURL(file);}catch(_){}
        }
        next.push({id:quickTaskImageId(),file,previewUrl});
      });
      OPS.quickTaskImages=next;
    }

    function removeQuickTaskImage(imageId){
      const id=String(imageId||'').trim();
      if(!id)return;
      const next=[];
      (OPS.quickTaskImages||[]).forEach(entry=>{
        if(String(entry&&entry.id||'')===id){
          revokeQuickTaskImagePreview(entry);
          return;
        }
        next.push(entry);
      });
      OPS.quickTaskImages=next;
    }

    function setQuickTaskMicStatus(message,type){
      OPS.quickTaskDictationStatus=String(message||'').trim();
      OPS.quickTaskDictationStatusKind=type==='error'||type==='success'?type:'info';
    }

    function normalizeQuickTaskProjectSelection(){
      if(!OPS.projects.length){
        OPS.quickTaskProjectId='';
        return '';
      }
      const current=String(OPS.quickTaskProjectId||'').trim();
      if(current&&OPS.projects.some(project=>project.id===current))return current;
      OPS.quickTaskProjectId=OPS.projects[0].id;
      return OPS.quickTaskProjectId;
    }

    function quickTaskCanDictate(){
      return !!(
        OPS.quickTaskDictationSupported
        && normalizeQuickTaskProjectSelection()
        && !OPS.quickTaskBusy
      );
    }

    function quickTaskMicButtonState(){
      let label='Record';
      let title='Start recording';
      if(OPS.quickTaskDictationBusy){
        label='Transcribing';
        title='Transcribing audio...';
      }else if(OPS.quickTaskDictationActive){
        label='Stop';
        title='Stop recording';
      }else if(!OPS.quickTaskDictationSupported){
        title='Voice dictation is not supported in this browser.';
      }else if(!normalizeQuickTaskProjectSelection()){
        title='Select a project to enable quick task dictation.';
      }
      return {
        label,
        title,
        disabled:OPS.quickTaskDictationBusy||(!OPS.quickTaskDictationActive&&!quickTaskCanDictate()),
        listening:OPS.quickTaskDictationActive,
      };
    }

    function cleanupQuickTaskDictationStream(){
      const stream=OPS.quickTaskDictationStream;
      if(!stream||typeof stream.getTracks!=='function')return;
      stream.getTracks().forEach(track=>{
        try{track.stop();}catch(_){}
      });
      OPS.quickTaskDictationStream=null;
    }

    function stopQuickTaskDictation(options){
      const settings=options||{};
      if(settings.discard)OPS.quickTaskDictationDiscard=true;
      OPS.quickTaskDictationActive=false;
      const recorder=OPS.quickTaskDictationRecorder;
      if(recorder&&recorder.state!=='inactive'){
        try{
          recorder.stop();
          return;
        }catch(_){}
      }
      OPS.quickTaskDictationRecorder=null;
      OPS.quickTaskDictationChunks=[];
      OPS.quickTaskDictationDiscard=false;
      cleanupQuickTaskDictationStream();
      if(settings.updateStatus!==false){
        setQuickTaskMicStatus(settings.discard?'Dictation canceled.':'Recording stopped.',settings.discard?'info':'success');
      }
      renderCurrentOpsView();
    }

    async function transcribeQuickTaskAudio(blob){
      if(!blob||!blob.size)return;
      OPS.quickTaskDictationBusy=true;
      setQuickTaskMicStatus('Transcribing with OpenAI...','info');
      renderCurrentOpsView();
      try{
        const mimeType=String(blob.type||'audio/webm').trim()||'audio/webm';
        const extension=mimeType.includes('ogg')?'ogg':'webm';
        const file=FileRef
          ? new FileRef([blob],`quick-task-dictation.${extension}`,{type:mimeType})
          : blob;
        const data=await AgentBridgeRef.sessions.transcribeAudio(file,{filename:file&&file.name?file.name:`quick-task-dictation.${extension}`});
        const transcript=String(data.transcript||data.text||'').trim();
        if(!transcript){
          setQuickTaskMicStatus('No speech detected.','error');
          return;
        }
        OPS.quickTaskText=appendTranscriptText(OPS.quickTaskText,transcript);
        setQuickTaskMicStatus('Transcription added.','success');
        renderCurrentOpsView();
        restoreQuickTaskFocus();
      }catch(error){
        setQuickTaskMicStatus(error&&error.message?error.message:'Unable to transcribe audio.','error');
      }finally{
        OPS.quickTaskDictationBusy=false;
        renderCurrentOpsView();
      }
    }

    function handleQuickTaskDictationStop(recorder){
      const chunks=Array.isArray(OPS.quickTaskDictationChunks)?OPS.quickTaskDictationChunks.slice():[];
      const mimeType=String(recorder&&recorder.mimeType||'audio/webm').trim()||'audio/webm';
      OPS.quickTaskDictationRecorder=null;
      OPS.quickTaskDictationChunks=[];
      OPS.quickTaskDictationActive=false;
      cleanupQuickTaskDictationStream();
      if(OPS.quickTaskDictationDiscard){
        OPS.quickTaskDictationDiscard=false;
        setQuickTaskMicStatus('','info');
        renderCurrentOpsView();
        return;
      }
      if(!chunks.length){
        setQuickTaskMicStatus('No audio captured.','error');
        renderCurrentOpsView();
        return;
      }
      renderCurrentOpsView();
      void transcribeQuickTaskAudio(new Blob(chunks,{type:mimeType}));
    }

    async function startQuickTaskDictation(){
      if(OPS.quickTaskDictationActive||OPS.quickTaskDictationBusy)return;
      if(!OPS.quickTaskDictationSupported){
        setQuickTaskMicStatus('Voice dictation is not supported in this browser.','error');
        renderCurrentOpsView();
        return;
      }
      if(!quickTaskCanDictate()){
        setQuickTaskMicStatus('Select a project before using quick task dictation.','error');
        renderCurrentOpsView();
        return;
      }
      OPS.quickTaskDictationDiscard=false;
      OPS.quickTaskDictationBaseText=String(OPS.quickTaskText||'').trim();
      OPS.quickTaskDictationChunks=[];
      setQuickTaskMicStatus('Requesting microphone access...','info');
      renderCurrentOpsView();
      let stream=null;
      try{
        stream=await navigatorRef.mediaDevices.getUserMedia({audio:getDictationAudioConstraints()});
      }catch(error){
        const errorName=String(error&&error.name||'').trim();
        const message=errorName==='NotAllowedError'
          ? 'Microphone access was denied.'
          : errorName==='NotFoundError'
            ? 'No microphone found.'
            : 'Unable to access microphone.';
        setQuickTaskMicStatus(message,'error');
        renderCurrentOpsView();
        return;
      }
      OPS.quickTaskDictationStream=stream;
      let recorder=null;
      try{
        recorder=createDictationRecorder(stream,getPreferredAudioMimeType());
      }catch(error){
        OPS.quickTaskDictationSupported=false;
        cleanupQuickTaskDictationStream();
        setQuickTaskMicStatus('Recording is not supported in this browser.','error');
        renderCurrentOpsView();
        return;
      }
      OPS.quickTaskDictationRecorder=recorder;
      recorder.ondataavailable=event=>{
        if(event.data&&event.data.size>0)OPS.quickTaskDictationChunks.push(event.data);
      };
      recorder.onstart=()=>{
        OPS.quickTaskDictationActive=true;
        setQuickTaskMicStatus('Recording... Speak clearly and keep close to the mic.','info');
        renderCurrentOpsView();
      };
      recorder.onstop=()=>handleQuickTaskDictationStop(recorder);
      recorder.onerror=()=>{
        setQuickTaskMicStatus('Recording error. Try again.','error');
        stopQuickTaskDictation({updateStatus:false,discard:true});
      };
      try{
        recorder.start();
      }catch(error){
        OPS.quickTaskDictationRecorder=null;
        cleanupQuickTaskDictationStream();
        setQuickTaskMicStatus('Unable to start recording.','error');
        renderCurrentOpsView();
      }
    }

    function sessionGroupKey(group){
      const key=String((group&&group.key)||((group&&group.projectId)?`project:${group.projectId}`:'')).trim();
      return key||`group:${Math.random().toString(36).slice(2,10)}`;
    }

    function isSessionGroupCollapsed(key){
      return !!(key&&OPS.sessionGroupCollapsed&&OPS.sessionGroupCollapsed[key]);
    }

    function setSessionGroupCollapsed(key,collapsed){
      const groupKey=String(key||'').trim();
      if(!groupKey)return;
      OPS.sessionGroupCollapsed={...(OPS.sessionGroupCollapsed||{}),[groupKey]:!!collapsed};
      if(!collapsed)delete OPS.sessionGroupCollapsed[groupKey];
      writeStoredJson(sessionGroupStorageKey,OPS.sessionGroupCollapsed);
    }

    function syncSessionGroupState(groups){
      const activeKeys=new Set((groups||[]).map(group=>sessionGroupKey(group)).filter(Boolean));
      const next={};
      Object.entries(OPS.sessionGroupCollapsed||{}).forEach(([key,value])=>{
        if(activeKeys.has(key)&&value)next[key]=true;
      });
      OPS.sessionGroupCollapsed=next;
      writeStoredJson(sessionGroupStorageKey,OPS.sessionGroupCollapsed);
    }

    function sessionDisplayProject(group){
      if(group&&group.project&&group.project.id)return group.project;
      return findProject(group&&group.projectId||'');
    }

    function sessionWorkspaceProject(session){
      return findProject(session&&session.ops_project_id||session&&session.projectId||'');
    }

    function sessionDisplayTitle(session){
      const taskText=String(session&&session.ops_task&&session.ops_task.text||'').trim();
      if(taskText)return taskText;
      const title=String(session&&session.title||'').trim();
      return title||'Untitled';
    }

    function sessionDisplaySubtitle(session){
      const taskText=String(session&&session.ops_task&&session.ops_task.text||'').trim();
      const title=String(session&&session.title||'').trim();
      if(taskText&&title&&title!==taskText)return title;
      if(taskText){
        const epicTitle=String(session&&session.ops_task&&session.ops_task.epicTitle||'').trim();
        return epicTitle?`Epic: ${epicTitle}`:'Task session';
      }
      return 'Project chat';
    }

    function sessionWorkspacePrimaryLabel(session){
      const project=sessionWorkspaceProject(session);
      if(project)return projectCardTitle(project,OPS.projects);
      const branch=String(session&&session.branchLabel||session&&session.branch||'').trim();
      const repo=String(session&&session.repositoryLabel||session&&session.projectName||'').trim();
      return branch||repo||sessionDisplayTitle(session);
    }

    function sessionWorkspaceRepoLabel(session){
      const project=sessionWorkspaceProject(session);
      if(project)return projectRepositoryLabel(project);
      return String(session&&session.repositoryLabel||session&&session.projectName||'').trim();
    }

    function sessionWorkspaceSubtitle(session){
      const parts=[];
      const title=sessionWorkspacePrimaryLabel(session);
      const repo=sessionWorkspaceRepoLabel(session);
      const taskText=String(session&&session.ops_task&&session.ops_task.text||'').trim();
      const sessionTitle=String(session&&session.title||'').trim();
      const epicTitle=String(session&&session.ops_task&&session.ops_task.epicTitle||'').trim();
      if(repo&&repo!==title)parts.push(repo);
      if(taskText&&taskText!==title&&taskText!==repo)parts.push(taskText);
      else if(sessionTitle&&sessionTitle!==title&&sessionTitle!==repo)parts.push(sessionTitle);
      if(epicTitle)parts.push(`Epic ${epicTitle}`);
      return parts.join(' • ')||sessionDisplaySubtitle(session);
    }

    function sessionWorkspaceStatus(session){
      if(session&&session.waitingForApproval)return {label:'Waiting approval',kind:'attention',badge:'Waiting for approval'};
      if(session&&session.waitingForInput)return {label:'Waiting input',kind:'attention',badge:'Waiting for input'};
      if(session&&session.active_stream_id)return {label:'Running',kind:'running',badge:''};
      const runStatus=normalizeRunStatus(session&&session.ops_run&&session.ops_run.status);
      if(runStatus&&runActiveStatusValues.includes(runStatus)){
        return {
          label:runStatusLabel(runStatus),
          kind:runStatusKind(runStatus)==='attention'?'attention':'running',
          badge:'',
        };
      }
      return {label:'Open',kind:'open',badge:''};
    }

    function sessionWorkspaceMeta(session){
      const parts=[];
      const waitingSince=session&&session.waitingSince;
      const lastOutputAt=session&&session.lastOutputAt;
      const lastActivityAt=session&&session.lastActivityAt||session&&session.updated_at||session&&session.created_at;
      if(session&&session.waitingForApproval){
        parts.push(`Waiting approval${waitingSince?` since ${formatOpsDateTime(waitingSince,'unknown')}`:''}`);
      }else if(session&&session.waitingForInput){
        parts.push(`Waiting for input${waitingSince?` since ${formatOpsDateTime(waitingSince,'unknown')}`:''}`);
      }else{
        parts.push(`Last active ${formatOpsDateTime(lastActivityAt,'unknown')}`);
      }
      if(lastOutputAt)parts.push(`Last output ${formatOpsDateTime(lastOutputAt,'unknown')}`);
      const startedBy=String(session&&session.taskStartedBy&&session.taskStartedBy.label||'').trim();
      if(startedBy)parts.push(`Started by ${startedBy}`);
      return parts.join(' • ');
    }

    function activeProjectSessionsFor(project){
      return projectSessionsFor(project,OPS.sessions);
    }

    function activeUngroupedSessions(){
      return (OPS.sessions||[])
        .filter(session=>!session.archived&&!OPS.projects.some(project=>isSessionForProject(session,project)))
        .sort((a,b)=>(Number(b.updated_at)||0)-(Number(a.updated_at)||0));
    }

    function pendingRequestCountForSessions(sessions){
      return (sessions||[]).reduce((total,session)=>total+Number(session&&session.ops_pending_request_count||0),0);
    }

    function sessionWorkspaceGroups(){
      const hasExplicitGroups=!!(OPS.sessionGroups&&Array.isArray(OPS.sessionGroups.groups));
      const explicit=hasExplicitGroups?OPS.sessionGroups.groups:[];
      const explicitSections=explicit.filter(group=>String(group&&group.groupType||'activity').trim().toLowerCase()==='activity');
      const legacyGroupedSessions=explicit
        .filter(group=>String(group&&group.groupType||'').trim().toLowerCase()!=='activity')
        .flatMap(group=>Array.isArray(group&&group.sessions)?group.sessions:[]);
      const sourceUngrouped=hasExplicitGroups
        ? [...legacyGroupedSessions,...(Array.isArray(OPS.sessionGroups&&OPS.sessionGroups.ungrouped)?OPS.sessionGroups.ungrouped:[])]
        : (OPS.sessions||[]).filter(session=>session&&!session.archived);
      const sessionSortKey=session=>Math.max(
        Number(session&&session.lastActivityAt)||0,
        Number(session&&session.lastOutputAt)||0,
        Number(session&&session.updated_at)||0,
        Number(session&&session.created_at)||0,
      );
      const sections=(explicitSections||[]).map((group,index)=>{
        const sessions=canonicalTaskSessions(Array.isArray(group&&group.sessions)?group.sessions:[]).sort((left,right)=>sessionSortKey(right)-sessionSortKey(left));
        return {
          ...group,
          key:String(group&&group.key||group&&group.groupId||`group:${index}`),
          groupType:String(group&&group.groupType||'activity'),
          sessions,
          sessionCount:Number(group&&group.sessionCount)||sessions.length,
          activeCount:Number(group&&group.activeCount)||sessions.length,
          pendingRequestCount:Number(group&&group.pendingRequestCount)||pendingRequestCountForSessions(sessions),
          waitingCount:Number(group&&group.waitingCount)||sessions.filter(session=>session&&(session.waitingForInput||session.waitingForApproval)).length,
          latestUpdatedAt:Number(group&&group.latestUpdatedAt)||Math.max(0,...sessions.map(session=>sessionSortKey(session))),
          isUngrouped:false,
        };
      });
      const ungrouped=canonicalTaskSessions(sourceUngrouped).sort((left,right)=>sessionSortKey(right)-sessionSortKey(left));
      if(ungrouped.length){
        sections.push({
          key:'ungrouped',
          groupType:'ungrouped',
          label:'Ungrouped',
          sessions:ungrouped,
          sessionCount:ungrouped.length,
          activeCount:ungrouped.length,
          pendingRequestCount:pendingRequestCountForSessions(ungrouped),
          waitingCount:ungrouped.filter(session=>session&&(session.waitingForInput||session.waitingForApproval)).length,
          latestUpdatedAt:Math.max(0,...ungrouped.map(session=>sessionSortKey(session))),
          isUngrouped:true,
        });
      }
      syncSessionGroupState(sections);
      return sections;
    }

    function rememberQuickTaskFocus(){
      const active=documentRef&&documentRef.activeElement;
      if(!active||typeof active.closest!=='function'){
        OPS.quickTaskFocusedField='';
        OPS.quickTaskSelectionStart=null;
        OPS.quickTaskSelectionEnd=null;
        return;
      }
      const field=active.closest('[data-ops-quick-field]');
      if(!field||!root()||!root().contains(field)){
        OPS.quickTaskFocusedField='';
        OPS.quickTaskSelectionStart=null;
        OPS.quickTaskSelectionEnd=null;
        return;
      }
      OPS.quickTaskFocusedField=field.dataset.opsQuickField||'';
      OPS.quickTaskSelectionStart=typeof field.selectionStart==='number'?field.selectionStart:null;
      OPS.quickTaskSelectionEnd=typeof field.selectionEnd==='number'?field.selectionEnd:null;
    }

    function restoreQuickTaskFocus(){
      if(!OPS.quickTaskFocusedField)return;
      const field=root()&&root().querySelector(`[data-ops-quick-field="${OPS.quickTaskFocusedField}"]`);
      if(!field||field.disabled)return;
      requestAnimationFrameRef(()=>{
        if(!root()||!root().contains(field)||field.disabled)return;
        field.focus({preventScroll:true});
        if(typeof field.setSelectionRange==='function'&&OPS.quickTaskFocusedField==='text'){
          const start=typeof OPS.quickTaskSelectionStart==='number'?OPS.quickTaskSelectionStart:field.value.length;
          const end=typeof OPS.quickTaskSelectionEnd==='number'?OPS.quickTaskSelectionEnd:start;
          field.setSelectionRange(start,end);
        }
      });
    }

    function renderQuickTaskImageList(){
      const images=Array.isArray(OPS.quickTaskImages)?OPS.quickTaskImages:[];
      if(!images.length)return '';
      return `
        <div class="ops-quick-task-images" aria-label="Quick task screenshots">
          ${images.map(entry=>{
            const file=entry&&entry.file;
            const label=taskImageLabel(file&&file.name||'Image');
            const preview=String(entry&&entry.previewUrl||'').trim();
            return `
              <div class="ops-quick-task-image">
                ${preview?`<img src="${esc(preview)}" alt="">`:`<div class="ops-quick-task-image-fallback">${svg.folder}</div>`}
                <span title="${esc(String(file&&file.name||label))}">${esc(label)}</span>
                <button class="ops-icon-btn" type="button" data-ops-action="remove-quick-task-image" data-quick-task-image-id="${esc(entry&&entry.id||'')}" title="Remove screenshot">${svg.close}</button>
              </div>
            `;
          }).join('')}
        </div>
      `;
    }

    function renderSessionWorkspaceActions(group,options){
      const project=sessionDisplayProject(group);
      const settings=options||{};
      if(!project||!project.id)return '';
      return `
        <div class="ops-session-group-actions">
          <button class="ops-btn" type="button" data-ops-action="new-chat" data-project-id="${esc(project.id)}">${svg.chat}<span>Chat</span></button>
          ${settings.showProjectLink===false?'':`<button class="ops-btn" type="button" data-ops-action="open-project" data-project-id="${esc(project.id)}"><span>Project</span></button>`}
          ${renderProjectGitQuickAction(project)}
          ${renderProjectPlayQuickAction(project)}
          ${renderProjectActivityQuickAction(project)}
        </div>
      `;
    }

    function renderSessionWorkspaceRow(session,project){
      const linkedProject=project&&project.id?project:sessionWorkspaceProject(session);
      const status=sessionWorkspaceStatus(session);
      const title=sessionWorkspacePrimaryLabel(session);
      const subtitle=sessionWorkspaceSubtitle(session);
      const repo=sessionWorkspaceRepoLabel(session);
      const style=sessionAccentStyle(session,0,'ops-session-row');
      return `
        <div class="ops-session ${esc(status.kind)}" ${style?`style="${esc(style)}"`:''}>
          <div class="ops-session-main">
            <div class="ops-session-title-row">
              <span class="ops-session-status ${esc(status.kind)}">${esc(status.label)}</span>
              <span class="ops-session-title">${esc(title)}</span>
              ${repo&&repo!==title?`<span class="ops-session-repo">${esc(repo)}</span>`:''}
            </div>
            ${subtitle?`<div class="ops-session-subtitle">${esc(subtitle)}</div>`:''}
            <div class="ops-session-meta">
              <span>${esc(sessionWorkspaceMeta(session))}</span>
              ${status.badge?`<span>${esc(status.badge)}</span>`:''}
            </div>
          </div>
          <div class="ops-session-actions">
            <button class="ops-btn" type="button" data-ops-action="open-session" data-session-key="${esc(sessionRefValue(session))}" ${linkedProject&&linkedProject.id?`data-project-id="${esc(linkedProject.id)}"`:''}>${svg.chat}<span>Open session</span></button>
            <button class="ops-btn danger" type="button" data-ops-action="close-session" data-session-key="${esc(sessionRefValue(session))}" ${linkedProject&&linkedProject.id?`data-project-id="${esc(linkedProject.id)}"`:''}>${svg.close}<span>Close session</span></button>
          </div>
        </div>
      `;
    }

    function renderSessionWorkspaceGroup(group,index){
      const groupKey=sessionGroupKey(group);
      const collapsed=isSessionGroupCollapsed(groupKey);
      const sessions=Array.isArray(group&&group.sessions)?group.sessions:[];
      const waitingCount=Number(group&&group.waitingCount)||sessions.filter(session=>session&&(session.waitingForInput||session.waitingForApproval)).length;
      const title=String(group&&group.label||'Session activity').trim()||'Session activity';
      const context=String(group&&group.contextLabel||'').trim();
      const meta=[
        `${sessions.length} active session${sessions.length===1?'':'s'}`,
        waitingCount?`${waitingCount} waiting`:'',
        Number(group&&group.pendingRequestCount)?`${Number(group&&group.pendingRequestCount)} open request${Number(group&&group.pendingRequestCount)===1?'':'s'}`:'',
      ].filter(Boolean).join(' • ');
      const style=sessionGroupAccentStyle(group,index,'ops-card');
      const rows=sessions.length
        ? sessions.map(session=>renderSessionWorkspaceRow(session,sessionWorkspaceProject(session))).join('')
        : `<div class="ops-project-session-empty">${group&&group.isUngrouped?'No active sessions.':'No active sessions in this group.'}</div>`;
      return `
        <section class="ops-session-group-card ops-session-activity-group ${group&&group.isUngrouped?'ungrouped':''} ${waitingCount?'has-waiting':''} ${collapsed?'collapsed':''}" data-session-group-key="${esc(groupKey)}" ${style?`style="${esc(style)}"`:''}>
          <div class="ops-session-group-header">
            <div class="ops-session-group-main">
              <button class="ops-session-group-toggle" type="button" data-ops-action="toggle-session-group" data-session-group-key="${esc(groupKey)}" aria-expanded="${collapsed?'false':'true'}" title="${collapsed?'Expand sessions':'Collapse sessions'}">
                <span class="ops-session-group-caret" aria-hidden="true">${svg.arrow}</span>
              </button>
              <div class="ops-session-group-title-block">
                <div class="ops-session-group-title-line">
                  <span class="ops-session-group-title">${esc(title)}</span>
                  ${group&&group.isUngrouped?'<span class="ops-session-group-badge neutral">Sessions</span>':''}
                </div>
                ${context?`<div class="ops-session-group-context">${esc(context)}</div>`:''}
                <div class="ops-session-group-meta">${esc(meta)}</div>
              </div>
            </div>
          </div>
          <div class="ops-project-sessions">
            ${rows}
          </div>
        </section>
      `;
    }

    function renderHomeSessionOverview(){
      if(OPS.loading)return '<div class="ops-empty">Loading sessions...</div>';
      const groups=sessionWorkspaceGroups();
      if(!groups.length)return '<div class="ops-empty">No active sessions.</div>';
      return `<div class="ops-home-project-list">${groups.map((group,index)=>renderSessionWorkspaceGroup(group,index)).join('')}</div>`;
    }

    function renderProjectSessionRows(project,sessionsOverride){
      const sessions=Array.isArray(sessionsOverride)?sessionsOverride:projectSessionsFor(project,OPS.sessions);
      const rows=sessions.length?sessions.map(session=>renderSessionWorkspaceRow(session,project)).join(''):`<div class="ops-project-session-empty">No active sessions for this project.</div>`;
      return `
        <div class="ops-project-sessions">
          ${rows}
        </div>
      `;
    }

    function renderProjectSessionRow(project,session){
      return renderSessionWorkspaceRow(session,project);
    }

    function renderGenericSessionRow(session){
      return renderSessionWorkspaceRow(session,null);
    }

    function renderHome(){
      setDashboardTopbar('Dashboard','');
      const el=root();
      if(!el)return;
      rememberQuickTaskFocus();
      const selectedProjectId=normalizeQuickTaskProjectSelection();
      const projectOptions=OPS.projects.length
        ? OPS.projects.map(project=>`<option value="${esc(project.id)}" ${project.id===selectedProjectId?'selected':''}>${esc(formatQuickTaskProjectOptionLabel(project))}</option>`).join('')
        : '<option value="">No projects available</option>';
      const quickTaskDisabled=OPS.loading||OPS.quickTaskBusy||OPS.quickTaskDictationActive||OPS.quickTaskDictationBusy||!selectedProjectId;
      const quickTaskAttachDisabled=OPS.loading||OPS.quickTaskBusy||!selectedProjectId;
      const quickTaskStatus=OPS.quickTaskStatus
        ? `<div class="ops-status ${esc(OPS.quickTaskStatusKind||'info')}">${esc(OPS.quickTaskStatus)}</div>`
        : '';
      const quickTaskMicState=quickTaskMicButtonState();
      const quickTaskMicStatus=OPS.quickTaskDictationStatus
        ? `<div class="task-mic-status ${esc(OPS.quickTaskDictationStatusKind||'info')}">${esc(OPS.quickTaskDictationStatus)}</div>`
        : '';
      const quickTaskImages=renderQuickTaskImageList();
      const notifications=renderNotifications();
      const sessionOverview=renderHomeSessionOverview();
      const autoPolicy=normalizedAutoApprovalPolicy();
      const notificationsBusy=!!OPS.notificationBusy;
      el.innerHTML=`
        <div class="ops-dashboard ops-home-dashboard">
          <div class="ops-home-top">
            <button class="ops-home-projects-btn" type="button" data-ops-action="open-projects">
              ${svg.folder}
              <span>Projects</span>
            </button>
            <button class="ops-btn" type="button" data-ops-action="refresh-home">${svg.refresh}<span>Refresh</span></button>
          </div>
          <section class="ops-panel ops-notifications-panel">
            <div class="ops-panel-header">
              <div>
                <h2>Notifications</h2>
                <span>Sessions that need input or have finished.</span>
              </div>
              <div class="ops-notification-diagnostics-actions">
                <button class="ops-btn" type="button" data-ops-action="toggle-auto-approval-policy" ${notificationsBusy?'disabled':''}>${autoPolicy.enabled?svg.check:svg.close}<span>${autoPolicy.enabled?'Auto-approve on':'Auto-approve off'}</span></button>
                <button class="ops-btn" type="button" data-ops-action="refresh-notification-diagnostics" ${notificationsBusy?'disabled':''}>${svg.refresh}<span>Refresh</span></button>
              </div>
            </div>
            ${notifications}
          </section>
          <section class="ops-panel ops-quick-task-panel">
            <div class="ops-panel-header">
              <div>
                <h2>Quick task runner</h2>
                <span>Create the task under the Quick tasks epic and start it immediately.</span>
              </div>
            </div>
            <form class="ops-quick-task-form" data-ops-submit="quick-task">
              <label>
                <span>Project</span>
                <select name="projectId" data-ops-quick-field="projectId" ${OPS.loading||OPS.quickTaskBusy?'disabled':''}>${projectOptions}</select>
              </label>
              <label class="wide">
                <span>Task</span>
                <textarea name="text" data-ops-quick-field="text" rows="3" required ${quickTaskDisabled?'disabled':''} placeholder="${OPS.projects.length?'Describe the task you want Codex to execute...':'Create a project first to use quick tasks.'}">${esc(OPS.quickTaskText)}</textarea>
              </label>
              <div class="ops-quick-task-actions">
                <div class="ops-quick-task-secondary-actions">
                  <button class="ops-btn task-mic-btn ${quickTaskMicState.listening?'listening':''}" type="button" data-ops-action="toggle-quick-task-dictation" ${quickTaskMicState.disabled?'disabled':''} aria-pressed="${quickTaskMicState.listening?'true':'false'}" title="${esc(quickTaskMicState.title)}">${svg.chat}<span>${esc(quickTaskMicState.label)}</span></button>
                  <button class="ops-btn" type="button" data-ops-action="attach-quick-task-images" ${quickTaskAttachDisabled?'disabled':''}>${svg.folder}<span>Attach screenshots</span></button>
                </div>
                <button class="ops-btn primary" type="submit" ${quickTaskDisabled?'disabled':''}>${svg.play}<span>${OPS.quickTaskBusy?'Creating...':'Create & run'}</span></button>
              </div>
              <input id="opsQuickTaskImagesInput" type="file" accept="image/*" multiple hidden data-ops-quick-field="images">
            </form>
            ${quickTaskImages}
            ${quickTaskMicStatus}
            ${quickTaskStatus}
          </section>
          <section class="ops-panel ops-session-overview-panel">
            <div class="ops-panel-header">
              <div>
                <h2>Active sessions</h2>
                <span>Session activity, state, and the next action from one place.</span>
              </div>
            </div>
            ${sessionOverview}
          </section>
        </div>
      `;
      restoreQuickTaskFocus();
    }

    async function loadDashboardHome(){
      setBusy(true);
      try{
        await Promise.all([
          loadProjects(),
          loadNotifications(),
          loadOpsRuns(),
          loadNotificationDiagnostics({render:false}).catch(()=>null),
        ]);
        normalizeQuickTaskProjectSelection();
      }catch(err){
        OPS.quickTaskStatus=err&&err.message?err.message:'Unable to load dashboard data.';
        OPS.quickTaskStatusKind='error';
        showError(err);
      }finally{
        setBusy(false);
        if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home')renderHome();
      }
    }

    async function handleHomeAction(action,btn){
      if(action==='refresh-home')return await loadDashboardHome();
      if(action==='attach-quick-task-images'){
        const input=root()&&root().querySelector('#opsQuickTaskImagesInput');
        if(input&&!input.disabled)input.click();
        return null;
      }
      if(action==='remove-quick-task-image'){
        removeQuickTaskImage(btn&&btn.dataset&&btn.dataset.quickTaskImageId);
        if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home')renderHome();
        return null;
      }
      if(action==='toggle-quick-task-dictation'){
        if(OPS.quickTaskDictationActive)return stopQuickTaskDictation();
        return await startQuickTaskDictation();
      }
      if(action==='toggle-session-group'){
        setSessionGroupCollapsed(btn&&btn.dataset&&btn.dataset.sessionGroupKey,!isSessionGroupCollapsed(btn&&btn.dataset&&btn.dataset.sessionGroupKey));
        return renderCurrentOpsView();
      }
      return false;
    }

    function handleQuickTaskField(event){
      const field=event.target.closest('[data-ops-quick-field]');
      if(!field||!root()||!root().contains(field))return false;
      if(field.dataset.opsQuickField==='projectId'){
        if(OPS.quickTaskDictationActive)stopQuickTaskDictation({updateStatus:false,discard:true});
        OPS.quickTaskProjectId=field.value;
      }
      if(field.dataset.opsQuickField==='text')OPS.quickTaskText=field.value;
      if(field.dataset.opsQuickField==='images'){
        addQuickTaskImages(field.files);
        field.value='';
        if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home')renderHome();
      }
      return true;
    }

    return {
      formatQuickTaskProjectOptionLabel,
      clearQuickTaskImages,
      stopQuickTaskDictation,
      renderHome,
      loadDashboardHome,
      normalizeQuickTaskProjectSelection,
      activeProjectSessionsFor,
      activeUngroupedSessions,
      pendingRequestCountForSessions,
      renderSessionWorkspaceActions,
      renderSessionWorkspaceRow,
      renderHomeSessionOverview,
      renderProjectSessionRows,
      renderProjectSessionRow,
      renderGenericSessionRow,
      handleHomeAction,
      handleQuickTaskField,
    };
  }

  window.HermesOpsModules.home={bindDashboard};
})();

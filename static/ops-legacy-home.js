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
    const openProjectDetail=ctx&&ctx.openProjectDetail;
    const createQuickTask=ctx&&ctx.createQuickTask;
    const executeReadyTasksWithAi=ctx&&ctx.executeReadyTasksWithAi;
    const loadNotifications=ctx&&ctx.loadNotifications;
    const loadOpsRuns=ctx&&ctx.loadOpsRuns;
    const loadNotificationDiagnostics=ctx&&ctx.loadNotificationDiagnostics;
    const openOpsSession=ctx&&ctx.openOpsSession;
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
    const playStatusFor=ctx&&ctx.playStatusFor;
    const sessionAccentStyle=ctx&&ctx.sessionAccentStyle;
    const sessionGroupAccentStyle=ctx&&ctx.sessionGroupAccentStyle;
    const sessionRefValue=ctx&&ctx.sessionRefValue;
    const canonicalTaskSessions=ctx&&ctx.canonicalTaskSessions;
    const projectSessionsFor=ctx&&ctx.projectSessionsFor;
    const isSessionForProject=ctx&&ctx.isSessionForProject;
    const taskImageLabel=ctx&&ctx.taskImageLabel;
    const writeStoredJson=ctx&&ctx.writeStoredJson;
    const sessionActivityStorageKey=ctx&&ctx.sessionActivityStorageKey;
    const navigatorRef=ctx&&ctx.navigatorRef;
    const windowRef=ctx&&ctx.windowRef;
    const documentRef=ctx&&ctx.documentRef;
    const URLRef=ctx&&ctx.URLRef;
    const MediaRecorderRef=ctx&&ctx.MediaRecorderRef;
    const FileRef=ctx&&ctx.FileRef;
    const showPromptDialog=ctx&&ctx.showPromptDialog;
    const showConfirmDialog=ctx&&ctx.showConfirmDialog;
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
      || typeof createQuickTask!=='function'
      || typeof executeReadyTasksWithAi!=='function'
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
      || typeof showPromptDialog!=='function'
      || typeof showConfirmDialog!=='function'
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

    function sessionActivityEntries(){
      return Array.isArray(OPS.sessionActivity)?OPS.sessionActivity:[];
    }

    function sessionActivityGroups(){
      return Array.isArray(OPS.sessionActivityGroups)?OPS.sessionActivityGroups:[];
    }

    function sessionActivityGroupCollapseKey(group){
      if(group&&group.isUngrouped)return '__ungrouped__';
      return String(group&&group.id||'').trim();
    }

    function isSessionActivityGroupCollapsed(group){
      const groupKey=sessionActivityGroupCollapseKey(group);
      return !!(groupKey&&OPS.sessionActivityCollapsed&&OPS.sessionActivityCollapsed[groupKey]);
    }

    function setSessionActivityGroupCollapsed(groupKey,collapsed){
      const normalizedKey=String(groupKey||'').trim();
      if(!normalizedKey)return;
      OPS.sessionActivityInitialized={...(OPS.sessionActivityInitialized||{}),[normalizedKey]:true};
      OPS.sessionActivityCollapsed={...(OPS.sessionActivityCollapsed||{})};
      if(collapsed)OPS.sessionActivityCollapsed[normalizedKey]=true;
      else delete OPS.sessionActivityCollapsed[normalizedKey];
      writeStoredJson(sessionActivityStorageKey,OPS.sessionActivityCollapsed);
    }

    function syncSessionActivityCollapsedGroups(groups){
      const validKeys=(groups||[])
        .map(group=>sessionActivityGroupCollapseKey(group))
        .filter(Boolean);
      const validKeySet=new Set(validKeys);
      const nextCollapsed={};
      const nextInitialized={};
      validKeys.forEach(groupKey=>{
        const known=!!(OPS.sessionActivityInitialized&&OPS.sessionActivityInitialized[groupKey]);
        if(known&&OPS.sessionActivityCollapsed&&OPS.sessionActivityCollapsed[groupKey]){
          nextCollapsed[groupKey]=true;
        }
        if(!known){
          nextCollapsed[groupKey]=true;
        }
        nextInitialized[groupKey]=true;
      });
      OPS.sessionActivityCollapsed=nextCollapsed;
      OPS.sessionActivityInitialized=nextInitialized;
      writeStoredJson(sessionActivityStorageKey,OPS.sessionActivityCollapsed);
    }

    function sessionActivityStatus(session){
      const status=session&&session.activityStatus;
      const key=String(status&&status.key||'').trim().toLowerCase();
      const toneClass=String(status&&status.toneClass||key||'idle').trim().toLowerCase()||'idle';
      const labelText=String(status&&status.labelText||'Quiet').trim()||'Quiet';
      const title=String(status&&status.title||'No recent Codex activity detected for this session.').trim()
        || 'No recent Codex activity detected for this session.';
      return {key:key||'idle',toneClass,labelText,title};
    }

    function sessionActivitySortKey(session){
      return Math.max(
        Number(session&&session.lastOutputAt)||0,
        Number(session&&session.lastActive)||0,
        0,
      );
    }

    function formatSessionActivityBranchLabel(session){
      const direct=String(session&&session.branchLabel||session&&session.branch||'').trim();
      if(direct)return direct;
      const projectId=String(session&&session.projectId||session&&session.ops_project_id||'').trim();
      const project=projectId?findProject(projectId):null;
      return project?String(projectBranchLabel(project)||'').trim():'';
    }

    function formatSessionActivityTitle(session){
      const branchLabel=formatSessionActivityBranchLabel(session);
      if(branchLabel)return branchLabel;
      return String(
        session&&(
          session.label
          || session.taskText
          || session.projectName
          || session.title
          || 'Untitled'
        )||'Untitled'
      ).trim()||'Untitled';
    }

    function formatSessionActivityRepoLabel(session){
      return String(session&&session.repoLabel||session&&session.projectName||'').trim();
    }

    function sessionActivityTaskText(session){
      return String(
        session&&(
          session.taskText
          || (session.ops_task&&session.ops_task.text)
          || ''
        )||''
      ).replace(/\s+/g,' ').trim();
    }

    function formatSessionActivityTaskPreview(session){
      const text=sessionActivityTaskText(session);
      if(!text)return '';
      const limit=140;
      if(text.length<=limit)return text;
      return `${text.slice(0,limit-1).trimEnd()}…`;
    }

    function sessionActivityProjectPlayState(session){
      if(typeof playStatusFor!=='function')return null;
      const projectId=String(session&&session.projectId||session&&session.ops_project_id||'').trim();
      if(!projectId)return null;
      const status=playStatusFor(projectId);
      if(!status)return null;
      const configured=!!(status.configured===true||status.configAvailable===true||status.configExists===true);
      if(!configured)return null;
      const normalizedStatus=String(status.status||'idle').trim().toLowerCase()||'idle';
      if(normalizedStatus==='queued'){
        return {key:'queued',label:'Queued',stateClass:'state-queued',title:'Project Play is queued behind another build.'};
      }
      if(normalizedStatus==='building'||normalizedStatus==='starting'){
        return {
          key:'building',
          label:'Building',
          stateClass:'state-building',
          title:normalizedStatus==='starting'
            ? 'Project Play build passed and the app is starting.'
            : 'Project Play build is running.',
        };
      }
      if(normalizedStatus==='ready'&&status.ready===true){
        return {key:'play',label:'Play',stateClass:'state-ready',title:'Project Play is ready.'};
      }
      if(normalizedStatus==='failed'){
        return {key:'failed',label:'Failed',stateClass:'state-failed',title:status.error||'Project Play failed.'};
      }
      return {key:'idle',label:'Idle',stateClass:'state-idle',title:'Project Play is idle.'};
    }

    function formatSessionActivitySummary(entries,groups,refreshedLabel){
      const counts={
        active:0,
        connecting:0,
        waiting:0,
        approval:0,
        degraded:0,
        done:0,
        prompt:0,
        idle:0,
        readableOutputPending:0,
      };
      (entries||[]).forEach(session=>{
        const state=sessionActivityStatus(session);
        if(Object.prototype.hasOwnProperty.call(counts,state.key))counts[state.key]+=1;
        if(session&&session.readableOutputPending)counts.readableOutputPending+=1;
      });
      const parts=[];
      if(counts.active>0)parts.push(`${counts.active} working`);
      if(counts.connecting>0)parts.push(`${counts.connecting} connecting`);
      if(counts.waiting>0)parts.push(`${counts.waiting} waiting`);
      if(counts.approval>0)parts.push(`${counts.approval} approval`);
      if(counts.degraded>0)parts.push(`${counts.degraded} degraded`);
      if(counts.prompt>0)parts.push(`${counts.prompt} at prompt`);
      if(counts.done>0)parts.push(`${counts.done} done`);
      if(counts.idle>0)parts.push(`${counts.idle} quiet`);
      if(counts.readableOutputPending>0){
        parts.push(`${counts.readableOutputPending} unread output${counts.readableOutputPending===1?'':'s'}`);
      }
      const groupCount=Array.isArray(groups)?groups.length:0;
      const summaryParts=parts.length?` ${parts.join(' • ')}.`:'';
      const groupPart=groupCount?` ${groupCount} group${groupCount===1?'':'s'}.`:'';
      const refreshedPart=refreshedLabel?` Last checked ${refreshedLabel}.`:'';
      return `${entries.length} active session${entries.length===1?'':'s'}.${groupPart}${summaryParts}${refreshedPart}`;
    }

    function buildSessionActivitySections(entries,groups){
      const normalizedGroups=Array.isArray(groups)?groups:[];
      const sections=normalizedGroups.map(group=>({
        ...group,
        sessions:[],
        isUngrouped:false,
      }));
      const sectionsById=new Map(sections.map(group=>[String(group&&group.id||'').trim(),group]));
      const ungrouped={
        id:'',
        label:'Ungrouped',
        position:Number.MAX_SAFE_INTEGER,
        sessions:[],
        isUngrouped:true,
      };
      (entries||[]).forEach(session=>{
        const target=session&&session.groupId?sectionsById.get(String(session.groupId||'').trim()):null;
        if(target){
          target.sessions.push(session);
          return;
        }
        ungrouped.sessions.push(session);
      });
      sections.forEach(group=>{
        group.sessions=(group.sessions||[]).slice().sort((left,right)=>sessionActivitySortKey(right)-sessionActivitySortKey(left));
      });
      ungrouped.sessions=(ungrouped.sessions||[]).slice().sort((left,right)=>sessionActivitySortKey(right)-sessionActivitySortKey(left));
      if(ungrouped.sessions.length||sections.length===0)sections.push(ungrouped);
      syncSessionActivityCollapsedGroups(sections);
      return sections;
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
      const sections=buildSessionActivitySections(sessionActivityEntries(),sessionActivityGroups());
      const ungrouped=sections.find(group=>group&&group.isUngrouped);
      return Array.isArray(ungrouped&&ungrouped.sessions)?ungrouped.sessions:[];
    }

    function pendingRequestCountForSessions(sessions){
      return (sessions||[]).reduce((total,session)=>{
        const state=sessionActivityStatus(session);
        return total+((state.key==='waiting'||state.key==='approval')?1:0);
      },0);
    }

    function menuTargetProject(){
      const quickProjectId=normalizeQuickTaskProjectSelection();
      if(quickProjectId){
        const quickProject=findProject(quickProjectId);
        if(quickProject&&quickProject.id)return quickProject;
      }
      if(OPS.currentProject&&OPS.currentProject.id)return OPS.currentProject;
      const sessionProjectId=String((sessionActivityEntries().find(session=>String(session&&session.projectId||'').trim())||{}).projectId||'').trim();
      if(sessionProjectId){
        const sessionProject=findProject(sessionProjectId);
        if(sessionProject&&sessionProject.id)return sessionProject;
      }
      return Array.isArray(OPS.projects)&&OPS.projects.length?OPS.projects[0]:null;
    }

    function menuLatestSession(project){
      const targetProjectId=String(project&&project.id||'').trim();
      const entries=sessionActivityEntries().slice().sort((left,right)=>sessionActivitySortKey(right)-sessionActivitySortKey(left));
      if(targetProjectId){
        const matching=entries.find(session=>String(session&&session.projectId||'').trim()===targetProjectId);
        if(matching)return matching;
      }
      return entries[0]||null;
    }

    function shellUrl(path){
      const rel=String(path||'').trim();
      const base=(documentRef&&documentRef.baseURI)
        || (windowRef&&windowRef.location&&windowRef.location.href)
        || (typeof location!=='undefined' && location.href)
        || '';
      if(!base)return rel;
      try{return new URL(rel, base).href;}catch(_error){return rel;}
    }

    function mainAppUrl(panel){
      const rel=panel&&panel!=='chat'
        ? `index.html?panel=${encodeURIComponent(panel)}`
        : 'index.html';
      return shellUrl(rel);
    }

    async function switchMainPanel(panel){
      if(windowRef&&typeof windowRef.switchPanel==='function'){
        await windowRef.switchPanel(panel);
        if(typeof windowRef.closeOpsDashboard==='function')windowRef.closeOpsDashboard();
        return true;
      }
      if(windowRef&&windowRef.location&&typeof windowRef.location.assign==='function'){
        windowRef.location.assign(mainAppUrl(panel));
        return true;
      }
      return false;
    }

    async function openMainSession(session,options){
      const sessionKey=sessionActionRefValue(session);
      if(!sessionKey||typeof openOpsSession!=='function')return false;
      await openOpsSession(sessionKey);
      if(options&&options.openWorkspace&&windowRef&&typeof windowRef.toggleWorkspacePanel==='function'){
        windowRef.toggleWorkspacePanel(true);
      }
      return true;
    }

    async function openDeploymentDestination(){
      const project=menuTargetProject();
      if(project&&project.id&&typeof openProjectDetail==='function'){
        return openProjectDetail(project.id);
      }
      OPS.view='projects';
      OPS.currentProject=null;
      OPS.taskData=null;
      OPS.showCreate=false;
      setDashboardTopbar('Projects','');
      await loadProjects();
      return renderCurrentOpsView();
    }

    async function openFilesDestination(){
      const project=menuTargetProject();
      const session=menuLatestSession(project);
      if(await openMainSession(session,{openWorkspace:true}))return true;
      return switchMainPanel('workspaces');
    }

    async function openTerminalDestination(){
      const project=menuTargetProject();
      const session=menuLatestSession(project);
      if(await openMainSession(session))return true;
      return switchMainPanel('chat');
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

    function activeQuickTaskField(){
      const active=documentRef&&documentRef.activeElement;
      if(!active||typeof active.closest!=='function')return null;
      const field=active.closest('[data-ops-quick-field]');
      if(!field||!root()||!root().contains(field))return null;
      return field;
    }

    function isQuickTaskProjectPickerActive(){
      const field=activeQuickTaskField();
      return String(field&&field.dataset&&field.dataset.opsQuickField||'').trim()==='projectId';
    }

    function isQuickTaskFieldActive(){
      return !!activeQuickTaskField();
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

    function sessionActionRefValue(sessionLike){
      if(!sessionLike)return '';
      if(typeof sessionLike==='string')return String(sessionLike).trim();
      const direct=String(sessionLike.session_id||sessionLike.sessionId||sessionLike.id||'').trim();
      if(direct)return direct;
      return String(sessionLike.sessionKey||sessionLike.session_key||sessionRefValue(sessionLike)||'').trim();
    }

    function renderSessionWorkspaceRow(session,project){
      const linkedProject=project&&project.id?project:sessionWorkspaceProject(session);
      const status=sessionWorkspaceStatus(session);
      const title=sessionWorkspacePrimaryLabel(session);
      const subtitle=sessionWorkspaceSubtitle(session);
      const repo=sessionWorkspaceRepoLabel(session);
      const style=sessionAccentStyle(session,0,'ops-session-row');
      const sessionKey=sessionActionRefValue(session);
      const rowClass=['ops-session',status.kind,sessionKey?'interactive':''].filter(Boolean).join(' ');
      const rowAttrs=sessionKey
        ? ` tabindex="0" role="button" data-ops-action="open-session" data-session-key="${esc(sessionKey)}" data-ops-session-row="true"${linkedProject&&linkedProject.id?` data-project-id="${esc(linkedProject.id)}"`:''}`
        : '';
      return `
        <div class="${esc(rowClass)}"${rowAttrs} ${style?`style="${esc(style)}"`:''}>
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
            <button class="ops-btn" type="button" data-ops-action="open-session" data-session-key="${esc(sessionKey)}" ${linkedProject&&linkedProject.id?`data-project-id="${esc(linkedProject.id)}"`:''}>${svg.chat}<span>Open session</span></button>
            <button class="ops-btn danger" type="button" data-ops-action="close-session" data-session-key="${esc(sessionKey)}" ${linkedProject&&linkedProject.id?`data-project-id="${esc(linkedProject.id)}"`:''}>${svg.close}<span>Close session</span></button>
          </div>
        </div>
      `;
    }

    function focusSessionActivityGroupInput(){
      const targetGroupId=String(OPS.sessionActivityFocusGroupId||'').trim();
      if(!targetGroupId||!root())return;
      OPS.sessionActivityFocusGroupId='';
      requestAnimationFrameRef(()=>{
        const input=Array.from(root().querySelectorAll('[data-ops-session-group-label="true"]'))
          .find(field=>String(field&&field.dataset&&field.dataset.groupId||'').trim()===targetGroupId);
        if(!input||input.disabled)return;
        input.focus({preventScroll:true});
        if(typeof input.select==='function')input.select();
      });
    }

    function renderSessionActivityControls(session,groups){
      if(!Array.isArray(groups)||!groups.length)return '<div class="menu-session-activity-controls"></div>';
      const sessionKey=sessionActionRefValue(session);
      return `
        <div class="menu-session-activity-controls">
          <label class="menu-session-activity-group-select-wrap" title="Move session between groups.">
            <span class="menu-session-activity-group-select-label">Group</span>
            <select class="menu-session-activity-group-select" data-ops-session-group-select="true" data-session-key="${esc(sessionKey)}">
              <option value="">Ungrouped</option>
              ${groups.map(group=>`<option value="${esc(group.id)}" ${String(session&&session.groupId||'').trim()===String(group.id||'').trim()?'selected':''}>${esc(String(group&&group.label||''))}</option>`).join('')}
            </select>
          </label>
        </div>
      `;
    }

    function renderSessionActivityItemActions(session){
      const sessionKey=sessionActionRefValue(session);
      if(!sessionKey)return '';
      const projectId=String(session&&session.projectId||session&&session.ops_project_id||'').trim();
      return `
        <div class="menu-session-activity-actions">
          <button class="menu-action-btn danger small" type="button" data-ops-action="close-session" data-session-key="${esc(sessionKey)}" ${projectId?`data-project-id="${esc(projectId)}"`:''} title="Close this active session.">${svg.close}<span>Close session</span></button>
        </div>
      `;
    }

    function renderSessionActivityItem(session,groups){
      const state=sessionActivityStatus(session);
      const title=formatSessionActivityTitle(session);
      const repoLabel=formatSessionActivityRepoLabel(session);
      const taskText=sessionActivityTaskText(session);
      const taskPreview=formatSessionActivityTaskPreview(session);
      const sessionKey=sessionActionRefValue(session);
      const hasReadableOutput=session&&session.readableOutputPending===true;
      const projectPlayState=sessionActivityProjectPlayState(session);
      return `
        <div class="menu-session-activity-item interactive ${hasReadableOutput?'has-readable-output':''}" tabindex="0" role="button" data-ops-action="open-session" data-session-key="${esc(sessionKey)}" data-ops-session-activity-item="true" data-readable-output-pending="${hasReadableOutput?'true':'false'}" data-project-play-state="${esc(projectPlayState&&projectPlayState.key||'')}">
          <div class="menu-session-activity-main">
            <div class="menu-session-activity-heading">
              <div class="menu-session-activity-copy">
                <div class="menu-session-activity-title-line">
                  <div class="menu-session-activity-title">${esc(title)}</div>
                  <span class="menu-session-activity-state state-${esc(state.toneClass||'idle')}" title="${esc(state.title||'')}">${esc(state.labelText||'Quiet')}</span>
                  ${projectPlayState?`<span class="menu-session-activity-badge project-play play-status-badge ${esc(projectPlayState.stateClass)}" title="${esc(projectPlayState.title)}">${esc(projectPlayState.label)}</span>`:''}
                  ${hasReadableOutput?'<span class="menu-session-activity-badge readable-output">Unread output</span>':''}
                </div>
                ${repoLabel&&repoLabel!==title?`<div class="menu-session-activity-repo">${esc(repoLabel)}</div>`:''}
                ${taskPreview?`<div class="menu-session-activity-task-preview" title="${esc(taskText)}"><span class="menu-session-activity-task-label">Task</span><span>${esc(taskPreview)}</span></div>`:''}
              </div>
              ${renderSessionActivityControls(session,groups)}
            </div>
          </div>
          ${renderSessionActivityItemActions(session)}
        </div>
      `;
    }

    function renderSessionActivityGroupSection(group,index,groups){
      const sessions=Array.isArray(group&&group.sessions)?group.sessions:[];
      const collapsed=isSessionActivityGroupCollapsed(group);
      const groupKey=sessionActivityGroupCollapseKey(group);
      const waitingCount=sessions.filter(session=>{
        const state=sessionActivityStatus(session);
        return state.key==='waiting'||state.key==='approval';
      }).length;
      const readableOutputCount=sessions.filter(session=>session&&session.readableOutputPending).length;
      const style=group&&group.isUngrouped?'':sessionGroupAccentStyle(group,index,'menu-session-activity-group');
      const meta=`${sessions.length} active session${sessions.length===1?'':'s'}${waitingCount?` • ${waitingCount} waiting`:''}${readableOutputCount?` • ${readableOutputCount} unread output${readableOutputCount===1?'':'s'}`:''}`;
      return `
        <section class="menu-session-activity-group ${group&&group.isUngrouped?'ungrouped':''} ${collapsed?'collapsed':''} ${readableOutputCount?'has-readable-output':''}" ${group&&group.isUngrouped?'':`data-group-id="${esc(String(group&&group.id||''))}"`} ${style?`style="${esc(style)}"`:''}>
          <div class="menu-session-activity-group-header">
            <div class="menu-session-activity-group-header-main">
              <button class="menu-session-activity-group-toggle" type="button" data-ops-action="toggle-session-activity-group" data-session-activity-group-key="${esc(groupKey)}" aria-expanded="${collapsed?'false':'true'}" title="${collapsed?'Expand this group.':'Collapse this group.'}">
                <span class="menu-session-activity-group-caret" aria-hidden="true"></span>
                <span class="menu-session-activity-group-toggle-label">${collapsed?'Show':'Hide'}</span>
              </button>
              <div class="menu-session-activity-group-title-wrap">
                ${group&&group.isUngrouped
                  ? `<div class="menu-session-activity-group-title">${esc(String(group&&group.label||'Ungrouped'))}</div>`
                  : `<input type="text" class="menu-session-activity-group-input" data-ops-session-group-label="true" data-group-id="${esc(String(group&&group.id||''))}" data-initial-label="${esc(String(group&&group.label||''))}" value="${esc(String(group&&group.label||''))}" maxlength="80" aria-label="Session group label" title="Rename this session group.">`
                }
                <div class="menu-session-activity-group-meta">${esc(meta)}</div>
              </div>
            </div>
            ${group&&group.isUngrouped?'':`<button class="menu-action-btn secondary small" type="button" data-ops-action="delete-session-activity-group" data-group-id="${esc(String(group&&group.id||''))}" title="Delete this session group and move its sessions back to Ungrouped.">Delete</button>`}
          </div>
          <div class="menu-session-activity-group-sessions">
            ${sessions.length
              ? sessions.map(session=>renderSessionActivityItem(session,groups)).join('')
              : `<div class="menu-session-activity-group-empty">${group&&group.isUngrouped?'No active sessions without a group.':'No active sessions in this group.'}</div>`
            }
          </div>
        </section>
      `;
    }

    function renderHomeSessionOverview(){
      if(OPS.loading&&OPS.sessionActivityBusy&&!sessionActivityEntries().length){
        return '<div class="repo-status">Loading sessions...</div><p class="repo-empty">No active sessions.</p>';
      }
      const entries=sessionActivityEntries();
      const groups=sessionActivityGroups();
      const sections=buildSessionActivitySections(entries,groups);
      const refreshedLabel=OPS.sessionActivityLastRefreshedAt
        ? new Date(OPS.sessionActivityLastRefreshedAt).toLocaleTimeString()
        : '';
      const statusText=OPS.sessionActivityError
        ? String(OPS.sessionActivityError||'').trim()
        : formatSessionActivitySummary(entries,groups,refreshedLabel);
      const statusClass=OPS.sessionActivityError?' error':'';
      const showList=OPS.sessionActivityExpanded!==false;
      return `
        <div class="repo-status${statusText?statusClass:''}${statusText?'':' hidden'}">${esc(statusText||'')}</div>
        ${showList?`<div class="menu-session-activity-list">${sections.map((group,index)=>renderSessionActivityGroupSection(group,index,groups)).join('')}</div>`:''}
        <p class="repo-empty ${showList&&entries.length?'hidden':''}">${OPS.sessionActivityExpanded===false?'':'No active sessions.'}</p>
      `;
    }

    function renderHomeSessionActivityPanelMarkup(sessionOverview){
      const sessionActivityExpanded=OPS.sessionActivityExpanded!==false;
      return `
          <section class="ops-panel repo-panel menu-session-activity-panel ops-session-overview-panel" aria-live="polite" data-ops-home-session-activity-panel="true">
            <div class="menu-notification-header">
              <div class="menu-notification-header-copy">
                <div class="quick-response-title">Active sessions</div>
                <div class="menu-session-activity-header-help">Heartbeat only, plus repo and branch. Group sessions with freeform labels. Refreshes every 5 seconds while this menu is visible.</div>
              </div>
              <div class="menu-notification-header-actions">
                <button class="menu-action-btn secondary small" type="button" data-ops-action="create-session-activity-group" ${OPS.sessionActivityBusy?'disabled':''}>Add group</button>
                <button class="menu-action-btn secondary small" type="button" data-ops-action="refresh-session-activity" ${OPS.sessionActivityBusy?'disabled':''}>${OPS.sessionActivityBusy?'Refreshing...':'Refresh'}</button>
                <button class="menu-action-btn secondary small" type="button" data-ops-action="toggle-session-activity" aria-expanded="${sessionActivityExpanded?'true':'false'}">${sessionActivityExpanded?'Collapse':'Expand'}</button>
              </div>
            </div>
            ${sessionOverview||renderHomeSessionOverview()}
          </section>`;
    }

    function renderHomeSessionActivityPanel(){
      const panel=root()&&root().querySelector('[data-ops-home-session-activity-panel="true"]');
      if(!panel)return false;
      panel.outerHTML=renderHomeSessionActivityPanelMarkup();
      return true;
    }

    function renderProjectSessionRows(project,sessionsOverride){
      const sessions=Array.isArray(sessionsOverride)?sessionsOverride:projectSessionsFor(project,OPS.sessions);
      const count=sessions.length;
      const rows=count?sessions.map(session=>renderSessionWorkspaceRow(session,project)).join(''):`<div class="ops-project-session-empty">No active sessions for this project.</div>`;
      const summary=count
        ? `${count} active session${count===1?'':'s'}`
        : 'No active sessions';
      return `
        <details class="ops-project-sessions" data-ops-project-sessions="${esc(project&&project.id||'')}">
          <summary class="ops-project-sessions-summary">${esc(summary)}</summary>
          <div class="ops-project-sessions-body">
            ${rows}
          </div>
        </details>
      `;
    }

    function renderProjectSessionRow(project,session){
      return renderSessionWorkspaceRow(session,project);
    }

    function renderGenericSessionRow(session){
      return renderSessionWorkspaceRow(session,null);
    }

    function ensureSessionActivityAutoRefresh(){
      if(OPS.sessionActivityAutoRefreshTimer)return;
      OPS.sessionActivityAutoRefreshTimer=windowRef.setInterval(()=>{
        if(!windowRef||!windowRef._opsDashboardOpen||OPS.view!=='home'||OPS.sessionActivityBusy)return;
        void loadSessionActivity();
      },5000);
    }

    async function loadSessionActivity(options){
      const settings=options||{};
      OPS.sessionActivityBusy=true;
      try{
        const payload=await AgentBridgeRef.sessions.activity();
        OPS.sessionActivity=Array.isArray(payload&&payload.sessions)?payload.sessions:[];
        OPS.sessionActivityGroups=Array.isArray(payload&&payload.groups)?payload.groups:[];
        OPS.sessionActivityLastRefreshedAt=Date.now();
        OPS.sessionActivityError='';
      }catch(error){
        OPS.sessionActivityError=error&&error.message?error.message:'Unable to load session activity.';
      }finally{
        OPS.sessionActivityBusy=false;
        if(settings.render!==false&&windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home'){
          if(isQuickTaskFieldActive()){
            OPS.sessionActivityRenderPending=false;
            if(renderHomeSessionActivityPanel())return;
            OPS.sessionActivityRenderPending=true;
            return;
          }
          OPS.sessionActivityRenderPending=false;
          renderHome();
        }
      }
    }

    function renderHome(){
      setDashboardTopbar('Menu','');
      const el=root();
      if(!el)return;
      OPS.sessionActivityRenderPending=false;
      ensureSessionActivityAutoRefresh();
      rememberQuickTaskFocus();
      const selectedProjectId=normalizeQuickTaskProjectSelection();
      const projectOptions=OPS.projects.length
        ? OPS.projects.map(project=>`<option value="${esc(project.id)}" ${project.id===selectedProjectId?'selected':''}>${esc(formatQuickTaskProjectOptionLabel(project))}</option>`).join('')
        : '<option value="">No projects available</option>';
      const quickTaskBusyAction=String(OPS.quickTaskBusyAction||'').trim();
      const quickTaskDisabled=OPS.loading||OPS.quickTaskBusy||OPS.quickTaskDictationActive||OPS.quickTaskDictationBusy||!selectedProjectId;
      const quickTaskAttachDisabled=OPS.loading||OPS.quickTaskBusy||!selectedProjectId;
      const quickTaskExecuteReadyDisabled=OPS.loading||OPS.quickTaskBusy||!selectedProjectId;
      const quickTaskStatusKind=String(OPS.quickTaskStatusKind||'').trim().toLowerCase();
      const quickTaskStatusClass=quickTaskStatusKind==='error'
        ? ' error'
        : (quickTaskStatusKind==='success'?' success':'');
      const quickTaskStatus=OPS.quickTaskStatus
        ? `<div class="repo-status${quickTaskStatusClass}">${esc(OPS.quickTaskStatus)}</div>`
        : '<div class="repo-status hidden"></div>';
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
        <div class="ops-dashboard ops-home-dashboard menu-page-content">
          <h2>Menu</h2>
          <p class="menu-description">Use the navigation buttons below and review active agent notifications.</p>
          <section class="ops-panel repo-panel menu-notification-panel ops-notifications-panel">
            <div class="menu-notification-header">
              <div class="menu-notification-header-copy">
                <div class="quick-response-title">Notifications</div>
                <div class="menu-notification-header-help">Auto-approve routine inline approvals while leaving important requests for manual review.</div>
              </div>
              <div class="menu-notification-header-actions">
                <label class="menu-inline-toggle" for="opsAutoApproveRoutine" data-ops-action="toggle-auto-approval-policy">
                  <input id="opsAutoApproveRoutine" type="checkbox" ${autoPolicy.enabled?'checked':''} ${notificationsBusy?'disabled':''}>
                  <span>Auto-approve routine requests</span>
                </label>
                <button class="menu-action-btn secondary small" type="button" data-ops-action="refresh-notification-diagnostics" ${notificationsBusy?'disabled':''}>Refresh</button>
              </div>
            </div>
            ${notifications}
          </section>
          <section class="ops-panel repo-panel menu-quick-task-panel ops-quick-task-panel">
            <div class="menu-notification-header">
              <div class="menu-notification-header-copy">
                <div class="quick-response-title">Quick task runner</div>
                <div class="menu-notification-header-help">Pick a project, describe the work, and Hermes will create the task under the Quick tasks epic and start Codex on it immediately.</div>
              </div>
            </div>
            <form class="menu-quick-task-form" data-ops-submit="quick-task">
              <label class="tasks-field">
                <span class="tasks-field-label">Project</span>
                <select class="task-select" name="projectId" data-ops-quick-field="projectId" ${OPS.loading||OPS.quickTaskBusy?'disabled':''}>${projectOptions}</select>
              </label>
              <label class="tasks-field">
                <span class="tasks-field-label">Task</span>
                <textarea class="task-input menu-quick-task-input" name="text" data-ops-quick-field="text" rows="3" required ${quickTaskDisabled?'disabled':''} placeholder="${OPS.projects.length?'Describe the task you want Codex to execute...':'Create a project first to use quick tasks.'}">${esc(OPS.quickTaskText)}</textarea>
              </label>
              <label class="menu-inline-toggle" for="opsQuickTaskGoalMode">
                <input id="opsQuickTaskGoalMode" type="checkbox" name="goalMode" value="on" data-ops-quick-field="goalMode" ${OPS.quickTaskGoalMode?'checked':''} ${quickTaskDisabled?'disabled':''}>
                <span>Run as standing /goal</span>
              </label>
              <div class="todo-form-row menu-quick-task-actions">
                <div class="menu-quick-task-secondary-actions">
                  <button class="menu-action-btn secondary small" type="button" data-ops-action="attach-quick-task-images" ${quickTaskAttachDisabled?'disabled':''}>Attach screenshots</button>
                  <button class="task-mic-btn ${quickTaskMicState.listening?'listening':''}" type="button" data-ops-action="toggle-quick-task-dictation" ${quickTaskMicState.disabled?'disabled':''} aria-pressed="${quickTaskMicState.listening?'true':'false'}" title="${esc(quickTaskMicState.title)}">${esc(quickTaskMicState.label)}</button>
                </div>
                <div class="menu-quick-task-primary-actions">
                  <button class="menu-action-btn secondary small" type="button" data-ops-action="create-quick-task" ${quickTaskDisabled?'disabled':''}>${quickTaskBusyAction==='create-only'?'Creating...':'Create'}</button>
                  <button class="task-add-btn" type="submit" ${quickTaskDisabled?'disabled':''}>${quickTaskBusyAction==='create-run'?'Creating...':'Create & run'}</button>
                  <button class="menu-action-btn secondary small" type="button" data-ops-action="execute-ready-tasks" ${quickTaskExecuteReadyDisabled?'disabled':''} title="Ask Codex to execute ready and needs-more-work tasks in sequence.">${quickTaskBusyAction==='execute-ready'?'Starting...':'Execute ready tasks with AI'}</button>
                </div>
              </div>
              <input id="opsQuickTaskImagesInput" type="file" accept="image/*" multiple hidden data-ops-quick-field="images">
            </form>
            ${quickTaskImages}
            ${quickTaskMicStatus}
            ${quickTaskStatus}
          </section>
          ${renderHomeSessionActivityPanelMarkup(sessionOverview)}
          <div class="menu-actions">
            <button class="menu-action-btn" type="button" data-ops-action="open-projects">Projects</button>
            <button class="menu-action-btn" type="button" data-ops-action="view-deployments">View deployments</button>
            <button class="menu-action-btn" type="button" data-ops-action="show-create-project">Create project</button>
            <button class="menu-action-btn" type="button" data-ops-action="view-todos">View todos</button>
            <button class="menu-action-btn" type="button" data-ops-action="view-files">View files</button>
            <button class="menu-action-btn" type="button" data-ops-action="view-settings">Settings</button>
            <button class="menu-action-btn" type="button" data-ops-action="go-recovery">Recovery</button>
            <button class="menu-action-btn secondary" type="button" data-ops-action="back-to-terminal">Back to terminal</button>
          </div>
        </div>
      `;
      restoreQuickTaskFocus();
      focusSessionActivityGroupInput();
    }

    async function loadDashboardHome(){
      const token=(OPS.dashboardHomeLoadToken||0)+1;
      OPS.dashboardHomeLoadToken=token;
      const renderIfCurrent=()=>{
        if(token===OPS.dashboardHomeLoadToken&&windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home')renderHome();
      };
      // Opening the dashboard should not be gated by every diagnostics/feed request.
      // Render cached/empty home immediately, then hydrate critical controls and
      // finally fill secondary panels in the background.
      setBusy(false);
      renderIfCurrent();
      try{
        await Promise.all([
          loadProjects(),
          loadSessionActivity({render:false}),
        ]);
        if(token!==OPS.dashboardHomeLoadToken)return;
        normalizeQuickTaskProjectSelection();
        renderIfCurrent();
      }catch(err){
        if(token!==OPS.dashboardHomeLoadToken)return;
        OPS.quickTaskStatus=err&&err.message?err.message:'Unable to load dashboard data.';
        OPS.quickTaskStatusKind='error';
        showError(err);
        renderIfCurrent();
        return;
      }
      Promise.allSettled([
        loadNotifications(),
        loadOpsRuns(),
        loadNotificationDiagnostics({render:false}).catch(()=>null),
      ]).then(()=>{
        if(token!==OPS.dashboardHomeLoadToken)return;
        setBusy(false);
        renderIfCurrent();
      });
    }

    async function handleHomeAction(action,btn){
      if(action==='refresh-home')return await loadDashboardHome();
      if(action==='show-create-project'){
        OPS.view='projects';
        OPS.currentProject=null;
        OPS.taskData=null;
        OPS.showCreate=true;
        setDashboardTopbar('Projects','');
        await loadProjects();
        return renderCurrentOpsView();
      }
      if(action==='view-deployments')return await openDeploymentDestination();
      if(action==='view-todos')return await switchMainPanel('todos');
      if(action==='view-files')return await openFilesDestination();
      if(action==='view-settings')return await switchMainPanel('settings');
      if(action==='go-recovery'){
        if(windowRef&&windowRef.location&&typeof windowRef.location.assign==='function'){
          windowRef.location.assign(shellUrl('recovery'));
        }
        return null;
      }
      if(action==='back-to-terminal')return await openTerminalDestination();
      if(action==='back-to-hermes'){
        if(windowRef&&windowRef.location&&typeof windowRef.location.assign==='function'){
          windowRef.location.assign(mainAppUrl('chat'));
        }
        return null;
      }
      if(action==='refresh-session-activity')return await loadSessionActivity();
      if(action==='toggle-session-activity'){
        OPS.sessionActivityExpanded=OPS.sessionActivityExpanded===false?true:false;
        return renderCurrentOpsView();
      }
      if(action==='create-session-activity-group'){
        const label=await showPromptDialog({
          title:'Create session group',
          message:'Give this activity group a short label.',
          confirmLabel:'Create',
          placeholder:'New group',
          initialValue:'New group',
        });
        if(label===null)return null;
        const created=await AgentBridgeRef.sessions.createActivityGroup(label);
        OPS.sessionActivityFocusGroupId=String(created&&created.group&&created.group.id||'').trim();
        return await loadSessionActivity();
      }
      if(action==='delete-session-activity-group'){
        const groupId=String(btn&&btn.dataset&&btn.dataset.groupId||'').trim();
        if(!groupId)return null;
        const ok=await showConfirmDialog({
          title:'Delete session group',
          message:'Delete this group? Sessions in it will move back to Ungrouped.',
          confirmLabel:'Delete',
          danger:true,
          focusCancel:true,
        });
        if(!ok)return null;
        await AgentBridgeRef.sessions.deleteActivityGroup(groupId);
        return await loadSessionActivity();
      }
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
      if(action==='create-quick-task'&&OPS.view==='home'){
        const projectId=String(OPS.quickTaskProjectId||normalizeQuickTaskProjectSelection()||'').trim();
        await createQuickTask(projectId,OPS.quickTaskText,{run:false});
        return null;
      }
      if(action==='execute-ready-tasks'&&OPS.view==='home'){
        const projectId=String(OPS.quickTaskProjectId||normalizeQuickTaskProjectSelection()||'').trim();
        if(!projectId)throw new Error('Choose a project first.');
        OPS.quickTaskBusy=true;
        OPS.quickTaskBusyAction='execute-ready';
        OPS.quickTaskStatus='Preparing ready task execution...';
        OPS.quickTaskStatusKind='info';
        if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home')renderHome();
        try{
          await executeReadyTasksWithAi(projectId);
          OPS.quickTaskStatus='Ready task execution session started.';
          OPS.quickTaskStatusKind='success';
        }catch(err){
          OPS.quickTaskStatus=err&&err.message?err.message:'Unable to execute ready tasks.';
          OPS.quickTaskStatusKind='error';
          throw err;
        }finally{
          OPS.quickTaskBusy=false;
          OPS.quickTaskBusyAction='';
          if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home')renderHome();
        }
        return null;
      }
      if(action==='toggle-session-activity-group'){
        const groupKey=String(btn&&btn.dataset&&btn.dataset.sessionActivityGroupKey||'').trim();
        if(!groupKey)return null;
        setSessionActivityGroupCollapsed(groupKey,!isSessionActivityGroupCollapsed({id:groupKey,isUngrouped:groupKey==='__ungrouped__'}));
        return renderCurrentOpsView();
      }
      return false;
    }

    function handleQuickTaskField(event){
      const sessionGroupLabelField=event.target.closest('[data-ops-session-group-label]');
      if(sessionGroupLabelField&&root()&&root().contains(sessionGroupLabelField)&&event.type==='change'){
        const groupId=String(sessionGroupLabelField.dataset.groupId||'').trim();
        const initialLabel=String(sessionGroupLabelField.dataset.initialLabel||'').trim();
        const nextLabel=String(sessionGroupLabelField.value||'').replace(/\s+/g,' ').trim();
        if(!groupId)return true;
        if(!nextLabel){
          sessionGroupLabelField.value=initialLabel;
          return true;
        }
        if(nextLabel===initialLabel)return true;
        sessionGroupLabelField.disabled=true;
        AgentBridgeRef.sessions.renameActivityGroup(groupId,nextLabel)
          .then(()=>loadSessionActivity())
          .catch(error=>{
            sessionGroupLabelField.disabled=false;
            sessionGroupLabelField.value=initialLabel;
            OPS.sessionActivityError=error&&error.message?error.message:'Unable to rename session group.';
            if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home')renderHome();
          });
        return true;
      }
      const sessionGroupSelect=event.target.closest('[data-ops-session-group-select]');
      if(sessionGroupSelect&&root()&&root().contains(sessionGroupSelect)&&event.type==='change'){
        const sessionKey=String(sessionGroupSelect.dataset.sessionKey||'').trim();
        sessionGroupSelect.disabled=true;
        AgentBridgeRef.sessions.assignActivityGroup(sessionKey,sessionGroupSelect.value||null)
          .then(()=>loadSessionActivity())
          .catch(error=>{
            sessionGroupSelect.disabled=false;
            OPS.sessionActivityError=error&&error.message?error.message:'Unable to move session.';
            if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home')renderHome();
          });
        return true;
      }
      const field=event.target.closest('[data-ops-quick-field]');
      if(!field||!root()||!root().contains(field))return false;
      if(field.dataset.opsQuickField==='projectId'){
        if(OPS.quickTaskDictationActive)stopQuickTaskDictation({updateStatus:false,discard:true});
        OPS.quickTaskProjectId=field.value;
        if(OPS.sessionActivityRenderPending&&windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home'){
          OPS.sessionActivityRenderPending=false;
          renderHome();
        }
      }
      if(field.dataset.opsQuickField==='text')OPS.quickTaskText=field.value;
      if(field.dataset.opsQuickField==='goalMode')OPS.quickTaskGoalMode=!!field.checked;
      if(field.dataset.opsQuickField==='images'){
        addQuickTaskImages(field.files);
        field.value='';
        if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home')renderHome();
      }
      return true;
    }

    function handleHomeClick(event){
      if(!root()||!root().contains(event.target))return false;
      if(event.target.closest('[data-ops-session-group-select]')||event.target.closest('[data-ops-session-group-label]')){
        event.stopImmediatePropagation();
        return true;
      }
      return false;
    }

    function handleHomeKeydown(event){
      if(!root()||!root().contains(event.target))return false;
      const item=event.target.closest('[data-ops-session-activity-item="true"]');
      if(
        item
        && !event.target.closest('[data-ops-session-group-select]')
        && !event.target.closest('[data-ops-session-group-label]')
        && !event.target.closest('.menu-session-activity-actions')
      ){
        if(event.key==='Enter'||event.key===' '){
          event.preventDefault();
          item.click();
          return true;
        }
      }
      const sessionRow=event.target.closest('[data-ops-session-row="true"]');
      if(sessionRow&&!event.target.closest('.ops-session-actions')){
        if(event.key==='Enter'||event.key===' '){
          event.preventDefault();
          sessionRow.click();
          return true;
        }
      }
      const groupInput=event.target.closest('[data-ops-session-group-label]');
      if(groupInput){
        if(event.key==='Enter'){
          event.preventDefault();
          groupInput.blur();
          return true;
        }
        if(event.key==='Escape'){
          groupInput.value=String(groupInput.dataset.initialLabel||'');
          groupInput.blur();
          return true;
        }
      }
      return false;
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
      handleHomeClick,
      handleHomeKeydown,
      handleQuickTaskField,
    };
  }

  window.HermesOpsModules.home={bindDashboard};
})();

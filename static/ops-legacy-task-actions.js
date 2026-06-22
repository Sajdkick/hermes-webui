(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};

  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const AgentBridgeRef=ctx&&ctx.AgentBridge;
    const api=ctx&&ctx.api;
    const projectUrl=ctx&&ctx.projectUrl;
    const projectPath=ctx&&ctx.projectPath;
    const nameOf=ctx&&ctx.nameOf;
    const findProject=ctx&&ctx.findProject;
    const findTask=ctx&&ctx.findTask;
    const findTaskInData=ctx&&ctx.findTaskInData;
    const allTasks=ctx&&ctx.allTasks;
    const findSession=ctx&&ctx.findSession;
    const sessionTaskId=ctx&&ctx.sessionTaskId;
    const latestSessionForTask=ctx&&ctx.latestSessionForTask;
    const sessionRefValue=ctx&&ctx.sessionRefValue;
    const normalizeTaskGrade=ctx&&ctx.normalizeTaskGrade;
    const getTaskQaStatus=ctx&&ctx.getTaskQaStatus;
    const getTaskMoreWork=ctx&&ctx.getTaskMoreWork;
    const actionableTaskCount=ctx&&ctx.actionableTaskCount;
    const summarizeTaskFilters=ctx&&ctx.summarizeTaskFilters;
    const renderProjectDetail=ctx&&ctx.renderProjectDetail;
    const loadProjectDetail=ctx&&ctx.loadProjectDetail;
    const refreshOpsSessions=ctx&&ctx.refreshOpsSessions;
    const reloadProjectTasks=ctx&&ctx.reloadProjectTasks;
    const loadProjects=ctx&&ctx.loadProjects;
    const renderProjects=ctx&&ctx.renderProjects;
    const renderHome=ctx&&ctx.renderHome;
    const loadSession=ctx&&ctx.loadSession;
    const renderSessionList=ctx&&ctx.renderSessionList;
    const closeOpsDashboard=ctx&&ctx.closeOpsDashboard;
    const showToast=ctx&&ctx.showToast;
    const showPromptDialog=ctx&&ctx.showPromptDialog;
    const showConfirmDialog=ctx&&ctx.showConfirmDialog;
    const setBusy=ctx&&ctx.setBusy;
    const domLookup=ctx&&ctx.domLookup;
    const documentRef=(ctx&&ctx.documentRef)||(typeof document!=='undefined'?document:null);
    const windowRef=(ctx&&ctx.windowRef)||(typeof window!=='undefined'?window:null);
    const FileReaderRef=(ctx&&ctx.FileReaderRef)||(typeof FileReader!=='undefined'?FileReader:null);
    const SRef=ctx&&ctx.SRef;
    const addFiles=ctx&&ctx.addFiles;
    const renderTray=ctx&&ctx.renderTray;
    const clearPersistedSessionId=ctx&&ctx.clearPersistedSessionId;
    const sendTurn=ctx&&ctx.sendTurn;
    const autoResize=ctx&&ctx.autoResize;
    const clearQuickTaskImages=ctx&&ctx.clearQuickTaskImages;
    const enterOpsSessionInspectMode=ctx&&ctx.enterOpsSessionInspectMode;
    if(
      !OPS
      || !AgentBridgeRef
      || !AgentBridgeRef.sessions
      || !AgentBridgeRef.runs
      || typeof api!=='function'
      || typeof projectUrl!=='function'
      || typeof projectPath!=='function'
      || typeof nameOf!=='function'
      || typeof findProject!=='function'
      || typeof findTask!=='function'
      || typeof findTaskInData!=='function'
      || typeof allTasks!=='function'
      || typeof findSession!=='function'
      || typeof sessionTaskId!=='function'
      || typeof latestSessionForTask!=='function'
      || typeof sessionRefValue!=='function'
      || typeof normalizeTaskGrade!=='function'
      || typeof getTaskQaStatus!=='function'
      || typeof getTaskMoreWork!=='function'
      || typeof actionableTaskCount!=='function'
      || typeof summarizeTaskFilters!=='function'
      || typeof renderProjectDetail!=='function'
      || typeof loadProjectDetail!=='function'
      || typeof refreshOpsSessions!=='function'
      || typeof reloadProjectTasks!=='function'
      || typeof loadProjects!=='function'
      || typeof renderProjects!=='function'
      || typeof renderHome!=='function'
      || typeof loadSession!=='function'
      || typeof renderSessionList!=='function'
      || typeof closeOpsDashboard!=='function'
      || typeof showToast!=='function'
      || typeof showPromptDialog!=='function'
      || typeof showConfirmDialog!=='function'
      || typeof setBusy!=='function'
      || typeof domLookup!=='function'
      || !documentRef
      || typeof clearQuickTaskImages!=='function'
    ){
      return {};
    }

    const TASK_EXECUTION_PREFACE=String(ctx&&ctx.taskExecutionPreface||'Execute on this task from the user');
    const TASK_EXECUTION_INSTRUCTIONS=String(ctx&&ctx.taskExecutionInstructions||'but before doing so you must first read the contents of AGENTS.md. Once you have done that you have all the context you need to decide how to move forward with the task.');
    const TASK_BATCH_EXECUTION_PROMPT=String(ctx&&ctx.taskBatchExecutionPrompt||'Analyze the current project task file and execute the ready tasks with AI.');
    const TASK_BATCH_INSTRUCTIONS=String(ctx&&ctx.taskBatchInstructions||'Follow the project task file as the source of truth for execution order and status updates.');

    function stateRef(){
      return typeof SRef==='function'?SRef():null;
    }

    function projectTaskFileInfo(projectId){
      const projectKey=String(projectId||'').trim();
      const cached=projectKey&&OPS.currentProject&&OPS.currentProject.id===projectKey
        ? OPS.taskData
        : OPS.taskDataByProject[projectKey];
      return {
        path:String(cached&&((cached.tasksFile)||(cached.tasksFilePath))||'').trim(),
        branch:String(cached&&cached.branch||'').trim(),
      };
    }

    async function fetchProjectTaskFileInfo(projectId){
      const projectKey=String(projectId||'').trim();
      if(!projectKey)return {path:'',branch:''};
      const cached=projectTaskFileInfo(projectKey);
      if(cached.path||cached.branch)return cached;
      const data=await api(projectUrl(projectKey,'/tasks-file')).catch(()=>({path:'',branch:''}));
      return {
        path:String(data&&data.path||'').trim(),
        branch:String(data&&data.branch||'').trim(),
      };
    }

    function buildTaskBatchExecutionPrompt(tasksFileInfo){
      const lines=[TASK_BATCH_EXECUTION_PROMPT];
      lines.push(TASK_BATCH_INSTRUCTIONS);
      if(tasksFileInfo&&tasksFileInfo.branch){
        lines.push(`Branch: ${tasksFileInfo.branch}`);
      }
      if(tasksFileInfo&&tasksFileInfo.path){
        lines.push(`Tasks JSON file for this branch: ${tasksFileInfo.path}`);
      }
      lines.push('Read and update that JSON file directly for this branch.');
      lines.push('Process tasks sequentially with no user prompts.');
      lines.push('Actionable tasks are only:');
      lines.push('- ready: not done, not blocked by dependencies, no qaStatus, and not inProgress.');
      lines.push('- needs-more-work: qaStatus is "needs-more-work".');
      lines.push('Execution loop for each actionable task:');
      lines.push('1) Reload task JSON and choose the next actionable task.');
      lines.push('2) Implement the task in the codebase.');
      lines.push('3) Immediately update the task JSON before moving on.');
      lines.push('If you discover new follow-up work while executing, add it as a new ready task with done=false, no qaStatus, and no inProgress.');
      lines.push('Never set qaStatus="ready-for-test" on newly created follow-up tasks; that status is only for actionable tasks you just executed.');
      lines.push('4) If task is completed, keep done=false, set qaStatus="ready-for-test", and clear moreWork/inProgress/sessionId/lastSessionAt when present.');
      lines.push('5) If task cannot be completed now, keep done=false, set qaStatus="needs-more-work", and write a clear moreWork note.');
      lines.push('6) Save the JSON and continue to the next actionable task until none remain.');
      return lines.filter(Boolean).join('\n');
    }

    function readFileAsDataUrl(file){
      return new Promise((resolve,reject)=>{
        if(typeof FileReaderRef!=='function'){
          reject(new Error('File uploads are not supported in this browser.'));
          return;
        }
        const reader=new FileReaderRef();
        reader.onload=()=>resolve(String(reader.result||''));
        reader.onerror=()=>reject(reader.error||new Error('Unable to read file.'));
        reader.readAsDataURL(file);
      });
    }

    async function uploadQuickTaskImages(projectId,taskId,entries){
      const projectKey=String(projectId||'').trim();
      const taskKey=String(taskId||'').trim();
      const pending=Array.isArray(entries)?entries.filter(entry=>entry&&entry.file):[];
      if(!projectKey||!taskKey||!pending.length)return [];
      const uploaded=[];
      for(const entry of pending){
        const file=entry.file;
        const content=await readFileAsDataUrl(file);
        const result=await api(projectUrl(projectKey,`/tasks/${encodeURIComponent(taskKey)}/images`),{
          method:'POST',
          body:JSON.stringify({filename:file.name,mimeType:file.type,content}),
        });
        if(result&&result.image)uploaded.push(result.image);
      }
      return uploaded;
    }

    async function refreshDetail(){
      if(!OPS.currentProject)return;
      await loadProjectDetail(OPS.currentProject.id);
      renderProjectDetail();
    }

    async function uploadTaskImage(taskId){
      const match=findTask(taskId);
      if(!match||!OPS.currentProject){
        showToast('Task was not found.',2600);
        return;
      }
      const input=documentRef.createElement('input');
      input.type='file';
      input.accept='image/png,image/jpeg,image/gif,image/webp';
      input.style.position='fixed';
      input.style.left='-10000px';
      documentRef.body.appendChild(input);
      try{
        const file=await new Promise(resolve=>{
          input.addEventListener('change',()=>resolve(input.files&&input.files[0]||null),{once:true});
          input.click();
        });
        if(!file)return;
        const content=await readFileAsDataUrl(file);
        await api(projectUrl(OPS.currentProject.id,`/tasks/${encodeURIComponent(taskId)}/images`),{
          method:'POST',
          body:JSON.stringify({filename:file.name,mimeType:file.type,content}),
        });
        showToast('Task image uploaded',2400);
        await refreshDetail();
      }finally{
        input.remove();
      }
    }

    function findTaskBySessionId(sessionId,projectId){
      const sid=sessionRefValue(sessionId);
      if(!sid)return null;
      const liveSession=findSession(sid);
      const liveTaskId=sessionTaskId(liveSession);
      if(liveTaskId){
        return allTasks(projectId).find(({task})=>String(task&&task.id||'').trim()===liveTaskId)||null;
      }
      return allTasks(projectId).find(({task})=>{
        const latest=latestSessionForTask(task&&task.id,projectId);
        return !!(latest&&sessionRefValue(latest)===sid);
      })||null;
    }

    async function updateTaskGrade(taskId,grade){
      if(!OPS.currentProject||!taskId)return;
      const match=findTask(taskId);
      const normalizedGrade=normalizeTaskGrade(grade);
      const previousGrade=match&&match.task?match.task.grade:undefined;
      if(match&&match.task){
        match.task.grade=normalizedGrade;
        renderProjectDetail();
      }
      try{
        await api(projectUrl(OPS.currentProject.id,`/tasks/${encodeURIComponent(taskId)}`),{
          method:'POST',
          body:JSON.stringify({grade:normalizedGrade}),
        });
        await refreshDetail();
      }catch(error){
        if(match&&match.task){
          if(previousGrade===undefined)delete match.task.grade;
          else match.task.grade=previousGrade;
        }
        await refreshDetail().catch(()=>renderProjectDetail());
        throw error;
      }
    }

    function snapshotTaskFields(task,fields){
      const snapshot={};
      fields.forEach(field=>{
        snapshot[field]={
          exists:Object.prototype.hasOwnProperty.call(task,field),
          value:task[field],
        };
      });
      return snapshot;
    }

    function restoreTaskFieldSnapshot(task,snapshot){
      Object.keys(snapshot||{}).forEach(field=>{
        const entry=snapshot[field]||{};
        if(entry.exists)task[field]=entry.value;
        else delete task[field];
      });
    }

    async function markTaskNeedsMoreWork(taskId){
      const match=findTask(taskId);
      if(!match||!OPS.currentProject)return;
      const existing=getTaskMoreWork(match.task);
      const response=await showPromptDialog({
        title:'Needs more work',
        message:'Describe what still needs work for this task.',
        value:existing||'',
        confirmLabel:'Save',
        cancelLabel:'Cancel',
      });
      if(response===null)return;
      const moreWork=String(response||'').trim();
      if(!moreWork){
        showToast('Needs-more-work feedback is required.',2600);
        return;
      }
      const projectKey=String(OPS.currentProject.id||'').trim();
      const previous=snapshotTaskFields(match.task,['done','qaStatus','moreWork','inProgress']);
      Object.assign(match.task,{done:false,qaStatus:'needs-more-work',moreWork,inProgress:false});
      renderProjectDetail();
      showToast('Task marked as needing more work',1800);
      (async function persistNeedsMoreWorkFeedback(){
        try{
          await api(projectUrl(projectKey,`/tasks/${encodeURIComponent(taskId)}`),{
            method:'POST',
            body:JSON.stringify({qaStatus:'needs-more-work',moreWork}),
          });
        }catch(error){
          restoreTaskFieldSnapshot(match.task,previous);
          if(OPS.currentProject&&String(OPS.currentProject.id||'').trim()===projectKey){
            await refreshDetail().catch(()=>renderProjectDetail());
          }
          showToast(error&&error.message?error.message:'Could not save needs-more-work feedback.',4200);
          return;
        }
        if(OPS.currentProject&&String(OPS.currentProject.id||'').trim()===projectKey){
          await refreshDetail().catch(()=>renderProjectDetail());
        }
      })();
    }

    function buildTaskExecutionPrompt(prompt){
      const trimmed=typeof prompt==='string'?prompt.trim():'';
      if(!trimmed)return '';
      return `${TASK_EXECUTION_PREFACE} '${trimmed}', ${TASK_EXECUTION_INSTRUCTIONS}`;
    }

    function splitTaskImageRefs(value){
      const rawItems=Array.isArray(value)
        ? value
        : String(value||'').split(/[\n,]+/);
      const seen=new Set();
      const refs=[];
      rawItems.forEach(item=>{
        const ref=String(item||'').trim();
        if(!ref||seen.has(ref))return;
        seen.add(ref);
        refs.push(ref);
      });
      return refs;
    }

    function appendTaskImageContext(prompt,task){
      const refs=splitTaskImageRefs(task&&task.images);
      if(!refs.length)return prompt;
      const base=String(prompt||'').replace(/[\r\n]+$/g,'');
      return `${base}\n\nAttached task screenshots/images:\n${refs.map(ref=>`- ${ref}`).join('\n')}`;
    }

    function buildTaskPrompt(project,epic,task){
      if(!task)return '';
      const basePrompt=typeof task.text==='string'?task.text.replace(/[\r\n]+$/g,''):'';
      if(getTaskQaStatus(task)!=='needs-more-work'){
        return buildTaskExecutionPrompt(appendTaskImageContext(basePrompt,task));
      }
      const moreWork=getTaskMoreWork(task)||'No details provided.';
      const retryPrompt=`I have tried to implement this feature '${basePrompt}' but when it went through QA we got this comment '${moreWork}' analyze all this in depth and fix all the comments`;
      return buildTaskExecutionPrompt(appendTaskImageContext(retryPrompt,task));
    }

    function providerFromModelValue(modelId){
      const value=String(modelId||'').trim();
      if(value.startsWith('@')&&value.includes(':')){
        return value.slice(1,value.lastIndexOf(':')).trim().toLowerCase();
      }
      return '';
    }

    function normalizeModelState(model,provider){
      const normalizedModel=String(model||'').trim();
      const normalizedProvider=String(provider||'').trim().toLowerCase()||providerFromModelValue(normalizedModel)||null;
      return {
        model:normalizedModel,
        model_provider:normalizedProvider||null,
      };
    }

    function selectedOpsModelState(){
      const modelSelect=domLookup('modelSelect');
      if(!modelSelect)return null;
      if(typeof _modelStateForSelect==='function'){
        const state=_modelStateForSelect(modelSelect,modelSelect.value||'');
        if(state&&state.model)return normalizeModelState(state.model,state.model_provider);
      }
      const selectedOption=modelSelect.selectedOptions&&modelSelect.selectedOptions[0];
      const group=selectedOption&&selectedOption.parentElement;
      const provider=group&&group.tagName==='OPTGROUP'&&group.dataset
        ? group.dataset.provider
        : '';
      return normalizeModelState(modelSelect.value||'',provider);
    }

    function readStoredOpsModelState(){
      if(typeof _readPersistedModelState==='function'){
        const stored=_readPersistedModelState();
        if(stored&&stored.model)return normalizeModelState(stored.model,stored.model_provider);
      }
      if(!windowRef||!windowRef.localStorage)return null;
      try{
        const raw=windowRef.localStorage.getItem('hermes-webui-model-state');
        if(raw){
          const parsed=JSON.parse(raw);
          if(parsed&&parsed.model){
            return normalizeModelState(parsed.model,parsed.model_provider);
          }
        }
      }catch(_){}
      try{
        const legacyModel=windowRef.localStorage.getItem('hermes-webui-model');
        if(legacyModel)return normalizeModelState(legacyModel,'');
      }catch(_){}
      return null;
    }

    function currentOpsModelState(){
      const selectedState=selectedOpsModelState();
      if(selectedState&&selectedState.model)return selectedState;
      const state=stateRef();
      const sessionState=state&&state.session&&state.session.model
        ? normalizeModelState(state.session.model,state.session.model_provider)
        : null;
      if(sessionState&&sessionState.model)return sessionState;
      const storedState=readStoredOpsModelState();
      if(storedState&&storedState.model)return storedState;
      const defaultModel=windowRef&&windowRef._defaultModel;
      const activeProvider=windowRef&&windowRef._activeProvider;
      return normalizeModelState(defaultModel||'',activeProvider||'');
    }

    function currentOpsProfile(project){
      const projectProfile=String(project&&project.profile||'').trim();
      if(projectProfile)return projectProfile;
      return 'default';
    }

    function setActiveProfileForOpsSession(profile){
      const profileName=String(profile||'').trim();
      if(!profileName)return '';
      const state=stateRef();
      if(state){
        state.activeProfile=profileName;
        if(state.session&&!state.session.profile)state.session.profile=profileName;
      }
      const profileLabel=domLookup('profileChipLabel');
      if(profileLabel)profileLabel.textContent=profileName;
      const compactProfileLabel=domLookup('profileChipCompactLabel');
      if(compactProfileLabel)compactProfileLabel.textContent=profileName;
      return profileName;
    }

    function selectLoadedOpsSessionProfile(fallbackProfile){
      const state=stateRef();
      const sessionProfile=String(state&&state.session&&state.session.profile||'').trim();
      return setActiveProfileForOpsSession(sessionProfile||fallbackProfile);
    }

    function openLoadedOpsSession(sessionRef){
      selectLoadedOpsSessionProfile('');
      closeOpsDashboard();
      if(typeof enterOpsSessionInspectMode==='function'){
        enterOpsSessionInspectMode({source:'ops-dashboard',sessionId:sessionRef});
      }
    }

    async function newChatInProject(projectOverride){
      const project=projectOverride||OPS.currentProject;
      if(!project)return;
      await api(projectUrl(project.id,'/ensure-workspace'),{method:'POST',body:JSON.stringify({})});
      const payload={
        workspace:projectPath(project),
        ops_project_id:project.id,
        project_id:project.id,
        projectId:project.id,
        profile:currentOpsProfile(project),
      };
      const data=await AgentBridgeRef.sessions.create(payload);
      if(data.session&&data.session.session_id){
        await AgentBridgeRef.sessions.rename(data.session,`${nameOf(project)} session`);
        await loadSession(data.session);
        await renderSessionList();
        openLoadedOpsSession(sessionRefValue(data.session)||data.session.session_id);
        showToast('Opened '+nameOf(project),2600);
      }
    }

    async function openOpsSession(sessionId){
      const sessionRef=sessionRefValue(sessionId);
      if(!sessionRef)return;
      try{
        await loadSession(sessionRef,{force:true});
        await renderSessionList();
        openLoadedOpsSession(sessionRef);
      }catch(error){
        showToast(error&&error.message?error.message:'Unable to open session',3600);
        throw error;
      }
    }

    async function clearDeletedSessionFromMainView(sessionId){
      const sid=sessionRefValue(sessionId);
      const state=stateRef();
      if(!sid||!state||!state.session||sessionRefValue(state.session)!==sid)return;
      state.session=null;
      state.messages=[];
      state.entries=[];
      if('activeStreamId' in state)state.activeStreamId='';
      if(typeof clearPersistedSessionId==='function')clearPersistedSessionId();
      else try{windowRef.localStorage.removeItem('hermes-webui-session');}catch(_){}
      let remaining={sessions:[]};
      try{
        remaining=await AgentBridgeRef.sessions.list();
      }catch(_){}
      if(Array.isArray(remaining.sessions)&&remaining.sessions.length&&typeof loadSession==='function'){
        await loadSession(remaining.sessions[0]);
        return;
      }
      if(domLookup('topbarTitle'))domLookup('topbarTitle').textContent=windowRef&&windowRef._botName||'Hermes';
      if(domLookup('topbarMeta'))domLookup('topbarMeta').textContent='Start a new conversation';
      if(domLookup('msgInner'))domLookup('msgInner').innerHTML='';
      if(domLookup('emptyState'))domLookup('emptyState').style.display='';
      if(domLookup('fileTree'))domLookup('fileTree').innerHTML='';
    }

    async function closeOpsSessionRecord(sessionId,options){
      const sid=sessionRefValue(sessionId);
      const opts=(options&&typeof options==='object')?options:{};
      if(!sid)return null;
      if(AgentBridgeRef&&AgentBridgeRef.sessions&&typeof AgentBridgeRef.sessions.closeOps==='function'){
        return await AgentBridgeRef.sessions.closeOps(sid,opts);
      }
      if(opts.projectId&&opts.taskId&&AgentBridgeRef&&AgentBridgeRef.sessions&&typeof AgentBridgeRef.sessions.closeTask==='function'){
        return await AgentBridgeRef.sessions.closeTask(opts.projectId,opts.taskId,{sessionId:sid});
      }
      await AgentBridgeRef.sessions.archive(sid,true);
      return {ok:true,sessionId:sid,closedSessionIds:[sid]};
    }

    async function deleteOpsSessionRecord(sessionId){
      const sid=sessionRefValue(sessionId);
      if(!sid)return false;
      const closeResult=await closeOpsSessionRecord(sid,{});
      const closedIds=[sid,closeResult&&closeResult.sessionId,...(Array.isArray(closeResult&&closeResult.closedSessionIds)?closeResult.closedSessionIds:[])];
      removeClosedSessionRefs(closedIds);
      OPS.sessions=(OPS.sessions||[]).filter(session=>sessionRefValue(session)!==sid);
      await clearDeletedSessionFromMainView(sid);
      return true;
    }

    async function recordOpsRun(project,epic,task,sessionId,status,summary){
      if(!project||!task||!sessionId)return null;
      return AgentBridgeRef.runs.create({
        projectId:project.id,
        taskId:task.id,
        sessionId,
        engine:'hermes-session',
        status,
        title:String(task.text||'').slice(0,120)||'Project task',
        summary:summary||'',
        metadata:{
          source:'ops-dashboard',
          epicId:epic&&epic.id?epic.id:'',
          projectName:nameOf(project),
          grade:task.grade||'',
        },
      });
    }

    function renderAfterSessionCloseMutation(project){
      if(project&&OPS.currentProject&&OPS.currentProject.id===project.id){
        renderProjectDetail();
      }else if(OPS.view==='home'){
        renderHome();
      }else{
        renderProjects();
      }
    }

    function sessionActionRefValue(sessionLike){
      if(!sessionLike)return '';
      if(typeof sessionLike==='string')return String(sessionLike).trim();
      const direct=String(sessionLike.session_id||sessionLike.sessionId||sessionLike.id||'').trim();
      if(direct)return direct;
      return String(sessionLike.sessionKey||sessionLike.session_key||sessionRefValue(sessionLike)||'').trim();
    }

    function normalizeClosedSessionIds(value){
      const raw=Array.isArray(value)?value:[value];
      const ids=new Set();
      raw.forEach(entry=>{
        const sid=sessionActionRefValue(entry)||String(entry||'').trim();
        if(sid)ids.add(sid);
      });
      return ids;
    }

    function removeClosedSessionRefs(sessionIds){
      const ids=normalizeClosedSessionIds(sessionIds);
      if(!ids.size)return;
      OPS.sessions=(OPS.sessions||[]).filter(session=>!ids.has(sessionActionRefValue(session)));
      if(Array.isArray(OPS.sessionActivity)){
        OPS.sessionActivity=OPS.sessionActivity.filter(session=>!ids.has(sessionActionRefValue(session)));
      }
    }

    const CLOSE_SESSION_CONFIRM_TASK_TEXT_LIMIT=180;

    function closeSessionConfirmTaskText(value){
      const normalized=String(value||'').replace(/\s+/g,' ').trim();
      if(normalized.length<=CLOSE_SESSION_CONFIRM_TASK_TEXT_LIMIT)return normalized;
      const clipped=normalized.slice(0,CLOSE_SESSION_CONFIRM_TASK_TEXT_LIMIT).replace(/\s+\S*$/,'').trim()
        || normalized.slice(0,CLOSE_SESSION_CONFIRM_TASK_TEXT_LIMIT).trim();
      return `${clipped}…`;
    }

    async function setOpsSessionClosed(sessionId,closed,projectId){
      const sessionRef=sessionRefValue(sessionId);
      const project=projectId?findProject(projectId):OPS.currentProject;
      if(!sessionRef)return;
      const linked=project?findTaskBySessionId(sessionRef,project.id):null;
      if(!closed){
        await AgentBridgeRef.sessions.archive(sessionRef,false);
        if(project&&linked){
          await recordOpsRun(
            project,
            linked.epic,
            linked.task,
            sessionRef,
            'starting',
            'Legacy session was restored from the ops dashboard.'
          ).catch(()=>null);
        }
        if(project&&OPS.currentProject&&OPS.currentProject.id===project.id){
          await refreshDetail();
        }else{
          await loadProjects();
          if(OPS.view==='home')renderHome();
          else renderProjects();
        }
        await renderSessionList();
        showToast('Session restored',2200);
        return;
      }
      const linkedTaskText=linked&&linked.task&&linked.task.text?closeSessionConfirmTaskText(linked.task.text):'';
      const label=linkedTaskText
        ? `Close the session for "${linkedTaskText}"? This removes it from the active flow.`
        : 'Close this session? This removes it from the active flow.';
      const ok=await showConfirmDialog({
        title:'Close session',
        message:label,
        confirmLabel:'Close',
        danger:true,
        focusCancel:true,
      });
      if(!ok)return;
      const previousSessions=Array.isArray(OPS.sessions)?OPS.sessions.slice():[];
      const previousActivity=Array.isArray(OPS.sessionActivity)?OPS.sessionActivity.slice():null;
      const previousTaskState=linked&&linked.task?{
        inProgress:linked.task.inProgress,
        sessionId:linked.task.sessionId,
        session_id:linked.task.session_id,
        lastSessionAt:linked.task.lastSessionAt,
        startedAt:linked.task.startedAt,
      }:null;
      removeClosedSessionRefs([sessionRef]);
      if(linked&&linked.task){
        linked.task.inProgress=false;
        delete linked.task.sessionId;
        delete linked.task.session_id;
      }
      renderAfterSessionCloseMutation(project);
      try{
        let closeResult=null;
        if(project&&linked){
          closeResult=await closeOpsSessionRecord(sessionRef,{projectId:project.id,taskId:linked.task.id});
          removeClosedSessionRefs([sessionRef,closeResult&&closeResult.sessionId,...(Array.isArray(closeResult&&closeResult.closedSessionIds)?closeResult.closedSessionIds:[])]);
          await refreshOpsSessions().catch(()=>OPS.sessions||[]);
        }else{
          closeResult=await closeOpsSessionRecord(sessionRef,{projectId:project&&project.id||projectId||''});
          removeClosedSessionRefs([sessionRef,closeResult&&closeResult.sessionId,...(Array.isArray(closeResult&&closeResult.closedSessionIds)?closeResult.closedSessionIds:[])]);
          await clearDeletedSessionFromMainView(sessionRef);
        }
        if(project&&OPS.currentProject&&OPS.currentProject.id===project.id){
          await refreshDetail();
        }else{
          await loadProjects();
          if(OPS.view==='home')renderHome();
          else renderProjects();
        }
        await renderSessionList();
        showToast('Session closed',2200);
      }catch(error){
        OPS.sessions=previousSessions;
        if(previousActivity)OPS.sessionActivity=previousActivity;
        if(previousTaskState&&linked&&linked.task){
          Object.assign(linked.task,previousTaskState);
        }
        renderAfterSessionCloseMutation(project);
        showToast(error&&error.message?error.message:'Unable to close session',3600);
        throw error;
      }
    }

    async function ensureTaskSession(match,projectOverride,options){
      const project=projectOverride||OPS.currentProject;
      if(!project)throw new Error('Project not found.');
      const opts=options&&typeof options==='object'?options:{};
      const {epic,task}=match;
      await api(projectUrl(project.id,'/ensure-workspace'),{method:'POST',body:JSON.stringify({})});
      const forceNewSession=opts.forceNewSession===true||opts.forceNew===true||opts.skipExistingLookup===true;
      const payload={
        workspace:projectPath(project),
        profile:currentOpsProfile(project),
        title:task.text.slice(0,80)||'Project task',
      };
      if(forceNewSession){
        payload.forceNew=true;
        payload.skipExistingLookup=true;
      }
      const data=await AgentBridgeRef.sessions.ensureTask(project.id,task.id,payload);
      const session=data&&data.session;
      if(!session||!session.session_id)throw new Error('Unable to create task session.');
      if(data&&data.task&&typeof data.task==='object'){
        Object.assign(task,data.task);
      }else{
        const now=new Date().toISOString();
        task.inProgress=true;
        task.lastSessionAt=now;
        if(!task.startedAt)task.startedAt=now;
      }
      await refreshOpsSessions().catch(()=>OPS.sessions||[]);
      await recordOpsRun(
        project,
        epic,
        task,
        session.session_id,
        session.active_stream_id?'running':'starting',
        session.active_stream_id?'Task session is already running.':'Task session is ready to start.'
      );
      return {
        sessionId:session.session_id,
        sessionKey:sessionRefValue(session),
        alreadyRunning:!!(data&&data.reused)||!!session.active_stream_id,
        epic,
        task,
      };
    }

    async function executeTaskMatch(project,match,options){
      if(!match||!project)return;
      const opts=options&&typeof options==='object'?options:{};
      const pendingQuickTaskFiles=Array.isArray(opts.files)?opts.files.filter(Boolean):[];
      const goalMode=!!opts.goalMode;
      const openInspectAfterStart=opts.openInspectAfterStart===true;
      setBusy(true);
      try{
        const {sessionId,sessionKey,alreadyRunning,epic,task}=await ensureTaskSession(match,project,opts);
        await loadSession(sessionKey||sessionId,{force:true});
        selectLoadedOpsSessionProfile(currentOpsProfile(project));
        await renderSessionList();
        const state=stateRef();
        const sessionRunning=!!(state&&state.session&&sessionRefValue(state.session)===(sessionKey||sessionId)&&(state.session.active_stream_id||state.activeStreamId));
        if(alreadyRunning||sessionRunning){
          showToast('Opened running task session',2600);
          openLoadedOpsSession(sessionKey||sessionId);
          return;
        }
        const msg=domLookup('msg');
        if(msg&&typeof sendTurn==='function'){
          if(pendingQuickTaskFiles.length){
            if(typeof addFiles==='function'){
              addFiles(pendingQuickTaskFiles);
            }else if(state){
              const existing=Array.isArray(state.pendingFiles)?state.pendingFiles:[];
              state.pendingFiles=[...existing,...pendingQuickTaskFiles];
              if(typeof renderTray==='function')renderTray();
            }
          }
          const taskPrompt=buildTaskPrompt(project,epic,task);
          // Targeted WebUI /goal bridge: prefix when the originating task flow
          // asks for standing goal execution.
          // Remove this once upstream Hermes WebUI ships native goal-mode support.
          msg.value=goalMode?`/goal ${taskPrompt}`:taskPrompt;
          if(typeof autoResize==='function')autoResize();
          // Start the first turn before opening inspect mode. In standalone Ops,
          // opening the loaded session navigates to /session/<id>; doing that
          // before sendTurn() can leave a linked task session empty.
          await sendTurn();
          await recordOpsRun(project,epic,task,sessionId,'running',goalMode?'Task goal execution was started from the ops dashboard.':'Task execution was started from the ops dashboard.');
          showToast(goalMode?'Task goal started':'Task execution started',2400);
          if(openInspectAfterStart){
            openLoadedOpsSession(sessionKey||sessionId);
          }
        }else{
          showToast('Opened task session',2400);
          openLoadedOpsSession(sessionKey||sessionId);
        }
      }finally{
        setBusy(false);
      }
    }

    async function executeTask(taskId,options){
      const match=findTask(taskId);
      if(!match||!OPS.currentProject)return;
      return executeTaskMatch(OPS.currentProject,match,options);
    }

    function rememberProjectTask(projectId,epic,task){
      const projectKey=String(projectId||'').trim();
      const epicKey=String(epic&&epic.id||'').trim();
      if(!projectKey||!epicKey)return;
      const targets=[];
      const cached=OPS.taskDataByProject&&OPS.taskDataByProject[projectKey];
      if(cached)targets.push(cached);
      if(OPS.currentProject&&OPS.currentProject.id===projectKey&&OPS.taskData&&OPS.taskData!==cached)targets.push(OPS.taskData);
      targets.forEach(data=>{
        if(!data||!Array.isArray(data.epics))return;
        let epicEntry=data.epics.find(entry=>String(entry&&entry.id||'').trim()===epicKey);
        if(!epicEntry){
          epicEntry={...epic,tasks:Array.isArray(epic.tasks)?epic.tasks.slice():[]};
          data.epics=[...data.epics,epicEntry];
        }
        if(!task||!task.id)return;
        const taskKey=String(task.id||'').trim();
        const tasks=Array.isArray(epicEntry.tasks)?epicEntry.tasks.slice():[];
        const index=tasks.findIndex(entry=>String(entry&&entry.id||'').trim()===taskKey);
        if(index>=0)tasks[index]={...tasks[index],...task};
        else tasks.push(task);
        epicEntry.tasks=tasks;
      });
    }

    async function ensureProjectEpic(projectId,title,options){
      const opts=options&&typeof options==='object'?options:{};
      const projectKey=String(projectId||'').trim();
      const normalizedTitle=String(title||'').trim().toLowerCase();
      const cached=(OPS.taskDataByProject&&OPS.taskDataByProject[projectKey])||(OPS.currentProject&&OPS.currentProject.id===projectKey?OPS.taskData:null);
      const cachedEpic=cached&&Array.isArray(cached.epics)
        ? cached.epics.find(entry=>String(entry.title||'').trim().toLowerCase()===normalizedTitle)
        : null;
      if(cachedEpic)return cachedEpic;
      if(opts.lean===true||opts.skipReload===true){
        const ensured=await api(projectUrl(projectKey,'/epics/ensure'),{method:'POST',body:JSON.stringify({title})});
        if(ensured&&ensured.epic)rememberProjectTask(projectKey,ensured.epic,null);
        return ensured&&ensured.epic;
      }
      let data=await reloadProjectTasks(projectKey);
      let epic=(data.epics||[]).find(entry=>String(entry.title||'').trim().toLowerCase()===normalizedTitle);
      if(epic)return epic;
      const created=await api(projectUrl(projectKey,'/epics'),{method:'POST',body:JSON.stringify({title})});
      data=await reloadProjectTasks(projectKey);
      epic=(data.epics||[]).find(entry=>entry.id===(created.epic&&created.epic.id));
      return epic||created.epic;
    }

    async function ensureQuickTaskEpic(projectId){
      return ensureProjectEpic(projectId,'Quick tasks',{lean:true});
    }

    async function executeReadyTasksWithAi(projectId){
      const project=findProject(projectId)||OPS.currentProject;
      const projectKey=String(project&&project.id||'').trim();
      if(!project||!projectKey)throw new Error('Project not found.');
      const summary=summarizeTaskFilters(
        ((OPS.taskDataByProject[projectKey]||OPS.taskData||{}).epics)||[],
        typeof ctx.buildTaskLookup==='function'
          ? ctx.buildTaskLookup(((OPS.taskDataByProject[projectKey]||OPS.taskData||{}).epics)||[])
          : {},
        {status:'active',grade:'',token:''}
      );
      if(!actionableTaskCount(summary)){
        throw new Error('No ready tasks are available to execute.');
      }

      OPS.taskAutomationBusyByProject[projectKey]='execute-ready';
      if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='project-detail'&&OPS.currentProject&&OPS.currentProject.id===projectKey){
        renderProjectDetail();
      }

      try{
        const tasksFileInfo=await fetchProjectTaskFileInfo(projectKey);
        const prompt=buildTaskBatchExecutionPrompt(tasksFileInfo);
        if(!prompt)throw new Error('Unable to build the AI batch execution prompt.');
        const epic=await ensureProjectEpic(projectKey,'AI automation');
        if(!epic||!epic.id)throw new Error('Unable to find or create the AI automation epic.');
        showToast('Preparing AI batch execution task...',2200);
        const created=await api(projectUrl(projectKey,'/tasks'),{
          method:'POST',
          body:JSON.stringify({epicId:epic.id,text:prompt,grade:'green'}),
        });
        if(!created.task||!created.task.id)throw new Error('Unable to create the AI batch execution task.');
        const data=await reloadProjectTasks(projectKey);
        const match=findTaskInData(data,created.task.id)||{epic,task:created.task};
        showToast('AI batch execution task created. Starting goal session...',2400);
        await executeTaskMatch(project,match,{goalMode:true});
      }finally{
        delete OPS.taskAutomationBusyByProject[projectKey];
        if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='project-detail'&&OPS.currentProject&&OPS.currentProject.id===projectKey){
          renderProjectDetail();
        }
      }
    }

    async function createQuickTask(projectId,text,options){
      const opts=options&&typeof options==='object'?options:{};
      const shouldRun=opts.run!==false;
      const project=findProject(projectId);
      const taskText=String(text||'').trim();
      const pendingQuickTaskImages=(OPS.quickTaskImages||[]).slice();
      const goalMode=!!OPS.quickTaskGoalMode;
      if(!project)throw new Error('Choose a project first.');
      if(!taskText)throw new Error('Enter a task before creating it.');
      if(OPS.quickTaskDictationActive||OPS.quickTaskDictationBusy){
        throw new Error('Wait for quick task dictation to finish before creating the task.');
      }

      OPS.quickTaskBusy=true;
      OPS.quickTaskBusyAction=shouldRun?'create-run':'create-only';
      OPS.quickTaskStatus='Creating quick task...';
      OPS.quickTaskStatusKind='info';
      if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home')renderHome();

      try{
        const epic=await ensureQuickTaskEpic(project.id);
        if(!epic||!epic.id)throw new Error('Unable to find or create the Quick tasks epic.');
        const created=await api(projectUrl(project.id,'/tasks'),{
          method:'POST',
          body:JSON.stringify({epicId:epic.id,text:taskText,grade:'green'}),
        });
        if(!created.task||!created.task.id)throw new Error('Unable to create the quick task.');
        if(pendingQuickTaskImages.length){
          OPS.quickTaskStatus='Quick task created. Uploading screenshots...';
          OPS.quickTaskStatusKind='info';
          if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home')renderHome();
          try{
            const uploadedImages=await uploadQuickTaskImages(project.id,created.task.id,pendingQuickTaskImages);
            const imagePaths=uploadedImages.map(image=>String(image&&image.path||'').trim()).filter(Boolean);
            if(imagePaths.length)created.task={...created.task,images:imagePaths.join(', ')};
          }catch(uploadErr){
            const message=uploadErr&&uploadErr.message?uploadErr.message:'Unable to upload screenshots.';
            OPS.quickTaskStatus=`Quick task created, but screenshots could not be uploaded: ${message}`;
            OPS.quickTaskStatusKind='warning';
            showToast(OPS.quickTaskStatus,4200);
            return;
          }
        }
        const match={epic,task:created.task};
        rememberProjectTask(project.id,epic,created.task);
        OPS.quickTaskText='';
        clearQuickTaskImages();
        if(!shouldRun){
          OPS.quickTaskStatus='Quick task created.';
          OPS.quickTaskStatusKind='success';
          if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home')renderHome();
          return match;
        }
        OPS.quickTaskStatus=goalMode?'Quick task created. Starting Hermes goal...':'Quick task created. Starting Hermes...';
        OPS.quickTaskStatusKind='info';
        if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home')renderHome();
        try{
          await executeTaskMatch(project,match,{goalMode,openInspectAfterStart:true,forceNewSession:true});
          OPS.quickTaskStatus=goalMode?'Quick task created and goal started.':'Quick task created and execution started.';
          OPS.quickTaskStatusKind='success';
        }catch(execErr){
          const message=execErr&&execErr.message?execErr.message:'Unable to start the task session.';
          OPS.quickTaskStatus=`Quick task created, but execution did not start: ${message}`;
          OPS.quickTaskStatusKind='warning';
          showToast(OPS.quickTaskStatus,4200);
        }
        return match;
      }catch(err){
        OPS.quickTaskStatus=err&&err.message?err.message:'Unable to create the quick task.';
        OPS.quickTaskStatusKind='error';
        throw err;
      }finally{
        OPS.quickTaskBusy=false;
        OPS.quickTaskBusyAction='';
        if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home')renderHome();
      }
    }

    return {
      projectTaskFileInfo,
      fetchProjectTaskFileInfo,
      buildTaskBatchExecutionPrompt,
      readFileAsDataUrl,
      uploadQuickTaskImages,
      uploadTaskImage,
      updateTaskGrade,
      markTaskNeedsMoreWork,
      buildTaskExecutionPrompt,
      buildTaskPrompt,
      refreshDetail,
      newChatInProject,
      openOpsSession,
      clearDeletedSessionFromMainView,
      deleteOpsSessionRecord,
      recordOpsRun,
      setOpsSessionClosed,
      ensureTaskSession,
      executeTaskMatch,
      executeTask,
      ensureProjectEpic,
      ensureQuickTaskEpic,
      executeReadyTasksWithAi,
      createQuickTask,
    };
  }

  window.HermesOpsModules.taskActions={bindDashboard};
})();

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
    const clearSessionReadableOutput=ctx&&ctx.clearSessionReadableOutput;
    const clearPersistedSessionId=ctx&&ctx.clearPersistedSessionId;
    const sendTurn=ctx&&ctx.sendTurn;
    const autoResize=ctx&&ctx.autoResize;
    const clearQuickTaskImages=ctx&&ctx.clearQuickTaskImages;
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
      await api(projectUrl(OPS.currentProject.id,`/tasks/${encodeURIComponent(taskId)}`),{
        method:'POST',
        body:JSON.stringify({grade:normalizeTaskGrade(grade)}),
      });
      await refreshDetail();
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
      await api(projectUrl(OPS.currentProject.id,`/tasks/${encodeURIComponent(taskId)}`),{
        method:'POST',
        body:JSON.stringify({qaStatus:'needs-more-work',moreWork}),
      });
      showToast('Task marked as needing more work',2400);
      await refreshDetail();
    }

    function buildTaskExecutionPrompt(prompt){
      const trimmed=typeof prompt==='string'?prompt.trim():'';
      if(!trimmed)return '';
      return `${TASK_EXECUTION_PREFACE} '${trimmed}', ${TASK_EXECUTION_INSTRUCTIONS}`;
    }

    function buildTaskPrompt(project,epic,task){
      if(!task)return '';
      const basePrompt=typeof task.text==='string'?task.text.replace(/[\r\n]+$/g,''):'';
      if(getTaskQaStatus(task)!=='needs-more-work'){
        return buildTaskExecutionPrompt(basePrompt);
      }
      const moreWork=getTaskMoreWork(task)||'No details provided.';
      const retryPrompt=`I have tried to implement this feature '${basePrompt}' but when it went through QA we got this comment '${moreWork}' analyze all this in depth and fix all the comments`;
      return buildTaskExecutionPrompt(retryPrompt);
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
      const state=stateRef();
      const activeProfile=String(state&&state.activeProfile||'').trim();
      if(activeProfile)return activeProfile;
      const projectProfile=String(project&&project.profile||'').trim();
      return projectProfile||'default';
    }

    async function newChatInProject(projectOverride){
      const project=projectOverride||OPS.currentProject;
      if(!project)return;
      await api(projectUrl(project.id,'/ensure-workspace'),{method:'POST',body:JSON.stringify({})});
      const modelState=currentOpsModelState();
      const state=stateRef();
      const payload={
        workspace:projectPath(project),
        model:modelState.model||undefined,
        model_provider:modelState.model_provider||null,
        ops_project_id:project.id,
        profile:currentOpsProfile(project),
      };
      const data=await AgentBridgeRef.sessions.create(payload);
      if(data.session&&data.session.session_id){
        await AgentBridgeRef.sessions.rename(data.session,`${nameOf(project)} session`);
        await loadSession(data.session);
        await renderSessionList();
        closeOpsDashboard();
        showToast('Opened '+nameOf(project),2600);
      }
    }

    async function openOpsSession(sessionId){
      const sessionRef=sessionRefValue(sessionId);
      if(!sessionRef)return;
      await loadSession(sessionRef);
      await renderSessionList();
      closeOpsDashboard();
    }

    async function clearDeletedSessionFromMainView(sessionId){
      const sid=sessionRefValue(sessionId);
      const state=stateRef();
      if(!sid||!state||!state.session||sessionRefValue(state.session)!==sid)return;
      state.session=null;
      state.messages=[];
      state.entries=[];
      if('activeStreamId' in state)state.activeStreamId='';
      if(typeof clearSessionReadableOutput==='function')clearSessionReadableOutput();
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

    async function deleteOpsSessionRecord(sessionId){
      const sid=sessionRefValue(sessionId);
      if(!sid)return false;
      await AgentBridgeRef.sessions.remove(sid);
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
      const label=linked&&linked.task&&linked.task.text
        ? `Close the session for "${linked.task.text}"? This removes it from the active flow.`
        : 'Close this session? This removes it from the active flow.';
      const ok=await showConfirmDialog({
        title:'Close session',
        message:label,
        confirmLabel:'Close',
        danger:true,
        focusCancel:true,
      });
      if(!ok)return;
      if(project&&linked){
        await AgentBridgeRef.sessions.closeTask(project.id,linked.task.id,{sessionId:sessionRef});
        await refreshOpsSessions().catch(()=>OPS.sessions||[]);
      }else{
        await deleteOpsSessionRecord(sessionRef);
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
    }

    async function ensureTaskSession(match,projectOverride){
      const project=projectOverride||OPS.currentProject;
      if(!project)throw new Error('Project not found.');
      const {epic,task}=match;
      await api(projectUrl(project.id,'/ensure-workspace'),{method:'POST',body:JSON.stringify({})});
      const modelState=currentOpsModelState();
      const payload={
        workspace:projectPath(project),
        model:modelState.model||undefined,
        model_provider:modelState.model_provider||null,
        profile:currentOpsProfile(project),
        title:task.text.slice(0,80)||'Project task',
      };
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
        alreadyRunning:!!session.active_stream_id,
        epic,
        task,
      };
    }

    async function executeTaskMatch(project,match,options){
      if(!match||!project)return;
      const opts=options&&typeof options==='object'?options:{};
      const pendingQuickTaskFiles=Array.isArray(opts.files)?opts.files.filter(Boolean):[];
      const goalMode=!!opts.goalMode;
      setBusy(true);
      try{
        const {sessionId,sessionKey,alreadyRunning,epic,task}=await ensureTaskSession(match,project);
        await loadSession(sessionKey||sessionId);
        await renderSessionList();
        const state=stateRef();
        const sessionRunning=!!(state&&state.session&&sessionRefValue(state.session)===(sessionKey||sessionId)&&(state.session.active_stream_id||state.activeStreamId));
        if(alreadyRunning||sessionRunning){
          showToast('Opened running task session',2600);
          closeOpsDashboard();
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
          // Targeted WebUI /goal bridge: prefix only when the user opted in.
          // Remove this once upstream Hermes WebUI ships native goal-mode support.
          msg.value=goalMode?`/goal ${taskPrompt}`:taskPrompt;
          if(typeof autoResize==='function')autoResize();
          await sendTurn();
          await recordOpsRun(project,epic,task,sessionId,'running',goalMode?'Task goal execution was started from the ops dashboard.':'Task execution was started from the ops dashboard.');
          showToast(goalMode?'Task goal started':'Task execution started',2400);
        }else{
          showToast('Opened task session',2400);
          closeOpsDashboard();
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

    async function ensureProjectEpic(projectId,title){
      let data=OPS.taskDataByProject[projectId]||await reloadProjectTasks(projectId);
      const normalizedTitle=String(title||'').trim().toLowerCase();
      let epic=(data.epics||[]).find(entry=>String(entry.title||'').trim().toLowerCase()===normalizedTitle);
      if(epic)return epic;
      const created=await api(projectUrl(projectId,'/epics'),{method:'POST',body:JSON.stringify({title})});
      data=await reloadProjectTasks(projectId);
      epic=(data.epics||[]).find(entry=>entry.id===(created.epic&&created.epic.id));
      return epic||created.epic;
    }

    async function ensureQuickTaskEpic(projectId){
      return ensureProjectEpic(projectId,'Quick tasks');
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
        showToast('AI batch execution task created. Starting session...',2400);
        await executeTaskMatch(project,match);
      }finally{
        delete OPS.taskAutomationBusyByProject[projectKey];
        if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='project-detail'&&OPS.currentProject&&OPS.currentProject.id===projectKey){
          renderProjectDetail();
        }
      }
    }

    async function createQuickTask(projectId,text){
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
            await uploadQuickTaskImages(project.id,created.task.id,pendingQuickTaskImages);
          }catch(uploadErr){
            const message=uploadErr&&uploadErr.message?uploadErr.message:'Unable to upload screenshots.';
            OPS.quickTaskStatus=`Quick task created, but screenshots could not be uploaded: ${message}`;
            OPS.quickTaskStatusKind='warning';
            showToast(OPS.quickTaskStatus,4200);
            return;
          }
        }
        const data=await reloadProjectTasks(project.id);
        const match=findTaskInData(data,created.task&&created.task.id)||{epic,task:created.task};
        const pendingQuickTaskFiles=pendingQuickTaskImages.map(entry=>entry&&entry.file).filter(Boolean);
        OPS.quickTaskText='';
        clearQuickTaskImages();
        OPS.quickTaskStatus=goalMode?'Quick task created. Starting Hermes goal...':'Quick task created. Starting Hermes...';
        OPS.quickTaskStatusKind='info';
        if(windowRef&&windowRef._opsDashboardOpen&&OPS.view==='home')renderHome();
        try{
          await executeTaskMatch(project,match,{files:pendingQuickTaskFiles,goalMode});
          OPS.quickTaskStatus=goalMode?'Quick task created and goal started.':'Quick task created and execution started.';
          OPS.quickTaskStatusKind='success';
        }catch(execErr){
          const message=execErr&&execErr.message?execErr.message:'Unable to start the task session.';
          OPS.quickTaskStatus=`Quick task created, but execution did not start: ${message}`;
          OPS.quickTaskStatusKind='warning';
          showToast(OPS.quickTaskStatus,4200);
        }
      }catch(err){
        OPS.quickTaskStatus=err&&err.message?err.message:'Unable to create the quick task.';
        OPS.quickTaskStatusKind='error';
        throw err;
      }finally{
        OPS.quickTaskBusy=false;
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

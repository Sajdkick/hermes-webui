(function(){
  function q(params={}){
    const entries=Object.entries(params).filter(([,value])=>value!==undefined&&value!==null&&value!=='');
    if(!entries.length) return '';
    return `?${new URLSearchParams(entries.map(([key,value])=>[key,String(value)])).toString()}`;
  }

  const legacyNotificationCompatState={
    dismissed:new Set(),
    index:new Map(),
    settings:{
      inAppEnabled:true,
      soundEnabled:false,
      pushEnabled:false,
    },
    autoApprovalPolicy:{
      enabled:false,
      rules:[],
    },
    subscriptions:[],
    logs:[],
  };

  function cloneCompat(value){
    return value==null ? value : JSON.parse(JSON.stringify(value));
  }

  function compatProjectUrl(projectId,suffix=''){
    if(typeof projectUrl==='function') return projectUrl(projectId,suffix);
    return `/api/ops/projects/${encodeURIComponent(String(projectId||'').trim())}${String(suffix||'')}`;
  }

  function compatNotificationTimestamp(value){
    if(Number.isFinite(Number(value))&&Number(value)>0) return Number(value);
    const parsed=Date.parse(String(value||'').trim());
    if(Number.isFinite(parsed)&&parsed>0) return Math.floor(parsed/1000);
    return Math.floor(Date.now()/1000);
  }

  function compatNotificationId(item){
    const direct=String(item&&((item.notificationKey)||(item.id))||'').trim();
    if(direct) return direct;
    const kind=String(item&&item.kind||'notification').trim()||'notification';
    const sessionId=String(item&&item.sessionId||item&&item.session_id||'').trim();
    const detailId=String(item&&item.approvalId||item&&item.requestedAt||item&&item.task&&item.task.id||'').trim();
    return [kind,sessionId,detailId].filter(Boolean).join(':')||`notification:${Date.now().toString(36)}`;
  }

  function compatNotificationLog(event, notificationId=''){
    legacyNotificationCompatState.logs.unshift({
      event:String(event||'event').trim()||'event',
      notificationId:String(notificationId||'').trim(),
      created_at:Math.floor(Date.now()/1000),
    });
    legacyNotificationCompatState.logs=legacyNotificationCompatState.logs.slice(0,20);
  }

  function mapCompatNotification(item){
    const source=item&&typeof item==='object'?item:{};
    const kind=String(source.kind||'').trim().toLowerCase();
    const notificationId=compatNotificationId(source);
    const projectId=String(source.project&&source.project.id||'').trim();
    const projectName=String(source.project&&source.project.name||projectId||'').trim();
    const taskId=String(source.task&&source.task.id||'').trim();
    const taskText=String(source.task&&source.task.text||taskId||'').trim();
    const sessionId=String(source.sessionId||source.session_id||'').trim();
    const createdAt=compatNotificationTimestamp(source.requestedAt||source.expiresAt||0);
    const isApproval=kind==='approval';
    const payload=isApproval
      ? {
          command:String(source.command||'').trim(),
          description:String(source.description||'').trim(),
          choices_offered:['once','session','always','deny'],
          pattern_keys:Array.isArray(source.patternKeys)?source.patternKeys.slice():[],
          projectId,
          projectName,
          taskId,
          sessionId,
        }
      : {
          question:String(source.question||'').trim(),
          choices_offered:Array.isArray(source.choices)?source.choices.slice():[],
          projectId,
          projectName,
          taskId,
          sessionId,
        };
    return {
      id:notificationId,
      kind:'input',
      input_kind:isApproval?'approval':'clarify',
      message:isApproval
        ? (String(source.description||'').trim()||'Session needs approval.')
        : (String(source.question||'').trim()||'Session needs clarification.'),
      session_id:sessionId,
      project_id:projectId,
      task_id:taskId,
      project_name:projectName,
      session_title:String(source.session&&source.session.title||taskText||sessionId||'Session').trim()||'Session',
      created_at:createdAt,
      updated_at:createdAt,
      payload,
    };
  }

  async function listCompatNotifications(){
    const response=await api('/api/ops/notifications/pending').catch(()=>({notifications:[]}));
    const items=Array.isArray(response&&response.notifications)?response.notifications:[];
    legacyNotificationCompatState.index.clear();
    const notifications=[];
    items.forEach(item=>{
      const mapped=mapCompatNotification(item);
      legacyNotificationCompatState.index.set(mapped.id, item);
      if(!legacyNotificationCompatState.dismissed.has(mapped.id)){
        notifications.push(mapped);
      }
    });
    return {notifications};
  }

  function compatNotificationMonitorSnapshot(openCount){
    return {
      healthy:true,
      counts:{
        open:Number(openCount)||0,
        visible:Number(openCount)||0,
        pushSubscriptions:legacyNotificationCompatState.subscriptions.length,
        logs:legacyNotificationCompatState.logs.length,
      },
      pushConfigured:false,
      lastLog:legacyNotificationCompatState.logs[0]||null,
    };
  }

  function bridgeSessionKey(sessionLike){
    if(!sessionLike) return '';
    if(typeof sessionLike==='string') return String(sessionLike).trim();
    return String(sessionLike.sessionKey||sessionLike.session_key||sessionLike.session_id||sessionLike.sessionId||'').trim();
  }

  async function resolveBridgeSessionId(sessionLike, options={}){
    const key=bridgeSessionKey(sessionLike);
    if(!key) return '';
    const directId=(sessionLike&&typeof sessionLike==='object')
      ? String(sessionLike.session_id||sessionLike.sessionId||'').trim()
      : key;
    if(directId&&directId===key) return directId;
    const sessions=Array.isArray(options.sessions)?options.sessions:(((await api('/api/sessions')).sessions)||[]);
    const match=sessions.find(session=>{
      const sessionKey=bridgeSessionKey(session);
      const sessionId=String(session&&session.session_id||session&&session.sessionId||'').trim();
      return sessionKey===key||sessionId===key;
    });
    return String(match&&match.session_id||match&&match.sessionId||directId||key).trim();
  }

  async function resolveSessionPayload(payload){
    const body=(payload&&typeof payload==='object')?{...payload}:{};
    const sessionRef=body.sessionKey||body.session_id||body.sessionId||'';
    if(!sessionRef) return body;
    const resolvedId=await resolveBridgeSessionId({
      sessionKey:body.sessionKey||'',
      session_id:body.session_id||body.sessionId||'',
    });
    if(resolvedId){
      body.session_id=resolvedId;
    }
    delete body.sessionId;
    return body;
  }

  function directSessionId(sessionLike){
    if(!sessionLike) return '';
    if(typeof sessionLike==='string') return String(sessionLike).trim();
    return String(sessionLike.session_id||sessionLike.sessionId||'').trim();
  }

  function upstreamSyncRecordKey(sessionLike){
    if(!sessionLike) return '';
    if(typeof sessionLike==='string') return '';
    return String(sessionLike.upstreamSyncRecordKey||sessionLike.recordKey||sessionLike.record_key||'').trim();
  }

  async function multipart(path, formData){
    const res=await fetch(new URL(path,location.href).href,{method:'POST',credentials:'include',body:formData});
    const data=await res.json().catch(async()=>{
      try{
        const text=await res.text();
        return text?{error:text}:{};
      }catch(_){
        return {};
      }
    });
    if(!res.ok||data.error){
      throw new Error(data.error||`Request failed (${res.status})`);
    }
    return data;
  }

  window.AgentBridge={
    streams:{
      async start(payload){
        const body=await resolveSessionPayload(payload);
        return api('/api/chat/start',{method:'POST',body:JSON.stringify(body||{})});
      },
      async runSync(payload){
        const body=await resolveSessionPayload(payload);
        return api('/api/chat',{method:'POST',body:JSON.stringify(body||{})});
      },
      status(streamId){
        return api(`/api/chat/stream/status${q({stream_id:streamId})}`);
      },
      open(streamId, options={}){
        const url=new URL(`api/chat/stream?stream_id=${encodeURIComponent(streamId)}`,location.href);
        const cursor=Number(options.cursor);
        if(Number.isFinite(cursor)&&cursor>0) url.searchParams.set('cursor', String(cursor));
        if(options.bridge!==false) url.searchParams.set('bridge','1');
        return new EventSource(url.href,{withCredentials:true});
      },
      parseFrame(event){
        let frame={};
        try{ frame=JSON.parse(event&&event.data||'{}'); }catch(_){}
        const eventId=Number(frame&&frame.eventId);
        return {
          type:String(frame&&frame.type||'message'),
          payload:(frame&&Object.prototype.hasOwnProperty.call(frame,'payload'))?frame.payload:{},
          eventId:Number.isFinite(eventId)?eventId:null,
          terminal:!!(frame&&frame.terminal),
        };
      },
      cancel(streamId){
        return api(`/api/chat/cancel${q({stream_id:streamId})}`);
      },
    },
    sessions:{
      sessionKey(sessionLike){
        return bridgeSessionKey(sessionLike);
      },
      async resolveId(sessionLike, options={}){
        return resolveBridgeSessionId(sessionLike, options);
      },
      async get(sessionId){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api(`/api/session?session_id=${encodeURIComponent(resolvedId)}`);
      },
      async status(sessionId){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api(`/api/session/status${q({session_id:resolvedId})}`);
      },
      async usage(sessionId){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api(`/api/session/usage${q({session_id:resolvedId})}`);
      },
      listPersonalities(){
        return api('/api/personalities');
      },
      async setPersonality(sessionId,name){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/personality/set',{method:'POST',body:JSON.stringify({session_id:resolvedId,name})});
      },
      async gitInfo(sessionId){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api(`/api/git-info${q({session_id:resolvedId})}`);
      },
      async listDir(sessionId,path='.'){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api(`/api/list${q({session_id:resolvedId,path})}`);
      },
      async readFile(sessionId,path){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api(`/api/file${q({session_id:resolvedId,path})}`);
      },
      downloadUrl(sessionId,path,options={}){
        const rawId=directSessionId(sessionId)||bridgeSessionKey(sessionId)||String(sessionId||'').trim();
        return `api/file/raw${q({session_id:rawId,path,download:options.download?1:''})}`;
      },
      list(){
        return api('/api/sessions');
      },
      search(params={}){
        return api(`/api/sessions/search${q(params)}`);
      },
      async uploadFile(sessionId,file){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        const fd=new FormData();
        fd.append('session_id',resolvedId);
        fd.append('file',file,file&&file.name?file.name:'upload.bin');
        return multipart('api/upload',fd);
      },
      async transcribeAudio(file, options={}){
        const fd=new FormData();
        const filename=String(options&&options.filename||file&&file.name||'voice-input.webm').trim()||'voice-input.webm';
        fd.append('file',file,filename);
        return multipart('api/transcribe',fd);
      },
      create(payload){
        return api('/api/session/new',{method:'POST',body:JSON.stringify(payload||{})});
      },
      exportUrl(sessionId){
        const rawId=directSessionId(sessionId)||bridgeSessionKey(sessionId)||String(sessionId||'').trim();
        return `/api/session/export?session_id=${encodeURIComponent(rawId)}`;
      },
      importData(payload){
        return api('/api/session/import',{method:'POST',body:JSON.stringify(payload||{})});
      },
      grouped(){
        return api('/api/sessions').then(fallback=>({
          sessions:Array.isArray(fallback&&fallback.sessions)?fallback.sessions:[],
          groups:[],
        }));
      },
      openGatewayStream(){
        return new EventSource('api/sessions/gateway/stream');
      },
      async readableOutput(sessionId, entryId=''){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        const normalizedEntryId=String(entryId||'').trim();
        const path=normalizedEntryId
          ? `/api/sessions/${encodeURIComponent(resolvedId)}/readable-output/entries/${encodeURIComponent(normalizedEntryId)}`
          : `/api/sessions/${encodeURIComponent(resolvedId)}/readable-output`;
        return api(path);
      },
      async approvalPending(sessionId){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api(`/api/approval/pending${q({session_id:resolvedId})}`);
      },
      async respondApproval(payload){
        const body=await resolveSessionPayload(payload);
        return api('/api/approval/respond',{method:'POST',body:JSON.stringify(body||{})});
      },
      async clarifyPending(sessionId){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api(`/api/clarify/pending${q({session_id:resolvedId})}`);
      },
      async respondClarify(payload){
        const body=await resolveSessionPayload(payload);
        return api('/api/clarify/respond',{method:'POST',body:JSON.stringify(body||{})});
      },
      async rename(sessionId,title){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/session/rename',{method:'POST',body:JSON.stringify({session_id:resolvedId,title})});
      },
      async update(payload){
        const body=await resolveSessionPayload(payload);
        return api('/api/session/update',{method:'POST',body:JSON.stringify(body||{})});
      },
      async truncate(sessionId,keepCount){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/session/truncate',{method:'POST',body:JSON.stringify({session_id:resolvedId,keep_count:keepCount})});
      },
      async compress(payload){
        const body=await resolveSessionPayload(payload);
        return api('/api/session/compress',{method:'POST',body:JSON.stringify(body||{})});
      },
      async deleteFile(sessionId,path){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/file/delete',{method:'POST',body:JSON.stringify({session_id:resolvedId,path})});
      },
      async saveFile(sessionId,path,content){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/file/save',{method:'POST',body:JSON.stringify({session_id:resolvedId,path,content})});
      },
      async createFile(sessionId,path,content=''){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/file/create',{method:'POST',body:JSON.stringify({session_id:resolvedId,path,content})});
      },
      async renameFile(sessionId,path,newName){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/file/rename',{method:'POST',body:JSON.stringify({session_id:resolvedId,path,new_name:newName})});
      },
      async createDir(sessionId,path){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/file/create-dir',{method:'POST',body:JSON.stringify({session_id:resolvedId,path})});
      },
      async retry(sessionId){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/session/retry',{method:'POST',body:JSON.stringify({session_id:resolvedId})});
      },
      async undo(sessionId){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/session/undo',{method:'POST',body:JSON.stringify({session_id:resolvedId})});
      },
      async remove(sessionId){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/session/delete',{method:'POST',body:JSON.stringify({session_id:resolvedId})});
      },
      async clear(sessionId){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/session/clear',{method:'POST',body:JSON.stringify({session_id:resolvedId})});
      },
      async pin(sessionId,pinned){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/session/pin',{method:'POST',body:JSON.stringify({session_id:resolvedId,pinned})});
      },
      async archive(sessionId,archived){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/session/archive',{method:'POST',body:JSON.stringify({session_id:resolvedId,archived})});
      },
      async move(sessionId,projectId){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/session/move',{method:'POST',body:JSON.stringify({session_id:resolvedId,project_id:projectId??null})});
      },
      async importCli(sessionId){
        const resolvedId=await resolveBridgeSessionId(sessionId);
        return api('/api/session/import_cli',{method:'POST',body:JSON.stringify({session_id:resolvedId})});
      },
      ensureTask(projectId,taskId,payload){
        return api(compatProjectUrl(projectId,`/tasks/${encodeURIComponent(taskId)}/session/ensure`),{method:'POST',body:JSON.stringify(payload||{})});
      },
      closeTask(projectId,taskId,payload){
        return api(compatProjectUrl(projectId,`/tasks/${encodeURIComponent(taskId)}/session/close`),{method:'POST',body:JSON.stringify(payload||{})});
      },
      completeTask(projectId,taskId,payload){
        return api(compatProjectUrl(projectId,`/tasks/${encodeURIComponent(taskId)}/complete`),{method:'POST',body:JSON.stringify(payload||{})});
      },
    },
    runs:{
      list(params={}){
        return api(`/api/ops/runs${q(params)}`);
      },
      staleScan(payload){
        return api('/api/ops/runs/stale-scan',{method:'POST',body:JSON.stringify(payload||{})});
      },
      get(runId){
        return api(`/api/ops/runs/${encodeURIComponent(runId)}`);
      },
      update(runId,payload){
        return api(`/api/ops/runs/${encodeURIComponent(runId)}`,{method:'POST',body:JSON.stringify(payload||{})});
      },
      complete(runId,payload){
        return api(`/api/ops/runs/${encodeURIComponent(runId)}/complete`,{method:'POST',body:JSON.stringify(payload||{})});
      },
      events(runId,params={}){
        return api(`/api/ops/runs/${encodeURIComponent(runId)}/events${q(params)}`);
      },
      createEvent(runId,payload){
        return api(`/api/ops/runs/${encodeURIComponent(runId)}/events`,{method:'POST',body:JSON.stringify(payload||{})});
      },
      logs(runId,params={}){
        return api(`/api/ops/runs/${encodeURIComponent(runId)}/logs${q(params)}`);
      },
      requests(runId,params={}){
        return api(`/api/ops/runs/${encodeURIComponent(runId)}/requests${q(params)}`);
      },
      respondRequest(runId,requestId,payload){
        return api(`/api/ops/runs/${encodeURIComponent(runId)}/requests/${encodeURIComponent(requestId)}/respond`,{method:'POST',body:JSON.stringify(payload||{})});
      },
      readableOutput(runId){
        return api(`/api/ops/runs/${encodeURIComponent(runId)}/readable-output`);
      },
      artifacts(runId,params={}){
        return api(`/api/ops/runs/${encodeURIComponent(runId)}/artifacts${q(params)}`);
      },
      createArtifact(runId,payload){
        return api(`/api/ops/runs/${encodeURIComponent(runId)}/artifacts`,{method:'POST',body:JSON.stringify(payload||{})});
      },
      create(payload){
        return api('/api/ops/runs',{method:'POST',body:JSON.stringify(payload||{})});
      },
    },
    notifications:{
      async list(){
        const data=await listCompatNotifications();
        return {notifications:data.notifications};
      },
      settings(){
        return Promise.resolve({settings:cloneCompat(legacyNotificationCompatState.settings)});
      },
      async monitor(){
        const data=await listCompatNotifications();
        return compatNotificationMonitorSnapshot(data.notifications.length);
      },
      logs(params={}){
        const limit=Math.max(1,Number(params&&params.limit)||5);
        return Promise.resolve({logs:cloneCompat(legacyNotificationCompatState.logs.slice(0,limit))});
      },
      pushSubscriptions(_params={}){
        return Promise.resolve({subscriptions:cloneCompat(legacyNotificationCompatState.subscriptions)});
      },
      pushStatus(){
        return Promise.resolve({
          available:false,
          missing:['Push delivery is not configured in the restart branch yet.'],
          vapidPublicKey:'',
        });
      },
      autoApproval(){
        return Promise.resolve({policy:cloneCompat(legacyNotificationCompatState.autoApprovalPolicy)});
      },
      saveSettings(payload){
        const body=payload&&typeof payload==='object'?payload:{};
        legacyNotificationCompatState.settings={
          ...legacyNotificationCompatState.settings,
          ...body,
        };
        compatNotificationLog('settings.saved');
        return Promise.resolve({ok:true,settings:cloneCompat(legacyNotificationCompatState.settings)});
      },
      saveAutoApproval(payload){
        const body=payload&&typeof payload==='object'?payload:{};
        const policy=body.policy&&typeof body.policy==='object'?body.policy:{enabled:false,rules:[]};
        legacyNotificationCompatState.autoApprovalPolicy={
          enabled:policy.enabled!==false,
          rules:Array.isArray(policy.rules)?cloneCompat(policy.rules):[],
        };
        compatNotificationLog('auto-approval.saved');
        return Promise.resolve({ok:true,policy:cloneCompat(legacyNotificationCompatState.autoApprovalPolicy)});
      },
      clearLogs(){
        legacyNotificationCompatState.logs=[];
        return Promise.resolve({ok:true});
      },
      savePushSubscription(payload){
        const body=payload&&typeof payload==='object'?payload:{};
        const id=String(body.id||body.endpoint||`subscription-${Date.now().toString(36)}`).trim();
        legacyNotificationCompatState.subscriptions=legacyNotificationCompatState.subscriptions
          .filter(item=>String(item&&item.id||'').trim()!==id);
        legacyNotificationCompatState.subscriptions.unshift({...body,id});
        compatNotificationLog('push.subscription.saved',id);
        return Promise.resolve({ok:true,id});
      },
      deletePushSubscription(id){
        const target=String(id||'').trim();
        legacyNotificationCompatState.subscriptions=legacyNotificationCompatState.subscriptions
          .filter(item=>String(item&&item.id||'').trim()!==target);
        compatNotificationLog('push.subscription.deleted',target);
        return Promise.resolve({ok:true});
      },
      sendPush(payload){
        return Promise.reject(new Error('Push delivery is not configured in the restart branch yet.'));
      },
      async respond(id,payload){
        const notificationId=String(id||'').trim();
        const source=legacyNotificationCompatState.index.get(notificationId);
        if(!source) throw new Error('Notification not found');
        const body=payload&&typeof payload==='object'?{...payload}:{};
        const response=await api('/api/ops/notifications/respond',{
          method:'POST',
          body:JSON.stringify({
            kind:String(source.kind||'').trim().toLowerCase(),
            sessionId:String(source.sessionId||source.session_id||'').trim(),
            approvalId:String(source.approvalId||'').trim(),
            choice:body.choice,
            response:body.response||body.answer||body.choice,
          }),
        });
        legacyNotificationCompatState.dismissed.add(notificationId);
        compatNotificationLog('notification.responded',notificationId);
        return response;
      },
      dismiss(id){
        const notificationId=String(id||'').trim();
        legacyNotificationCompatState.dismissed.add(notificationId);
        compatNotificationLog('notification.dismissed',notificationId);
        return Promise.resolve({ok:true});
      },
    },
    play:{
      config(projectId){
        return api(compatProjectUrl(projectId,'/play/config'));
      },
      saveConfig(projectId,payload){
        return api(compatProjectUrl(projectId,'/play/config'),{method:'POST',body:JSON.stringify(payload||{})});
      },
      status(projectId){
        return api(compatProjectUrl(projectId,'/play/status'));
      },
      logs(projectId, limit=1000){
        return api(compatProjectUrl(projectId,`/play/logs${q({limit})}`));
      },
      start(projectId,payload){
        return api(compatProjectUrl(projectId,'/play/start'),{method:'POST',body:JSON.stringify(payload||{})});
      },
      restart(projectId,payload){
        return api(compatProjectUrl(projectId,'/play/restart'),{method:'POST',body:JSON.stringify(payload||{})});
      },
      stop(projectId){
        return api(compatProjectUrl(projectId,'/play/stop'),{method:'POST',body:JSON.stringify({})});
      },
      notificationTarget(notificationId){
        return api(`/api/notifications/${encodeURIComponent(notificationId)}/play-target`);
      },
    },
    runtime:{
      gatherReports(projectId, params={}){
        return api(compatProjectUrl(projectId,`/runtime/gather/reports${q(params)}`));
      },
      reviewRequests(projectId, params={}){
        return api(compatProjectUrl(projectId,`/runtime/inspect/reviews${q(params)}`));
      },
      screenshot(projectId,payload){
        return api(compatProjectUrl(projectId,'/runtime/inspect/screenshot'),{method:'POST',body:JSON.stringify(payload||{})});
      },
    },
    profiles:{
      list(){
        return api('/api/profiles');
      },
      settings(){
        return api('/api/settings');
      },
      saveSettings(payload){
        return api('/api/settings',{method:'POST',body:JSON.stringify(payload||{})});
      },
      authStatus(){
        return api('/api/auth/status');
      },
      logout(){
        return api('/api/auth/logout',{method:'POST',body:'{}'});
      },
      onboardingStatus(){
        return api('/api/onboarding/status');
      },
      onboardingSetup(payload){
        return api('/api/onboarding/setup',{method:'POST',body:JSON.stringify(payload||{})});
      },
      onboardingComplete(){
        return api('/api/onboarding/complete',{method:'POST',body:'{}'});
      },
      oauthProviders(){
        return api('/api/providers/oauth');
      },
      startOauth(providerId){
        return api(`/api/providers/oauth/${encodeURIComponent(providerId)}/start`,{method:'POST',body:'{}'});
      },
      pollOauth(providerId,sessionId){
        return api(`/api/providers/oauth/${encodeURIComponent(providerId)}/poll/${encodeURIComponent(sessionId)}`);
      },
      listSkills(){
        return api('/api/skills');
      },
      getSkillContent(name,file=''){
        return api(`/api/skills/content${q({name,file})}`);
      },
      saveSkill(payload){
        return api('/api/skills/save',{method:'POST',body:JSON.stringify(payload||{})});
      },
      deleteSkill(name){
        return api('/api/skills/delete',{method:'POST',body:JSON.stringify({name})});
      },
      modelCatalog(){
        return api('/api/models');
      },
      setDefaultModel(model){
        return api('/api/default-model',{method:'POST',body:JSON.stringify({model})});
      },
      reasoningSettings(){
        return api('/api/reasoning');
      },
      setReasoningEffort(effort){
        return api('/api/reasoning',{method:'POST',body:JSON.stringify({effort})});
      },
      bulkDefaultModel(payload){
        return api('/api/profiles/default-model/bulk',{method:'POST',body:JSON.stringify(payload||{})});
      },
      switch(name){
        return api('/api/profile/switch',{method:'POST',body:JSON.stringify({name})});
      },
      create(payload){
        return api('/api/profile/create',{method:'POST',body:JSON.stringify(payload||{})});
      },
      update(payload){
        return api('/api/profile/update',{method:'POST',body:JSON.stringify(payload||{})});
      },
      delete(name){
        return api('/api/profile/delete',{method:'POST',body:JSON.stringify({name})});
      },
      active(){
        return api('/api/profile/active');
      },
      readMemory(){
        return api('/api/memory');
      },
      writeMemory(payload){
        return api('/api/memory/write',{method:'POST',body:JSON.stringify(payload||{})});
      },
      codexStatus(){
        return api('/api/codex/status');
      },
      codexUpdate(){
        return api('/api/codex/update',{method:'POST',body:'{}'});
      },
      codexRefreshModels(){
        return api('/api/codex/models/refresh',{method:'POST',body:'{}'});
      },
    },
    system:{
      startUpstreamSync(payload){
        return api('/api/upstream-sync/start',{method:'POST',body:JSON.stringify(payload||{})});
      },
      async upstreamSyncStatus(sessionLike){
        const recordKey=upstreamSyncRecordKey(sessionLike);
        const sessionId=recordKey?'':(directSessionId(sessionLike)||bridgeSessionKey(sessionLike));
        return api(`/api/upstream-sync/status${q({record_key:recordKey,session_id:sessionId})}`);
      },
      async applyUpstreamSync(payload){
        const body=(payload&&typeof payload==='object')?{...payload}:{};
        const recordKey=upstreamSyncRecordKey(body);
        const sessionId=recordKey?'':(directSessionId(body)||bridgeSessionKey(body.sessionKey||body.session_id||body.sessionId||''));
        if(recordKey){
          body.record_key=recordKey;
          delete body.session_id;
        }else if(sessionId) body.session_id=sessionId;
        delete body.sessionKey;
        delete body.sessionId;
        return api('/api/upstream-sync/apply',{method:'POST',body:JSON.stringify(body||{})});
      },
    },
  };
})();

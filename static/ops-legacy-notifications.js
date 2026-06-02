(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};
  let notificationPollTimer=null;
  const locallyDismissedNotificationIds=new Set();

  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const AgentBridgeRef=ctx&&ctx.AgentBridge;
    const renderCurrentOpsView=ctx&&ctx.renderCurrentOpsView;
    const showToast=ctx&&ctx.showToast;
    const esc=ctx&&ctx.esc;
    const svg=ctx&&ctx.svg;
    const openProjectDetail=ctx&&ctx.openProjectDetail;
    const openOpsSession=ctx&&ctx.openOpsSession;
    const openRunTarget=ctx&&ctx.openRunTarget;
    const loadRunDetail=ctx&&ctx.loadRunDetail;
    const loadOpsRuns=ctx&&ctx.loadOpsRuns;
    const windowRef=(ctx&&ctx.windowRef)||window;
    const documentRef=(ctx&&ctx.documentRef)||document;
    const NotificationRef=(ctx&&ctx.NotificationRef)||windowRef.Notification;
    const navigatorRef=(ctx&&ctx.navigatorRef)||windowRef.navigator;
    if(!OPS||!AgentBridgeRef||!AgentBridgeRef.notifications||!AgentBridgeRef.runs||!AgentBridgeRef.sessions||typeof renderCurrentOpsView!=='function'||typeof showToast!=='function'||typeof esc!=='function'||!svg){
      return {};
    }

    function sessionRefValue(ref){
      if(!ref)return '';
      if(typeof ref==='string')return ref.trim();
      return String(ref.sessionKey||ref.session_id||ref.sessionId||'').trim();
    }

    function isHomeQuickTaskFieldActive(){
      if(OPS.view!=='home')return false;
      const active=documentRef&&documentRef.activeElement;
      if(!active||typeof active.closest!=='function')return false;
      return !!active.closest('[data-ops-quick-field]');
    }

    function startNotificationPolling(){
      if(notificationPollTimer)return;
      notificationPollTimer=setInterval(async()=>{
        if(!windowRef._opsDashboardOpen||OPS.notificationPollBusy)return;
        OPS.notificationPollBusy=true;
        try{
          await loadNotifications();
          if(OPS.view==='home'&&!isHomeQuickTaskFieldActive())renderCurrentOpsView();
        }catch(e){
          // Keep polling quiet; explicit refresh surfaces errors.
        }finally{
          OPS.notificationPollBusy=false;
        }
      },5000);
    }

    function stopNotificationPolling(){
      if(!notificationPollTimer)return;
      clearInterval(notificationPollTimer);
      notificationPollTimer=null;
    }

    function notificationIdValue(note){
      return String(note&&note.id||note&&note.notificationKey||'').trim();
    }

    function visibleNotificationsFrom(items){
      return (Array.isArray(items)?items:[]).filter(note=>{
        const id=notificationIdValue(note);
        return !id||!locallyDismissedNotificationIds.has(id);
      });
    }

    async function loadNotifications(){
      const data=await AgentBridgeRef.notifications.list();
      OPS.notifications=visibleNotificationsFrom(data.notifications);
      return OPS.notifications;
    }

    function normalizedAutoApprovalPolicy(){
      const policy=OPS.notificationAutoApprovalPolicy&&typeof OPS.notificationAutoApprovalPolicy==='object'
        ? OPS.notificationAutoApprovalPolicy
        : {enabled:false,rules:[]};
      const rules=Array.isArray(policy.rules)?policy.rules:[];
      return {
        enabled:policy.enabled!==false,
        rules:rules.map(rule=>({
          id:String(rule&&rule.id||'').trim(),
          label:String(rule&&rule.label||'').trim(),
          enabled:rule&&rule.enabled!==false,
          choice:String(rule&&rule.choice||'once').trim()||'once',
          match:rule&&rule.match&&typeof rule.match==='object'?rule.match:{},
        })).filter(rule=>rule.id||rule.label||Object.keys(rule.match).length),
      };
    }

    async function loadNotificationDiagnostics(options){
      const settings=options||{};
      OPS.notificationBusy=true;
      try{
        const includeMonitor=settings.includeMonitor!==false;
        const includeDetails=settings.lightweight!==true;
        const [notificationSettings,monitor,logs,subscriptions,pushStatus,autoApproval]=await Promise.all([
          AgentBridgeRef.notifications.settings(),
          includeMonitor?AgentBridgeRef.notifications.monitor():Promise.resolve(OPS.notificationMonitor||null),
          includeDetails?AgentBridgeRef.notifications.logs({limit:5}):Promise.resolve({logs:OPS.notificationLogs||[]}),
          includeDetails?AgentBridgeRef.notifications.pushSubscriptions().catch(()=>({subscriptions:[]})):Promise.resolve({subscriptions:OPS.notificationPushSubscriptions||[]}),
          includeDetails?AgentBridgeRef.notifications.pushStatus().catch(()=>null):Promise.resolve(OPS.notificationPushStatus||null),
          AgentBridgeRef.notifications.autoApproval().catch(()=>({policy:{enabled:false,rules:[]}})),
        ]);
        OPS.notificationSettings=notificationSettings;
        if(monitor)OPS.notificationMonitor=monitor;
        OPS.notificationLogs=Array.isArray(logs.logs)?logs.logs:[];
        OPS.notificationPushSubscriptions=Array.isArray(subscriptions.subscriptions)?subscriptions.subscriptions:[];
        OPS.notificationPushStatus=pushStatus;
        OPS.notificationAutoApprovalPolicy=(autoApproval&&autoApproval.policy)||{enabled:false,rules:[]};
        if(includeDetails){
          OPS.notificationBrowserPush=await readBrowserPushState(OPS.notificationPushSubscriptions,pushStatus).catch(error=>({
            supported:false,
            secure:false,
            permission:'',
            subscribed:false,
            canSubscribe:false,
            canUnsubscribe:false,
            reason:error&&error.message?error.message:'Browser push unavailable.',
          }));
        }
        return {settings:notificationSettings,monitor,logs,subscriptions,pushStatus,autoApproval};
      }finally{
        OPS.notificationBusy=false;
        if(!settings||settings.render!==false)renderCurrentOpsView();
      }
    }

    async function toggleNotificationSetting(setting){
      const key=String(setting||'').trim();
      if(!key)return;
      const current=(OPS.notificationSettings&&OPS.notificationSettings.settings)||{};
      OPS.notificationBusy=true;
      try{
        await AgentBridgeRef.notifications.saveSettings({[key]:!current[key]});
        await loadNotificationDiagnostics({render:false});
      }finally{
        OPS.notificationBusy=false;
        renderCurrentOpsView();
      }
    }

    async function saveAutoApprovalPolicy(policy){
      OPS.notificationBusy=true;
      try{
        await AgentBridgeRef.notifications.saveAutoApproval({policy});
        await loadNotificationDiagnostics({render:false});
      }finally{
        OPS.notificationBusy=false;
        renderCurrentOpsView();
      }
    }

    async function toggleAutoApprovalPolicy(){
      const policy=normalizedAutoApprovalPolicy();
      return saveAutoApprovalPolicy({...policy,enabled:!policy.enabled});
    }

    async function deleteAutoApprovalRule(ruleId){
      const id=String(ruleId||'').trim();
      if(!id)return;
      const policy=normalizedAutoApprovalPolicy();
      return saveAutoApprovalPolicy({...policy,rules:policy.rules.filter(rule=>rule.id!==id)});
    }

    async function createAutoApprovalRule(data){
      const ruleData=data&&typeof data==='object'?data:{};
      const label=String(ruleData.label||'').trim();
      const commandContains=String(ruleData.commandContains||'').trim();
      const choice=String(ruleData.choice||'once').trim()||'once';
      if(!commandContains)throw new Error('Command match text is required.');
      const policy=normalizedAutoApprovalPolicy();
      const ruleId=`rule-${Date.now().toString(36)}`;
      const nextRule={
        id:ruleId,
        label:label||commandContains,
        enabled:true,
        choice,
        match:{commandContains},
      };
      return saveAutoApprovalPolicy({...policy,rules:[...policy.rules,nextRule]});
    }

    async function clearNotificationLogs(){
      OPS.notificationBusy=true;
      try{
        await AgentBridgeRef.notifications.clearLogs();
        await loadNotificationDiagnostics({render:false});
      }finally{
        OPS.notificationBusy=false;
        renderCurrentOpsView();
      }
    }

    async function deletePushSubscription(subscriptionId){
      const id=String(subscriptionId||'').trim();
      if(!id)return;
      OPS.notificationBusy=true;
      try{
        await AgentBridgeRef.notifications.deletePushSubscription(id);
        await loadNotificationDiagnostics({render:false});
      }finally{
        OPS.notificationBusy=false;
        renderCurrentOpsView();
      }
    }

    function browserPushSupport(){
      const serviceWorker=!!(navigatorRef&&navigatorRef.serviceWorker);
      const secure=!!(windowRef&&windowRef.isSecureContext);
      const pushManager=!!(windowRef&&windowRef.PushManager);
      const notifications=!!NotificationRef;
      return {serviceWorker,secure,pushManager,notifications};
    }

    function browserPushReason(support,pushStatus){
      if(!support.secure)return 'Browser push requires a secure context.';
      if(!support.serviceWorker)return 'Service workers are not available in this browser.';
      if(!support.pushManager)return 'Push messaging is not available in this browser.';
      if(!support.notifications)return 'Notifications are not supported by this browser.';
      if(!(pushStatus&&pushStatus.available))return (pushStatus&&pushStatus.missing&&pushStatus.missing[0])||'Push delivery is not configured.';
      return '';
    }

    function urlBase64ToUint8Array(value){
      const padding='='.repeat((4-value.length%4)%4);
      const base64=(value+padding).replace(/-/g,'+').replace(/_/g,'/');
      const raw=windowRef.atob(base64);
      const output=new Uint8Array(raw.length);
      for(let index=0;index<raw.length;index++)output[index]=raw.charCodeAt(index);
      return output;
    }

    function pushSubscriptionPayload(subscription,label){
      return {
        label:String(label||'').trim()||'This browser',
        endpoint:String(subscription&&subscription.endpoint||'').trim(),
        subscription:subscription&&typeof subscription.toJSON==='function'?subscription.toJSON():subscription,
      };
    }

    async function currentPushRegistration(){
      if(!navigatorRef||!navigatorRef.serviceWorker)return null;
      return navigatorRef.serviceWorker.getRegistration();
    }

    async function readBrowserPushState(subscriptions,pushStatus){
      const support=browserPushSupport();
      const supported=support.secure&&support.serviceWorker&&support.pushManager&&support.notifications;
      const reason=browserPushReason(support,pushStatus);
      const registration=supported?await currentPushRegistration():null;
      const subscription=registration?await registration.pushManager.getSubscription():null;
      const endpoint=String(subscription&&subscription.endpoint||'').trim();
      const list=Array.isArray(subscriptions)?subscriptions:[];
      const existing=list.find(item=>String(item&&item.endpoint||'').trim()===endpoint)||null;
      return {
        supported,
        secure:support.secure,
        permission:support.notifications&&NotificationRef?NotificationRef.permission:'',
        subscribed:!!subscription,
        canSubscribe:supported&&!subscription&&reason==='',
        canUnsubscribe:!!subscription,
        endpoint,
        subscriptionId:existing&&existing.id?String(existing.id):'',
        reason,
      };
    }

    async function subscribeBrowserPush(){
      const status=OPS.notificationPushStatus||{};
      if(!status.vapidPublicKey)throw new Error('Push delivery is not configured.');
      OPS.notificationBusy=true;
      try{
        const registration=await navigatorRef.serviceWorker.register('static/hermes-push-sw.js');
        const permission=await NotificationRef.requestPermission();
        if(permission!=='granted')throw new Error('Notification permission was not granted.');
        const existing=await registration.pushManager.getSubscription();
        const subscription=existing||await registration.pushManager.subscribe({
          userVisibleOnly:true,
          applicationServerKey:urlBase64ToUint8Array(status.vapidPublicKey),
        });
        await AgentBridgeRef.notifications.savePushSubscription(pushSubscriptionPayload(subscription,'This browser'));
        const settings=(OPS.notificationSettings&&OPS.notificationSettings.settings)||{};
        if(!settings.pushEnabled){
          await AgentBridgeRef.notifications.saveSettings({pushEnabled:true});
        }
        showToast('Browser push subscribed',2600);
        return await loadNotificationDiagnostics({render:false});
      }finally{
        OPS.notificationBusy=false;
        renderCurrentOpsView();
      }
    }

    async function unsubscribeBrowserPush(){
      const browserPush=OPS.notificationBrowserPush||{};
      OPS.notificationBusy=true;
      try{
        const registration=await currentPushRegistration();
        const subscription=registration?await registration.pushManager.getSubscription():null;
        const endpoint=subscription&&subscription.endpoint?String(subscription.endpoint):String(browserPush.endpoint||'');
        if(subscription)await subscription.unsubscribe();
        const id=String(browserPush.subscriptionId||endpoint||'');
        if(id)await AgentBridgeRef.notifications.deletePushSubscription(id).catch(()=>null);
        showToast('Browser push unsubscribed',2600);
        return await loadNotificationDiagnostics({render:false});
      }finally{
        OPS.notificationBusy=false;
        renderCurrentOpsView();
      }
    }

    async function sendTestPushNotification(){
      OPS.notificationBusy=true;
      try{
        const data=await AgentBridgeRef.notifications.sendPush({
          title:'Hermes',
          body:'Test push notification from Hermes Web UI.',
          kind:'test',
          url:'/',
        });
        showToast(`Push delivery ${data.status||'finished'} (${data.sent||0} sent, ${data.failed||0} failed)`,3600);
        return await loadNotificationDiagnostics({render:false});
      }finally{
        OPS.notificationBusy=false;
        renderCurrentOpsView();
      }
    }

    function notificationPayload(note){
      return note&&note.payload&&typeof note.payload==='object'?note.payload:{};
    }

    function notificationTarget(note){
      const terminal=(note&&note.terminalTarget&&typeof note.terminalTarget==='object')
        ? note.terminalTarget
        : {};
      if(note&&note.kind==='play'){
        return {
          runId:String((note&&note.run_id)||terminal.runId||''),
          sessionId:String((note&&note.session_id)||terminal.sessionId||''),
          projectId:String((note&&note.project_id)||terminal.projectId||''),
          taskId:String((note&&note.task_id)||terminal.taskId||''),
        };
      }
      const legacyTerminal=(note&&note.terminal_target&&typeof note.terminal_target==='object')?note.terminal_target:{};
      const payload=notificationPayload(note);
      return {
        runId:String((note&&note.run_id)||payload.run_id||payload.runId||legacyTerminal.run_id||legacyTerminal.runId||terminal.runId||''),
        sessionId:String((note&&note.session_id)||payload.session_id||payload.sessionId||legacyTerminal.session_id||legacyTerminal.sessionId||terminal.sessionId||''),
        projectId:String((note&&note.project_id)||payload.project_id||payload.projectId||legacyTerminal.project_id||legacyTerminal.projectId||terminal.projectId||''),
        taskId:String((note&&note.task_id)||payload.task_id||payload.taskId||legacyTerminal.task_id||legacyTerminal.taskId||terminal.taskId||''),
      };
    }

    function notificationTitle(note){
      return note&&String(note.session_title||note.project_name||note.project_id||note.session_id||'Session').trim()||'Session';
    }

    function notificationProjectLabel(note){
      const payload=notificationPayload(note);
      const target=notificationTarget(note);
      const explicit=String(
        note&&note.project_name||
        payload.project_name||
        payload.projectName||
        ''
      ).trim();
      if(explicit)return explicit;
      const projectId=String(target.projectId||'').trim();
      if(!projectId)return '';
      const project=(OPS.projects||[]).find(item=>item&&item.id===projectId)||null;
      if(project){
        return String(project.name||project.fullName||project.slug||project.id||'').trim();
      }
      return projectId;
    }

    function notificationHasRunTarget(note){
      const target=notificationTarget(note);
      return !!(target.runId||target.sessionId||(target.projectId&&target.taskId));
    }

    function notificationHasSessionTarget(note){
      return !!notificationTarget(note).sessionId;
    }

    function notificationHasProjectTarget(note){
      return !!notificationTarget(note).projectId;
    }

    function notificationModeLabel(note){
      if(note&&note.kind==='play')return 'Play';
      if(notificationHasSessionTarget(note))return 'Session';
      if(notificationHasProjectTarget(note))return 'Project';
      return 'Notification';
    }

    function playNotificationInspectUrl(note){
      const raw=note&&note.inspectUrl;
      let value=String(raw||'').trim();
      if(!value)return '';
      if(/^[a-z][a-z0-9+.-]*:\/\//i.test(value))return value;
      if(/^(localhost|127\.0\.0\.1|0\.0\.0\.0|\[[^\]]+\]|[a-z0-9.-]+):\d+(\/|$)/i.test(value)){
        value=`http://${value}`;
      }
      try{
        const parsed=new URL(value,windowRef.location.origin);
        if(parsed.protocol==='http:'||parsed.protocol==='https:')return parsed.href;
      }catch(e){}
      return value;
    }

    function playInspectOverlayUrl(note){
      const inspectUrl=playNotificationInspectUrl(note||{});
      if(!inspectUrl)return '';
      return new URL(inspectUrl,windowRef.location.origin).href;
    }

    function playNotificationStatus(note){
      return String(note&&note.playStatus||'ready').trim();
    }

    function playNotificationFallbackError(note){
      return String(note&&note.playFallbackError||'').replace(/\s+/g,' ').trim();
    }

    function playNotificationLogText(note){
      const direct=String(note&&note.playLogText||note&&note.playLogsText||'').trim();
      if(direct)return direct;
      const entries=Array.isArray(note&&note.playLogs)?note.playLogs:[];
      return entries.map(entry=>{
        if(entry&&typeof entry==='object'){
          const at=String(entry.at||'').trim();
          const stage=String(entry.stage||'system').trim()||'system';
          const stream=String(entry.stream||'system').trim()||'system';
          const message=String(entry.message||'').trim();
          return `${at?`[${at}] `:''}[${stage}:${stream}] ${message}`;
        }
        return String(entry||'').trim();
      }).filter(Boolean).join('\n').trim();
    }

    function playNotificationNeedsRepair(note){
      if(note&&typeof note.playNeedsRepair==='boolean')return note.playNeedsRepair;
      const status=playNotificationStatus(note).toLowerCase();
      return status==='failed'||!!playNotificationFallbackError(note);
    }

    function playNotificationLocked(note){
      if(note&&note.playLocked===true)return true;
      const status=playNotificationStatus(note).toLowerCase();
      return status==='queued'||status==='building'||status==='starting';
    }

    function notificationTypeLabel(note){
      if(note&&note.kind==='play'){
        if(playNotificationLocked(note))return 'Play build';
        return playNotificationNeedsRepair(note)?'Play fallback':'Play ready';
      }
      if(note&&note.kind==='done')return 'Done';
      if(note&&note.kind==='input'){
        return note.input_kind==='approval'?'Approval':'Clarification';
      }
      return 'Notification';
    }

    function notificationTypeStyleKey(note){
      if(note&&note.kind==='play'){
        if(playNotificationLocked(note))return 'play-building';
        return playNotificationNeedsRepair(note)?'play-fallback':'play-ready';
      }
      if(note&&note.kind==='done')return 'agent-done';
      if(note&&note.kind==='input')return 'input-request';
      return 'default';
    }

    function renderNotificationResponseOption(note,attrs,label,description,preview){
      const attributeMap=attrs&&typeof attrs==='object'?attrs:{};
      const previewText=String(preview||'').trim();
      return `
        <button class="menu-notification-response-option" type="button" ${Object.entries(attributeMap).map(([key,value])=>`${key}="${esc(value)}"`).join(' ')}>
          <span class="menu-notification-response-option-label">${esc(label)}</span>
          ${description?`<span class="menu-notification-response-option-description">${esc(description)}</span>`:''}
          ${previewText?`<span class="menu-notification-response-option-preview">${esc(previewText)}</span>`:''}
        </button>
      `;
    }

    function notificationPrimaryAction(note){
      const id=String(note&&note.id||'').trim();
      if(!id)return null;
      if(note&&note.kind==='play'){
        if(playNotificationLocked(note))return null;
        const action=String(note&&note.playPrimaryAction||'').trim();
        const inspectUrl=playNotificationInspectUrl(note);
        if(inspectUrl||action==='open-inspect'||action==='start-inspect'||action==='restart-inspect'||playNotificationNeedsRepair(note)){
          return {action:'open-play-notification',label:'Play'};
        }
        if(action==='open-project'&&notificationHasProjectTarget(note)){
          return {action:'open-notification-target',label:'Open project'};
        }
      }
      if(notificationHasRunTarget(note)||notificationHasProjectTarget(note)){
        return {
          action:'open-notification-target',
          label:notificationHasSessionTarget(note)?'Open session':(notificationHasProjectTarget(note)?'Open project':'Open'),
        };
      }
      return null;
    }

    function renderNotificationMeta(entries){
      const values=(Array.isArray(entries)?entries:[]).map(value=>String(value||'').trim()).filter(Boolean);
      if(!values.length)return '';
      return `<div class="menu-notification-meta">${esc(values.join(' • '))}</div>`;
    }

    function renderNotificationOpenSurface(note,options){
      const opts=options&&typeof options==='object'?options:{};
      const primary=notificationPrimaryAction(note);
      const typeStyleKey=notificationTypeStyleKey(note);
      const projectLabel=notificationProjectLabel(note);
      const badges=`
        <div class="menu-notification-badges">
          <span class="menu-notification-type-badge menu-notification-type-badge--${esc(typeStyleKey)}">${esc(opts.badgeLabel||'Notification')}</span>
          ${opts.important?'<span class="menu-notification-type-badge menu-notification-type-badge--important">Important</span>':''}
        </div>
      `;
      const content=`
        <div class="menu-notification-heading">
          <div class="menu-notification-title">${esc(opts.title||'Notification')}</div>
          ${badges}
        </div>
        <div class="menu-notification-message">${esc(opts.message||'')}</div>
        ${opts.command?`<pre class="menu-notification-command">${esc(opts.command)}</pre>`:''}
        ${projectLabel?`<div class="menu-notification-meta">${esc(`Project: ${projectLabel}`)}</div>`:''}
        ${opts.extra||''}
        ${renderNotificationMeta(opts.meta)}
      `;
      if(!primary){
        return `<div class="menu-notification-open-btn menu-notification-open-btn--${esc(typeStyleKey)}">${content}</div>`;
      }
      return `
        <button class="menu-notification-open-btn menu-notification-open-btn--${esc(typeStyleKey)}" type="button" data-ops-action="${esc(primary.action)}" data-notification-id="${esc(note&&note.id||'')}" title="${esc(primary.label)}">
          ${content}
        </button>
      `;
    }

    function notificationMatchesRun(note,run){
      if(!note||!run)return false;
      const target=notificationTarget(note);
      const runId=String(run.id||'');
      const sessionId=String(run.session_id||run.sessionId||'');
      const projectId=String(run.project_id||run.projectId||'');
      const taskId=String(run.task_id||run.taskId||'');
      if(target.runId&&runId&&target.runId===runId)return true;
      if(target.sessionId&&sessionId&&target.sessionId===sessionId)return true;
      if(target.projectId&&target.taskId&&projectId&&taskId&&target.projectId===projectId&&target.taskId===taskId)return true;
      return false;
    }

    function pendingNotificationsForRun(run){
      return (OPS.notifications||[]).filter(note=>{
        if(!notificationMatchesRun(note,run))return false;
        if(note.kind!=='input')return false;
        return !note.status||note.status==='open';
      });
    }

    function formatNotificationTime(note){
      const stamp=(Number(note&&note.created_at)||Number(note&&note.updated_at)||0)*1000;
      if(!stamp)return 'Just now';
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

    function renderInputNotification(note){
      const payload=(note.payload&&typeof note.payload==='object')?note.payload:{};
      const isApproval=note.input_kind==='approval';
      const typeLabel=isApproval?'Approval':'Clarification';
      const choices=Array.isArray(payload.choices_offered)?payload.choices_offered:(Array.isArray(payload.choices)?payload.choices:[]);
      const approvalActions=isApproval?`
        <div class="menu-notification-response-panel">
          <div class="menu-notification-response-question">
            <div class="menu-notification-response-prompt">Choose how this approval should be handled.</div>
          </div>
          <div class="menu-notification-response-options">
            ${[
              ['once','Allow once','Approve only this request.'],
              ['session','Allow session','Approve matching requests until the session ends.'],
              ['always','Always allow','Approve this routine request every time.'],
              ['deny','Deny','Reject this request.'],
            ].map(([choice,label,description])=>renderNotificationResponseOption(note,{
              'data-ops-action':'respond-notification',
              'data-notification-id':String(note.id||''),
              'data-choice':choice,
            },label,description,'')).join('')}
          </div>
        </div>
      `:'';
      const clarifyActions=!isApproval?`
        <div class="menu-notification-response-panel">
          <div class="menu-notification-response-question">
            <div class="menu-notification-response-prompt">${esc(note.message||'Send the answer the agent is waiting for.')}</div>
          </div>
          ${choices.length?`<div class="menu-notification-response-options">
            ${choices.map(choice=>renderNotificationResponseOption(note,{
              'data-ops-action':'respond-notification',
              'data-notification-id':String(note.id||''),
              'data-response':String(choice||''),
            },String(choice||''),'Send this response.','')).join('')}
          </div>`:''}
          <form class="menu-notification-response-form" data-ops-submit="notification-response" data-notification-id="${esc(note.id)}">
            <input class="menu-notification-response-input" name="response" autocomplete="off" placeholder="Type your answer..." required>
            <button class="menu-action-btn small menu-notification-response-submit-btn" type="submit">Send</button>
          </form>
        </div>
      `:'';
      const meta=[
        notificationTitle(note),
        formatNotificationTime(note),
        notificationModeLabel(note),
        `Type: ${typeLabel}`,
      ];
      return `
        <article class="menu-notification-item menu-notification-item--input-request">
          <div class="menu-notification-body">
            ${renderNotificationOpenSurface(note,{
            badgeLabel:typeLabel,
            title:notificationTitle(note),
            message:note.message||'Session needs input.',
            command:payload.command,
            meta,
          })}
            ${approvalActions}
            ${clarifyActions}
          </div>
          <div class="menu-notification-actions">
            <button class="menu-action-btn secondary small menu-notification-dismiss-btn" type="button" data-ops-action="dismiss-notification" data-notification-id="${esc(note.id)}">Dismiss</button>
          </div>
        </article>
      `;
    }

    function renderDoneNotification(note){
      const payload=notificationPayload(note);
      const runStatus=String(note&&note.run_status||payload.status||'succeeded').trim().toLowerCase();
      const badgeLabel=runStatus==='failed'?'Failed':(runStatus==='stopped'?'Stopped':'Done');
      const meta=[
        notificationTitle(note),
        formatNotificationTime(note),
        notificationModeLabel(note),
        `Type: ${notificationTypeLabel(note)}`,
      ];
      return `
        <article class="menu-notification-item menu-notification-item--agent-done">
          <div class="menu-notification-body">
            ${renderNotificationOpenSurface(note,{
            badgeLabel,
            title:notificationTitle(note),
            message:note.message||'Session finished.',
            meta,
          })}
          </div>
          <div class="menu-notification-actions">
            <button class="menu-action-btn secondary small menu-notification-dismiss-btn" type="button" data-ops-action="dismiss-notification" data-notification-id="${esc(note.id)}">Dismiss</button>
          </div>
        </article>
      `;
    }

    function renderPlayNotification(note){
      const inspectUrl=playNotificationInspectUrl(note);
      const playStatus=playNotificationStatus(note);
      const fallbackError=playNotificationFallbackError(note);
      const playLogText=playNotificationLogText(note);
      const needsRepair=playNotificationNeedsRepair(note);
      const target=notificationTarget(note);
      const repairAvailable=!!(note&&note.playRepairAvailable);
      const meta=[
        notificationTitle(note),
        formatNotificationTime(note),
        notificationModeLabel(note),
        `Type: ${notificationTypeLabel(note)}`,
      ];
      if(playStatus)meta.push(playStatus);
      if(playNotificationLocked(note))meta.push('Locked until the Play build finishes');
      if(!inspectUrl&&!needsRepair&&!playNotificationLocked(note))meta.push('Inspect URL missing');
      return `
        <article class="menu-notification-item menu-notification-item--${esc(needsRepair?'play-fallback':'play-ready')}">
          <div class="menu-notification-body">
            ${renderNotificationOpenSurface(note,{
            badgeLabel:needsRepair?'Play fallback':'Play',
            title:notificationTitle(note),
            message:note.message||(needsRepair
              ? 'Play handoff failed. Open the project and repair Play with the captured error.'
              : 'Play finished building. The app is ready to inspect.'
            ),
            extra:needsRepair&&fallbackError?`<div class="menu-notification-fallback-error">${esc(`Play handoff error: ${fallbackError}`)}</div>`:'',
            meta,
          })}
            ${needsRepair&&playLogText?`<div class="menu-notification-play-log-panel"><div class="menu-notification-play-log-title">Play logs</div><pre class="menu-notification-play-log-scroll" data-ops-log-scroll-key="play-notification:${esc(note&&note.id||'')}">${esc(playLogText)}</pre></div>`:''}
          </div>
          <div class="menu-notification-actions">
            ${needsRepair&&repairAvailable&&target.projectId?`<button class="menu-action-btn secondary small menu-notification-repair-btn" type="button" data-ops-action="repair-play-notification" data-notification-id="${esc(note.id)}">Repair Play</button>`:''}
            <button class="menu-action-btn secondary small menu-notification-dismiss-btn" type="button" data-ops-action="dismiss-notification" data-notification-id="${esc(note.id)}">Dismiss</button>
          </div>
        </article>
      `;
    }

    function renderNotification(note){
      if(note.kind==='input')return renderInputNotification(note);
      if(note.kind==='play')return renderPlayNotification(note);
      return renderDoneNotification(note);
    }

    function renderNotifications(){
      const list=OPS.notifications||[];
      if(!list.length)return '<div class="menu-notification-empty">No notifications.</div>';
      return `
        <div class="menu-notification-list">
          ${list.map(renderNotification).join('')}
        </div>
      `;
    }

    function renderNotificationDiagnostics(){
      const settings=(OPS.notificationSettings&&OPS.notificationSettings.settings)||{};
      const monitor=OPS.notificationMonitor||{};
      const counts=monitor.counts||{};
      const logs=OPS.notificationLogs||[];
      const subscriptions=OPS.notificationPushSubscriptions||[];
      const pushStatus=OPS.notificationPushStatus||monitor.pushDelivery||{};
      const browserPush=OPS.notificationBrowserPush||{};
      const autoPolicy=normalizedAutoApprovalPolicy();
      const busy=OPS.notificationBusy;
      const latest=logs.length?logs[0]:monitor.lastLog;
      const latestText=latest?`${latest.event||'event'} ${latest.notificationId||''}`.trim():'No notification log entries.';
      const pushText=settings.pushEnabled
        ? `${pushStatus.available||monitor.pushConfigured?'Push delivery ready':(pushStatus.missing||[])[0]||'Push enabled, delivery not configured'}`
        : 'Push disabled';
      const subscriptionRows=subscriptions.length
        ? subscriptions.map(subscription=>`
            <div class="ops-notification-subscription-row">
              <span>${esc(subscription.label||subscription.userAgent||subscription.endpoint||subscription.id)}</span>
              <button class="ops-icon-btn danger" type="button" title="Remove push subscription" data-ops-action="delete-push-subscription" data-push-subscription-id="${esc(subscription.id)}">${svg.trash}</button>
            </div>
          `).join('')
        : '<div class="ops-notification-subscription-row empty"><span>No active push subscriptions.</span></div>';
      const browserPushText=browserPush.subscribed
        ? 'This browser is subscribed'
        : browserPush.reason||'This browser can subscribe';
      const subscribeDisabled=busy||!browserPush.canSubscribe;
      const unsubscribeDisabled=busy||!browserPush.canUnsubscribe;
      const autoRuleRows=autoPolicy.rules.length
        ? autoPolicy.rules.map(rule=>{
            const match=(rule&&rule.match&&typeof rule.match==='object')?rule.match:{};
            const matchText=match.commandContains?`Command contains "${match.commandContains}"`:(match.patternKey?`Pattern ${match.patternKey}`:'Routine approval');
            return `
              <div class="ops-auto-approval-rule-row">
                <div>
                  <strong>${esc(rule.label||rule.id||'Routine rule')}</strong>
                  <span>${esc(`${rule.enabled===false?'Disabled':'Enabled'} | ${rule.choice||'once'} | ${matchText}`)}</span>
                </div>
                <button class="ops-icon-btn danger" type="button" title="Remove auto-approval rule" data-ops-action="delete-auto-approval-rule" data-auto-approval-rule-id="${esc(rule.id||'')}">${svg.trash}</button>
              </div>
            `;
          }).join('')
        : '<div class="ops-auto-approval-rule-row empty"><span>No routine auto-approval rules.</span></div>';
      return `
        <section class="ops-panel ops-notification-diagnostics-panel">
          <div class="ops-panel-header">
            <div>
              <h2>Notification diagnostics</h2>
              <span>${esc(`${counts.open||0} open | ${counts.visible||0} visible | ${counts.pushSubscriptions||subscriptions.length||0} push | ${counts.logs||logs.length||0} logs`)}</span>
            </div>
            <div class="ops-notification-diagnostics-actions">
              <button class="ops-btn" type="button" data-ops-action="refresh-notification-diagnostics" ${busy?'disabled':''}>${svg.refresh}<span>Refresh</span></button>
              <button class="ops-btn" type="button" data-ops-action="toggle-notification-setting" data-setting-key="soundEnabled" ${busy?'disabled':''}>${settings.soundEnabled?svg.check:svg.close}<span>Sound</span></button>
              <button class="ops-btn" type="button" data-ops-action="toggle-notification-setting" data-setting-key="pushEnabled" ${busy?'disabled':''}>${settings.pushEnabled?svg.check:svg.close}<span>Push</span></button>
              <button class="ops-btn" type="button" data-ops-action="subscribe-browser-push" ${subscribeDisabled?'disabled':''}>${svg.plus}<span>Subscribe</span></button>
              <button class="ops-btn" type="button" data-ops-action="unsubscribe-browser-push" ${unsubscribeDisabled?'disabled':''}>${svg.trash}<span>Unsubscribe</span></button>
              <button class="ops-btn" type="button" data-ops-action="send-test-push" ${busy||!pushStatus.available?'disabled':''}>${svg.play}<span>Test push</span></button>
              <button class="ops-btn danger" type="button" data-ops-action="clear-notification-logs" ${busy?'disabled':''}>${svg.trash}<span>Clear logs</span></button>
            </div>
          </div>
          <div class="ops-notification-diagnostics-body">
            <span>${esc(settings.inAppEnabled===false?'In-app disabled':'In-app enabled')}</span>
            <span>${esc(pushText)}</span>
            <span>${esc(browserPushText)}</span>
            <span>${esc(monitor.healthy===false?'Needs attention':'Healthy')}</span>
            <span>${esc(latestText)}</span>
          </div>
          <div class="ops-notification-subscriptions">${subscriptionRows}</div>
          <div class="ops-auto-approval-panel">
            <div class="ops-auto-approval-header">
              <div>
                <strong>Routine auto-approval</strong>
                <span>${esc(autoPolicy.enabled?'Enabled':'Disabled')} | ${autoPolicy.rules.length} rule${autoPolicy.rules.length===1?'':'s'}</span>
              </div>
              <button class="ops-btn" type="button" data-ops-action="toggle-auto-approval-policy" ${busy?'disabled':''}>${autoPolicy.enabled?svg.check:svg.close}<span>${autoPolicy.enabled?'Enabled':'Disabled'}</span></button>
            </div>
            <div class="ops-auto-approval-rules">${autoRuleRows}</div>
            <form class="ops-auto-approval-form" data-ops-submit="auto-approval-rule">
              <input name="label" autocomplete="off" placeholder="Rule label">
              <input name="commandContains" autocomplete="off" required placeholder="Command contains...">
              <select name="choice">
                <option value="once">Allow once</option>
                <option value="session">Allow session</option>
                <option value="always">Always allow</option>
                <option value="deny">Deny</option>
              </select>
              <button class="ops-btn primary" type="submit" ${busy?'disabled':''}>${svg.plus}<span>Add rule</span></button>
            </form>
          </div>
        </section>
      `;
    }

    async function reloadRunsForCurrentView(){
      if(typeof loadOpsRuns!=='function')return;
      if(OPS.currentProject&&OPS.view==='project-detail')await loadOpsRuns({projectId:OPS.currentProject.id}).catch(()=>[]);
      else await loadOpsRuns().catch(()=>[]);
    }

    async function reloadSelectedRunDetail(runId){
      if(typeof loadRunDetail!=='function'||!runId)return;
      await loadRunDetail(runId).catch(()=>null);
    }

    async function respondNotification(notificationId,body){
      const id=String(notificationId||'').trim();
      if(!id)return;
      const note=(OPS.notifications||[]).find(item=>String(item&&item.id||'')===id)||null;
      const selectedRun=OPS.runDetail&&String(OPS.runDetail.id||'')===String(OPS.selectedRunId||'')?OPS.runDetail:null;
      const relatedToSelectedRun=selectedRun&&notificationMatchesRun(note,selectedRun);
      await AgentBridgeRef.notifications.respond(id,body||{});
      await loadNotifications();
      if(relatedToSelectedRun&&selectedRun){
        await AgentBridgeRef.runs.update(selectedRun.id,{
          status:'running',
          summary:'Pending input was answered from the ops dashboard.',
        }).catch(()=>null);
        await AgentBridgeRef.runs.createEvent(selectedRun.id,{
          type:'notification.responded',
          level:'info',
          message:'Pending input was answered from run detail.',
          source:'ops-dashboard',
          metadata:{notificationId:id,inputKind:note&&note.input_kind||''},
        }).catch(()=>null);
        await reloadSelectedRunDetail(selectedRun.id);
        await reloadRunsForCurrentView();
      }
      renderCurrentOpsView();
      showToast('Notification answered',2200);
    }

    function removeNotificationOptimistically(id){
      const notifications=Array.isArray(OPS.notifications)?OPS.notifications:[];
      const index=notifications.findIndex(item=>notificationIdValue(item)===id);
      if(index<0)return null;
      const note=notifications[index];
      OPS.notifications=[...notifications.slice(0,index),...notifications.slice(index+1)];
      locallyDismissedNotificationIds.add(id);
      renderCurrentOpsView();
      return {note,index};
    }

    function restoreOptimisticNotification(id,snapshot){
      locallyDismissedNotificationIds.delete(id);
      if(!snapshot||!snapshot.note)return;
      const notifications=Array.isArray(OPS.notifications)?OPS.notifications:[];
      if(notifications.some(item=>notificationIdValue(item)===id))return;
      const index=Math.max(0,Math.min(snapshot.index,notifications.length));
      OPS.notifications=[...notifications.slice(0,index),snapshot.note,...notifications.slice(index)];
      renderCurrentOpsView();
    }

    async function dismissNotification(notificationId){
      const id=String(notificationId||'').trim();
      if(!id)return;
      const snapshot=removeNotificationOptimistically(id);
      if(!snapshot){
        locallyDismissedNotificationIds.add(id);
        renderCurrentOpsView();
      }
      try{
        await AgentBridgeRef.notifications.dismiss(id);
        locallyDismissedNotificationIds.delete(id);
        await loadNotifications().catch(()=>OPS.notifications);
        renderCurrentOpsView();
      }catch(error){
        restoreOptimisticNotification(id,snapshot);
        throw error;
      }
    }

    function notificationById(notificationId){
      const id=String(notificationId||'').trim();
      return (OPS.notifications||[]).find(item=>String(item&&item.id||'')===id)||null;
    }

    async function findRunForNotification(note){
      const target=notificationTarget(note);
      if(target.runId){
        return {id:target.runId,project_id:target.projectId||'',task_id:target.taskId||'',session_id:target.sessionId||''};
      }
      const params=new URLSearchParams();
      if(target.projectId)params.set('projectId',target.projectId);
      if(target.taskId)params.set('taskId',target.taskId);
      if(target.sessionId)params.set('sessionId',target.sessionId);
      if(!params.toString())return null;
      const data=await AgentBridgeRef.runs.list(Object.fromEntries(params.entries())).catch(()=>({runs:[]}));
      const runs=Array.isArray(data&&data.runs)?data.runs:[];
      return runs[0]||null;
    }

    async function resolveOpenableSessionId(sessionId){
      const sid=sessionRefValue(sessionId);
      if(!sid)return '';
      if((OPS.sessions||[]).some(session=>sessionRefValue(session)===sid&&!session.archived))return sid;
      try{
        const data=await AgentBridgeRef.sessions.list();
        OPS.sessions=Array.isArray(data&&data.sessions)?data.sessions:[];
      }catch(_){}
      return (OPS.sessions||[]).some(session=>sessionRefValue(session)===sid&&!session.archived)?sid:'';
    }

    async function openSessionTargetOrProject(sessionId,projectId){
      const sid=await resolveOpenableSessionId(sessionId);
      if(sid&&typeof openOpsSession==='function'){
        await openOpsSession(sid);
        return true;
      }
      const pid=String(projectId||'').trim();
      if(pid&&typeof openProjectDetail==='function'){
        await openProjectDetail(pid);
        return true;
      }
      return false;
    }

    async function openNotificationTarget(notificationId,options){
      const opts=options&&typeof options==='object'?options:{};
      const note=notificationById(notificationId);
      if(!note){
        showToast('Notification was not found.',2600);
        return;
      }
      const target=notificationTarget(note);
      if(opts.preferProject&&target.projectId&&typeof openProjectDetail==='function'){
        return openProjectDetail(target.projectId);
      }
      const openedDirectly=await openSessionTargetOrProject(target.sessionId,target.projectId);
      if(openedDirectly)return;
      const run=await findRunForNotification(note);
      if(!run){
        showToast('No related target was found for this notification.',3200);
        return;
      }
      const projectId=String((run&&run.project_id)||run&&run.projectId||'').trim();
      if(opts.preferProject&&projectId&&typeof openProjectDetail==='function'){
        return openProjectDetail(projectId);
      }
      if(run.id&&typeof openRunTarget==='function')return openRunTarget(run.id);
      showToast('No related target was found for this notification.',3200);
    }

    return {
      startNotificationPolling,
      stopNotificationPolling,
      loadNotifications,
      loadNotificationDiagnostics,
      toggleNotificationSetting,
      normalizedAutoApprovalPolicy,
      saveAutoApprovalPolicy,
      toggleAutoApprovalPolicy,
      deleteAutoApprovalRule,
      createAutoApprovalRule,
      clearNotificationLogs,
      deletePushSubscription,
      subscribeBrowserPush,
      unsubscribeBrowserPush,
      sendTestPushNotification,
      renderNotificationDiagnostics,
      renderNotifications,
      notificationTitle,
      notificationPayload,
      notificationProjectLabel,
      notificationTarget,
      notificationHasRunTarget,
      notificationHasSessionTarget,
      notificationHasProjectTarget,
      notificationModeLabel,
      notificationTypeLabel,
      notificationMatchesRun,
      pendingNotificationsForRun,
      renderNotification,
      playNotificationInspectUrl,
      playInspectOverlayUrl,
      playNotificationStatus,
      playNotificationFallbackError,
      playNotificationLogText,
      playNotificationNeedsRepair,
      respondNotification,
      dismissNotification,
      notificationById,
      findRunForNotification,
      resolveOpenableSessionId,
      openSessionTargetOrProject,
      openNotificationTarget,
    };
  }

  window.HermesOpsModules.notifications={
    name:'notifications',
    routes:[
      '/api/notifications',
      '/api/notifications/settings',
      '/api/notifications/monitor',
      '/api/notifications/logs',
      '/api/notifications/push-subscriptions',
      '/api/notifications/push-status',
      '/api/notifications/auto-approval',
      '/api/notifications/respond',
      '/api/notifications/dismiss',
      '/api/ops/notifications/dismissed',
      '/api/ops/notifications/dismiss',
      'static/hermes-push-sw.js',
    ],
    actions:[
      'refresh-notification-diagnostics',
      'toggle-notification-setting',
      'clear-notification-logs',
      'delete-push-subscription',
      'subscribe-browser-push',
      'unsubscribe-browser-push',
      'send-test-push',
      'toggle-auto-approval-policy',
      'delete-auto-approval-rule',
      'open-notification-target',
      'dismiss-notification',
      'respond-notification',
      'open-play-notification',
      'repair-play-notification',
    ],
    bindDashboard,
  };
})();

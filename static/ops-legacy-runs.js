(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};

  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const AgentBridgeRef=ctx&&ctx.AgentBridge;
    const renderCurrentOpsView=ctx&&ctx.renderCurrentOpsView;
    const showToast=ctx&&ctx.showToast;
    const esc=ctx&&ctx.esc;
    const svg=ctx&&ctx.svg;
    const findProject=ctx&&ctx.findProject;
    const formatProjectLabel=ctx&&ctx.formatProjectLabel;
    const findTaskInData=ctx&&ctx.findTaskInData;
    const renderNotification=ctx&&ctx.renderNotification;
    const pendingNotificationsForRun=ctx&&ctx.pendingNotificationsForRun;
    const openSessionTargetOrProject=ctx&&ctx.openSessionTargetOrProject;
    const renderMdRef=ctx&&ctx.renderMd;
    if(!OPS||!AgentBridgeRef||!AgentBridgeRef.runs||typeof renderCurrentOpsView!=='function'||typeof showToast!=='function'||typeof esc!=='function'||!svg){
      return {};
    }

    const RUN_STATUS_VALUES=['queued','starting','running','waiting-input','waiting-approval','succeeded','failed','stopped','stale'];
    const RUN_ACTIVE_STATUS_VALUES=['queued','starting','running','waiting-input','waiting-approval'];
    const RUN_ATTENTION_STATUS_VALUES=['waiting-input','waiting-approval','failed','stale'];
    const RUN_REQUEST_STATUS_VALUES=['pending','responded','dismissed','resolved','expired'];
    const RUN_ARTIFACT_TYPE_VALUES=['file','image','screenshot','temp-input','readable-output','log','report','link','other'];
    const RUN_LOG_STREAM_VALUES=['stdout','stderr','system','agent','tool','browser','test','other'];
    const RUN_LOG_LEVEL_VALUES=['debug','info','warning','error'];

    function loadProjectLabel(project){
      if(project&&typeof formatProjectLabel==='function')return formatProjectLabel(project);
      return String(project&&project.fullName||project&&project.name||project&&project.slug||project&&project.id||'Project').trim()||'Project';
    }

    function normalizeRunRequestStatus(value){
      const normalized=String(value||'').trim().toLowerCase().replace(/[_\s]+/g,'-');
      return RUN_REQUEST_STATUS_VALUES.includes(normalized)?normalized:'pending';
    }

    function runRequestStatusLabel(value){
      const status=normalizeRunRequestStatus(value);
      return status.split('-').map(part=>part?part[0].toUpperCase()+part.slice(1):part).join(' ');
    }

    function runRequestKind(request){
      const kind=String(request&&request.kind||'').trim().toLowerCase().replace(/[_\s]+/g,'-');
      if(kind==='approval')return 'approval';
      if(kind==='clarify'||kind==='clarification')return 'clarification';
      return 'input';
    }

    function runRequestResponseText(value){
      if(value===null||typeof value==='undefined'||value==='')return '';
      if(typeof value==='string')return value;
      try{return JSON.stringify(value);}
      catch(e){return String(value);}
    }

    function normalizeRunStatus(value){
      const normalized=String(value||'').trim().toLowerCase().replace(/[\s_]+/g,'-');
      return RUN_STATUS_VALUES.includes(normalized)?normalized:'stale';
    }

    function normalizeRunCompletionStatus(value){
      const status=normalizeRunStatus(value);
      return status==='failed'?'failed':'succeeded';
    }

    function runCompletionPayload(status,summary){
      const normalized=normalizeRunCompletionStatus(status);
      const fallback=normalized==='failed'?'Run marked failed from the ops dashboard.':'Run marked complete from the ops dashboard.';
      return {
        status:normalized,
        summary:String(summary||fallback),
        source:'ops-dashboard',
      };
    }

    function normalizeRunArtifactType(value){
      const normalized=String(value||'').trim().toLowerCase().replace(/[_\s]+/g,'-');
      return RUN_ARTIFACT_TYPE_VALUES.includes(normalized)?normalized:'other';
    }

    function runArtifactLabel(artifact){
      const title=String(artifact&&artifact.title||artifact&&artifact.name||'').trim();
      if(title)return title;
      const path=String(artifact&&artifact.path||'').trim();
      if(path)return path.split('/').filter(Boolean).pop()||path;
      const url=String(artifact&&artifact.url||artifact&&artifact.href||'').trim();
      if(url)return url.split('/').filter(Boolean).pop()||url;
      return 'Artifact';
    }

    function runArtifactHref(artifact){
      const url=String(artifact&&artifact.url||artifact&&artifact.href||'').trim();
      if(url)return url;
      const path=String(artifact&&artifact.path||'').trim();
      if(path.startsWith('/'))return `/api/media?path=${encodeURIComponent(path)}`;
      return '';
    }

    function compareRunArtifacts(a,b){
      const at=Number((a&&a.updated_at)||a&&a.created_at||0)||0;
      const bt=Number((b&&b.updated_at)||b&&b.created_at||0)||0;
      return bt-at;
    }

    function normalizeRunLogStream(value){
      const normalized=String(value||'').trim().toLowerCase().replace(/[_\s]+/g,'-');
      const aliases={out:'stdout',output:'stdout',console:'stdout',err:'stderr',error:'stderr','agent-log':'agent','tool-call':'tool',play:'browser',playwright:'browser'};
      const resolved=aliases[normalized]||normalized;
      return RUN_LOG_STREAM_VALUES.includes(resolved)?resolved:(resolved?'other':'system');
    }

    function normalizeRunLogLevel(value){
      const normalized=String(value||'').trim().toLowerCase();
      const aliases={warn:'warning',fatal:'error'};
      const resolved=aliases[normalized]||normalized;
      return RUN_LOG_LEVEL_VALUES.includes(resolved)?resolved:'info';
    }

    function compareRunLogs(a,b){
      const at=Number(a&&a.created_at||0)||0;
      const bt=Number(b&&b.created_at||0)||0;
      if(at!==bt)return at-bt;
      return String(a&&a.id||'').localeCompare(String(b&&b.id||''));
    }

    function runLogMessage(log){
      const value=Object.prototype.hasOwnProperty.call(log||{},'message')?log.message:log&&log.text;
      if(value===null||typeof value==='undefined')return '';
      if(typeof value==='string')return value;
      try{return JSON.stringify(value);}
      catch(e){return String(value);}
    }

    function runArtifactPayload(data){
      const payload=data&&typeof data==='object'?data:{};
      const path=String(payload.path||'').trim();
      const url=String(payload.url||'').trim();
      const body={
        type:normalizeRunArtifactType(payload.type),
        title:String(payload.title||'').trim(),
        description:String(payload.description||'').trim(),
        metadata:{source:'ops-dashboard'},
      };
      if(path)body.path=path;
      if(url)body.url=url;
      return body;
    }

    function compareRunRequests(a,b){
      const aPending=normalizeRunRequestStatus(a&&a.status)==='pending';
      const bPending=normalizeRunRequestStatus(b&&b.status)==='pending';
      if(aPending!==bPending)return aPending?-1:1;
      const at=Number((a&&a.updated_at)||a&&a.created_at||0)||0;
      const bt=Number((b&&b.updated_at)||b&&b.created_at||0)||0;
      return bt-at;
    }

    function pendingRunRequests(requests){
      return (Array.isArray(requests)?requests:[]).filter(request=>normalizeRunRequestStatus(request&&request.status)==='pending').sort(compareRunRequests);
    }

    function runStatusLabel(status){
      switch(normalizeRunStatus(status)){
        case 'queued': return 'Queued';
        case 'starting': return 'Starting';
        case 'running': return 'Running';
        case 'waiting-input': return 'Waiting input';
        case 'waiting-approval': return 'Waiting approval';
        case 'succeeded': return 'Succeeded';
        case 'failed': return 'Failed';
        case 'stopped': return 'Stopped';
        default: return 'Stale';
      }
    }

    function runStatusKind(status){
      const normalized=normalizeRunStatus(status);
      if(['failed','stale'].includes(normalized))return 'error';
      if(['waiting-input','waiting-approval'].includes(normalized))return 'attention';
      if(normalized==='succeeded')return 'success';
      if(normalized==='stopped')return 'stopped';
      if(RUN_ACTIVE_STATUS_VALUES.includes(normalized))return 'running';
      return 'stale';
    }

    function runActivityTime(run){
      return Number(run&&run.updated_at)||Number(run&&run.started_at)||Number(run&&run.created_at)||0;
    }

    function compareRunsByActivity(a,b){
      return runActivityTime(b)-runActivityTime(a);
    }

    function formatRunTime(run){
      const stamp=runActivityTime(run)*1000;
      if(!stamp)return 'No activity yet';
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

    function isRunActive(run){
      return RUN_ACTIVE_STATUS_VALUES.includes(normalizeRunStatus(run&&run.status));
    }

    function needsRunAttention(run){
      return RUN_ATTENTION_STATUS_VALUES.includes(normalizeRunStatus(run&&run.status));
    }

    function runsForProject(projectId){
      const id=String(projectId||'').trim();
      if(!id)return [];
      const cached=OPS.runsByProject[id];
      if(Array.isArray(cached))return cached.slice().sort(compareRunsByActivity);
      return (OPS.runs||[]).filter(run=>(run.project_id||run.projectId)===id).sort(compareRunsByActivity);
    }

    function summarizeRuns(runs){
      const summary={total:0,active:0,attention:0,succeeded:0,failed:0,stopped:0,stale:0};
      (runs||[]).forEach(run=>{
        summary.total++;
        const status=normalizeRunStatus(run&&run.status);
        if(isRunActive(run))summary.active++;
        if(needsRunAttention(run))summary.attention++;
        if(status==='succeeded')summary.succeeded++;
        if(status==='failed')summary.failed++;
        if(status==='stopped')summary.stopped++;
        if(status==='stale')summary.stale++;
      });
      return summary;
    }

    function runProjectLabel(run){
      const projectId=String(run&&run.project_id||run&&run.projectId||'');
      const project=typeof findProject==='function'?findProject(projectId):null;
      return project?loadProjectLabel(project):(projectId||'Project');
    }

    function runTaskLabel(run,projectId){
      const taskId=run&&String(run.task_id||run.taskId||'');
      if(!taskId||typeof findTaskInData!=='function')return '';
      const match=findTaskInData(
        projectId&&OPS.currentProject&&OPS.currentProject.id===projectId?OPS.taskData:OPS.taskDataByProject[projectId],
        taskId
      );
      return match&&match.task?match.task.text:`Task ${taskId}`;
    }

    function shortRunSessionId(run){
      const id=String((run&&run.session_id)||run&&run.sessionId||'');
      if(!id)return '';
      return id.length>12?`${id.slice(0,8)}...${id.slice(-4)}`:id;
    }

    function renderRunRow(run,options){
      const projectId=String(run&&run.project_id||run&&run.projectId||'');
      const status=normalizeRunStatus(run&&run.status);
      const taskLabel=runTaskLabel(run,projectId);
      const projectLabel=(options&&options.hideProject)?'':runProjectLabel(run);
      const title=String((run&&run.title)||taskLabel||'Project run');
      const summary=String((run&&run.summary)||'');
      const meta=[
        projectLabel,
        taskLabel,
        String((run&&run.engine)||'hermes-session'),
        shortRunSessionId(run)?`Session ${shortRunSessionId(run)}`:'',
        formatRunTime(run),
      ].filter(Boolean);
      return `
        <article class="ops-run ${esc(runStatusKind(status))}">
          <div class="ops-run-main">
            <div class="ops-run-title-row">
              <span class="ops-run-status ${esc(runStatusKind(status))}">${esc(runStatusLabel(status))}</span>
              <span class="ops-run-title">${esc(title)}</span>
            </div>
            ${summary?`<div class="ops-run-summary">${esc(summary)}</div>`:''}
            <div class="ops-run-meta">${meta.map(item=>`<span>${esc(item)}</span>`).join('')}</div>
          </div>
          <div class="ops-run-actions">
            <button class="ops-btn primary" type="button" data-ops-action="open-run-target" data-run-id="${esc(run&&run.id||'')}">${svg.chat}<span>Open</span></button>
            ${projectId?`<button class="ops-btn" type="button" data-ops-action="open-project" data-project-id="${esc(projectId)}">${svg.grid}<span>Project</span></button>`:''}
            <button class="ops-icon-btn" type="button" data-ops-action="open-run-detail" data-run-id="${esc(run&&run.id||'')}" title="Details">${svg.folder}</button>
          </div>
        </article>
      `;
    }

    function renderRunList(runs,options){
      if(OPS.loading&&(!runs||!runs.length))return '<div class="ops-empty">Loading runs...</div>';
      const visible=(runs||[]).slice(0,(options&&options.limit)||8);
      if(!visible.length)return `<div class="ops-empty">${esc((options&&options.emptyLabel)||'No runs yet.')}</div>`;
      return `<div class="ops-run-list">${visible.map(run=>renderRunRow(run,options)).join('')}</div>`;
    }

    function renderHomeRunActivity(){
      const runs=(OPS.runs||[]).slice().sort(compareRunsByActivity);
      const summary=summarizeRuns(runs);
      return `
        <div class="ops-run-summary-strip">
          <span>${esc(String(summary.active))} active</span>
          <span>${esc(String(summary.attention))} need attention</span>
          <span>${esc(String(summary.succeeded))} succeeded</span>
          <span>${esc(String(summary.failed))} failed</span>
        </div>
        ${renderRunList(runs,{limit:8,emptyLabel:'No recorded task runs yet.'})}
      `;
    }

    function renderProjectRunActivity(project){
      const runs=runsForProject(project&&project.id);
      const summary=summarizeRuns(runs);
      return `
        <section class="ops-run-panel">
          <div class="ops-run-panel-header">
            <div>
              <h3>Run activity</h3>
              <span>${esc(String(summary.active))} active | ${esc(String(summary.attention))} need attention | ${esc(String(summary.succeeded))} succeeded</span>
            </div>
          </div>
          ${renderRunList(runs,{limit:6,hideProject:true,emptyLabel:'No runs recorded for this project yet.'})}
        </section>
      `;
    }

    function readableAssetUrl(ref,assetBaseUrl){
      const value=String(ref||'').trim();
      if(!value||/^[a-z][a-z0-9+.-]*:/i.test(value)||value.startsWith('#')||value.startsWith('/'))return value;
      const base=String(assetBaseUrl||'');
      if(!base)return value;
      return base+value.split('/').map(part=>encodeURIComponent(part)).join('/');
    }

    function rewriteReadableOutputAssetRefs(markdown,artifact){
      const base=artifact&&artifact.assetBaseUrl;
      if(!base)return String(markdown||'');
      return String(markdown||'').replace(/(!?\[[^\]\n]*\]\()([^) \t\r\n]+)(\))/g,(match,prefix,ref,suffix)=>{
        return `${prefix}${readableAssetUrl(ref,base)}${suffix}`;
      });
    }

    function renderReadableOutput(artifact){
      if(!artifact)return '<div class="ops-empty">Loading readable output...</div>';
      if(!artifact.exists)return '<div class="ops-empty">No readable output is linked to this run yet.</div>';
      const markdown=rewriteReadableOutputAssetRefs(artifact.markdown||'',artifact);
      const rendered=typeof renderMdRef==='function'?renderMdRef(markdown):`<pre>${esc(markdown)}</pre>`;
      return `
        <div class="ops-run-readable">
          <div class="ops-run-readable-meta">
            <span>${esc(artifact.path||'Readable output')}</span>
            <span>${esc(String(artifact.size||0))} bytes</span>
            ${(artifact.assets||[]).length?`<span>${esc(String(artifact.assets.length))} assets</span>`:''}
          </div>
          <div class="preview-md ops-run-readable-body">${rendered}</div>
        </div>
      `;
    }

    function renderRunArtifacts(artifacts){
      if(!artifacts)return '<div class="ops-empty">Loading run artifacts...</div>';
      const ordered=(Array.isArray(artifacts)?artifacts:[]).slice().sort(compareRunArtifacts);
      const runId=String((OPS.runDetail&&OPS.runDetail.id)||OPS.selectedRunId||'');
      const artifactForm=`
        <form class="ops-run-artifact-form" data-ops-submit="run-artifact" data-run-id="${esc(runId)}">
          <label><span>Type</span><select name="type">
            ${RUN_ARTIFACT_TYPE_VALUES.map(type=>`<option value="${esc(type)}">${esc(type)}</option>`).join('')}
          </select></label>
          <label><span>Title</span><input name="title" autocomplete="off" placeholder="Result screenshot"></label>
          <label><span>Path</span><input name="path" autocomplete="off" placeholder="/absolute/path/to/file"></label>
          <label><span>URL</span><input name="url" autocomplete="off" inputmode="url" placeholder="https://example.com/artifact"></label>
          <label class="full"><span>Description</span><input name="description" autocomplete="off" placeholder="Short note"></label>
          <div class="ops-form-actions"><button class="ops-btn primary" type="submit">${svg.plus}<span>Add</span></button></div>
        </form>
      `;
      if(!ordered.length)return `
        <div class="ops-run-artifacts">
          <div class="ops-run-events-header">
            <span>Artifacts</span>
            <span>0 items</span>
          </div>
          ${artifactForm}
          <div class="ops-empty">No run artifacts recorded yet.</div>
        </div>
      `;
      return `
        <div class="ops-run-artifacts">
          <div class="ops-run-events-header">
            <span>Artifacts</span>
            <span>${esc(String(ordered.length))} item${ordered.length===1?'':'s'}</span>
          </div>
          ${artifactForm}
          <div class="ops-run-artifact-list">
            ${ordered.map(artifact=>{
              const href=runArtifactHref(artifact);
              const type=normalizeRunArtifactType(artifact&&artifact.type);
              const label=runArtifactLabel(artifact);
              const meta=[
                type,
                artifact&&artifact.size?`${artifact.size} bytes`:'',
                formatRunTime({updated_at:(artifact&&artifact.updated_at)||artifact&&artifact.created_at}),
              ].filter(Boolean);
              return `
                <article class="ops-run-artifact">
                  <div class="ops-run-artifact-main">
                    <div class="ops-run-artifact-title-row">
                      <span class="ops-run-status ${esc(type)}">${esc(type)}</span>
                      <span class="ops-run-title">${esc(label)}</span>
                    </div>
                    ${artifact&&artifact.description?`<div class="ops-run-summary">${esc(artifact.description)}</div>`:''}
                    <div class="ops-run-meta">${meta.map(item=>`<span>${esc(item)}</span>`).join('')}</div>
                  </div>
                  ${href?`<a class="ops-btn" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${svg.folder}<span>Open</span></a>`:''}
                </article>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }

    function renderRunLogs(logs){
      if(!logs)return '<div class="ops-empty">Loading run logs...</div>';
      const ordered=(Array.isArray(logs)?logs:[]).slice().sort(compareRunLogs);
      if(!ordered.length)return `
        <div class="ops-run-events">
          <div class="ops-run-events-header">
            <span>Run logs</span>
            <span>0 lines</span>
          </div>
          <div class="ops-empty">No run logs recorded yet.</div>
        </div>
      `;
      return `
        <div class="ops-run-events">
          <div class="ops-run-events-header">
            <span>Run logs</span>
            <span>${esc(String(ordered.length))} line${ordered.length===1?'':'s'}</span>
          </div>
          <div class="ops-run-log-list">
            ${ordered.map(log=>{
              const stream=normalizeRunLogStream(log&&log.stream);
              const level=normalizeRunLogLevel(log&&log.level);
              const meta=[stream,level,formatRunTime({updated_at:(log&&log.created_at)||0})].filter(Boolean);
              return `
                <article class="ops-run-log ${esc(level)}">
                  <div class="ops-run-log-header">${meta.map(item=>`<span>${esc(item)}</span>`).join('')}</div>
                  <pre class="ops-run-log-body">${esc(runLogMessage(log))}</pre>
                </article>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }

    function renderRunEvents(events){
      if(!events)return '<div class="ops-empty">Loading run events...</div>';
      const ordered=(Array.isArray(events)?events:[]).slice().sort((a,b)=>{
        const at=Number(a&&a.created_at||0)||0;
        const bt=Number(b&&b.created_at||0)||0;
        if(at!==bt)return bt-at;
        return String(b&&b.id||'').localeCompare(String(a&&a.id||''));
      });
      if(!ordered.length)return `
        <div class="ops-run-events">
          <div class="ops-run-events-header">
            <span>Run events</span>
            <span>0 items</span>
          </div>
          <div class="ops-empty">No run events recorded yet.</div>
        </div>
      `;
      return `
        <div class="ops-run-events">
          <div class="ops-run-events-header">
            <span>Run events</span>
            <span>${esc(String(ordered.length))} item${ordered.length===1?'':'s'}</span>
          </div>
          <div class="ops-run-event-list">
            ${ordered.map(event=>{
              const metadata=event&&event.metadata&&typeof event.metadata==='object'?event.metadata:{};
              const meta=[String(event&&event.type||'event'),String(event&&event.level||'info'),formatRunTime({updated_at:(event&&event.created_at)||0})].filter(Boolean);
              return `
                <article class="ops-run-event ${esc(String(event&&event.level||'info'))}">
                  <div class="ops-run-log-header">${meta.map(item=>`<span>${esc(item)}</span>`).join('')}</div>
                  <div class="ops-run-summary">${esc(String(event&&event.message||''))}</div>
                  ${Object.keys(metadata).length?`<pre class="ops-run-log-body">${esc(JSON.stringify(metadata,null,2))}</pre>`:''}
                </article>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }

    function renderRunRequest(request){
      const status=normalizeRunRequestStatus(request&&request.status);
      const kind=runRequestKind(request);
      const metadata=(request&&request.metadata&&typeof request.metadata==='object')?request.metadata:{};
      const choices=Array.isArray(metadata.choices_offered)?metadata.choices_offered:(Array.isArray(metadata.choices)?metadata.choices:[]);
      const response=runRequestResponseText(request&&request.response);
      const pending=status==='pending';
      const badge=kind==='approval'?'Approval':(kind==='clarification'?'Clarify':'Input');
      const title=kind==='approval'?'Approval needed':(kind==='clarification'?'Clarification needed':'Input needed');
      const approvalActions=pending&&kind==='approval'?`
        <div class="ops-notification-actions">
          ${['once','session','always','deny'].map(choice=>`
            <button class="ops-btn ${choice==='deny'?'danger':''}" type="button" data-ops-action="respond-run-request" data-run-request-id="${esc(request.id)}" data-choice="${esc(choice)}">${esc(choice==='once'?'Allow once':choice==='session'?'Allow session':choice==='always'?'Always allow':'Deny')}</button>
          `).join('')}
        </div>
      `:'';
      const inputActions=pending&&kind!=='approval'?`
        ${choices.length?`<div class="ops-notification-choices">
          ${choices.map(choice=>`<button class="ops-btn" type="button" data-ops-action="respond-run-request" data-run-request-id="${esc(request.id)}" data-response="${esc(choice)}">${esc(choice)}</button>`).join('')}
        </div>`:''}
        <form class="ops-notification-response" data-ops-submit="run-request-response" data-run-request-id="${esc(request.id)}">
          <input name="response" autocomplete="off" placeholder="Type your answer..." required>
          <button class="ops-btn primary" type="submit">Send</button>
        </form>
      `:'';
      const completed=!pending?`
        <div class="ops-notification-actions secondary">
          ${response?`<span class="ops-run-request-response">${esc(response)}</span>`:''}
        </div>
      `:'';
      return `
        <article class="ops-notification input">
          <div class="ops-notification-main">
            <div class="ops-notification-title-row">
              <span class="ops-notification-badge input">${esc(badge)}</span>
              <span class="ops-notification-title">${esc(title)}</span>
            </div>
            <div class="ops-notification-message">${esc(request&&request.message||'Run needs input.')}</div>
            ${metadata.command?`<pre class="ops-notification-command">${esc(metadata.command)}</pre>`:''}
            <div class="ops-notification-meta">
              <span>${esc(runRequestStatusLabel(status))}</span>
              <span>${esc(String(request&&request.source||'ops'))}</span>
              <span>${esc(formatRunTime({updated_at:(request&&request.updated_at)||request&&request.created_at}))}</span>
            </div>
          </div>
          <div class="ops-notification-control">
            ${approvalActions}
            ${inputActions}
            ${completed}
          </div>
        </article>
      `;
    }

    function renderRunRequests(requests){
      if(!requests)return '<div class="ops-empty">Loading run requests...</div>';
      const ordered=(Array.isArray(requests)?requests:[]).slice().sort(compareRunRequests);
      const pending=pendingRunRequests(ordered);
      if(!ordered.length)return `
        <div class="ops-run-notifications ops-run-requests">
          <div class="ops-run-events-header">
            <span>Run requests</span>
            <span>0 items</span>
          </div>
          <div class="ops-empty">No run-owned input or approval requests recorded yet.</div>
        </div>
      `;
      return `
        <div class="ops-run-notifications ops-run-requests">
          <div class="ops-run-events-header">
            <span>Run requests</span>
            <span>${esc(String(pending.length))} pending / ${esc(String(ordered.length))} total</span>
          </div>
          <div class="ops-notification-list">
            ${ordered.map(renderRunRequest).join('')}
          </div>
        </div>
      `;
    }

    function renderRunNotifications(run){
      const notifications=typeof pendingNotificationsForRun==='function'?pendingNotificationsForRun(run):[];
      if(!notifications.length)return `
        <div class="ops-run-notifications">
          <div class="ops-run-events-header">
            <span>Pending input</span>
            <span>0 items</span>
          </div>
          <div class="ops-empty">No pending input or approval requests for this run.</div>
        </div>
      `;
      return `
        <div class="ops-run-notifications">
          <div class="ops-run-events-header">
            <span>Pending input</span>
            <span>${esc(String(notifications.length))} item${notifications.length===1?'':'s'}</span>
          </div>
          <div class="ops-notification-list">
            ${notifications.map(note=>typeof renderNotification==='function'?renderNotification(note):'').join('')}
          </div>
        </div>
      `;
    }

    function renderRunDetailPanel(options){
      const run=OPS.runDetail;
      const selectedId=String(OPS.selectedRunId||'');
      if(!selectedId)return '';
      const loading=!run||String(run.id||'')!==selectedId;
      const status=normalizeRunStatus(run&&run.status);
      const sessionId=String((run&&run.session_id)||run&&run.sessionId||'');
      const sessionRef=String((run&&run.sessionKey)||sessionId||'').trim();
      const title=run?String(run.title||runTaskLabel(run,run.project_id||run.projectId)||'Project run'):'Loading run...';
      const canStop=run&&isRunActive(run);
      const canComplete=run&&!['succeeded','failed','stopped'].includes(status);
      const canFail=canComplete;
      const canReopen=run&&['failed','stopped','stale'].includes(status);
      return `
        <section class="ops-run-detail">
          <div class="ops-run-panel-header">
            <div>
              <h3>${esc(title)}</h3>
              <span>${loading?'Loading run detail...':esc([options&&options.hideProject?'':runProjectLabel(run),runStatusLabel(status),formatRunTime(run)].filter(Boolean).join(' | '))}</span>
            </div>
            <div class="ops-run-actions">
              ${sessionRef?`<button class="ops-btn" type="button" data-ops-action="open-session" data-session-key="${esc(sessionRef)}">${svg.chat}<span>Open</span></button>`:''}
              ${canStop?`<button class="ops-btn" type="button" data-ops-action="set-run-status" data-run-id="${esc(selectedId)}" data-run-status="stopped">${svg.close}<span>Stop</span></button>`:''}
              ${canComplete?`<button class="ops-btn" type="button" data-ops-action="complete-run" data-run-id="${esc(selectedId)}" data-run-completion-status="succeeded">${svg.check}<span>Complete</span></button>`:''}
              ${canFail?`<button class="ops-btn danger" type="button" data-ops-action="complete-run" data-run-id="${esc(selectedId)}" data-run-completion-status="failed">Failed</button>`:''}
              ${canReopen?`<button class="ops-btn" type="button" data-ops-action="set-run-status" data-run-id="${esc(selectedId)}" data-run-status="running">${svg.refresh}<span>Reopen</span></button>`:''}
              <button class="ops-btn" type="button" data-ops-action="refresh-run-detail" data-run-id="${esc(selectedId)}">${svg.refresh}<span>Refresh</span></button>
              <button class="ops-icon-btn" type="button" data-ops-action="close-run-detail" title="Close">${svg.close}</button>
            </div>
          </div>
          ${loading?'<div class="ops-empty">Loading run detail...</div>':`
            <div class="ops-run-detail-summary">
              <span class="ops-run-status ${esc(runStatusKind(status))}">${esc(runStatusLabel(status))}</span>
              ${String(run.summary||'')?`<span>${esc(run.summary)}</span>`:''}
              ${sessionId?`<span>Session ${esc(shortRunSessionId(run))}</span>`:''}
            </div>
            ${renderRunRequests(OPS.runRequests)}
            ${renderRunNotifications(run)}
            ${renderReadableOutput(OPS.runReadableOutput)}
            ${renderRunLogs(OPS.runLogs)}
            ${renderRunArtifacts(OPS.runArtifacts)}
            ${renderRunEvents(OPS.runEvents)}
          `}
        </section>
      `;
    }

    async function loadOpsRuns(filters){
      const params=new URLSearchParams();
      Object.entries(filters||{}).forEach(([key,value])=>{
        const trimmed=String(value||'').trim();
        if(trimmed)params.set(key,trimmed);
      });
      const data=await AgentBridgeRef.runs.list(Object.fromEntries(params.entries()));
      const runs=Array.isArray(data.runs)?data.runs:[];
      if(filters&&filters.projectId){
        OPS.runsByProject[filters.projectId]=runs;
        const other=(OPS.runs||[]).filter(run=>run.project_id!==filters.projectId&&run.projectId!==filters.projectId);
        OPS.runs=[...runs,...other].sort(compareRunsByActivity);
      }else{
        OPS.runs=runs;
        OPS.runsByProject={};
        runs.forEach(run=>{
          const projectId=run.project_id||run.projectId||'';
          if(!projectId)return;
          if(!OPS.runsByProject[projectId])OPS.runsByProject[projectId]=[];
          OPS.runsByProject[projectId].push(run);
        });
      }
      return runs;
    }

    async function scanStaleRuns(){
      await AgentBridgeRef.runs.staleScan({maxAgeSeconds:3600});
      await loadOpsRuns();
      renderCurrentOpsView();
    }

    async function loadRunDetail(runId){
      const id=String(runId||'').trim();
      if(!id)return null;
      const [runData,readableData,eventData,requestData,artifactData,logData,notificationData]=await Promise.all([
        AgentBridgeRef.runs.get(id),
        AgentBridgeRef.runs.readableOutput(id).catch(err=>({
          readableOutput:{exists:false,error:err&&err.message?err.message:'Readable output unavailable'},
        })),
        AgentBridgeRef.runs.events(id,{limit:80}).catch(()=>({events:[]})),
        AgentBridgeRef.runs.requests(id,{includeResolved:1}).catch(()=>({requests:[]})),
        AgentBridgeRef.runs.artifacts(id).catch(()=>({artifacts:[]})),
        AgentBridgeRef.runs.logs(id,{limit:160}).catch(()=>({logs:[]})),
        AgentBridgeRef.notifications&&typeof AgentBridgeRef.notifications.list==='function'
          ? AgentBridgeRef.notifications.list().catch(()=>({notifications:OPS.notifications||[]}))
          : Promise.resolve({notifications:OPS.notifications||[]}),
      ]);
      OPS.runDetail=runData&&runData.run?runData.run:null;
      OPS.runReadableOutput=readableData&&readableData.readableOutput?readableData.readableOutput:null;
      OPS.runEvents=Array.isArray(eventData&&eventData.events)?eventData.events:[];
      OPS.runRequests=Array.isArray(requestData&&requestData.requests)?requestData.requests:[];
      OPS.runArtifacts=Array.isArray(artifactData&&artifactData.artifacts)?artifactData.artifacts:[];
      OPS.runLogs=Array.isArray(logData&&logData.logs)?logData.logs:[];
      OPS.notifications=Array.isArray(notificationData&&notificationData.notifications)?notificationData.notifications:OPS.notifications;
      return OPS.runDetail;
    }

    async function openRunDetail(runId){
      const id=String(runId||'').trim();
      if(!id)return;
      OPS.selectedRunId=id;
      OPS.runDetail=null;
      OPS.runReadableOutput=null;
      OPS.runEvents=null;
      OPS.runRequests=null;
      OPS.runArtifacts=null;
      OPS.runLogs=null;
      renderCurrentOpsView();
      await loadRunDetail(id);
      renderCurrentOpsView();
    }

    function closeRunDetail(){
      OPS.selectedRunId='';
      OPS.runDetail=null;
      OPS.runReadableOutput=null;
      OPS.runEvents=null;
      OPS.runRequests=null;
      OPS.runArtifacts=null;
      OPS.runLogs=null;
      renderCurrentOpsView();
    }

    async function reloadRunsForCurrentView(){
      if(OPS.currentProject&&OPS.view==='project-detail')await loadOpsRuns({projectId:OPS.currentProject.id}).catch(()=>[]);
      else await loadOpsRuns().catch(()=>[]);
    }

    async function setRunStatus(runId,status){
      const id=String(runId||'').trim();
      if(!id)return;
      const normalized=normalizeRunStatus(status);
      await AgentBridgeRef.runs.update(id,{status:normalized,summary:`Run marked ${runStatusLabel(normalized).toLowerCase()} from the ops dashboard.`});
      await reloadRunsForCurrentView();
      OPS.selectedRunId=id;
      await loadRunDetail(id);
      renderCurrentOpsView();
    }

    async function completeRun(runId,status,summary){
      const id=String(runId||'').trim();
      if(!id)return null;
      await AgentBridgeRef.runs.complete(id,runCompletionPayload(status,summary));
      await reloadRunsForCurrentView();
      OPS.selectedRunId=id;
      await loadRunDetail(id).catch(()=>null);
      renderCurrentOpsView();
      showToast(normalizeRunCompletionStatus(status)==='failed'?'Run marked failed':'Run marked complete',2200);
      return OPS.runDetail;
    }

    async function respondRunRequest(requestId,body){
      const id=String(requestId||'').trim();
      const runId=String((OPS.runDetail&&OPS.runDetail.id)||OPS.selectedRunId||'').trim();
      if(!id||!runId)return;
      await AgentBridgeRef.runs.respondRequest(runId,id,body||{});
      await loadRunDetail(runId).catch(()=>null);
      await reloadRunsForCurrentView();
      renderCurrentOpsView();
      showToast('Run request answered',2200);
    }

    async function createRunArtifact(runId,data){
      const id=String(runId||'').trim();
      if(!id)throw new Error('Run is not selected.');
      const body=runArtifactPayload(data);
      if(!body.path&&!body.url)throw new Error('Artifact path or URL is required.');
      await AgentBridgeRef.runs.createArtifact(id,body);
      await loadRunDetail(id).catch(()=>null);
      await reloadRunsForCurrentView();
      renderCurrentOpsView();
      showToast('Artifact added',2200);
    }

    async function openRunTarget(runId){
      const id=String(runId||'').trim();
      if(!id)return;
      let run=(OPS.runs||[]).find(entry=>String(entry&&entry.id||'')===id)||null;
      if(!run&&OPS.runDetail&&String(OPS.runDetail.id||'')===id)run=OPS.runDetail;
      if(!run){
        const data=await AgentBridgeRef.runs.get(id).catch(()=>null);
        run=data&&data.run?data.run:null;
      }
      if(!run){
        showToast('Run was not found.',2600);
        return;
      }
      const sessionId=String((run&&run.session_id)||run&&run.sessionId||'').trim();
      const projectId=String((run&&run.project_id)||run&&run.projectId||'').trim();
      const opened=typeof openSessionTargetOrProject==='function'
        ? await openSessionTargetOrProject(sessionId,projectId)
        : false;
      if(!opened)await openRunDetail(id);
    }

    return {
      loadOpsRuns,
      scanStaleRuns,
      renderHomeRunActivity,
      renderProjectRunActivity,
      renderRunDetailPanel,
      loadRunDetail,
      openRunDetail,
      closeRunDetail,
      setRunStatus,
      completeRun,
      respondRunRequest,
      createRunArtifact,
      openRunTarget,
      normalizeRunStatus,
      runStatusLabel,
      runStatusKind,
      runActivityTime,
      compareRunsByActivity,
      isRunActive,
      needsRunAttention,
      summarizeRuns,
      readableAssetUrl,
      rewriteReadableOutputAssetRefs,
      normalizeRunRequestStatus,
      runRequestStatusLabel,
      runRequestKind,
      runRequestResponseText,
      normalizeRunCompletionStatus,
      runCompletionPayload,
      normalizeRunArtifactType,
      runArtifactLabel,
      runArtifactHref,
      compareRunArtifacts,
      runArtifactPayload,
      normalizeRunLogStream,
      normalizeRunLogLevel,
      compareRunLogs,
      runLogMessage,
      compareRunRequests,
      pendingRunRequests,
    };
  }

  window.HermesOpsModules.runs={
    name:'runs',
    routes:[
      '/api/ops/runs',
      '/api/ops/runs/stale-scan',
      '/api/ops/runs/*/events',
      '/api/ops/runs/*/requests',
      '/api/ops/runs/*/artifacts',
      '/api/ops/runs/*/logs',
      '/api/ops/runs/*/readable-output',
    ],
    actions:[
      'scan-stale-runs',
      'open-run-target',
      'open-run-detail',
      'refresh-run-detail',
      'close-run-detail',
      'set-run-status',
      'complete-run',
      'respond-run-request',
    ],
    bindDashboard,
  };
})();

(function(){
  function escapeHtml(value){
    return String(value||'')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  function renderSection(state){
    const items=Array.isArray(state.notifications)?state.notifications:[];
    const content=state.loadingNotifications
      ? '<p class="ops-shell-loading">Loading workflow notifications…</p>'
      : items.length
        ? '<div class="ops-notification-list">'+items.map(function(item){return renderNotificationCard(item,state);}).join('')+'</div>'
        : '<p class="ops-shell-loading">No pending approval or clarify requests for task-linked sessions.</p>';
    return [
      '<section class="ops-notification-panel">',
      '<div class="ops-project-column-header"><h2>Workflow Inbox</h2><span>'+escapeHtml(state.loadingNotifications?'Loading…':String(items.length)+' pending')+'</span></div>',
      '<div class="ops-notification-toolbar">',
      '<p class="ops-notification-copy">Pending approval and clarify prompts from task-linked Hermes sessions appear here without taking over upstream chat flow.</p>',
      '<button class="ops-shell-link" type="button" data-ops-action="refresh-notifications">Refresh inbox</button>',
      '</div>',
      state.notificationsError?'<p class="ops-shell-error">'+escapeHtml(state.notificationsError)+'</p>':'',
      content,
      '</section>'
    ].join('');
  }

  function renderNotificationCard(item,state){
    const kind=String(item&&item.kind||'').toLowerCase();
    const project=item&&item.project||{};
    const task=item&&item.task||{};
    const session=item&&item.session||{};
    const summary=kind==='approval'
      ? renderApprovalSummary(item,state)
      : renderClarifySummary(item,state);
    return [
      '<article class="ops-notification-card '+escapeHtml(kind||'note')+'">',
      '<div class="ops-notification-meta">',
      '<span class="ops-task-chip '+escapeHtml(kind==='approval'?'flag':'label')+'">'+escapeHtml(kind||'notification')+'</span>',
      '<strong>'+escapeHtml(project.name||'Project')+'</strong>',
      '<span>'+escapeHtml(task.text||'Task')+'</span>',
      '<em>'+escapeHtml(session.title||item.sessionId||'Session')+'</em>',
      '</div>',
      summary,
      '<div class="ops-notification-footer">',
      '<a class="ops-shell-link" href="'+escapeHtml(String(item&&item.sessionUrl||'/'))+'">Open session</a>',
      '</div>',
      '</article>'
    ].join('');
  }

  function renderApprovalSummary(item,state){
    const key=notificationKey(item);
    const waiting=state.respondingNotificationKey===key;
    const description=String(item&&item.description||'Approval required').trim()||'Approval required';
    const command=String(item&&item.command||'').trim();
    const patternKeys=Array.isArray(item&&item.patternKeys)?item.patternKeys:[];
    return [
      '<div class="ops-notification-body">',
      '<p>'+escapeHtml(description)+(patternKeys.length?' <span class="ops-notification-inline">['+escapeHtml(patternKeys.join(', '))+']</span>':'')+'</p>',
      command?'<pre class="ops-notification-command">'+escapeHtml(command)+'</pre>':'',
      '<div class="ops-notification-actions">',
      approvalButton(item,'once','Allow once',waiting),
      approvalButton(item,'session','Allow session',waiting),
      approvalButton(item,'always','Always allow',waiting),
      approvalButton(item,'deny','Deny',waiting),
      '</div>',
      '</div>'
    ].join('');
  }

  function approvalButton(item,choice,label,waiting){
    return '<button class="ops-shell-link'+(waiting?' disabled':'')+'" type="button" data-ops-action="respond-notification" data-notification-key="'+escapeHtml(notificationKey(item))+'" data-notification-kind="approval" data-session-id="'+escapeHtml(item&&item.sessionId||'')+'" data-approval-id="'+escapeHtml(item&&item.approvalId||'')+'" data-choice="'+escapeHtml(choice)+'"'+(waiting?' disabled':'')+'>'+escapeHtml(waiting?'Sending…':label)+'</button>';
  }

  function renderClarifySummary(item,state){
    const key=notificationKey(item);
    const waiting=state.respondingNotificationKey===key;
    const choices=Array.isArray(item&&item.choices)?item.choices:[];
    return [
      '<div class="ops-notification-body">',
      '<p>'+escapeHtml(String(item&&item.question||'Clarification needed'))+'</p>',
      choices.length?'<div class="ops-notification-actions">'+choices.map(function(choice){
        return '<button class="ops-shell-link'+(waiting?' disabled':'')+'" type="button" data-ops-action="respond-notification" data-notification-key="'+escapeHtml(notificationKey(item))+'" data-notification-kind="clarify" data-session-id="'+escapeHtml(item&&item.sessionId||'')+'" data-response="'+escapeHtml(choice)+'"'+(waiting?' disabled':'')+'>'+escapeHtml(waiting?'Sending…':choice)+'</button>';
      }).join('')+'</div>':'',
      '<form class="ops-inline-form compact notification" data-ops-form="clarify-response">',
      '<input type="hidden" name="notificationKey" value="'+escapeHtml(notificationKey(item))+'">',
      '<input type="hidden" name="kind" value="clarify">',
      '<input type="hidden" name="sessionId" value="'+escapeHtml(item&&item.sessionId||'')+'">',
      '<label><span>Reply</span><input name="response" type="text" placeholder="Type your response"></label>',
      '<button class="ops-shell-link'+(waiting?' disabled':'')+'" type="submit"'+(waiting?' disabled':'')+'>'+(waiting?'Sending…':'Send')+'</button>',
      '</form>',
      '</div>'
    ].join('');
  }

  function notificationKey(item){
    return String(item&&item.notificationKey||item&&item.kind||'')+':'+String(item&&item.sessionId||'');
  }

  window.HermesOpsNotifications={
    renderSection:renderSection,
    notificationKey:notificationKey,
  };
})();

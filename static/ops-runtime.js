(function(){
  function escapeHtml(value){
    return String(value||'')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  function statusLabel(value){
    const text=String(value||'').trim();
    return text||'unknown';
  }

  function capabilityCards(summary){
    const capabilities=summary && summary.capabilities ? summary.capabilities : {};
    const orderedKeys=['gatherReports','reviewRequests','snapshot','screenshot','actions','play'];
    return orderedKeys.filter(function(key){return capabilities[key];}).map(function(key){
      const item=capabilities[key]||{};
      const available=item.available===true;
      return [
        '<article class="ops-runtime-capability '+(available?'ready':'deferred')+'">',
        '<strong>'+escapeHtml(item.label||key)+'</strong>',
        '<span>'+escapeHtml(available?'Available':'Deferred')+'</span>',
        item.reason?'<p>'+escapeHtml(item.reason)+'</p>':'',
        '</article>'
      ].join('');
    }).join('');
  }

  function reportItems(summary){
    const gather=summary && summary.gather ? summary.gather : {};
    const reports=Array.isArray(gather.reports)?gather.reports:[];
    if(!reports.length){
      return '<p class="ops-runtime-empty">No gather reports have been recorded for this project yet.</p>';
    }
    return reports.map(function(report){
      const latestEvent=report.latestEvent && report.latestEvent.message ? report.latestEvent.message : '';
      return [
        '<article class="ops-runtime-record gather">',
        '<header>',
        '<strong>'+escapeHtml(report.title||'Runtime gather report')+'</strong>',
        '<span class="ops-runtime-pill">'+escapeHtml(statusLabel(report.status))+'</span>',
        '</header>',
        report.summary?'<p>'+escapeHtml(report.summary)+'</p>':'',
        latestEvent?'<p class="ops-runtime-note">'+escapeHtml(latestEvent)+'</p>':'',
        '<footer>',
        '<span>'+escapeHtml(report.updatedAt||report.createdAt||'')+'</span>',
        report.reportPath?'<span>'+escapeHtml(report.reportPath)+'</span>':'',
        '</footer>',
        '</article>'
      ].join('');
    }).join('');
  }

  function reviewItems(summary){
    const reviewsBlock=summary && summary.reviews ? summary.reviews : {};
    const reviews=Array.isArray(reviewsBlock.reviews)?reviewsBlock.reviews:[];
    if(!reviews.length){
      return '<p class="ops-runtime-empty">No runtime reviews have been recorded for this project yet.</p>';
    }
    return reviews.map(function(review){
      const latestEvent=review.latestEvent && review.latestEvent.message ? review.latestEvent.message : '';
      return [
        '<article class="ops-runtime-record review">',
        '<header>',
        '<strong>'+escapeHtml(review.title||'Runtime review')+'</strong>',
        '<span class="ops-runtime-pill">'+escapeHtml(statusLabel(review.status))+'</span>',
        '</header>',
        review.prompt?'<p>'+escapeHtml(review.prompt)+'</p>':'',
        review.summary?'<p class="ops-runtime-note">'+escapeHtml(review.summary)+'</p>':(latestEvent?'<p class="ops-runtime-note">'+escapeHtml(latestEvent)+'</p>':''),
        '<footer>',
        '<span>'+escapeHtml(review.updatedAt||review.createdAt||'')+'</span>',
        review.reviewPath?'<span>'+escapeHtml(review.reviewPath)+'</span>':'',
        '</footer>',
        '</article>'
      ].join('');
    }).join('');
  }

  function playStatus(summary){
    const play=summary && summary.play ? summary.play : {};
    return play && typeof play === 'object' ? play : {};
  }

  function playButtons(play,state){
    const busy=String(state && state.playBusyAction || '').trim();
    const running=play.running===true || ['queued','building','starting','ready'].includes(String(play.status||'').toLowerCase());
    const ready=play.ready===true;
    const configured=play.configExists===true && play.valid===true;
    const buttons=[
      '<button class="ops-shell-link" type="button" data-ops-action="refresh-play">Refresh Play</button>',
      '<button class="ops-shell-link" type="button" data-ops-action="show-play-config">Configure</button>'
    ];
    buttons.push('<button class="ops-shell-link'+(configured&&!running?' primary':'')+'" type="button" data-ops-action="start-play"'+(configured&&!running&&!busy?'':' disabled')+'>'+(busy==='start'?'Starting…':'Start')+'</button>');
    buttons.push('<button class="ops-shell-link" type="button" data-ops-action="restart-play"'+(configured&&!busy?'':' disabled')+'>'+(busy==='restart'?'Restarting…':'Restart')+'</button>');
    buttons.push('<button class="ops-shell-link" type="button" data-ops-action="stop-play"'+(running&&!busy?'':' disabled')+'>'+(busy==='stop'?'Stopping…':'Stop')+'</button>');
    buttons.push('<button class="ops-shell-link" type="button" data-ops-action="show-play-logs">Logs</button>');
    buttons.push('<button class="ops-shell-link" type="button" data-ops-action="open-play"'+(ready&&play.inspectUrl?'':' disabled')+'>Open</button>');
    return buttons.join('');
  }

  function playMeta(play){
    const bits=[];
    if(play.configPath)bits.push('Config: '+String(play.configPath));
    if(play.inspectUrl)bits.push('Inspect: '+String(play.inspectUrl));
    if(play.allocatedPort)bits.push('Port: '+String(play.allocatedPort));
    return bits.length ? '<p class="ops-runtime-note">'+escapeHtml(bits.join(' | '))+'</p>' : '';
  }

  function playConfigPanel(state){
    if(!(state && state.showPlayConfig))return '';
    const doc=state.playConfigDoc||{};
    const info=doc.info||{};
    const target=String(doc.targetPath||doc.path||info.path||'');
    const content=String(doc.content||'');
    return [
      '<form class="ops-runtime-config-form" data-ops-form="play-config">',
      '<div class="ops-runtime-inline-header"><strong>Play config</strong><button class="ops-shell-link" type="button" data-ops-action="close-play-config">Close</button></div>',
      target?'<p class="ops-runtime-note">'+escapeHtml(target)+'</p>':'',
      '<textarea name="content" rows="14"'+((state.loadingPlayConfig||state.savingPlayConfig)?' disabled':'')+'>'+escapeHtml(content)+'</textarea>',
      '<div class="ops-runtime-actions">',
      '<button class="ops-shell-link primary" type="submit"'+((state.loadingPlayConfig||state.savingPlayConfig)?' disabled':'')+'>'+(state.savingPlayConfig?'Saving…':'Save Play config')+'</button>',
      '<button class="ops-shell-link" type="button" data-ops-action="reload-play-config"'+(state.loadingPlayConfig?' disabled':'')+'>Reload</button>',
      '</div>',
      '</form>'
    ].join('');
  }

  function playLogsPanel(state){
    if(!(state && state.showPlayLogs))return '';
    const logs=state.playLogs||{};
    const text=String(logs.text||'No Play logs yet.');
    return [
      '<div class="ops-runtime-logs-panel">',
      '<div class="ops-runtime-inline-header"><strong>Play logs</strong><button class="ops-shell-link" type="button" data-ops-action="close-play-logs">Close</button></div>',
      '<pre class="ops-runtime-logs">'+escapeHtml(text)+'</pre>',
      '</div>'
    ].join('');
  }

  function playSection(summary,state){
    const play=playStatus(summary);
    const summaryText=String(play.statusSummary||play.failureSummary||'Play status unavailable.');
    const label=String(play.status||'idle');
    return [
      '<section class="ops-runtime-play-panel">',
      '<div class="ops-epic-header"><h3>Play workflow</h3><span>'+escapeHtml(label)+'</span></div>',
      state && state.playError ? '<p class="ops-shell-error">'+escapeHtml(state.playError)+'</p>' : '',
      '<div class="ops-runtime-play-status"><span class="ops-runtime-pill">'+escapeHtml(statusLabel(label))+'</span><p>'+escapeHtml(summaryText)+'</p></div>',
      playMeta(play),
      '<div class="ops-runtime-actions">'+playButtons(play,state)+'</div>',
      playConfigPanel(state),
      playLogsPanel(state),
      '</section>'
    ].join('');
  }

  function inspectRecordMeta(parts){
    const filtered=(parts||[]).filter(function(item){return item;});
    return filtered.length ? '<p class="ops-runtime-note">'+escapeHtml(filtered.join(' | '))+'</p>' : '';
  }

  function inspectSnapshotSection(summary,state){
    const snapshot=summary && summary.snapshot ? summary.snapshot : {};
    const busy=String(state && state.inspectBusyAction || '').trim();
    const summaryText=String(snapshot.summary||'Resolve the current inspect target or reset the seeded debug state before capturing evidence.');
    return [
      '<article class="ops-runtime-tool">',
      '<div class="ops-epic-header"><h3>Runtime snapshot</h3><span>'+escapeHtml(snapshot.kind||'snapshot')+'</span></div>',
      '<p>'+escapeHtml(summaryText)+'</p>',
      inspectRecordMeta([
        snapshot.inspectUrl ? 'Inspect: '+String(snapshot.inspectUrl) : '',
        snapshot.browserUrl ? 'Browser: '+String(snapshot.browserUrl) : '',
        snapshot.sessionId ? 'Session: '+String(snapshot.sessionId) : '',
        snapshot.updatedAt ? 'Updated: '+String(snapshot.updatedAt) : ''
      ]),
      '<div class="ops-runtime-actions">',
      '<button class="ops-shell-link" type="button" data-ops-action="run-inspect-url"'+(busy?' disabled':'')+'>'+(busy==='inspect-url'?'Resolving…':'Inspect URL')+'</button>',
      '<button class="ops-shell-link" type="button" data-ops-action="reset-inspect-state"'+(busy?' disabled':'')+'>'+(busy==='reset-state'?'Resetting…':'Reset state')+'</button>',
      '</div>',
      '</article>'
    ].join('');
  }

  function inspectScreenshotSection(summary,state){
    const screenshot=summary && summary.screenshot ? summary.screenshot : {};
    const busy=String(state && state.inspectBusyAction || '').trim();
    return [
      '<article class="ops-runtime-tool">',
      '<div class="ops-epic-header"><h3>Runtime screenshot</h3><span>'+escapeHtml(screenshot.kind||'capture')+'</span></div>',
      '<form class="ops-runtime-tool-form" data-ops-form="runtime-screenshot">',
      '<label><span>URL</span><input name="url" type="text" placeholder="/app/runtime-preview"></label>',
      '<label><span>Selector</span><input name="selector" type="text" placeholder="figure.preview"></label>',
      '<label><span>File name</span><input name="fileName" type="text" placeholder="runtime-check"></label>',
      '<div class="ops-runtime-actions">',
      '<button class="ops-shell-link primary" type="submit"'+(busy?' disabled':'')+'>'+(busy==='screenshot'?'Capturing…':'Capture screenshot')+'</button>',
      '</div>',
      '</form>',
      '<div class="ops-runtime-tool-output">',
      '<p>'+escapeHtml(String(screenshot.summary||'Capture a full-page or element-targeted screenshot through ct-runtime.'))+'</p>',
      inspectRecordMeta([
        screenshot.absolutePath ? 'File: '+String(screenshot.absolutePath) : '',
        screenshot.inspectUrl ? 'Inspect: '+String(screenshot.inspectUrl) : '',
        screenshot.updatedAt ? 'Updated: '+String(screenshot.updatedAt) : ''
      ]),
      '</div>',
      '</article>'
    ].join('');
  }

  function inspectActionSection(summary,state){
    const action=summary && summary.actions ? summary.actions : {};
    const actionSummary=action && action.actions ? action.actions : {};
    const busy=String(state && state.inspectBusyAction || '').trim();
    const scriptText=[
      '[',
      '  { "type": "waitForSelectorVisible", "selector": "body" },',
      '  { "type": "captureElementScreenshot", "selector": "body", "label": "runtime-check" }',
      ']'
    ].join('\\n');
    return [
      '<article class="ops-runtime-tool">',
      '<div class="ops-epic-header"><h3>Runtime actions</h3><span>'+escapeHtml(String(actionSummary.executedCount||0)+'/'+String(actionSummary.requestedCount||0))+'</span></div>',
      '<form class="ops-runtime-tool-form" data-ops-form="runtime-action">',
      '<label><span>URL</span><input name="url" type="text" placeholder="/app/editor"></label>',
      '<label><span>File name</span><input name="fileName" type="text" placeholder="runtime-action"></label>',
      '<label class="ops-runtime-checkbox"><input name="captureScreenshot" type="checkbox" checked>Capture screenshot</label>',
      '<label><span>Action script</span><textarea name="script" rows="10">'+escapeHtml(scriptText)+'</textarea></label>',
      '<div class="ops-runtime-actions">',
      '<button class="ops-shell-link primary" type="submit"'+(busy?' disabled':'')+'>'+(busy==='action'?'Running…':'Run actions')+'</button>',
      '</div>',
      '</form>',
      '<div class="ops-runtime-tool-output">',
      '<p>'+escapeHtml(String(action.summary||'Run scripted wait, click, drag, evaluate, assert, and capture steps through ct-runtime.'))+'</p>',
      inspectRecordMeta([
        action.capture && action.capture.absolutePath ? 'Capture: '+String(action.capture.absolutePath) : '',
        action.artifacts && action.artifacts.manifest && action.artifacts.manifest.absolutePath ? 'Artifacts: '+String(action.artifacts.manifest.absolutePath) : '',
        action.updatedAt ? 'Updated: '+String(action.updatedAt) : ''
      ]),
      '</div>',
      '</article>'
    ].join('');
  }

  function inspectToolkitSection(summary,state){
    return [
      '<section class="ops-runtime-inspect-panel">',
      '<div class="ops-epic-header"><h3>Inspect toolkit</h3><span>ct-runtime</span></div>',
      state && state.inspectError ? '<p class="ops-shell-error">'+escapeHtml(state.inspectError)+'</p>' : '',
      '<div class="ops-runtime-tool-grid">',
      inspectSnapshotSection(summary,state),
      inspectScreenshotSection(summary,state),
      inspectActionSection(summary,state),
      '</div>',
      '</section>'
    ].join('');
  }

  function renderSection(state){
    const selectedProject=state && state.selectedProject ? state.selectedProject : null;
    if(!selectedProject){
      return [
        '<section class="ops-runtime-panel">',
        '<div class="ops-project-column-header"><h2>Runtime evidence</h2><span>Select a project</span></div>',
        '<p class="ops-runtime-empty">Choose a project to inspect gather reports and review requests.</p>',
        '</section>'
      ].join('');
    }

    if(state && state.loadingRuntimeSummary){
      return [
        '<section class="ops-runtime-panel">',
        '<div class="ops-project-column-header"><h2>Runtime evidence</h2><span>Loading…</span></div>',
        '<p class="ops-runtime-empty">Loading recent gather reports and reviews…</p>',
        '</section>'
      ].join('');
    }

    if(state && state.runtimeError){
      return [
        '<section class="ops-runtime-panel">',
        '<div class="ops-project-column-header"><h2>Runtime evidence</h2><button class="ops-shell-link" type="button" data-ops-action="refresh-runtime">Retry</button></div>',
        '<p class="ops-shell-error">'+escapeHtml(state.runtimeError)+'</p>',
        '</section>'
      ].join('');
    }

    const summary=state && state.runtimeSummary ? state.runtimeSummary : {};
    const gatherCount=summary && summary.gather ? summary.gather.count : 0;
    const reviewCount=summary && summary.reviews ? summary.reviews.count : 0;
    return [
      '<section class="ops-runtime-panel">',
      '<div class="ops-project-column-header"><h2>Runtime evidence</h2><button class="ops-shell-link" type="button" data-ops-action="refresh-runtime">Refresh runtime</button></div>',
      '<div class="ops-runtime-overview">',
      '<span><strong>Gather reports</strong>'+escapeHtml(String(gatherCount||0))+'</span>',
      '<span><strong>Review requests</strong>'+escapeHtml(String(reviewCount||0))+'</span>',
      '</div>',
      playSection(summary,state),
      inspectToolkitSection(summary,state),
      '<div class="ops-runtime-capabilities">'+capabilityCards(summary)+'</div>',
      '<div class="ops-runtime-grid">',
      '<section class="ops-runtime-column"><div class="ops-epic-header"><h3>Recent gather reports</h3><span>'+escapeHtml(String(gatherCount||0)+' total')+'</span></div>'+reportItems(summary)+'</section>',
      '<section class="ops-runtime-column"><div class="ops-epic-header"><h3>Recent reviews</h3><span>'+escapeHtml(String(reviewCount||0)+' total')+'</span></div>'+reviewItems(summary)+'</section>',
      '</div>',
      '</section>'
    ].join('');
  }

  window.HermesOpsRuntime={renderSection:renderSection};
})();

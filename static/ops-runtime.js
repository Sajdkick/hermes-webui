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

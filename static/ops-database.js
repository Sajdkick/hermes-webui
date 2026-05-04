(function(){
  function escapeHtml(value){
    return String(value||'')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  function configuredLabel(payload){
    if(!payload || !payload.settings) return 'Not configured';
    const settings=payload.settings;
    const configured=!!payload.configured;
    if(!configured) return 'Not configured';
    const parts=[
      String(settings.kind||'sqlite').trim(),
      String(settings.label||settings.path||'').trim(),
      payload.inherited ? 'inherited' : '',
    ].filter(Boolean);
    return parts.join(' | ') || 'Configured';
  }

  function renderTableSummary(tables){
    const items=Array.isArray(tables) ? tables : [];
    if(!items.length) return '<p class="ops-runtime-note">No tables loaded.</p>';
    return [
      '<div class="ops-database-table-list">',
      items.slice(0,12).map(function(table){
        const columns=Array.isArray(table && table.columns) ? table.columns : [];
        return '<div class="ops-database-table-chip"><strong>'+escapeHtml(table && table.name || 'table')+'</strong><span>'+escapeHtml(String(columns.length)+' cols')+'</span></div>';
      }).join(''),
      '</div>'
    ].join('');
  }

  function renderQueryResult(result){
    if(!result || !Array.isArray(result.columns)) return '';
    const columns=result.columns;
    const rows=Array.isArray(result.rows) ? result.rows : [];
    return [
      '<div class="ops-database-query-result">',
      '<div class="ops-runtime-note">Query result · '+escapeHtml(String(result.rowCount||0))+' rows</div>',
      '<div class="ops-database-table-wrap">',
      '<table class="ops-database-result-table"><thead><tr>',
      columns.map(function(column){ return '<th>'+escapeHtml(column)+'</th>'; }).join(''),
      '</tr></thead><tbody>',
      rows.length ? rows.map(function(row){
        const cells=Array.isArray(row) ? row : [];
        return '<tr>'+columns.map(function(_column,index){
          return '<td>'+escapeHtml(cells[index])+'</td>';
        }).join('')+'</tr>';
      }).join('') : '<tr><td colspan="'+escapeHtml(columns.length)+'">No rows returned.</td></tr>',
      '</tbody></table>',
      '</div>',
      '</div>'
    ].join('');
  }

  function renderPanel(options){
    const payload=options.payload||{};
    const settings=payload.settings||{};
    const configured=!!payload.configured;
    const inherited=!!payload.inherited;
    const tables=Array.isArray(options.tables) ? options.tables : [];
    const queryResult=options.queryResult||null;
    const error=String(options.error||'').trim();
    const busyAction=String(options.busyAction||'').trim();
    const settingsForm=options.settingsForm;
    const queryForm=options.queryForm;
    const refreshAction=options.refreshAction;
    const testAction=options.testAction;
    const inspectAction=options.inspectAction;
    const title=options.title;
    const subtitle=options.subtitle;
    const configuredText=configuredLabel(payload);
    const pathValue=escapeHtml(settings.path||'');
    const labelValue=escapeHtml(settings.label||'');
    const modeValue=String(settings.mode||'persistent').trim() || 'persistent';
    return [
      '<section class="ops-admin-panel ops-database-panel">',
      '<div class="ops-project-column-header"><h2>'+escapeHtml(title)+'</h2><span>'+escapeHtml(configuredText)+'</span></div>',
      '<p class="ops-runtime-note">'+escapeHtml(subtitle)+(inherited?' · inherited from global settings':'')+'</p>',
      error?'<p class="ops-shell-error">'+escapeHtml(error)+'</p>':'',
      '<form class="ops-inline-form compact" data-ops-form="'+escapeHtml(settingsForm)+'">',
      '<label><span>SQLite path</span><input name="path" type="text" value="'+pathValue+'" placeholder="/path/to/app.db"></label>',
      '<label><span>Label</span><input name="label" type="text" value="'+labelValue+'" placeholder="App DB"></label>',
      '<label><span>Mode</span><select name="mode"><option value="persistent"'+selectedAttr(modeValue,'persistent')+'>persistent</option><option value="copy"'+selectedAttr(modeValue,'copy')+'>copy</option><option value="shared"'+selectedAttr(modeValue,'shared')+'>shared</option><option value="empty"'+selectedAttr(modeValue,'empty')+'>empty</option></select></label>',
      '<div class="ops-runtime-actions">',
      '<button class="ops-shell-link primary" type="submit"'+(busyAction==='save'?' disabled':'')+'>'+(busyAction==='save'?'Saving…':'Save settings')+'</button>',
      '<button class="ops-shell-link" type="button" data-ops-action="'+escapeHtml(refreshAction)+'"'+(busyAction==='refresh'?' disabled':'')+'>'+(busyAction==='refresh'?'Refreshing…':'Refresh')+'</button>',
      '<button class="ops-shell-link" type="button" data-ops-action="'+escapeHtml(testAction)+'"'+(busyAction==='test' || !configured?' disabled':'')+'>'+(busyAction==='test'?'Testing…':'Test')+'</button>',
      '<button class="ops-shell-link" type="button" data-ops-action="'+escapeHtml(inspectAction)+'"'+(busyAction==='inspect' || !configured?' disabled':'')+'>'+(busyAction==='inspect'?'Loading…':'Tables')+'</button>',
      '</div>',
      '</form>',
      renderTableSummary(tables),
      '<form class="ops-inline-form compact" data-ops-form="'+escapeHtml(queryForm)+'">',
      '<label class="ops-wide-field"><span>Read-only query</span><textarea name="query" rows="4" placeholder="select name from sqlite_master order by name"></textarea></label>',
      '<label><span>Row limit</span><input name="limit" type="number" min="1" max="200" value="'+escapeHtml(queryResult && queryResult.limit || 50)+'"></label>',
      '<div class="ops-runtime-actions">',
      '<button class="ops-shell-link" type="submit"'+(busyAction==='query' || !configured?' disabled':'')+'>'+(busyAction==='query'?'Running…':'Run query')+'</button>',
      '</div>',
      '</form>',
      renderQueryResult(queryResult),
      '</section>'
    ].join('');
  }

  function selectedAttr(value,expected){
    return String(value||'')===String(expected||'') ? ' selected' : '';
  }

  function renderGlobalSection(state){
    return renderPanel({
      payload: state && state.databaseSettings ? state.databaseSettings : {},
      tables: state && state.databaseTables,
      queryResult: state && state.databaseQueryResult,
      error: state && state.databaseError,
      busyAction: state && state.databaseBusyAction,
      settingsForm: 'database-settings',
      queryForm: 'database-query',
      refreshAction: 'refresh-database',
      testAction: 'test-database',
      inspectAction: 'inspect-database',
      title: 'Database admin',
      subtitle: 'Global read-only SQLite settings for inspection and query workflows.',
    });
  }

  function renderProjectSection(payload){
    return renderPanel({
      payload: payload && payload.projectDatabase ? payload.projectDatabase : {},
      tables: payload && payload.projectDatabaseTables,
      queryResult: payload && payload.projectDatabaseQueryResult,
      error: payload && payload.projectDatabaseError,
      busyAction: payload && payload.projectDatabaseBusyAction,
      settingsForm: 'project-database-settings',
      queryForm: 'project-database-query',
      refreshAction: 'refresh-project-database',
      testAction: 'test-project-database',
      inspectAction: 'inspect-project-database',
      title: 'Project database',
      subtitle: 'Project-scoped read-only SQLite settings. Relative paths resolve from the project root.',
    });
  }

  window.HermesOpsDatabase={
    renderGlobalSection:renderGlobalSection,
    renderProjectSection:renderProjectSection,
  };
})();

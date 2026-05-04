(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};
  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const api=ctx&&ctx.api;
    const projectUrl=ctx&&ctx.projectUrl;
    const renderCurrentOpsView=ctx&&ctx.renderCurrentOpsView;
    const showToast=ctx&&ctx.showToast;
    const esc=ctx&&ctx.esc;
    const svg=ctx&&ctx.svg;
    if(!OPS||typeof api!=='function'||typeof projectUrl!=='function'||typeof renderCurrentOpsView!=='function'||typeof showToast!=='function'||typeof esc!=='function'||!svg){
      return {};
    }

    async function loadDatabaseSettings(options){
      OPS.databaseBusy=true;
      OPS.databaseError='';
      try{
        const data=await api('/api/ops/database/settings');
        OPS.databaseSettings=data;
        return data;
      }catch(e){
        OPS.databaseError=e.message||'Database settings unavailable.';
        throw e;
      }finally{
        OPS.databaseBusy=false;
        if(!options||options.render!==false)renderCurrentOpsView();
      }
    }

    async function inspectDatabaseTables(){
      OPS.databaseBusy=true;
      OPS.databaseError='';
      try{
        const data=await api('/api/ops/database/inspect/tables');
        OPS.databaseTables=Array.isArray(data.tables)?data.tables:[];
        return data;
      }catch(e){
        OPS.databaseError=e.message||'Database inspection failed.';
        throw e;
      }finally{
        OPS.databaseBusy=false;
        renderCurrentOpsView();
      }
    }

    async function loadProjectDatabase(projectId,options){
      const id=String(projectId||'').trim();
      if(!id)return null;
      OPS.projectDatabaseBusyByProject[id]='settings';
      try{
        const data=await api(projectUrl(id,'/database/settings'));
        OPS.projectDatabaseByProject[id]={...(OPS.projectDatabaseByProject[id]||{}),settings:data};
        return data;
      }finally{
        delete OPS.projectDatabaseBusyByProject[id];
        if(!options||options.render!==false)renderCurrentOpsView();
      }
    }

    async function inspectProjectDatabase(projectId){
      const id=String(projectId||'').trim();
      if(!id)return null;
      OPS.projectDatabaseBusyByProject[id]='tables';
      try{
        const data=await api(projectUrl(id,'/database/inspect/tables'));
        OPS.projectDatabaseByProject[id]={...(OPS.projectDatabaseByProject[id]||{}),tables:Array.isArray(data.tables)?data.tables:[],settings:{configured:true,settings:data.settings||{}}};
        return data;
      }finally{
        delete OPS.projectDatabaseBusyByProject[id];
        renderCurrentOpsView();
      }
    }

    async function testProjectDatabase(projectId){
      const id=String(projectId||'').trim();
      if(!id)return null;
      OPS.projectDatabaseBusyByProject[id]='test';
      try{
        const data=await api(projectUrl(id,'/database/test'),{method:'POST',body:JSON.stringify({})});
        showToast(data.ok?'Database connection OK':'Database connection failed',2600);
        return data;
      }finally{
        delete OPS.projectDatabaseBusyByProject[id];
        renderCurrentOpsView();
      }
    }

    function renderDatabasePanel(){
      const settings=(OPS.databaseSettings&&OPS.databaseSettings.settings)||{};
      const configured=!!(OPS.databaseSettings&&OPS.databaseSettings.configured);
      const tables=OPS.databaseTables||[];
      const tableText=tables.length
        ? tables.slice(0,8).map(table=>`${table.name} (${(table.columns||[]).length})`).join(' | ')
        : configured?'No tables loaded.':'Configure database settings through the API to enable read-only inspection.';
      const error=OPS.databaseError?`<div class="ops-status error">${esc(OPS.databaseError)}</div>`:'';
      return `
        <section class="ops-panel ops-database-panel">
          <div class="ops-panel-header">
            <div>
              <h2>Database</h2>
              <span>${esc(configured?`${settings.kind||'sqlite'} | ${settings.label||settings.path||''}`:'Read-only inspection not configured.')}</span>
            </div>
            <div class="ops-database-actions">
              <button class="ops-btn" type="button" data-ops-action="refresh-database" ${OPS.databaseBusy?'disabled':''}>${svg.refresh}<span>Refresh</span></button>
              <button class="ops-btn primary" type="button" data-ops-action="inspect-database" ${OPS.databaseBusy||!configured?'disabled':''}>${svg.grid}<span>Tables</span></button>
            </div>
          </div>
          <div class="ops-database-body">
            <div class="ops-database-summary">${esc(tableText)}</div>
          </div>
          ${error}
        </section>
      `;
    }

    function renderProjectDatabase(project){
      if(!project||!project.id)return '';
      const data=OPS.projectDatabaseByProject[project.id]||{};
      const settingsData=data.settings||{};
      const settings=settingsData.settings||{};
      const configured=!!settingsData.configured;
      const tables=Array.isArray(data.tables)?data.tables:[];
      const busy=!!OPS.projectDatabaseBusyByProject[project.id];
      const tableText=tables.length
        ? tables.slice(0,8).map(table=>`${table.name} (${(table.columns||[]).length})`).join(' | ')
        : configured?'No project tables loaded.':'No project database configured; global settings may be inherited.';
      return `
        <section class="ops-panel ops-project-database-panel">
          <div class="ops-panel-header">
            <div>
              <h2>Project database</h2>
              <span>${esc(configured?`${settings.kind||'sqlite'} | ${settings.label||settings.path||''}${settingsData.inherited?' | inherited':''}`:'Read-only project database not configured.')}</span>
            </div>
            <div class="ops-database-actions">
              <button class="ops-btn" type="button" data-ops-action="refresh-project-database" data-project-id="${esc(project.id)}" ${busy?'disabled':''}>${svg.refresh}<span>Refresh</span></button>
              <button class="ops-btn" type="button" data-ops-action="test-project-database" data-project-id="${esc(project.id)}" ${busy||!configured?'disabled':''}>${svg.check}<span>Test</span></button>
              <button class="ops-btn primary" type="button" data-ops-action="inspect-project-database" data-project-id="${esc(project.id)}" ${busy||!configured?'disabled':''}>${svg.grid}<span>Tables</span></button>
            </div>
          </div>
          <div class="ops-database-body">
            <div class="ops-database-summary">${esc(tableText)}</div>
          </div>
        </section>
      `;
    }

    return {
      loadDatabaseSettings,
      inspectDatabaseTables,
      loadProjectDatabase,
      inspectProjectDatabase,
      testProjectDatabase,
      renderDatabasePanel,
      renderProjectDatabase,
    };
  }

  window.HermesOpsModules.database={
    name:'database',
    routes:[
      '/api/ops/database/settings',
      '/api/ops/database/test',
      '/api/ops/database/inspect/tables',
      '/api/ops/database/inspect/query',
      '/database/settings',
      '/database/test',
      '/database/inspect/tables',
      '/database/inspect/query',
    ],
    actions:[
      'refresh-database',
      'inspect-database',
      'refresh-project-database',
      'test-project-database',
      'inspect-project-database',
    ],
    bindDashboard,
  };
})();

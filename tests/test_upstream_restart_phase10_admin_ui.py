import subprocess
import textwrap
from pathlib import Path


def test_phase10_ops_ui_renders_admin_panels():
    script = textwrap.dedent(
        """
        (async () => {
        const fs = require('fs');
        const vm = require('vm');

        class Root {
          constructor(){
            this.innerHTML = '';
            this.listeners = {};
          }
          addEventListener(name, handler){
            this.listeners[name] = handler;
          }
          querySelector(){
            return null;
          }
        }

        function HTMLFormElement(){}
        function HTMLElement(){}
        function HTMLInputElement(){}

        const fetchCalls = [];
        const databaseSource = fs.readFileSync('static/ops-database.js', 'utf8');
        const githubSource = fs.readFileSync('static/ops-github-admin.js', 'utf8');
        const upstreamSource = fs.readFileSync('static/ops-upstream-sync.js', 'utf8');
        const projectsSource = fs.readFileSync('static/ops-projects.js', 'utf8');
        const fetch = async (path) => {
          fetchCalls.push(path);
          if (path === '/api/ops/notifications/pending'){
            return { ok: true, json: async () => ({ count: 0, notifications: [] }) };
          }
          if (path === '/api/ops/database/settings'){
            return {
              ok: true,
              json: async () => ({
                configured: true,
                settings: { kind: 'sqlite', path: '/tmp/app.db', label: 'App DB', mode: 'persistent' }
              })
            };
          }
          if (path === '/api/ops/github/status'){
            return {
              ok: true,
              json: async () => ({
                authenticated: true,
                tokenPresent: true,
                tokenSource: 'GITHUB_TOKEN',
                user: { login: 'octo' }
              })
            };
          }
          throw new Error('Unexpected fetch path: ' + path);
        };

        const context = {
          console,
          window: {},
          fetch,
          HTMLFormElement,
          HTMLElement,
          HTMLInputElement,
          FormData: function FormData(){ return { get: () => '' }; },
          setTimeout,
          clearTimeout,
        };
        vm.createContext(context);
        vm.runInContext(databaseSource, context);
        vm.runInContext(githubSource, context);
        vm.runInContext(upstreamSource, context);
        vm.runInContext(projectsSource, context);

        const root = new Root();
        context.window.HermesOpsProjects.mount(root, {
          phase: 'phase-10',
          route: '/ops',
          apiBase: '/api/ops',
          version: 'test-version',
        });

        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));

        if (!root.innerHTML.includes('GitHub admin')){
          throw new Error('GitHub admin panel did not render');
        }
        if (!root.innerHTML.includes('Database admin')){
          throw new Error('Database admin panel did not render');
        }
        if (!fetchCalls.includes('/api/ops/database/settings')){
          throw new Error('Database settings endpoint was not requested');
        }
        if (!fetchCalls.includes('/api/ops/github/status')){
          throw new Error('GitHub status endpoint was not requested');
        }

        const projectDatabaseHtml = context.window.HermesOpsDatabase.renderProjectSection({
          projectDatabase: {
            configured: true,
            settings: { kind: 'sqlite', path: '/tmp/project.db', label: 'Project DB', mode: 'copy' },
            inherited: false,
          },
          projectDatabaseTables: [{ name: 'users', columns: [{ name: 'id' }, { name: 'name' }] }],
          projectDatabaseQueryResult: { columns: ['name'], rows: [['Ada']], rowCount: 1, limit: 50 },
          projectDatabaseError: '',
          projectDatabaseBusyAction: '',
        });
        if (!projectDatabaseHtml.includes('Project database')){
          throw new Error('Project database panel did not render');
        }

        const upstreamSyncHtml = context.window.HermesOpsUpstreamSync.renderSection({
          loadingUpstreamSync: false,
          upstreamSync: {
            recordId: 'sync-1',
            state: 'ready_for_review',
            canApply: true,
            applied: false,
            message: 'Ready to fast-forward feature/local.',
            sourceBranch: 'feature/local',
            upstreamRef: 'upstream/main',
            worktreePath: '/tmp/worktree',
            sessionUrl: '/session/sess-1',
            blockers: [],
          },
          upstreamSyncRecords: [{ syncBranch: 'upstream-sync/feature-local/1', state: 'ready_for_review' }],
          upstreamSyncError: '',
          upstreamSyncBusyAction: '',
        });
        if (!upstreamSyncHtml.includes('Maintenance sync')){
          throw new Error('Maintenance sync panel did not render');
        }
        if (!upstreamSyncHtml.includes('Apply reviewed sync')){
          throw new Error('Maintenance apply action did not render');
        }
        console.log('ok');
        })().catch((error) => {
          console.error(error);
          process.exit(1);
        });
        """
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "ok"


def test_main_shell_exposes_ops_navigation_entry():
    html = Path("static/index.html").read_text(encoding="utf-8")
    js = Path("static/panels.js").read_text(encoding="utf-8")

    assert html.count('onclick="openOpsDashboard()"') == 3
    assert html.count("title=\"Ops dashboard\"") == 2
    assert "Open Ops dashboard" in html
    assert "function openOpsDashboard()" in js
    assert "const base=(typeof document!=='undefined' && document.baseURI)" in js
    assert "return new URL(rel, base).href;" in js
    assert "_appRelativeUrl('ops')" in js

    assert html.count('onclick="openRecoveryPage()"') == 3
    assert html.count("title=\"Recovery page\"") == 2
    assert "Open recovery page" in html
    assert "function openRecoveryPage()" in js
    assert "function _siteRootUrl(path)" in js
    assert "const target=_siteRootUrl('recovery');" in js


def test_main_shell_exposes_codex_and_maintenance_settings_entries():
    html = Path("static/index.html").read_text(encoding="utf-8")
    js = Path("static/panels.js").read_text(encoding="utf-8")

    assert 'data-settings-section="codex"' in html
    assert 'id="settingsPaneCodex"' in html
    assert 'id="settingsCodexConfigEditor"' in html
    assert 'data-settings-section="maintenance"' in html
    assert 'id="settingsPaneMaintenance"' in html
    assert 'id="settingsMaintenanceProject"' in html
    assert "switchSettingsSection('codex')" in html
    assert "switchSettingsSection('maintenance')" in html

    assert "name==='appearance'||name==='preferences'||name==='providers'||name==='codex'||name==='maintenance'||name==='system'" in js
    assert "api('/api/codex-config')" in js
    assert "/api/ops/projects/'+encodeURIComponent(state.selectedProjectId)+'/upstream-sync" in js
    assert "Open Codex settings" in js

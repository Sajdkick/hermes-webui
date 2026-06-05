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


def test_phase10_github_import_prompts_for_branch_and_posts_create_missing_payload():
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
          querySelectorAll(){
            return [];
          }
        }

        function HTMLFormElement(){}
        function HTMLElement(){}
        function HTMLInputElement(){}

        const importBodies = [];
        const promptCalls = [];
        const githubSource = fs.readFileSync('static/ops-github-admin.js', 'utf8');
        const projectsSource = fs.readFileSync('static/ops-projects.js', 'utf8');
        const fetch = async (path, options = {}) => {
          if (path === '/api/ops/notifications/pending'){
            return { ok: true, json: async () => ({ count: 0, notifications: [] }) };
          }
          if (path === '/api/ops/github/status'){
            return { ok: true, json: async () => ({ authenticated: true, user: { login: 'octo' } }) };
          }
          if (path === '/api/ops/github/import'){
            importBodies.push(JSON.parse(options.body || '{}'));
            return {
              ok: true,
              json: async () => ({ ok: true, imported: true, repo: 'repo', targetPath: '/tmp/repo', project: { id: 'p1', name: 'repo' } })
            };
          }
          if (path === '/api/ops/projects'){
            return { ok: true, json: async () => ({ projects: [] }) };
          }
          throw new Error('Unexpected fetch path: ' + path);
        };

        const context = {
          console,
          window: {
            prompt(message, defaultValue){
              promptCalls.push({ message, defaultValue });
              return 'feature/new-project';
            },
          },
          fetch,
          HTMLFormElement,
          HTMLElement,
          HTMLInputElement,
          setTimeout,
          clearTimeout,
        };
        vm.createContext(context);
        vm.runInContext(githubSource, context);
        vm.runInContext(projectsSource, context);

        const root = new Root();
        context.window.HermesOpsProjects.mount(root, {
          phase: 'phase-10',
          route: '/ops',
          apiBase: '/api/ops',
          version: 'test-version',
        });

        const attrs = {
          'data-ops-action': 'github-import-repo',
          'data-owner': 'acme',
          'data-repo': 'repo',
          'data-branch': 'main',
          'data-default-branch': 'main',
          'data-project-name': 'repo',
        };
        const action = { getAttribute(name){ return attrs[name] || ''; } };
        root.listeners.click({ target: { closest(){ return action; } } });
        for (let index = 0; index < 5; index += 1){
          await new Promise((resolve) => setTimeout(resolve, 0));
        }

        if (promptCalls.length !== 1){
          throw new Error('Expected one branch prompt, got ' + promptCalls.length);
        }
        if (promptCalls[0].defaultValue !== 'main'){
          throw new Error('Expected prompt default branch main, got ' + promptCalls[0].defaultValue);
        }
        if (!promptCalls[0].message.includes('acme/repo')){
          throw new Error('Prompt message did not include repo name: ' + promptCalls[0].message);
        }
        if (importBodies.length !== 1){
          throw new Error('Expected one import request, got ' + importBodies.length);
        }
        const body = importBodies[0];
        if (body.branch !== 'feature/new-project'){
          throw new Error('Import body branch mismatch: ' + body.branch);
        }
        if (body.defaultBranch !== 'main' || body.baseBranch !== 'main'){
          throw new Error('Import body base branch mismatch: ' + JSON.stringify(body));
        }
        if (body.createMissingBranch !== true || body.createMissingCoreBranch !== true){
          throw new Error('Import body did not request missing branch creation: ' + JSON.stringify(body));
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
    assert html.count('aria-label="Ops dashboard"') == 2
    assert "Open Ops dashboard" in html
    assert "function openOpsDashboard()" in js
    assert "const base=(typeof document!=='undefined' && document.baseURI)" in js
    assert "return new URL(rel, base).href;" in js
    assert "const target=_siteRootUrl('ops-phase');" in js

    assert html.count('onclick="openRecoveryPage()"') == 3
    assert html.count('aria-label="Recovery page"') == 2
    assert "Open recovery page" in html
    assert "function openRecoveryPage()" in js
    assert "function _siteRootUrl(path)" in js
    assert "const target=_siteRootUrl('recovery');" in js


def test_main_shell_ops_navigation_uses_site_root_from_session_routes():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/panels.js', 'utf8');
        const start = source.indexOf("function _siteRootUrl(path){");
        const end = source.indexOf("function openRecoveryPage()", start);
        if (start === -1 || end === -1){
          throw new Error('Could not isolate ops navigation helpers from panels.js');
        }
        const snippet = source.slice(start, end);
        const calls = [];
        const locationRef = {
          origin: 'http://example.com',
          href: 'http://example.com/session/demo/index.html',
          assign: (target) => calls.push(target),
        };
        const context = {
          URL,
          window: { location: locationRef },
          document: { baseURI: 'http://example.com/session/demo/' },
          location: locationRef,
        };
        vm.createContext(context);
        vm.runInContext(snippet, context);
        context.openOpsDashboard();
        if (calls.length !== 1){
          throw new Error('Ops navigation should assign exactly one target URL.');
        }
        if (calls[0] !== 'http://example.com/ops-phase'){
          throw new Error('Ops navigation should leave session-prefixed routes and open the site-root ops shell.');
        }
        console.log('ok');
        """
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "ok"


def test_main_shell_exposes_codex_and_maintenance_settings_entries():
    html = Path("static/index.html").read_text(encoding="utf-8")
    js = Path("static/panels.js").read_text(encoding="utf-8")

    assert 'data-settings-section="codex"' in html
    assert 'id="settingsPaneCodex"' in html
    assert 'id="settingsCodexConfigEditor"' in html
    assert 'data-settings-section="maintenance"' in html
    assert 'id="settingsPaneMaintenance"' in html
    assert 'id="settingsMaintenanceProject"' in html
    assert 'data-settings-section="plugins"' in html
    assert "switchSettingsSection('codex')" in html
    assert "switchSettingsSection('maintenance')" in html
    assert "switchSettingsSection('plugins')" in html

    assert "name==='appearance'||name==='preferences'||name==='providers'||name==='codex'||name==='maintenance'||name==='plugins'||name==='system'" in js
    assert "api('/api/codex-config')" in js
    assert "/api/ops/projects/'+encodeURIComponent(state.selectedProjectId)+'/upstream-sync" in js
    assert "Open Codex settings" in js

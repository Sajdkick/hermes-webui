import subprocess
import textwrap


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

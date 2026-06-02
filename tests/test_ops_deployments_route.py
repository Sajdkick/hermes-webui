import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_node(script: str) -> str:
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_ops_home_deployments_action_opens_deployments_route_not_project_detail():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (async () => {
          const source = fs.readFileSync('static/ops-legacy-home.js', 'utf8');
          const windowRef = { HermesOpsModules: {}, setInterval: () => 1 };
          const rootEl = { contains: () => true, querySelector: () => null, innerHTML: '' };
          const context = {
            console,
            window: windowRef,
            document: { activeElement: null },
            navigator: {},
            URL,
            setTimeout,
            clearTimeout,
            requestAnimationFrame: (cb) => cb(),
          };
          vm.createContext(context);
          vm.runInContext(source, context);

          let deploymentsOpened = 0;
          let projectDetailOpened = 0;
          const dashboard = context.window.HermesOpsModules.home.bindDashboard({
            OPS: {
              projects: [{ id: 'project-1', name: 'Project one' }],
              sessions: [],
              sessionActivity: [],
              sessionActivityGroups: [],
              sessionActivityCollapsed: {},
              sessionActivityInitialized: {},
              sessionActivityExpanded: true,
              quickTaskImages: [],
              quickTaskText: '',
              quickTaskGoalMode: true,
            },
            AgentBridge: {
              sessions: {
                activity: async () => ({ sessions: [], groups: [] }),
                createActivityGroup: async () => ({ group: { id: 'group-1' } }),
                deleteActivityGroup: async () => ({}),
                renameActivityGroup: async () => ({}),
                assignActivityGroup: async () => ({}),
              },
            },
            renderCurrentOpsView: () => {},
            root: () => rootEl,
            esc: (value) => String(value ?? ''),
            svg: { refresh: '', plus: '', play: '', check: '' },
            showError: (error) => { throw error; },
            setBusy: () => {},
            setDashboardTopbar: () => {},
            renderNotifications: () => '',
            normalizedAutoApprovalPolicy: () => ({ enabled: false, rules: [] }),
            loadProjects: async () => [],
            openProjectDetail: async () => { projectDetailOpened += 1; },
            openDeployments: async () => { deploymentsOpened += 1; return 'deployments'; },
            createQuickTask: async () => {},
            executeReadyTasksWithAi: async () => {},
            loadNotifications: async () => [],
            loadOpsRuns: async () => [],
            loadNotificationDiagnostics: async () => null,
            openOpsSession: async () => {},
            findProject: () => ({ id: 'project-1' }),
            projectUsesBranchTitle: () => false,
            projectBranchLabel: () => 'main',
            projectCardTitle: (project) => project.name,
            projectRepositoryLabel: (project) => project.name,
            normalizeRunStatus: (status) => status || 'running',
            runStatusLabel: (status) => status || 'Running',
            runStatusKind: () => 'running',
            formatOpsDateTime: () => 'now',
            renderProjectGitQuickAction: () => '',
            renderProjectPlayQuickAction: () => '',
            renderProjectActivityQuickAction: () => '',
            playStatusFor: () => null,
            sessionAccentStyle: () => '',
            sessionGroupAccentStyle: () => '',
            sessionRefValue: () => '',
            canonicalTaskSessions: () => [],
            projectSessionsFor: () => [],
            isSessionForProject: () => false,
            taskImageLabel: () => '',
            writeStoredJson: () => {},
            sessionActivityStorageKey: 'test-session-activity',
            navigatorRef: {},
            windowRef,
            documentRef: context.document,
            URLRef: URL,
            voiceInput: null,
            MediaRecorderRef: null,
            FileRef: null,
            showPromptDialog: async () => null,
            showConfirmDialog: async () => false,
            requestAnimationFrameRef: (cb) => cb(),
            taskDictationPrompt: '',
            taskDictationAudioBitsPerSecond: 128000,
            runActiveStatusValues: ['running'],
          });

          if (!dashboard || typeof dashboard.handleHomeAction !== 'function') {
            throw new Error('home dashboard did not bind');
          }
          await dashboard.handleHomeAction('view-deployments', null);
          if (deploymentsOpened !== 1) throw new Error('deployments route was not opened');
          if (projectDetailOpened !== 0) throw new Error('project detail route should not open for deployments');
          console.log('ok');
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )
    assert _run_node(script) == "ok"


def test_ops_deployments_module_renders_top_level_project_deployment_panels():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (async () => {
          const source = fs.readFileSync('static/ops-legacy-deployments.js', 'utf8');
          const windowRef = { HermesOpsModules: {} };
          const context = { console, window: windowRef };
          vm.createContext(context);
          vm.runInContext(source, context);

          const rootEl = { innerHTML: '' };
          const apiUrls = [];
          const project = {
            id: 'project-1',
            name: 'Deployable app',
            resolvedPath: '/workspace/deployable-app',
            coreBranch: 'main',
            opsCapabilities: { deployment: true },
          };
          const OPS = {
            view: 'home',
            projects: [],
            deploymentsByProject: {},
            deploymentBusyByProject: {},
            currentProject: null,
            taskData: null,
            showCreate: false,
          };
          const dashboard = context.window.HermesOpsModules.deployments.bindDashboard({
            OPS,
            api: async (url) => {
              apiUrls.push(url);
              if (url === '/api/core/deployments/providers') {
                return { providers: [{ id: 'manual', label: 'Manual record' }, { id: 'local-legacy', label: 'Cloud Terminal host (legacy)' }], defaultProvider: 'manual' };
              }
              return {
                deployment: { status: 'published', provider: 'local-legacy', source: 'cloud-terminal', slug: 'alternativedata', databaseMode: 'persistent', environment: 'production', summary: 'Cloud Terminal deployment `alternativedata` is published.' },
                artifacts: [{ kind: 'cloud-terminal-snapshot', relativePath: '.deployments/items/alternativedata/source' }],
                logs: [{ message: 'Cloud Terminal deployment metadata loaded read-only; database mode was preserved.' }],
              };
            },
            projectUrl: (projectId, suffix) => `/api/ops/projects/${encodeURIComponent(projectId)}${suffix || ''}`,
            coreUrl: (suffix) => `/api/core${suffix || ''}`,
            coreProjectUrl: (projectId, suffix) => `/api/core/projects/${encodeURIComponent(projectId)}${suffix || ''}`,
            root: () => rootEl,
            renderCurrentOpsView: () => {},
            showToast: () => {},
            showPromptDialog: async () => null,
            showConfirmDialog: async () => false,
            esc: (value) => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'),
            svg: { refresh: '<r/>', plus: '<p/>', check: '<c/>', play: '<y/>' },
            nameOf: (entry) => entry.name || entry.id,
            projectPath: (entry) => entry.resolvedPath || entry.path || '',
            setDashboardTopbar: () => {},
            renderLoading: (label) => { rootEl.innerHTML = label; },
            loadProjects: async () => [project],
            windowRef,
          });

          if (!dashboard || typeof dashboard.openDeployments !== 'function') {
            throw new Error('deployments dashboard did not bind');
          }
          await dashboard.openDeployments();
          if (OPS.view !== 'deployments') throw new Error(`expected deployments view, got ${OPS.view}`);
          if (!apiUrls.includes('/api/core/deployments/providers')) throw new Error('deployment providers endpoint was not loaded');
          if (!apiUrls.includes('/api/core/projects/project-1/deployment')) throw new Error('core deployment endpoint was not loaded');
          for (const text of ['Deployments', 'Deployment projects', 'Deployable app', 'Cloud Terminal deployment `alternativedata` is published.', '.deployments/items/alternativedata/source', 'Cloud Terminal host (legacy)', 'Cloud Terminal', 'alternativedata', 'persistent database', 'Redeploy', 'Record', 'Execute']) {
            if (!rootEl.innerHTML.includes(text)) throw new Error(`missing rendered text: ${text}`);
          }
          console.log('ok');
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )
    assert _run_node(script) == "ok"


def test_ops_deployments_redeploy_action_posts_core_redeploy_preserving_database():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (async () => {
          const source = fs.readFileSync('static/ops-legacy-deployments.js', 'utf8');
          const windowRef = {
            HermesOpsModules: {},
            localStorage: {
              getItem: (key) => key === 'cloudTerminalSessionToken' ? 'ct-token' : null,
            },
          };
          const context = { console, window: windowRef };
          vm.createContext(context);
          vm.runInContext(source, context);

          const rootEl = { innerHTML: '' };
          const calls = [];
          let confirmOptions = null;
          let toastMessage = '';
          let progressRendered = false;
          const OPS = {
            view: 'deployments',
            projects: [{ id: 'project-1', name: 'Alternative Data', opsCapabilities: { deployment: true } }],
            deploymentsByProject: {
              'project-1': {
                deployment: {
                  status: 'published',
                  provider: 'local-legacy',
                  source: 'cloud-terminal',
                  slug: 'alternativedata',
                  databaseMode: 'persistent',
                  database: { mode: 'persistent', preservesExistingData: true },
                },
                artifacts: [],
                logs: [],
              },
            },
            deploymentBusyByProject: {},
            deploymentProviders: [{ id: 'local-legacy', label: 'Cloud Terminal host (legacy)', capabilities: { redeploy: true, preservesDatabase: true } }],
          };
          const dashboard = context.window.HermesOpsModules.deployments.bindDashboard({
            OPS,
            api: async (url, options = {}) => {
              calls.push({ url, method: options.method || 'GET', headers: options.headers || {}, body: options.body ? JSON.parse(options.body) : null });
              if (url === '/api/core/projects/project-1/deployment/redeploy') {
                return { operation: { status: 'succeeded' } };
              }
              if (url === '/api/core/projects/project-1/deployment') {
                return OPS.deploymentsByProject['project-1'];
              }
              throw new Error(`unexpected api url: ${url}`);
            },
            projectUrl: (projectId, suffix) => `/api/ops/projects/${encodeURIComponent(projectId)}${suffix || ''}`,
            coreUrl: (suffix) => `/api/core${suffix || ''}`,
            coreProjectUrl: (projectId, suffix) => `/api/core/projects/${encodeURIComponent(projectId)}${suffix || ''}`,
            root: () => rootEl,
            renderCurrentOpsView: () => {
              if (OPS.deploymentBusyByProject['project-1'] && OPS.deploymentProgressByProject && OPS.deploymentProgressByProject['project-1']) {
                progressRendered = true;
              }
            },
            showToast: (message) => { toastMessage = message; },
            showPromptDialog: async () => null,
            showConfirmDialog: async (options) => { confirmOptions = options; return true; },
            esc: (value) => String(value ?? ''),
            svg: { refresh: '<r/>', plus: '<p/>', check: '<c/>', play: '<y/>' },
            nameOf: (entry) => entry.name || entry.id,
            projectPath: () => '',
            setDashboardTopbar: () => {},
            renderLoading: () => {},
            loadProjects: async () => OPS.projects,
            windowRef,
          });

          await dashboard.redeployProjectDeployment('project-1');
          const redeployCall = calls.find((call) => call.url === '/api/core/projects/project-1/deployment/redeploy');
          if (!redeployCall) throw new Error('redeploy endpoint was not called');
          if (redeployCall.method !== 'POST') throw new Error('redeploy must be POST');
          if (redeployCall.body.confirm !== 'redeploy') throw new Error('redeploy confirmation missing');
          if (redeployCall.body.databaseMode !== 'persistent') throw new Error('persistent database mode was not preserved');
          if (redeployCall.headers['X-Session-Token'] !== 'ct-token') throw new Error('Cloud Terminal session token was not forwarded');
          if (!confirmOptions || !confirmOptions.message.includes('preserving the existing persistent deployment database')) {
            throw new Error('confirmation copy does not explain database preservation');
          }
          if (!progressRendered) throw new Error('redeploy progress state was not rendered before the API returned');
          if (!toastMessage.includes('redeploy succeeded')) throw new Error(`unexpected toast: ${toastMessage}`);
          console.log('ok');
        })().catch((error) => { console.error(error); process.exit(1); });
        """
    )
    assert _run_node(script) == "ok"


def test_ops_dashboard_shell_and_dispatcher_register_deployments_view():
    dashboard = (ROOT / "static" / "ops-legacy-dashboard.js").read_text(encoding="utf-8")
    shell = (ROOT / "static" / "ops-legacy-dashboard-shell.js").read_text(encoding="utf-8")
    actions = (ROOT / "static" / "ops-legacy-dashboard-actions.js").read_text(encoding="utf-8")
    deployments = (ROOT / "static" / "ops-legacy-deployments.js").read_text(encoding="utf-8")

    assert "renderDeploymentsRef:()=>renderDeployments" in dashboard
    assert "if(normalized.view==='deployments')" in dashboard
    assert "return DASHBOARD_DEPLOYMENTS.openDeployments({historyMode:'skip'});" in dashboard
    assert "openDeployments:(options)=>openDeployments(options)" in dashboard
    assert "const openDeployments=DASHBOARD_DEPLOYMENTS.openDeployments" in dashboard
    assert "const refreshDeployments=DASHBOARD_DEPLOYMENTS.refreshDeployments" in dashboard
    assert "const redeployProjectDeployment=DASHBOARD_DEPLOYMENTS.redeployProjectDeployment" in dashboard
    assert "root:typeof root==='function'?root:null" in dashboard
    assert "coreProjectUrl:(projectId,suffix)=>`/api/core/projects/" in dashboard
    assert "loadProjects:()=>loadProjects()" in dashboard

    assert "view==='projects'||view==='deployments'" in shell
    assert "renderDeploymentsRef" in shell
    assert "OPS.view==='deployments'" in shell

    assert "const refreshDeployments=ctx&&ctx.refreshDeployments" in actions
    assert "const redeployProjectDeployment=ctx&&ctx.redeployProjectDeployment" in actions
    assert "action==='refresh-deployments'" in actions
    assert "action==='redeploy-deployment'" in actions

    assert "function renderDeployments()" in deployments
    assert "async function openDeployments(options)" in deployments
    assert "async function redeployProjectDeployment(projectId)" in deployments
    assert "coreApiUrl('/deployments/providers')" in deployments
    assert "deploymentProjectUrl(id,'/deployment')" in deployments
    assert "deploymentProjectUrl(id,'/deployment/redeploy')" in deployments
    assert "data-ops-action=\"refresh-deployments\"" in deployments
    assert "data-ops-action=\"redeploy-deployment\"" in deployments


def test_play_proxy_run_context_script_is_vendored_and_served_at_root():
    routes = (ROOT / "api" / "routes.py").read_text(encoding="utf-8")
    script = (ROOT / "static" / "play-proxy-run-context.js").read_text(encoding="utf-8")

    assert 'parsed.path == "/play-proxy-run-context.js"' in routes
    assert 'Content-Type", "text/javascript; charset=utf-8"' in routes
    assert "window.__ctPlayProxyRunContextPatched" in script
    assert "data-ct-play-run" in script

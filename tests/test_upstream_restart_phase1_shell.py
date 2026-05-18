import json
from pathlib import Path
import subprocess
import textwrap
from urllib.parse import urlparse


class _FakeHandler:
    def __init__(self):
        self.status = None
        self.sent_headers = []
        self.body = bytearray()
        self.wfile = self
        self.headers = {}

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent_headers.append((name, value))

    def end_headers(self):
        pass

    def write(self, data):
        self.body.extend(data)

    def header(self, name):
        for key, value in self.sent_headers:
            if key.lower() == name.lower():
                return value
        return None


def test_root_landing_route_serves_legacy_ops_dashboard():
    from api.routes import handle_get

    handler = _FakeHandler()
    parsed = urlparse("http://example.com/")

    assert handle_get(handler, parsed) is True
    assert handler.status == 200
    assert (handler.header("Content-Type") or "").startswith("text/html")
    html = bytes(handler.body).decode("utf-8")
    assert 'src="static/ops-legacy-host.js?v=' in html
    assert 'src="static/ops-legacy-dashboard.js?v=' in html
    assert 'href="index.html" title="Back to Hermes"' in html
    assert 'id="app"' not in html


def test_chat_shell_stays_available_at_index_html():
    from api.routes import handle_get

    handler = _FakeHandler()
    parsed = urlparse("http://example.com/index.html")

    handle_get(handler, parsed)
    assert handler.status == 200
    assert (handler.header("Content-Type") or "").startswith("text/html")
    html = bytes(handler.body).decode("utf-8")
    assert 'id="appTitlebarTitle"' in html
    assert 'src="static/ops-legacy-host.js?v=' not in html


def test_ops_shell_route_is_registered_and_serves_html():
    from api.routes import handle_get

    handler = _FakeHandler()
    parsed = urlparse("http://example.com/ops")

    assert handle_get(handler, parsed) is True
    assert handler.status == 200
    assert (handler.header("Content-Type") or "").startswith("text/html")
    html = bytes(handler.body).decode("utf-8")
    assert 'document.write(\'<base href="' in html
    assert 'href="static/ops-legacy.css?v=' in html
    assert 'src="static/ops-legacy-host.js?v=' in html
    assert 'src="static/ops-legacy-dashboard.js?v=' in html
    assert 'src="static/ops-legacy-projects.js?v=' in html
    assert 'src="static/ops-legacy-task-actions.js?v=' in html
    assert 'src="static/cloud-terminal-entry.js?v=' not in html
    assert 'Phase 10 post-restart admin slice' not in html


def test_ops_phase_shell_route_is_registered_and_serves_html():
    from api.routes import handle_get

    handler = _FakeHandler()
    parsed = urlparse("http://example.com/ops-phase")

    assert handle_get(handler, parsed) is True
    assert handler.status == 200
    assert (handler.header("Content-Type") or "").startswith("text/html")
    html = bytes(handler.body).decode("utf-8")
    assert 'data-ops-shell="cloud-terminal"' in html
    assert 'href="static/cloud-terminal.css?v=__WEBUI_VERSION__"' not in html
    assert 'href="static/cloud-terminal.css?v=' in html
    assert 'src="static/ops-github-admin.js?v=' in html
    assert 'src="static/ops-database.js?v=' in html
    assert 'src="static/ops-git.js?v=' in html
    assert 'src="static/ops-runs.js?v=' in html
    assert 'src="static/ops-upstream-sync.js?v=' in html
    assert 'src="static/ops-projects.js?v=' in html
    assert 'src="static/cloud-terminal-entry.js?v=' in html
    assert 'href="index.html">Back to Hermes' in html
    assert 'href="api/ops/shell"' in html


def test_ops_phase_shell_back_link_resolves_to_main_app_under_trailing_slash_routes():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const html = fs.readFileSync('static/ops-shell.html', 'utf8');
        const match = html.match(/<script>(\\(function\\(\\)\\{[\\s\\S]*?\\}\\)\\(\\))<\\/script>/);
        if (!match) throw new Error('Missing ops shell base bootstrap.');
        const bootstrap = match[1];

        function resolveBase(pathname){
          const writes = [];
          const context = {
            location: { origin: 'http://example.com', pathname },
            document: { write: (value) => writes.push(value) },
          };
          vm.createContext(context);
          vm.runInContext(bootstrap, context);
          return writes[0];
        }

        const plain = resolveBase('/demo/ops-phase');
        const trailing = resolveBase('/demo/ops-phase/');
        if (plain !== '<base href="http://example.com/demo/">') {
          throw new Error('Plain ops-phase route should resolve to the app root base.');
        }
        if (trailing !== '<base href="http://example.com/demo/">') {
          throw new Error('Trailing-slash ops-phase route should resolve to the app root base.');
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


def test_session_prefixed_ops_routes_redirect_to_site_root_ops_phase():
    from api.routes import handle_get

    stale_ops = _FakeHandler()
    assert handle_get(stale_ops, urlparse("http://example.com/session/demo/ops")) is True
    assert stale_ops.status == 302
    assert stale_ops.header("Location") == "/ops-phase"
    assert stale_ops.header("Cache-Control") == "no-store"

    stale_ops_phase = _FakeHandler()
    assert handle_get(stale_ops_phase, urlparse("http://example.com/session/demo/ops-phase?via=cache")) is True
    assert stale_ops_phase.status == 302
    assert stale_ops_phase.header("Location") == "/ops-phase?via=cache"
    assert stale_ops_phase.header("Cache-Control") == "no-store"


def test_ops_shell_bootstrap_api_is_registered():
    from api.routes import handle_get

    handler = _FakeHandler()
    parsed = urlparse("http://example.com/api/ops/shell")

    assert handle_get(handler, parsed) is True
    assert handler.status == 200
    assert (handler.header("Content-Type") or "").startswith("application/json")
    payload = json.loads(bytes(handler.body).decode("utf-8"))
    assert payload["phase"].startswith("phase-")
    assert payload["route"] == "/ops-phase"
    assert payload["assets"]["entryScript"] == "/static/cloud-terminal-entry.js"
    assert payload["assets"]["entryStylesheet"] == "/static/cloud-terminal.css"
    assert payload["assets"]["githubScript"] == "/static/ops-github-admin.js"
    assert payload["assets"]["databaseScript"] == "/static/ops-database.js"
    assert payload["assets"]["gitScript"] == "/static/ops-git.js"
    assert payload["assets"]["runsScript"] == "/static/ops-runs.js"
    assert payload["assets"]["upstreamSyncScript"] == "/static/ops-upstream-sync.js"
    assert payload["assets"]["projectsScript"] == "/static/ops-projects.js"


def test_ops_entry_uses_base_relative_shell_fetch():
    source = Path("static/cloud-terminal-entry.js").read_text(encoding="utf-8")

    assert "const base=(typeof document!=='undefined' && document.baseURI)" in source
    assert "return new URL(rel, base).href;" in source
    assert "fetch(appUrl('api/ops/shell')" in source


def test_legacy_ops_shell_keeps_restart_compatibility_contract():
    host_source = Path("static/ops-legacy-host.js").read_text(encoding="utf-8")
    bridge_source = Path("static/ops-legacy-agent-bridge.js").read_text(encoding="utf-8")
    dashboard_source = Path("static/ops-legacy-dashboard.js").read_text(encoding="utf-8")
    quick_actions_source = Path("static/ops-legacy-dashboard-quick-actions.js").read_text(encoding="utf-8")
    health_source = Path("static/ops-legacy-health.js").read_text(encoding="utf-8")
    deployments_source = Path("static/ops-legacy-deployments.js").read_text(encoding="utf-8")
    task_actions_source = Path("static/ops-legacy-task-actions.js").read_text(encoding="utf-8")

    assert "window.projectUrl = projectUrl;" in host_source
    assert "function ensureLocalDialog(){" in host_source
    assert "const LOCAL_DIALOG = {" in host_source
    assert "api('/api/ops/notifications/pending')" in bridge_source
    assert "api('/api/ops/runs')" in bridge_source
    assert "return api('/api/ops/sessions').catch(()=>api('/api/sessions'));" in bridge_source
    assert "return api('/api/ops/sessions').then(data=>({" in bridge_source
    assert "/sessions/launch" in bridge_source
    assert "/session/close" in bridge_source
    assert "/session/ensure" not in bridge_source
    assert "function normalizeRunStatus(value){" in dashboard_source
    assert "function runStatusLabel(status){" in dashboard_source
    assert "function runStatusKind(status){" in dashboard_source
    assert "function renderProjectPlayQuickAction(project){" in dashboard_source
    assert "async function renderProjectPlayQuickAction(project){" not in dashboard_source
    assert "function renderProjectPlayQuickAction(project){" in quick_actions_source
    assert "async function renderProjectPlayQuickAction(project){" not in quick_actions_source
    home_source = Path("static/ops-legacy-home.js").read_text(encoding="utf-8")
    projects_source = Path("static/ops-legacy-projects.js").read_text(encoding="utf-8")
    play_source = Path("static/ops-legacy-play.js").read_text(encoding="utf-8")
    notifications_source = Path("static/ops-legacy-notifications.js").read_text(encoding="utf-8")
    assert "settings.showPlayAction===false?'':renderProjectPlayQuickAction(project)" in home_source
    assert "renderSessionWorkspaceActions({projectId:project.id,project},{showPlayAction:false})" in projects_source
    assert "data-ops-log-scroll-key=\"play-logs:${esc(projectId)}\"" in play_source
    assert "data-ops-log-scroll-key=\"play-notification:${esc(note&&note.id||'')}\"" in notifications_source
    assert "function captureLogScrollState(container){" in home_source
    assert "function restoreLogScrollState(container,snapshot){" in projects_source
    assert "function restoreLogScrollState(container,snapshot){" in Path("static/ops-legacy-project-detail.js").read_text(encoding="utf-8")
    assert "data-ops-log-scroll-key=\"runtime-play-logs:" in Path("static/ops-runtime.js").read_text(encoding="utf-8")
    assert "restoreLogScrollState(root,logScrollState);" in Path("static/ops-projects.js").read_text(encoding="utf-8")
    assert "if(!capabilities.dependencyHealth){" in health_source
    assert "if(!capabilities.deployment){" in deployments_source
    assert "function currentOpsModelState(){" in task_actions_source
    assert "function currentOpsProfile(project){" in task_actions_source
    assert "typeof _readPersistedModelState==='function'" in task_actions_source
    assert "model_provider:modelState.model_provider||null" in task_actions_source
    assert "profile:currentOpsProfile(project)" in task_actions_source


def test_ops_shell_assets_are_served_by_static_route():
    from api.routes import handle_get

    legacy_script = _FakeHandler()
    assert handle_get(legacy_script, urlparse("http://example.com/static/ops-legacy-host.js")) is True
    assert legacy_script.status == 200
    assert (legacy_script.header("Content-Type") or "").startswith("application/javascript")

    legacy_dashboard = _FakeHandler()
    assert handle_get(legacy_dashboard, urlparse("http://example.com/static/ops-legacy-dashboard.js")) is True
    assert legacy_dashboard.status == 200
    assert (legacy_dashboard.header("Content-Type") or "").startswith("application/javascript")

    legacy_stylesheet = _FakeHandler()
    assert handle_get(legacy_stylesheet, urlparse("http://example.com/static/ops-legacy.css")) is True
    assert legacy_stylesheet.status == 200
    assert (legacy_stylesheet.header("Content-Type") or "").startswith("text/css")

    script = _FakeHandler()
    assert handle_get(script, urlparse("http://example.com/static/cloud-terminal-entry.js")) is True
    assert script.status == 200
    assert (script.header("Content-Type") or "").startswith("application/javascript")

    stylesheet = _FakeHandler()
    assert handle_get(stylesheet, urlparse("http://example.com/static/cloud-terminal.css")) is True
    assert stylesheet.status == 200
    assert (stylesheet.header("Content-Type") or "").startswith("text/css")

    git_script = _FakeHandler()
    assert handle_get(git_script, urlparse("http://example.com/static/ops-git.js")) is True
    assert git_script.status == 200
    assert (git_script.header("Content-Type") or "").startswith("application/javascript")

    runs_script = _FakeHandler()
    assert handle_get(runs_script, urlparse("http://example.com/static/ops-runs.js")) is True
    assert runs_script.status == 200
    assert (runs_script.header("Content-Type") or "").startswith("application/javascript")

    github_script = _FakeHandler()
    assert handle_get(github_script, urlparse("http://example.com/static/ops-github-admin.js")) is True
    assert github_script.status == 200
    assert (github_script.header("Content-Type") or "").startswith("application/javascript")

    database_script = _FakeHandler()
    assert handle_get(database_script, urlparse("http://example.com/static/ops-database.js")) is True
    assert database_script.status == 200
    assert (database_script.header("Content-Type") or "").startswith("application/javascript")

    upstream_sync_script = _FakeHandler()
    assert handle_get(upstream_sync_script, urlparse("http://example.com/static/ops-upstream-sync.js")) is True
    assert upstream_sync_script.status == 200
    assert (upstream_sync_script.header("Content-Type") or "").startswith("application/javascript")

    projects_script = _FakeHandler()
    assert handle_get(projects_script, urlparse("http://example.com/static/ops-projects.js")) is True
    assert projects_script.status == 200
    assert (projects_script.header("Content-Type") or "").startswith("application/javascript")


def test_legacy_bridge_merges_done_notifications_from_runs():
    script = textwrap.dedent(
        """
        (async () => {
        const fs = require('fs');
        const vm = require('vm');

        const bridgeSource = fs.readFileSync('static/ops-legacy-agent-bridge.js', 'utf8');
        const recent = new Date().toISOString();
        const api = async (path) => {
          if (path === '/api/ops/notifications/pending'){
            return {
              notifications: [{
                notificationKey: 'approval:session-1:a1',
                kind: 'approval',
                sessionId: 'session-1',
                project: { id: 'project-1', name: 'Hermes' },
                task: { id: 'task-1', text: 'Pending approval' },
                session: { title: 'Approval session' },
                approvalId: 'a1',
                description: 'Need approval',
                command: 'git push'
              }]
            };
          }
          if (path === '/api/ops/runs'){
            return {
              runs: [{
                id: 'run-1',
                status: 'succeeded',
                summary: 'Task completed successfully.',
                completedAt: recent,
                sessionId: 'session-2',
                projectId: 'project-1',
                taskId: 'task-2',
                project: { id: 'project-1', name: 'Hermes' },
                task: { id: 'task-2', text: 'Completed task' },
                session: { session_id: 'session-2', title: 'Completed session' }
              }]
            };
          }
          throw new Error('Unexpected API path: ' + path);
        };

        const context = {
          console,
          api,
          projectUrl: (projectId, suffix='') => '/api/ops/projects/' + projectId + suffix,
          fetch: async () => ({ ok: true, json: async () => ({}) }),
          location: { href: 'http://example.com/ops' },
          URL,
          URLSearchParams,
          EventSource: function EventSource(){},
          FormData: function FormData(){},
          window: {},
          document: {},
          setTimeout,
          clearTimeout,
          Date,
        };
        context.window = context;
        vm.createContext(context);
        vm.runInContext(bridgeSource, context);
        const payload = await context.window.AgentBridge.notifications.list();
        if (!Array.isArray(payload.notifications) || payload.notifications.length !== 2){
          throw new Error('Expected pending and done notifications.');
        }
        const done = payload.notifications.find((entry) => entry.kind === 'done');
        if (!done){
          throw new Error('Expected a synthesized done notification.');
        }
        if (done.run_id !== 'run-1'){
          throw new Error('Done notification did not preserve run id.');
        }
        if (done.message !== 'Task completed successfully.'){
          throw new Error('Done notification did not use run summary.');
        }
        console.log('ok');
        })().catch((error) => {
          console.error(error && error.stack ? error.stack : error);
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


def test_legacy_bridge_preserves_play_notifications_and_opens_them_locally():
    script = textwrap.dedent(
        """
        (async () => {
        const fs = require('fs');
        const vm = require('vm');

        const bridgeSource = fs.readFileSync('static/ops-legacy-agent-bridge.js', 'utf8');
        const playSource = fs.readFileSync('static/ops-legacy-play.js', 'utf8');
        const api = async (path) => {
          if (path === '/api/ops/notifications/pending'){
            return {
              notifications: [{
                notificationKey: 'play:project-1:ready:2026-05-06T06:00:00Z',
                kind: 'play',
                message: 'Play app is ready for inspection.',
                project: { id: 'project-1', name: 'Hermes' },
                inspectUrl: '/play-project/project-1/app',
                playStatus: 'ready',
                playNeedsRepair: false,
                playFallbackError: '',
                playRepairAvailable: true,
                playPrimaryAction: 'open-inspect',
                terminalTarget: { projectId: 'project-1', taskId: '', sessionId: '', runId: '' },
                updatedAt: '2026-05-06T06:00:00Z'
              }]
            };
          }
          if (path === '/api/ops/runs'){
            return { runs: [] };
          }
          if (path === '/api/ops/notifications/dismissed'){
            return { dismissed: [] };
          }
          throw new Error('Unexpected API path: ' + path);
        };

        const assigned = [];
        const context = {
          console,
          api,
          projectUrl: (projectId, suffix='') => '/api/ops/projects/' + projectId + suffix,
          fetch: async () => ({ ok: true, json: async () => ({}) }),
          location: { href: 'http://example.com/ops', assign: (url) => assigned.push(url) },
          URL,
          URLSearchParams,
          EventSource: function EventSource(){},
          FormData: function FormData(){},
          window: {},
          document: {},
          setTimeout,
          clearTimeout,
          Date,
        };
        context.window = context;
        vm.createContext(context);
        vm.runInContext(bridgeSource, context);
        const payload = await context.window.AgentBridge.notifications.list();
        const play = payload.notifications.find((entry) => entry.kind === 'play');
        if (!play){
          throw new Error('Expected a synthesized play notification.');
        }
        if (play.inspectUrl !== '/play-project/project-1/app'){
          throw new Error('Play notification did not preserve the inspect URL.');
        }
        if (play.playRepairAvailable !== true || play.playPrimaryAction !== 'open-inspect'){
          throw new Error('Play notification repair/action metadata was not preserved.');
        }

        vm.runInContext(playSource, context);
        const dashboard = context.window.HermesOpsModules.play.bindDashboard({
          OPS: {
            notifications: [play],
            playStatusByProject: {},
            playBusyByProject: {},
            playLogsByProject: {},
            playSnapshotsByProject: {},
            playScreenshotsByProject: {},
          },
          api,
          projectUrl: (projectId, suffix='') => '/api/ops/projects/' + projectId + suffix,
          renderCurrentOpsView: () => {},
          showToast: (message) => { throw new Error(message); },
          esc: (value) => String(value ?? ''),
          svg: {},
          AgentBridge: {
            play: {
              status: async () => ({}),
              logs: async () => ({ text: '' }),
              start: async () => ({}),
              restart: async () => ({}),
              stop: async () => ({}),
              notificationTarget: async () => {
                throw new Error('play notificationTarget should not be called for local play notifications');
              },
            },
            runtime: {},
          },
          loadNotifications: async () => [],
          playInspectOverlayUrl: (note) => note && note.inspectUrl ? note.inspectUrl : '',
          openProjectDetail: async () => null,
          notificationById: (id) => id === play.id ? play : null,
          notificationTarget: (note) => note && note.terminalTarget ? note.terminalTarget : {},
          playNotificationFallbackError: (note) => note && note.playFallbackError || '',
          windowRef: context.window,
        });

        await dashboard.openPlayNotification(play.id);
        if (assigned[0] !== '/play-project/project-1/app'){
          throw new Error('Play notification did not open using the local inspect URL.');
        }
        console.log('ok');
        })().catch((error) => {
          console.error(error && error.stack ? error.stack : error);
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


def test_legacy_bridge_prefers_locked_build_notification_over_newer_ready_note():
    script = textwrap.dedent(
        """
        (async () => {
        const fs = require('fs');
        const vm = require('vm');

        const bridgeSource = fs.readFileSync('static/ops-legacy-agent-bridge.js', 'utf8');
        const api = async (path) => {
          if (path === '/api/ops/notifications/pending'){
            return {
              notifications: [
                {
                  notificationKey: 'play:project-1:building:2026-05-06T06:00:00Z',
                  kind: 'play',
                  message: 'Play build in progress.',
                  project: { id: 'project-1', name: 'Hermes' },
                  inspectUrl: '',
                  playStatus: 'building',
                  playLocked: true,
                  playNeedsRepair: false,
                  terminalTarget: { projectId: 'project-1', taskId: '', sessionId: '', runId: '' },
                  updatedAt: '2026-05-06T06:00:00Z'
                },
                {
                  notificationKey: 'play:project-1:ready:2026-05-06T06:05:00Z',
                  kind: 'play',
                  message: 'Stale ready notification from the previous build.',
                  project: { id: 'project-1', name: 'Hermes' },
                  inspectUrl: '/play-project/project-1/app',
                  playStatus: 'ready',
                  playLocked: false,
                  playNeedsRepair: false,
                  terminalTarget: { projectId: 'project-1', taskId: '', sessionId: '', runId: '' },
                  updatedAt: '2026-05-06T06:05:00Z'
                }
              ]
            };
          }
          if (path === '/api/ops/runs') return { runs: [] };
          if (path === '/api/ops/notifications/dismissed') return { dismissed: [] };
          throw new Error('Unexpected API path: ' + path);
        };
        const context = {
          console,
          api,
          projectUrl: (projectId, suffix='') => '/api/ops/projects/' + projectId + suffix,
          fetch: async () => ({ ok: true, json: async () => ({}) }),
          location: { href: 'http://example.com/ops' },
          URL,
          URLSearchParams,
          EventSource: function EventSource(){},
          FormData: function FormData(){},
          window: {},
          document: {},
          setTimeout,
          clearTimeout,
          Date,
        };
        context.window = context;
        vm.createContext(context);
        vm.runInContext(bridgeSource, context);
        const payload = await context.window.AgentBridge.notifications.list();
        const playNotes = payload.notifications.filter((entry) => entry.kind === 'play');
        if (playNotes.length !== 1){
          throw new Error('Expected exactly one compacted play notification, got ' + playNotes.length);
        }
        if (playNotes[0].playStatus !== 'building' || playNotes[0].playLocked !== true){
          throw new Error('Compaction should keep the active locked build notification over a newer stale ready note.');
        }
        console.log('ok');
        })().catch((error) => {
          console.error(error && error.stack ? error.stack : error);
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


def test_play_notification_click_starts_build_and_opens_inspect_url():
    script = textwrap.dedent(
        """
        (async () => {
        const fs = require('fs');
        const vm = require('vm');

        const playSource = fs.readFileSync('static/ops-legacy-play.js', 'utf8');
        const notificationsSource = fs.readFileSync('static/ops-legacy-notifications.js', 'utf8');
        const assigned = [];
        const toasts = [];
        const startCalls = [];
        let notificationRefreshes = 0;
        let statusCalls = 0;
        const note = {
          id: 'play:project-1:run-1:stale:now',
          kind: 'play',
          message: 'Play handoff needs attention.',
          project_id: 'project-1',
          inspectUrl: '',
          playStatus: 'stale',
          playNeedsRepair: true,
          playRepairAvailable: true,
          playPrimaryAction: 'start-inspect',
          terminalTarget: { projectId: 'project-1', runId: 'run-1', taskId: 'task-1', sessionId: 'session-1' },
        };
        const context = {
          console,
          URL,
          setTimeout: (fn) => { fn(); return 1; },
          clearTimeout: () => {},
          window: {},
        };
        context.window = context;
        context.location = { href: 'http://example.com/ops', assign: (url) => assigned.push(url) };
        vm.createContext(context);
        vm.runInContext(notificationsSource, context);
        const notificationDashboard = context.window.HermesOpsModules.notifications.bindDashboard({
          OPS: { notifications: [note], projects: [], sessions: [] },
          AgentBridge: {
            notifications: { list: async () => ({ notifications: [note] }), dismiss: async () => ({}) },
            runs: { list: async () => ({ runs: [] }) },
            sessions: { list: async () => ({ sessions: [] }) },
          },
          renderCurrentOpsView: () => {},
          showToast: (message) => { toasts.push(message); },
          esc: (value) => String(value ?? ''),
          svg: {},
          openProjectDetail: async () => { throw new Error('render should not open project'); },
          openOpsSession: async () => { throw new Error('render should not open session'); },
          openRunTarget: async () => { throw new Error('render should not open run'); },
          loadRunDetail: async () => ({}),
          loadOpsRuns: async () => [],
          windowRef: context.window,
          documentRef: { activeElement: null },
        });
        const rendered = notificationDashboard.renderNotification(note);
        if (!rendered.includes('data-ops-action="open-play-notification"')){
          throw new Error('Stale Play notification did not render with the Play open action.');
        }
        if (rendered.includes('data-ops-action="open-notification-target"')){
          throw new Error('Stale Play notification still renders the chat/project target action.');
        }
        const buildingNote = {
          ...note,
          id: 'play:project-1:run-1:building:now',
          message: 'Play build is running.',
          inspectUrl: '',
          playStatus: 'building',
          playNeedsRepair: false,
          playLocked: true,
          playPrimaryAction: '',
        };
        const buildingRendered = notificationDashboard.renderNotification(buildingNote);
        if (buildingRendered.includes('data-ops-action="open-play-notification"')){
          throw new Error('Building Play notification should not render an open action while locked.');
        }
        if (!buildingRendered.includes('Play build') || !buildingRendered.includes('Locked until the Play build finishes')){
          throw new Error('Building Play notification did not show the locked build state.');
        }
        vm.runInContext(playSource, context);
        const playOps = {
          notifications: [note],
          playStatusByProject: {},
          playBusyByProject: {},
          playLogsByProject: {},
          playSnapshotsByProject: {},
          playScreenshotsByProject: {},
        };
        const dashboard = context.window.HermesOpsModules.play.bindDashboard({
          OPS: playOps,
          api: async () => ({}),
          projectUrl: (projectId, suffix='') => '/api/ops/projects/' + projectId + suffix,
          renderCurrentOpsView: () => {},
          showToast: (message) => { toasts.push(message); },
          esc: (value) => String(value ?? ''),
          svg: {},
          AgentBridge: {
            play: {
              status: async () => {
                statusCalls += 1;
                if (statusCalls === 1){
                  return { projectId: 'project-1', configured: true, valid: true, configExists: true, status: 'idle', running: false, ready: false, inspectUrl: '' };
                }
                return { projectId: 'project-1', configured: true, valid: true, configExists: true, status: 'ready', running: true, ready: true, inspectUrl: '/play-project/project-1/app' };
              },
              logs: async () => ({ text: '' }),
              start: async (projectId, payload) => {
                startCalls.push({ projectId, payload });
                return { status: { projectId, configured: true, valid: true, configExists: true, status: 'building', running: true, ready: false, inspectUrl: '' } };
              },
              restart: async () => ({}),
              stop: async () => ({}),
            },
            runtime: {},
          },
          loadNotifications: async () => {
            notificationRefreshes += 1;
            playOps.notifications = [{ ...buildingNote, id: 'play:project-1:run-1:building:fresh' }];
            return playOps.notifications;
          },
          playInspectOverlayUrl: (item) => item && item.inspectUrl ? item.inspectUrl : '',
          openProjectDetail: async () => { throw new Error('should not open the project/chat target'); },
          notificationById: (id) => id === note.id ? note : null,
          notificationTarget: (item) => item && item.terminalTarget ? item.terminalTarget : {},
          playNotificationFallbackError: (item) => item && item.playFallbackError || '',
          windowRef: context.window,
        });

        await dashboard.openPlayNotification(note.id);
        if (assigned[0] !== '/play-project/project-1/app'){
          throw new Error('Play notification did not open the inspect URL after starting Play.');
        }
        if (startCalls.length !== 1 || startCalls[0].projectId !== 'project-1'){
          throw new Error('Play notification did not start Play for the project.');
        }
        if (startCalls[0].payload.runId !== 'run-1' || startCalls[0].payload.taskId !== 'task-1' || startCalls[0].payload.sessionId !== 'session-1'){
          throw new Error('Play notification did not preserve terminal target metadata when starting Play.');
        }
        if (notificationRefreshes < 1){
          throw new Error('Play notification start did not refresh notifications immediately.');
        }
        if (playOps.notifications.some((item) => item.id === note.id)){
          throw new Error('Old Play notification still lingered after the build notification refresh.');
        }
        console.log('ok');
        })().catch((error) => {
          console.error(error && error.stack ? error.stack : error);
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


def test_ops_host_api_allows_domain_error_payloads_when_requested():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/ops-legacy-host.js', 'utf8');
        let fetchOptions = null;
        const context = {
          console,
          URL,
          URLSearchParams,
          Headers,
          setTimeout,
          clearTimeout,
          window: {
            location: { href: 'http://example.test/ops' },
            addEventListener: () => {},
            localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
            sessionStorage: { setItem: () => {}, removeItem: () => {} },
          },
          document: {
            baseURI: 'http://example.test/ops',
            addEventListener: () => {},
            getElementById: () => null,
            createElement: () => ({ className: '', classList: { add: () => {}, remove: () => {} } }),
            body: { appendChild: () => {} },
          },
          fetch: async (url, options) => {
            fetchOptions = options || {};
            return {
              ok: true,
              status: 200,
              headers: { get: () => 'application/json' },
              json: async () => ({ status: 'failed', error: 'Build failed: process exited with code 1.' }),
              text: async () => '',
            };
          },
        };
        context.window.window = context.window;
        vm.createContext(context);
        vm.runInContext(source, context);

        (async () => {
          let threw = false;
          try {
            await context.window.api('/api/ops/projects/project-1/play/status');
          } catch (error) {
            threw = /Build failed/.test(String(error && error.message || error));
          }
          if (!threw) throw new Error('Default api() call should still reject 200 payload.error responses.');
          const payload = await context.window.api('/api/ops/projects/project-1/play/status', { allowErrorPayload: true });
          if (payload.status !== 'failed' || !payload.error) throw new Error('Allowed domain error payload was not returned.');
          if (fetchOptions && Object.prototype.hasOwnProperty.call(fetchOptions, 'allowErrorPayload')){
            throw new Error('Internal allowErrorPayload option leaked into fetch options.');
          }
          console.log('ok');
        })().catch((error) => {
          console.error(error && error.stack ? error.stack : error);
          process.exit(1);
        });
        """
    )
    completed = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    assert completed.stdout.strip() == "ok"


def test_play_status_bridge_allows_failed_pipeline_error_payload():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/ops-legacy-agent-bridge.js', 'utf8');
        const calls = [];
        const context = {
          console,
          URLSearchParams,
          window: {},
          JSON,
          api: (path, options) => {
            calls.push({ path, options: options || {} });
            return Promise.resolve({ status: 'failed', error: 'Build failed: process exited with code 1.' });
          },
          projectUrl: (projectId, suffix) => `/api/ops/projects/${projectId}${suffix}`,
          localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
          fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
        };
        context.window.window = context.window;
        vm.createContext(context);
        vm.runInContext(source, context);

        (async () => {
          const payload = await context.window.AgentBridge.play.status('project-1');
          if (payload.status !== 'failed' || !payload.error) throw new Error('Failed Play status payload was not returned.');
          if (!calls.length || calls[0].path !== '/api/ops/projects/project-1/play/status') throw new Error('Play status route was not requested.');
          if (calls[0].options.allowErrorPayload !== true) throw new Error('Play status bridge did not opt into domain error payloads.');
          console.log('ok');
        })().catch((error) => {
          console.error(error && error.stack ? error.stack : error);
          process.exit(1);
        });
        """
    )
    completed = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    assert completed.stdout.strip() == "ok"


def test_play_quick_action_accepts_backend_status_fields():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/ops-legacy-dashboard-quick-actions.js', 'utf8');
        const context = { window: { HermesOpsModules: {} } };
        vm.createContext(context);
        vm.runInContext(source, context);
        const dashboard = context.window.HermesOpsModules.dashboardQuickActions.bindDashboard({
          OPS: { playBusyByProject: {} },
          esc: (value) => String(value ?? ''),
          svg: { play: '' },
          playStatusFor: () => ({
            status: 'ready',
            configured: true,
            valid: true,
            configExists: true,
            ready: true,
            inspectUrl: '/play-project/project-1/app',
            title: 'Ready',
            label: 'Play ready',
          }),
          isPlayRunning: () => false,
          playStatusTitle: (status) => status.title || '',
          playStatusLabel: (status) => status.label || '',
        });
        const html = dashboard.renderProjectPlayQuickAction({ id: 'project-1' });
        if (!html.includes('data-ops-action="open-play"')) throw new Error('Quick action did not switch to Play.');
        if (html.includes('disabled')) throw new Error('Quick action Play button should not be disabled.');
        if (!html.includes('<span>Play</span>')) throw new Error('Quick action did not render Play label.');
        console.log('ok');
        """
    )
    completed = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    assert completed.stdout.strip() == "ok"


def test_play_quick_action_uses_build_capability_not_config_file_existence():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/ops-legacy-dashboard-quick-actions.js', 'utf8');
        const context = { window: { HermesOpsModules: {} } };
        vm.createContext(context);
        vm.runInContext(source, context);
        const dashboard = context.window.HermesOpsModules.dashboardQuickActions.bindDashboard({
          OPS: { playBusyByProject: {} },
          esc: (value) => String(value ?? ''),
          svg: { play: '' },
          playStatusFor: () => ({
            status: 'idle',
            configured: false,
            valid: true,
            configExists: false,
            configAvailable: true,
            buildAvailable: true,
            canBuild: true,
            ready: false,
            inspectUrl: '',
            title: 'Auto-detected package-script build workflow from package.json.',
            label: 'Build ready',
          }),
          isPlayRunning: () => false,
          playStatusTitle: (status) => status.title || '',
          playStatusLabel: (status) => status.label || '',
        });
        const html = dashboard.renderProjectPlayQuickAction({ id: 'project-1' });
        if (!html.includes('data-ops-action="start-play"')) throw new Error('Quick action did not render Build action.');
        if (html.includes('disabled')) throw new Error('Build should not be disabled when buildAvailable=true and configExists=false.');
        if (!html.includes('<span>Build</span>')) throw new Error('Quick action did not render Build label.');
        console.log('ok');
        """
    )
    completed = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    assert completed.stdout.strip() == "ok"

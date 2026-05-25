import io
import json
import subprocess
import textwrap
from pathlib import Path
from urllib.parse import urlparse


class _FakeHandler:
    def __init__(self, body=None):
        raw = json.dumps(body or {}).encode("utf-8")
        self.status = None
        self.sent_headers = []
        self.body = bytearray()
        self.wfile = self
        self.rfile = io.BytesIO(raw)
        self.headers = {"Content-Length": str(len(raw))}

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent_headers.append((name, value))

    def end_headers(self):
        pass

    def write(self, data):
        self.body.extend(data)


def _response_json(handler: _FakeHandler) -> dict:
    return json.loads(bytes(handler.body).decode("utf-8"))


def test_phase11_session_activity_routes_support_groups_and_lineage_assignments(monkeypatch, tmp_path):
    from api import session_activity
    from api.routes import handle_get, handle_post

    state_path = tmp_path / "session-activity.json"
    monkeypatch.setattr(session_activity, "_state_path", lambda: state_path)
    monkeypatch.setattr(
        session_activity.ops_sessions,
        "list_ops_sessions",
        lambda: {
            "sessions": [
                {
                    "session_id": "tip-1",
                    "_lineage_root_id": "root-1",
                    "_lineage_tip_id": "tip-1",
                    "title": "Implement the parity fix",
                    "projectName": "Hermes",
                    "repositoryLabel": "Sajdkick/hermes-webui",
                    "branchLabel": "master",
                    "active_stream_id": "stream-1",
                    "message_count": 3,
                    "updated_at": "2026-05-05T12:00:00Z",
                    "ops_run": {
                        "status": "running",
                        "readableOutput": {
                            "available": False,
                        },
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(
        session_activity,
        "all_sessions",
        lambda: [
            {
                "session_id": "tip-1",
                "_lineage_root_id": "root-1",
                "_lineage_tip_id": "tip-1",
                "parent_session_id": "",
            }
        ],
    )

    create = _FakeHandler({"label": "Needs review"})
    assert handle_post(create, urlparse("http://example.com/api/sessions/activity/groups")) is True
    assert create.status == 201
    group_id = _response_json(create)["group"]["id"]

    assign = _FakeHandler({"sessionId": "tip-1", "groupId": group_id})
    assert handle_post(assign, urlparse("http://example.com/api/sessions/activity/group-assignment")) is True
    assert assign.status == 200

    grouped = _FakeHandler()
    assert handle_get(grouped, urlparse("http://example.com/api/sessions/activity")) is True
    assert grouped.status == 200
    payload = _response_json(grouped)
    assert payload["groupCount"] == 1
    assert payload["sessionCount"] == 1
    assert payload["groups"][0]["label"] == "Needs review"
    assert payload["sessions"][0]["groupId"] == group_id
    assert payload["sessions"][0]["activityStatus"]["key"] == "active"

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["assignments"][0]["sessionId"] == "root-1"

    rename = _FakeHandler({"label": "Release blockers"})
    assert handle_post(
        rename,
        urlparse(f"http://example.com/api/sessions/activity/groups/{group_id}/rename"),
    ) is True
    assert rename.status == 200
    assert _response_json(rename)["group"]["label"] == "Release blockers"

    delete = _FakeHandler()
    assert handle_post(
        delete,
        urlparse(f"http://example.com/api/sessions/activity/groups/{group_id}/delete"),
    ) is True
    assert delete.status == 200

    ungrouped = _FakeHandler()
    assert handle_get(ungrouped, urlparse("http://example.com/api/sessions/activity")) is True
    ungrouped_payload = _response_json(ungrouped)
    assert ungrouped_payload["groupCount"] == 0
    assert ungrouped_payload["sessions"][0]["groupId"] is None


def test_phase11_session_activity_keeps_open_task_sessions_visible_after_run_quiets(monkeypatch, tmp_path):
    from api import session_activity
    from api.routes import handle_get

    state_path = tmp_path / "session-activity.json"
    monkeypatch.setattr(session_activity, "_state_path", lambda: state_path)
    monkeypatch.setattr(
        session_activity.ops_sessions,
        "list_ops_sessions",
        lambda: {
            "sessions": [
                {
                    "session_id": "task-session-1",
                    "_lineage_root_id": "task-session-1",
                    "_lineage_tip_id": "task-session-1",
                    "title": "Hermes: Fix the dashboard parity gap",
                    "projectName": "Hermes",
                    "repositoryLabel": "Sajdkick/hermes-webui",
                    "branchLabel": "master",
                    "active_stream_id": None,
                    "message_count": 12,
                    "updated_at": "2026-05-05T18:00:00Z",
                    "ops_task": {
                        "id": "task-1",
                        "text": "Fix the dashboard parity gap",
                        "done": False,
                    },
                    "ops_run": {
                        "status": "succeeded",
                        "readableOutput": {
                            "available": True,
                            "updatedAt": "2026-05-05T18:01:00Z",
                        },
                    },
                }
            ]
        },
    )

    grouped = _FakeHandler()
    assert handle_get(grouped, urlparse("http://example.com/api/sessions/activity")) is True
    assert grouped.status == 200
    payload = _response_json(grouped)

    assert payload["sessionCount"] == 1
    assert payload["sessions"][0]["id"] == "task-session-1"
    assert payload["sessions"][0]["activityStatus"]["key"] == "done"
    assert payload["sessions"][0]["readableOutputPending"] is True


def test_phase11_home_session_activity_overview_matches_cloud_terminal_shape():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (async () => {
          const source = fs.readFileSync('static/ops-legacy-home.js', 'utf8');
          const windowRef = { HermesOpsModules: {}, setInterval: () => 1 };
          const context = {
            console,
            window: windowRef,
            document: {
              activeElement: null,
            },
            navigator: {},
            URL,
            setTimeout,
            clearTimeout,
            requestAnimationFrame: (cb) => cb(),
          };
          vm.createContext(context);
          vm.runInContext(source, context);

          const dashboard = context.window.HermesOpsModules.home.bindDashboard({
            OPS: {
              loading: false,
              projects: [],
              sessions: [],
              sessionActivity: [
                {
                  id: 'session-1',
                  session_id: 'session-1',
                  label: 'Fix parity',
                  repoLabel: 'Sajdkick/hermes-webui',
                  groupId: 'group-1',
                  readableOutputPending: true,
                  activityStatus: {
                    key: 'approval',
                    toneClass: 'approval',
                    labelText: 'Codex needs approval',
                    title: 'Codex is waiting for approval in this session.',
                  },
                },
                {
                  id: 'session-2',
                  session_id: 'session-2',
                  label: 'Ungrouped task',
                  repoLabel: 'Sajdkick/hermes-webui',
                  activityStatus: {
                    key: 'active',
                    toneClass: 'active',
                    labelText: 'Codex is working',
                    title: 'Codex is actively processing this session.',
                  },
                },
              ],
              sessionActivityGroups: [{ id: 'group-1', label: 'Needs review', position: 0 }],
              sessionActivityCollapsed: {},
              sessionActivityInitialized: {},
              sessionActivityExpanded: true,
              sessionActivityLastRefreshedAt: 0,
              sessionActivityError: '',
              sessionActivityBusy: false,
              sessionActivityFocusGroupId: '',
              quickTaskImages: [],
            },
            AgentBridge: { sessions: {} },
            renderCurrentOpsView: () => {},
            root: () => ({ contains: () => true, querySelectorAll: () => [] }),
            esc: (value) => String(value ?? ''),
            svg: { folder: '', close: '', chat: '', play: '', refresh: '', check: '', arrow: '' },
            showError: () => {},
            setBusy: () => {},
            setDashboardTopbar: () => {},
            renderNotifications: () => '',
            normalizedAutoApprovalPolicy: () => ({ enabled: false }),
            loadProjects: async () => [],
            createQuickTask: async () => null,
            executeReadyTasksWithAi: async () => null,
            loadNotifications: async () => [],
            loadOpsRuns: async () => [],
            loadNotificationDiagnostics: async () => null,
            findProject: () => null,
            projectUsesBranchTitle: () => false,
            projectBranchLabel: () => '',
            projectCardTitle: () => '',
            projectRepositoryLabel: () => '',
            normalizeRunStatus: () => 'running',
            runStatusLabel: () => 'Running',
            runStatusKind: () => 'running',
            formatOpsDateTime: () => 'now',
            renderProjectGitQuickAction: () => '',
            renderProjectPlayQuickAction: () => '',
            renderProjectActivityQuickAction: () => '',
            sessionAccentStyle: () => '',
            sessionGroupAccentStyle: () => '',
            sessionRefValue: (session) => session.session_id || session.id,
            canonicalTaskSessions: (sessions) => sessions,
            projectSessionsFor: () => [],
            isSessionForProject: () => false,
            taskImageLabel: () => '',
            writeStoredJson: () => {},
            sessionActivityStorageKey: 'activity-collapse',
            navigatorRef: {},
            windowRef,
            documentRef: context.document,
            URLRef: URL,
            MediaRecorderRef: function(){},
            FileRef: function(){},
            showPromptDialog: async () => null,
            showConfirmDialog: async () => false,
            requestAnimationFrameRef: (cb) => cb(),
            taskDictationPrompt: '',
            taskDictationAudioBitsPerSecond: 0,
            runActiveStatusValues: ['running'],
          });

          const html = dashboard.renderHomeSessionOverview();
          if (!html.includes('menu-session-activity-list')) throw new Error('Missing Cloud Terminal session activity list.');
          if (html.includes('menu-session-activity-state')) throw new Error('Legacy verbose Active-session Codex status labels should not render in task rows.');
          if (html.includes('Codex needs approval') || html.includes('Codex is working')) throw new Error('Active-session task rows should omit verbose Codex status label text.');
          if (!html.includes('menu-session-activity-status approval') || !html.includes('Session status: Approval')) throw new Error('Missing compact approval status badge.');
          if (!html.includes('menu-session-activity-status active') || !html.includes('Session status: Working')) throw new Error('Missing compact working status badge.');
          if (!html.includes('menu-session-activity-group')) throw new Error('Missing Cloud Terminal session activity groups.');
          if (!html.includes('data-ops-session-group-select="true"')) throw new Error('Missing group assignment select.');
          if (!html.includes('Unread output')) throw new Error('Missing readable-output badge.');
          if (!html.includes('Ungrouped')) throw new Error('Missing ungrouped bucket.');
          if (!html.includes('collapsed')) throw new Error('Groups should default to collapsed like Cloud Terminal.');
          if (html.includes('ops-home-project-list')) throw new Error('Old project-grouped home overview is still being rendered.');

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


def test_phase11_home_active_session_rows_open_from_the_whole_card():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (() => {
          const source = fs.readFileSync('static/ops-legacy-home.js', 'utf8');
          const windowRef = { HermesOpsModules: {}, setInterval: () => 1 };
          const context = {
            console,
            window: windowRef,
            document: { activeElement: null },
            navigator: {},
            URL,
            setTimeout,
            clearTimeout,
          };
          vm.createContext(context);
          vm.runInContext(source, context);

          const project = {
            id: 'project-1',
            name: 'Hermes',
            fullName: 'Sajdkick/hermes-webui',
            coreBranch: 'master',
          };
          const session = {
            session_id: 'session-1',
            sessionKey: 'project-1',
            title: 'Fix the live dashboard',
            updated_at: 1746400800,
            active_stream_id: 'stream-1',
            projectId: 'project-1',
          };
          const secondSession = {
            session_id: 'session-2',
            sessionKey: 'project-1',
            title: 'Review the live dashboard',
            updated_at: 1746400900,
            active_stream_id: 'stream-2',
            projectId: 'project-1',
          };

          const dashboard = context.window.HermesOpsModules.home.bindDashboard({
            OPS: {
              loading: false,
              projects: [project],
              sessions: [session, secondSession],
              sessionActivity: [],
              sessionActivityGroups: [],
              sessionActivityCollapsed: {},
              sessionActivityInitialized: {},
              sessionActivityExpanded: true,
              sessionActivityLastRefreshedAt: 0,
              sessionActivityError: '',
              sessionActivityBusy: false,
              sessionActivityFocusGroupId: '',
              quickTaskImages: [],
            },
            AgentBridge: { sessions: {} },
            renderCurrentOpsView: () => {},
            root: () => ({ contains: () => true, querySelectorAll: () => [] }),
            esc: (value) => String(value ?? ''),
            svg: { folder: '', close: '', chat: '', play: '', refresh: '', check: '', arrow: '' },
            showError: () => {},
            setBusy: () => {},
            setDashboardTopbar: () => {},
            renderNotifications: () => '',
            normalizedAutoApprovalPolicy: () => ({ enabled: false }),
            loadProjects: async () => [],
            createQuickTask: async () => null,
            executeReadyTasksWithAi: async () => null,
            openProjectDetail: async () => null,
            loadNotifications: async () => [],
            loadOpsRuns: async () => [],
            loadNotificationDiagnostics: async () => null,
            openOpsSession: async () => null,
            findProject: (projectId) => projectId === 'project-1' ? project : null,
            projectUsesBranchTitle: () => false,
            projectBranchLabel: () => 'master',
            projectCardTitle: (entry) => entry.fullName || entry.name || entry.id,
            projectRepositoryLabel: (entry) => entry.fullName || entry.name || entry.id,
            normalizeRunStatus: () => 'running',
            runStatusLabel: () => 'Running',
            runStatusKind: () => 'running',
            formatOpsDateTime: () => 'now',
            renderProjectGitQuickAction: () => '',
            renderProjectPlayQuickAction: () => '',
            renderProjectActivityQuickAction: () => '',
            sessionAccentStyle: () => '',
            sessionGroupAccentStyle: () => '',
            sessionRefValue: (entry) => entry.sessionKey || entry.session_id || entry.id,
            canonicalTaskSessions: (sessions) => sessions,
            projectSessionsFor: () => [session, secondSession],
            isSessionForProject: () => true,
            taskImageLabel: () => '',
            writeStoredJson: () => {},
            sessionActivityStorageKey: 'activity-collapse',
            navigatorRef: {},
            windowRef,
            documentRef: context.document,
            URLRef: URL,
            MediaRecorderRef: function(){},
            FileRef: function(){},
            showPromptDialog: async () => null,
            showConfirmDialog: async () => false,
            requestAnimationFrameRef: (cb) => cb(),
            taskDictationPrompt: '',
            taskDictationAudioBitsPerSecond: 0,
            runActiveStatusValues: ['running'],
          });

          const html = dashboard.renderProjectSessionRows(project, [session, secondSession]);
          if (!html.includes('data-ops-session-row="true"')) throw new Error('Missing interactive session-row marker.');
          if (!html.includes('data-ops-action="open-session"')) throw new Error('Missing whole-row open-session action.');
          if (!html.includes('ops-session running interactive')) throw new Error('Missing interactive active-session card class.');
          if (!html.includes('Open session')) throw new Error('Missing explicit open-session button.');
          if (!html.includes('data-session-key="session-1"') || !html.includes('data-session-key="session-2"')) {
            throw new Error('Active session rows must preserve each concrete session id, even when sessions share a project-level key.');
          }
          if (html.includes('data-session-key="project-1"')) throw new Error('Project-level session keys must not replace concrete session ids.');

          console.log('ok');
        })();
        """
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "ok"


def test_phase11_home_menu_shell_matches_cloud_terminal_shape():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (async () => {
          const source = fs.readFileSync('static/ops-legacy-home.js', 'utf8');
          const rootEl = {
            innerHTML: '',
            contains: () => true,
            querySelectorAll: () => [],
            querySelector: () => null,
          };
          const windowRef = {
            HermesOpsModules: {},
            setInterval: () => 1,
            _opsDashboardOpen: true,
            location: { assign: () => {} },
          };
          const context = {
            console,
            window: windowRef,
            document: {
              activeElement: null,
            },
            navigator: {},
            URL,
            setTimeout,
            clearTimeout,
            requestAnimationFrame: (cb) => cb(),
          };
          vm.createContext(context);
          vm.runInContext(source, context);

          let executeReadyProjectId = '';
          const dashboard = context.window.HermesOpsModules.home.bindDashboard({
            OPS: {
              loading: false,
              view: 'home',
              projects: [{ id: 'hermes', name: 'Hermes', coreBranch: 'master' }],
              sessions: [],
              notifications: [],
              notificationBusy: false,
              notificationAutoApprovalPolicy: { enabled: true, rules: [] },
              sessionActivity: [{
                id: 's1',
                projectId: 'hermes',
                label: 'Hermes',
                branchLabel: 'Summons',
                repoLabel: 'Hermes',
                taskText: 'Fix the active sessions view so every session card shows the first part of the task text before the user opens the chat.',
                activityStatus: { key: 'active', toneClass: 'active', labelText: 'Codex is working', title: 'Meaningful terminal output detected recently.' },
                lastOutputAt: 1000,
              }],
              sessionActivityGroups: [],
              sessionActivityCollapsed: {},
              sessionActivityInitialized: {},
              sessionActivityExpanded: true,
              sessionActivityLastRefreshedAt: 0,
              sessionActivityError: '',
              sessionActivityBusy: false,
              sessionActivityFocusGroupId: '',
              quickTaskImages: [],
              quickTaskProjectId: 'hermes',
              quickTaskText: '',
              quickTaskBusy: false,
              quickTaskDictationActive: false,
              quickTaskDictationBusy: false,
              quickTaskStatus: '',
              quickTaskStatusKind: 'info',
            },
            AgentBridge: { sessions: {} },
            renderCurrentOpsView: () => {},
            root: () => rootEl,
            esc: (value) => String(value ?? ''),
            svg: { folder: '', close: '', chat: '', play: '', refresh: '', check: '', arrow: '' },
            showError: () => {},
            setBusy: () => {},
            setDashboardTopbar: () => {},
            renderNotifications: () => '<div class="ops-notification-empty">No notifications.</div>',
            normalizedAutoApprovalPolicy: () => ({ enabled: true }),
            loadProjects: async () => [],
            createQuickTask: async () => null,
            executeReadyTasksWithAi: async (projectId) => { executeReadyProjectId = projectId; },
            loadNotifications: async () => [],
            loadOpsRuns: async () => [],
            loadNotificationDiagnostics: async () => null,
            findProject: () => null,
            projectUsesBranchTitle: () => false,
            projectBranchLabel: () => '',
            projectCardTitle: () => '',
            projectRepositoryLabel: () => '',
            normalizeRunStatus: () => 'running',
            runStatusLabel: () => 'Running',
            runStatusKind: () => 'running',
            formatOpsDateTime: () => 'now',
            renderProjectGitQuickAction: () => '',
            renderProjectPlayQuickAction: () => '',
            renderProjectActivityQuickAction: () => '',
            sessionAccentStyle: () => '',
            sessionGroupAccentStyle: () => '',
            sessionRefValue: (session) => session.session_id || session.id,
            canonicalTaskSessions: (sessions) => sessions,
            projectSessionsFor: () => [],
            isSessionForProject: () => false,
            taskImageLabel: () => '',
            writeStoredJson: () => {},
            sessionActivityStorageKey: 'activity-collapse',
            navigatorRef: {},
            windowRef,
            documentRef: context.document,
            URLRef: URL,
            MediaRecorderRef: function(){},
            FileRef: function(){},
            showPromptDialog: async () => null,
            showConfirmDialog: async () => false,
            requestAnimationFrameRef: (cb) => cb(),
            taskDictationPrompt: '',
            taskDictationAudioBitsPerSecond: 0,
            runActiveStatusValues: ['running'],
            playStatusFor: (projectId) => projectId === 'hermes' ? { configured: true, status: 'building', running: true } : null,
          });

          dashboard.renderHome();
          const html = rootEl.innerHTML;
          if (!html.includes('data-project-play-state="building"')) throw new Error('Missing active-session Play building state marker.');
          if (!html.includes('project-play play-status-badge state-building')) throw new Error('Missing active-session Play building badge.');
          if (!html.includes('<div class="menu-session-activity-title">Summons</div>')) throw new Error('Active-session title should prefer the branch label over the shared repository name.');
          if (!html.includes('<div class="menu-session-activity-repo">Hermes</div>')) throw new Error('Active-session row should keep the repository name as secondary context.');
          if (!html.includes('menu-session-activity-task-preview')) throw new Error('Active-session row should show a task preview.');
          if (!html.includes('<span class="menu-session-activity-task-label">Task</span>')) throw new Error('Active-session task preview should be labeled.');
          if (!html.includes('Fix the active sessions view so every session card shows the first part of the task text')) throw new Error('Active-session task preview should include the task text prefix.');
          if (!html.includes('title="Fix the active sessions view so every session card shows the first part of the task text before the user opens the chat."')) throw new Error('Active-session task preview should keep the full task text in the title.');
          if (!html.includes('menu-page-content')) throw new Error('Missing Cloud Terminal menu-page wrapper.');
          if (!html.includes('<h2>Menu</h2>')) throw new Error('Missing Cloud Terminal menu heading.');
          if (!html.includes('Use the navigation buttons below and review active agent notifications.')) throw new Error('Missing Cloud Terminal menu description.');
          if (!html.includes('menu-inline-toggle')) throw new Error('Missing inline auto-approve toggle.');
          if (!html.includes('Auto-approve routine requests')) throw new Error('Missing Cloud Terminal auto-approve copy.');
          if (!html.includes('menu-quick-task-form')) throw new Error('Missing Cloud Terminal quick task form wrapper.');
          if (!html.includes('task-add-btn')) throw new Error('Missing Cloud Terminal quick task primary button style.');
          if (!html.includes('data-ops-action="create-quick-task"')) throw new Error('Missing create-only quick task action.');
          if (!html.includes('Create & run')) throw new Error('Missing Cloud Terminal quick task submit label.');
          if (!html.includes('data-ops-action="execute-ready-tasks"')) throw new Error('Missing quick task execute-ready action.');
          if (!html.includes('Execute ready tasks with AI')) throw new Error('Missing quick task execute-ready label.');
          if (!html.includes('Run as standing /goal')) throw new Error('Missing Hermes quick-task goal-mode toggle.');
          if (!html.includes('menu-actions')) throw new Error('Missing Cloud Terminal menu action strip.');
          if (!html.includes('data-ops-action="show-create-project"')) throw new Error('Missing create-project menu action.');
          if (!html.includes('data-ops-action="view-deployments"')) throw new Error('Missing deployments menu action.');
          if (!html.includes('data-ops-action="view-todos"')) throw new Error('Missing todos menu action.');
          if (!html.includes('data-ops-action="view-files"')) throw new Error('Missing files menu action.');
          if (!html.includes('data-ops-action="view-settings"')) throw new Error('Missing settings menu action.');
          if (!html.includes('Back to terminal')) throw new Error('Missing back-to-terminal menu action.');
          if (html.includes('Back to Hermes')) throw new Error('Legacy back-to-Hermes action should not remain in the Cloud Terminal parity shell.');
          if (!html.includes('while this menu is visible.')) throw new Error('Missing Cloud Terminal active-session help copy.');
          if (html.includes('ops-home-top')) throw new Error('Legacy Hermes home top bar should not render in the Cloud Terminal parity shell.');

          await dashboard.handleHomeAction('execute-ready-tasks', { dataset: {} });
          if (executeReadyProjectId !== 'hermes') throw new Error('Home execute-ready action did not use the selected quick-task project.');
          if (!rootEl.innerHTML.includes('Ready task execution session started.')) throw new Error('Home execute-ready action did not render a success status.');

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


def test_phase11_home_menu_routes_back_into_main_hermes_app():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (async () => {
          const source = fs.readFileSync('static/ops-legacy-home.js', 'utf8');
          const rootEl = {
            innerHTML: '',
            contains: () => true,
            querySelectorAll: () => [],
            querySelector: () => null,
          };
          const assigned = [];
          const windowRef = {
            HermesOpsModules: {},
            setInterval: () => 1,
            _opsDashboardOpen: true,
            location: {
              href: 'http://example.com/hermes/',
              assign: (value) => assigned.push(value),
            },
          };
          const context = {
            console,
            window: windowRef,
            document: {
              activeElement: null,
              baseURI: 'http://example.com/hermes/',
            },
            navigator: {},
            URL,
            setTimeout,
            clearTimeout,
            requestAnimationFrame: (cb) => cb(),
          };
          vm.createContext(context);
          vm.runInContext(source, context);

          const dashboard = context.window.HermesOpsModules.home.bindDashboard({
            OPS: {
              loading: false,
              view: 'home',
              projects: [{ id: 'hermes', name: 'Hermes', coreBranch: 'master' }],
              sessions: [],
              notifications: [],
              notificationBusy: false,
              notificationAutoApprovalPolicy: { enabled: true, rules: [] },
              sessionActivity: [],
              sessionActivityGroups: [],
              sessionActivityCollapsed: {},
              sessionActivityInitialized: {},
              sessionActivityExpanded: true,
              sessionActivityLastRefreshedAt: 0,
              sessionActivityError: '',
              sessionActivityBusy: false,
              sessionActivityFocusGroupId: '',
              quickTaskImages: [],
              quickTaskProjectId: 'hermes',
              quickTaskText: '',
              quickTaskBusy: false,
              quickTaskDictationActive: false,
              quickTaskDictationBusy: false,
              quickTaskStatus: '',
              quickTaskStatusKind: 'info',
            },
            AgentBridge: { sessions: {} },
            renderCurrentOpsView: () => {},
            root: () => rootEl,
            esc: (value) => String(value ?? ''),
            svg: { folder: '', close: '', chat: '', play: '', refresh: '', check: '', arrow: '' },
            showError: () => {},
            setBusy: () => {},
            setDashboardTopbar: () => {},
            renderNotifications: () => '<div class="ops-notification-empty">No notifications.</div>',
            normalizedAutoApprovalPolicy: () => ({ enabled: true }),
            loadProjects: async () => [],
            createQuickTask: async () => null,
            executeReadyTasksWithAi: async () => null,
            loadNotifications: async () => [],
            loadOpsRuns: async () => [],
            loadNotificationDiagnostics: async () => null,
            findProject: (projectId) => projectId === 'hermes' ? { id: 'hermes', name: 'Hermes', coreBranch: 'master' } : null,
            projectUsesBranchTitle: () => false,
            projectBranchLabel: () => '',
            projectCardTitle: () => '',
            projectRepositoryLabel: () => '',
            normalizeRunStatus: () => 'running',
            runStatusLabel: () => 'Running',
            runStatusKind: () => 'running',
            formatOpsDateTime: () => 'now',
            renderProjectGitQuickAction: () => '',
            renderProjectPlayQuickAction: () => '',
            renderProjectActivityQuickAction: () => '',
            sessionAccentStyle: () => '',
            sessionGroupAccentStyle: () => '',
            sessionRefValue: (session) => session.session_id || session.id,
            canonicalTaskSessions: (sessions) => sessions,
            projectSessionsFor: () => [],
            isSessionForProject: () => false,
            taskImageLabel: () => '',
            writeStoredJson: () => {},
            sessionActivityStorageKey: 'activity-collapse',
            navigatorRef: {},
            windowRef,
            documentRef: context.document,
            URLRef: URL,
            MediaRecorderRef: function(){},
            FileRef: function(){},
            showPromptDialog: async () => null,
            showConfirmDialog: async () => false,
            requestAnimationFrameRef: (cb) => cb(),
            taskDictationPrompt: '',
            taskDictationAudioBitsPerSecond: 0,
            runActiveStatusValues: ['running'],
            playStatusFor: () => null,
          });

          await dashboard.handleHomeAction('view-settings');
          await dashboard.handleHomeAction('view-todos');
          await dashboard.handleHomeAction('back-to-terminal');
          await dashboard.handleHomeAction('go-recovery');
          await dashboard.handleHomeAction('back-to-hermes');

          const expected = [
            'http://example.com/hermes/index.html?panel=settings',
            'http://example.com/hermes/index.html?panel=todos',
            'http://example.com/hermes/index.html',
            'http://example.com/hermes/recovery',
            'http://example.com/hermes/index.html',
          ];
          if (JSON.stringify(assigned) !== JSON.stringify(expected)) {
            throw new Error('Unexpected Hermes navigation targets: ' + JSON.stringify(assigned));
          }
          if (assigned.some((value) => value === '/' || value.startsWith('/?panel='))) {
            throw new Error('Legacy Cloud Terminal navigation still points at the ops root.');
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


def test_phase11_home_menu_routes_back_into_main_hermes_app_from_trailing_ops_route():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        async function runCase(baseHref){
          const source = fs.readFileSync('static/ops-legacy-home.js', 'utf8');
          const rootEl = {
            innerHTML: '',
            contains: () => true,
            querySelectorAll: () => [],
            querySelector: () => null,
          };
          const assigned = [];
          const windowRef = {
            HermesOpsModules: {},
            setInterval: () => 1,
            _opsDashboardOpen: true,
            location: {
              href: baseHref,
              assign: (value) => assigned.push(value),
            },
          };
          const context = {
            console,
            window: windowRef,
            document: {
              activeElement: null,
              baseURI: baseHref,
            },
            navigator: {},
            URL,
            setTimeout,
            clearTimeout,
            requestAnimationFrame: (cb) => cb(),
          };
          vm.createContext(context);
          vm.runInContext(source, context);

          const dashboard = context.window.HermesOpsModules.home.bindDashboard({
            OPS: {
              loading: false,
              view: 'home',
              projects: [{ id: 'hermes', name: 'Hermes', coreBranch: 'master' }],
              sessions: [],
              notifications: [],
              notificationBusy: false,
              notificationAutoApprovalPolicy: { enabled: true, rules: [] },
              sessionActivity: [],
              sessionActivityGroups: [],
              sessionActivityCollapsed: {},
              sessionActivityInitialized: {},
              sessionActivityExpanded: true,
              sessionActivityLastRefreshedAt: 0,
              sessionActivityError: '',
              sessionActivityBusy: false,
              sessionActivityFocusGroupId: '',
              quickTaskImages: [],
              quickTaskProjectId: 'hermes',
              quickTaskText: '',
              quickTaskBusy: false,
              quickTaskDictationActive: false,
              quickTaskDictationBusy: false,
              quickTaskStatus: '',
              quickTaskStatusKind: 'info',
            },
            AgentBridge: { sessions: {} },
            renderCurrentOpsView: () => {},
            root: () => rootEl,
            esc: (value) => String(value ?? ''),
            svg: { folder: '', close: '', chat: '', play: '', refresh: '', check: '', arrow: '' },
            showError: () => {},
            setBusy: () => {},
            setDashboardTopbar: () => {},
            renderNotifications: () => '<div class="ops-notification-empty">No notifications.</div>',
            normalizedAutoApprovalPolicy: () => ({ enabled: true }),
            loadProjects: async () => [],
            createQuickTask: async () => null,
            executeReadyTasksWithAi: async () => null,
            loadNotifications: async () => [],
            loadOpsRuns: async () => [],
            loadNotificationDiagnostics: async () => null,
            findProject: (projectId) => projectId === 'hermes' ? { id: 'hermes', name: 'Hermes', coreBranch: 'master' } : null,
            projectUsesBranchTitle: () => false,
            projectBranchLabel: () => '',
            projectCardTitle: () => '',
            projectRepositoryLabel: () => '',
            normalizeRunStatus: () => 'running',
            runStatusLabel: () => 'Running',
            runStatusKind: () => 'running',
            formatOpsDateTime: () => 'now',
            renderProjectGitQuickAction: () => '',
            renderProjectPlayQuickAction: () => '',
            renderProjectActivityQuickAction: () => '',
            sessionAccentStyle: () => '',
            sessionGroupAccentStyle: () => '',
            sessionRefValue: (session) => session.session_id || session.id,
            canonicalTaskSessions: (sessions) => sessions,
            projectSessionsFor: () => [],
            isSessionForProject: () => false,
            taskImageLabel: () => '',
            writeStoredJson: () => {},
            sessionActivityStorageKey: 'activity-collapse',
            navigatorRef: {},
            windowRef,
            documentRef: context.document,
            URLRef: URL,
            MediaRecorderRef: function(){},
            FileRef: function(){},
            showPromptDialog: async () => null,
            showConfirmDialog: async () => false,
            requestAnimationFrameRef: (cb) => cb(),
            taskDictationPrompt: '',
            taskDictationAudioBitsPerSecond: 0,
            runActiveStatusValues: ['running'],
            playStatusFor: () => null,
          });

          await dashboard.handleHomeAction('view-settings');
          await dashboard.handleHomeAction('view-todos');
          await dashboard.handleHomeAction('back-to-terminal');
          await dashboard.handleHomeAction('go-recovery');
          await dashboard.handleHomeAction('back-to-hermes');
          return assigned;
        }

        (async () => {
          const cases = [
            'http://example.com/hermes/ops/',
            'http://example.com/hermes/ops-phase/',
            'http://example.com/hermes/session/abc123/ops/',
          ];
          const expected = [
            'http://example.com/hermes/index.html?panel=settings',
            'http://example.com/hermes/index.html?panel=todos',
            'http://example.com/hermes/index.html',
            'http://example.com/hermes/recovery',
            'http://example.com/hermes/index.html',
          ];
          for (const baseHref of cases){
            const assigned = await runCase(baseHref);
            if (JSON.stringify(assigned) !== JSON.stringify(expected)) {
              throw new Error('Unexpected Hermes navigation targets for ' + baseHref + ': ' + JSON.stringify(assigned));
            }
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


def test_phase11_quick_task_create_only_does_not_start_execution():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (async () => {
          const source = fs.readFileSync('static/ops-legacy-task-actions.js', 'utf8');
          const windowRef = { HermesOpsModules: {}, _opsDashboardOpen: true };
          const context = { console, window: windowRef, document: {} };
          vm.createContext(context);
          vm.runInContext(source, context);

          const project = { id: 'hermes', name: 'Hermes', path: '/tmp/hermes' };
          const quickEpic = { id: 'quick-epic', title: 'Quick tasks', tasks: [] };
          const createdTask = { id: 'task-1', text: 'Create only', grade: 'green' };
          const calls = [];
          let renderHomeCount = 0;
          let sendTurnCount = 0;
          const OPS = {
            currentProject: null,
            taskData: null,
            taskDataByProject: { hermes: { epics: [quickEpic], tasksFile: 'project_tasks/master.json', branch: 'master' } },
            taskAutomationBusyByProject: {},
            view: 'home',
            quickTaskImages: [],
            quickTaskText: 'Create only',
            quickTaskGoalMode: true,
            quickTaskBusy: false,
            quickTaskBusyAction: '',
            quickTaskDictationActive: false,
            quickTaskDictationBusy: false,
            quickTaskStatus: '',
            quickTaskStatusKind: 'info',
          };

          const dashboard = context.window.HermesOpsModules.taskActions.bindDashboard({
            OPS,
            AgentBridge: { sessions: {}, runs: {} },
            api: async (url, options) => {
              calls.push({ url, method: options && options.method, body: options && options.body });
              if (url === '/projects/hermes/tasks') return { task: createdTask };
              throw new Error('Unexpected API call: ' + url);
            },
            projectUrl: (projectId, suffix) => `/projects/${projectId}${suffix || ''}`,
            projectPath: () => '/tmp/hermes',
            nameOf: () => 'Hermes',
            findProject: (projectId) => projectId === 'hermes' ? project : null,
            findTask: () => null,
            findTaskInData: () => ({ epic: quickEpic, task: createdTask }),
            allTasks: () => [],
            findSession: () => null,
            sessionTaskId: () => '',
            latestSessionForTask: () => null,
            sessionRefValue: () => '',
            normalizeTaskGrade: (value) => value || 'green',
            getTaskQaStatus: () => '',
            getTaskMoreWork: () => '',
            actionableTaskCount: () => 0,
            summarizeTaskFilters: () => ({}),
            renderProjectDetail: () => {},
            loadProjectDetail: async () => OPS.taskDataByProject.hermes,
            refreshOpsSessions: async () => [],
            reloadProjectTasks: async () => OPS.taskDataByProject.hermes,
            loadProjects: async () => [],
            renderProjects: () => {},
            renderHome: () => { renderHomeCount += 1; },
            loadSession: async () => null,
            renderSessionList: () => {},
            closeOpsDashboard: () => {},
            showToast: () => {},
            showPromptDialog: async () => null,
            showConfirmDialog: async () => false,
            setBusy: () => {},
            domLookup: () => null,
            documentRef: context.document,
            clearQuickTaskImages: () => { OPS.quickTaskImages = []; },
            sendTurn: async () => { sendTurnCount += 1; },
          });

          await dashboard.createQuickTask('hermes', 'Create only', { run: false });

          if (calls.length !== 1 || calls[0].url !== '/projects/hermes/tasks') throw new Error('Create-only should only post the quick task.');
          if (sendTurnCount !== 0) throw new Error('Create-only should not start a chat turn.');
          if (OPS.quickTaskText !== '') throw new Error('Create-only should clear the quick task text after creating.');
          if (OPS.quickTaskBusy || OPS.quickTaskBusyAction) throw new Error('Create-only should clear busy state.');
          if (OPS.quickTaskStatus !== 'Quick task created.' || OPS.quickTaskStatusKind !== 'success') throw new Error('Create-only should leave a success status.');
          if (renderHomeCount < 2) throw new Error('Create-only should refresh the home panel while busy and after completion.');

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


def test_phase11_quick_task_screenshots_persist_and_reach_started_session():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (async () => {
          const source = fs.readFileSync('static/ops-legacy-task-actions.js', 'utf8');
          const windowRef = { HermesOpsModules: {}, _opsDashboardOpen: true };
          class FakeFileReader {
            readAsDataURL(file){
              this.result = `data:${file.type || 'image/png'};base64,c2NyZWVuc2hvdA==`;
              if (this.onload) this.onload();
            }
          }
          const context = { console, window: windowRef, document: {}, FileReader: FakeFileReader };
          vm.createContext(context);
          vm.runInContext(source, context);

          const project = { id: 'hermes', name: 'Hermes', path: '/tmp/hermes' };
          const quickEpic = { id: 'quick-epic', title: 'Quick tasks', tasks: [] };
          const createdTask = { id: 'task-1', text: 'Debug screenshot flow', grade: 'green' };
          const savedImagePath = '/tmp/hermes-task-images/hermes/task-1/shot.png';
          const calls = [];
          const msg = { value: '' };
          let sentPrompt = '';
          let addFilesCount = 0;
          const state = { session: { session_id: 'sess-1', profile: 'default' }, activeProfile: 'default', pendingFiles: [] };
          const OPS = {
            currentProject: null,
            taskData: null,
            taskDataByProject: { hermes: { epics: [quickEpic], tasksFile: 'project_tasks/master.json', branch: 'master' } },
            taskAutomationBusyByProject: {},
            view: 'home',
            quickTaskImages: [{ id: 'img-1', file: { name: 'shot.png', type: 'image/png' }, previewUrl: 'blob:shot' }],
            quickTaskText: 'Debug screenshot flow',
            quickTaskGoalMode: false,
            quickTaskBusy: false,
            quickTaskBusyAction: '',
            quickTaskDictationActive: false,
            quickTaskDictationBusy: false,
            quickTaskStatus: '',
            quickTaskStatusKind: 'info',
          };
          const reloadedTask = { ...createdTask, images: savedImagePath };
          const reloadedData = { epics: [{ ...quickEpic, tasks: [reloadedTask] }] };

          const dashboard = context.window.HermesOpsModules.taskActions.bindDashboard({
            OPS,
            AgentBridge: {
              sessions: {
                ensureTask: async () => ({ session: { session_id: 'sess-1', profile: 'default' }, task: reloadedTask }),
              },
              runs: { create: async (payload) => { calls.push({ kind: 'run', payload }); return { id: 'run-1' }; } },
            },
            api: async (url, options) => {
              calls.push({ kind: 'api', url, method: options && options.method, body: options && options.body });
              if (url === '/projects/hermes/tasks') return { task: createdTask };
              if (url === '/projects/hermes/tasks/task-1/images') return { image: { name: 'shot.png', path: savedImagePath, mime: 'image/png', size: 10 }, task: reloadedTask };
              if (url === '/projects/hermes/ensure-workspace') return {};
              throw new Error('Unexpected API call: ' + url);
            },
            projectUrl: (projectId, suffix) => `/projects/${projectId}${suffix || ''}`,
            projectPath: () => '/tmp/hermes',
            nameOf: () => 'Hermes',
            findProject: (projectId) => projectId === 'hermes' ? project : null,
            findTask: () => null,
            findTaskInData: (data, taskId) => {
              for (const epic of data.epics || []){
                for (const task of epic.tasks || []){
                  if (task.id === taskId) return { epic, task };
                }
              }
              return null;
            },
            allTasks: () => [],
            findSession: () => null,
            sessionTaskId: () => '',
            latestSessionForTask: () => null,
            sessionRefValue: (value) => typeof value === 'string' ? value : ((value && value.session_id) || ''),
            normalizeTaskGrade: (value) => value || 'green',
            getTaskQaStatus: () => '',
            getTaskMoreWork: () => '',
            actionableTaskCount: () => 0,
            summarizeTaskFilters: () => ({}),
            renderProjectDetail: () => {},
            loadProjectDetail: async () => reloadedData,
            refreshOpsSessions: async () => [],
            reloadProjectTasks: async () => reloadedData,
            loadProjects: async () => [],
            renderProjects: () => {},
            renderHome: () => {},
            loadSession: async () => state.session,
            renderSessionList: () => {},
            closeOpsDashboard: () => {},
            showToast: () => {},
            showPromptDialog: async () => null,
            showConfirmDialog: async () => false,
            setBusy: () => {},
            domLookup: (id) => id === 'msg' ? msg : null,
            documentRef: context.document,
            windowRef,
            FileReaderRef: FakeFileReader,
            SRef: () => state,
            addFiles: (files) => { addFilesCount += files.length; },
            renderTray: () => {},
            clearSessionReadableOutput: () => {},
            clearPersistedSessionId: () => {},
            sendTurn: async () => { sentPrompt = msg.value; },
            autoResize: () => {},
            clearQuickTaskImages: () => { OPS.quickTaskImages = []; },
            enterOpsSessionInspectMode: () => {},
          });

          await dashboard.createQuickTask('hermes', 'Debug screenshot flow', { run: true });

          const uploadCall = calls.find((call) => call.kind === 'api' && call.url === '/projects/hermes/tasks/task-1/images');
          if (!uploadCall) throw new Error('Expected quick task screenshot upload call.');
          const uploadBody = JSON.parse(uploadCall.body);
          if (uploadBody.filename !== 'shot.png' || !String(uploadBody.content || '').startsWith('data:image/png;base64,')) {
            throw new Error('Screenshot upload did not include the selected image file.');
          }
          if (addFilesCount !== 1) throw new Error('Expected raw screenshot file to remain forwarded to composer upload.');
          if (!sentPrompt.includes('Attached task screenshots/images:') || !sentPrompt.includes(savedImagePath)) {
            throw new Error('Started quick task prompt did not include saved task screenshot path: ' + sentPrompt);
          }
          if (OPS.quickTaskImages.length !== 0) throw new Error('Quick task screenshot UI state should be cleared after handoff.');
          if (OPS.quickTaskStatus !== 'Quick task created and execution started.' || OPS.quickTaskStatusKind !== 'success') {
            throw new Error('Expected successful quick task execution status.');
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


def test_phase11_open_session_loads_target_before_closing_dashboard():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (async () => {
          const source = fs.readFileSync('static/ops-legacy-task-actions.js', 'utf8');
          const windowRef = { HermesOpsModules: {}, _opsDashboardOpen: true };
          const context = { console, window: windowRef, document: {} };
          vm.createContext(context);
          vm.runInContext(source, context);

          const calls = [];
          let loadSessionCalled = false;
          let loadResolve;
          const loadPromise = new Promise((resolve) => { loadResolve = resolve; });
          const OPS = {
            currentProject: null,
            taskData: null,
            taskDataByProject: {},
            sessions: [],
            view: 'home',
          };

          const dashboard = context.window.HermesOpsModules.taskActions.bindDashboard({
            OPS,
            AgentBridge: { sessions: {}, runs: {} },
            api: async () => ({}),
            projectUrl: (projectId, suffix) => `/projects/${projectId}${suffix || ''}`,
            projectPath: () => '/tmp/hermes',
            nameOf: () => 'Hermes',
            findProject: () => null,
            findTask: () => null,
            findTaskInData: () => null,
            allTasks: () => [],
            findSession: () => null,
            sessionTaskId: () => '',
            latestSessionForTask: () => null,
            sessionRefValue: (item) => typeof item === 'string' ? item : (item && item.session_id || item && item.sessionId || ''),
            normalizeTaskGrade: (value) => value || 'green',
            getTaskQaStatus: () => '',
            getTaskMoreWork: () => '',
            actionableTaskCount: () => 0,
            summarizeTaskFilters: () => ({}),
            renderProjectDetail: () => {},
            loadProjectDetail: async () => ({}),
            refreshOpsSessions: async () => [],
            reloadProjectTasks: async () => ({}),
            loadProjects: async () => [],
            renderProjects: () => {},
            renderHome: () => {},
            loadSession: async (sessionId) => {
              if (sessionId !== 'session-1') throw new Error('Wrong session id');
              calls.push(`load:${sessionId}`);
              loadSessionCalled = true;
              await loadPromise;
            },
            renderSessionList: () => { calls.push('render-list'); },
            closeOpsDashboard: () => { calls.push('close-dashboard'); },
            showToast: () => {},
            showPromptDialog: async () => null,
            showConfirmDialog: async () => true,
            setBusy: () => {},
            domLookup: () => null,
            documentRef: context.document,
            clearQuickTaskImages: () => {},
          });

          const pending = dashboard.openOpsSession('session-1');
          await new Promise((resolve) => setTimeout(resolve, 0));
          if (!loadSessionCalled) throw new Error('loadSession was not called.');
          if (JSON.stringify(calls) !== JSON.stringify(['load:session-1'])) {
            throw new Error(`Dashboard closed before target session finished loading: ${JSON.stringify(calls)}`);
          }
          loadResolve();
          await pending;
          const expected = ['load:session-1', 'render-list', 'close-dashboard'];
          if (JSON.stringify(calls) !== JSON.stringify(expected)) {
            throw new Error(`Unexpected open order: ${JSON.stringify(calls)}`);
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


def test_phase11_close_session_optimistically_removes_active_row_before_api_returns():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (async () => {
          const source = fs.readFileSync('static/ops-legacy-task-actions.js', 'utf8');
          const windowRef = { HermesOpsModules: {}, _opsDashboardOpen: true };
          const context = { console, window: windowRef, document: {} };
          vm.createContext(context);
          vm.runInContext(source, context);

          const project = { id: 'hermes', name: 'Hermes', path: '/tmp/hermes' };
          const task = { id: 'task-1', text: 'Close me', inProgress: true, sessionId: 'session-1' };
          const epic = { id: 'epic-1', tasks: [task] };
          const session = { session_id: 'session-1', taskId: 'task-1' };
          let renderHomeCount = 0;
          let closeTaskCheckedOptimisticState = false;
          let closeTaskResolve;
          const closeTaskPromise = new Promise((resolve) => { closeTaskResolve = resolve; });
          const OPS = {
            currentProject: null,
            taskData: null,
            taskDataByProject: { hermes: { epics: [epic] } },
            sessions: [session],
            view: 'home',
          };

          const dashboard = context.window.HermesOpsModules.taskActions.bindDashboard({
            OPS,
            AgentBridge: {
              sessions: {
                closeTask: async (projectId, taskId, payload) => {
                  if (projectId !== 'hermes' || taskId !== 'task-1' || payload.sessionId !== 'session-1'){
                    throw new Error('closeTask payload did not preserve project/task/session ids.');
                  }
                  if (OPS.sessions.length !== 0 || task.inProgress !== false || task.sessionId){
                    throw new Error('Session close did not update the visible state before the API call.');
                  }
                  if (renderHomeCount < 1){
                    throw new Error('Session close did not render the home panel optimistically.');
                  }
                  closeTaskCheckedOptimisticState = true;
                  await closeTaskPromise;
                  return { ok: true };
                },
              },
              runs: {},
            },
            api: async () => ({}),
            projectUrl: (projectId, suffix) => `/projects/${projectId}${suffix || ''}`,
            projectPath: () => '/tmp/hermes',
            nameOf: () => 'Hermes',
            findProject: (projectId) => projectId === 'hermes' ? project : null,
            findTask: () => ({ epic, task }),
            findTaskInData: () => ({ epic, task }),
            allTasks: () => [{ epic, task }],
            findSession: (sid) => sid === 'session-1' ? session : null,
            sessionTaskId: (item) => item && item.taskId || '',
            latestSessionForTask: () => session,
            sessionRefValue: (item) => typeof item === 'string' ? item : (item && item.session_id || item && item.sessionId || ''),
            normalizeTaskGrade: (value) => value || 'green',
            getTaskQaStatus: () => '',
            getTaskMoreWork: () => '',
            actionableTaskCount: () => 0,
            summarizeTaskFilters: () => ({}),
            renderProjectDetail: () => {},
            loadProjectDetail: async () => OPS.taskDataByProject.hermes,
            refreshOpsSessions: async () => OPS.sessions,
            reloadProjectTasks: async () => OPS.taskDataByProject.hermes,
            loadProjects: async () => [],
            renderProjects: () => {},
            renderHome: () => { renderHomeCount += 1; },
            loadSession: async () => null,
            renderSessionList: () => {},
            closeOpsDashboard: () => {},
            showToast: () => {},
            showPromptDialog: async () => null,
            showConfirmDialog: async () => true,
            setBusy: () => {},
            domLookup: () => null,
            documentRef: context.document,
            clearQuickTaskImages: () => {},
          });

          const pending = dashboard.setOpsSessionClosed('session-1', true, 'hermes');
          await new Promise((resolve) => setTimeout(resolve, 0));
          if (!closeTaskCheckedOptimisticState) throw new Error('closeTask was not called.');
          closeTaskResolve();
          await pending;
          if (OPS.sessions.length !== 0) throw new Error('Closed session was restored unexpectedly.');
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


def test_phase11_notifications_match_cloud_terminal_card_shape():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (() => {
          const source = fs.readFileSync('static/ops-legacy-notifications.js', 'utf8');
          const windowRef = { HermesOpsModules: {} };
          const context = {
            console,
            window: windowRef,
            document: {},
            navigator: {},
            URL,
            setTimeout,
            clearTimeout,
          };
          vm.createContext(context);
          vm.runInContext(source, context);

          const dashboard = context.window.HermesOpsModules.notifications.bindDashboard({
            OPS: {
              notifications: [
                {
                  id: 'note-1',
                  kind: 'input',
                  input_kind: 'approval',
                  message: 'Review the pending approval request.',
                  created_at: 1746400800,
                  session_title: 'Fix parity',
                  project_name: 'Hermes',
                  payload: { command: 'git push origin master' },
                },
                {
                  id: 'note-2',
                  kind: 'done',
                  message: 'The task is ready for review.',
                  created_at: 1746400900,
                  session_title: 'Fix parity',
                  project_name: 'Hermes',
                },
              ],
              runs: [],
              sessions: [],
              projects: [],
            },
            AgentBridge: { notifications: {}, runs: {}, sessions: {} },
            renderCurrentOpsView: () => {},
            showToast: () => {},
            esc: (value) => String(value ?? ''),
            svg: {},
            openProjectDetail: async () => null,
            openOpsSession: async () => null,
            openRunTarget: async () => null,
            loadRunDetail: async () => null,
            loadOpsRuns: async () => [],
            windowRef,
            documentRef: context.document,
            NotificationRef: function Notification(){},
            navigatorRef: context.navigator,
          });

          const html = dashboard.renderNotifications();
          if (!html.includes('menu-notification-list')) throw new Error('Missing Cloud Terminal notification list.');
          if (!html.includes('menu-notification-item--input-request')) throw new Error('Missing Cloud Terminal input notification card.');
          if (!html.includes('menu-notification-open-btn--input-request')) throw new Error('Missing Cloud Terminal input notification surface.');
          if (!html.includes('menu-notification-response-panel')) throw new Error('Missing Cloud Terminal notification response panel.');
          if (!html.includes('menu-notification-response-option')) throw new Error('Missing Cloud Terminal notification response options.');
          if (!html.includes('menu-notification-item--agent-done')) throw new Error('Missing Cloud Terminal done notification card.');
          if (!html.includes('menu-notification-dismiss-btn')) throw new Error('Missing Cloud Terminal dismiss action.');
          if (html.includes('ops-notification-title-row')) throw new Error('Legacy Hermes notification title row should not render.');
          if (html.includes('ops-notification-list')) throw new Error('Legacy Hermes notification list should not render.');

          console.log('ok');
        })();
        """
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "ok"


def test_phase11_quick_task_project_picker_defers_home_rerender_during_activity_refresh():
    script = textwrap.dedent(
        """
        (async () => {
          const fs = require('fs');
          const vm = require('vm');

          const source = fs.readFileSync('static/ops-legacy-home.js', 'utf8');
          let intervalCallback = null;

          class Root {
            constructor(){
              this._html = '';
              this.renderCount = 0;
              this.projectField = null;
            }
            set innerHTML(value){
              this._html = value;
              this.renderCount += 1;
            }
            get innerHTML(){
              return this._html;
            }
            addEventListener(){}
            querySelector(selector){
              if (selector === '[data-ops-quick-field="projectId"]') return this.projectField;
              return null;
            }
            contains(node){
              return node === this.projectField;
            }
          }

          const rootEl = new Root();
          const quickProjectField = {
            dataset: { opsQuickField: 'projectId' },
            disabled: false,
            value: 'hermes',
            focus: () => {},
            closest: (selector) => selector === '[data-ops-quick-field]' ? quickProjectField : null,
          };
          rootEl.projectField = quickProjectField;

          const documentRef = {
            activeElement: quickProjectField,
          };
          const windowRef = {
            HermesOpsModules: {},
            _opsDashboardOpen: true,
            setInterval: (callback) => {
              intervalCallback = callback;
              return 1;
            },
          };

          const context = {
            console,
            window: windowRef,
            document: documentRef,
            navigator: {},
            URL,
            setTimeout,
            clearTimeout,
          };
          vm.createContext(context);
          vm.runInContext(source, context);

          let activityCalls = 0;
          const OPS = {
            loading: false,
            view: 'home',
            projects: [{ id: 'hermes', name: 'Hermes', coreBranch: 'master' }],
            sessions: [],
            notifications: [],
            notificationBusy: false,
            notificationAutoApprovalPolicy: { enabled: true, rules: [] },
            sessionActivity: [],
            sessionActivityGroups: [],
            sessionActivityCollapsed: {},
            sessionActivityInitialized: {},
            sessionActivityExpanded: true,
            sessionActivityLastRefreshedAt: 0,
            sessionActivityError: '',
            sessionActivityBusy: false,
            sessionActivityFocusGroupId: '',
            quickTaskImages: [],
            quickTaskProjectId: 'hermes',
            quickTaskText: '',
            quickTaskBusy: false,
            quickTaskDictationActive: false,
            quickTaskDictationBusy: false,
            quickTaskStatus: '',
            quickTaskStatusKind: 'info',
          };

          const dashboard = context.window.HermesOpsModules.home.bindDashboard({
            OPS,
            AgentBridge: {
              sessions: {
                activity: async () => {
                  activityCalls += 1;
                  return { sessions: [{ session_id: 'sess-1', title: 'Test session' }], groups: [] };
                },
              },
            },
            renderCurrentOpsView: () => {},
            root: () => rootEl,
            esc: (value) => String(value ?? ''),
            svg: { folder: '', close: '', chat: '', play: '', refresh: '', check: '', arrow: '' },
            showError: () => {},
            setBusy: () => {},
            setDashboardTopbar: () => {},
            renderNotifications: () => '<div class="ops-notification-empty">No notifications.</div>',
            normalizedAutoApprovalPolicy: () => ({ enabled: true }),
            loadProjects: async () => [],
            createQuickTask: async () => null,
            executeReadyTasksWithAi: async () => null,
            openProjectDetail: async () => null,
            loadNotifications: async () => [],
            loadOpsRuns: async () => [],
            loadNotificationDiagnostics: async () => null,
            openOpsSession: async () => null,
            findProject: () => null,
            projectUsesBranchTitle: () => false,
            projectBranchLabel: () => '',
            projectCardTitle: () => '',
            projectRepositoryLabel: () => '',
            normalizeRunStatus: () => 'running',
            runStatusLabel: () => 'Running',
            runStatusKind: () => 'running',
            formatOpsDateTime: () => 'now',
            renderProjectGitQuickAction: () => '',
            renderProjectPlayQuickAction: () => '',
            renderProjectActivityQuickAction: () => '',
            sessionAccentStyle: () => '',
            sessionGroupAccentStyle: () => '',
            sessionRefValue: (session) => session.session_id || session.id,
            canonicalTaskSessions: (sessions) => sessions,
            projectSessionsFor: () => [],
            isSessionForProject: () => false,
            taskImageLabel: () => '',
            writeStoredJson: () => {},
            sessionActivityStorageKey: 'activity-collapse',
            navigatorRef: {},
            windowRef,
            documentRef,
            URLRef: URL,
            MediaRecorderRef: function(){},
            FileRef: function(){},
            showPromptDialog: async () => null,
            showConfirmDialog: async () => false,
            requestAnimationFrameRef: (cb) => cb(),
            taskDictationPrompt: '',
            taskDictationAudioBitsPerSecond: 0,
            runActiveStatusValues: ['running'],
          });

          dashboard.renderHome();
          const initialRenderCount = rootEl.renderCount;
          if (typeof intervalCallback !== 'function'){
            throw new Error('Home auto-refresh timer was not registered');
          }

          intervalCallback();
          await new Promise((resolve) => setTimeout(resolve, 0));
          await new Promise((resolve) => setTimeout(resolve, 0));

          if (activityCalls !== 1){
            throw new Error('Session activity refresh did not run');
          }
          if (rootEl.renderCount !== initialRenderCount){
            throw new Error('Home should not rerender while the quick-task project picker is focused');
          }
          if (OPS.sessionActivityRenderPending !== true){
            throw new Error('Deferred session activity render flag was not set');
          }

          dashboard.handleQuickTaskField({
            type: 'change',
            target: {
              value: 'hermes',
              checked: false,
              files: null,
              dataset: { opsQuickField: 'projectId' },
              closest: (selector) => selector === '[data-ops-quick-field]' ? quickProjectField : null,
            },
          });

          if (rootEl.renderCount <= initialRenderCount){
            throw new Error('Changing the quick-task project should flush the deferred home render');
          }
          if (OPS.sessionActivityRenderPending){
            throw new Error('Deferred session activity render flag should clear after the picker change');
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


def test_phase11_archive_completed_keeps_current_task_view():
    script = textwrap.dedent(
        """
        (async () => {
          const fs = require('fs');
          const vm = require('vm');

          const source = fs.readFileSync('static/ops-legacy-dashboard-actions.js', 'utf8');
          const windowRef = { HermesOpsModules: {} };
          const rootEl = {
            contains: () => true,
          };
          const context = {
            console,
            window: windowRef,
            document: {},
            FormData,
          };
          vm.createContext(context);
          vm.runInContext(source, context);

          const apiCalls = [];
          let setTaskFilterStatusCalls = 0;
          let refreshDetailCalls = 0;
          const dashboard = context.window.HermesOpsModules.dashboardActions.bindDashboard({
            OPS: {
              currentProject: { id: 'project-1' },
            },
            root: () => rootEl,
            showError: (error) => { throw error; },
            setBusy: () => {},
            handleHomeAction: async () => false,
            AgentBridge: { sessions: {}, runs: {} },
            api: async (path, options) => {
              apiCalls.push({ path, options: options || null });
              return { ok: true };
            },
            projectUrl: (projectId, suffix='') => '/api/ops/projects/' + projectId + suffix,
            showConfirmDialog: async () => true,
            splitList: () => [],
            splitImageRefs: () => [],
            refreshDetail: async () => { refreshDetailCalls += 1; },
            setTaskFilterStatus: () => { setTaskFilterStatusCalls += 1; },
          });

          await dashboard.handleClick({
            target: {
              closest: () => ({
                dataset: { opsAction: 'archive-completed' },
              }),
            },
          });

          if (!apiCalls.length || apiCalls[0].path !== '/api/ops/projects/project-1/tasks/archive-completed'){
            throw new Error('Archive-completed endpoint was not called');
          }
          if (setTaskFilterStatusCalls !== 0){
            throw new Error('Archiving completed tasks should not force the archived task filter');
          }
          if (refreshDetailCalls !== 1){
            throw new Error('Project detail should refresh after archiving completed tasks');
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


def test_phase11_project_runs_match_cloud_terminal_card_shape():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (() => {
          const source = fs.readFileSync('static/ops-legacy-runs.js', 'utf8');
          const windowRef = { HermesOpsModules: {} };
          const context = {
            console,
            window: windowRef,
            document: {},
            setTimeout,
            clearTimeout,
          };
          vm.createContext(context);
          vm.runInContext(source, context);

          const run = {
            id: 'run-1',
            project_id: 'project-1',
            task_id: 'task-1',
            title: 'Inspect run activity',
            status: 'waiting-approval',
            summary: 'Awaiting review from the dashboard.',
            updated_at: 1746400800,
            session_id: 'session-run-1',
          };
          const taskData = {
            epics: [{ tasks: [{ id: 'task-1', text: 'Inspect run activity' }] }],
          };

          const dashboard = context.window.HermesOpsModules.runs.bindDashboard({
            OPS: {
              loading: false,
              runs: [run],
              runsByProject: { 'project-1': [run] },
              selectedRunId: 'run-1',
              runDetail: run,
              runRequests: [{
                id: 'request-1',
                kind: 'approval',
                status: 'pending',
                message: 'Approve the next command.',
                metadata: { command: 'git push origin master' },
                updated_at: 1746400800,
              }],
              runReadableOutput: { exists: false },
              runArtifacts: [],
              runLogs: [],
              runEvents: [],
              notifications: [],
              currentProject: { id: 'project-1' },
              taskDataByProject: { 'project-1': taskData },
            },
            AgentBridge: { runs: {} },
            renderCurrentOpsView: () => {},
            showToast: () => {},
            esc: (value) => String(value ?? ''),
            svg: { plus: '', folder: '' },
            findProject: (projectId) => projectId === 'project-1'
              ? { id: 'project-1', fullName: 'Sajdkick/hermes-webui', name: 'Hermes' }
              : null,
            formatProjectLabel: (project) => project.fullName || project.name || project.id,
            findTaskInData: (data, taskId) => {
              const task = (data && data.epics && data.epics[0] && data.epics[0].tasks || []).find((entry) => entry.id === taskId);
              return task ? { task } : null;
            },
            renderNotification: () => '<article class="menu-notification-item menu-notification-item--input-request"></article>',
            pendingNotificationsForRun: () => [{ id: 'note-1' }],
            openSessionTargetOrProject: async () => true,
            renderMd: (markdown) => markdown,
          });

          const activityHtml = dashboard.renderProjectRunActivity({ id: 'project-1' });
          if (!activityHtml.includes('tasks-card ops-run-panel')) throw new Error('Missing Cloud Terminal-aligned run panel shell.');
          if (!activityHtml.includes('menu-session-activity-list')) throw new Error('Missing Cloud Terminal run list.');
          if (!activityHtml.includes('menu-session-activity-item')) throw new Error('Missing Cloud Terminal run cards.');
          if (!activityHtml.includes('menu-session-activity-state state-approval')) throw new Error('Missing Cloud Terminal run status state badge.');
          if (!activityHtml.includes('menu-action-btn small')) throw new Error('Missing Cloud Terminal run primary action.');
          if (activityHtml.includes('ops-btn primary')) throw new Error('Legacy Hermes run button shell should not render.');

          const detailHtml = dashboard.renderRunDetailPanel({ hideProject: true });
          if (!detailHtml.includes('tasks-card ops-run-detail')) throw new Error('Missing Cloud Terminal-aligned run detail shell.');
          if (!detailHtml.includes('menu-notification-list')) throw new Error('Missing Cloud Terminal notification list inside run detail.');
          if (!detailHtml.includes('menu-notification-response-panel')) throw new Error('Missing Cloud Terminal response panel inside run detail.');
          if (detailHtml.includes('ops-icon-btn')) throw new Error('Legacy Hermes icon-only close button should not render in run detail.');

          console.log('ok');
        })();
        """
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "ok"


def test_phase11_project_side_panels_match_cloud_terminal_card_shape():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (() => {
          const windowRef = {
            HermesOpsModules: {},
            location: { assign: () => {} },
            setTimeout,
            clearTimeout,
          };
          const context = {
            console,
            window: windowRef,
            URL,
            setTimeout,
            clearTimeout,
          };
          vm.createContext(context);
          [
            'static/ops-legacy-deployments.js',
            'static/ops-legacy-database.js',
            'static/ops-legacy-health.js',
            'static/ops-legacy-play.js',
          ].forEach((path) => vm.runInContext(fs.readFileSync(path, 'utf8'), context));

          const project = {
            id: 'project-1',
            name: 'Hermes',
            active: true,
            profile: 'default',
            opsCapabilities: {
              deployment: true,
              dependencyHealth: true,
              dependencyInstall: true,
              inodeScan: true,
              inodeCleanup: true,
              projectActivity: true,
              projectSettings: true,
            },
          };
          const OPS = {
            projects: [project],
            currentProject: project,
            notifications: [],
            deploymentsByProject: {
              'project-1': {
                deployment: {
                  status: 'ready',
                  summary: 'Deployment is healthy.',
                  provider: 'manual',
                  environment: 'production',
                  url: 'https://example.com/deploy',
                },
                artifacts: [{ relativePath: 'Dockerfile', kind: 'dockerfile' }],
                logs: [{ message: 'Deploy completed.' }],
              },
            },
            deploymentBusyByProject: {},
            databaseSettings: {
              configured: true,
              settings: { kind: 'sqlite', label: 'Main DB', path: '/tmp/main.db' },
            },
            databaseTables: [{ name: 'users', columns: [{}, {}] }],
            databaseBusy: false,
            databaseError: '',
            projectDatabaseByProject: {
              'project-1': {
                settings: {
                  configured: true,
                  inherited: true,
                  settings: { kind: 'postgres', label: 'Project DB', path: 'postgres://db' },
                },
                tables: [{ name: 'tasks', columns: [{}] }],
              },
            },
            projectDatabaseBusyByProject: {},
            migrationHealth: {
              status: 'ready',
              summary: 'Ready to retire the old Cloud Terminal shell.',
              checks: [{ id: 'check-1', title: 'Paths', status: 'ready', summary: 'No legacy paths remain.' }],
              counts: { projects: 1, tasks: 2, activeRuns: 0 },
            },
            migrationHealthBusy: false,
            artifactHealth: {
              issueCount: 0,
              artifactCount: 4,
              fileReferenceCount: 2,
              urlReferenceCount: 2,
              missingFileCount: 0,
              orphanArtifactCount: 0,
              issues: [],
            },
            artifactHealthBusy: false,
            projectHealthByProject: {
              'project-1': {
                dependencies: {
                  manager: 'pnpm',
                  status: 'ready',
                  installCommandText: 'pnpm install',
                  supported: true,
                },
                inodeScan: {
                  totalInodes: 24,
                  totalBytes: 4096,
                  directories: [{ path: 'node_modules' }],
                },
                cleanup: {
                  status: 'finished',
                  removed: [],
                },
              },
            },
            projectHealthBusyByProject: {},
            gatherReportsByProject: {
              'project-1': [{
                status: 'succeeded',
                title: 'Runtime gather report',
                updatedAt: '2026-05-05T12:00:00Z',
                eventsCount: 2,
                runId: 'run-1',
                reportPath: '/tmp/report.json',
                summary: 'Gather completed.',
              }],
            },
            gatherBusyByProject: {},
            reviewRequestsByProject: {
              'project-1': [{
                status: 'requested',
                title: 'Runtime review',
                updatedAt: '2026-05-05T12:00:00Z',
                eventsCount: 1,
                runId: 'run-2',
                kind: 'visual',
                reviewPath: '/tmp/review.json',
                summary: 'Waiting for review.',
              }],
            },
            reviewBusyByProject: {},
            playStatusByProject: {
              'project-1': {
                status: 'ready',
                kind: 'ready',
                label: 'Play ready',
                title: 'Play is ready.',
                summary: 'Inspect overlay is available.',
                configured: true,
                valid: true,
                configExists: true,
                inspectUrl: 'https://example.com/inspect',
                ready: true,
                running: false,
                logsAvailable: true,
              },
            },
            playBusyByProject: {},
            playLogsByProject: {
              'project-1': { text: 'first line\\nsecond line' },
            },
            playSnapshotsByProject: {
              'project-1': {
                bodyPath: '/tmp/snapshot.json',
                statusCode: 200,
                contentType: 'application/json',
                size: 42,
              },
            },
            playScreenshotsByProject: {
              'project-1': {
                screenshotPath: '/tmp/screenshot.png',
                selector: 'main',
                size: 84,
                createdAt: '2026-05-05T12:00:00Z',
              },
            },
          };

          const shared = {
            OPS,
            api: async () => ({}),
            projectUrl: (projectId, path) => `/api/ops/projects/${projectId}${path}`,
            renderCurrentOpsView: () => {},
            showToast: () => {},
            showPromptDialog: async () => '',
            showConfirmDialog: async () => true,
            esc: (value) => String(value ?? ''),
            svg: {
              refresh: '',
              plus: '',
              check: '',
              play: '',
              folder: '',
              edit: '',
              close: '',
              grid: '',
              trash: '',
            },
            nameOf: (entry) => entry.name || entry.id,
            findProject: (projectId) => projectId === project.id ? project : null,
            openProjects: () => {},
            renderProjectProfileOptions: () => '<option value="default">Default</option>',
            mergeProjectUpdate: () => {},
            AgentBridge: {
              runtime: {
                gatherReports: async () => ({ reports: OPS.gatherReportsByProject['project-1'] }),
                reviewRequests: async () => ({ reviews: OPS.reviewRequestsByProject['project-1'] }),
                screenshot: async () => ({ screenshot: OPS.playScreenshotsByProject['project-1'] }),
              },
              play: {
                status: async () => OPS.playStatusByProject['project-1'],
                logs: async () => OPS.playLogsByProject['project-1'],
                notificationTarget: async () => ({}),
              },
            },
            loadNotifications: async () => {},
            playInspectOverlayUrl: ({ inspectUrl }) => inspectUrl || '',
            openProjectDetail: async () => {},
            windowRef: { location: { assign: () => {} } },
          };

          const deployments = context.window.HermesOpsModules.deployments.bindDashboard(shared);
          const database = context.window.HermesOpsModules.database.bindDashboard(shared);
          const health = context.window.HermesOpsModules.health.bindDashboard(shared);
          const play = context.window.HermesOpsModules.play.bindDashboard(shared);

          const panels = [
            ['deployment', deployments.renderProjectDeployment(project), ['tasks-card ops-deployment-panel', 'menu-action-btn small'], [/class="ops-btn/, /class="ops-panel/]],
            ['database', database.renderDatabasePanel(), ['tasks-card ops-database-panel', 'menu-action-btn small'], [/class="ops-btn/, /class="ops-panel/]],
            ['project database', database.renderProjectDatabase(project), ['tasks-card ops-project-database-panel'], [/class="ops-btn/, /class="ops-panel/]],
            ['migration health', health.renderMigrationHealthPanel(), ['tasks-card ops-migration-health-panel'], [/class="ops-btn/, /class="ops-panel/]],
            ['artifact health', health.renderArtifactHealthPanel(), ['tasks-card ops-artifact-health-panel'], [/class="ops-btn/, /class="ops-panel/]],
            ['project health', health.renderProjectHealth(project), ['tasks-card ops-project-health-panel', 'menu-action-btn danger small'], [/class="ops-btn/, /class="ops-panel/]],
            ['project settings', health.renderProjectSettings(project), ['tasks-card ops-project-settings-panel', 'menu-action-btn small'], [/class="ops-btn/, /class="ops-panel/]],
            ['gather reports', health.renderProjectGatherReports(project), ['tasks-card ops-gather-panel', 'menu-action-btn secondary small'], [/class="ops-btn/, /class="ops-panel/]],
            ['review requests', health.renderProjectReviewRequests(project), ['tasks-card ops-gather-panel', 'menu-action-btn secondary small'], [/class="ops-btn/, /class="ops-panel/]],
            ['play detail controls', play.renderProjectPlayControls(project, { detail: true }), ['menu-action-btn small', 'menu-action-btn secondary small'], [/class="ops-btn/]],
            ['play logs', play.renderProjectPlayLogs(project.id), ['tasks-card ops-play-log-panel'], [/class="ops-btn/, /class="ops-panel/]],
            ['play snapshot', play.renderProjectRuntimeSnapshot(project.id), ['tasks-card ops-play-snapshot-panel'], [/class="ops-btn/, /class="ops-panel/]],
            ['play screenshot', play.renderProjectRuntimeScreenshot(project.id), ['tasks-card ops-play-snapshot-panel'], [/class="ops-btn/, /class="ops-panel/]],
          ];

          panels.forEach(([label, html, includes, excludes]) => {
            includes.forEach((needle) => {
              if (!html.includes(needle)) throw new Error(`Missing ${needle} in ${label}.`);
            });
            excludes.forEach((pattern) => {
              if (pattern.test(html)) throw new Error(`Legacy shell pattern ${pattern} should not render in ${label}.`);
            });
          });

          const playControls = play.renderProjectPlayControls(project, { detail: true });
          if (!playControls.includes('data-ops-action="open-play"')){
            throw new Error('Backend-shaped ready Play status did not render the Play open action.');
          }
          if (/data-ops-action="open-play"[^>]*disabled/.test(playControls)){
            throw new Error('Backend-shaped ready Play status rendered a disabled Play open action.');
          }

          OPS.playStatusByProject['project-1'] = {
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
          };
          const buildCapControls = play.renderProjectPlayControls(project, { detail: true });
          if (!buildCapControls.includes('data-ops-action="start-play"')){
            throw new Error('Build capability without a config file did not render Build action.');
          }
          if (/data-ops-action="start-play"[^>]*disabled/.test(buildCapControls)){
            throw new Error('Build capability without a config file rendered a disabled Build action.');
          }

          OPS.playStatusByProject['project-1'] = {
            status: 'idle',
            configured: false,
            valid: false,
            configExists: false,
            ready: false,
            inspectUrl: '',
          };
          OPS.notifications = [{
            id: 'play-project-1-ready',
            kind: 'play',
            project_id: 'project-1',
            inspectUrl: '/play-project/project-1/app',
            playStatus: 'ready',
            message: 'Play app is ready for inspection.',
          }];
          const notificationBackedControls = play.renderProjectPlayControls(project, { detail: true });
          if (!notificationBackedControls.includes('data-ops-action="open-play"')){
            throw new Error('Ready Play notification did not enable the Play open action.');
          }
          if (/data-ops-action="open-play"[^>]*disabled/.test(notificationBackedControls)){
            throw new Error('Ready Play notification rendered a disabled Play open action.');
          }

          console.log('ok');
        })();
        """
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "ok"



def test_phase11_ops_active_session_click_loads_target_before_closing_dashboard():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (async () => {
          const source = fs.readFileSync('static/ops-legacy-task-actions.js', 'utf8');
          const windowRef = { HermesOpsModules: {} };
          const context = {
            console,
            window: windowRef,
            document: { querySelector: () => null, querySelectorAll: () => [] },
            FileReader: function(){},
            setTimeout,
            clearTimeout,
          };
          vm.createContext(context);
          vm.runInContext(source, context);

          const calls = [];
          const dashboard = context.window.HermesOpsModules.taskActions.bindDashboard({
            OPS: { currentProject: null, taskData: null, taskDataByProject: {}, sessions: [] },
            AgentBridge: {
              sessions: {
                rename: async () => null,
                delete: async () => null,
                archive: async () => null,
                setClosed: async () => null,
                start: async () => ({ session: 'created-session' }),
              },
              runs: {
                create: async () => ({}),
                setStatus: async () => ({}),
                complete: async () => ({}),
                addArtifact: async () => ({}),
              },
            },
            api: async () => ({}),
            projectUrl: (projectId, path) => `/api/ops/projects/${projectId}${path}`,
            projectPath: () => '',
            nameOf: () => 'Project',
            findProject: () => null,
            findTask: () => null,
            findTaskInData: () => null,
            allTasks: () => [],
            findSession: () => null,
            sessionTaskId: () => '',
            latestSessionForTask: () => null,
            sessionRefValue: (entry) => typeof entry === 'string' ? entry : (entry && (entry.session_id || entry.id)) || '',
            normalizeTaskGrade: () => 'green',
            getTaskQaStatus: () => '',
            getTaskMoreWork: () => '',
            actionableTaskCount: () => 0,
            summarizeTaskFilters: () => '',
            renderProjectDetail: () => {},
            loadProjectDetail: async () => ({}),
            refreshOpsSessions: async () => [],
            reloadProjectTasks: async () => ({}),
            loadProjects: async () => [],
            renderProjects: () => {},
            renderHome: () => {},
            loadSession: async (sid) => { calls.push(`load:${sid}`); },
            renderSessionList: async () => { calls.push('render-list'); },
            closeOpsDashboard: () => { calls.push('close-dashboard'); },
            showToast: () => {},
            showPromptDialog: async () => null,
            showConfirmDialog: async () => false,
            setBusy: () => {},
            domLookup: () => ({ value: '', files: [] }),
            documentRef: context.document,
            windowRef,
            FileReaderRef: function(){},
            SRef: () => ({ session: { session_id: 'current-session' }, messages: [], entries: [] }),
            addFiles: () => {},
            renderTray: () => {},
            clearSessionReadableOutput: () => {},
            clearPersistedSessionId: () => {},
            sendTurn: async () => {},
            autoResize: () => {},
            clearQuickTaskImages: () => {},
          });

          await dashboard.openOpsSession('target-session');
          const expected = ['load:target-session', 'render-list', 'close-dashboard'];
          if (JSON.stringify(calls) !== JSON.stringify(expected)) {
            throw new Error(`Unexpected open order: ${JSON.stringify(calls)}`);
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


def test_phase11_open_ops_session_enters_simplified_inspect_mode_after_dashboard_close():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (async () => {
          const source = fs.readFileSync('static/ops-legacy-task-actions.js', 'utf8');
          const windowRef = { HermesOpsModules: {}, _opsDashboardOpen: true };
          const context = { console, window: windowRef, document: {} };
          vm.createContext(context);
          vm.runInContext(source, context);

          const calls = [];
          const dashboard = context.window.HermesOpsModules.taskActions.bindDashboard({
            OPS: { sessions: [] },
            AgentBridge: { sessions: {}, runs: {} },
            api: async () => ({}),
            projectUrl: () => '',
            projectPath: () => '',
            nameOf: () => 'Project',
            findProject: () => null,
            findTask: () => null,
            findTaskInData: () => null,
            allTasks: () => [],
            findSession: () => null,
            sessionTaskId: () => '',
            latestSessionForTask: () => null,
            sessionRefValue: (entry) => typeof entry === 'string' ? entry : (entry && (entry.session_id || entry.id)) || '',
            normalizeTaskGrade: () => 'green',
            getTaskQaStatus: () => '',
            getTaskMoreWork: () => '',
            actionableTaskCount: () => 0,
            summarizeTaskFilters: () => '',
            renderProjectDetail: () => {},
            loadProjectDetail: async () => ({}),
            refreshOpsSessions: async () => [],
            reloadProjectTasks: async () => ({}),
            loadProjects: async () => [],
            renderProjects: () => {},
            renderHome: () => {},
            loadSession: async (sid) => { calls.push(`load:${sid}`); },
            renderSessionList: async () => { calls.push('render-list'); },
            closeOpsDashboard: () => { calls.push('close-dashboard'); },
            enterOpsSessionInspectMode: (payload) => { calls.push(`inspect:${payload && payload.sessionId}`); },
            showToast: () => {},
            showPromptDialog: async () => null,
            showConfirmDialog: async () => false,
            setBusy: () => {},
            domLookup: () => ({ value: '', files: [] }),
            documentRef: context.document,
            windowRef,
            FileReaderRef: function(){},
            SRef: () => ({ session: { session_id: 'current-session' }, messages: [], entries: [] }),
            addFiles: () => {},
            renderTray: () => {},
            clearSessionReadableOutput: () => {},
            clearPersistedSessionId: () => {},
            sendTurn: async () => {},
            autoResize: () => {},
            clearQuickTaskImages: () => {},
          });

          await dashboard.openOpsSession('target-session');
          const expected = ['load:target-session', 'render-list', 'close-dashboard', 'inspect:target-session'];
          if (JSON.stringify(calls) !== JSON.stringify(expected)) {
            throw new Error(`Unexpected simplified inspect order: ${JSON.stringify(calls)}`);
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


def test_phase11_ops_task_execution_selects_project_profile_before_sending_turn():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        (async () => {
          const source = fs.readFileSync('static/ops-legacy-task-actions.js', 'utf8');
          const windowRef = { HermesOpsModules: {}, _opsDashboardOpen: true, localStorage: { getItem: () => null } };
          const documentRef = {};
          const context = { console, window: windowRef, document: documentRef };
          vm.createContext(context);
          vm.runInContext(source, context);

          const project = { id: 'project-1', name: 'Project One', profile: 'project-profile', resolvedPath: '/tmp/project-1' };
          const epic = { id: 'epic-1', title: 'Epic' };
          const task = { id: 'task-1', text: 'Run task', done: false };
          const state = { session: null, activeProfile: 'default', messages: [], entries: [] };
          const calls = [];
          const labels = { profileChipLabel: { textContent: '' }, profileChipCompactLabel: { textContent: '' } };

          const dashboard = context.window.HermesOpsModules.taskActions.bindDashboard({
            OPS: { currentProject: project, sessions: [], projects: [project] },
            AgentBridge: {
              sessions: {
                ensureTask: async (projectId, taskId, payload) => {
                  calls.push(`ensure:${payload.profile}`);
                  return { session: { session_id: 'session-1', profile: payload.profile }, task: { ...task, inProgress: true } };
                },
              },
              runs: { create: async (payload) => ({ id: 'run-1', ...payload }) },
            },
            api: async () => ({}),
            projectUrl: (projectId, suffix) => `/projects/${projectId}${suffix}`,
            projectPath: (entry) => entry.resolvedPath,
            nameOf: (entry) => entry.name,
            findProject: () => project,
            findTask: () => ({ epic, task }),
            findTaskInData: () => ({ epic, task }),
            allTasks: () => [task],
            findSession: () => null,
            sessionTaskId: () => '',
            latestSessionForTask: () => null,
            sessionRefValue: (entry) => typeof entry === 'string' ? entry : (entry && (entry.session_id || entry.id)) || '',
            normalizeTaskGrade: () => 'green',
            getTaskQaStatus: () => '',
            getTaskMoreWork: () => '',
            actionableTaskCount: () => 1,
            summarizeTaskFilters: () => '',
            renderProjectDetail: () => {},
            loadProjectDetail: async () => ({}),
            refreshOpsSessions: async () => [],
            reloadProjectTasks: async () => ({ epics: [{ ...epic, tasks: [task] }] }),
            loadProjects: async () => [project],
            renderProjects: () => {},
            renderHome: () => {},
            loadSession: async (sid) => { state.session = { session_id: sid, profile: 'project-profile' }; calls.push(`load:${sid}`); },
            renderSessionList: async () => { calls.push('render-list'); },
            closeOpsDashboard: () => {},
            showToast: () => {},
            showPromptDialog: async () => null,
            showConfirmDialog: async () => false,
            setBusy: (value) => { calls.push(`busy:${value}`); },
            domLookup: (id) => id === 'msg' ? { value: '', files: [] } : (labels[id] || null),
            documentRef,
            windowRef,
            FileReaderRef: function(){},
            SRef: () => state,
            addFiles: () => {},
            renderTray: () => {},
            clearSessionReadableOutput: () => {},
            clearPersistedSessionId: () => {},
            sendTurn: async () => { calls.push(`send-profile:${state.activeProfile}`); },
            autoResize: () => {},
            clearQuickTaskImages: () => {},
          });

          await dashboard.executeTaskMatch(project, { epic, task }, {});
          if (!calls.includes('ensure:project-profile')) throw new Error(`Task session was not created for project profile: ${JSON.stringify(calls)}`);
          if (!calls.includes('send-profile:project-profile')) throw new Error(`Send turn did not use project profile: ${JSON.stringify(calls)}`);
          if (state.activeProfile !== 'project-profile') throw new Error(`Active profile was not selected: ${state.activeProfile}`);
          if (labels.profileChipLabel.textContent !== 'project-profile') throw new Error(`Profile chip was not updated: ${labels.profileChipLabel.textContent}`);
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

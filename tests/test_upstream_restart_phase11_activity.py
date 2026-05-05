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

          dashboard.renderHome();
          const html = rootEl.innerHTML;
          if (!html.includes('menu-page-content')) throw new Error('Missing Cloud Terminal menu-page wrapper.');
          if (!html.includes('<h2>Menu</h2>')) throw new Error('Missing Cloud Terminal menu heading.');
          if (!html.includes('Use the navigation buttons below and review active agent notifications.')) throw new Error('Missing Cloud Terminal menu description.');
          if (!html.includes('menu-inline-toggle')) throw new Error('Missing inline auto-approve toggle.');
          if (!html.includes('Auto-approve routine requests')) throw new Error('Missing Cloud Terminal auto-approve copy.');
          if (!html.includes('menu-quick-task-form')) throw new Error('Missing Cloud Terminal quick task form wrapper.');
          if (!html.includes('task-add-btn')) throw new Error('Missing Cloud Terminal quick task primary button style.');
          if (!html.includes('Create & run')) throw new Error('Missing Cloud Terminal quick task submit label.');
          if (!html.includes('menu-actions')) throw new Error('Missing Cloud Terminal menu action strip.');
          if (!html.includes('data-ops-action="show-create-project"')) throw new Error('Missing create-project menu action.');
          if (!html.includes('while this menu is visible.')) throw new Error('Missing Cloud Terminal active-session help copy.');
          if (html.includes('Run as standing /goal')) throw new Error('Hermes-only goal-mode control should not be rendered in the Cloud Terminal parity shell.');
          if (html.includes('ops-home-top')) throw new Error('Legacy Hermes home top bar should not render in the Cloud Terminal parity shell.');

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

import io
import json
import shutil
import subprocess
import textwrap
from pathlib import Path
from urllib.parse import urlparse

import pytest


def run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


@pytest.fixture()
def git_available():
    if not shutil.which("git"):
        pytest.skip("git is not available")


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


def init_project_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "notification-project"
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    run_git(repo, "checkout", "-b", "feature/phase6")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "initial")
    return repo


def test_phase6_ops_notifications_list_and_respond_round_trip(monkeypatch, tmp_path, git_available):
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(tmp_path / "projects-root"))

    repo = init_project_repo(tmp_path)

    from api.routes import handle_get, handle_post, submit_pending
    from api.clarify import submit_pending as submit_clarify_pending
    from api.models import Session
    from api import ops_projects, session_sidecars

    project = ops_projects.create_ops_project({"name": "Notification Project", "path": str(repo), "coreBranch": "main"})
    epic_id = ops_projects.add_ops_project_epic(project["id"], "Phase 6")["epic"]["id"]
    approval_task = ops_projects.add_ops_project_task(project["id"], epic_id, "Review approval prompt")["task"]
    clarify_task = ops_projects.add_ops_project_task(project["id"], epic_id, "Answer clarify prompt")["task"]

    approval_session = Session(session_id="notifapprove1", title="Approval session", workspace=str(repo), messages=[{"role": "user", "content": "hello"}])
    approval_session.save()
    clarify_session = Session(session_id="notifclarify1", title="Clarify session", workspace=str(repo), messages=[{"role": "user", "content": "hello"}])
    clarify_session.save()

    session_sidecars.set_session_linkage(approval_session.session_id, project["id"], approval_task["id"])
    session_sidecars.set_session_linkage(clarify_session.session_id, project["id"], clarify_task["id"])

    submit_pending(
        approval_session.session_id,
        {
            "command": "git push origin master",
            "pattern_key": "git_push",
            "pattern_keys": ["git_push"],
            "description": "Potentially destructive push",
        },
    )
    submit_clarify_pending(
        clarify_session.session_id,
        {
            "question": "Which branch should I compare?",
            "choices_offered": ["main", "feature/phase6"],
            "session_id": clarify_session.session_id,
            "kind": "clarify",
        },
    )

    pending = _FakeHandler()
    assert handle_get(pending, urlparse("http://example.com/api/ops/notifications/pending")) is True
    payload = _response_json(pending)
    notifications = payload["notifications"]
    assert payload["count"] == 2
    approval = next(item for item in notifications if item["kind"] == "approval")
    clarify = next(item for item in notifications if item["kind"] == "clarify")
    assert approval["task"]["text"] == "Review approval prompt"
    assert approval["command"] == "git push origin master"
    assert clarify["question"] == "Which branch should I compare?"
    assert clarify["choices"] == ["main", "feature/phase6"]

    approval_respond = _FakeHandler(
        {
            "kind": "approval",
            "sessionId": approval_session.session_id,
            "approvalId": approval["approvalId"],
            "choice": "once",
        }
    )
    assert handle_post(approval_respond, urlparse("http://example.com/api/ops/notifications/respond")) is True
    assert _response_json(approval_respond)["choice"] == "once"

    clarify_respond = _FakeHandler(
        {
            "kind": "clarify",
            "sessionId": clarify_session.session_id,
            "response": "feature/phase6",
        }
    )
    assert handle_post(clarify_respond, urlparse("http://example.com/api/ops/notifications/respond")) is True
    assert _response_json(clarify_respond)["response"] == "feature/phase6"

    after = _FakeHandler()
    assert handle_get(after, urlparse("http://example.com/api/ops/notifications/pending")) is True
    assert _response_json(after)["notifications"] == []


def test_phase6_ops_notification_dismissals_persist(monkeypatch, tmp_path):
    from api import ops_notifications
    from api.routes_ops_notifications import handle_get, handle_post

    monkeypatch.setattr(
        ops_notifications,
        "OPS_NOTIFICATION_DISMISSALS_FILE",
        tmp_path / "ops" / "notification_dismissals.json",
    )

    initial = _FakeHandler()
    assert handle_get(initial, urlparse("http://example.com/api/ops/notifications/dismissed")) is True
    assert _response_json(initial)["dismissed"] == []

    dismissed = _FakeHandler({"notificationId": "run:completed-1"})
    assert handle_post(dismissed, urlparse("http://example.com/api/ops/notifications/dismiss"), {"notificationId": "run:completed-1"}) is True
    assert _response_json(dismissed)["notificationId"] == "run:completed-1"

    persisted = _FakeHandler()
    assert handle_get(persisted, urlparse("http://example.com/api/ops/notifications/dismissed")) is True
    payload = _response_json(persisted)
    assert payload["dismissed"] == ["run:completed-1"]
    assert (tmp_path / "ops" / "notification_dismissals.json").exists()



def test_phase6_ops_legacy_notification_dismiss_is_optimistic():
    script = textwrap.dedent(
        """
        (async () => {
        const fs = require('fs');
        const vm = require('vm');
        const source = fs.readFileSync('static/ops-legacy-notifications.js', 'utf8');
        const context = { window: {}, console, setInterval, clearInterval };
        vm.createContext(context);
        vm.runInContext(source, context);

        let persisted = false;
        let dismissResolve = null;
        let renderCount = 0;
        const OPS = {
          notifications: [
            { id: 'note-1', kind: 'run', message: 'First' },
            { id: 'note-2', kind: 'run', message: 'Second' },
          ],
          selectedRunId: 'run-1',
        };
        const bound = context.window.HermesOpsModules.notifications.bindDashboard({
          OPS,
          AgentBridge: {
            notifications: {
              dismiss(id){
                if (id !== 'note-1') throw new Error('wrong notification dismissed: '+id);
                return new Promise((resolve) => { dismissResolve = () => { persisted = true; resolve({ ok: true }); }; });
              },
              list(){
                return Promise.resolve({ notifications: persisted ? [{ id: 'note-2', kind: 'run', message: 'Second' }] : OPS.notifications });
              },
            },
            runs: { update(){ return Promise.resolve({}); }, createEvent(){ return Promise.resolve({}); }, list(){ return Promise.resolve({ runs: [] }); } },
            sessions: { list(){ return Promise.resolve({ sessions: [] }); } },
          },
          renderCurrentOpsView(){ renderCount += 1; },
          showToast(){},
          esc(value){ return String(value || ''); },
          svg(){ return ''; },
          windowRef: { navigator: {} },
          documentRef: { activeElement: null },
          loadRunDetail(){ throw new Error('dismiss should not block on run-detail reload'); },
          loadOpsRuns(){ return Promise.resolve({}); },
        });

        const pending = bound.dismissNotification('note-1');
        if (OPS.notifications.some((item) => item.id === 'note-1')) throw new Error('notification was not removed optimistically');
        if (renderCount !== 1) throw new Error('optimistic render did not happen before persistence');
        if (!dismissResolve) throw new Error('dismiss persistence was not started');
        dismissResolve();
        await pending;
        if (OPS.notifications.some((item) => item.id === 'note-1')) throw new Error('dismissed notification reappeared after persistence');
        if (renderCount < 2) throw new Error('final render after persistence did not happen');
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


def test_phase6_play_notification_proxy_url_preserves_subpath_mount():
    script = textwrap.dedent(
        """
        (() => {
        const fs = require('fs');
        const vm = require('vm');
        const source = fs.readFileSync('static/ops-legacy-notifications.js', 'utf8');
        const context = { window: {}, console, setInterval, clearInterval, URL };
        vm.createContext(context);
        vm.runInContext(source, context);

        const windowRef = {
          location: {
            origin: 'https://example.test',
            pathname: '/hermes/ops',
            href: 'https://example.test/hermes/ops',
          },
          navigator: {},
        };
        const bound = context.window.HermesOpsModules.notifications.bindDashboard({
          OPS: { notifications: [] },
          AgentBridge: { notifications: {}, runs: {}, sessions: {} },
          renderCurrentOpsView(){},
          showToast(){},
          esc(value){ return String(value || ''); },
          svg(){ return ''; },
          windowRef,
          documentRef: { activeElement: null },
          loadRunDetail(){},
          loadOpsRuns(){ return Promise.resolve({}); },
        });

        const resolved = bound.playInspectOverlayUrl({
          kind: 'play',
          projectId: 'project-1',
          inspectUrl: 'http://127.0.0.1:5123/game?x=1#chat',
          allocatedPort: 5123,
          inspectMode: 'proxy',
        });
        const expected = 'https://example.test/hermes/play-project/project-1/game?x=1#chat';
        if (resolved !== expected) throw new Error(`unexpected proxy URL: ${resolved}`);
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



def test_phase6_notification_polling_skips_overlapping_refreshes():
    script = textwrap.dedent(
        """
        (async () => {
        const fs = require('fs');
        const vm = require('vm');
        const source = fs.readFileSync('static/ops-legacy-notifications.js', 'utf8');
        let intervalCallback = null;
        const context = {
          window: {},
          console,
          setInterval(callback){ intervalCallback = callback; return 1; },
          clearInterval(){},
        };
        vm.createContext(context);
        vm.runInContext(source, context);

        let listCalls = 0;
        let pendingResolve = null;
        const OPS = {
          view: 'home',
          notifications: [],
          notificationPollBusy: false,
        };
        const windowRef = { _opsDashboardOpen: true, navigator: {} };
        const bound = context.window.HermesOpsModules.notifications.bindDashboard({
          OPS,
          AgentBridge: {
            notifications: {
              list(){
                listCalls += 1;
                return new Promise((resolve) => { pendingResolve = resolve; });
              },
            },
            runs: {},
            sessions: {},
          },
          renderCurrentOpsView(){},
          showToast(){},
          esc(value){ return String(value || ''); },
          svg(){ return ''; },
          windowRef,
          documentRef: { activeElement: null },
          loadRunDetail(){},
          loadOpsRuns(){ return Promise.resolve({}); },
        });

        bound.startNotificationPolling();
        if (typeof intervalCallback !== 'function') throw new Error('poll callback not registered');
        const firstTick = intervalCallback();
        const secondTick = intervalCallback();
        await Promise.resolve();
        if (listCalls !== 1) throw new Error(`overlapping poll was not skipped: ${listCalls}`);
        if (OPS.notificationPollBusy !== true) throw new Error('poll busy flag was not set');
        pendingResolve({ notifications: [] });
        await firstTick;
        await secondTick;
        if (OPS.notificationPollBusy !== false) throw new Error('poll busy flag was not cleared');
        const thirdTick = intervalCallback();
        await Promise.resolve();
        if (listCalls !== 2) throw new Error('poll did not resume after first request finished');
        pendingResolve({ notifications: [] });
        await thirdTick;
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



def test_phase6_pending_notifications_skips_linkage_resolution_until_pending(monkeypatch):
    from api import ops_notifications, ops_projects, ops_runs, session_sidecars, play_pipeline

    monkeypatch.setattr(
        ops_projects,
        "list_ops_projects",
        lambda: {"projects": [{"id": "project-1", "name": "Project"}]},
    )
    monkeypatch.setattr(
        session_sidecars,
        "list_project_linkage_records",
        lambda project_id: [
            {"projectId": project_id, "taskId": f"task-{index}", "sessionId": f"session-{index}"}
            for index in range(200)
        ],
    )
    monkeypatch.setattr(
        session_sidecars,
        "get_session_linkage",
        lambda session_id: (_ for _ in ()).throw(AssertionError("resolved an idle linkage")),
    )
    monkeypatch.setattr(
        ops_notifications,
        "_task_context",
        lambda project_id, task_id: (_ for _ in ()).throw(AssertionError("loaded idle task context")),
    )
    monkeypatch.setattr(ops_notifications, "_pending_approval", lambda session_id: {"pending": None, "pending_count": 0})
    monkeypatch.setattr(ops_notifications, "_pending_clarify", lambda session_id: {"pending": None, "pending_count": 0})
    monkeypatch.setattr(
        ops_runs,
        "list_ops_runs",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("notification polling called rich run enrichment")),
    )
    monkeypatch.setattr(play_pipeline, "build_project_play_status", lambda project_id: {})

    payload = ops_notifications.list_pending_notifications()

    assert payload == {"notifications": [], "count": 0}


def test_phase6_play_fallback_notification_targets_resolved_session_tip(monkeypatch):
    from api import ops_notifications

    monkeypatch.setattr(ops_notifications, "_recent_notification_time", lambda value: True)
    notification = ops_notifications._play_handoff_fallback_notification(
        {"id": "project-1", "name": "Project"},
        {
            "id": "run-1",
            "projectId": "project-1",
            "taskId": "task-1",
            "sessionId": "session-root",
            "metadata": {
                "resolvedSessionId": "session-tip",
                "playPipelineTriggeredAt": "2026-05-19T18:34:52.654Z",
                "playPipelineStatus": "building",
            },
        },
    )

    assert notification is not None
    assert notification["sessionId"] == "session-tip"
    assert notification["terminalTarget"]["sessionId"] == "session-tip"


def test_phase6_shell_includes_notifications_asset_and_payload():
    from api.routes import handle_get

    shell_page = _FakeHandler()
    assert handle_get(shell_page, urlparse("http://example.com/ops-phase")) is True
    html = bytes(shell_page.body).decode("utf-8")
    assert 'src="static/ops-notifications.js?v=' in html

    shell_api = _FakeHandler()
    assert handle_get(shell_api, urlparse("http://example.com/api/ops/shell")) is True
    payload = _response_json(shell_api)
    assert payload["assets"]["notificationsScript"] == "/static/ops-notifications.js"

    script = _FakeHandler()
    assert handle_get(script, urlparse("http://example.com/static/ops-notifications.js")) is True
    assert script.status == 200


def test_phase6_ops_ui_renders_and_responds_to_notifications():
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

        const fetchCalls = [];
        const projectsSource = fs.readFileSync('static/ops-projects.js', 'utf8');
        const notificationsSource = fs.readFileSync('static/ops-notifications.js', 'utf8');
        const fetch = async (path, options) => {
          fetchCalls.push({ path, options: options || null });
          if (path === '/api/ops/notifications/pending'){
            return {
              ok: true,
              json: async () => ({
                count: 2,
                notifications: [
                  {
                    notificationKey: 'approval:notifapprove1:a1',
                    kind: 'approval',
                    sessionId: 'notifapprove1',
                    sessionUrl: '/session/notifapprove1',
                    project: { name: 'Notification Project' },
                    task: { text: 'Review approval prompt' },
                    session: { title: 'Approval session' },
                    approvalId: 'a1',
                    description: 'Potentially destructive push',
                    command: 'git push origin master',
                    patternKeys: ['git_push'],
                    pendingCount: 1
                  },
                  {
                    notificationKey: 'clarify:notifclarify1:1',
                    kind: 'clarify',
                    sessionId: 'notifclarify1',
                    sessionUrl: '/session/notifclarify1',
                    project: { name: 'Notification Project' },
                    task: { text: 'Answer clarify prompt' },
                    session: { title: 'Clarify session' },
                    question: 'Which branch should I compare?',
                    choices: ['main', 'feature/phase6'],
                    pendingCount: 1
                  }
                ]
              })
            };
          }
          if (path === '/api/ops/projects'){
            return { ok: true, json: async () => ({ projects: [] }) };
          }
          if (path === '/api/ops/notifications/respond'){
            return { ok: true, json: async () => ({ ok: true }) };
          }
          throw new Error('Unexpected fetch path: ' + path);
        };

        const context = {
          console,
          window: {},
          fetch,
          HTMLFormElement: function HTMLFormElement(){},
          HTMLElement: function HTMLElement(){},
          HTMLInputElement: function HTMLInputElement(){},
          FormData: function FormData(){
            return {
              get: (name) => name === 'response' ? 'feature/phase6' : (name === 'sessionId' ? 'notifclarify1' : (name === 'kind' ? 'clarify' : ''))
            };
          },
          setTimeout,
          clearTimeout,
        };
        vm.createContext(context);
        vm.runInContext(notificationsSource, context);
        vm.runInContext(projectsSource, context);

        const root = new Root();
        context.window.HermesOpsProjects.mount(root, {
          phase: 'phase-6',
          route: '/ops',
          apiBase: '/api/ops',
          version: 'test-version',
        });

        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));

        if (!root.innerHTML.includes('Workflow Inbox')) throw new Error('Workflow inbox did not render');
        if (!root.innerHTML.includes('Review approval prompt')) throw new Error('Approval notification did not render');
        if (!root.innerHTML.includes('Which branch should I compare?')) throw new Error('Clarify notification did not render');
        if (!root.innerHTML.includes('Allow once')) throw new Error('Approval actions were not rendered');

        root.listeners.click({
          target: {
            closest: () => ({
              getAttribute: (name) => {
                if (name === 'data-ops-action') return 'respond-notification';
                if (name === 'data-notification-kind') return 'approval';
                if (name === 'data-session-id') return 'notifapprove1';
                if (name === 'data-approval-id') return 'a1';
                if (name === 'data-choice') return 'once';
                if (name === 'data-response') return '';
                return null;
              }
            })
          }
        });

        await new Promise((resolve) => setTimeout(resolve, 0));
        await new Promise((resolve) => setTimeout(resolve, 0));

        if (!fetchCalls.some((call) => call.path === '/api/ops/notifications/respond')) {
          throw new Error('Approval response route was not called');
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


def test_phase6_notification_refresh_preserves_existing_cards_during_loading():
    source = (Path(__file__).parent.parent / "static" / "ops-notifications.js").read_text(encoding="utf-8")
    assert "const content=items.length" in source
    assert "? '<div class=\"ops-notification-list\">'" in source
    assert "String(items.length)+' pending · refreshing'" in source
    assert "escapeHtml(headerText)" in source

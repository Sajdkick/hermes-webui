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

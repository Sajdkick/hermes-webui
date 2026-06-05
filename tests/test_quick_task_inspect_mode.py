from pathlib import Path
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[1]
OPS_DASHBOARD_JS = (ROOT / "static" / "ops-legacy-dashboard.js").read_text(encoding="utf-8")
DASHBOARD_ACTIONS_JS = (ROOT / "static" / "ops-legacy-dashboard-actions.js").read_text(encoding="utf-8")
TASK_ACTIONS_JS = (ROOT / "static" / "ops-legacy-task-actions.js").read_text(encoding="utf-8")


def test_quick_task_create_and_run_requests_inspect_mode_after_stream_start():
    assert "openInspectAfterStart=opts.openInspectAfterStart===true" in TASK_ACTIONS_JS
    assert "executeTaskMatch(project,match,{goalMode,openInspectAfterStart:true,forceNewSession:true})" in TASK_ACTIONS_JS
    assert "files:pendingQuickTaskFiles" not in TASK_ACTIONS_JS
    assert "model:modelState.model||undefined" not in TASK_ACTIONS_JS
    assert "model_provider:modelState.model_provider||null" not in TASK_ACTIONS_JS
    assert "project_id:project.id" in TASK_ACTIONS_JS


def test_quick_task_create_and_run_uses_lean_task_start_path():
    assert "return ensureProjectEpic(projectId,'Quick tasks',{lean:true});" in TASK_ACTIONS_JS
    assert "projectUrl(projectKey,'/epics/ensure')" in TASK_ACTIONS_JS
    assert "payload.skipExistingLookup=true" in TASK_ACTIONS_JS
    assert "const data=await reloadProjectTasks(project.id);" not in TASK_ACTIONS_JS
    assert "findTaskInData(data,created.task&&created.task.id)" not in TASK_ACTIONS_JS


def test_execute_task_match_sends_task_prompt_before_opening_inspect_mode():
    expected = """if(typeof autoResize==='function')autoResize();
          // Start the first turn before opening inspect mode. In standalone Ops,
          // opening the loaded session navigates to /session/<id>; doing that
          // before sendTurn() can leave a linked task session empty.
          await sendTurn();"""
    assert expected in TASK_ACTIONS_JS
    assert "openedInspectBeforeSend" not in TASK_ACTIONS_JS


def test_execute_task_match_runtime_order_sends_before_inspect_navigation():
    script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const code = fs.readFileSync({str(ROOT / 'static' / 'ops-legacy-task-actions.js')!r}, 'utf8');
        const events = [];
        const msg = {{ value: '' }};
        const task = {{ id: 'task-1', text: 'Fix the Summons launch flow', grade: 'green' }};
        const epic = {{ id: 'epic-1', title: 'Quick tasks' }};
        const project = {{ id: 'summons', name: 'Summons', path: '/tmp/summons', resolvedPath: '/tmp/summons', profile: 'summons' }};
        const state = {{ session: null, messages: [], entries: [], pendingFiles: [], activeProfile: 'wrong-profile' }};

        global.window = {{
          HermesOpsModules: {{}},
          _defaultModel: 'test-model',
          _activeProvider: 'test-provider',
          _opsDashboardOpen: true,
          localStorage: {{ getItem: () => null, setItem: () => null, removeItem: () => null }},
        }};
        global.document = {{
          body: {{ appendChild: () => null, classList: {{ add: () => null, remove: () => null }} }},
          createElement: () => ({{ style: {{}}, remove: () => null, addEventListener: () => null, click: () => null }}),
        }};

        vm.runInThisContext(code, {{ filename: 'ops-legacy-task-actions.js' }});
        const actions = window.HermesOpsModules.taskActions.bindDashboard({{
          OPS: {{ currentProject: project, sessions: [], sessionActivity: [], taskDataByProject: {{}}, taskData: {{}}, playBusyByProject: {{}}, projectHealthBusyByProject: {{}}, taskAutomationBusyByProject: {{}} }},
          AgentBridge: {{
            sessions: {{
              ensureTask: async (_projectId, _taskId, payload) => {{
                events.push(`ensure:${{payload.profile}}:${{Object.prototype.hasOwnProperty.call(payload,'model')}}:${{Object.prototype.hasOwnProperty.call(payload,'model_provider')}}`);
                return {{ session: {{ session_id: 'sess-1', profile: 'summons', source_tag: 'ops_task', messages: [] }}, task: {{ ...task, inProgress: true, sessionId: 'sess-1' }} }};
              }},
            }},
            runs: {{ create: async () => {{ events.push('record-run'); return {{ id: 'run-1' }}; }} }},
          }},
          api: async () => {{ events.push('api'); return {{}}; }},
          projectUrl: (_projectId, path) => `/api/ops/projects/summons${{path}}`,
          projectPath: () => '/tmp/summons',
          nameOf: () => 'Summons',
          findProject: () => project,
          findTask: () => ({{ epic, task }}),
          findTaskInData: () => ({{ epic, task }}),
          allTasks: () => [{{ epic, task }}],
          findSession: () => null,
          sessionTaskId: () => '',
          latestSessionForTask: () => null,
          sessionRefValue: (value) => typeof value === 'string' ? value : String((value && (value.session_id || value.sessionId || value.id)) || ''),
          normalizeTaskGrade: (grade) => grade || 'green',
          getTaskQaStatus: () => '',
          getTaskMoreWork: () => '',
          actionableTaskCount: () => 0,
          summarizeTaskFilters: () => ({{}}),
          renderProjectDetail: () => null,
          loadProjectDetail: async () => null,
          refreshOpsSessions: async () => [],
          reloadProjectTasks: async () => ({{ epics: [{{ ...epic, tasks: [task] }}] }}),
          loadProjects: async () => null,
          renderProjects: () => null,
          renderHome: () => null,
          loadSession: async () => {{ events.push('load-session'); state.session = {{ session_id: 'sess-1', profile: 'summons', source_tag: 'ops_task', message_count: 0 }}; }},
          renderSessionList: async () => {{ events.push('render-list'); }},
          closeOpsDashboard: () => {{ events.push('open-session'); }},
          showToast: () => null,
          showPromptDialog: async () => null,
          showConfirmDialog: async () => false,
          setBusy: (busy) => {{ events.push(`busy:${{busy}}`); }},
          domLookup: (id) => id === 'msg' ? msg : null,
          documentRef: global.document,
          windowRef: global.window,
          SRef: () => state,
          addFiles: () => null,
          renderTray: () => null,
          clearPersistedSessionId: () => null,
          sendTurn: async () => {{ events.push(`send:${{msg.value}}`); state.session.active_stream_id = 'stream-1'; }},
          autoResize: () => {{ events.push('resize'); }},
          clearQuickTaskImages: () => null,
          enterOpsSessionInspectMode: () => {{ events.push('inspect'); }},
        }});

        (async () => {{
          await actions.executeTaskMatch(project, {{ epic, task }}, {{ goalMode: true, openInspectAfterStart: true }});
          const sendIndex = events.findIndex((entry) => entry.startsWith('send:'));
          const openIndex = events.indexOf('open-session');
          if (sendIndex < 0) throw new Error(`sendTurn was not called: ${{events.join(',')}}`);
          if (openIndex < 0) throw new Error(`inspect/open handoff was not called: ${{events.join(',')}}`);
          if (sendIndex > openIndex) throw new Error(`sendTurn happened after inspect/open navigation: ${{events.join(',')}}`);
          if (!events[sendIndex].includes('/goal Execute on this task from the user')) throw new Error(`task prompt was not sent through goal mode: ${{events[sendIndex]}}`);
          const ensureEvent = events.find((entry) => entry.startsWith('ensure:'));
          if (ensureEvent !== 'ensure:summons:false:false') throw new Error(`task session inherited stale launch state: ${{events.join(',')}}`);
        }})().catch((error) => {{ console.error(error && error.stack || error); process.exit(1); }});
        """
    )
    subprocess.run(["node", "-e", script], check=True, cwd=ROOT)


def test_existing_ops_task_execution_actions_request_goal_mode():
    assert DASHBOARD_ACTIONS_JS.count("executeTask(taskId,{goalMode:true})") >= 2


def test_execute_ready_batch_execution_starts_as_goal():
    assert "msg.value=goalMode?`/goal ${taskPrompt}`:taskPrompt;" in TASK_ACTIONS_JS
    assert "executeTaskMatch(project,match,{goalMode:true})" in TASK_ACTIONS_JS
    assert "AI batch execution task created. Starting goal session..." in TASK_ACTIONS_JS


def test_quick_task_runner_defaults_to_goal_mode():
    assert "quickTaskGoalMode:true" in OPS_DASHBOARD_JS

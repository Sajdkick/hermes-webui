import subprocess
import textwrap


def test_project_detail_task_form_focus_survives_transient_refresh_body_focus():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync('static/ops-legacy-project-detail.js', 'utf8');
        let restoredField = null;
        let focusOptions = null;
        let selection = null;
        const body = { nodeName: 'BODY' };
        const documentElement = { nodeName: 'HTML' };
        const rootEl = {
          _inside: true,
          _html: '',
          contains(node){ return !!(node && node._inside); },
          querySelector(selector){
            if (selector === 'form[data-ops-submit="save-task"] [name="text"]') return restoredField;
            return null;
          },
          querySelectorAll(){ return []; },
          set innerHTML(value){
            this._html = String(value || '');
            const form = { _inside: true, dataset: { opsSubmit: 'save-task' } };
            restoredField = {
              _inside: true,
              disabled: false,
              focus(options){ focusOptions = options || {}; },
              setSelectionRange(start, end){ selection = [start, end]; },
              getAttribute(name){ return name === 'name' ? 'text' : ''; },
              closest(selector){
                if (selector.includes('data-ops-submit="save-task"')) return form;
                if (selector === '[name]') return this;
                return null;
              },
            };
          },
          get innerHTML(){ return this._html; },
        };
        const windowRef = { requestAnimationFrame: (cb) => cb() };
        const documentRef = { activeElement: body, body, documentElement };
        const context = { window: { HermesOpsModules: {} }, console, setTimeout, clearTimeout };
        vm.createContext(context);
        vm.runInContext(source, context);
        const OPS = {
          view: 'project-detail',
          currentProject: { id: 'project-1', name: 'Hermes', coreBranch: 'master', resolvedPath: '/repo' },
          taskData: { branch: 'master', epics: [{ id: 'epic-1', title: 'Epic 1', tasks: [] }] },
          taskFormDraft: { taskId: '', text: 'Keep typing', epicId: 'epic-1', grade: 'green', flags: '', markers: '', images: '' },
          createEpicDraftTitle: '',
          taskCreateCollapsed: false,
          taskFiltersCollapsed: true,
          taskFilters: {},
          taskFormDictationStatus: '',
          taskFormDictationStatusKind: 'info',
          taskFormDictationBusy: false,
          taskFormDictationActive: false,
          taskAutomationBusyByProject: {},
          editingTask: null,
        };
        const dashboard = context.window.HermesOpsModules.projectDetail.bindDashboard({
          OPS,
          root: () => rootEl,
          esc: (value) => String(value ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;'),
          svg: { refresh: '', close: '', mic: '' },
          setDashboardTopbar: () => {},
          showError: (error) => { throw error; },
          documentRef,
          windowRef,
          navigatorRef: {},
          AgentBridge: { sessions: {} },
          summarizeEpics: () => ({ active: 0, done: 0, epics: 1 }),
          nameOf: (project) => project.name,
          projectPath: (project) => project.resolvedPath,
          projectProfileLabel: () => 'default',
          rememberTaskFilterFocus: () => {},
          restoreTaskFilterFocus: () => {},
          syncEpicCollapseState: () => {},
          isEpicCollapsed: () => false,
          renderProjectPlayControls: () => '',
          renderProjectSettings: () => '',
          renderProjectHealth: () => '',
          renderProjectGitStatus: () => '',
          renderProjectRuntimeSnapshot: () => '',
          renderProjectRuntimeScreenshot: () => '',
          renderProjectPlayLogs: () => '',
          renderProjectGatherReports: () => '',
          renderProjectReviewRequests: () => '',
          renderProjectDeployment: () => '',
          renderProjectDatabase: () => '',
          renderProjectRunActivity: () => '',
          renderRunDetailPanel: () => '',
          resolvedTaskSession: () => null,
          sessionRefValue: () => '',
          updateTaskGrade: async () => {},
        });
        const form = { _inside: true, dataset: { opsSubmit: 'save-task' } };
        const oldField = {
          _inside: true,
          selectionStart: 4,
          selectionEnd: 8,
          getAttribute(name){ return name === 'name' ? 'text' : ''; },
          closest(selector){
            if (selector.includes('data-ops-submit="save-task"')) return form;
            if (selector === '[name]') return this;
            return null;
          },
        };
        dashboard.handleTaskFormFocus({ target: oldField });
        documentRef.activeElement = body;
        dashboard.renderProjectDetail();
        if (!rootEl.innerHTML.includes('value="Keep typing"')) throw new Error('Task draft text was not preserved.');
        if (!focusOptions || focusOptions.preventScroll !== true) throw new Error('Task text field was not refocused after refresh.');
        if (!selection || selection[0] !== 4 || selection[1] !== 8) throw new Error('Task text selection was not restored.');
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


def test_project_detail_dashboard_listens_for_task_form_focus():
    dashboard_js = open("static/ops-legacy-dashboard.js", encoding="utf-8").read()
    project_detail_js = open("static/ops-legacy-project-detail.js", encoding="utf-8").read()

    assert "document.addEventListener('focusin',handleTaskFormFocus)" in dashboard_js
    assert "handleTaskFormFocus," in project_detail_js
    assert "isTransientProjectDetailFocus(active))return" in project_detail_js

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPS_DASHBOARD_JS = (ROOT / "static" / "ops-legacy-dashboard.js").read_text(encoding="utf-8")
DASHBOARD_ACTIONS_JS = (ROOT / "static" / "ops-legacy-dashboard-actions.js").read_text(encoding="utf-8")
TASK_ACTIONS_JS = (ROOT / "static" / "ops-legacy-task-actions.js").read_text(encoding="utf-8")


def test_quick_task_create_and_run_requests_inspect_mode_after_stream_start():
    assert "openInspectAfterStart=opts.openInspectAfterStart===true" in TASK_ACTIONS_JS
    assert "executeTaskMatch(project,match,{files:pendingQuickTaskFiles,goalMode,openInspectAfterStart:true})" in TASK_ACTIONS_JS


def test_execute_task_match_opens_loaded_session_before_sending_task_prompt():
    expected = """if(typeof autoResize==='function')autoResize();
          if(openInspectAfterStart){
            openLoadedOpsSession(sessionKey||sessionId);
            openedInspectBeforeSend=true;
          }
          await sendTurn();"""
    assert expected in TASK_ACTIONS_JS
    assert "if(openInspectAfterStart&&!openedInspectBeforeSend){" in TASK_ACTIONS_JS


def test_existing_ops_task_execution_actions_request_goal_mode():
    assert DASHBOARD_ACTIONS_JS.count("executeTask(taskId,{goalMode:true})") >= 2


def test_execute_ready_batch_execution_starts_as_goal():
    assert "msg.value=goalMode?`/goal ${taskPrompt}`:taskPrompt;" in TASK_ACTIONS_JS
    assert "executeTaskMatch(project,match,{goalMode:true})" in TASK_ACTIONS_JS
    assert "AI batch execution task created. Starting goal session..." in TASK_ACTIONS_JS


def test_quick_task_runner_defaults_to_goal_mode():
    assert "quickTaskGoalMode:true" in OPS_DASHBOARD_JS

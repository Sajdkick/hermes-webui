from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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

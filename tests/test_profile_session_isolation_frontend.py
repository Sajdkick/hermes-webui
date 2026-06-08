"""Frontend regressions for per-session profile isolation.

Existing chats and project-owned sessions must keep using their own
`session.profile` even after the tab's active profile changes for a different
chat/project. Plain empty placeholder sessions may still adopt the newly
selected active profile before their first turn.
"""

from pathlib import Path
import subprocess
import textwrap

ROOT = Path(__file__).resolve().parents[1]
UI_JS = (ROOT / "static" / "ui.js").read_text(encoding="utf-8")
MESSAGES_JS = (ROOT / "static" / "messages.js").read_text(encoding="utf-8")
COMMANDS_JS = (ROOT / "static" / "commands.js").read_text(encoding="utf-8")
SESSIONS_JS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")


def _function_body(src: str, name: str) -> str:
    async_marker = f"async function {name}"
    marker = async_marker if async_marker in src else f"function {name}"
    start = src.index(marker)
    brace = src.index("{", start)
    depth = 0
    for idx in range(brace, len(src)):
        if src[idx] == "{":
            depth += 1
        elif src[idx] == "}":
            depth -= 1
            if depth == 0:
                return src[start:idx + 1]
    raise AssertionError(f"Could not extract {name}()")


def test_profile_helper_prefers_locked_session_profile_but_allows_empty_retag():
    helper_prefix = UI_JS[: UI_JS.index("const INFLIGHT=")]
    script = helper_prefix + textwrap.dedent(
        """
        function assertEqual(actual, expected, label){
          if(actual!==expected){
            throw new Error(`${label}: expected ${expected}, got ${actual}`);
          }
        }

        S.activeProfile='hermes';
        S.messages=[];
        const summonsWithHistory={profile:'summons',message_count:2};
        assertEqual(currentSessionProfileForTurn(summonsWithHistory),'summons','persisted history locks profile');
        assertEqual(displayProfileForCurrentSession(summonsWithHistory),'summons','display uses locked session profile');

        S.session={profile:'summons',message_count:0};
        S.messages=[{role:'user',content:'optimistic first turn'}];
        assertEqual(currentSessionProfileForTurn(S.session),'summons','optimistic local message locks first turn profile');

        S.session={profile:'summons',message_count:0};
        S.messages=[];
        assertEqual(currentSessionProfileForTurn(S.session),'hermes','empty placeholder can adopt active profile');
        assertEqual(displayProfileForCurrentSession(S.session),'hermes','empty placeholder display follows active profile');

        S.activeProfile='laxlyftet';
        S.session={profile:'hermes-webui',message_count:0,project_id:'project-1'};
        S.messages=[];
        assertEqual(currentSessionProfileForTurn(S.session),'hermes-webui','project-owned empty session locks project profile');

        S.session={profile:'hermes-webui',message_count:0,source_tag:'ops_task'};
        assertEqual(currentSessionProfileForTurn(S.session),'hermes-webui','ops task session locks project profile before first turn');

        S.activeProfile='';
        S.session=null;
        assertEqual(currentSessionProfileForTurn(null),'default','missing active profile falls back to default');
        """
    )
    subprocess.run(["node", "-e", script], check=True, cwd=ROOT)


def test_chat_start_uses_turn_profile_not_global_active_profile_directly():
    send_body = _function_body(MESSAGES_JS, "send")
    assert "const turnProfile=currentSessionProfileForTurn(S.session);" in send_body
    assert "profile:turnProfile" in send_body
    assert "if(S.session&&!sessionHasLockedProfile(S.session))S.session.profile=turnProfile" in send_body

    chat_start_index = send_body.index("api('/api/chat/start'")
    chat_start_payload = send_body[chat_start_index : chat_start_index + 500]
    assert "profile:turnProfile" in chat_start_payload
    assert "S.activeProfile" not in chat_start_payload


def test_queued_followups_goal_and_status_are_session_profile_aware():
    assert "profile:currentSessionProfileForTurn(_targetSession||S.session)" in MESSAGES_JS
    assert MESSAGES_JS.count("profile:currentSessionProfileForTurn(S.session)") >= 3
    assert "profile:S.activeProfile||S.session.profile" not in MESSAGES_JS
    assert "profile:S.session.profile||S.activeProfile" not in SESSIONS_JS
    assert "profile:currentSessionProfileForTurn(S.session)" in SESSIONS_JS

    helper_prefix = UI_JS[: UI_JS.index("const INFLIGHT=")]
    sidebar_helper = _function_body(SESSIONS_JS, "_sessionRowsWithActiveEphemeralSession")
    script = helper_prefix + sidebar_helper + textwrap.dedent(
        """
        function assertEqual(actual, expected, label){
          if(actual!==expected){
            throw new Error(`${label}: expected ${expected}, got ${actual}`);
          }
        }

        S.activeProfile='default';
        S.session={
          session_id:'modelkit-session',
          profile:'modelkit-profile',
          message_count:0,
          project_id:'modelkit',
          title:'ModelKit task',
        };
        const projectRows=_sessionRowsWithActiveEphemeralSession([]);
        assertEqual(projectRows[0].profile,'modelkit-profile','project-owned ephemeral sidebar row keeps session profile');

        S.session={session_id:'plain-empty',profile:'modelkit-profile',message_count:0,title:'New Chat'};
        const plainRows=_sessionRowsWithActiveEphemeralSession([]);
        assertEqual(plainRows[0].profile,'default','plain empty placeholder can still adopt active profile');
        """
    )
    subprocess.run(["node", "-e", script], check=True, cwd=ROOT)

    for fn_name in ("cmdGoal", "cmdQueue", "cmdInterrupt"):
        body = _function_body(COMMANDS_JS, fn_name)
        assert "currentSessionProfileForTurn" in body
        assert "S.activeProfile" not in body

    status_body = _function_body(COMMANDS_JS, "_statusCardFromSession")
    assert "displayProfileForCurrentSession(s)" in status_body
    assert "S.activeProfile" not in status_body

import os
import re
from pathlib import Path

import yaml


def test_profile_runtime_env_includes_terminal_config_and_dotenv(tmp_path):
    from api.profiles import get_profile_runtime_env

    home = tmp_path / "profiles" / "server-ops"
    home.mkdir(parents=True)
    (home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "terminal": {
                    "backend": "ssh",
                    "cwd": "/home/dso2ng/repos",
                    "timeout": 180,
                    "ssh_host": "pollux",
                    "ssh_user": "dso2ng",
                    "persistent_shell": True,
                    "lifetime_seconds": 300,
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (home / ".env").write_text(
        "TERMINAL_TIMEOUT=60\n"
        "TERMINAL_SSH_HOST=pollux-from-env\n"
        "HERMES_MAX_ITERATIONS=90\n",
        encoding="utf-8",
    )

    env = get_profile_runtime_env(home)

    assert env["TERMINAL_ENV"] == "ssh"
    assert env["TERMINAL_CWD"] == "/home/dso2ng/repos"
    assert env["TERMINAL_SSH_USER"] == "dso2ng"
    assert env["TERMINAL_PERSISTENT_SHELL"] == "true"
    assert env["TERMINAL_LIFETIME_SECONDS"] == "300"
    # .env remains the final override source, matching CLI/profile behaviour.
    assert env["TERMINAL_TIMEOUT"] == "60"
    assert env["TERMINAL_SSH_HOST"] == "pollux-from-env"
    assert env["HERMES_MAX_ITERATIONS"] == "90"


def test_profile_shared_skill_dirs_are_added_without_duplicates(tmp_path, monkeypatch):
    from api import profiles as profiles_mod

    home = tmp_path / "profiles" / "summons"
    shared = tmp_path / "shared-skills"
    shared.mkdir(parents=True)
    home.mkdir(parents=True)
    (home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "terminal": {"backend": "local", "cwd": "/workspace"},
                "skills": {"external_dirs": ["~/team-skills"]},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(profiles_mod, "get_webui_shared_skills_dirs", lambda: [shared])

    assert profiles_mod.ensure_webui_shared_skill_dirs(home) is True
    first = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert first["terminal"]["cwd"] == "/workspace"
    assert first["skills"]["external_dirs"] == ["~/team-skills", str(shared.resolve())]

    assert profiles_mod.ensure_webui_shared_skill_dirs(home) is False
    second = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert second["skills"]["external_dirs"] == ["~/team-skills", str(shared.resolve())]


def test_profile_runtime_env_ensures_shared_skill_dirs(tmp_path, monkeypatch):
    from api import profiles as profiles_mod

    home = tmp_path / "profiles" / "ops"
    shared = tmp_path / "repo" / ".agents" / "skills"
    shared.mkdir(parents=True)
    home.mkdir(parents=True)
    (home / "config.yaml").write_text("terminal:\n  backend: local\n", encoding="utf-8")
    monkeypatch.setattr(profiles_mod, "get_webui_shared_skills_dirs", lambda: [shared])

    env = profiles_mod.get_profile_runtime_env(home)

    assert env["TERMINAL_ENV"] == "local"
    cfg = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert str(shared.resolve()) in cfg["skills"]["external_dirs"]


def test_streaming_applies_profile_runtime_env_to_agent_run():
    src = Path("api/streaming.py").read_text(encoding="utf-8")

    assert "get_profile_runtime_env" in src
    assert "_profile_runtime_env" in src
    assert "old_profile_env" in src
    assert "os.environ.update(_profile_runtime_env)" in src


def test_streaming_thread_env_allows_profile_terminal_cwd_override():
    src = Path("api/streaming.py").read_text(encoding="utf-8")

    assert "def _build_agent_thread_env" in src
    assert "_thread_env = _build_agent_thread_env(" in src
    assert "_set_thread_env(**_thread_env)" in src
    assert "_set_thread_env(\n            **_profile_runtime_env,\n            TERMINAL_CWD" not in src
    assert "_readable_output_process_env =" in src
    assert "os.environ.update(_readable_output_process_env)" in src

    match = re.search(
        r"(def _build_agent_thread_env\(.*?\n)(?=\ndef |\nclass )",
        src,
        re.DOTALL,
    )
    assert match, "_build_agent_thread_env not found in api/streaming.py"
    ns: dict = {}
    exec(compile(match.group(1), "<streaming_extract>", "exec"), ns)

    env = ns["_build_agent_thread_env"](
        {
            "TERMINAL_CWD": "/profile/config/cwd",
            "HERMES_EXEC_ASK": "0",
            "HERMES_SESSION_KEY": "old-session",
            "HERMES_SESSION_ID": "old-session",
            "HERMES_SESSION_PLATFORM": "cli",
            "HERMES_HOME": "/old/profile/home",
            "TERMINAL_ENV": "ssh",
        },
        "/active/workspace",
        "active-session",
        "/active/profile/home",
    )

    assert env["TERMINAL_CWD"] == "/active/workspace"
    assert env["HERMES_EXEC_ASK"] == "1"
    assert env["HERMES_SESSION_KEY"] == "active-session"
    assert env["HERMES_SESSION_ID"] == "active-session"
    assert env["HERMES_SESSION_PLATFORM"] == "webui"
    assert env["HERMES_HOME"] == "/active/profile/home"
    assert env["TERMINAL_ENV"] == "ssh"
    assert env["HERMES_READABLE_OUTPUT_PATH"].endswith("/readable-output/active-session/message.md")
    assert env["HERMES_READABLE_OUTPUT_ASSET_DIR"].endswith("/readable-output/active-session/assets")
    assert env["CLOUD_TERMINAL_READABLE_OUTPUT_PATH"] == env["HERMES_READABLE_OUTPUT_PATH"]
    assert env["CLOUD_TERMINAL_SESSION_ID"] == "active-session"

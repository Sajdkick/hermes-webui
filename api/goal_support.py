"""Small WebUI bridge for Hermes Agent /goal support.

This module intentionally stays tiny and isolated so this fork can delete it when
Hermes WebUI grows native slash-command /goal support upstream.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ParsedGoalCommand:
    """Parsed `/goal` command from the WebUI composer."""

    action: str
    arg: str = ""


@dataclass(frozen=True)
class GoalCommandResult:
    """Result of a command-only goal action."""

    message: str
    run_text: Optional[str] = None


def parse_goal_command(text: str) -> Optional[ParsedGoalCommand]:
    """Return parsed goal command details, or None for non-`/goal` text."""
    raw = str(text or "").strip()
    if not raw.startswith("/goal"):
        return None
    head, _, rest = raw.partition(" ")
    if head.lower() != "/goal":
        return None
    arg = rest.strip()
    lower = arg.lower()
    if not arg or lower == "status":
        return ParsedGoalCommand("status")
    if lower == "pause":
        return ParsedGoalCommand("pause")
    if lower == "resume":
        return ParsedGoalCommand("resume")
    if lower in {"clear", "stop", "done"}:
        return ParsedGoalCommand("clear")
    return ParsedGoalCommand("set", arg)


def goal_manager_for_session(session_id: str) -> Any:
    """Create Hermes Agent's GoalManager for a WebUI session.

    The caller is responsible for setting HERMES_HOME / profile env before
    calling this so Hermes Agent persists state in the active profile.
    """
    from hermes_cli.goals import GoalManager

    max_turns = 20
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        goals_cfg = cfg.get("goals") or {}
        max_turns = int(goals_cfg.get("max_turns", 20) or 20)
    except Exception:
        max_turns = 20
    return GoalManager(session_id=session_id, default_max_turns=max_turns)


def handle_goal_command_only(manager: Any, parsed: ParsedGoalCommand) -> GoalCommandResult:
    """Handle `/goal` subcommands that do not start an agent turn."""
    if parsed.action == "status":
        return GoalCommandResult(str(manager.status_line()))
    if parsed.action == "pause":
        state = manager.pause(reason="user-paused")
        if state is None:
            return GoalCommandResult("No goal set.")
        return GoalCommandResult(f"⏸ Goal paused: {state.goal}")
    if parsed.action == "resume":
        state = manager.resume()
        if state is None:
            return GoalCommandResult("No goal to resume.")
        return GoalCommandResult(
            f"▶ Goal resumed: {state.goal}\n\nSend a message, or type `continue`, to kick it off."
        )
    if parsed.action == "clear":
        had = bool(manager.has_goal())
        manager.clear()
        return GoalCommandResult("✓ Goal cleared." if had else "No active goal.")
    raise ValueError(f"unsupported command-only goal action: {parsed.action}")


def handle_goal_set(manager: Any, parsed: ParsedGoalCommand) -> GoalCommandResult:
    """Set a goal and return the first prompt to run through AIAgent."""
    state = manager.set(parsed.arg)
    return GoalCommandResult(
        (
            f"⊙ Goal set ({state.max_turns}-turn budget): {state.goal}\n\n"
            "After each turn, Hermes will check if the goal is done and continue "
            "until it is complete, paused, cleared, or the turn budget is exhausted."
        ),
        run_text=state.goal,
    )

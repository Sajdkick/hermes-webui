"""Regression tests for targeted WebUI /goal support."""

from types import SimpleNamespace

from api.goal_support import (
    handle_goal_command_only,
    handle_goal_set,
    parse_goal_command,
)


class FakeGoalManager:
    def __init__(self):
        self.goal = "Ship the patch"
        self.cleared = False

    def status_line(self):
        return "Goal active: Ship the patch"

    def pause(self, reason=""):
        return SimpleNamespace(goal=self.goal, reason=reason)

    def resume(self):
        return SimpleNamespace(goal=self.goal)

    def has_goal(self):
        return not self.cleared

    def clear(self):
        self.cleared = True

    def set(self, goal):
        self.goal = goal
        return SimpleNamespace(goal=goal, max_turns=7)


def test_parse_goal_command_distinguishes_subcommands_and_goal_text():
    assert parse_goal_command("hello") is None
    assert parse_goal_command("/goal").action == "status"
    assert parse_goal_command("/goal status").action == "status"
    assert parse_goal_command("/goal pause").action == "pause"
    assert parse_goal_command("/goal resume").action == "resume"
    assert parse_goal_command("/goal clear").action == "clear"

    parsed = parse_goal_command("/goal Finish the implementation")
    assert parsed.action == "set"
    assert parsed.arg == "Finish the implementation"


def test_handle_goal_set_returns_kickoff_text_not_literal_slash_command():
    result = handle_goal_set(FakeGoalManager(), parse_goal_command("/goal Finish the implementation"))

    assert result.run_text == "Finish the implementation"
    assert "Goal set" in result.message


def test_handle_goal_command_only_keeps_status_display_only():
    result = handle_goal_command_only(FakeGoalManager(), parse_goal_command("/goal status"))

    assert result.run_text is None
    assert result.message == "Goal active: Ship the patch"

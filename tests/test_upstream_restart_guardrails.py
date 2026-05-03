import shutil
import subprocess
from pathlib import Path

import pytest

import upstream_restart_guardrails as restart_guardrails


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


def init_repo_with_upstream(tmp_path: Path) -> Path:
    upstream_remote = tmp_path / "upstream.git"
    subprocess.run(["git", "init", "--bare", str(upstream_remote)], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "--git-dir", str(upstream_remote), "symbolic-ref", "HEAD", "refs/heads/master"],
        check=True,
        capture_output=True,
        text=True,
    )

    seed = tmp_path / "seed"
    seed.mkdir()
    run_git(seed, "init")
    run_git(seed, "config", "user.email", "test@example.com")
    run_git(seed, "config", "user.name", "Test User")
    (seed / "api").mkdir()
    (seed / "static").mkdir()
    (seed / "api" / "routes.py").write_text("def route():\n    return 'ok'\n", encoding="utf-8")
    (seed / "static" / "index.html").write_text("<html>\n<body>ok</body>\n</html>\n", encoding="utf-8")
    run_git(seed, "add", "api/routes.py", "static/index.html")
    run_git(seed, "commit", "-m", "initial")
    run_git(seed, "remote", "add", "upstream", str(upstream_remote))
    run_git(seed, "push", "upstream", "HEAD:master")

    repo = tmp_path / "repo"
    run_git(tmp_path, "clone", str(upstream_remote), str(repo))
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    run_git(repo, "remote", "add", "upstream", str(upstream_remote))
    run_git(repo, "fetch", "upstream", "master")
    return repo


def test_restart_docs_exist_and_reference_phase_zero():
    plan = Path("docs/migration/upstream-restart-execution-plan.md").read_text(encoding="utf-8")
    progress = Path("docs/migration/restart-progress.md").read_text(encoding="utf-8")

    assert "Phase 0: Baseline And Guardrails" in plan
    assert "Hotspot Budget" in plan
    assert "Phase 0 deliverables" in progress
    assert "upstream_restart_guardrails.py" in progress


def test_restart_guardrails_block_when_branch_hotspot_exceeds_hard_budget(tmp_path, git_available):
    repo = init_repo_with_upstream(tmp_path)
    baseline = (repo / "api" / "routes.py").read_text(encoding="utf-8")
    extra_lines = "".join(f"line_{index}=True\n" for index in range(60))
    (repo / "api" / "routes.py").write_text(baseline + extra_lines, encoding="utf-8")
    run_git(repo, "add", "api/routes.py")
    run_git(repo, "commit", "-m", "expand routes")

    report = restart_guardrails.get_restart_guardrails(repo)

    assert report["status"] == "blocked"
    assert report["baseRef"] == "upstream/master"
    assert report["branchCounts"]["reviewRequired"] == 1
    assert report["branchHotspots"][0]["path"] == "api/routes.py"
    assert report["branchHotspots"][0]["budgetStatus"] == "review-required"


def test_restart_guardrails_warn_when_working_tree_hotspot_needs_justification(tmp_path, git_available):
    repo = init_repo_with_upstream(tmp_path)
    baseline = (repo / "static" / "index.html").read_text(encoding="utf-8")
    extra_lines = "".join(f"<div>line {index}</div>\n" for index in range(25))
    (repo / "static" / "index.html").write_text(baseline + extra_lines, encoding="utf-8")

    report = restart_guardrails.get_restart_guardrails(repo)

    assert report["status"] == "warning"
    assert report["branchCounts"]["changed"] == 0
    assert report["workingTreeCounts"]["changed"] == 1
    assert report["workingTreeCounts"]["needsJustification"] == 1
    assert report["workingTreeHotspots"][0]["path"] == "static/index.html"
    assert report["workingTreeHotspots"][0]["budgetStatus"] == "needs-justification"

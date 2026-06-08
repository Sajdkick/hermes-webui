import io
import json
import shutil
import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace
from urllib import error as urlerror

import pytest

import api.routes as routes
from api import ops_github, ops_projects, routes_ops_github

ROOT = Path(__file__).resolve().parents[1]
OPS_PROJECTS_JS = (ROOT / "static" / "ops-projects.js").read_text(encoding="utf-8")


def _function_body(src: str, name: str) -> str:
    marker = f"async function {name}"
    if marker not in src:
        marker = f"function {name}"
    start = src.index(marker)
    brace = src.index("{", start)
    depth = 0
    for idx in range(brace, len(src)):
        if src[idx] == "{":
            depth += 1
        elif src[idx] == "}":
            depth -= 1
            if depth == 0:
                return src[start : idx + 1]
    raise AssertionError(f"Could not extract {name}()")


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def fake_urlopen_factory(payloads, calls):
    def fake_urlopen(request, timeout=None):
        calls.append({"url": request.full_url, "headers": dict(request.header_items()), "timeout": timeout})
        if not payloads:
            raise AssertionError("Unexpected GitHub request")
        payload = payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return FakeResponse(payload)

    return fake_urlopen


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def isolate_projects(monkeypatch, projects_dir: Path) -> None:
    write_json(projects_dir / "projects.json", [])
    monkeypatch.setenv("HERMES_WEBUI_CLOUD_TERMINAL_PROJECTS_DIR", str(projects_dir))
    monkeypatch.setattr(ops_projects, "validate_workspace_to_add", lambda path: Path(path).resolve())
    monkeypatch.setattr(ops_projects, "load_workspaces", lambda: [])
    monkeypatch.setattr(ops_projects, "save_workspaces", lambda workspaces: None)


@pytest.fixture()
def git_available():
    if not shutil.which("git"):
        pytest.skip("git is not available")


def test_phase10_github_status_reports_missing_token(monkeypatch):
    for env_name in ops_github.TOKEN_ENV_NAMES:
        monkeypatch.delenv(env_name, raising=False)

    status = ops_github.github_status()

    assert status["tokenPresent"] is False
    assert status["authenticated"] is False
    assert status["user"] is None


def test_phase10_github_status_fetches_authenticated_user(monkeypatch):
    calls = []
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setattr(
        ops_github.urlrequest,
        "urlopen",
        fake_urlopen_factory(
            [
                {
                    "login": "octo",
                    "name": "Octo Cat",
                    "avatar_url": "https://example.com/avatar.png",
                    "html_url": "https://github.com/octo",
                }
            ],
            calls,
        ),
    )

    status = ops_github.github_status()

    assert status["authenticated"] is True
    assert status["tokenSource"] == "GITHUB_TOKEN"
    assert status["user"]["login"] == "octo"
    assert calls[0]["url"] == "https://api.github.com/user"
    assert calls[0]["headers"]["Authorization"] == "Bearer ghp_test"


def test_phase10_list_repositories_and_branches(monkeypatch):
    repo_calls = []
    monkeypatch.setenv("HERMES_GITHUB_TOKEN", "ghp_test")
    monkeypatch.setattr(
        ops_github.urlrequest,
        "urlopen",
        fake_urlopen_factory(
            [
                {
                    "total_count": 1,
                    "items": [
                        {
                            "id": 2,
                            "name": "hermes-webui",
                            "full_name": "acme/hermes-webui",
                            "owner": {"login": "acme"},
                            "default_branch": "main",
                        }
                    ],
                },
                [
                    {"name": "main", "protected": True, "commit": {"sha": "abc123"}},
                    {"name": "feature", "protected": False, "commit": {"sha": "def456"}},
                ],
            ],
            repo_calls,
        ),
    )

    repos = ops_github.list_repositories({"q": "hermes", "limit": "10"})
    branches = ops_github.list_branches("acme", "hermes-webui", {"limit": "2"})

    assert repos["source"] == "search"
    assert repos["repositories"][0]["fullName"] == "acme/hermes-webui"
    assert branches["authenticated"] is True
    assert [branch["name"] for branch in branches["branches"]] == ["main", "feature"]


def test_phase10_github_http_errors_are_normalized(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "bad")
    monkeypatch.setattr(
        ops_github.urlrequest,
        "urlopen",
        fake_urlopen_factory(
            [
                urlerror.HTTPError(
                    "https://api.github.com/user",
                    401,
                    "Unauthorized",
                    {},
                    io.BytesIO(b'{"message":"Bad credentials"}'),
                )
            ],
            [],
        ),
    )

    with pytest.raises(ops_github.OpsGitHubError) as exc:
        ops_github.github_status()

    assert exc.value.status == 401
    assert "Bad credentials" in str(exc.value)


def test_phase10_import_repository_clones_and_registers_project(tmp_path, monkeypatch, git_available):
    projects_dir = tmp_path / "projects"
    isolate_projects(monkeypatch, projects_dir)
    calls = []

    def fake_run(args, check=None, capture_output=None, text=None, timeout=None, cwd=None):
        calls.append(
            {
                "args": args,
                "check": check,
                "capture_output": capture_output,
                "text": text,
                "timeout": timeout,
                "cwd": cwd,
            }
        )
        if args[:2] == ["git", "clone"]:
            target = Path(args[-1])
            (target / ".git").mkdir(parents=True)
            (target / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
            (target / "README.md").write_text("# Repo\n", encoding="utf-8")
            return ops_github.subprocess.CompletedProcess(args, 0, stdout="cloned\n", stderr="")
        if args[:3] == ["git", "rev-parse", "--abbrev-ref"]:
            return ops_github.subprocess.CompletedProcess(args, 0, stdout="main\n", stderr="")
        return ops_github.subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(ops_github.subprocess, "run", fake_run)

    result = ops_github.import_repository({"owner": "acme", "repo": "repo", "branch": "main"})

    assert result["imported"] is True
    assert result["cloned"] is True
    assert result["cloneUrl"] == "https://github.com/acme/repo.git"
    assert result["project"]["fullName"] == "acme/repo"
    assert calls[0]["args"][:3] == ["git", "clone", "--branch"]


def test_phase10_import_missing_branch_creates_and_pushes_to_origin(tmp_path, monkeypatch, git_available):
    projects_dir = tmp_path / "projects"
    isolate_projects(monkeypatch, projects_dir)
    calls = []

    def fake_run(args, check=None, capture_output=None, text=None, timeout=None, cwd=None):
        calls.append(
            {
                "args": args,
                "check": check,
                "capture_output": capture_output,
                "text": text,
                "timeout": timeout,
                "cwd": cwd,
            }
        )
        if args[:4] == ["git", "ls-remote", "--exit-code", "--heads"]:
            branch = args[-1]
            if branch == "feature/new-project":
                return ops_github.subprocess.CompletedProcess(args, 2, stdout="", stderr="")
            return ops_github.subprocess.CompletedProcess(args, 0, stdout=f"abc123\trefs/heads/{branch}\n", stderr="")
        if args[:2] == ["git", "clone"]:
            target = Path(args[-1])
            (target / ".git").mkdir(parents=True)
            (target / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
            (target / "README.md").write_text("# Repo\n", encoding="utf-8")
            return ops_github.subprocess.CompletedProcess(args, 0, stdout="cloned main\n", stderr="")
        if args[:3] == ["git", "checkout", "-B"]:
            return ops_github.subprocess.CompletedProcess(args, 0, stdout="checked out\n", stderr="")
        if args[:3] == ["git", "push", "--set-upstream"]:
            return ops_github.subprocess.CompletedProcess(args, 0, stdout="pushed\n", stderr="")
        return ops_github.subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(ops_github.subprocess, "run", fake_run)

    result = ops_github.import_repository(
        {
            "owner": "acme",
            "repo": "repo",
            "branch": "feature/new-project",
            "defaultBranch": "main",
            "baseBranch": "main",
            "createMissingBranch": True,
        }
    )

    commands = [call["args"] for call in calls]
    assert result["imported"] is True
    assert result["branch"] == "feature/new-project"
    assert result["baseBranch"] == "main"
    assert result["branchCreated"] is True
    assert result["branchPushed"] is True
    assert result["project"]["coreBranch"] == "feature/new-project"
    assert ["git", "clone", "--branch", "main", "--single-branch", "https://github.com/acme/repo.git", str(projects_dir / "repo")] in commands
    assert ["git", "checkout", "-B", "feature/new-project", "origin/main"] in commands
    assert ["git", "push", "--set-upstream", "origin", "feature/new-project"] in commands


def test_phase10_github_import_prompt_sends_requested_branch_with_default_base():
    import_fn = _function_body(OPS_PROJECTS_JS, "importGitHubRepository")
    prompt_fn = _function_body(OPS_PROJECTS_JS, "promptGitHubImportBranch")
    script = import_fn + "\n" + prompt_fn + textwrap.dedent(
        """
        const calls=[];
        const state={};
        const root={};
        global.window={
          prompt(message, fallback){
            calls.push({kind:'prompt', message, fallback});
            return 'feature/from-prompt';
          }
        };
        function render(){ calls.push({kind:'render'}); }
        async function loadProjects(_root,_state,keepSelection){
          calls.push({kind:'loadProjects', keepSelection});
        }
        async function api(path,options){
          calls.push({kind:'api', path, body:options.body});
          return {imported:true, project:{name:'repo'}};
        }
        function assertEqual(actual, expected, label){
          if(actual!==expected){
            throw new Error(`${label}: expected ${expected}, got ${actual}`);
          }
        }
        (async()=>{
          await importGitHubRepository(root,state,{
            owner:'acme',
            repo:'repo',
            branch:'main',
            defaultBranch:'main',
            projectName:'repo',
          });
          const promptCall=calls.find((call)=>call.kind==='prompt');
          const apiCall=calls.find((call)=>call.kind==='api');
          assertEqual(promptCall.fallback,'main','prompt defaults to clicked/default branch');
          assertEqual(apiCall.path,'/api/ops/github/import','import endpoint');
          assertEqual(apiCall.body.branch,'feature/from-prompt','payload uses prompted branch');
          assertEqual(apiCall.body.defaultBranch,'main','payload preserves repo default branch');
          assertEqual(apiCall.body.baseBranch,'main','payload sends default branch as creation base');
          assertEqual(apiCall.body.createMissingBranch,true,'payload opts into missing branch creation');
          assertEqual(apiCall.body.createMissingCoreBranch,true,'payload opts into core branch creation');
          assertEqual(state.githubImportingRepoKey,'','busy key is cleared after import');
        })().catch((error)=>{
          console.error(error && error.stack || error);
          process.exit(1);
        });
        """
    )
    subprocess.run(["node", "-e", script], check=True, cwd=ROOT)


def test_phase10_github_routes_dispatch_through_ops_modules(monkeypatch):
    dispatch_calls = []
    handler = SimpleNamespace(command="POST", headers={}, host="127.0.0.1")

    def fake_get(_handler, parsed):
        dispatch_calls.append(("get", parsed.path, parsed.query))
        return parsed.path in {
            "/api/ops/github/status",
            "/api/ops/github/repos",
            "/api/ops/github/repos/acme/repo/branches",
        }

    def fake_post(_handler, parsed, body):
        dispatch_calls.append(("post", parsed.path, body))
        return parsed.path == "/api/ops/github/import"

    monkeypatch.setattr(routes_ops_github, "handle_get", fake_get)
    monkeypatch.setattr(routes_ops_github, "handle_post", fake_post)
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    monkeypatch.setattr(routes, "read_body", lambda _handler: {"owner": "acme", "repo": "repo"})

    assert routes.handle_get(handler, SimpleNamespace(path="/api/ops/github/status", query="")) is True
    assert routes.handle_get(handler, SimpleNamespace(path="/api/ops/github/repos", query="q=hermes")) is True
    assert routes.handle_get(handler, SimpleNamespace(path="/api/ops/github/repos/acme/repo/branches", query="limit=5")) is True
    assert routes.handle_post(handler, SimpleNamespace(path="/api/ops/github/import", query="")) is True

    assert dispatch_calls == [
        ("get", "/api/ops/github/status", ""),
        ("get", "/api/ops/github/repos", "q=hermes"),
        ("get", "/api/ops/github/repos/acme/repo/branches", "limit=5"),
        ("post", "/api/ops/github/import", {"owner": "acme", "repo": "repo"}),
    ]

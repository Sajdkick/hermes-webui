# Core API and Ops Deployments boundary extraction

Use this reference when a Hermes WebUI task asks to extract Cloud Terminal-style project/runtime/deployment capabilities into a shell-neutral Hermes Core API, or when Ops Dashboard Deployments should behave like Cloud Terminal's first-class Deployments page instead of linking to project detail.

## Durable pattern

1. Treat Cloud Terminal as design evidence unless the user explicitly asks for cross-repo shared code. For Hermes work, implement the contract inside Hermes and keep Cloud Terminal legacy/reference-only.
2. Add a shell-neutral `/api/core` namespace with small domain facades rather than putting shell-specific behavior into Ops route modules. Useful domain splits:
   - `core_contracts.py` for version, capability map, error envelope, operation record shape, redaction, and path-containment helpers.
   - `routes_core.py` as the HTTP dispatcher.
   - `core_projects.py`, `core_deployments.py`, `core_database.py`, `core_git.py`, `core_runtime_tools.py`, `core_host.py`, `core_session_assets.py`, and `core_play.py` as facade modules.
3. Keep existing `/api/ops/...` routes as compatibility shims where tests or UI contracts still depend on them. Route new UI surfaces through `/api/core/...`.
4. For Deployments, model Cloud Terminal's first-class page shape:
   - provider registry: `GET /api/core/deployments/providers`
   - per-project state: `GET /api/core/projects/{projectId}/deployment`
   - logs/artifacts/scaffold/execute/actions under the same project deployment subtree.
5. In the Ops Dashboard, add a dedicated `deployments` view in the shell/history router rather than overloading project detail. The Home/Menu action should open `DASHBOARD_DEPLOYMENTS.openDeployments()`, and the deployments module should load Core provider/project deployment data.
6. Preserve legacy project-card semantics while adding the dedicated page. In the successful session, legacy `opsCapabilities.deployment` stayed `false` for project compatibility tests, while the dedicated deployments view forced deployment-enabled behavior from Core provider availability.
7. Make deployment-module binding backwards compatible with older side-panel tests: optional page-level helpers such as `root`, `renderLoading`, `setDashboardTopbar`, and `loadProjects` should have safe fallbacks. Do not require them for project-detail side-panel rendering.

## Verification pattern

- Syntax: `python3 -m py_compile` for touched API modules and `node --check` for touched static modules.
- Focused tests should cover:
  - Core contract/capabilities/health/error redaction.
  - Core Play boundary compatibility if Play callers were rerouted.
  - Ops Deployments UI route/API behavior, especially that dedicated deployments calls `/api/core/deployments/providers` and `/api/core/projects/{id}/deployment`.
  - Legacy project compatibility expectations, including unchanged `opsCapabilities` shape where relevant.
- Browser smoke is valuable: start a temporary Hermes server, open `/ops`, click **View deployments**, confirm the heading is **Deployments**, provider metadata renders, project cards render, and the console is clean.
- If the full test suite has unrelated failures, isolate and rerun the focused Core/Ops tests plus any failures plausibly introduced by the change before reporting the unrelated full-suite drift.

## Pitfalls

- Do not mark all legacy project cards deployment-enabled just to make the dedicated page work; this can break compatibility tests and older side panels.
- Do not let `/api/core` expose shell-specific names, UI labels, or Cloud Terminal/Codex-only assumptions. Core can wrap existing implementations initially, but the contract should stay shell-neutral.
- Do not remove `/api/ops` compatibility routes in the same step as adding `/api/core`; migrate UI call sites deliberately and keep tests for both surfaces.

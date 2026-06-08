---
name: hermes-runtime-tools
description: Use this skill when a Hermes WebUI project/session needs managed Play startup, app inspection, screenshots, scripted browser actions, inspect guide recordings, gather report access, or user visual review through the Hermes runtime bridge. Start with doctor; missing runtime context in a WebUI-launched agent is a WebUI runtime-context injection gap, so report it and fall back to project docs, terminal/browser tools, and gather workflows instead of blocking.
---

# Hermes Runtime Tools

Use `hermes-runtime` as the Hermes WebUI Play/inspect bridge. In a correctly wired Hermes WebUI agent session, runtime context should be injected into the agent process, giving project-aware Play lifecycle, inspect URLs, managed browser sessions, screenshots, scripts, guides, and review requests. If that context is missing, treat it as a WebUI launch/runtime-context integration gap for the current session; continue with the project’s documented build/start path, browser tools, and `hermes-gather-information`, but do not normalize the missing bridge or claim managed runtime verification.

## First check

1. Resolve the command:
   - Start with `command -v hermes-runtime`.
   - If it is not on `PATH` but the Hermes WebUI checkout is available, use `/home/ubuntu/cloud-terminal-data/projects/hermes-webui/bin/hermes-runtime` or set `HERMES_RUNTIME_BIN` to that path for project helpers that invoke the runtime.
   - Do **not** switch to the legacy Cloud Terminal runtime tool when working from a Hermes WebUI task/session.
2. Check the runtime bridge before relying on managed Play/inspect:
   - `hermes-runtime doctor --json`
   - If using the repo binary directly: `/home/ubuntu/cloud-terminal-data/projects/hermes-webui/bin/hermes-runtime doctor --json`
3. Interpret `doctor` carefully:
   - `ok: true` means managed runtime commands should be available.
   - Missing `HERMES_WEBUI_RUNTIME_API_BASE_URL` / `HERMES_WEBUI_REQUEST_INPUT_TOKEN` means the active agent process does not have the WebUI runtime bridge context. In a normal Hermes WebUI-launched project session this should be present; if it is missing, report it as a WebUI runtime-context injection gap, not as an app failure.
   - If `doctor` is not `ok`, stop trying managed runtime commands except for help/diagnostics and jump to the manual Play-equivalent fallback.

## Workflow

1. Check current state:
   - `hermes-runtime status --json`
   - `hermes-runtime play status --json`
   - Compare `projectId`, `configPath`, `configBranch`, and Play build logs against the current workspace. If they point at a different project checkout/profile/branch than the task workspace, use `references/play-project-runtime-binding-mismatch.md` before treating app-specific 404s as source-code router failures.
   - For severe mismatches, also compare live non-secret env routing fields (`HERMES_SESSION_ID`, `HERMES_SESSION_KEY`, `HERMES_WEBUI_RUNTIME_API_BASE_URL`, `HERMES_WEBUI_RUNTIME_PROJECT_ID`, `TERMINAL_CWD`) with persisted session metadata. Mixed values from unrelated Ops task sessions indicate WebUI runtime/session isolation leakage rather than an app build-pipeline failure.
2. Start Play and wait for an inspectable app:
   - `hermes-runtime play start --wait --json`
   - Add `--restart` when you need a clean rerun.
   - Use `--timeout <duration>` for slower builds, e.g. `--timeout 8m`.
3. Inspect the app:
   - `hermes-runtime inspect url --json`
   - `hermes-runtime inspect screenshot --file-name ui-check --json`
   - `hermes-runtime inspect action --script-file inspect-actions.json --json`
   - `hermes-runtime inspect action --capture-screenshot --file-name post-action-check --script-file inspect-actions.json --json`
   - `hermes-runtime inspect run-script <path> --json`
   - `hermes-runtime inspect scenario list --json`
   - `hermes-runtime inspect scenario run <scenario-id> --json`
   - `hermes-runtime inspect session close <session-id> --json`
4. Use inspect guides for unfamiliar flows:
   - `hermes-runtime inspect guide list --json`
   - `hermes-runtime inspect guide show <guide-id> --json`
   - `hermes-runtime inspect guide request "Show me how to complete this flow in Play." --json`
   - `hermes-runtime inspect guide update <guide-id> --content-file <path> --json`
   - `hermes-runtime inspect guide delete <guide-id> --json`
5. Use gather report access when it complements runtime inspection:
   - `hermes-runtime gather create --title "Runtime repro" --json`
   - `hermes-runtime gather show <report-id> --json`
   - Prefer the `hermes-gather-information` skill when you need temporary app instrumentation and a user-driven repro.
6. If Play fails or never becomes ready:
   - `hermes-runtime play logs --limit 200 --json`
7. If screenshot capture is unavailable or you need human feedback:
   - `hermes-runtime inspect request-image-review <image-path> "Question for the user" --json`
   - `hermes-runtime inspect request-review "Please inspect the running app and share feedback." --json`

## Guidance

- When the managed bridge is available, run `hermes-runtime play start --wait --json` before trying to inspect or capture screenshots through the runtime.
- Use `hermes-runtime inspect screenshot --url <url>` only when you need a specific in-app route after Play is ready.
- Use `hermes-runtime inspect screenshot --session <id>` when the app state lives only inside an already-mutated browser session.
- If the project enables inspect auth, such as `inspect.auth.strategy=debug-login` or `AUTH_DEBUG_LOGIN=true` in Play config, `hermes-runtime inspect screenshot` primes a temporary authenticated browser profile before capture.
- Use `hermes-runtime inspect action` when managed browser reuse, scripted wait/click/drag/evaluate/assert automation, capture bundles, or transient playback inspection is more valuable than a one-off browser-tool interaction.
- Add `--capture-screenshot` when the action itself creates the state you need to verify and that state would be lost in a fresh browser.
- Add `--keep-session` when you want later `inspect action` or `inspect screenshot` commands to reuse the same browser memory and profile.
- Use `inspect run-script` or `inspect scenario run` when a workflow has multiple steps, helper code, adapter methods, gather snapshots, or previous-bundle comparison.
- Before guessing at an unfamiliar UI path, check `hermes-runtime inspect guide list` for a saved guide recording for that project.
- If no guide is good enough, ask the user to demonstrate the flow with `hermes-runtime inspect guide request` and then maintain or delete stale guides as part of the cleanup.
- Treat managed screenshots as best-effort. If runtime screenshot capture is not available, use browser tools or a manual Play-equivalent verification path and report the runtime limitation separately.
- Keep screenshot file names short and task-specific. Mention saved screenshot paths when you used them.

## Core API boundary extraction

When the task is to extract or refactor Hermes WebUI Play/runtime/project/deployment code into a core/runtime boundary, do **not** assume Cloud Terminal must consume the new boundary. If the user scopes Cloud Terminal as legacy/reference-only, keep all changes inside Hermes and use Cloud Terminal only as design evidence.

Use the boundary-first pattern from `references/core-play-boundary-extraction.md` for Play-only slices: add a small in-process facade such as `api/core_play.py`, keep `api/play_pipeline.py` as the implementation for the first slice, route every Ops Play caller through the facade, preserve route shapes/error behavior, document the contract, and prove no behavior changed with focused Play/runtime tests.

For broader `/api/core` extraction and Ops Deployments work, use `references/core-api-deployments-boundary.md`: keep Core shell-neutral, add compatibility shims for legacy `/api/ops` routes, make the dedicated Deployments view load provider/project deployment data from `/api/core`, and preserve legacy project capability shapes unless explicitly migrating them.

## Manual Play-equivalent fallback

This fallback is a workaround for the current session, not the desired steady state for Hermes WebUI-launched agents. The previous Summons flick-arrow investigation was successfully solved with `hermes-gather-information`, manual build/start, browser inspection, and targeted tests, but a correctly wired WebUI project session should still make `hermes-runtime doctor --json` pass.

If `hermes-runtime doctor --json` reports missing WebUI runtime context in the active agent process:

1. Do not claim managed runtime verification.
2. State that the current agent process is missing Hermes WebUI runtime bridge env and that this should be fixed in the WebUI/session launcher.
3. Use the project’s documented Play/build path instead, such as `docs/BUILDING.md`, `project_play.json`, or app-specific scripts.
4. Start the app manually, inspect it with browser tools, check console errors, and run targeted tests/builds.
5. In the final report, separate:
   - direct Hermes runtime availability;
   - manual Play-equivalent app health;
   - test/build results.

## Common patterns

- Visual check after a UI change:
  - `hermes-runtime doctor --json`
  - `hermes-runtime play start --wait --json`
  - `hermes-runtime inspect screenshot --file-name character-update --json`
- Scripted editor interaction:
  - `hermes-runtime play start --wait --json`
  - `hermes-runtime inspect action --url /app/editor --capture-screenshot --file-name trunk-graft --script-file trunk-graft.json --json`
- Reuse the same editor browser across multiple commands:
  - `hermes-runtime inspect action --url /app/editor --keep-session --script-file trunk-graft.json --json`
  - `hermes-runtime inspect screenshot --session <session-id> --file-name trunk-graft-review --json`
  - `hermes-runtime inspect session close <session-id> --json`
- Ask the user to verify a nuanced visual change:
  - `hermes-runtime inspect request-image-review /absolute/path/to/screenshot.png "Does this visual state look correct?" --json`
  - `hermes-runtime inspect request-review "Please verify the updated visuals and tell me what still looks off." --json`
- Debug a failing Play startup:
  - `hermes-runtime play start --wait --timeout 8m --json`
  - `hermes-runtime play logs --limit 200 --json`

## WebUI slowdown and recovery diagnostics

When Hermes WebUI starts responsive but slows over time, crashes, or lands on the recovery page, do not jump straight to broad cleanup. First correlate request diagnostics and code stages. In particular, repeated `/api/sessions` polling can be taken down by optional Agent `state.db` lineage metadata if the SQLite DB is malformed, locked, or slow. Use `references/webui-session-sidebar-slowdown.md` for the diagnostic path and degrade-safe fix pattern: quarantine malformed DB stat states, use short read-only SQLite timeouts for optional metadata, preserve `/api/sessions` JSON-session results without lineage metadata, and test retry-after-file-change behavior.

For project/session interruption reports where the session store is large or long-running transcripts are common, enforce the metadata-only hot-route boundary in `references/metadata-only-hot-route-boundary.md`: sidebar/session-list code must not silently fall back from metadata reads to full transcript parsing, because that can make UI polling heavy enough to trigger WebUI recovery and apparent response interruptions.

## References

- `references/play-project-runtime-binding-mismatch.md` — diagnostic and recovery pattern for Play/runtime sessions bound to the wrong WebUI project id, causing app-specific tRPC/static 404s despite correct source routers.
- `references/cloud-terminal-runtime-migration.md` — cleanup checklist and rationale for replacing Cloud Terminal-era runtime guidance with Hermes runtime usage.
- `references/core-play-boundary-extraction.md` — proven Hermes-only Play core boundary pattern, contract shape, caller list, verification gate, and pitfalls.
- `references/core-api-deployments-boundary.md` — broader Hermes Core API extraction and Ops Deployments page pattern, including Core route/domain shape, legacy Ops compatibility shims, and verification pitfalls.
- `references/webui-session-sidebar-slowdown.md` — diagnostic and fix pattern for WebUI slowdown/recovery caused by `/api/sessions` sidebar polling stuck in optional Agent `state.db` lineage metadata.
- `references/metadata-only-hot-route-boundary.md` — invariant and test pattern for keeping `/api/sessions`/sidebar metadata paths from falling back to full transcript parsing on large session stores.

---
name: cloud-terminal-runtime-tools
description: Use this skill when you are working in Hermes WebUI or a compatible runtime session and need to run the project, inspect the running app, capture screenshots, review Play logs, or ask the user to check the UI. Prefer this workflow for visual QA and runtime verification instead of guessing npm scripts, ports, or browser commands.
---

# Hermes Runtime Tools

Use `hermes-runtime` for Hermes WebUI Play, inspect, and gather workflows when available; it is the Hermes-owned runtime CLI and should be preferred over Cloud Terminal's `ct-runtime` in `/home/ubuntu/cloud-terminal-data/projects/hermes-webui`. Use `ct-runtime` only for actual Cloud Terminal project sessions that do not have `hermes-runtime`. Do not guess the app startup command, inspect URL, or screenshot tooling when the goal is to run and verify the current project from an agent session.

## Workflow

Use `hermes-runtime` in Hermes WebUI sessions. Substitute `ct-runtime` only when you are explicitly inside a Cloud Terminal project session that does not provide `hermes-runtime`.

1. Diagnose the runtime/session env before deeper debugging:
   - `hermes-runtime doctor --json`
   - Prefer `HERMES_WEBUI_RUNTIME_API_BASE_URL`, `HERMES_WEBUI_REQUEST_INPUT_URL`, and `HERMES_WEBUI_REQUEST_INPUT_TOKEN` for Hermes WebUI sessions. The older `HERMES_RUNTIME_API_BASE_URL`, `HERMES_REQUEST_INPUT_URL`, and `HERMES_REQUEST_INPUT_TOKEN` names are backward-compatible fallbacks.
   - If `doctor` reports missing runtime API/request-input env in a Hermes WebUI API-launched session, do not claim managed Play/inspect/gather is available. State the limitation and either use built-in browser tools, focused tests, or a clearly labeled manual Play-equivalent verification path. Do not add `ct-runtime` compatibility shims or switch to `ct-runtime` as a workaround.
2. Check the current runtime state:
   - `hermes-runtime status`
   - `hermes-runtime play status`
3. Start Play and wait for an inspectable app:
   - `hermes-runtime play start --wait`
   - Add `--restart` when you need a clean rerun.
4. Inspect the app:
   - `hermes-runtime inspect url`
   - `hermes-runtime inspect guide list`
   - `hermes-runtime inspect guide show <guide-id>`
   - `hermes-runtime inspect guide update <guide-id> --content-file <path>`
   - `hermes-runtime inspect guide delete <guide-id>`
   - `hermes-runtime inspect guide request "Show me how to complete this flow in Play."`
   - `hermes-runtime inspect screenshot --file-name ui-check`
   - `hermes-runtime inspect action --script-file inspect-actions.json`
   - `hermes-runtime inspect action --capture-screenshot --file-name post-action-check --script-file inspect-actions.json`
   - `hermes-runtime inspect session close <session-id>`
5. Gather user-driven repro evidence when runtime context is available:
   - `hermes-runtime gather create --title "Save flow repro" --json`
   - `hermes-runtime gather show REPORT_ID --json`
6. If Play fails or never becomes ready:
   - `hermes-runtime play logs --limit 200`
7. If screenshot capture is unavailable or you need human feedback:
   - `hermes-runtime inspect request-review "Please inspect the running app and share feedback."`

## Guidance

- Prefer `hermes-runtime play start --wait` before trying to inspect or capture screenshots.
- Use `hermes-runtime inspect screenshot --url <url>` only when you need a specific in-app route after Play is ready.
- Use `hermes-runtime inspect screenshot --session <id>` when the app state lives only inside an already-mutated browser session.
- If the project enables inspect auth (for example `inspect.auth.strategy=debug-login` or `AUTH_DEBUG_LOGIN=*** in Play config), `hermes-runtime inspect screenshot` will automatically prime a temporary authenticated browser profile before capture.
- Use `hermes-runtime inspect action` when you need scripted wait/click/drag automation inside the inspect browser, especially for canvas-heavy editors.
- Before guessing at an unfamiliar UI path, check `hermes-runtime inspect guide list` for a saved guide recording for that project.
- `hermes-runtime inspect guide show <guide-id>` prints any maintained written guide before the raw event log. Follow the written guide first and only fall back to the raw recording when you need extra detail.
- If no existing guide is good enough, use `hermes-runtime inspect guide request "..."` to ask the user to demonstrate the flow in Play and save a reusable recording.
- After you successfully use or troubleshoot a guide recording, update it with `hermes-runtime inspect guide update <guide-id> --content-file <path>` so the next agent gets the clearer steps and pitfalls instead of reinterpreting the recording from scratch.
- If you confirm that an existing guide is stale, misleading, or replaced by a newer recording, delete it with `hermes-runtime inspect guide delete <guide-id>` so future agents do not follow outdated instructions.
- When you rerecord a flow because the app changed, treat cleanup as part of the task: keep the new recording and remove the obsolete one.
- Add `--capture-screenshot` when the action itself creates the state you need to verify and that state would be lost in a fresh browser.
- Add `--keep-session` when you want later `inspect action` or `inspect screenshot` commands to reuse the same browser memory and profile.
- `inspect action` also supports `evaluate` and `assert` steps for deterministic DOM/app-state checks inside the running page.
- Treat screenshots as best-effort. If no supported headless browser is installed, fall back to `hermes-runtime inspect request-review`.
- Keep screenshot file names short and task-specific.
- Mention the saved screenshot path in your response when you used one.
- For manual review outside the CLI, Cloud Terminal Settings now has a Recordings section that groups guide recordings by project.

## Common Patterns

- Visual check after a UI change:
  - `hermes-runtime play start --wait`
  - `hermes-runtime inspect screenshot --file-name character-update`
- Scripted editor interaction:
  - `hermes-runtime play start --wait`
  - `hermes-runtime inspect action --url /app/editor --capture-screenshot --file-name trunk-graft --script-file trunk-graft.json`
- Reuse the same editor browser across multiple commands:
  - `hermes-runtime play start --wait`
  - `hermes-runtime inspect action --url /app/editor --keep-session --script-file trunk-graft.json`
  - `hermes-runtime inspect screenshot --session <session-id> --file-name trunk-graft-review`
  - `hermes-runtime inspect session close <session-id>`
- Gather repro diagnostics:
  - `hermes-runtime doctor --json`
  - `hermes-runtime gather create --title "Save flow repro" --json`
  - `hermes-runtime gather show REPORT_ID --json`
- Ask the user to verify a nuanced visual change:
  - `hermes-runtime inspect request-review "Please verify the updated visuals and tell me what still looks off."`
- Debug a failing Play startup:
  - `hermes-runtime play start --wait`
  - `hermes-runtime play logs --limit 200`

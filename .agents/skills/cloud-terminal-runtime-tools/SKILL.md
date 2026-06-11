---
name: cloud-terminal-runtime-tools
description: Use this skill when you are working inside a Cloud Terminal project session and need to run the project, inspect the running app, capture screenshots, review Play logs, or ask the user to check the UI. Prefer this workflow for visual QA and runtime verification instead of guessing npm scripts, ports, or browser commands.
---

# Cloud Terminal Runtime Tools

Use `ct-runtime` for Cloud Terminal Play and inspect workflows. Do not guess the app startup command, inspect URL, or screenshot tooling when the goal is to run and verify the current project from an agent session.

## Workflow

1. Check the current runtime state:
   - `ct-runtime status`
   - `ct-runtime play status`
2. Start Play and wait for an inspectable app:
   - `ct-runtime play start --wait`
   - Add `--restart` when you need a clean rerun.
3. Inspect the app:
   - `ct-runtime inspect url`
   - `ct-runtime inspect guide list`
   - `ct-runtime inspect guide show <guide-id>`
   - `ct-runtime inspect guide update <guide-id> --content-file <path>`
   - `ct-runtime inspect guide delete <guide-id>`
   - `ct-runtime inspect guide request "Show me how to complete this flow in Play."`
   - `ct-runtime inspect screenshot --file-name ui-check`
   - `ct-runtime inspect action --script-file inspect-actions.json`
   - `ct-runtime inspect action --capture-screenshot --file-name post-action-check --script-file inspect-actions.json`
   - `ct-runtime inspect session close <session-id>`
4. If `ct-runtime` itself refuses to run with a message like `ct-runtime only works inside a Cloud Terminal project session`, do not loop on it. Fall back to the repo-local Play configuration:
   - read `project_play.json` to identify the start command, port range, inspect URL, and auth strategy,
   - use `ps`/`ss`/`curl` to identify the live Play server and health endpoint,
   - if browser automation is needed, run Playwright against the local Play URL and use the app's configured inspect auth flow (for example, debug login) when available,
   - clearly report that `ct-runtime` was unavailable in the current tool session.
5. If Play fails or never becomes ready:
   - `ct-runtime play logs --limit 200`
6. If screenshot capture is unavailable or you need human feedback:
   - `ct-runtime inspect request-review "Please inspect the running app and share feedback."`

## Guidance

- Prefer `ct-runtime play start --wait` before trying to inspect or capture screenshots.
- Use `ct-runtime inspect screenshot --url <url>` only when you need a specific in-app route after Play is ready.
- Use `ct-runtime inspect screenshot --session <id>` when the app state lives only inside an already-mutated browser session.
- If the project enables inspect auth (for example `inspect.auth.strategy=debug-login` or `AUTH_DEBUG_LOGIN=true` in Play config), `ct-runtime inspect screenshot` will automatically prime a temporary authenticated browser profile before capture.
- Use `ct-runtime inspect action` when you need scripted wait/click/drag automation inside the inspect browser, especially for canvas-heavy editors.
- Before guessing at an unfamiliar UI path, check `ct-runtime inspect guide list` for a saved guide recording for that project.
- `ct-runtime inspect guide show <guide-id>` prints any maintained written guide before the raw event log. Follow the written guide first and only fall back to the raw recording when you need extra detail.
- If no existing guide is good enough, use `ct-runtime inspect guide request "..."` to ask the user to demonstrate the flow in Play and save a reusable recording.
- After you successfully use or troubleshoot a guide recording, update it with `ct-runtime inspect guide update <guide-id> --content-file <path>` so the next agent gets the clearer steps and pitfalls instead of reinterpreting the recording from scratch.
- If you confirm that an existing guide is stale, misleading, or replaced by a newer recording, delete it with `ct-runtime inspect guide delete <guide-id>` so future agents do not follow outdated instructions.
- When you rerecord a flow because the app changed, treat cleanup as part of the task: keep the new recording and remove the obsolete one.
- Add `--capture-screenshot` when the action itself creates the state you need to verify and that state would be lost in a fresh browser.
- Add `--keep-session` when you want later `inspect action` or `inspect screenshot` commands to reuse the same browser memory and profile.
- `inspect action` also supports `evaluate` and `assert` steps for deterministic DOM/app-state checks inside the running page.
- Treat screenshots as best-effort. If no supported headless browser is installed, fall back to `ct-runtime inspect request-review`.
- In UI Mode live preview tasks, follow `references/ui-mode-fast-iteration.md`: start from the resolved project source workspace and selected/page context, make targeted source edits first, let hot reload update the preview when possible, and only rebuild/restart after evidence shows the preview is serving immutable built output or did not pick up the edit.
- For UI Mode selected-element removal requests, also follow `references/ui-mode-selected-element-removal.md`: remove only the selected presentation elements/copy, preserve unselected controls/state, avoid empty header wrappers, and verify removed text/links/alerts are absent while core controls remain visible.
- When a build regenerates source files unrelated to the requested UI change (for example an app-module manifest), inspect the diff and revert only that incidental generated source while preserving the requested edit and any built runtime assets needed by the preview.
- For layout moves, prefer a deterministic DOM coordinate check over text-only grep: use Playwright against the local Play URL, authenticate through the configured inspect/debug flow if available, collect bounding boxes for the moved controls, and assert row/center alignment within a small tolerance.
- Keep screenshot file names short and task-specific.
- Mention the saved screenshot path in your response when you used one.
- For manual review outside the CLI, Cloud Terminal Settings now has a Recordings section that groups guide recordings by project.

## Common Patterns

- Visual check after a UI change:
  - `ct-runtime play start --wait`
  - `ct-runtime inspect screenshot --file-name character-update`
- Scripted editor interaction:
  - `ct-runtime play start --wait`
  - `ct-runtime inspect action --url /app/editor --capture-screenshot --file-name trunk-graft --script-file trunk-graft.json`
- Reuse the same editor browser across multiple commands:
  - `ct-runtime play start --wait`
  - `ct-runtime inspect action --url /app/editor --keep-session --script-file trunk-graft.json`
  - `ct-runtime inspect screenshot --session <session-id> --file-name trunk-graft-review`
  - `ct-runtime inspect session close <session-id>`
- Ask the user to verify a nuanced visual change:
  - `ct-runtime inspect request-review "Please verify the updated visuals and tell me what still looks off."`
- Debug a failing Play startup:
  - `ct-runtime play start --wait`
  - `ct-runtime play logs --limit 200`

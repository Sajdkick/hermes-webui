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
4. If Play fails or never becomes ready:
   - `ct-runtime play logs --limit 200`
5. If `ct-runtime` itself is unavailable in the agent shell (`command not found`), do not stop. Fall back to direct runtime discovery:
   - inspect running processes/ports with `ps`/`ss`,
   - hit local HTTP endpoints with `curl`/Python `urllib`,
   - use the browser tool against the discovered localhost URL,
   - verify the browser console and rendered DOM directly.
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

---
name: cloud-terminal-readable-output
description: Use this skill for any user-facing content the user needs to read, including the final answer. Do not rely on terminal scrollback for summaries, instructions, findings, conclusions, or next steps; write a Markdown briefing to the session-scoped readable-output file so Cloud Terminal shows it in the terminal page, including copied image assets when needed. Prefer the readable-output env vars when they exist, and derive the standard project-scoped fallback path when they do not.
---

# Cloud Terminal Readable Output

Use this skill by default for any user-facing content the user needs to read after the agent finishes, including your final answer. Cloud Terminal scrollback is not a reliable place for summaries, instructions, review notes, remediation steps, findings, conclusions, or next steps.

Do not put readable user-facing output in the terminal. Reserve terminal output for brief progress pings, routine chatter, and raw command output that the user is not expected to read later.

## Workflow

1. Prefer these env vars when they exist:
   - `CLOUD_TERMINAL_READABLE_OUTPUT_PATH`
   - `CLOUD_TERMINAL_READABLE_OUTPUT_DIR`
   - `CLOUD_TERMINAL_READABLE_OUTPUT_ASSET_DIR`
2. If those env vars are missing but `CLOUD_TERMINAL_SESSION_ID` exists, derive the standard project-scoped fallback path:
   - `PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"`
   - `CLOUD_TERMINAL_READABLE_OUTPUT_DIR="$PROJECT_ROOT/.cloud-terminal/readable-output/$CLOUD_TERMINAL_SESSION_ID"`
   - `CLOUD_TERMINAL_READABLE_OUTPUT_PATH="$CLOUD_TERMINAL_READABLE_OUTPUT_DIR/message.md"`
   - `CLOUD_TERMINAL_READABLE_OUTPUT_ASSET_DIR="$CLOUD_TERMINAL_READABLE_OUTPUT_DIR/assets"`
3. Use that fallback path for project sessions when you know the project root. `Repair session env` writes vars into the interactive shell, but the already-running agent process may still not see them, so deriving the canonical path is expected in that case.
4. If neither the env vars nor a safe fallback path can be derived, do not silently fall back to terminal scrollback. Tell the user readable-output is unavailable in this session.
5. Create the target directories if needed:
   - `mkdir -p "$(dirname "$CLOUD_TERMINAL_READABLE_OUTPUT_PATH")" "$CLOUD_TERMINAL_READABLE_OUTPUT_ASSET_DIR"`
6. Write a concise Markdown document to `CLOUD_TERMINAL_READABLE_OUTPUT_PATH`.
7. If you want inline images, copy them into `CLOUD_TERMINAL_READABLE_OUTPUT_ASSET_DIR` and reference them from the Markdown with relative paths such as `![Result screenshot](assets/result.png)`.
8. Leave the file in place after writing it. Cloud Terminal shows it automatically and deletes it when the user clicks the read button.
9. If you need to update the unread message, overwrite the same Markdown file instead of creating multiple variants.

## Content Guidance

- Prefer a short title, then the minimum sections the user needs.
- Keep it easy to scan: short paragraphs, short lists, concrete paths, concrete next steps.
- Prefer copied local assets in `assets/` over remote image URLs.
- Avoid raw HTML. Standard Markdown is enough.
- Keep the document compact. If it is getting very large, summarize and link to the relevant files instead.

## Example Shape

```markdown
# Fix applied

## What changed

- Updated the terminal overlay to show readable Markdown files.
- Added session-scoped asset support for inline screenshots.

## Verification

- `npm test`
- Manual check in the terminal page

## Next step

- Click **Read and return to terminal** after reviewing this note.

![Overlay screenshot](assets/overlay.png)
```

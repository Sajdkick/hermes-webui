---
name: cloud-terminal-important-requests
description: Use this skill when an approval or input request should bypass routine auto-approval and explicitly wait for the user. Reserve it for online lookups, destructive or privileged actions, or major work outside the current working directory.
---

# Cloud Terminal Important Requests

Use this skill sparingly. Most local reads, project-scoped edits, and routine test runs should continue without being flagged as important.

## Mark A Request Important When

- You need to look something up online or otherwise require network access.
- You need destructive, privileged, or high-risk approval.
- You need to read from or write to a location outside the current working directory in a significant way.
- You are about to trigger a costly or hard-to-reverse external side effect.

## Do Not Mark Important For

- Routine project tests.
- Normal reads inside the project or nearby repo metadata.
- Standard project-scoped code edits.
- Ordinary `ct-runtime` inspection or gather-information workflows.

## How To Flag It

- If the request format supports structured metadata, set `important: true` or `importance: "important"`.
- Also prefix the user-visible prompt or approval justification with `IMPORTANT:` so Cloud Terminal can detect it in text-only approval flows.
- Keep the request specific. State the exact action and why it must not be auto-approved.

## Examples

- `IMPORTANT: Do you want to allow network access so I can verify the latest API docs before changing the integration?`
- `IMPORTANT: Do you want to allow editing files outside /workspace because the fix requires updating a shared runtime config?`

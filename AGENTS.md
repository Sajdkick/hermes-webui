# Agent instructions for Hermes WebUI

This file is the shared entry point for AI assistants working in this
repository. Keep it project-specific and safe to publish. Do not put personal
machine setup, private network details, credentials, tokens, or local-only
workflow notes here.

## Read first

Before making changes, read:

1. `README.md`
2. `CONTRIBUTING.md`
3. `CHANGELOG.md`

For architecture, testing, or setup work, also read the matching reference:

- `ARCHITECTURE.md` for design constraints and current module layout
- `TESTING.md` for local verification commands and manual test guidance
- `docs/onboarding.md` for first-run onboarding behavior
- `docs/troubleshooting.md` for diagnostic flows

## Onboarding and reinstall support

If the task involves install, reinstall, bootstrap, first-run onboarding,
provider setup, local model server setup, Docker onboarding, WSL onboarding, or
support for a failed first run, read `docs/onboarding-agent-checklist.md`
before running commands or inspecting logs.

Follow that checklist's safety rules:

- use isolated `HERMES_HOME` and `HERMES_WEBUI_STATE_DIR` for trials unless the
  human explicitly asks to use real state
- do not delete or overwrite a real `~/.hermes` directory without explicit
  approval
- do not print API keys, OAuth tokens, cookies, full `.env` files, full
  `auth.json` files, or password hashes
- collect non-secret status and log evidence before recommending a fix

## Contribution style

- Keep changes focused on one logical problem.
- Prefer the existing Python + vanilla JavaScript structure over new
  dependencies or build steps.
- Update docs when changing setup, onboarding, runtime behavior, architecture,
  or testing guidance.
- Update `CHANGELOG.md` for user-visible behavior, setup, workflow, or
  documentation changes that should be release-note ready.
- For UI or UX changes, follow `CONTRIBUTING.md`: include before/after evidence
  and test relevant responsive states.

## Local state and secrets

Hermes WebUI can read and write real agent state, sessions, workspaces,
credentials, and cron data. Treat local validation as potentially destructive
unless you have confirmed the active state directories.

Prefer isolated trial state for experiments:

```bash
HERMES_HOME=/tmp/hermes-webui-agent-home \
HERMES_WEBUI_STATE_DIR=/tmp/hermes-webui-agent-state \
HERMES_WEBUI_PORT=8789 \
python3 bootstrap.py
```

Do not include private machine instructions in this tracked file. Use a
git-ignored local note for personal workflow details.

<!-- cloud-terminal:shared-instructions:start -->
When working in the project you might run into messy code or bugs that are unrelated to your current task. If you do, add a follow-up task to the project_tasks/<branch>.json file so we can fix it in the future. If you cannot find a suitable epic for the new task, create a new epic.

When adding follow-up tasks, keep them as new tasks in ready status:
- set "done": false
- leave "qaStatus" unset
- leave "inProgress" unset
- do not set "sessionId" or "lastSessionAt"
- never set newly created tasks to "ready-for-test"

Mark AI-generated epics and tasks by adding a "markers" array containing "AI suggestion".
If the epic or task already has markers, append "AI suggestion" without removing existing entries.
Examples:
- Epic: "markers": ["AI suggestion"]
- Task: "markers": ["AI suggestion"]

Always use the readable output skill when outputting text.
<!-- cloud-terminal:shared-instructions:end -->

# Prepare for shutdown button added

## What changed

Implemented a new **Prepare for shutdown** action in the Cloud Terminal recovery page source:

- Working checkout: `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal`
- UI/API file: `proxy.js`
- Tests: `test/proxy.test.js`

The recovery page now includes a **Prepare for shutdown** button that calls an authenticated read-only endpoint:

- `GET /control/shutdown-prep`

## What the report checks

The endpoint builds a shutdown-preparation report covering:

- Host/platform uptime, memory, and load.
- Root proxy state, active target, pending restart, and current operation.
- Runtime health.
- Running persisted terminal/agent sessions.
- Deployment metadata and deployment proxy status.
- Persistent deployment database modes.
- Managed Cloud Terminal PostgreSQL and system PostgreSQL TCP readiness.
- Disk usage for root, project, state, and deployment metadata paths.
- Relevant systemd services.
- Warnings and a manual checklist for safe RAM-upgrade shutdown.

## Safety properties

The action is intentionally non-destructive:

- It does **not** shut down the VM.
- It does **not** stop services.
- It does **not** restart the proxy.
- It does **not** mutate deployments or databases.
- It returns `shutdownStarted: false` and says no shutdown was started.
- It omits deployment provider secrets and database usernames/passwords/tokens.

## Verification

Ran from `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal`:

```bash
node --test test/proxy.test.js
```

Result:

- `38/38` proxy tests passed.
- New tests cover recovery-page wiring, authentication on `/control/shutdown-prep`, `shutdownStarted: false`, no-cache headers, and secret redaction.

Also ran:

```bash
git diff --check
```

Result: no whitespace errors.

## Notes

The live recovery page is served from the runtime copy, while changes were made in the working checkout as required by `AGENTS.md`. The live runtime will need the normal Cloud Terminal update/promotion path before the new button appears in the currently running `/recovery` page.

Existing unrelated `project_tasks/*` changes were already present in the Cloud Terminal checkout; this implementation touched only `proxy.js` and `test/proxy.test.js`.

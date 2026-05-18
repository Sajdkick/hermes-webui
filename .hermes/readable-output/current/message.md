# Ready tasks executed

## What changed

- Implemented Cloud Terminal deployment routing so `/deploy/...` requests are routed to a running Cloud Terminal backend instead of following the currently selected proxy target blindly.
- Added deployment proxy status discovery on Cloud Terminal backends at `/api/deployments/public/:slug/proxy-status`.
- Kept Hermes out of deployment target selection while preserving dev/prod fallback order.
- Added compatibility routing for deployment assets/API/WebSocket-style paths using deployment referer/cookie context, so deployed apps continue loading after switching to Hermes or the other Cloud Terminal target.
- Added proxy tests for deployment target selection, compatibility-path detection, and deployment-cookie handling.

## Task file updates

Updated `/home/ubuntu/cloud-terminal-data/projects/hermes-webui/project_tasks/master.json` directly:

- `1ca04eb3-3f09-481a-b855-f55e873cd655` → `qaStatus: "ready-for-test"`
- `68a44609-436a-4cc6-a3d8-4f25f9bd43c7` → `qaStatus: "ready-for-test"`
- `c49d1b23-f236-4909-8841-10b8e96ca9c9` → `qaStatus: "ready-for-test"`

No actionable ready / needs-more-work tasks remain in `master.json`.

## Verification

- `PATH=/usr/bin:/bin:$PATH node --test test/proxy.test.js` — 29/29 passing
- `PATH=/usr/bin:/bin:$PATH node --check server.js` — passing
- Earlier syntax check also covered `proxy.js`

## Files changed by this session

- `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/proxy.js`
- `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/server.js`
- `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal/test/proxy.test.js`
- `/home/ubuntu/cloud-terminal-data/projects/hermes-webui/project_tasks/master.json`

## Skill update

- Updated the `cloud-terminal-runtime-switching` skill with the deployment-routing pattern learned here.

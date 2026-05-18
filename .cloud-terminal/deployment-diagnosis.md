# Cloud Terminal deployment diagnosis

## Verdict

Cloud Terminal **is updated on disk**, but the public proxy process has not restarted into the updated code yet. The deployment request is still being handled by the old in-memory proxy path and is forwarded to Hermes, which returns `404 {"error":"not found"}`.

## Evidence

- Live root checkout: `/home/ubuntu/cloud-terminal` is at commit `7f117795e6a73c467f845fd5a6d6b69fc20df670`.
- Working checkout: `/home/ubuntu/cloud-terminal-data/projects/cloud-terminal` is also at `7f117795e6a73c467f845fd5a6d6b69fc20df670`.
- Runtime health reports `launcherCommitAligned: true` with `rootCommit == devCommit == 7f117795e6a73c467f845fd5a6d6b69fc20df670`.
- The updated `proxy.js` on disk contains deployment proxy routing (`DEPLOYMENT_PUBLIC_BASE_PATH`, `resolveDeploymentProxyTargetConfig`, `/api/deployments/public/.../proxy-status`).
- A test import of the updated proxy code resolves `/deploy/alternativedata/` to `dev` on port `5001`.
- The actual public proxy process is old/in-memory: PID `653611`, `node proxy.js`, uptime about 64 hours, started before the update.
- `/health/runtime` reports a pending proxy restart: `update-dev applied control-plane changes` at `2026-05-13T06:40:59.654Z`.

## Deployment status

- Deployment metadata exists for slug `alternativedata` with status `published`.
- Direct dev backend probe works: `http://127.0.0.1:5001/api/deployments/public/alternativedata/proxy-status` returns `200` with `running: true`.
- Public proxy probe fails: `http://127.0.0.1:5000/deploy/alternativedata/` returns a Hermes `404`, proving the public proxy did not apply the new deployment routing yet.

## Why the restart has not happened

The proxy has a pending self-restart, but it defers restarts while persisted dev/prod terminal sessions remain. Current blockers are in dev session state:

- `f9853864-8b69-444d-802b-31187fa0e4dc` — Cloud-Terminal task session, `notificationFlowState: running`
- `1633ff60-8bbc-4280-b072-5f6edab1e841` — hermes-webui task session, `notificationFlowState: completed`
- `a4084ce4-7f0b-46c8-a793-4f9940fdfc50` — hermes-webui task session, `notificationFlowState: completed`

I did **not** force-kill/restart the proxy because that can interrupt active Cloud Terminal/Hermes sessions.

## Next action

Close or clean up the persisted dev terminal sessions, then let the proxy retry (it has a pending restart) or restart Cloud Terminal during a safe maintenance window. After the proxy restarts, `/deploy/alternativedata/` should route to the dev backend instead of Hermes.

Readable-output note: this Hermes session did not expose `CLOUD_TERMINAL_READABLE_OUTPUT_PATH` or `CLOUD_TERMINAL_SESSION_ID`, so I could not write to the session-scoped Cloud Terminal readable-output channel. I saved this report at `.cloud-terminal/deployment-diagnosis.md` instead.

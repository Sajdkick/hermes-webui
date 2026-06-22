# WebUI session/sidebar slowdown from optional Agent state DB metadata

Use this reference when Hermes WebUI starts fast but slows over time, `/api/sessions` polling becomes slow, the UI falls into recovery, or logs mention malformed/unavailable Hermes Agent `state.db`.

## Diagnostic pattern

1. Confirm the hot endpoint and stage before optimizing broad session storage:
   - inspect recent WebUI/agent logs for slow `/api/sessions` requests;
   - look for request diagnostics stages such as `all_sessions.lineage_metadata`;
   - if the stage accounts for most wall time, follow the optional Agent `state.db` lineage path rather than assuming JSON session parsing is the only cause.
2. Trace the code path:
   - `GET /api/sessions` route;
   - `all_sessions(...)`;
   - sidebar lineage enrichment;
   - `api.agent_sessions.read_session_lineage_metadata(...)`;
   - SQLite reads against the Hermes Agent state database.
3. Check non-secret state pressure separately:
   - total WebUI state directory size;
   - session JSON count/size;
   - `sessions/_run_journal` size;
   - disk/memory/swap pressure.
   These amplify the failure, but do not treat them as root cause if the watchdog pins time in lineage metadata.
4. Check the Agent `state.db` non-destructively:
   - header/readability helpers if present;
   - read-only SQLite probes such as `PRAGMA quick_check` or `PRAGMA integrity_check` only when safe and scoped;
   - redact credentials and never dump full DB contents.

## Root-cause signal

A repeated warning like `database disk image is malformed` plus multi-minute `/api/sessions` requests stuck in `all_sessions.lineage_metadata` means optional lineage metadata is taking down the sidebar/session API. Restarting clears piled-up requests temporarily but does not fix the malformed DB or retry behavior.

## Fix pattern

Make optional Agent state DB metadata degrade safely:

- Quarantine/cache malformed or not-a-database SQLite errors against the DB stat key `(mtime_ns, size)` so the same bad DB is skipped until it changes.
- Give transient failures a short TTL instead of retrying every sidebar poll.
- Use read-only SQLite connections with a short timeout for optional metadata paths; do not allow default multi-second busy waits to stack up behind polling.
- Consider a small single-flight/cache around sidebar lineage metadata enrichment so concurrent `/api/sessions` polls do not open many simultaneous SQLite readers.
- Ensure `/api/sessions` still returns JSON session rows when Agent DB lineage metadata is unavailable.

## Tests to add

Prefer extending the existing session lineage metadata tests if present:

- malformed `state.db` is warned/skipped once and not retried while file stat is unchanged;
- retry occurs after the DB file changes;
- `all_sessions()`/`/api/sessions` returns sessions without optional lineage metadata when the DB is unavailable;
- optional concurrent/sidebar-style calls do not fan out into repeated SQLite probes.

## Reporting

When reporting this class of incident, include denominators and timings:

- `/api/sessions` normal vs degraded latency;
- slow diagnostic stage and duration;
- state directory/session/run-journal sizes;
- DB health result;
- whether the implemented fix is a quarantine/degrade-safe behavior or only a cleanup recommendation.

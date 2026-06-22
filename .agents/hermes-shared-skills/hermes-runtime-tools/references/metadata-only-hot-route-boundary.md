# Metadata-only hot-route boundary

Use this reference when diagnosing Hermes WebUI project/session interruptions that correlate with large session stores, giant sidecars, or slow `/api/sessions` polling.

## Durable lesson

A "metadata-only" load must be a hard contract on hot session-list/sidebar paths. If a helper named `load_metadata_only()` can silently fall back to full transcript parsing, then ordinary UI polling can become proportional to multi-megabyte or multi-gigabyte session history. On large project histories, that pressure can restart or stall the WebUI process and later surface as `**Response interrupted.**` recovery cards.

## Code smell

Look for these patterns in hot route/index code:

- `Session.load_metadata_only(...)` falling back to `Session.load(...)` on malformed or missing metadata prefix.
- `all_sessions()` or sidebar/index rebuild code calling `Session.load(...)` only to backfill `last_message_at`, `message_count`, title, profile, or lineage metadata.
- Broad directory scans that include `_run_journal`, temp files, backups, or helper directories near `sessions/`.
- Per-row reads of `_index.json` or state DB instead of one bounded/batched pass.

## Preferred invariant

For hot routes such as `/api/sessions`:

1. Read `_index.json` and metadata prefixes only.
2. If metadata is missing/corrupt, return a degraded metadata row or skip the row; do not parse `messages`.
3. Full transcript reads are allowed only on explicit cold paths: opening a specific session, import/recovery/admin tools, or user-requested transcript repair.
4. Persist hot-route fields, especially `last_message_at` and message count, before the `messages` array when saving sidecars so bounded metadata reads can satisfy sidebar ordering without scanning transcript tails.
5. Centralize canonical sidecar filtering in one iterator/predicate. Reuse it for full scans and index rebuilds so underscore system files, request dumps, temp files, backups, and helper artifacts cannot re-enter hot paths through a second ad hoc glob.
6. Treat degraded metadata rows as unavailable for full index rebuild/sidebar rows unless there is a deliberate compatibility reason to show them; do not invent convincing rows from corrupt or messages-first artifacts.
7. Add tests that monkeypatch `Session.load` to fail if called from `all_sessions()` or metadata-only scan paths.
8. Add fixture sidecars with giant `messages` arrays, messages-before-metadata legacy shape, malformed prefixes, and `request_dump_*.json` artifacts to prove route work stays bounded and filtering is centralized.
9. Test fixtures should use production `Session.save(..., skip_index=True)` ordering when they mean “valid sidecar”. Only hand-write `__dict__`/messages-first JSON when the test intentionally exercises legacy degradation.

## Implementation pattern

A robust fix usually needs both data-shape and code-boundary changes:

- Add a bounded parser for optional timestamps/counts that never needs the `messages` tail.
- Make `load_metadata_only()` return a marked degraded stub on missing/malformed prefixes instead of silently calling `Session.load()`.
- Replace legacy backfill logic such as “load full session to recover `last_message_at`” with persisted metadata, bounded metadata fallback, or explicit degradation.
- Route every sidecar scan through a single `_iter_session_sidecar_paths()`-style helper instead of repeating `SESSION_DIR.glob('*.json')`.
- Keep tests aligned with the contract: valid sidecars should be written with production save paths, while legacy fixtures should assert bounded degradation rather than exact transcript-derived recovery.

## Why this prevents interruption bugs

The visible interruption marker is often only the recovery symptom. The deeper cause can be that hot UI polling exhausts CPU/RAM or blocks long enough for the WebUI process to restart or lose stream bookkeeping. Enforcing a metadata-only boundary makes it harder for future edits to accidentally convert a sidebar refresh into a full transcript scan, which protects active `ACTIVE_RUNS` from being misclassified as dead after UI/SSE detachment.

# Hermes runtime/gather naming cleanup reference

Use this reference when the user asks to remove stale CT-runtime / Cloud Terminal gather wording or to verify that workflows are consistently Hermes runtime + Hermes gather.

## Canonical separation

- Runtime/Play/inspect lifecycle: `hermes-runtime`.
- User-reproduced evidence capture: Hermes WebUI gather via `scripts/hermes-gather.py` and `/api/gather/<report-id>/events`.
- Browser/server gather token header: `X-Hermes-Gather-Token`.

Do not teach gather creation/show through runtime commands. Keep runtime inspection and gather reports as separate workflows.

## Search patterns

Scan both skill libraries and the current workspace. Use exact patterns that avoid false positives like `direct-runtime`:

- `ct-runtime`
- `CT runtime`
- `Cloud Terminal runtime`
- `cloud-terminal-runtime`
- `Cloud Terminal Play`
- `Cloud Terminal gather`
- `cloud-terminal-gather`
- `x-cloud-terminal-gather-token`
- `/runtime/gather/`

Also scan for accidental broad-replacement corruption such as `direhermes-runtime`; repair those back to `direct-runtime`.

## Places stale references can hide

- Active profile skills under `~/cloud-terminal-data/projects/.cloud-terminal/hermes/skills`.
- Source/project skills under the WebUI checkout `.agents/skills`.
- Project docs, scripts, tests, and task JSON files.
- Debug helper code with default token headers.
- Generated reports, inspect artifacts, and snapshot index files under `.cloud-terminal/`.

Generated artifacts may preserve historical strings. If they are caches/reports rather than source-of-truth project files, remove them after verifying they are not required for the current task.

## Cleanup rules

1. Delete or absorb stale alias skills into the class-level Hermes skills instead of keeping parallel Cloud Terminal runtime/gather skills.
2. Replace operational instructions with Hermes equivalents:
   - `hermes-runtime` for Play/inspect/lifecycle.
   - Hermes WebUI gather script for report creation/show.
3. Replace stale gather headers with `X-Hermes-Gather-Token`.
4. Replace old ingest examples with canonical `/api/gather/<report-id>/events` when an example path is still needed.
5. Preserve legitimate app-internal terms like `direct-runtime`; do not broad-replace substrings.
6. Run focused tests for any changed helper code plus `git diff --check`.
7. Finish with a zero-match scan and report the exact roots scanned.

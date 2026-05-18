# Local Upstream Patches

This file tracks Type 2 changes: small local patches we carry in upstream-owned Hermes code.

Use this file to make maintenance work fast and reversible. When upstream catches up, remove the local patch instead of keeping duplicate logic around.

## Entry format

For every Type 2 patch, record:

- Patch name
- Status
- Files touched
- User-visible bug or behavior
- Why we carry it locally
- How to check whether upstream now supersedes it
- Exact removal steps
- Focused verification

## Current patches

### Codex OAuth compatibility in WebUI runtime

- Status: active
- Files touched: `api/oauth.py`
- User-visible bug or behavior:
  - Codex OAuth startup could fail with `HTTP Error 530` during device auth.
  - A successful Codex login in Settings could still fail to start a session with `Provider 'openai-codex' is set in config.yaml but no API key was found`.
- Why we carry it locally:
  - The WebUI needed to send an explicit Codex OAuth user agent for the OpenAI device-auth endpoint.
  - The Hermes runtime resolves Codex credentials from `providers.openai-codex.tokens`, while the WebUI was only persisting browser login state in `credential_pool`.
  - Named profiles can shadow root Codex credentials with stale profile-local refresh tokens; the runtime wrapper repairs that specific credential-failure case from the root profile before retrying.
- How to check whether upstream now supersedes it:
  - Inspect the upstream `api/oauth.py` or equivalent Codex OAuth path.
  - Confirm upstream already sends an explicit Codex OAuth `User-Agent` on the device-auth POST.
  - Confirm upstream persists or backfills active-profile Codex OAuth tokens into the runtime-visible provider state, not only `credential_pool`.
  - Confirm WebUI streaming passes the session profile's Hermes home into Codex runtime-state priming/backfill rather than relying on active-profile globals from a background thread.
  - Confirm upstream handles stale named-profile Codex tokens that shadow a newer root login, either by root fallback or an equivalent explicit repair path.
  - Confirm a Codex login through Settings can start a new `openai-codex` session without `OPENAI-CODEX_API_KEY`.
- Exact removal steps:
  - Remove the explicit Codex OAuth `User-Agent` override only if upstream now provides the same protection.
  - Remove the local provider-state mirror and backfill helpers only if upstream now writes or reconstructs `providers.openai-codex.tokens` itself.
  - Remove the runtime priming call only after the upstream auth resolution path already sees the correct Codex OAuth state without local help.
  - Keep or replace the regression tests so the working behavior stays covered after removal.
- Focused verification:
  - `pytest -q tests/test_issue1362_codex_oauth_onboarding.py tests/test_codex_settings_panel.py`
  - Manual check: login through Settings, then start a Codex-backed session without setting `OPENAI-CODEX_API_KEY`

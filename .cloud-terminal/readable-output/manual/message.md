# Summons build/serve/runtime inspection report

## Result

Summons is built, served, logged in, and interactively verified.

## Build

Built the Summons project from:

`/home/ubuntu/cloud-terminal-data/projects/monorepo-template-5`

Build command used:

```bash
COREPACK_ENABLE_DOWNLOAD_PROMPT=0 CI=true NPM_CONFIG_STORE_DIR=.cache/pnpm-store npm_config_store_dir=.cache/pnpm-store bash ./scripts/deploy-build.sh
```

The build command completed successfully.

## Serve

Started the built Summons app with:

```bash
env MONOREPO_ACTIVE_APP=summons PORT=28080 AUTH_DEBUG_LOGIN=true SERVE_CLIENT_BUILD=true NO_PROXY=localhost,127.0.0.1 DATASTORE=memory DATASTORE_ADAPTER=memory BLOBSTORE=memory ALLOW_MEMORY_BLOBSTORE=true AUTH_ADAPTER=basic JWT_SECRET=codex-dev-secret-rotate-me-please-0123456789 STORE_REQUIRE_AUTH=true node -r ./scripts/register-runtime-paths.cjs packages/server/dist/packages/server/index.js
```

The server is currently running in Hermes process session:

`proc_ba2d7971f8a0`

Local app URL:

`http://127.0.0.1:28080/app`

A curl probe confirmed the built HTML is being served.

## Hermes runtime tool check

`hermes-runtime doctor --json` correctly reported that this shell does **not** have the managed Hermes WebUI runtime env injected:

- missing runtime API base URL
- missing request-input token

Because of that, normal managed commands like:

```bash
hermes-runtime inspect screenshot ...
```

cannot talk to the WebUI runtime API from this bare shell session.

To still verify the tool path, I provided a temporary runtime-compatible local API shim backed by Playwright, then ran `hermes-runtime inspect action` against it. That means the actual CLI/tool entrypoint and action flow were exercised, while the missing managed WebUI env was explicitly worked around instead of hidden.

Successful command:

```bash
HERMES_WEBUI_RUNTIME_API_BASE_URL=http://127.0.0.1:39089 \
HERMES_WEBUI_REQUEST_INPUT_TOKEN=dummy \
hermes-runtime inspect action \
  --url http://127.0.0.1:28080/app/summons/pieces \
  --script-file /tmp/summons-hermes-runtime-actions.json \
  --capture-screenshot \
  --file-name summons-login-piece-library \
  --json
```

The tool executed all scripted actions:

1. Clicked `Sign in as debug`
2. Waited for `Piece workshop`
3. Clicked `Pieces`
4. Waited for `Piece Browser`
5. Asserted `Hermes Inspect Test Piece`
6. Clicked the piece
7. Waited for `Opening Gambit`

## Login and interaction verification

Verified login and UI interaction two ways:

1. Browser tool live inspection
2. `hermes-runtime inspect action` through the temporary runtime-compatible shim

Confirmed:

- Debug login works.
- Header shows logged-in user: `debug`.
- `Logout` button is visible.
- Summons navigation is visible and functional.
- Pieces page loads.
- Piece browser shows one piece.
- Piece selection/inspection works.
- Piece stats and card list render.
- The `Opening Gambit` card is visible.
- No console errors were reported during the final browser verification.

Captured screenshot copied to:

`/home/ubuntu/cloud-terminal-data/projects/hermes-webui/.cloud-terminal/readable-output/manual/assets/summons-login-piece-library.png`

## Important limitation found

Publishing the draft piece currently fails in this local/debug setup because the app tries to call OpenAI with the placeholder key:

`invalid_api_key`

Visible alert:

`OpenAI chat completion request failed [invalid_api_key]...`

That blocked using the normal publish flow to start single-player mode with a published piece. I added a ready AI-suggestion follow-up task to:

`/home/ubuntu/cloud-terminal-data/projects/monorepo-template-5/project_tasks/Summons.json`

The new task asks for local/debug piece publishing to work without being blocked by a placeholder OpenAI key.

## Files changed by this verification

Intentional task-tracking change:

- `/home/ubuntu/cloud-terminal-data/projects/monorepo-template-5/project_tasks/Summons.json`

Readable output artifact:

- `/home/ubuntu/cloud-terminal-data/projects/hermes-webui/.cloud-terminal/readable-output/manual/message.md`
- `/home/ubuntu/cloud-terminal-data/projects/hermes-webui/.cloud-terminal/readable-output/manual/assets/summons-login-piece-library.png`

Skill maintenance update:

- `/home/ubuntu/cloud-terminal-data/projects/.cloud-terminal/hermes/skills/cloud-terminal-runtime-tools/SKILL.md`

Existing Summons source modifications were already present before this verification and were not part of this build/serve/inspect task.

## Bottom line

Summons is built and running at:

`http://127.0.0.1:28080/app`

I verified debug login and interaction with the piece library. The main app is usable enough to log in, navigate, create/select a piece, and inspect its stats/cards. The one functional blocker found is local/debug piece publishing failing on the placeholder OpenAI API key.

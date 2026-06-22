# UI Mode / Play database parity

Use this when a Hermes WebUI UI Mode preview shows different data, login state, or server behavior than normal Play for the same project.

## Key finding

Play and UI Mode have separate lifecycle implementations:

- Play: `api/play_pipeline.py`
- UI Mode: `api/core_ui.py`

Play prepares app start env with `_prepare_start_runtime()`, which calls `_prepare_database_env(project_id, explicit_env, state)`. If the Play config does not already provide explicit DB env, `_prepare_database_env()` calls `managed_postgres.ensure_project_database_env(project_id)` and injects Hermes managed Postgres variables such as:

- `DATABASE_URL`
- `DATASTORE_POSTGRES_URL`
- `NAKAMA_DATABASE_URL`
- `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`

Native UI Mode prepares its dev runtime with `_prepare_dev_runtime()` and currently only merges UI config env plus the allocated port/host variables. If no explicit DB env is present, the previewed app may fall back to its own default dev DB (sqlite/local/test DB/etc.) instead of the Hermes managed Play DB.

## Diagnostic path

1. Compare UI and Play status/config:
   - `GET /api/core/projects/{projectId}/ui/status`
   - `GET /api/core/projects/{projectId}/play/status`
   - Check `configSource`, `workflowSource`, `playConfigPath`, `configPath`, and command/env sections.
2. Inspect source:
   - `api/play_pipeline.py`: `_prepare_start_runtime`, `_prepare_database_env`
   - `api/core_ui.py`: `_prepare_dev_runtime`, `_normalize_play_sourced_ui_config`
   - `api/managed_postgres.py`: `ensure_project_database_env`, `build_database_name`
3. If `.hermes/ui.json`, `.cloud-terminal/ui.json`, or `project_ui.json` contains `{ "source": "project_play.json" }`, remember that this maps Play build/start/inspect commands into UI Mode, but command mapping alone does not guarantee managed DB env parity.

## Fix pattern

When UI Mode is meant to mirror Play runtime semantics, make UI Mode apply the same project managed database env as Play before spawning the long-running dev/start runtime. The safest initial scope is Play-sourced UI configs, because the user has explicitly asked UI Mode to use Play behavior. Consider broader native UI config support only if product semantics say UI Mode should always get Hermes managed DB env.

Preserve Play's explicit-env override behavior: if the UI/Play config already provides a DB connection (`DATABASE_URL`, `DATASTORE_POSTGRES_URL`, `NAKAMA_DATABASE_URL`, `PG*`, `DB_*`, or `POSTGRES_*`), do not replace it silently.

## Verification ideas

- Unit/source test: UI Mode Play-sourced config applies managed DB aliases when no explicit DB env exists.
- Unit/source test: explicit DB env in UI/Play config wins over managed env.
- Runtime smoke: Play and UI Mode report/use the same project database name for the same project id.
- Regression: native Vite-only UI Mode still receives allocated `PORT`, `HOST`, and `HOSTNAME` as before.

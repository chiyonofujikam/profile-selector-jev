# Local development

See [README.md](../README.md) for the workflow and code map. Run commands below from the repository root.

## Startup

The standard launcher handles dependencies, database credentials, migrations, and both application servers:

```powershell
.\run.cmd
```

Use `.\run.cmd -SetupOnly` to prepare dependencies and the database without starting the application servers. Custom ports are supported with `-BackendPort 8000 -FrontendPort 5173`. Keep the launcher terminal open; Ctrl+C stops only application servers it started. Healthy existing services are reused. PostgreSQL stays running with its persistent volume.

Requirements: Python 3.13, uv, Node.js, and Docker Desktop with Linux containers. If a newly installed tool is missing from PATH, reopen the terminal.

After changing Jev settings in `.env`, stop the original launcher with Ctrl+C before restarting. Local startup applies `.env` over old terminal values. The launcher checks the provider and model before reusing an existing backend, and reports a mismatch instead of silently keeping an old mock server.

## Start each service manually

Create `.env` from [`.env-example`](../.env-example) only if `.env` does not already exist. For manual startup, set a nonempty `POSTGRES_PASSWORD` and uncomment `DATABASE_URL`, matching its credentials and port to `POSTGRES_*`.

```powershell
uv sync --project backend --locked
docker compose --env-file .env up -d postgres
docker compose --env-file .env ps
```

Wait for PostgreSQL to report healthy, then apply migrations and start the API:

```powershell
uv run --project backend alembic upgrade head
uv run --project backend uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open [the app](http://127.0.0.1:5173) or [API documentation](http://127.0.0.1:8000/docs). Vite proxies `/api` and `/health` to the local backend. Set `VITE_API_URL` only when using another API address. Only `VITE_*` settings are exposed to the frontend.

Backend dependencies and the Python environment live under `backend/`. Add a dependency with `uv add --project backend PACKAGE` and commit `backend/pyproject.toml` with `backend/uv.lock`. Frontend dependency changes belong in `frontend/package.json` and `frontend/package-lock.json`.

## Data

The database starts empty. Plain startup retains existing data. To load the supplied taxonomy and 12 fictional profiles explicitly, run `.\run.cmd -Demo`. Add `-SetupOnly` to load them without starting the servers.

With an existing prepared database, you can generate or import the demo separately:

```powershell
uv run --project backend python -m scripts.seed_demo --write-only
uv run --project backend python -m scripts.seed_demo --dry-run
uv run --project backend python -m scripts.seed_demo
```

The generated `local-data/demo.json` uses the normal import schema. Original catalog IDs and labels are retained. Tool-level associations and all profile facts are synthetic demo choices. Reloading updates those same records and retains unrelated data. The script does not add language filters or infer skills from taxonomy membership.

Prepare reviewed data using [the import schema](IMPLEMENTATION.md):

```powershell
uv run --project backend python -m scripts.convert_legacy --output local-data/catalog-review.json
uv run --project backend python -m scripts.import_data local-data/reviewed.json --validate-only
uv run --project backend python -m scripts.import_data local-data/reviewed.json --dry-run
uv run --project backend python -m scripts.import_data local-data/reviewed.json
```

Review the converted catalog and add applicable levels, aliases, and profiles before import. `--validate-only` checks structure without PostgreSQL. `--dry-run` validates database references and rolls back. A normal import runs in one transaction and updates records by stable ID. Keep private files under ignored `local-data/`.

## Tests

```powershell
uv run --project backend pytest
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:browser
```

Python tests cover selection, probability validation, matching, imports, and the launcher. Database tests skip unless `TEST_DATABASE_URL` points to a dedicated PostgreSQL database ending in `_test`. Frontend unit tests mock the API. Browser tests start Vite automatically and use isolated API fixtures with the installed Microsoft Edge browser; PostgreSQL and live Jev are not required. Screenshots are written under ignored `frontend/test-results/`.

For database integration tests, create a separate database once:

```powershell
docker compose --env-file .env exec postgres sh -c 'createdb -U "$POSTGRES_USER" jev_test'
```

In a separate PowerShell terminal, configure the test connection without displaying its credentials:

```powershell
$env:TEST_DATABASE_URL = uv run --project backend python -c "from sqlalchemy.engine import make_url; from backend.app.config import get_settings; print(make_url(get_settings().database_url).set(database='jev_test').render_as_string(hide_password=False))"
$env:DATABASE_URL = $env:TEST_DATABASE_URL
$env:DECISION_PROVIDER = 'mock'
uv run --project backend alembic upgrade head
uv run --project backend pytest
```

The fixtures roll back their records. Close this terminal after testing so its environment variables do not affect normal startup. Existing migrated test databases do not need `createdb` again.

## Database troubleshooting

Check [health](http://127.0.0.1:8000/health): `database.reachable` means the API can connect; `database.migrated` means the schema is current; `database.ready` requires both. Provider readiness is reported separately.

A healthy container does not verify the application's password. Docker's `POSTGRES_*` settings initialize an empty data directory; changing them later does not update existing roles. The launcher synchronizes local credentials. For manual setup, synchronize the existing role's password with `.env` while preserving the volume, then restart the API.

`docker compose --env-file .env down` stops PostgreSQL while retaining its named volume. Normal startup and restarts preserve imported records.

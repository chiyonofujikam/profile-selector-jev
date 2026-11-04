# Smart Filter Selector with Jev

A local engineering profile search dashboard. Describe a requirement, inspect and edit the catalog filters Jev proposes, and search candidates using explicit requirements and level constraints.

The application uses React/TypeScript/Vite, FastAPI, SQLAlchemy/Alembic, and PostgreSQL in Docker. The backend owns TypeSafe credentials and all provider calls. PostgreSQL is required; there is no SQLite fallback.

The initial database is intentionally empty. Candidate records, example states, reviewed level mappings, and representative evaluation data await the user's examples, as specified in [PROJECT_PLAN.md](PROJECT_PLAN.md). The preserved legacy taxonomy is reference material and is never seeded automatically.

## Quick start (Windows)

Start Docker Desktop, then run this from the repository root:

```powershell
.\run.cmd
```

The launcher uses `POSTGRES_PASSWORD` from the root `.env`, prepares the database with that password, applies migrations, and starts the frontend and backend. It installs locked dependencies when needed and keeps the Python environment in `backend/.venv`. Existing database records are preserved, and `DATABASE_URL` is aligned with the configured local PostgreSQL credentials.

Open `http://127.0.0.1:5173` for the dashboard or `http://127.0.0.1:8000/docs` for the API. Keep the launcher terminal open; Ctrl+C stops the frontend and backend processes it started. PostgreSQL stays running with its persistent volume. Healthy services that were already running are reused and are not stopped by the launcher.

For database/dependency setup without starting either application server:

```powershell
.\run.cmd -SetupOnly
```

The equivalent PowerShell entry point is `.\run.ps1`. Node.js, uv, and Docker Desktop must be installed; the launcher reports missing tools without changing unrelated services.

## Local setup

Install Python 3.13, [uv](https://docs.astral.sh/uv/getting-started/installation/), a current Node.js LTS release, and Docker Desktop with Linux containers. Run the commands below from the repository root. Backend dependencies live in `backend/pyproject.toml`; uv creates the Python environment at `backend/.venv`. Keep `backend/uv.lock` and `frontend/package-lock.json` in source control. The `--project backend` option selects this environment without requiring activation or a shell environment variable. Add backend dependencies with `uv add --project backend PACKAGE`.

1. Create `.env` from `.env-example` **only if `.env` does not already exist**. Review the database credentials and ports. The `DATABASE_URL` credentials and port must agree with the PostgreSQL settings.
2. Install backend dependencies, start the database, and apply migrations:

   ```powershell
   uv sync --project backend --locked
   docker compose --env-file .env up -d postgres
   docker compose --env-file .env ps
   uv run --project backend alembic upgrade head
   ```

   Wait for the `postgres` service to report healthy before running migrations. Inspect readiness with `docker compose --env-file .env exec postgres pg_isready`. Normal restarts retain records in the named volume. `docker compose --env-file .env down` stops the service without removing that volume.

3. Start the backend in one terminal:

   ```powershell
   uv run --project backend uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
   ```

4. Install and start the frontend in another terminal:

   ```powershell
   npm --prefix frontend ci
   npm --prefix frontend run dev
   ```

Open the URL Vite prints, normally `http://127.0.0.1:5173`. API documentation is at `http://127.0.0.1:8000/docs`; `GET /health` reports database and provider readiness separately. Vite reads the root environment file, exposing only `VITE_*` variables. Its development proxy sends `/api` and `/health` requests to the local backend. Build the frontend with `npm --prefix frontend run build`.

If a tool is installed but unavailable in a new terminal, add its installation directory to `PATH` or reopen the terminal. Do not replace an existing environment file or commit credentials.

A healthy PostgreSQL container does not verify the application's password. Docker's `POSTGRES_*` variables initialize an empty data directory; changing them later does not update roles in the persistent volume. If authentication fails, synchronize the existing role's password with `DATABASE_URL` and `POSTGRES_PASSWORD`, preserving the volume. Restart the API after `.env` changes because connection settings are loaded at startup. Check `/health`: `database.reachable` confirms the application can connect, `database.migrated` confirms the schema is current, and `database.ready` requires both.

## Decision modes

- `DECISION_PROVIDER=mock` uses deterministic catalog matching without an API key. The dashboard labels mock decisions and heuristic values. Mock mode still requires PostgreSQL and a reviewed catalog; it does not generate candidates or establish model accuracy.
- `DECISION_PROVIDER=jev` uses the official TypeSafe Python SDK. Configure the backend-only API key and model using `.env-example`. Provider errors are reported directly, with no silent switch to mock mode. Configured credentials do not establish that live access or domain quality has been verified.

The state text is submitted only when requested. Manual filter edits refresh candidate searches, and delayed analyses cannot overwrite newer edits. The response inspector retains every returned decision and distribution, including uncertain and rejected values. Candidate match scores, model probabilities, and model confidence have separate meanings.

## Reviewed data import

The import command accepts a versioned UTF-8 JSON envelope, validates IDs and references, and applies all changes in one PostgreSQL transaction. Repeating the same file updates the same IDs. Imported filters replace their alias/level associations; imported profiles replace their competency/language associations. Records omitted from the file remain unchanged.

```powershell
uv run --project backend python -m scripts.import_data local-data/reviewed.json --validate-only
uv run --project backend python -m scripts.import_data local-data/reviewed.json --dry-run
uv run --project backend python -m scripts.import_data local-data/reviewed.json
```

`--validate-only` checks JSON structure without contacting PostgreSQL. `--dry-run` checks the actual database references and constraints, then rolls back. Keep private input files under the ignored `local-data/` directory. The required schema and review procedure are documented in [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md).

To prepare the existing taxonomy for review without changing the database:

```powershell
uv run --project backend python -m scripts.convert_legacy --output local-data/catalog-review.json
```

This preserves the legacy category keys, text, and source paths, assigns deterministic IDs, and collapses only identical records at the same path. It does not create profiles, aliases, language records, or level associations. Review the generated file against the user's examples before importing it. Different paths with the same label remain different records. Conflicting duplicates cause conversion to fail.

## Verification and current boundaries

```powershell
uv run --project backend pytest
npm --prefix frontend test
npm --prefix frontend run build
```

Backend unit tests use isolated fixtures, never product seed data. PostgreSQL integration checks require Docker and migrated tables. Verify database migrations and record persistence using PostgreSQL before relying on a local release. Live TypeSafe verification requires configured credentials and network access; domain-quality evaluation requires the forthcoming reviewed examples. The current implementation does not include authentication, CV ingestion, automatic hiring decisions, or hosted deployment.

To run PostgreSQL integration tests, create a dedicated database once and use a separate terminal. These commands use the configured PostgreSQL user and derive the test connection URL from backend settings without displaying its credentials:

```powershell
docker compose --env-file .env exec postgres sh -c 'createdb -U "$POSTGRES_USER" jev_test'
$env:TEST_DATABASE_URL = uv run --project backend python -c "from sqlalchemy.engine import make_url; from backend.app.core.config import get_settings; print(make_url(get_settings().database_url).set(database='jev_test').render_as_string(hide_password=False))"
$env:DATABASE_URL = $env:TEST_DATABASE_URL
$env:DECISION_PROVIDER = 'mock'
uv run --project backend alembic upgrade head
uv run --project backend pytest
```

Tests require a PostgreSQL database name ending in `_test`; their fixture data is rolled back. Close that terminal afterward so the test-only environment variables do not affect normal startup. Reusing an existing migrated test database does not require `createdb` again.

Optional browser verification uses the locally installed Microsoft Edge browser. Start the API and Vite with the commands above, then run:

```powershell
npm --prefix frontend run test:browser
```

This read-only smoke test checks the initial empty workspace, response expansion, dialog focus, keyboard dismissal, desktop layout, and mobile navigation at `http://127.0.0.1:5173`. It expects an empty product database and writes ignored screenshots under `frontend/test-results/`. The frontend unit tests use isolated API fixtures to cover populated searches, delayed response protection, full probability inspection, and provider failure/retry without calling TypeSafe.

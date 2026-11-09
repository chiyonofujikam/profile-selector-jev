# Profile Selector with Jev

Describe the expertise you need. Jev turns your text into editable catalog filters; the app uses those filters to find matching profiles.

The interface has three steps:

1. **Describe** skills, languages, levels, and exclusions, then submit to Jev.
2. **Review** the suggested filters or select them manually.
3. **View matches** and inspect matched, unmet, and unknown requirements.

The response panel shows every returned decision and probability. Saved searches and analysis history are available from the header.

## Run locally

Install Python 3.13, uv, Node.js, and Docker Desktop. Start Docker Desktop, then **double-click `run.cmd`** or run from the repository root:

```powershell
.\run.cmd
```

The launcher installs locked dependencies, prepares PostgreSQL, applies migrations, and starts both servers. It asks for a local database password if one is missing. Existing `.env` values and database records are retained.

Keep the launcher window open while using the app. If startup fails, the window stays open so you can read the error. Run `.\run.cmd --help` for setup-only and custom-port options.

- App: [localhost:5173](http://127.0.0.1:5173)
- API docs: [localhost:8000/docs](http://127.0.0.1:8000/docs)
- Ctrl+C stops the application servers started by the launcher. PostgreSQL keeps its data.

To load the supplied filters and fictional demo profiles, run:

```powershell
.\run.cmd -Demo
```

This imports the complete taxonomy from `data/values_with_context.json`, tool levels from `data/levels.json`, 12 synthetic profiles, and five sample requirements. Start a new search and try:

| Requirement | Expected matches in mock mode |
| --- | --- |
| `Railway and DOORS` | 4 |
| `DOORS advanced or higher` | 3 |
| `Railway and DOORS, excluding Metro` | 3 |
| `Energy and Python` | 2 |
| `Railway and CATIA` | 1 |

Demo data works with either decision provider; loading it does not change your Jev settings. Repeating `-Demo` updates the same demo IDs and catalog records, without deleting unrelated profiles. It restores the generated demo records, so use your own IDs for custom profiles. The generated import file is `local-data/demo.json`; edit the fictional profile definitions in `scripts/seed_demo.py` to change future demo loads.

Plain `run.cmd` retains your existing data and does not seed anything. For your own catalog and profiles, use [the data guide](docs/IMPLEMENTATION.md).

For manual startup, custom ports, database troubleshooting, and integration-test setup, see [development instructions](docs/DEVELOPMENT.md).

## Configure Jev

Settings live in the root `.env`. A small reference is provided in [`.env-example`](.env-example); keep your existing `.env` if you already have one.

```dotenv
DECISION_PROVIDER=jev
TYPESAFE_API_KEY=your-backend-api-key
JEV_MODEL=jev-latest
```

Restart the backend after changing settings. The TypeSafe SDK calls `system_one` with typed **Noul** questions for relevance, exclusion, and required status, and **Choice** questions for levels and comparisons. The API key stays on the backend.

`DECISION_PROVIDER=mock` runs deterministic catalog-name and alias rules without a key. Demo values are not model probabilities. Provider failures in live mode are reported to the user.

## Read the code

Start with these two flows:

```text
Frontend: App → useSearch → POST /api/v1/analyses → editable filters
Backend:  analysis → decisions → retrieval → Jev → selection policy
Matches:  edited filters → POST /api/v1/profiles/search → matching
```

| File | Responsibility |
| --- | --- |
| `frontend/src/App.tsx` | Page layout and requirement input. |
| `frontend/src/hooks/useSearch.ts` | Search state, explicit submission, retry IDs, and protection for newer edits. |
| `frontend/src/components/FiltersPanel.tsx` | Browse the catalog and edit filters. |
| `frontend/src/components/CandidatesPanel.tsx` | Fetch matches and show profile evidence. |
| `frontend/src/components/ResponsePanel.tsx` | Inspect and export decisions and provider JSON. |
| `frontend/src/components/SearchLibrary.tsx` | Save, restore, and delete searches; restore analyses. |
| `backend/app/api/routes.py` | HTTP endpoints. |
| `backend/app/schemas/__init__.py` | API request and response types. |
| `backend/app/services/analysis.py` | Reuse request IDs and store completed analyses. |
| `backend/app/services/decisions.py` | Build typed questions, validate answers, and apply thresholds. |
| `backend/app/services/jev.py` | TypeSafe SDK call and provider error handling. |
| `backend/app/services/mock.py` | Local demo rules. |
| `backend/app/services/retrieval.py` | Shortlist catalog filters from names, aliases, and text overlap. |
| `backend/app/services/matching.py` | Shared filter validation and profile matching. |
| `backend/app/db/` | Database models, sessions, and record serialization. |
| `scripts/seed_demo.py` | Build and import the supplied catalog with fictional profiles. |

Only submitting the requirement calls Jev. Editing filters refreshes matches automatically. A delayed analysis cannot overwrite newer edits, and retrying unchanged input reuses its request ID.

Required filters determine eligibility; preferred filters affect ranking. Exclusions always apply. A level belongs to one filter and can mean exact or minimum. Missing evidence stays unknown. Match scores, Noul probabilities, and Choice confidence are different values.

## Check changes

```powershell
uv run --project backend pytest
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:browser
```

Browser tests start Vite automatically and use isolated API fixtures in Microsoft Edge. They do not call Jev or change product data. PostgreSQL integration tests require a separate database ending in `_test`; see [development instructions](docs/DEVELOPMENT.md).

Live Jev access and domain accuracy require configured credentials and reviewed examples. Synthetic demo profiles are for exploring the workflow. The app currently provides local search, without authentication or hosted deployment.

# Profile Selector

Type the skills you need, review the selected filters, and see matching profiles.

## Start the app

Install Python 3.13, uv, Node.js, and Docker Desktop. Start Docker Desktop, then run:

```powershell
.\run.cmd
```

The launcher prepares the database and starts the app. It asks for a database password if needed.

Open [localhost:5173](http://127.0.0.1:5173). Keep the launcher window open. Press Ctrl+C to stop the app.

## Try sample profiles

```powershell
.\run.cmd -Demo
```

This loads 12 fictional profiles and the supplied filters. Try `Railway and DOORS`.

Normal startup keeps existing data. Running `-Demo` again updates the same sample records.

## Choose demo or Jev

Edit the root `.env` file. For local rules without an API key:

```dotenv
DECISION_PROVIDER=mock
```

For live Jev:

```dotenv
DECISION_PROVIDER=jev
TYPESAFE_API_KEY=your-api-key
```

Restart the app after changing settings. Keep the key in `.env`; it stays on the backend. See [`.env-example`](.env-example) for the basic settings.

## Understand the code

There are three main folders:

- `frontend/src`: the page, buttons, and filters.
- `backend/app`: the API, Jev calls, and profile matching.
- `scripts`: starting the app and loading data.

Start with these files:

| File | What it does |
| --- | --- |
| `frontend/src/App.tsx` | Shows the page. |
| `frontend/src/useSearch.ts` | Holds the search and submits the text. |
| `frontend/src/api.ts` | Sends requests to the backend. |
| `backend/app/routes.py` | Receives those requests. |
| `backend/app/selection.py` | Turns the text into selected filters. |
| `backend/app/matching.py` | Finds profiles that match the filters. |

`jev.py` calls Jev; `demo.py` supplies local rules. `models.py` defines the database tables, `schemas.py` defines API fields, and `config.py` reads `.env`.

Only submitting text calls Jev. Editing filters refreshes profile matches. Required filters decide who appears; preferred filters affect the score. Missing profile information stays unknown.

## Check your changes

```powershell
uv run --project backend pytest
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:browser
```

For other setup options, see [development](docs/DEVELOPMENT.md). To load your own profiles, see [the data guide](docs/IMPLEMENTATION.md).

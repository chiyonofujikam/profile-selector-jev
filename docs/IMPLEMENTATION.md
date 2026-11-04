# Data preparation and implementation contracts

The product's demonstration data remains pending user examples. No candidate dataset, example states, or expected domain selections are installed by setup or migration. Test fixtures remain isolated in tests.

## Import envelope

Run Python commands from the repository root with `uv run --project backend`; dependencies and the lockfile live in `backend/pyproject.toml` and `backend/uv.lock`, and the environment is `backend/.venv`.

`uv run --project backend python -m scripts.import_data FILE` accepts these top-level fields. Unknown fields are rejected to catch misspellings.

| Field | Type | Meaning |
| --- | --- | --- |
| `version` | integer `1` | Import schema version. |
| `provenance` | nonempty string | Origin and review/synthetic status of the supplied records. Stored on filters and profiles. |
| `categories` | array | Category definitions; defaults to empty. |
| `levels` | array | Explicit level definitions; defaults to empty. |
| `filters` | array | Reviewed catalog records; defaults to empty. |
| `profiles` | array | Reviewed candidate records; defaults to empty. |
| `examples` | array | Reviewed state shortcuts; defaults to empty. |
| `review_notes` | array of strings | Preparation notes; accepted but not interpreted as application instructions. |

All IDs are nonempty strings of at most 128 characters. IDs must be unique within each entity list; category keys must also be unique. An input file may refer to records already in PostgreSQL. Missing references cause the entire transaction to roll back. Repeated import with the same IDs creates no duplicate records. Stable IDs are independent of display labels.

The following empty envelope is valid and does not insert any product data:

```json
{
  "version": 1,
  "provenance": "Awaiting reviewed user examples",
  "categories": [],
  "levels": [],
  "filters": [],
  "profiles": [],
  "examples": []
}
```

### Category

Required: `id`, `key`, `label`. Optional: `description` (default empty string), `order` (nonnegative integer, default `0`). Legacy category keys retain their original spelling, including `environnement-domain` and `environnement-context`.

### Level

Required: `id`, `dimension`, `label`. Optional: `rank` (nonnegative integer or `null`). Use an explicit common dimension such as `language-level`, `experience`, or `tool-expertise` for levels that belong together. An unordered label has a null rank and cannot support a minimum constraint. Ranks must express a reviewed ordering; years of experience do not imply seniority.

### Filter

Required: `id`, `category_id`, `label`. Optional: `description`, `subcategory`, `active` (default `true`), `legacy_path`, `aliases` (default `[]`), and `level_ids` (default `[]`). Each alias is either a string or an object with `text` and `language` (default `und`). Duplicate aliases and duplicate level IDs on one filter are rejected.

Every `level_id` must identify an imported or existing level. Imported filter/level links allow exact constraints, and allow minimum constraints only for ranked levels. The import replaces the specified filter's previous aliases and allowed levels; it leaves other filters unchanged. Do not attach every level to every filter. A tool may support tool-expertise levels; a language may support language-level definitions. Filters without reviewed levels use an empty `level_ids` list.

### Profile

Required: `id`, `display_name`, `title`. Optional: `summary`, `experience_years` (finite number from 0 to 100, or `null`), `competencies` (default `[]`), `languages` (default `[]`). Both association lists contain objects with a required `filter_id`, optional `level_id` (default `null`), and optional `present` boolean (default `true`). Use `present: false` only for confirmed absence; absent facts cannot carry a level. A filter may appear only once across the two lists. A language association's level must use the `language-level` dimension.

Every referenced filter must already exist or appear in the same import. A non-null level must be explicitly allowed by that filter. Importing a profile replaces its existing competency and language records. Missing competency information is unknown, not proof of absence; missing levels remain unknown. The source provenance must make any synthetic candidate records explicit.

### Example

Required: `id`, `label`, `state_text` (1–10,000 characters). Optional: `locale`, one of `en`, `fr`, or `es` (default `en`). Examples must come from the user's reviewed scenarios; the converter does not manufacture them.

## Legacy review

The converter reads `data/values_with_context.json` unless `--source` selects another file. It accepts only the five documented legacy category keys. Flat lists and nested named groups are supported. Stable IDs hash the complete category/group/label path; matching names under different paths do not merge. Source SHA-256 and original path are retained. Identical duplicate entries at the same path collapse; conflicting duplicate descriptions fail with a review error.

The converter preserves Unicode and punctuation rather than guessing encoding repairs. Review known defects against the actual source text, and record confirmed corrections. Review descriptive text for overbroad relevance hints. Taxonomy membership is organizational context and does not prove candidate competency. Aliases, language filters, and applicable levels must be reviewed explicitly; the legacy global level lists cannot establish those associations.

Suggested sequence:

1. Convert the preserved taxonomy into an ignored review file.
2. Review it against the supplied examples; remove incorrect definitions and add explicit aliases and allowed level IDs where justified.
3. Prepare candidate and scenario records from those examples, retaining provenance.
4. Run structural validation, then a PostgreSQL dry run.
5. Import the reviewed file, rerun it to check repeatability, and evaluate the actual expected selections.

## Matching and provider limits

The versioned `/api/v1` routes are the canonical API. The legacy `/api/filter/analyze-query` route is not exposed: its global-level and confidence response shape has no agreed lossless mapping to per-filter levels, Noul probabilities, and Choice confidence. The plan makes a compatibility adapter conditional on that mapping. Legacy catalog keys remain preserved by the explicit converter. Imported example records have an API contract, while dashboard example shortcuts remain deferred until the user's reviewed scenarios arrive.

Search requests explicitly specify AND/OR grouping. Mandatory conditions and exclusions govern eligibility; preferred conditions contribute to ranking. Level constraints distinguish exact from minimum operators. Missing evidence remains visible as unknown. Neither profile matching nor taxonomy membership implies unrecorded competencies.

The mock decision path validates orchestration and UI behavior with deterministic catalog evidence. Its values are heuristic, not calibrated Jev probabilities. Live Jev uses typed Noul/Choice questions through the official SDK; selection thresholds are application policy. Every returned question and option probability is retained alongside policy decisions, with Noul probability separate from Choice confidence. Live credentials, latency, multilingual quality, precision/recall, and held-out domain quality require separate verification.

PostgreSQL migration and restart-persistence checks require a working Docker engine. The application does not substitute an in-memory database or seed invented examples when that engine is unavailable.

## Verification record

Local verification on 4 November 2026 used Python 3.13.9, PostgreSQL 17.11 in Docker, FastAPI, React 19, and Vite 8. The final combined Python run passed 58 checks with PostgreSQL integrations enabled; frontend workflows passed 3 tests, the production frontend build passed, and the Edge browser smoke test passed 1 test.

The checks have exercised:

- Locked Python dependency installation, Alembic migrations, and the FastAPI application against PostgreSQL in Docker.
- Named-volume persistence: a committed saved-search marker and migration revision `5be32c366157` survived PostgreSQL container recreation. The marker was removed from the dedicated test database afterward.
- PostgreSQL API contracts, complete provider-response JSONB persistence, request-ID idempotency, saved-search operations, matching/level semantics, and transactional import repeatability and rollback. Fixtures use a dedicated `_test` database and are rolled back.
- Three frontend workflow tests covering state submission and candidate refresh, level/filter edits during delayed analyses, full probability inspection without additional provider calls, and provider failure/retry with the same request ID.
- A production frontend build, plus Microsoft Edge browser checks of desktop/mobile layout, empty states, response-panel controls, keyboard dialog dismissal, modal focus, and mobile navigation.

The browser smoke test reads the real local API and expects the intentionally empty product database. Populated workflow tests use isolated fixtures. These checks establish application behavior; they do not establish live Jev access or domain-quality results. No candidate dataset or user example scenarios have been synthesized. Live provider access has not been verified. Representative multilingual/domain evaluation awaits the reviewed examples described in the project plan.

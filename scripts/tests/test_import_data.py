"""Isolated import fixtures; never loaded as product demonstration data."""

import os

import pytest
from pydantic import ValidationError

from scripts.convert_legacy import convert_catalog
from scripts.import_data import ImportPayload, import_payload


def test_converter_preserves_identifiers_and_separates_equal_labels_by_path():
    source = {
        "tool": [{"name": "C++", "description": "Literal punctuation"}],
        "domain-speciality": {
            "One": [{"name": "C++", "description": "First path"}],
            "Two": [{"name": "C++", "description": "Second path"}],
        },
    }
    first = convert_catalog(source, "test fixture")
    second = convert_catalog(source, "test fixture")
    assert first == second
    assert {item["label"] for item in first["filters"]} == {"C++"}
    assert len({item["id"] for item in first["filters"]}) == 3
    assert all(item["level_ids"] == [] for item in first["filters"])
    assert first["profiles"] == first["examples"] == []
    ImportPayload.model_validate(first)


def test_converter_collapses_identical_duplicates_but_rejects_conflicts():
    record = {"name": "EN50128", "description": "Preserved identifier"}
    converted = convert_catalog({"tool": [record, record]}, "test fixture")
    assert len(converted["filters"]) == 1
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        convert_catalog({"tool": [record, {**record, "description": "Conflicting"}]}, "test fixture")


@pytest.mark.parametrize("field,records", [
    ("categories", [{"id": "same", "key": "one", "label": "One"},
                    {"id": "same", "key": "two", "label": "Two"}]),
    ("levels", [{"id": "same", "dimension": "test", "label": "One"},
                {"id": "same", "dimension": "test", "label": "Two"}]),
])
def test_import_rejects_duplicate_stable_ids(field, records):
    with pytest.raises(ValidationError, match="Duplicate IDs"):
        ImportPayload.model_validate({"version": 1, "provenance": "isolated test", field: records})


def test_import_rejects_unrecognized_fields_and_nonfinite_experience():
    with pytest.raises(ValidationError):
        ImportPayload.model_validate({"version": 1, "provenance": "test", "profiels": []})
    with pytest.raises(ValidationError):
        ImportPayload.model_validate({"version": 1, "provenance": "test", "profiles": [{
            "id": "fixture", "display_name": "Fixture", "title": "Test only", "experience_years": float("nan"),
        }]})


def test_import_rejects_conflicting_profile_facts():
    with pytest.raises(ValidationError, match="appears more than once"):
        ImportPayload.model_validate({"version": 1, "provenance": "test", "profiles": [{
            "id": "fixture", "display_name": "Fixture", "title": "Test only",
            "competencies": [{"filter_id": "shared"}], "languages": [{"filter_id": "shared"}],
        }]})


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires migrated PostgreSQL TEST_DATABASE_URL")
def test_postgres_import_is_idempotent_and_transactional():
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session

    from backend.app.db.models import Category, Filter, FilterAlias, FilterLevel, Profile, ProfileCompetency

    database_url = os.environ["TEST_DATABASE_URL"]
    parsed = make_url(database_url)
    assert parsed.get_backend_name() == "postgresql", "Integration tests require PostgreSQL."
    assert parsed.database and parsed.database.endswith("_test"), "Use a dedicated database with an _test suffix."
    engine = create_engine(database_url)
    payload = ImportPayload.model_validate({
        "version": 1, "provenance": "Automated isolated fixture; not product data",
        "categories": [{"id": "import-test-category", "key": "import-test", "label": "Import fixture"}],
        "levels": [{"id": "import-test-level", "dimension": "tool-expertise", "label": "Fixture level", "rank": 1}],
        "filters": [{"id": "import-test-filter", "category_id": "import-test-category", "label": "Fixture filter",
                     "aliases": ["Fixture alias"], "level_ids": ["import-test-level"]}],
        "profiles": [{"id": "import-test-profile", "display_name": "Isolated fixture", "title": "Test only",
                      "competencies": [{"filter_id": "import-test-filter", "level_id": "import-test-level"}]}],
    })
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            session = Session(bind=connection, join_transaction_mode="create_savepoint")
            try:
                for _ in range(2):
                    import_payload(session, payload)
                assert session.scalar(select(func.count()).select_from(Category).where(Category.id == "import-test-category")) == 1
                assert session.scalar(select(func.count()).select_from(Filter).where(Filter.id == "import-test-filter")) == 1
                assert session.scalar(select(func.count()).select_from(FilterAlias).where(FilterAlias.filter_id == "import-test-filter")) == 1
                assert session.scalar(select(func.count()).select_from(FilterLevel).where(FilterLevel.filter_id == "import-test-filter")) == 1
                assert session.scalar(select(func.count()).select_from(Profile).where(Profile.id == "import-test-profile")) == 1
                assert session.scalar(select(func.count()).select_from(ProfileCompetency).where(ProfileCompetency.profile_id == "import-test-profile")) == 1
                # A failing import must roll back its earlier writes as one unit.
                invalid = ImportPayload.model_validate({"version": 1, "provenance": "isolated fixture",
                    "categories": [{"id": "import-test-rollback", "key": "import-test-rollback", "label": "Rollback fixture"}],
                    "filters": [{"id": "import-test-bad", "category_id": "missing-category", "label": "Invalid fixture"}]})
                with pytest.raises(ValueError, match="Unknown category"):
                    with session.begin_nested():
                        import_payload(session, invalid)
                assert session.get(Category, "import-test-rollback") is None
            finally:
                session.close()
                transaction.rollback()
    finally:
        engine.dispose()

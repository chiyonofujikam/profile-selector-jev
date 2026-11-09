"""Exercise the supplied demo catalog through selection, matching, and import."""

import json
import os

import pytest

from backend.app.selection import analyze
from backend.app.matching import search_profiles
from scripts.convert_legacy import convert_catalog
from scripts.import_data import ImportPayload, import_payload
from scripts.seed_demo import ROOT, build_demo_data


def test_demo_preserves_the_complete_source_catalog_and_stable_ids():
    source_path = ROOT / "data/values_with_context.json"
    original_bytes = source_path.read_bytes()
    source = convert_catalog(json.loads(original_bytes.decode("utf-8-sig")), "source reference")
    payload = build_demo_data()
    assert payload == build_demo_data()
    assert source_path.read_bytes() == original_bytes
    assert {item["id"] for item in payload["filters"]} == {item["id"] for item in source["filters"]}
    for actual, original in zip(payload["filters"], source["filters"], strict=True):
        for key in ("id", "category_id", "label", "description", "subcategory", "legacy_path"):
            assert actual[key] == original[key]


def test_every_demo_profile_fact_and_level_has_a_catalog_reference():
    payload = ImportPayload.model_validate(build_demo_data())
    by_id = {item.id: item for item in payload.filters}
    levels = {item.id for item in payload.levels}
    for profile in payload.profiles:
        assert "(Demo)" in profile.display_name
        for fact in profile.competencies + profile.languages:
            assert fact.filter_id in by_id
            if fact.level_id:
                assert fact.level_id in levels
                assert fact.level_id in by_id[fact.filter_id].level_ids


@pytest.mark.parametrize("query,expected", [
    ("Railway and DOORS", {"demo-alex", "demo-sam", "demo-jordan", "demo-robin"}),
    ("DOORS advanced or higher", {"demo-alex", "demo-jordan", "demo-avery"}),
    ("Railway and DOORS, excluding Metro", {"demo-alex", "demo-jordan", "demo-robin"}),
    ("Energy and Python", {"demo-riley", "demo-drew"}),
    ("Railway and CATIA", {"demo-morgan"}),
])
def test_demo_queries_select_filters_and_find_expected_profiles(query, expected):
    payload = build_demo_data()
    levels = {item["id"]: item for item in payload["levels"]}
    catalog = [{**item, "levels": [levels[level_id] for level_id in item["level_ids"]]}
               for item in payload["filters"]]
    result = analyze(query, catalog, [], provider="mock")
    assert result["filters"]
    matches = search_profiles(payload["profiles"], catalog, result["filters"])
    assert {item["profile"]["id"] for item in matches} == expected


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires isolated PostgreSQL TEST_DATABASE_URL")
def test_demo_import_is_repeatable_and_preserves_unrelated_profiles():
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from backend.app import models as db

    url = make_url(os.environ["TEST_DATABASE_URL"])
    assert url.get_backend_name() == "postgresql" and (url.database or "").endswith("_test")
    engine = create_engine(url)
    db.Base.metadata.create_all(engine)
    payload = ImportPayload.model_validate(build_demo_data())
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            session = Session(bind=connection, join_transaction_mode="create_savepoint")
            try:
                session.add(db.Profile(id="fixture-demo-untouched", display_name="Untouched fixture", title="Test only"))
                session.flush()
                for _ in range(2):
                    counts = import_payload(session, payload)
                assert counts["profiles"] == len(payload.profiles)
                assert session.scalar(select(func.count()).select_from(db.Profile).where(
                    db.Profile.id.in_([item.id for item in payload.profiles]))) == len(payload.profiles)
                assert session.scalar(select(func.count()).select_from(db.Filter).where(
                    db.Filter.id.in_([item.id for item in payload.filters]))) == len(payload.filters)
                assert session.get(db.Profile, "fixture-demo-untouched").display_name == "Untouched fixture"
            finally:
                session.close()
                transaction.rollback()
    finally:
        engine.dispose()

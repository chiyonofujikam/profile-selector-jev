"""PostgreSQL API contracts; fixtures remain inside rolled-back test transactions."""
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.db import models as db
from backend.app.db.session import get_db
from backend.app.main import app


@pytest.fixture
def api():
    configured = os.environ.get("TEST_DATABASE_URL")
    if not configured:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated PostgreSQL database ending in _test")
    url = make_url(configured)
    if url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_test"):
        pytest.fail("API tests require an isolated PostgreSQL database ending in _test")
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    db.Base.metadata.create_all(engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    session.add_all([db.Category(id="fixture-tools", key="fixture-tools", label="Fixture tools"),
                     db.Category(id="fixture-languages", key="fixture-languages", label="Fixture languages"),
                     db.Level(id="fixture-b2", dimension="language-level", label="B2", rank=4),
                     db.Level(id="fixture-c1", dimension="language-level", label="C1", rank=5)])
    session.flush()
    session.add_all([db.Filter(id="fixture-doors", category_id="fixture-tools", label="DOORS", description="Requirements management"),
                     db.Filter(id="fixture-english", category_id="fixture-languages", label="English", description="English language")])
    session.flush()
    session.add_all([db.FilterLevel(filter_id="fixture-english", level_id="fixture-b2"),
                     db.FilterLevel(filter_id="fixture-english", level_id="fixture-c1"),
                     db.Profile(id="fixture-profile", display_name="Isolated test fixture", title="Test engineer", summary="Automated test fixture")])
    session.flush()
    session.add_all([db.ProfileCompetency(profile_id="fixture-profile", filter_id="fixture-doors"),
                     db.ProfileLanguage(profile_id="fixture-profile", filter_id="fixture-english", level_id="fixture-c1")])
    session.flush()
    app.dependency_overrides[get_db] = lambda: session
    try:
        with TestClient(app) as client:
            yield client, session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def test_analysis_persists_complete_response_and_retry_is_idempotent(api):
    client, session = api
    payload = {"state_text": "DOORS and English B2 or higher", "current_filters": [], "client_revision": 4, "request_id": str(uuid4())}
    first = client.post("/api/v1/analyses", json=payload)
    assert first.status_code == 200, first.text
    value = first.json()
    assert value["client_revision"] == 4
    assert value["provider"] == "mock"
    assert value["decisions"]
    assert value["provider_response"]["value_kind"] == "deterministic_rule"
    assert all(item["probability"] is None for item in value["decisions"])
    assert {item["filter_id"] for item in value["filters"]} == {"fixture-doors", "fixture-english"}
    assert next(item for item in value["filters"] if item["filter_id"] == "fixture-doors")["level_id"] is None
    repeated = client.post("/api/v1/analyses", json=payload)
    assert repeated.status_code == 200
    assert repeated.json()["id"] == value["id"]
    assert session.scalar(select(func.count()).select_from(db.Analysis).where(db.Analysis.id == value["id"])) == 1
    assert session.get(db.ProviderResponse, value["id"]).response == value["provider_response"]
    assert session.scalar(select(func.count()).select_from(db.AnalysisDecision).where(db.AnalysisDecision.analysis_id == value["id"])) == len(value["decisions"])
    assert client.get(f"/api/v1/analyses/{value['id']}").json() == value
    assert any(item["id"] == value["id"] for item in client.get("/api/v1/analyses").json()["items"])
    conflict = client.post("/api/v1/analyses", json={**payload, "state_text": "Different state"})
    assert conflict.status_code == 409


def test_saved_search_crud_and_level_validation(api):
    client, _ = api
    filters = [{"filter_id": "fixture-english", "level_id": "fixture-b2", "operator": "minimum"}]
    created = client.post("/api/v1/saved-searches", json={"label": "Language search", "query": "English B2 or higher", "filters": filters})
    assert created.status_code == 201
    search_id = created.json()["id"]
    assert client.patch(f"/api/v1/saved-searches/{search_id}", json={"label": "Updated name"}).json()["label"] == "Updated name"
    assert any(item["id"] == search_id for item in client.get("/api/v1/saved-searches").json()["items"])
    assert client.patch(f"/api/v1/saved-searches/{search_id}", json={"label": None}).status_code == 422
    invalid = [{"filter_id": "fixture-doors", "level_id": "fixture-b2"}]
    assert client.post("/api/v1/saved-searches", json={"label": "Invalid", "filters": invalid}).status_code == 422
    assert client.delete(f"/api/v1/saved-searches/{search_id}").status_code == 204
    assert client.delete(f"/api/v1/saved-searches/{search_id}").status_code == 404


def test_catalog_filters_and_search_preserve_level_semantics(api):
    client, _ = api
    public_config = client.get("/api/v1/config")
    assert public_config.status_code == 200
    assert public_config.json()["provider"] == "mock"
    assert "typesafe_api_key" not in public_config.json()
    readiness = client.get("/health")
    assert readiness.status_code == 200
    assert isinstance(readiness.json()["database"]["migrated"], bool)
    assert isinstance(client.get("/api/v1/examples").json(), list)
    assert client.get("/api/v1/filters?q=DOORS").json()["total"] == 1
    assert client.get("/api/v1/filters?ids=fixture-english").json()["items"][0]["id"] == "fixture-english"
    assert client.get("/api/v1/filters?page_size=101").status_code == 422
    assert isinstance(client.get("/api/v1/categories").json(), list)
    minimum = {"filters": [{"filter_id": "fixture-english", "level_id": "fixture-b2", "operator": "minimum"}], "grouping": "and"}
    result = client.post("/api/v1/profiles/search", json=minimum)
    assert result.status_code == 200, result.text
    assert result.json()["total"] == 1
    assert result.json()["items"][0]["score"] == 100
    exact = {**minimum, "filters": [{**minimum["filters"][0], "operator": "exact"}]}
    assert client.post("/api/v1/profiles/search", json=exact).json()["total"] == 0
    assert client.post("/api/v1/profiles/search", json={"filters": [{"filter_id": "unregistered"}]}).status_code == 422
    assert client.get("/api/v1/profiles/fixture-profile").status_code == 200


def test_blank_state_and_provider_errors_are_distinct(api, monkeypatch):
    from backend.app.services import decisions
    client, _ = api
    assert client.post("/api/v1/analyses", json={"state_text": "  "}).status_code == 422
    def failure(*args, **kwargs):
        raise decisions.ProviderError("provider_timeout", "Jev request timed out. Please retry.", 504)
    monkeypatch.setattr(decisions, "analyze", failure)
    result = client.post("/api/v1/analyses", json={"state_text": "DOORS"})
    assert result.status_code == 504
    assert result.json()["error"]["code"] == "provider_timeout"
    assert result.json()["error"]["request_id"]

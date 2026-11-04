import hashlib
import json
import logging
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db import models as db
from backend.app.db.session import get_db
from backend.app.schemas import (
    AnalysisRequest, AnalysisResponse, CatalogFilter, Category, ExampleResponse,
    Page, Profile, PublicConfig, SavedSearchCreate, SavedSearchPatch,
    SavedSearchResponse, SearchRequest, SearchResponse,
)

router = APIRouter(prefix="/api/v1")
POLICY_VERSION = "selection-v1"


def serialize_filter(item: db.Filter) -> dict:
    return {
        "id": item.id, "category_id": item.category_id, "label": item.label,
        "description": item.description, "subcategory": item.subcategory,
        "aliases": [alias.text for alias in item.aliases],
        "levels": [dict(id=link.level.id, label=link.level.label, dimension=link.level.dimension,
                        rank=link.level.rank, supports_exact=link.supports_exact,
                        supports_minimum=link.supports_minimum) for link in item.level_links],
    }


def catalog(session: Session) -> list[dict]:
    return [serialize_filter(item) for item in session.scalars(select(db.Filter).where(db.Filter.active).order_by(db.Filter.id))]


def serialize_profile(item: db.Profile) -> dict:
    return {"id": item.id, "display_name": item.display_name, "title": item.title,
            "summary": item.summary, "experience_years": item.experience_years,
            "competencies": [{"filter_id": fact.filter_id, "level_id": fact.level_id, "present": fact.present} for fact in item.competencies],
            "languages": [{"filter_id": fact.filter_id, "level_id": fact.level_id, "present": fact.present} for fact in item.languages]}


def validate_filters(filters, items):
    by_id = {item["id"]: item for item in items}
    seen = set()
    for constraint in filters:
        value = constraint.model_dump() if hasattr(constraint, "model_dump") else constraint
        filter_id = value["filter_id"]
        if filter_id in seen:
            raise HTTPException(422, "A filter may appear only once; resolve contradictory selections")
        seen.add(filter_id)
        item = by_id.get(filter_id)
        if item is None:
            raise HTTPException(422, f"Unknown or inactive filter: {filter_id}")
        if value.get("level_id"):
            level = next((level for level in item["levels"] if level["id"] == value["level_id"]), None)
            if level is None:
                raise HTTPException(422, f"Level is not applicable to filter: {filter_id}")
            operator = value.get("operator", "exact")
            if operator == "minimum" and (level["rank"] is None or not level["supports_minimum"]):
                raise HTTPException(422, f"Minimum level is not supported for: {filter_id}")
            if operator == "exact" and not level["supports_exact"]:
                raise HTTPException(422, f"Exact level is not supported for: {filter_id}")


def paginate(items, page, page_size):
    return {"items": items[(page - 1) * page_size:page * page_size], "total": len(items), "page": page, "page_size": page_size}


@router.get("/config", response_model=PublicConfig)
def config():
    settings = get_settings()
    return {"provider": settings.decision_provider, "model": settings.jev_model if settings.decision_provider == "jev" else "deterministic-demo",
            "provider_ready": settings.provider_ready, "supported_locales": ["en", "fr", "es"],
            "policy_version": POLICY_VERSION, "select_threshold": settings.select_threshold,
            "reject_threshold": settings.reject_threshold, "max_state_length": 12000}


@router.get("/categories", response_model=list[Category])
def categories(session: Session = Depends(get_db)):
    counts = dict(session.execute(select(db.Filter.category_id, func.count()).where(db.Filter.active).group_by(db.Filter.category_id)).all())
    return [dict(id=item.id, key=item.key, label=item.label, description=item.description, count=counts.get(item.id, 0))
            for item in session.scalars(select(db.Category).order_by(db.Category.order, db.Category.label))]


@router.get("/filters", response_model=Page[CatalogFilter])
def filters(q: str = Query(default="", max_length=240), category_id: str | None = None,
            ids: str | None = Query(default=None, max_length=32200),
            page: int = Query(default=1, ge=1, le=100000), page_size: int = Query(default=100, ge=1, le=100),
            session: Session = Depends(get_db)):
    statement = select(db.Filter).where(db.Filter.active)
    if ids is not None:
        identifiers = [value for value in ids.split(",") if value]
        if len(identifiers) > 200 or any(len(value) > 160 for value in identifiers):
            raise HTTPException(422, "At most 200 filter IDs may be requested")
        statement = statement.where(db.Filter.id.in_(identifiers))
    if category_id:
        statement = statement.where(db.Filter.category_id == category_id)
    if q.strip():
        # Escape SQL wildcard characters so catalog search follows the literal user text.
        term = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        alias_match = select(db.FilterAlias.filter_id).where(db.FilterAlias.text.ilike(term, escape="\\"))
        statement = statement.where(or_(db.Filter.label.ilike(term, escape="\\"), db.Filter.description.ilike(term, escape="\\"), db.Filter.id.in_(alias_match)))
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    items = session.scalars(statement.order_by(db.Filter.label, db.Filter.id).offset((page - 1) * page_size).limit(page_size))
    return {"items": [serialize_filter(item) for item in items], "total": total, "page": page, "page_size": page_size}


@router.get("/examples", response_model=list[ExampleResponse])
def examples(session: Session = Depends(get_db)):
    return [dict(id=item.id, label=item.label, state_text=item.state_text, locale=item.locale)
            for item in session.scalars(select(db.Example).order_by(db.Example.label))]


@router.post("/analyses", response_model=AnalysisResponse)
def create_analysis(payload: AnalysisRequest, session: Session = Depends(get_db)):
    from backend.app.services.decisions import analyze

    settings = get_settings()
    request_id = payload.request_id or str(uuid4())
    request_data = payload.model_dump(exclude={"request_id"})
    request_hash = hashlib.sha256(json.dumps(request_data, sort_keys=True).encode()).hexdigest()
    # Serialize retries with the same id across workers before making a provider call.
    from sqlalchemy import text
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": request_id})
    existing = session.scalar(select(db.Analysis).where(db.Analysis.request_id == request_id))
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(409, "This request ID was already used for different state or filters")
        return existing.result
    items = catalog(session)
    validate_filters(payload.current_filters, items)
    start = perf_counter()
    result = analyze(payload.state_text, items, [item.model_dump() for item in payload.current_filters],
                     provider=settings.decision_provider, model=settings.jev_model,
                     api_key=settings.typesafe_api_key.get_secret_value() if settings.typesafe_api_key else None,
                     timeout_seconds=settings.request_timeout_seconds, max_retries=settings.max_retries,
                     candidate_budget=settings.candidate_filter_budget, select_threshold=settings.select_threshold,
                     reject_threshold=settings.reject_threshold, max_filters_per_category=settings.max_filters_per_category)
    validate_filters(result["filters"], items)
    catalog_version = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()[:16]
    response = AnalysisResponse(id=str(uuid4()), state_text=payload.state_text, client_revision=payload.client_revision,
                                provider=settings.decision_provider, model=result.get("model"), policy_version=POLICY_VERSION,
                                catalog_version=catalog_version, status="completed", created_at=datetime.now(timezone.utc),
                                duration_ms=round((perf_counter() - start) * 1000, 2), filters=result["filters"],
                                decisions=result["decisions"], provider_response=result["provider_response"], usage=result.get("usage") or {})
    response_data = response.model_dump(mode="json")
    row = db.Analysis(id=response.id, request_id=request_id, request_hash=request_hash, state_text=payload.state_text,
                      client_revision=payload.client_revision, submitted_filters=request_data["current_filters"],
                      provider=response.provider, model=response.model, policy_version=POLICY_VERSION,
                      catalog_version=catalog_version, status=response.status, duration_ms=response.duration_ms,
                      created_at=response.created_at, result=response_data)
    session.add(row)
    session.flush()
    for decision in response_data["decisions"]:
        session.add(db.AnalysisDecision(analysis_id=response.id, question_id=decision["question_id"],
                                       filter_id=decision["filter_id"], primitive=decision["primitive"], status=decision["status"], payload=decision))
    session.add(db.ProviderResponse(analysis_id=response.id, request=request_data, response=response_data["provider_response"], usage=response_data["usage"]))
    session.commit()
    logging.getLogger("jev.analysis").info(
        "Analysis completed id=%s provider=%s model=%s duration_ms=%s catalog_filters=%s decisions=%s",
        response.id, response.provider, response.model, response.duration_ms, len(items), len(response.decisions))
    return response


@router.get("/analyses", response_model=Page[AnalysisResponse])
def analyses(page: int = Query(default=1, ge=1, le=100000), page_size: int = Query(default=20, ge=1, le=100), session: Session = Depends(get_db)):
    total = session.scalar(select(func.count()).select_from(db.Analysis))
    items = [item.result for item in session.scalars(select(db.Analysis).order_by(db.Analysis.created_at.desc()).offset((page - 1) * page_size).limit(page_size))]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def analysis_detail(analysis_id: str, session: Session = Depends(get_db)):
    item = session.get(db.Analysis, analysis_id)
    if item is None:
        raise HTTPException(404, "Analysis not found")
    return item.result


@router.post("/profiles/search", response_model=SearchResponse)
def search_profiles(payload: SearchRequest, session: Session = Depends(get_db)):
    from backend.app.services.matching import search_profiles as match
    items = catalog(session)
    validate_filters(payload.filters, items)
    category_ids = {item["category_id"] for item in items}
    if set(payload.category_grouping) - category_ids:
        raise HTTPException(422, "Unknown category in grouping")
    profiles = [serialize_profile(item) for item in session.scalars(select(db.Profile))]
    matches = match(profiles, items, [item.model_dump() for item in payload.filters], grouping=payload.grouping, category_grouping=payload.category_grouping)
    return paginate(matches, payload.page, payload.page_size)


@router.get("/profiles/{profile_id}", response_model=Profile)
def profile_detail(profile_id: str, session: Session = Depends(get_db)):
    item = session.get(db.Profile, profile_id)
    if item is None:
        raise HTTPException(404, "Profile not found")
    return serialize_profile(item)


def serialize_saved(item):
    return {"id": item.id, "label": item.label, "query": item.query, "filters": item.filters,
            "grouping": item.grouping, "category_grouping": item.category_grouping,
            "created_at": item.created_at, "updated_at": item.updated_at}


@router.get("/saved-searches", response_model=Page[SavedSearchResponse])
def saved_searches(page: int = Query(default=1, ge=1, le=100000), page_size: int = Query(default=20, ge=1, le=100), session: Session = Depends(get_db)):
    total = session.scalar(select(func.count()).select_from(db.SavedSearch))
    items = [serialize_saved(item) for item in session.scalars(select(db.SavedSearch).order_by(db.SavedSearch.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/saved-searches", status_code=201, response_model=SavedSearchResponse)
def create_saved_search(payload: SavedSearchCreate, session: Session = Depends(get_db)):
    validate_filters(payload.filters, catalog(session))
    item = db.SavedSearch(**payload.model_dump())
    session.add(item)
    session.commit()
    return serialize_saved(item)


@router.patch("/saved-searches/{search_id}", response_model=SavedSearchResponse)
def update_saved_search(search_id: str, payload: SavedSearchPatch, session: Session = Depends(get_db)):
    item = session.get(db.SavedSearch, search_id)
    if item is None:
        raise HTTPException(404, "Saved search not found")
    if payload.filters is not None:
        validate_filters(payload.filters, catalog(session))
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    session.commit()
    return serialize_saved(item)


@router.delete("/saved-searches/{search_id}", status_code=204)
def delete_saved_search(search_id: str, session: Session = Depends(get_db)):
    item = session.get(db.SavedSearch, search_id)
    if item is None:
        raise HTTPException(404, "Saved search not found")
    session.delete(item)
    session.commit()
    return Response(status_code=204)

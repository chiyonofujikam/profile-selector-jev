"""API URLs used by the page. Each function handles one request."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import get_settings
from . import models
from .database import get_db
from .catalog import load_catalog, serialize_filter, serialize_profile
from . import analysis
from .selection import POLICY_VERSION
from .matching import search_profiles as match_profiles, validate_constraints
from .schemas import (
    AnalysisRequest, AnalysisResponse, CatalogFilter, Category, Constraint, ExampleResponse,
    Page, Profile, PublicConfig, SavedSearchCreate, SavedSearchPatch,
    SavedSearchResponse, SearchRequest, SearchResponse,
)

router = APIRouter(prefix="/api/v1")


def validate_filters(filters: list[Constraint], items: list[dict]) -> None:
    """Use the same constraint rules for API input and provider output."""
    validate_constraints([item.model_dump() for item in filters], items)


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
    counts = dict(session.execute(select(models.Filter.category_id, func.count()).where(models.Filter.active).group_by(models.Filter.category_id)).all())
    return [dict(id=item.id, key=item.key, label=item.label, description=item.description, count=counts.get(item.id, 0))
            for item in session.scalars(select(models.Category).order_by(models.Category.order, models.Category.label))]


@router.get("/filters", response_model=Page[CatalogFilter])
def filters(q: str = Query(default="", max_length=240), category_id: str | None = None,
            ids: str | None = Query(default=None, max_length=32200),
            page: int = Query(default=1, ge=1, le=100000), page_size: int = Query(default=100, ge=1, le=100),
            session: Session = Depends(get_db)):
    statement = select(models.Filter).where(models.Filter.active)
    if ids is not None:
        identifiers = [value for value in ids.split(",") if value]
        if len(identifiers) > 200 or any(len(value) > 160 for value in identifiers):
            raise HTTPException(422, "At most 200 filter IDs may be requested")
        statement = statement.where(models.Filter.id.in_(identifiers))
    if category_id:
        statement = statement.where(models.Filter.category_id == category_id)
    if q.strip():
        # Escape SQL wildcard characters so catalog search follows the literal user text.
        term = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        alias_match = select(models.FilterAlias.filter_id).where(models.FilterAlias.text.ilike(term, escape="\\"))
        statement = statement.where(or_(models.Filter.label.ilike(term, escape="\\"), models.Filter.description.ilike(term, escape="\\"), models.Filter.id.in_(alias_match)))
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    items = session.scalars(statement.order_by(models.Filter.label, models.Filter.id).offset((page - 1) * page_size).limit(page_size))
    return {"items": [serialize_filter(item) for item in items], "total": total, "page": page, "page_size": page_size}


@router.get("/examples", response_model=list[ExampleResponse])
def examples(session: Session = Depends(get_db)):
    return [dict(id=item.id, label=item.label, state_text=item.state_text, locale=item.locale)
            for item in session.scalars(select(models.Example).order_by(models.Example.label))]


@router.post("/analyses", response_model=AnalysisResponse)
def create_analysis(payload: AnalysisRequest, session: Session = Depends(get_db)):
    return analysis.create_analysis(payload, session, get_settings())


@router.get("/analyses", response_model=Page[AnalysisResponse])
def analyses(page: int = Query(default=1, ge=1, le=100000), page_size: int = Query(default=20, ge=1, le=100), session: Session = Depends(get_db)):
    total = session.scalar(select(func.count()).select_from(models.Analysis))
    items = [item.result for item in session.scalars(select(models.Analysis).order_by(models.Analysis.created_at.desc()).offset((page - 1) * page_size).limit(page_size))]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def analysis_detail(analysis_id: str, session: Session = Depends(get_db)):
    item = session.get(models.Analysis, analysis_id)
    if item is None:
        raise HTTPException(404, "Analysis not found")
    return item.result


@router.post("/profiles/search", response_model=SearchResponse)
def search_profiles(payload: SearchRequest, session: Session = Depends(get_db)):
    items = load_catalog(session)
    category_ids = {item["category_id"] for item in items}
    if set(payload.category_grouping) - category_ids:
        raise HTTPException(422, "Unknown category in grouping")
    profiles = [serialize_profile(item) for item in session.scalars(select(models.Profile))]
    constraints = [item.model_dump() for item in payload.filters]
    matches = match_profiles(
        profiles, items, constraints,
        grouping=payload.grouping,
        category_grouping=payload.category_grouping,
    )
    return paginate(matches, payload.page, payload.page_size)


@router.get("/profiles/{profile_id}", response_model=Profile)
def profile_detail(profile_id: str, session: Session = Depends(get_db)):
    item = session.get(models.Profile, profile_id)
    if item is None:
        raise HTTPException(404, "Profile not found")
    return serialize_profile(item)


def serialize_saved(item):
    return {"id": item.id, "label": item.label, "query": item.query, "filters": item.filters,
            "grouping": item.grouping, "category_grouping": item.category_grouping,
            "created_at": item.created_at, "updated_at": item.updated_at}


@router.get("/saved-searches", response_model=Page[SavedSearchResponse])
def saved_searches(page: int = Query(default=1, ge=1, le=100000), page_size: int = Query(default=20, ge=1, le=100), session: Session = Depends(get_db)):
    total = session.scalar(select(func.count()).select_from(models.SavedSearch))
    items = [serialize_saved(item) for item in session.scalars(select(models.SavedSearch).order_by(models.SavedSearch.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/saved-searches", status_code=201, response_model=SavedSearchResponse)
def create_saved_search(payload: SavedSearchCreate, session: Session = Depends(get_db)):
    validate_filters(payload.filters, load_catalog(session))
    item = models.SavedSearch(**payload.model_dump())
    session.add(item)
    session.commit()
    return serialize_saved(item)


@router.patch("/saved-searches/{search_id}", response_model=SavedSearchResponse)
def update_saved_search(search_id: str, payload: SavedSearchPatch, session: Session = Depends(get_db)):
    item = session.get(models.SavedSearch, search_id)
    if item is None:
        raise HTTPException(404, "Saved search not found")
    if payload.filters is not None:
        validate_filters(payload.filters, load_catalog(session))
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    session.commit()
    return serialize_saved(item)


@router.delete("/saved-searches/{search_id}", status_code=204)
def delete_saved_search(search_id: str, session: Session = Depends(get_db)):
    item = session.get(models.SavedSearch, search_id)
    if item is None:
        raise HTTPException(404, "Saved search not found")
    session.delete(item)
    session.commit()
    return Response(status_code=204)

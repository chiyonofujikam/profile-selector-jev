"""Idempotent analysis orchestration and persistence."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.db import models as db
from backend.app.db.catalog import catalog
from backend.app.schemas import AnalysisRequest, AnalysisResponse
from . import decisions
from .decisions import POLICY_VERSION
from .matching import validate_constraints


def create_analysis(payload: AnalysisRequest, session: Session, settings: Settings):
    request_id = payload.request_id or str(uuid4())
    request_data = payload.model_dump(exclude={"request_id"})
    request_hash = hashlib.sha256(json.dumps(request_data, sort_keys=True).encode()).hexdigest()

    # Serialize retries across workers. Return a stored response before calling Jev.
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": request_id},
    )
    existing = session.scalar(select(db.Analysis).where(db.Analysis.request_id == request_id))
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(409, "This request ID was already used for different state or filters")
        return existing.result

    # Selection uses plain dictionaries; it does not depend on the database session.
    items = catalog(session)
    start = perf_counter()
    result = decisions.analyze(
        payload.state_text, items, request_data["current_filters"],
        provider=settings.decision_provider,
        model=settings.jev_model,
        api_key=settings.typesafe_api_key.get_secret_value() if settings.typesafe_api_key else None,
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        candidate_budget=settings.candidate_filter_budget,
        select_threshold=settings.select_threshold,
        reject_threshold=settings.reject_threshold,
        max_filters_per_category=settings.max_filters_per_category,
    )
    validate_constraints(result["filters"], items)
    catalog_version = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()[:16]
    response = AnalysisResponse(
        id=str(uuid4()), state_text=payload.state_text, client_revision=payload.client_revision,
        provider=settings.decision_provider, model=result.get("model"),
        policy_version=POLICY_VERSION, catalog_version=catalog_version,
        status="completed", created_at=datetime.now(timezone.utc),
        duration_ms=round((perf_counter() - start) * 1000, 2),
        filters=result["filters"], decisions=result["decisions"],
        provider_response=result["provider_response"], usage=result.get("usage") or {},
    )
    response_data = response.model_dump(mode="json")

    # Store the analysis, every decision, and the complete response in one transaction.
    session.add(db.Analysis(
        id=response.id, request_id=request_id, request_hash=request_hash,
        state_text=payload.state_text, client_revision=payload.client_revision,
        submitted_filters=request_data["current_filters"], provider=response.provider,
        model=response.model, policy_version=POLICY_VERSION, catalog_version=catalog_version,
        status=response.status, duration_ms=response.duration_ms,
        created_at=response.created_at, result=response_data,
    ))
    session.flush()
    for decision in response_data["decisions"]:
        session.add(db.AnalysisDecision(
            analysis_id=response.id, question_id=decision["question_id"],
            filter_id=decision["filter_id"], primitive=decision["primitive"],
            status=decision["status"], payload=decision,
        ))
    session.add(db.ProviderResponse(
        analysis_id=response.id, request=request_data,
        response=response_data["provider_response"], usage=response_data["usage"],
    ))
    session.commit()
    logging.getLogger("jev.analysis").info(
        "Analysis completed id=%s provider=%s model=%s duration_ms=%s catalog_filters=%s decisions=%s",
        response.id, response.provider, response.model, response.duration_ms, len(items), len(response.decisions),
    )
    return response

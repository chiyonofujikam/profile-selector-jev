"""Read records into plain dictionaries for selection and matching."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


def serialize_filter(item: models.Filter) -> dict:
    levels = []
    for link in item.level_links:
        levels.append({
            "id": link.level.id,
            "label": link.level.label,
            "dimension": link.level.dimension,
            "rank": link.level.rank,
            "supports_exact": link.supports_exact,
            "supports_minimum": link.supports_minimum,
        })
    return {
        "id": item.id,
        "category_id": item.category_id,
        "label": item.label,
        "description": item.description,
        "subcategory": item.subcategory,
        "aliases": [alias.text for alias in item.aliases],
        "levels": levels,
    }


def load_catalog(session: Session) -> list[dict]:
    statement = select(models.Filter).where(models.Filter.active).order_by(models.Filter.id)
    return [serialize_filter(item) for item in session.scalars(statement)]


def serialize_profile(item: models.Profile) -> dict:
    return {
        "id": item.id,
        "display_name": item.display_name,
        "title": item.title,
        "summary": item.summary,
        "experience_years": item.experience_years,
        "competencies": [serialize_fact(fact) for fact in item.competencies],
        "languages": [serialize_fact(fact) for fact in item.languages],
    }


def serialize_fact(fact) -> dict:
    return {
        "filter_id": fact.filter_id,
        "level_id": fact.level_id,
        "present": fact.present,
    }



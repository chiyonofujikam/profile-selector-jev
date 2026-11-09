"""Read records into plain dictionaries for selection and matching."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as db


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



"""Validate and transactionally upsert reviewed catalog/profile JSON into PostgreSQL.

Usage: uv run --project backend python -m scripts.import_data local-data/reviewed.json --dry-run
       uv run --project backend python -m scripts.import_data local-data/reviewed.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


Identifier = Annotated[str, Field(min_length=1, max_length=128, strict=True)]
Label = Annotated[str, Field(min_length=1, max_length=240, strict=True)]
Description = Annotated[str, Field(max_length=20000, strict=True)]


class ImportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class CategoryInput(ImportModel):
    id: Identifier
    key: Identifier
    label: Label
    description: Description = ""
    order: int = Field(default=0, ge=0, strict=True)


class LevelInput(ImportModel):
    id: Identifier
    dimension: str = Field(min_length=1, max_length=100, strict=True)
    label: str = Field(min_length=1, max_length=160, strict=True)
    rank: int | None = Field(default=None, ge=0, strict=True)


class AliasInput(ImportModel):
    text: Label
    language: str = Field(default="und", min_length=2, max_length=16)


class FilterInput(ImportModel):
    id: Identifier
    category_id: Identifier
    label: Label
    description: Description = ""
    subcategory: str | None = Field(default=None, max_length=240)
    aliases: list[Label | AliasInput] = Field(default_factory=list, max_length=100)
    level_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    active: bool = Field(default=True, strict=True)
    legacy_path: str | None = None

    @model_validator(mode="after")
    def unique_levels(self) -> FilterInput:
        if len(set(self.level_ids)) != len(self.level_ids):
            raise ValueError(f"Duplicate level IDs on filter {self.id!r}.")
        aliases = [(alias, "und") if isinstance(alias, str) else (alias.text, alias.language)
                   for alias in self.aliases]
        if len(set(aliases)) != len(aliases):
            raise ValueError(f"Duplicate aliases on filter {self.id!r}.")
        return self


class CompetencyInput(ImportModel):
    filter_id: Identifier
    level_id: Identifier | None = None
    present: bool = Field(default=True, strict=True)

    @model_validator(mode="after")
    def absent_has_no_level(self) -> CompetencyInput:
        if not self.present and self.level_id is not None:
            raise ValueError("A confirmed-absent competency cannot have a proficiency level.")
        return self


class ProfileInput(ImportModel):
    id: Identifier
    display_name: Label
    title: Label
    summary: Description = ""
    experience_years: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    competencies: list[CompetencyInput] = Field(default_factory=list, max_length=1000)
    languages: list[CompetencyInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_competencies(self) -> ProfileInput:
        identifiers = [item.filter_id for item in self.competencies + self.languages]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"Filter appears more than once on profile {self.id!r}.")
        return self


class ExampleInput(ImportModel):
    id: Identifier
    label: Label
    state_text: str = Field(min_length=1, max_length=10000)
    locale: Literal["en", "fr", "es"] = "en"


class ImportPayload(ImportModel):
    version: Literal[1]
    provenance: str = Field(min_length=1, max_length=2000)
    categories: list[CategoryInput] = Field(default_factory=list)
    levels: list[LevelInput] = Field(default_factory=list)
    filters: list[FilterInput] = Field(default_factory=list)
    profiles: list[ProfileInput] = Field(default_factory=list)
    examples: list[ExampleInput] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_records(self) -> ImportPayload:
        for name in ("categories", "levels", "filters", "profiles", "examples"):
            identifiers = [item.id for item in getattr(self, name)]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"Duplicate IDs in {name}.")
        keys = [category.key for category in self.categories]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate category keys.")
        return self


def import_payload(session: Any, payload: ImportPayload) -> dict[str, int]:
    """Upsert without committing; the caller owns the single atomic transaction."""
    from sqlalchemy import and_, delete, select

    from backend.app.db.models import (
        Category, Example, Filter, FilterAlias, FilterLevel, Level, Profile,
        ProfileCompetency, ProfileLanguage,
    )

    def upsert(model: Any, values: dict[str, Any]) -> None:
        current = session.get(model, values["id"])
        if current is None:
            session.add(model(**values))
        else:
            for key, value in values.items():
                setattr(current, key, value)

    for category in payload.categories:
        upsert(Category, category.model_dump())
    for level in payload.levels:
        upsert(Level, level.model_dump())
    session.flush()
    for catalog_filter in payload.filters:
        if session.get(Category, catalog_filter.category_id) is None:
            raise ValueError(f"Unknown category {catalog_filter.category_id!r} on filter {catalog_filter.id!r}.")
        values = catalog_filter.model_dump(exclude={"aliases", "level_ids"})
        values["provenance"] = payload.provenance
        upsert(Filter, values)
        session.flush()
        session.execute(delete(FilterAlias).where(FilterAlias.filter_id == catalog_filter.id))
        session.execute(delete(FilterLevel).where(FilterLevel.filter_id == catalog_filter.id))
        for alias in catalog_filter.aliases:
            value = AliasInput(text=alias) if isinstance(alias, str) else alias
            session.add(FilterAlias(filter_id=catalog_filter.id, language=value.language, text=value.text))
        for level_id in catalog_filter.level_ids:
            level = session.get(Level, level_id)
            if level is None:
                raise ValueError(f"Unknown level {level_id!r} on filter {catalog_filter.id!r}.")
            session.add(FilterLevel(filter_id=catalog_filter.id, level_id=level_id,
                                    supports_exact=True, supports_minimum=level.rank is not None))
        session.flush()
    for profile in payload.profiles:
        values = profile.model_dump(exclude={"competencies", "languages"})
        values["provenance"] = payload.provenance
        upsert(Profile, values)
        session.flush()
        session.execute(delete(ProfileCompetency).where(ProfileCompetency.profile_id == profile.id))
        session.execute(delete(ProfileLanguage).where(ProfileLanguage.profile_id == profile.id))
        for association, attributes in ((ProfileCompetency, profile.competencies),
                                        (ProfileLanguage, profile.languages)):
            for competency in attributes:
                if session.get(Filter, competency.filter_id) is None:
                    raise ValueError(f"Unknown filter {competency.filter_id!r} on profile {profile.id!r}.")
                if competency.level_id is not None:
                    link = session.scalar(select(FilterLevel).where(
                        FilterLevel.filter_id == competency.filter_id,
                        FilterLevel.level_id == competency.level_id,
                    ))
                    if link is None:
                        raise ValueError(f"Level {competency.level_id!r} is not allowed for filter {competency.filter_id!r}.")
                    level = session.get(Level, competency.level_id)
                    if association is ProfileLanguage and level.dimension != "language-level":
                        raise ValueError(f"Language {competency.filter_id!r} must use a language-level definition.")
                session.add(association(profile_id=profile.id, **competency.model_dump()))
        session.flush()
    for example in payload.examples:
        upsert(Example, example.model_dump())
    session.flush()
    # Replacing allowed levels must not invalidate facts on profiles omitted from
    # this file. Check after all imported profiles have replaced their old facts.
    for association in (ProfileCompetency, ProfileLanguage):
        invalid = session.execute(select(association.filter_id, association.level_id).outerjoin(
            FilterLevel, and_(FilterLevel.filter_id == association.filter_id,
                              FilterLevel.level_id == association.level_id),
        ).where(association.level_id.is_not(None), FilterLevel.filter_id.is_(None)).limit(1)).first()
        if invalid is not None:
            raise ValueError(f"Import would leave an unsupported profile level for filter {invalid.filter_id!r}.")
    return {name: len(getattr(payload, name))
            for name in ("categories", "levels", "filters", "profiles", "examples")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Reviewed UTF-8 JSON import envelope.")
    parser.add_argument("--dry-run", action="store_true", help="Validate against PostgreSQL, then roll back all changes.")
    parser.add_argument("--validate-only", action="store_true", help="Check JSON structure without a database connection.")
    args = parser.parse_args(argv)
    try:
        payload = ImportPayload.model_validate_json(args.source.read_text(encoding="utf-8-sig"))
        if args.validate_only:
            print("Import JSON structure is valid. Database references have not been checked.")
            return 0
        from sqlalchemy.exc import SQLAlchemyError

        from backend.app.db.session import SessionLocal

        try:
            with SessionLocal() as session:
                with session.begin():
                    counts = import_payload(session, payload)
                    if args.dry_run:
                        session.rollback()
            print(("Validated; rolled back" if args.dry_run else "Imported") + ": " + json.dumps(counts, sort_keys=True))
            return 0
        except SQLAlchemyError:
            # Driver exceptions can contain connection information or candidate field values.
            print("Import failed; no changes committed. Check database readiness, migrations, unique keys, and references.", file=sys.stderr)
            return 1
    except ValidationError as error:
        details = [f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
                   for issue in error.errors(include_input=False, include_url=False)]
        print("Invalid import JSON:\n" + "\n".join(details), file=sys.stderr)
        return 1
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Import failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

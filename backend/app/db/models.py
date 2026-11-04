from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now():
    return datetime.now(timezone.utc)


def identifier():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    key: Mapped[str] = mapped_column(String(160), unique=True)
    label: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    order: Mapped[int] = mapped_column(Integer, default=0)


class Level(Base):
    __tablename__ = "levels"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    dimension: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(160))
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Filter(Base):
    __tablename__ = "filters"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"), index=True)
    label: Mapped[str] = mapped_column(String(240), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    subcategory: Mapped[str | None] = mapped_column(String(240), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    legacy_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[str] = mapped_column(Text, default="user-import")
    aliases: Mapped[list["FilterAlias"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    level_links: Mapped[list["FilterLevel"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class FilterAlias(Base):
    __tablename__ = "filter_aliases"
    __table_args__ = (UniqueConstraint("filter_id", "language", "text"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    filter_id: Mapped[str] = mapped_column(ForeignKey("filters.id", ondelete="CASCADE"), index=True)
    language: Mapped[str] = mapped_column(String(20), default="und")
    text: Mapped[str] = mapped_column(String(500))


class FilterLevel(Base):
    __tablename__ = "filter_levels"
    filter_id: Mapped[str] = mapped_column(ForeignKey("filters.id", ondelete="CASCADE"), primary_key=True)
    level_id: Mapped[str] = mapped_column(ForeignKey("levels.id"), primary_key=True)
    supports_exact: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_minimum: Mapped[bool] = mapped_column(Boolean, default=True)
    level: Mapped[Level] = relationship(lazy="joined")


class FilterRelationship(Base):
    __tablename__ = "filter_relationships"
    source_id: Mapped[str] = mapped_column(ForeignKey("filters.id"), primary_key=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("filters.id"), primary_key=True)
    relationship_type: Mapped[str] = mapped_column(String(60), primary_key=True)


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(240))
    title: Mapped[str] = mapped_column(String(240), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    provenance: Mapped[str] = mapped_column(Text, default="user-import")
    competencies: Mapped[list["ProfileCompetency"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    languages: Mapped[list["ProfileLanguage"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class ProfileCompetency(Base):
    __tablename__ = "profile_competencies"
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    filter_id: Mapped[str] = mapped_column(ForeignKey("filters.id"), primary_key=True)
    level_id: Mapped[str | None] = mapped_column(ForeignKey("levels.id"), nullable=True)
    present: Mapped[bool] = mapped_column(Boolean, default=True)


class ProfileLanguage(Base):
    __tablename__ = "profile_languages"
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    filter_id: Mapped[str] = mapped_column(ForeignKey("filters.id"), primary_key=True)
    level_id: Mapped[str | None] = mapped_column(ForeignKey("levels.id"), nullable=True)
    present: Mapped[bool] = mapped_column(Boolean, default=True)


class Example(Base):
    __tablename__ = "examples"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    label: Mapped[str] = mapped_column(String(240))
    state_text: Mapped[str] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(String(10), default="en")


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    request_id: Mapped[str] = mapped_column(String(160), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    state_text: Mapped[str] = mapped_column(Text)
    client_revision: Mapped[int] = mapped_column(Integer)
    submitted_filters: Mapped[list] = mapped_column(JSONB)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(100))
    catalog_version: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    duration_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    result: Mapped[dict] = mapped_column(JSONB)


class AnalysisDecision(Base):
    __tablename__ = "analysis_decisions"
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True)
    question_id: Mapped[str] = mapped_column(String(240), primary_key=True)
    filter_id: Mapped[str] = mapped_column(String(160))
    primitive: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONB)


class ProviderResponse(Base):
    __tablename__ = "provider_responses"
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True)
    request: Mapped[dict] = mapped_column(JSONB)
    response: Mapped[dict] = mapped_column(JSONB)
    usage: Mapped[dict] = mapped_column(JSONB)


class SavedSearch(Base):
    __tablename__ = "saved_searches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    label: Mapped[str] = mapped_column(String(240))
    query: Mapped[str] = mapped_column(Text, default="")
    filters: Mapped[list] = mapped_column(JSONB, default=list)
    grouping: Mapped[str] = mapped_column(String(10), default="and")
    category_grouping: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

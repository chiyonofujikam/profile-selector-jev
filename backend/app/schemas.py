"""Fields accepted and returned by the API. Pydantic checks these automatically."""

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


T = TypeVar("T")


class Page(Schema, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class PublicConfig(Schema):
    provider: Literal["mock", "jev"]
    model: str
    provider_ready: bool
    supported_locales: list[Literal["en", "fr", "es"]]
    policy_version: str
    select_threshold: float = Field(ge=0, le=1)
    reject_threshold: float = Field(ge=0, le=1)
    max_state_length: int


class DatabaseHealth(Schema):
    ready: bool
    reachable: bool
    migrated: bool


class ProviderHealth(Schema):
    name: Literal["mock", "jev"]
    ready: bool
    live_verified: bool | None = None


class HealthResponse(Schema):
    status: Literal["ok", "degraded"]
    database: DatabaseHealth
    provider: ProviderHealth


class ExampleResponse(Schema):
    id: str
    label: str
    state_text: str
    locale: Literal["en", "fr", "es"]


class Category(Schema):
    id: str
    key: str
    label: str
    description: str = ""
    count: int = 0


class Level(Schema):
    id: str
    label: str
    dimension: str
    rank: int | None = None
    supports_exact: bool = True
    supports_minimum: bool = True


class CatalogFilter(Schema):
    id: str
    category_id: str
    label: str
    description: str = ""
    subcategory: str | None = None
    levels: list[Level] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)


class Constraint(Schema):
    filter_id: str = Field(min_length=1, max_length=160)
    mode: Literal["include", "exclude"] = "include"
    requirement: Literal["mandatory", "preferred"] = "mandatory"
    level_id: str | None = Field(default=None, max_length=160)
    operator: Literal["exact", "minimum"] = "exact"
    source: str = Field(default="manual", max_length=100)

    @model_validator(mode="after")
    def validate_level(self):
        if self.operator == "minimum" and not self.level_id:
            raise ValueError("A minimum operator requires a level")
        return self


class AnalysisRequest(Schema):
    state_text: str = Field(min_length=1, max_length=12000)
    current_filters: list[Constraint] = Field(default_factory=list, max_length=200)
    client_revision: int = Field(default=0, ge=0)
    locale: Literal["en", "fr", "es"] = "en"
    request_id: str | None = Field(default=None, min_length=1, max_length=160)

    @field_validator("state_text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("State for Jev cannot be blank")
        return value


class Decision(Schema):
    question_id: str
    filter_id: str
    filter_label: str
    question: str
    primitive: Literal["noul", "choice"]
    kind: Literal["relevance", "exclusion", "mandatory", "level"]
    status: str
    probability: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    probabilities: dict[str, float] | None = None
    selected_value: str | None = None
    provenance: str
    evidence: str | None = None
    threshold: float | None = None


class AnalysisResponse(Schema):
    id: str
    state_text: str
    client_revision: int
    provider: str
    model: str | None = None
    policy_version: str
    catalog_version: str
    status: str
    created_at: datetime
    duration_ms: float
    filters: list[Constraint]
    decisions: list[Decision]
    provider_response: dict[str, Any]
    usage: dict[str, Any] = Field(default_factory=dict)


class Competency(Schema):
    filter_id: str
    level_id: str | None = None
    present: bool = True


class Profile(Schema):
    id: str
    display_name: str
    title: str = ""
    summary: str = ""
    experience_years: float | None = None
    competencies: list[Competency] = Field(default_factory=list)
    languages: list[Competency] = Field(default_factory=list)


class SearchRequest(Schema):
    filters: list[Constraint] = Field(default_factory=list, max_length=200)
    grouping: Literal["and", "or"] = "and"
    category_grouping: dict[str, Literal["and", "or"]] = Field(default_factory=dict)
    page: int = Field(default=1, ge=1, le=100000)
    page_size: int = Field(default=12, ge=1, le=100)


class ProfileMatch(Schema):
    profile: Profile
    score: float
    matched: list[str]
    unmet: list[str]
    unknown: list[str]
    eligible: bool


class SearchResponse(Schema):
    items: list[ProfileMatch]
    total: int
    page: int
    page_size: int


class SavedSearchCreate(Schema):
    label: str = Field(min_length=1, max_length=240)
    query: str = Field(default="", max_length=12000)
    filters: list[Constraint] = Field(default_factory=list, max_length=200)
    grouping: Literal["and", "or"] = "and"
    category_grouping: dict[str, Literal["and", "or"]] = Field(default_factory=dict)

    @field_validator("label")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip()


class SavedSearchPatch(Schema):
    label: str | None = Field(default=None, min_length=1, max_length=240)
    query: str | None = Field(default=None, max_length=12000)
    filters: list[Constraint] | None = Field(default=None, max_length=200)
    grouping: Literal["and", "or"] | None = None
    category_grouping: dict[str, Literal["and", "or"]] | None = None

    @model_validator(mode="after")
    def explicit_nulls(self):
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Updated fields cannot be null")
        if self.label is not None and not self.label.strip():
            raise ValueError("Name cannot be blank")
        return self


class SavedSearchResponse(SavedSearchCreate):
    id: str
    created_at: datetime
    updated_at: datetime

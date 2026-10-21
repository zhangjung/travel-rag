from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Pace(StrEnum):
    RELAXED = "relaxed"
    BALANCED = "balanced"
    INTENSIVE = "intensive"


class TravelRequest(BaseModel):
    destination: str = Field(min_length=1, max_length=50)
    days: int = Field(ge=1, le=14)
    budget_cny: int = Field(gt=0, le=1_000_000)
    travelers: list[str] = Field(min_length=1, max_length=10)
    interests: list[str] = Field(default_factory=list, max_length=12)
    pace: Pace = Pace.BALANCED
    trip_start: date | None = None
    constraints: list[str] = Field(default_factory=list, max_length=12)


class KnowledgeRecordCreate(BaseModel):
    kind: Literal["cases", "experiences"]
    record_id: str | None = Field(
        default=None,
        min_length=3,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$",
    )
    title: str = Field(min_length=2, max_length=100)
    text: str = Field(min_length=10, max_length=3000)
    destination: str = Field(min_length=1, max_length=50)
    traveler_tags: list[str] = Field(default_factory=list, max_length=12)
    interest_tags: list[str] = Field(default_factory=list, max_length=12)
    quality_score: float = Field(default=0.8, ge=0, le=1)
    days: int | None = Field(default=None, ge=1, le=30)
    pace: Pace | None = None
    budget_level: Literal["low", "medium", "high"] | None = None
    scene: str | None = Field(default=None, max_length=50)
    freshness: Literal["stable", "seasonal", "realtime_required"] | None = None

    @field_validator("title", "text", "destination", "scene")
    @classmethod
    def strip_text_fields(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("traveler_tags", "interest_tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @model_validator(mode="after")
    def validate_kind_fields(self) -> KnowledgeRecordCreate:
        if self.kind == "cases" and not all(
            value is not None for value in (self.days, self.pace, self.budget_level)
        ):
            raise ValueError("历史案例必须填写天数、行程节奏和预算级别。")
        if self.kind == "experiences" and (not self.scene or not self.freshness):
            raise ValueError("旅行经验必须填写场景和时效类型。")
        return self


class KnowledgeRecord(BaseModel):
    id: str
    kind: Literal["cases", "experiences"]
    title: str
    text: str
    metadata: dict[str, str | int | float | bool]


class KnowledgeListResponse(BaseModel):
    mode: Literal["mock", "live"]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    items: list[KnowledgeRecord]


class KnowledgeCreateResponse(BaseModel):
    mode: Literal["mock", "live"]
    source_saved: bool
    indexed: bool
    record: KnowledgeRecord


class Citation(BaseModel):
    source_id: str
    title: str
    source_type: Literal["case", "experience", "realtime"]
    url: str | None = None
    score: float | None = Field(default=None, ge=0, le=1)
    retrieved_at: datetime


class EvidenceItem(BaseModel):
    evidence_id: str
    claim: str
    source_ids: list[str] = Field(min_length=1)
    freshness: Literal["stable", "seasonal", "realtime"]


class RouteDecision(BaseModel):
    query: str
    selected_source: Literal["local", "realtime", "local+realtime"]
    route_reason: str
    local_confidence: float | None = Field(default=None, ge=0, le=1)


class ResearchReport(BaseModel):
    request_id: str
    destination: str
    summary: str
    case_insights: list[str]
    experience_advice: list[str]
    realtime_facts: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem]
    citations: list[Citation]
    route_decisions: list[RouteDecision]


class DayPlan(BaseModel):
    day: int = Field(ge=1)
    theme: str
    morning: str
    afternoon: str
    evening: str
    estimated_cost_cny: int = Field(ge=0)
    evidence_ids: list[str] = Field(default_factory=list)


class Itinerary(BaseModel):
    request_id: str
    destination: str
    days: int = Field(ge=1, le=14)
    total_estimated_cost_cny: int = Field(ge=0)
    schedule: list[DayPlan]
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_total_cost(self) -> Itinerary:
        calculated = sum(day.estimated_cost_cny for day in self.schedule)
        if self.total_estimated_cost_cny != calculated:
            self.total_estimated_cost_cny = calculated
        return self


class ValidationIssue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    day: int | None = None


class ValidationResult(BaseModel):
    passed: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class ReviewResult(BaseModel):
    approved: bool
    summary: str
    issues: list[str] = Field(default_factory=list)
    improvement_instructions: list[str] = Field(default_factory=list)
    requires_additional_research: bool = False
    additional_research_query: str | None = None


class PlanResponse(BaseModel):
    mode: Literal["mock", "live"]
    request: TravelRequest
    research: ResearchReport
    itinerary: Itinerary
    validation: ValidationResult
    review: ReviewResult
    retry_count: int = Field(default=0, ge=0, le=1)


class SavedPlanSummary(BaseModel):
    plan_id: str
    request_id: str
    title: str
    destination: str
    days: int = Field(ge=1, le=14)
    status: Literal["completed", "archived"]
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class SavedPlanDetail(SavedPlanSummary):
    plan: PlanResponse


class SavedPlanListResponse(BaseModel):
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    items: list[SavedPlanSummary]


class SavedPlanSaveResponse(BaseModel):
    created: bool
    item: SavedPlanDetail

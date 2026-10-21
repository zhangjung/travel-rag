from __future__ import annotations

from datetime import UTC, datetime

from travel_rag.domain.models import (
    Citation,
    DayPlan,
    EvidenceItem,
    Itinerary,
    ResearchReport,
    RouteDecision,
    TravelRequest,
)
from travel_rag.domain.validator import validate_itinerary


def _report() -> ResearchReport:
    return ResearchReport(
        request_id="request-1",
        destination="北京",
        summary="测试",
        case_insights=[],
        experience_advice=[],
        evidence=[
            EvidenceItem(
                evidence_id="ev-1",
                claim="证据",
                source_ids=["source-1"],
                freshness="stable",
            )
        ],
        citations=[
            Citation(
                source_id="source-1",
                title="来源",
                source_type="case",
                retrieved_at=datetime.now(UTC),
            )
        ],
        route_decisions=[
            RouteDecision(
                query="测试",
                selected_source="local",
                route_reason="测试",
                local_confidence=0.8,
            )
        ],
    )


def test_validator_rejects_budget_overrun() -> None:
    request = TravelRequest(
        destination="北京",
        days=1,
        budget_cny=100,
        travelers=["成人"],
    )
    itinerary = Itinerary(
        request_id="request-1",
        destination="北京",
        days=1,
        total_estimated_cost_cny=200,
        schedule=[
            DayPlan(
                day=1,
                theme="测试",
                morning="上午",
                afternoon="下午",
                evening="晚上",
                estimated_cost_cny=200,
                evidence_ids=["ev-1"],
            )
        ],
    )
    result = validate_itinerary(request, _report(), itinerary)
    assert not result.passed
    assert "BUDGET_EXCEEDED" in {issue.code for issue in result.issues}

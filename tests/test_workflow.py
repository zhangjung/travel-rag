from __future__ import annotations

import pytest

from travel_rag.domain.models import Pace, TravelRequest
from travel_rag.workflow import MockTravelWorkflow, create_workflow


def _request() -> TravelRequest:
    return TravelRequest(
        destination="北京",
        days=4,
        budget_cny=6000,
        travelers=["2位成人", "1名儿童"],
        interests=["历史", "亲子"],
        pace=Pace.RELAXED,
        constraints=["每天仅一个高体力核心景点", "午间需要休息"],
    )


def test_mock_end_to_end(test_settings, mock_kb) -> None:
    workflow = MockTravelWorkflow(test_settings, mock_kb)
    response = workflow.run(_request())
    assert response.mode == "mock"
    assert response.validation.passed
    assert response.review.approved
    assert len(response.itinerary.schedule) == 4
    assert response.itinerary.total_estimated_cost_cny <= 6000
    assert response.research.citations
    assert response.research.route_decisions[0].selected_source == "local"


def test_live_mode_does_not_fall_back_without_keys(test_settings) -> None:
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        create_workflow(test_settings, "live")

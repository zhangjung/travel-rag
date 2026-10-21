from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from travel_rag.agents.live import LiveTravelWorkflow, _extract_pydantic
from travel_rag.domain.models import ResearchReport, ReviewResult, TravelRequest


class FakeCrewOutput:
    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.pydantic = None


def test_extract_pydantic_from_json_dict() -> None:
    result = _extract_pydantic(
        SimpleNamespace(
            pydantic=None,
            json_dict={
                "approved": True,
                "summary": "通过",
                "issues": [],
                "improvement_instructions": [],
                "requires_additional_research": False,
                "additional_research_query": None,
            },
            raw="not used",
        ),
        ReviewResult,
    )
    assert result.approved


def test_extract_pydantic_from_plain_json() -> None:
    result = _extract_pydantic(
        FakeCrewOutput(
            """
            {
              "approved": true,
              "summary": "通过",
              "issues": [],
              "improvement_instructions": [],
              "requires_additional_research": false,
              "additional_research_query": null
            }
            """
        ),
        ReviewResult,
    )
    assert result.approved


def test_extract_pydantic_from_json_fence_without_llm_repair() -> None:
    result = _extract_pydantic(
        FakeCrewOutput(
            """
            ```json
            {
              "approved": false,
              "summary": "需要修订",
              "issues": ["预算超限"],
              "improvement_instructions": ["降低住宿预算"],
              "requires_additional_research": false,
              "additional_research_query": null
            }
            ```
            """
        ),
        ReviewResult,
    )
    assert not result.approved
    assert result.issues == ["预算超限"]


def test_extract_pydantic_rejects_invalid_json() -> None:
    with pytest.raises(RuntimeError, match="本地结构化解析失败"):
        _extract_pydantic(FakeCrewOutput("不是 JSON"), ReviewResult)


def test_research_task_uses_deepseek_json_without_crewai_converter(
    test_settings, mock_kb, monkeypatch
) -> None:
    settings = test_settings.model_copy(
        update={
            "deepseek_api_key": SecretStr("test-deepseek-key"),
            "tavily_api_key": SecretStr("test-tavily-key"),
        }
    )
    workflow = LiveTravelWorkflow(settings, mock_kb)
    report = ResearchReport(
        request_id="request-test",
        destination="北京",
        summary="测试调研",
        case_insights=["案例"],
        experience_advice=["经验"],
        evidence=[],
        citations=[],
        route_decisions=[],
    )
    captured = {}

    def fake_run_single(agent, task):
        captured["task"] = task
        return SimpleNamespace(pydantic=report, raw=report.model_dump_json())

    monkeypatch.setattr(workflow, "_run_single", fake_run_single)
    request = TravelRequest(
        destination="北京",
        days=2,
        budget_cny=3000,
        travelers=["2位成人"],
    )

    assert workflow._research("request-test", request) == report
    assert captured["task"].output_pydantic is None
    assert captured["task"].output_json is None
    assert workflow.research_llm.response_format == {"type": "json_object"}
    assert workflow.research_llm.additional_params == {
        "extra_body": {"thinking": {"type": "disabled"}}
    }
    assert workflow.research_llm.max_tokens == settings.research_max_tokens

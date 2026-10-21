from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from travel_rag.agents.live import LiveTravelWorkflow
from travel_rag.config import Settings
from travel_rag.domain.models import (
    Citation,
    DayPlan,
    EvidenceItem,
    Itinerary,
    PlanResponse,
    ResearchReport,
    ReviewResult,
    RouteDecision,
    TravelRequest,
)
from travel_rag.domain.validator import validate_itinerary
from travel_rag.observability import log_event
from travel_rag.rag.factory import create_knowledge_base
from travel_rag.rag.store import LocalKnowledgeBase, RetrievedItem

LOGGER = logging.getLogger(__name__)


class TravelWorkflow(Protocol):
    knowledge_base: LocalKnowledgeBase

    def run(self, request: TravelRequest) -> PlanResponse: ...


class MockTravelWorkflow:
    """Deterministic end-to-end demo; never selected as a Live fallback."""

    def __init__(self, settings: Settings, knowledge_base: LocalKnowledgeBase) -> None:
        self.settings = settings
        self.knowledge_base = knowledge_base

    @staticmethod
    def _citation(item: RetrievedItem, source_type: str) -> Citation:
        return Citation(
            source_id=item.source_id,
            title=item.title,
            source_type=source_type,
            score=item.rerank_score,
            retrieved_at=datetime.now(UTC),
        )

    def _research(self, request_id: str, request: TravelRequest) -> ResearchReport:
        query = " ".join(
            [
                request.destination,
                f"{request.days}天",
                *request.travelers,
                *request.interests,
                request.pace.value,
                *request.constraints,
            ]
        )
        cases = self.knowledge_base.search(
            "cases",
            query=query,
            destination=request.destination,
            top_k=self.settings.retrieval_top_k,
            rerank_top_n=self.settings.rerank_top_n,
        )
        experiences = self.knowledge_base.search(
            "experiences",
            query=query,
            destination=request.destination,
            top_k=self.settings.retrieval_top_k,
            rerank_top_n=self.settings.rerank_top_n,
        )
        if not cases or not experiences:
            raise RuntimeError("Mock 知识库为空，请先运行 ingest-demo --mode mock。")

        selected = [*cases[:2], *experiences[:3]]
        freshness_map = {
            "seasonal": "seasonal",
            "realtime_required": "realtime",
        }
        evidence = [
            EvidenceItem(
                evidence_id=f"ev-{index}",
                claim=item.text,
                source_ids=[item.source_id],
                freshness=freshness_map.get(
                    str(item.metadata.get("freshness")),
                    "stable",
                ),
            )
            for index, item in enumerate(selected, start=1)
        ]
        case_confidence = max(item.rerank_score for item in cases)
        experience_confidence = max(item.rerank_score for item in experiences)
        return ResearchReport(
            request_id=request_id,
            destination=request.destination,
            summary=(
                f"本次 Mock 调研从 {request.destination} 案例和经验卡中完成向量检索、"
                "目的地过滤与重排；Mock 不访问 Tavily，也不伪造当前票价或开放状态。"
            ),
            case_insights=[item.text for item in cases[:2]],
            experience_advice=[item.text for item in experiences[:3]],
            realtime_facts=[],
            evidence=evidence,
            citations=[
                *[self._citation(item, "case") for item in cases[:2]],
                *[self._citation(item, "experience") for item in experiences[:3]],
            ],
            route_decisions=[
                RouteDecision(
                    query=query,
                    selected_source="local",
                    route_reason="Mock 模式只验证本地 RAG 链路，不访问外部 API。",
                    local_confidence=max(case_confidence, experience_confidence),
                )
            ],
        )

    @staticmethod
    def _plan(request: TravelRequest, report: ResearchReport) -> Itinerary:
        beijing_templates = [
            (
                "故宫历史启蒙",
                "提前到达故宫预约入口，按中轴线进行亲子历史参观。",
                "控制专题馆数量并安排午休，视体力选择景山短线。",
                "返回住宿区附近用餐，整理第二天远郊出行物品。",
                650,
            ),
            (
                "长城独立成日",
                "按预留交通方案前往长城，避开过密的市区叠加行程。",
                "根据儿童体力选择步行与缆车组合，保留返程缓冲。",
                "回城后仅安排轻松晚餐和休息。",
                1100,
            ),
            (
                "科技与城市空间",
                "参观中国科技馆，以互动展项为核心。",
                "午休后游览奥林匹克公园，依据天气缩短室外停留。",
                "返回市区自由用餐，不设置刚性排队餐厅。",
                700,
            ),
            (
                "皇家园林与返程",
                "游览颐和园东宫门至长廊的舒缓路线。",
                "根据返程时间选择短线收尾并预留行李领取时间。",
                "返程或在住宿周边休息。",
                550,
            ),
        ]
        generic = (
            "目的地主题探索",
            "上午安排一个核心景点。",
            "午休后进行低强度文化体验。",
            "晚间在住宿区附近用餐并休息。",
            500,
        )
        schedule: list[DayPlan] = []
        for index in range(request.days):
            template = (
                beijing_templates[index]
                if request.destination == "北京" and index < len(beijing_templates)
                else generic
            )
            schedule.append(
                DayPlan(
                    day=index + 1,
                    theme=template[0],
                    morning=template[1],
                    afternoon=template[2],
                    evening=template[3],
                    estimated_cost_cny=template[4],
                    evidence_ids=[report.evidence[index % len(report.evidence)].evidence_id],
                )
            )
        total = sum(day.estimated_cost_cny for day in schedule)
        if total > request.budget_cny:
            per_day = max(0, request.budget_cny // request.days)
            for day in schedule:
                day.estimated_cost_cny = per_day
            total = sum(day.estimated_cost_cny for day in schedule)
        return Itinerary(
            request_id=report.request_id,
            destination=request.destination,
            days=request.days,
            total_estimated_cost_cny=total,
            schedule=schedule,
            notes=[
                "Mock 行程用于验证链路与 Schema，不代表实时开放信息。",
                "Live 模式会由调研 Agent 查询预约、天气和营业状态。",
            ],
        )

    def run(self, request: TravelRequest) -> PlanResponse:
        request_id = str(uuid4())
        log_event(
            LOGGER,
            "workflow_started",
            request_id=request_id,
            mode="mock",
            destination=request.destination,
            days=request.days,
        )
        report = self._research(request_id, request)
        itinerary = self._plan(request, report)
        validation = validate_itinerary(request, report, itinerary)
        review = ReviewResult(
            approved=validation.passed,
            summary=(
                "Mock 审核通过：天数、预算、日程完整度与证据引用满足规则。"
                if validation.passed
                else "Mock 审核未通过：存在确定性规则错误。"
            ),
            issues=[issue.message for issue in validation.issues],
            improvement_instructions=[],
            requires_additional_research=False,
        )
        response = PlanResponse(
            mode="mock",
            request=request,
            research=report,
            itinerary=itinerary,
            validation=validation,
            review=review,
            retry_count=0,
        )
        log_event(
            LOGGER,
            "workflow_completed",
            request_id=request_id,
            mode="mock",
            approved=review.approved,
            retry_count=0,
        )
        return response


def create_workflow(settings: Settings, mode: str) -> TravelWorkflow:
    if mode == "mock":
        return MockTravelWorkflow(
            settings=settings,
            knowledge_base=create_knowledge_base(settings, "mock"),
        )
    if mode == "live":
        # Validate external authority before any model download or index initialization.
        settings.validate_live()
        return LiveTravelWorkflow(
            settings=settings,
            knowledge_base=create_knowledge_base(settings, "local"),
        )
    raise ValueError(f"不支持的运行模式：{mode}")

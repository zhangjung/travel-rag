from __future__ import annotations

import json
import logging
import re
import time
from typing import TypeVar
from uuid import uuid4

from crewai import LLM, Agent, Crew, Process, Task
from crewai.llms.base_llm import JsonResponseFormat
from pydantic import BaseModel

from travel_rag.config import Settings
from travel_rag.domain.models import (
    Itinerary,
    PlanResponse,
    ResearchReport,
    ReviewResult,
    TravelRequest,
)
from travel_rag.domain.validator import validate_itinerary
from travel_rag.observability import log_event
from travel_rag.rag.store import LocalKnowledgeBase
from travel_rag.tools.local_search import CaseSearchTool, ExperienceSearchTool
from travel_rag.tools.realtime_search import RealtimeSearchTool

ModelT = TypeVar("ModelT", bound=BaseModel)
LOGGER = logging.getLogger(__name__)


def _extract_pydantic(result: object, model: type[ModelT]) -> ModelT:
    parsed = getattr(result, "pydantic", None)
    if isinstance(parsed, model):
        return parsed
    json_dict = getattr(result, "json_dict", None)
    if isinstance(json_dict, dict):
        try:
            return model.model_validate(json_dict)
        except ValueError:
            pass
    raw = getattr(result, "raw", None)
    if not isinstance(raw, str) or not raw.strip():
        raise RuntimeError(f"CrewAI 未返回可解析文本：{model.__name__}")

    stripped = raw.strip()
    candidates = [
        match.strip()
        for match in re.findall(
            r"```(?:json)?\s*(.*?)\s*```",
            stripped,
            flags=re.DOTALL | re.IGNORECASE,
        )
    ]
    candidates.append(stripped)
    start, end = stripped.find("{"), stripped.rfind("}")
    if start >= 0 and end > start:
        candidates.append(stripped[start : end + 1])

    unique_candidates = list(dict.fromkeys(candidates))
    errors: list[str] = []
    for candidate in unique_candidates:
        try:
            return model.model_validate(json.loads(candidate))
        except (json.JSONDecodeError, ValueError) as exc:
            errors.append(type(exc).__name__)
    LOGGER.error(
        "structured_output_parse_failed",
        extra={
            "event": {
                "model": model.__name__,
                "raw_chars": len(raw),
                "candidate_count": len(unique_candidates),
                "has_opening_brace": "{" in stripped,
                "has_terminal_brace": stripped.rstrip("`").rstrip().endswith("}"),
                "error_types": sorted(set(errors)),
            }
        },
    )
    raise RuntimeError(
        f"本地结构化解析失败：{model.__name__}；"
        f"尝试 {len(unique_candidates)} 种 JSON 边界，错误类型：{sorted(set(errors))}；"
        "输出诊断已写入结构化日志。"
    )


def _json_schema(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2)


class LiveTravelWorkflow:
    """Three CrewAI agents with a deterministic validator between plan and review."""

    def __init__(self, settings: Settings, knowledge_base: LocalKnowledgeBase) -> None:
        settings.validate_live()
        self.settings = settings
        self.knowledge_base = knowledge_base

        key = settings.deepseek_api_key.get_secret_value()  # type: ignore[union-attr]
        common = {
            "api_key": key,
            "base_url": settings.deepseek_base_url,
            "provider": "openai",
            "temperature": 0.2,
            "timeout": 120,
            "response_format": JsonResponseFormat(type="json_object"),
            # DeepSeek defaults to thinking mode. In this workflow the reasoning tokens
            # share max_tokens with the final JSON and can consume the whole budget,
            # leaving CrewAI with empty content. Structured Agent hand-offs therefore
            # use DeepSeek's documented non-thinking JSON mode explicitly.
            "additional_params": {
                "extra_body": {"thinking": {"type": "disabled"}}
            },
        }
        self.research_llm = LLM(
            model=settings.research_model,
            max_tokens=settings.research_max_tokens,
            **common,
        )
        self.planner_llm = LLM(
            model=settings.planner_model,
            max_tokens=settings.planner_max_tokens,
            **common,
        )
        self.reviewer_llm = LLM(
            model=settings.reviewer_model,
            max_tokens=settings.reviewer_max_tokens,
            **common,
        )

        tool_kwargs = {
            "knowledge_base": knowledge_base,
            "top_k": settings.retrieval_top_k,
            "rerank_top_n": settings.rerank_top_n,
            "confidence_threshold": settings.local_confidence_threshold,
        }
        self.research_tools = [
            CaseSearchTool(**tool_kwargs),
            ExperienceSearchTool(**tool_kwargs),
            RealtimeSearchTool(
                api_key=settings.tavily_api_key.get_secret_value()  # type: ignore[union-attr]
            ),
        ]

    @staticmethod
    def _run_single(agent: Agent, task: Task) -> object:
        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            cache=False,
            memory=False,
            verbose=False,
            tracing=False,
        )
        return crew.kickoff()

    def _research(
        self,
        request_id: str,
        request: TravelRequest,
        targeted_query: str | None = None,
    ) -> ResearchReport:
        agent = Agent(
            role="旅行调研专家",
            goal="为规划 Agent 产出带来源、可核验、时效边界清晰的结构化调研报告",
            backstory=(
                "你不是一个搜索 API，而是由 DeepSeek 模型驱动、能够选择和调用工具的执行单元。"
                "你负责区分长期经验与实时事实，并对每条结论保留证据链。"
            ),
            llm=self.research_llm,
            tools=self.research_tools,
            allow_delegation=False,
            allow_code_execution=False,
            max_iter=5,
            max_retry_limit=1,
            verbose=False,
        )
        request_json = request.model_dump_json(indent=2)
        targeted = targeted_query or "无；执行首次完整调研。"
        task = Task(
            agent=agent,
            description=f"""
请求 ID：{request_id}
用户需求：
{request_json}

补充调研目标：{targeted}

执行规则：
1. 必须调用 case_search 与 experience_search，destination 严格使用“{request.destination}”。
2. 历史案例只能提供路线结构，经验卡只能支持稳定经验。
3. 票价、天气、预约、营业状态、临时限流等当前事实必须调用 realtime_search。
4. 如果本地工具返回的 local_confidence 低于 {self.settings.local_confidence_threshold}，
   且该问题影响可执行性，必须调用 realtime_search。
5. 不得把其他城市的具体景点写进报告；不得编造 URL、分数或来源 ID。
6. route_decisions 必须说明使用本地、实时或组合来源的原因。
7. case_search 与 experience_search 各调用一次；如需实时核验，把问题合并后最多调用一次
   realtime_search。取得工具结果后立即汇总，不得重复调用相同工具。
8. 最终回复只能包含一个完整 JSON 对象，不得使用 Markdown 代码块或添加解释文字。

必须严格符合以下 JSON Schema：
{_json_schema(ResearchReport)}
""",
            expected_output="只输出符合 ResearchReport JSON Schema 的一个 JSON 对象。",
        )
        return _extract_pydantic(self._run_single(agent, task), ResearchReport)

    def _plan(
        self,
        request: TravelRequest,
        report: ResearchReport,
        revision_notes: list[str] | None = None,
    ) -> Itinerary:
        agent = Agent(
            role="旅行规划专家",
            goal="把用户硬约束与调研证据转为逐日可执行行程",
            backstory=(
                "你只基于用户需求和调研报告规划，不自行调用搜索工具。"
                "你需要在体验、交通节奏、预算与证据引用之间取得平衡。"
            ),
            llm=self.planner_llm,
            tools=[],
            allow_delegation=False,
            allow_code_execution=False,
            max_iter=6,
            max_retry_limit=1,
            verbose=False,
        )
        task = Task(
            agent=agent,
            description=f"""
用户需求：
{request.model_dump_json(indent=2)}

调研报告：
{report.model_dump_json(indent=2)}

上一轮修订要求：
{json.dumps(revision_notes or [], ensure_ascii=False)}

生成规则：
1. schedule 天数必须等于 {request.days}，day 从 1 连续编号。
2. 总花费不得超过 {request.budget_cny} 元，保留合理机动空间。
3. 每天早、午、晚完整，{request.pace.value} 节奏下避免核心景点过载。
4. evidence_ids 只能引用调研报告中真实存在的 evidence_id。
5. 不要添加调研报告未支持的实时事实。
6. 最终回复只能包含一个 JSON 对象，不得使用 Markdown 代码块或添加解释文字。

必须严格符合以下 JSON Schema：
{_json_schema(Itinerary)}
""",
            expected_output="只输出符合 Itinerary JSON Schema 的一个 JSON 对象。",
        )
        return _extract_pydantic(self._run_single(agent, task), Itinerary)

    def _review(
        self,
        request: TravelRequest,
        report: ResearchReport,
        itinerary: Itinerary,
        validation_json: str,
    ) -> ReviewResult:
        agent = Agent(
            role="旅行方案审核专家",
            goal="审核行程的约束满足、证据充分性、节奏和可执行性",
            backstory=(
                "你不重写完整行程，而是基于结构化输入作出是否通过的判断。"
                "确定性校验器的 error 不能被忽略。"
            ),
            llm=self.reviewer_llm,
            tools=[],
            allow_delegation=False,
            allow_code_execution=False,
            max_iter=5,
            max_retry_limit=1,
            verbose=False,
        )
        task = Task(
            agent=agent,
            description=f"""
用户需求：
{request.model_dump_json(indent=2)}

调研报告：
{report.model_dump_json(indent=2)}

待审核行程：
{itinerary.model_dump_json(indent=2)}

Python 规则校验结果：
{validation_json}

审核规则：
1. 校验存在 error 时 approved 必须为 false。
2. 只有缺少关键事实依据时 requires_additional_research 才能为 true，
   并给出一个明确 additional_research_query。
3. 路线或预算问题应写进 improvement_instructions，不要误判成需要联网调研。
4. 最终回复只能包含一个 JSON 对象，不得使用 Markdown 代码块或添加解释文字。

必须严格符合以下 JSON Schema：
{_json_schema(ReviewResult)}
""",
            expected_output="只输出符合 ReviewResult JSON Schema 的一个 JSON 对象。",
        )
        return _extract_pydantic(self._run_single(agent, task), ReviewResult)

    def run(self, request: TravelRequest) -> PlanResponse:
        request_id = str(uuid4())
        started = time.perf_counter()
        log_event(
            LOGGER,
            "workflow_started",
            request_id=request_id,
            mode="live",
            destination=request.destination,
            days=request.days,
        )
        try:
            report = self._research(request_id, request)
            itinerary = self._plan(request, report)
            validation = validate_itinerary(request, report, itinerary)
            review = self._review(
                request,
                report,
                itinerary,
                validation.model_dump_json(indent=2),
            )
            retry_count = 0

            if not review.approved:
                retry_count = 1
                if review.requires_additional_research:
                    if not review.additional_research_query:
                        raise RuntimeError("审核要求补充调研，但未提供目标查询。")
                    report = self._research(
                        request_id,
                        request,
                        targeted_query=review.additional_research_query,
                    )
                itinerary = self._plan(
                    request,
                    report,
                    revision_notes=review.improvement_instructions,
                )
                validation = validate_itinerary(request, report, itinerary)
                review = self._review(
                    request,
                    report,
                    itinerary,
                    validation.model_dump_json(indent=2),
                )

            response = PlanResponse(
                mode="live",
                request=request,
                research=report,
                itinerary=itinerary,
                validation=validation,
                review=review,
                retry_count=retry_count,
            )
            log_event(
                LOGGER,
                "workflow_completed",
                request_id=request_id,
                mode="live",
                approved=review.approved,
                retry_count=retry_count,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            return response
        except Exception:
            LOGGER.exception(
                "workflow_failed",
                extra={
                    "event": {
                        "request_id": request_id,
                        "mode": "live",
                        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    }
                },
            )
            raise

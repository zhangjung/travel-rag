from __future__ import annotations

import json
from datetime import UTC, datetime

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from travel_rag.rag.store import CollectionKind, LocalKnowledgeBase


class LocalSearchArgs(BaseModel):
    query: str = Field(description="围绕旅行需求编写的检索查询")
    destination: str = Field(description="目的地，用于严格元数据过滤")


class _LocalSearchTool(BaseTool):
    args_schema: type[BaseModel] = LocalSearchArgs
    _knowledge_base: LocalKnowledgeBase = PrivateAttr()
    _kind: CollectionKind = PrivateAttr()
    _top_k: int = PrivateAttr()
    _rerank_top_n: int = PrivateAttr()
    _confidence_threshold: float = PrivateAttr()

    def __init__(
        self,
        *,
        knowledge_base: LocalKnowledgeBase,
        kind: CollectionKind,
        top_k: int,
        rerank_top_n: int,
        confidence_threshold: float,
        **data: object,
    ) -> None:
        super().__init__(**data)
        self._knowledge_base = knowledge_base
        self._kind = kind
        self._top_k = top_k
        self._rerank_top_n = rerank_top_n
        self._confidence_threshold = confidence_threshold

    def _run(self, query: str, destination: str) -> str:
        items = self._knowledge_base.search(
            kind=self._kind,
            query=query,
            destination=destination,
            top_k=self._top_k,
            rerank_top_n=self._rerank_top_n,
        )
        confidence = max((item.rerank_score for item in items), default=0.0)
        payload = {
            "query": query,
            "destination_filter": destination,
            "source_type": "case" if self._kind == "cases" else "experience",
            "local_confidence": round(confidence, 4),
            "route_reason": (
                "本地证据置信度充足，适合回答稳定经验。"
                if confidence >= self._confidence_threshold
                else "本地证据低于阈值；如问题涉及当前状态，必须继续调用 realtime_search。"
            ),
            "retrieved_at": datetime.now(UTC).isoformat(),
            "results": [item.to_dict() for item in items],
        }
        return json.dumps(payload, ensure_ascii=False)


class CaseSearchTool(_LocalSearchTool):
    name: str = "case_search"
    description: str = (
        "从历史优质行程集合中检索相似案例。执行向量召回、目的地元数据过滤和重排，"
        "返回分数、来源 ID 与路由建议。"
    )

    def __init__(self, **kwargs: object) -> None:
        super().__init__(kind="cases", **kwargs)


class ExperienceSearchTool(_LocalSearchTool):
    name: str = "experience_search"
    description: str = (
        "从场景化旅行经验卡片中检索稳定经验。执行向量召回、目的地/通用元数据过滤"
        "和重排，返回分数、时效标签、来源 ID 与路由建议。"
    )

    def __init__(self, **kwargs: object) -> None:
        super().__init__(kind="experiences", **kwargs)

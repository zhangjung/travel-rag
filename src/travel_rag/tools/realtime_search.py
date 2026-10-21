from __future__ import annotations

import json
from datetime import UTC, datetime

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr
from tavily import TavilyClient


class RealtimeSearchArgs(BaseModel):
    query: str = Field(description="包含目的地、出行日期和待核验事实的实时查询，不要传入 API Key")


class RealtimeSearchTool(BaseTool):
    name: str = "realtime_search"
    description: str = (
        "查询票价、天气、预约规则、营业状态、临时限流等时效性信息。"
        "只在事实具有时效性或本地检索置信度不足时使用。"
    )
    args_schema: type[BaseModel] = RealtimeSearchArgs
    _client: TavilyClient = PrivateAttr()

    def __init__(self, api_key: str) -> None:
        super().__init__()
        if not api_key:
            raise RuntimeError("TAVILY_API_KEY 为空，不能创建实时检索工具。")
        self._client = TavilyClient(api_key=api_key)

    def _run(self, query: str) -> str:
        # API errors intentionally propagate to the workflow; no mock/cache fallback.
        response = self._client.search(
            query=query,
            search_depth="advanced",
            max_results=4,
            include_answer="advanced",
        )
        answer = response.get("answer")
        if isinstance(answer, str):
            answer = answer[:1000]
        payload = {
            "query": query,
            "route_reason": "查询对象具有实时性，长期知识库不能作为当前事实依据。",
            "retrieved_at": datetime.now(UTC).isoformat(),
            "answer": answer,
            "results": [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "content": (
                        item.get("content", "")[:800]
                        if isinstance(item.get("content"), str)
                        else None
                    ),
                    "score": item.get("score"),
                }
                for item in response.get("results", [])
            ],
        }
        return json.dumps(payload, ensure_ascii=False)

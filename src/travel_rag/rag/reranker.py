from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import torch
from sentence_transformers import CrossEncoder


@dataclass(frozen=True)
class RerankCandidate:
    text: str
    vector_score: float


class Reranker(Protocol):
    def score(self, query: str, candidates: list[RerankCandidate]) -> list[float]: ...


class MockReranker:
    """Offline character-overlap reranker used only in explicit mock mode."""

    @staticmethod
    def _tokens(text: str) -> set[str]:
        compact = "".join(text.lower().split())
        return {compact[index : index + 2] for index in range(max(1, len(compact) - 1))}

    def score(self, query: str, candidates: list[RerankCandidate]) -> list[float]:
        query_tokens = self._tokens(query)
        scores: list[float] = []
        for candidate in candidates:
            candidate_tokens = self._tokens(candidate.text)
            overlap = len(query_tokens & candidate_tokens) / max(1, len(query_tokens))
            scores.append(min(1.0, 0.65 * overlap + 0.35 * candidate.vector_score))
        return scores


class BgeReranker:
    def __init__(
        self,
        model_name: str,
        revision: str,
        device: str = "cuda",
        cache_folder: Path | None = None,
        local_files_only: bool = True,
    ) -> None:
        if device != "cuda":
            raise RuntimeError("本项目 Live Reranker 配置要求 CUDA，不允许自动切换到 CPU。")
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA 不可用，已停止加载 BGE Reranker；不会自动降级到 CPU。")
        self._model = CrossEncoder(
            model_name,
            device=device,
            cache_folder=str(cache_folder) if cache_folder else None,
            revision=revision,
            local_files_only=local_files_only,
        )

    def score(self, query: str, candidates: list[RerankCandidate]) -> list[float]:
        if not candidates:
            return []
        logits = self._model.predict([(query, candidate.text) for candidate in candidates])
        return [1.0 / (1.0 + math.exp(-float(logit))) for logit in logits]

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from pathlib import Path

import torch
from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings


class HashEmbeddings(Embeddings):
    """Deterministic offline embeddings used only in explicit mock mode."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def _embed(self, text: str) -> list[float]:
        normalized = f" {text.strip().lower()} "
        grams: Iterable[str] = (
            normalized[index : index + 2] for index in range(max(1, len(normalized) - 1))
        )
        vector = [0.0] * self.dimensions
        for gram in grams:
            digest = hashlib.sha256(gram.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def create_bge_embeddings(
    model_name: str,
    revision: str,
    device: str = "cuda",
    cache_folder: Path | None = None,
    local_files_only: bool = True,
) -> Embeddings:
    if device != "cuda":
        raise RuntimeError("本项目 Live RAG 配置要求 CUDA，不允许自动切换到 CPU。")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA 不可用，已停止加载 BGE Embedding；不会自动降级到 CPU。")
    return HuggingFaceEmbeddings(
        model_name=model_name,
        cache_folder=str(cache_folder) if cache_folder else None,
        model_kwargs={
            "device": device,
            "revision": revision,
            "local_files_only": local_files_only,
        },
        encode_kwargs={"normalize_embeddings": True},
    )

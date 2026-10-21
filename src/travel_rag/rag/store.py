from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

from travel_rag.rag.reranker import RerankCandidate, Reranker

CollectionKind = Literal["cases", "experiences"]


@dataclass(frozen=True)
class RetrievedItem:
    source_id: str
    title: str
    text: str
    metadata: dict[str, Any]
    vector_score: float
    rerank_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "text": self.text,
            "metadata": self.metadata,
            "vector_score": round(self.vector_score, 4),
            "rerank_score": round(self.rerank_score, 4),
        }


class LocalKnowledgeBase:
    """Two Chroma collections with vector recall, metadata filtering and reranking."""

    def __init__(
        self,
        persist_directory: Path,
        embeddings: Embeddings,
        reranker: Reranker,
    ) -> None:
        self.persist_directory = persist_directory
        self.embeddings = embeddings
        self.reranker = reranker
        client_settings = ChromaSettings(anonymized_telemetry=False)
        self._stores = {
            "cases": Chroma(
                collection_name="travel_cases",
                persist_directory=str(persist_directory),
                embedding_function=embeddings,
                collection_metadata={"hnsw:space": "cosine"},
                client_settings=client_settings,
            ),
            "experiences": Chroma(
                collection_name="travel_experiences",
                persist_directory=str(persist_directory),
                embedding_function=embeddings,
                collection_metadata={"hnsw:space": "cosine"},
                client_settings=client_settings,
            ),
        }

    @staticmethod
    def _metadata(record: dict[str, Any]) -> dict[str, str | int | float | bool]:
        metadata: dict[str, str | int | float | bool] = {}
        for key, value in record.items():
            if key in {"id", "text", "title"} or value is None:
                continue
            metadata[key] = (
                "|".join(str(item) for item in value) if isinstance(value, list) else value
            )
        metadata["title"] = record["title"]
        return metadata

    def ingest_jsonl(self, kind: CollectionKind, path: Path) -> int:
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        store = self._stores[kind]
        # Chroma add_texts uses upsert, making repeated demo ingestion idempotent.
        store.add_texts(
            texts=[record["text"] for record in records],
            metadatas=[self._metadata(record) for record in records],
            ids=[record["id"] for record in records],
        )
        return len(records)

    def count(self, kind: CollectionKind) -> int:
        return int(self._stores[kind]._collection.count())

    def contains(self, kind: CollectionKind, record_id: str) -> bool:
        result = self._stores[kind]._collection.get(
            ids=[record_id],
            include=["metadatas"],
        )
        return bool(result["ids"])

    def add_record(self, kind: CollectionKind, record: dict[str, Any]) -> None:
        record_id = str(record["id"])
        if self.contains(kind, record_id):
            raise ValueError(f"知识记录 ID 已存在：{record_id}")
        self._stores[kind].add_texts(
            texts=[str(record["text"])],
            metadatas=[self._metadata(record)],
            ids=[record_id],
        )

    def browse(
        self,
        kind: CollectionKind,
        *,
        query: str = "",
        destination: str | None = None,
    ) -> list[dict[str, Any]]:
        where = {"destination": {"$eq": destination}} if destination else None
        result = self._stores[kind]._collection.get(
            where=where,
            include=["documents", "metadatas"],
        )
        query_text = query.strip().casefold()
        records: list[dict[str, Any]] = []
        for record_id, document, metadata in zip(
            result["ids"],
            result["documents"] or [],
            result["metadatas"] or [],
            strict=True,
        ):
            searchable = " ".join(
                [str(record_id), str(document), *(str(value) for value in metadata.values())]
            ).casefold()
            if query_text and query_text not in searchable:
                continue
            records.append(
                {
                    "id": str(record_id),
                    "kind": kind,
                    "title": str(metadata.get("title", "未命名记录")),
                    "text": str(document),
                    "metadata": metadata,
                }
            )
        return sorted(
            records,
            key=lambda record: (
                str(record["metadata"].get("destination", "")),
                str(record["title"]),
            ),
        )

    def search(
        self,
        kind: CollectionKind,
        query: str,
        destination: str,
        top_k: int,
        rerank_top_n: int,
    ) -> list[RetrievedItem]:
        if kind == "experiences":
            where: dict[str, Any] = {
                "$or": [
                    {"destination": {"$eq": destination}},
                    {"destination": {"$eq": "通用"}},
                ]
            }
        else:
            where = {"destination": {"$eq": destination}}

        raw = self._stores[kind].similarity_search_with_score(
            query=query,
            k=top_k,
            filter=where,
        )
        if not raw:
            return []

        vector_scores = [max(0.0, min(1.0, 1.0 - float(distance))) for _, distance in raw]
        candidates = [
            RerankCandidate(text=document.page_content, vector_score=vector_score)
            for (document, _), vector_score in zip(raw, vector_scores, strict=True)
        ]
        rerank_scores = self.reranker.score(query, candidates)

        items = [
            RetrievedItem(
                source_id=str(document.id or document.metadata.get("id", "")),
                title=str(document.metadata["title"]),
                text=document.page_content,
                metadata=document.metadata,
                vector_score=vector_score,
                rerank_score=rerank_score,
            )
            for ((document, _), vector_score, rerank_score) in zip(
                raw, vector_scores, rerank_scores, strict=True
            )
        ]
        return sorted(items, key=lambda item: item.rerank_score, reverse=True)[:rerank_top_n]

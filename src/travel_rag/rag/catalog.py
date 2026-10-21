from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from travel_rag.domain.models import KnowledgeRecordCreate
from travel_rag.observability import log_event
from travel_rag.rag.store import CollectionKind, LocalKnowledgeBase

LOGGER = logging.getLogger(__name__)


class KnowledgeConflictError(ValueError):
    """Raised when a manually supplied record ID is already present."""


class KnowledgeIndexError(RuntimeError):
    """The source is preserved when indexing fails; no silent rollback is attempted."""

    def __init__(self, record_id: str) -> None:
        super().__init__(
            f"源数据已保存，但向量索引写入失败（ID: {record_id}）。"
            "系统没有删除或回滚源数据，请检查日志后重新执行 ingest-demo。"
        )


class KnowledgeCatalog:
    def __init__(self, knowledge_base: LocalKnowledgeBase, source_dir: Path) -> None:
        self.knowledge_base = knowledge_base
        self.source_dir = source_dir
        self._write_lock = Lock()

    @staticmethod
    def _filename(kind: CollectionKind) -> str:
        return "cases.jsonl" if kind == "cases" else "experiences.jsonl"

    def _source_path(self, kind: CollectionKind) -> Path:
        return self.source_dir / self._filename(kind)

    @staticmethod
    def _record_id(payload: KnowledgeRecordCreate) -> str:
        if payload.record_id:
            return payload.record_id
        prefix = "case-user" if payload.kind == "cases" else "exp-user"
        return f"{prefix}-{uuid4().hex[:12]}"

    @staticmethod
    def _to_record(payload: KnowledgeRecordCreate, record_id: str) -> dict[str, Any]:
        common: dict[str, Any] = {
            "id": record_id,
            "title": payload.title,
            "text": payload.text,
            "destination": payload.destination,
            "traveler_tags": payload.traveler_tags,
            "interest_tags": payload.interest_tags,
            "quality_score": payload.quality_score,
        }
        if payload.kind == "cases":
            common.update(
                {
                    "days": payload.days,
                    "pace": payload.pace.value if payload.pace else None,
                    "budget_level": payload.budget_level,
                }
            )
        else:
            common.update({"scene": payload.scene, "freshness": payload.freshness})
        return common

    @staticmethod
    def _source_contains(path: Path, record_id: str) -> bool:
        if not path.exists():
            return False
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and json.loads(line).get("id") == record_id:
                return True
        return False

    @staticmethod
    def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        needs_newline = False
        if path.exists() and path.stat().st_size:
            with path.open("rb") as source:
                source.seek(-1, 2)
                needs_newline = source.read(1) not in {b"\n", b"\r"}
        with path.open("a", encoding="utf-8", newline="\n") as target:
            if needs_newline:
                target.write("\n")
            target.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            target.write("\n")
            target.flush()

    def add(self, payload: KnowledgeRecordCreate) -> dict[str, Any]:
        kind: CollectionKind = payload.kind
        record_id = self._record_id(payload)
        record = self._to_record(payload, record_id)
        path = self._source_path(kind)

        with self._write_lock:
            if self._source_contains(path, record_id) or self.knowledge_base.contains(
                kind, record_id
            ):
                raise KnowledgeConflictError(f"知识记录 ID 已存在：{record_id}")
            self._append_jsonl(path, record)
            try:
                self.knowledge_base.add_record(kind, record)
            except Exception as exc:
                LOGGER.exception(
                    "knowledge_index_failed",
                    extra={
                        "event": {
                            "record_id": record_id,
                            "kind": kind,
                            "source_saved": True,
                            "error_type": type(exc).__name__,
                        }
                    },
                )
                raise KnowledgeIndexError(record_id) from exc

        log_event(
            LOGGER,
            "knowledge_record_created",
            record_id=record_id,
            kind=kind,
            destination=payload.destination,
        )
        return {
            "id": record_id,
            "kind": kind,
            "title": payload.title,
            "text": payload.text,
            "metadata": self.knowledge_base._metadata(record),
        }

from __future__ import annotations

from pathlib import Path

from travel_rag.config import Settings
from travel_rag.rag.embeddings import HashEmbeddings, create_bge_embeddings
from travel_rag.rag.reranker import BgeReranker, MockReranker
from travel_rag.rag.store import LocalKnowledgeBase


def _resolve_local_snapshot(
    model_name: str,
    revision: str,
    cache_folder: Path,
    *,
    local_files_only: bool,
) -> str:
    """Resolve a pinned Hugging Face snapshot before model construction.

    Passing a Hub model ID plus ``cache_folder`` can still cause some
    sentence-transformers releases to issue a metadata request even when
    ``local_files_only`` is set. Resolving the already downloaded snapshot
    ourselves gives Live mode a strict offline boundary.
    """
    if not local_files_only:
        return model_name

    repository_dir = f"models--{model_name.replace('/', '--')}"
    snapshot_path = cache_folder / repository_dir / "snapshots" / revision
    if not snapshot_path.is_dir():
        raise RuntimeError(
            "本地模型快照不存在："
            f"{snapshot_path}。请先执行 travel-rag download-models；"
            "Live 模式不会自动联网下载或降级。"
        )
    return str(snapshot_path)


def create_knowledge_base(settings: Settings, mode: str) -> LocalKnowledgeBase:
    if mode == "mock":
        return LocalKnowledgeBase(
            persist_directory=settings.chroma_dir.parent / "mock-chroma",
            embeddings=HashEmbeddings(),
            reranker=MockReranker(),
        )
    if mode != "local":
        raise ValueError(f"不支持的知识库模式：{mode}")
    embedding_path = _resolve_local_snapshot(
        settings.embedding_model,
        settings.embedding_revision,
        settings.hf_home,
        local_files_only=settings.model_local_files_only,
    )
    reranker_path = _resolve_local_snapshot(
        settings.reranker_model,
        settings.reranker_revision,
        settings.hf_home,
        local_files_only=settings.model_local_files_only,
    )
    return LocalKnowledgeBase(
        persist_directory=settings.chroma_dir,
        embeddings=create_bge_embeddings(
            embedding_path,
            revision=settings.embedding_revision,
            device=settings.embedding_device,
            cache_folder=settings.hf_home,
            local_files_only=settings.model_local_files_only,
        ),
        reranker=BgeReranker(
            reranker_path,
            revision=settings.reranker_revision,
            device=settings.reranker_device,
            cache_folder=settings.hf_home,
            local_files_only=settings.model_local_files_only,
        ),
    )

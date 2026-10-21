from __future__ import annotations

from pathlib import Path

import pytest

from travel_rag.config import PROJECT_ROOT, Settings
from travel_rag.rag.factory import create_knowledge_base


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    source_dir = tmp_path / "data" / "demo"
    source_dir.mkdir(parents=True)
    demo_dir = PROJECT_ROOT / "data" / "demo"
    for filename in ("cases.jsonl", "experiences.jsonl"):
        (source_dir / filename).write_bytes((demo_dir / filename).read_bytes())
    return Settings(
        _env_file=None,
        app_mode="mock",
        log_dir=tmp_path / "logs",
        chroma_dir=tmp_path / "index" / "chroma",
        knowledge_source_dir=source_dir,
        plans_db_path=tmp_path / "user" / "travel-rag.sqlite3",
    )


@pytest.fixture
def mock_kb(test_settings: Settings):
    knowledge_base = create_knowledge_base(test_settings, "mock")
    demo_dir = PROJECT_ROOT / "data" / "demo"
    knowledge_base.ingest_jsonl("cases", demo_dir / "cases.jsonl")
    knowledge_base.ingest_jsonl("experiences", demo_dir / "experiences.jsonl")
    return knowledge_base

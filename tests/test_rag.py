from __future__ import annotations

import json

from travel_rag.config import PROJECT_ROOT

EXPECTED_DEMO_COUNTS = {"cases": 40, "experiences": 66}


def test_demo_dataset_counts(mock_kb) -> None:
    assert mock_kb.count("cases") == EXPECTED_DEMO_COUNTS["cases"]
    assert mock_kb.count("experiences") == EXPECTED_DEMO_COUNTS["experiences"]


def test_demo_dataset_ids_are_unique_and_cities_are_covered() -> None:
    demo_dir = PROJECT_ROOT / "data" / "demo"
    records = [
        json.loads(line)
        for filename in ("cases.jsonl", "experiences.jsonl")
        for line in (demo_dir / filename).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = [record["id"] for record in records]
    destinations = {record["destination"] for record in records}

    assert len(ids) == len(set(ids))
    assert {"北京", "上海", "西安", "成都", "杭州", "广州", "南京", "重庆"} <= destinations


def test_destination_filter_excludes_other_cities(mock_kb) -> None:
    cases = mock_kb.search(
        "cases",
        query="北京 四天 家庭 儿童 历史 舒缓",
        destination="北京",
        top_k=8,
        rerank_top_n=8,
    )
    assert cases
    assert all(item.metadata["destination"] == "北京" for item in cases)
    assert not any("上海" in item.title or "西安" in item.title for item in cases)


def test_experience_filter_allows_destination_and_generic(mock_kb) -> None:
    items = mock_kb.search(
        "experiences",
        query="北京 家庭 儿童 预算 历史",
        destination="北京",
        top_k=12,
        rerank_top_n=12,
    )
    assert items
    assert {item.metadata["destination"] for item in items} <= {"北京", "通用"}

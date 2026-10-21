from __future__ import annotations

from fastapi.testclient import TestClient

from travel_rag.api import create_app
from travel_rag.workflow import MockTravelWorkflow


def test_api_health_ready_and_plan(test_settings, mock_kb) -> None:
    workflow = MockTravelWorkflow(test_settings, mock_kb)
    client = TestClient(create_app(settings=test_settings, workflow=workflow, mode="mock"))

    assert client.get("/api/v1/health").json() == {
        "status": "ok",
        "mode": "mock",
    }
    ready = client.get("/api/v1/ready")
    assert ready.status_code == 200
    assert ready.json()["collections"] == {"cases": 40, "experiences": 66}

    response = client.post(
        "/api/v1/plans",
        json={
            "destination": "北京",
            "days": 4,
            "budget_cny": 6000,
            "travelers": ["2位成人", "1名儿童"],
            "interests": ["历史", "亲子"],
            "pace": "relaxed",
            "constraints": ["每天仅一个高体力核心景点", "午间需要休息"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "mock"
    assert body["validation"]["passed"] is True

    exported = client.post("/api/v1/plans/export/markdown", json=body)
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/markdown")
    assert "filename*=UTF-8''" in exported.headers["content-disposition"]
    markdown = exported.content.decode("utf-8")
    assert "# 北京 4 日旅行方案" in markdown
    assert "## 需求概览" in markdown
    assert "## 逐日安排" in markdown
    assert "## 费用" in markdown
    assert "## 证据来源" not in markdown
    assert "## 校验与审核" not in markdown

    saved = client.post("/api/v1/saved-plans", json=body)
    assert saved.status_code == 200
    assert saved.json()["created"] is True
    plan_id = saved.json()["item"]["plan_id"]

    saved_again = client.post("/api/v1/saved-plans", json=body)
    assert saved_again.status_code == 200
    assert saved_again.json()["created"] is False
    assert saved_again.json()["item"]["plan_id"] == plan_id

    saved_list = client.get("/api/v1/saved-plans", params={"destination": "北京"})
    assert saved_list.status_code == 200
    assert saved_list.json()["total"] == 1

    saved_detail = client.get(f"/api/v1/saved-plans/{plan_id}")
    assert saved_detail.status_code == 200
    assert saved_detail.json()["plan"] == body

    saved_export = client.post(f"/api/v1/saved-plans/{plan_id}/export/markdown")
    assert saved_export.status_code == 200
    assert "## 逐日安排" in saved_export.content.decode("utf-8")

    missing = client.get("/api/v1/saved-plans/does-not-exist")
    assert missing.status_code == 404


def test_api_can_browse_search_and_add_knowledge(test_settings, mock_kb) -> None:
    workflow = MockTravelWorkflow(test_settings, mock_kb)
    client = TestClient(create_app(settings=test_settings, workflow=workflow, mode="mock"))

    listing = client.get("/api/v1/knowledge", params={"limit": 5})
    assert listing.status_code == 200
    assert listing.json()["total"] == 106
    assert len(listing.json()["items"]) == 5

    search = client.get(
        "/api/v1/knowledge",
        params={"kind": "cases", "destination": "北京", "query": "亲子"},
    )
    assert search.status_code == 200
    assert search.json()["total"] > 0
    assert all(item["metadata"]["destination"] == "北京" for item in search.json()["items"])

    payload = {
        "kind": "experiences",
        "record_id": "exp-user-api-test",
        "title": "雨天亲子备选策略",
        "text": "雨天亲子旅行应准备室内场馆备选，并在出发前再次核验预约和开放状态。",
        "destination": "北京",
        "traveler_tags": ["家庭", "儿童"],
        "interest_tags": ["亲子"],
        "quality_score": 0.82,
        "scene": "雨天",
        "freshness": "stable",
    }
    created = client.post("/api/v1/knowledge", json=payload)
    assert created.status_code == 201
    assert created.json()["source_saved"] is True
    assert created.json()["indexed"] is True

    found = client.get("/api/v1/knowledge", params={"query": "exp-user-api-test"})
    assert found.status_code == 200
    assert found.json()["total"] == 1
    assert found.json()["items"][0]["title"] == "雨天亲子备选策略"

    duplicate = client.post("/api/v1/knowledge", json=payload)
    assert duplicate.status_code == 409

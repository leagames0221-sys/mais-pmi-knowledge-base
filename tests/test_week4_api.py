"""tests for src/api/ (Week 4 sub-task 1、 FastAPI Web UI、 9 test)"""
from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.app import app


client = TestClient(app)


def test_landing_200():
    r = client.get("/")
    assert r.status_code == 200
    assert "MAIS PMI Knowledge Base" in r.text


def test_health_json():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "mais-t5-pmi-knowledge-base"


def test_api_health_endpoints_list():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "/" in body["endpoints"]
    assert "/search" in body["endpoints"]
    assert "/assistant" in body["endpoints"]


def test_search_get_form():
    r = client.get("/search")
    assert r.status_code == 200
    assert "<form" in r.text
    assert "textarea" in r.text


def test_search_post_ranked():
    r = client.post(
        "/search",
        data={
            "query": "Day-1 で組合存続",
            "industry": "製造業",
            "size_band": "100-300",
            "culture": "同族経営、 関西本社",
            "financial": "30-50",
            "integration_type": "tuck-in",
        },
    )
    assert r.status_code == 200
    assert "aggregate" in r.text # ranked table column header
    assert "PMI-" in r.text # at least 1 candidate PMI-id surface


def test_search_post_extracts_pmi_terms():
    r = client.post(
        "/search",
        data={"query": "Day-1 で組合 retention 検討、 EBITDA margin 8%", "industry": "製造業", "size_band": "100-300", "culture": "同族", "financial": "30-50", "integration_type": "tuck-in"},
    )
    assert r.status_code == 200
    # extract_pmi_terms から literal surface (32 canonical の subset)
    assert "Day-1" in r.text or "組合" in r.text or "retention" in r.text


def test_assistant_get_form():
    r = client.get("/assistant")
    assert r.status_code == 200
    assert "<textarea" in r.text
    assert "user_role" in r.text


def test_assistant_post_ranked_recommendation():
    r = client.post("/assistant", data={"query": "Day-1 で組合存続を判断", "user_role": "junior_consultant"})
    assert r.status_code == 200
    assert "LIL-" in r.text # LIL id surface
    assert "Rank 1" in r.text # recommendation rank surface
    assert "PMI-" in r.text or "REF-" in r.text # citation_array surface


def test_assistant_post_invalid_role_falls_to_default():
    """invalid user_role でも literal junior_consultant fallback で 200 return。"""
    r = client.post("/assistant", data={"query": "test", "user_role": "invalid_role"})
    assert r.status_code == 200

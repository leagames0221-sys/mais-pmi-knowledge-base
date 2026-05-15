"""tests for Week 4 e2e_smoke (full pipeline integration、 8 test)

scope:
- data_gen → operational store: 合成 corpus literal persist
- retrieval → multi_axis: rank similar cases
- assistant → emit_audit: AIQ-XXXXXX audit emit
- api endpoint integration: 全 7 endpoint pipeline 経由
"""
from __future__ import annotations

import os
import random
from datetime import datetime
from pathlib import Path

import pytest
from faker import Faker
from fastapi.testclient import TestClient

from src.api.app import app
from src.data_gen.generate_synthetic_pmi import generate_pmi_cases
from src.assistant.dialogue_orchestrate import (
    AssistantCounter,
    AssistantDialogueRequest,
    emit_assistant_audit,
    assistant_recommend,
)
from src.llm.provider import MockProvider
from src.operational.store import list_pmi_cases, store_pmi_case
from src.retrieval.multi_axis_similar_cases import rank_similar_cases
from src.schema.types import PMICase


@pytest.fixture
def e2e_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


# === pipeline integration ===


def test_data_gen_to_operational_store(e2e_env: Path):
    """data_gen 合成 → operational store 永続化 → list で literal 復元。"""
    rng = random.Random(0)
    fake = Faker(["en_US", "ja_JP"])
    Faker.seed(0)
    cases = generate_pmi_cases(count=5, fake=fake, rng=rng)
    for c in cases:
        store_pmi_case(c)
    stored = list_pmi_cases()
    assert len(stored) == 5


def test_retrieval_with_stored_cases(e2e_env: Path):
    """operational store → retrieval rank_similar_cases pipeline。"""
    rng = random.Random(0)
    fake = Faker(["en_US", "ja_JP"])
    Faker.seed(0)
    cases = generate_pmi_cases(count=5, fake=fake, rng=rng)
    for c in cases:
        store_pmi_case(c)
    pool = list_pmi_cases()
    query = pool[0]
    ranked = rank_similar_cases(query, pool, top_k=3)
    # query 自身は self-exclude、 最大 4 件 candidates から top-3
    assert len(ranked) <= 3
    assert all(s.candidate_pmi_id != query.pmi_id for s in ranked)


def test_assistant_full_pipeline(e2e_env: Path):
    """Assistant pipeline: request → recommend → emit_audit → counter + log file create。"""
    import json
    fixture = json.dumps([
        {"rank": 1, "recommendation_redacted": "test recommendation", "confidence": 0.85, "citation_array": ["PMI-000000001"]}
    ])
    llm = MockProvider(fixture={"listwise CoT": fixture})
    req = AssistantDialogueRequest(query_text_redacted="Day-1 query", user_role="junior_consultant")
    recs = assistant_recommend(req, [], [], [], llm)
    counter = AssistantCounter(audit_dir=e2e_env / "audit")
    lq = emit_assistant_audit(req, recs, [], [], counter, raw_query_text="raw", user_name="user")
    assert lq.lil_id == "LIL-000001"
    assert (e2e_env / "audit" / "assistant_log.jsonl").exists()
    assert (e2e_env / "audit" / "assistant_counter.jsonl").exists()
    assert (e2e_env / "audit" / "assistant_vault.jsonl").exists()


# === FastAPI endpoint full pipeline ===


def test_api_pipeline_landing_health(e2e_env: Path):
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    r2 = client.get("/health")
    assert r2.status_code == 200


def test_api_pipeline_search_to_results(e2e_env: Path):
    client = TestClient(app)
    r = client.post(
        "/search",
        data={
            "query": "Day-1 retention 検討",
            "industry": "製造業",
            "size_band": "100-300",
            "culture": "同族経営",
            "financial": "30-50",
            "integration_type": "tuck-in",
        },
    )
    assert r.status_code == 200
    assert "aggregate" in r.text


def test_api_pipeline_assistant_full(e2e_env: Path):
    client = TestClient(app)
    r = client.post("/assistant", data={"query": "test query", "user_role": "junior_consultant"})
    assert r.status_code == 200
    assert "LIL-" in r.text
    assert "Rank 1" in r.text


# === cross-module integration ===


def test_pmi_case_roundtrip_through_store_and_retrieval(e2e_env: Path):
    """Pydantic instance → store → load → retrieval rank (full lifecycle)。"""
    case = PMICase(
        pmi_id="PMI-000000001",
        industry="製造業",
        size_band="100-300",
        culture_profile="同族経営、 関西本社",
        financial_band="30-50",
        integration_type="tuck-in",
        lifecycle_stage="final_outcome",
        summary_redacted="(summary)",
        generated_at=datetime(2026, 5, 14),
    )
    store_pmi_case(case)
    loaded = list_pmi_cases()
    assert len(loaded) == 1
    assert loaded[0].pmi_id == "PMI-000000001"
    assert loaded[0].industry == "製造業"  # ja_JP literal preserved


def test_e2e_corpus_size_deterministic_seed(e2e_env: Path):
    """deterministic seed = 同 corpus 再現 (test reproducibility)。"""
    rng1 = random.Random(0)
    fake1 = Faker(["en_US", "ja_JP"])
    Faker.seed(0)
    cases1 = generate_pmi_cases(count=3, fake=fake1, rng=rng1)
    ids1 = [c.pmi_id for c in cases1]

    rng2 = random.Random(0)
    fake2 = Faker(["en_US", "ja_JP"])
    Faker.seed(0)
    cases2 = generate_pmi_cases(count=3, fake=fake2, rng=rng2)
    ids2 = [c.pmi_id for c in cases2]

    assert ids1 == ids2  # deterministic

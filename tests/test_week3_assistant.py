"""tests for src/assistant/dialogue_orchestrate.py (internal ADR § 1 + § 4 + § 9 順守、 17 test)"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.llm.provider import MockProvider
from src.assistant.dialogue_orchestrate import (
    DEFAULT_TOP_K,
    LIL_COUNTER_MAX,
    LISTWISE_COT_SYSTEM_PROMPT,
    AssistantCounter,
    AssistantDialogueRequest,
    emit_assistant_audit,
    assistant_recommend,
)
from src.retrieval.multi_axis_similar_cases import SimilarityScore


# === Constants ===


def test_default_top_k_3():
    """internal ADR § 1 + original proposal line 461「2-3 件」 順守。"""
    assert DEFAULT_TOP_K == 3


def test_counter_max_999999():
    """internal ADR § 4: 6 桁 counter 上限 (doctrine: future-proof 9 桁拡張 trigger)。"""
    assert LIL_COUNTER_MAX == 999999


def test_listwise_cot_prompt_contains_citation_rule():
    """internal ADR § 1: citation_array 必須 (doctrine: citation-required 順守)。"""
    assert "citation_array" in LISTWISE_COT_SYSTEM_PROMPT
    assert "doctrine: citation-required" in LISTWISE_COT_SYSTEM_PROMPT or "citation" in LISTWISE_COT_SYSTEM_PROMPT
    assert "PII redact" in LISTWISE_COT_SYSTEM_PROMPT or "redact" in LISTWISE_COT_SYSTEM_PROMPT


# === AssistantDialogueRequest schema ===


def test_request_valid():
    r = AssistantDialogueRequest(query_text_redacted="Day-1 で組合存続", user_role="junior_consultant")
    assert r.max_recommendations == 3


def test_request_empty_query_rejected():
    with pytest.raises(Exception):
        AssistantDialogueRequest(query_text_redacted="", user_role="junior_consultant")


def test_request_max_recommendations_range():
    with pytest.raises(Exception):
        AssistantDialogueRequest(query_text_redacted="q", user_role="junior_consultant", max_recommendations=0)
    with pytest.raises(Exception):
        AssistantDialogueRequest(query_text_redacted="q", user_role="junior_consultant", max_recommendations=11)


# === AssistantCounter persistence (internal ADR § 4) ===


def test_counter_sequence():
    with tempfile.TemporaryDirectory() as tmp:
        c = AssistantCounter(audit_dir=Path(tmp))
        assert c.next_id() == "LIL-000001"
        assert c.next_id() == "LIL-000002"
        assert c.next_id() == "LIL-000003"


def test_counter_persistence_across_instances():
    """新 instance が literal jsonl tail から reload する verify (singleton 不変性)。"""
    with tempfile.TemporaryDirectory() as tmp:
        c1 = AssistantCounter(audit_dir=Path(tmp))
        c1.next_id()
        c1.next_id()
        c2 = AssistantCounter(audit_dir=Path(tmp))  # new instance、 disk 経由 reload
        assert c2.next_id() == "LIL-000003"


def test_counter_file_not_exist_starts_at_1():
    with tempfile.TemporaryDirectory() as tmp:
        c = AssistantCounter(audit_dir=Path(tmp))
        assert c._read_current_counter() == 0  # 不在 = 0
        assert c.next_id() == "LIL-000001"


def test_counter_corruption_fallback():
    """corruption file → counter 0 fallback (silent fail 不採用、 fresh start)。"""
    with tempfile.TemporaryDirectory() as tmp:
        cpath = Path(tmp) / "assistant_counter.jsonl"
        cpath.write_text("not valid json\n", encoding="utf-8")
        c = AssistantCounter(audit_dir=Path(tmp))
        assert c._read_current_counter() == 0


# === assistant_recommend (MockProvider 経由) ===


def _make_request() -> AssistantDialogueRequest:
    return AssistantDialogueRequest(query_text_redacted="Day-1 で組合存続 vs 解消", user_role="junior_consultant", max_recommendations=3)


def _make_top_k() -> list[SimilarityScore]:
    return [
        SimilarityScore(query_pmi_id="Q", candidate_pmi_id="PMI-000000019", industry_score=1.0, culture_score=0.5, size_score=1.0, integration_type_score=1.0, financial_score=1.0, aggregate_score=0.875)
    ]


def test_recommend_parses_ranked_list():
    fixture = json.dumps([
        {"rank": 1, "recommendation_redacted": "組合存続 path", "confidence": 0.88, "citation_array": ["PMI-000000019"]},
        {"rank": 2, "recommendation_redacted": "解消 path", "confidence": 0.65, "citation_array": ["PMI-000000003"]},
    ])
    llm = MockProvider(fixture={"listwise CoT": fixture})
    recs = assistant_recommend(_make_request(), _make_top_k(), [], [], llm)
    assert len(recs) == 2
    assert recs[0].rank == 1
    assert "PMI-000000019" in recs[0].citation_array


def test_recommend_rank_sort_defensive():
    """LLM 出力 rank 順序不正でも literal sort 修正 verify。"""
    fixture = json.dumps([
        {"rank": 3, "recommendation_redacted": "C", "confidence": 0.5, "citation_array": ["PMI-000000003"]},
        {"rank": 1, "recommendation_redacted": "A", "confidence": 0.88, "citation_array": ["PMI-000000019"]},
        {"rank": 2, "recommendation_redacted": "B", "confidence": 0.65, "citation_array": ["PMI-000000005"]},
    ])
    llm = MockProvider(fixture={"listwise CoT": fixture})
    recs = assistant_recommend(_make_request(), _make_top_k(), [], [], llm)
    assert [r.rank for r in recs] == [1, 2, 3]


def test_recommend_max_recommendations_slice():
    """max_recommendations 超過時 literal slice。"""
    fixture = json.dumps([
        {"rank": i, "recommendation_redacted": f"R{i}", "confidence": 0.5, "citation_array": [f"PMI-00000000{i}"]}
        for i in range(1, 6)
    ])
    llm = MockProvider(fixture={"listwise CoT": fixture})
    req = AssistantDialogueRequest(query_text_redacted="q", user_role="junior_consultant", max_recommendations=2)
    recs = assistant_recommend(req, _make_top_k(), [], [], llm)
    assert len(recs) == 2


def test_recommend_invalid_json_raises():
    llm = MockProvider(fixture={"listwise CoT": "not json"})
    with pytest.raises(ValueError):
        assistant_recommend(_make_request(), _make_top_k(), [], [], llm)


# === emit_assistant_audit (internal ADR § 4 3 file 分離) ===


def test_emit_audit_3_file_separation():
    """operational + counter + vault 3 file literal 分離 verify (PII layer separation)。"""
    with tempfile.TemporaryDirectory() as tmp:
        counter = AssistantCounter(audit_dir=Path(tmp))
        from src.schema.types import RecommendationItem
        recs = [RecommendationItem(rank=1, recommendation_redacted="r1", confidence=0.8, citation_array=["PMI-000000019"])]
        lq = emit_assistant_audit(
            request=_make_request(),
            recommendations=recs,
            retrieved_cases=["PMI-000000019"],
            retrieved_papers=["REF-000007"],
            counter=counter,
            raw_query_text="raw value",
            user_name="raw_user_name",
        )
        assert (Path(tmp) / "assistant_log.jsonl").exists()
        assert (Path(tmp) / "assistant_counter.jsonl").exists()
        assert (Path(tmp) / "assistant_vault.jsonl").exists()
        # operational log: raw fields 不在
        log_content = (Path(tmp) / "assistant_log.jsonl").read_text(encoding="utf-8").strip()
        log_record = json.loads(log_content)
        assert "raw_query_text" not in log_record
        assert "user_name" not in log_record
        # vault: raw fields literal 存在
        vault_content = (Path(tmp) / "assistant_vault.jsonl").read_text(encoding="utf-8").strip()
        vault_record = json.loads(vault_content)
        assert vault_record["raw_query_text"] == "raw value"


def test_emit_audit_vault_optional():
    """raw_query_text/user_name None で vault file literal 不発 (opt-in PII pattern)。"""
    with tempfile.TemporaryDirectory() as tmp:
        counter = AssistantCounter(audit_dir=Path(tmp))
        emit_assistant_audit(
            request=_make_request(),
            recommendations=[],
            retrieved_cases=[],
            retrieved_papers=[],
            counter=counter,
        )
        assert not (Path(tmp) / "assistant_vault.jsonl").exists()  # vault 不発


def test_emit_audit_lil_id_increments():
    with tempfile.TemporaryDirectory() as tmp:
        counter = AssistantCounter(audit_dir=Path(tmp))
        lq1 = emit_assistant_audit(request=_make_request(), recommendations=[], retrieved_cases=[], retrieved_papers=[], counter=counter)
        lq2 = emit_assistant_audit(request=_make_request(), recommendations=[], retrieved_cases=[], retrieved_papers=[], counter=counter)
        assert lq1.lil_id == "LIL-000001"
        assert lq2.lil_id == "LIL-000002"

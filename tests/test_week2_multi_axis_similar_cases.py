"""tests for src/retrieval/multi_axis_similar_cases.py"""
from __future__ import annotations

from datetime import datetime

import pytest

from src.retrieval.multi_axis_similar_cases import (
    FINANCIAL_BAND_ORDER,
    SIZE_BAND_ORDER,
    SimilarityScore,
    compute_similarity,
    rank_similar_cases,
    similarity_culture,
    similarity_financial,
    similarity_industry,
    similarity_integration_type,
    similarity_size,
)
from src.schema.types import PMICase, PatternWeight


# === Helper: PMICase factory ===


def _pmi(
    pid: str,
    industry: str = "製造業",
    size: str = "100-300",
    culture: str = "同族経営、 関西本社",
    financial: str = "30-50",
    itype: str = "tuck-in",
) -> PMICase:
    return PMICase(
        pmi_id=pid,
        industry=industry,
        size_band=size, # type: ignore[arg-type]
        culture_profile=culture,
        financial_band=financial, # type: ignore[arg-type]
        integration_type=itype, # type: ignore[arg-type]
        lifecycle_stage="final_outcome",
        summary_redacted="(redacted summary)",
        generated_at=datetime(2026, 5, 14),
    )


# === Ordinal band ordering ===


def test_size_band_order_6_steps():
    assert len(SIZE_BAND_ORDER) == 6
    assert SIZE_BAND_ORDER[0] == "under_50"
    assert SIZE_BAND_ORDER[-1] == "over_1000"


def test_financial_band_order_5_steps():
    assert len(FINANCIAL_BAND_ORDER) == 5


# === Per-dim similarity ===


def test_industry_exact_match_1():
    a = _pmi("PMI-000000001", industry="製造業")
    b = _pmi("PMI-000000002", industry="製造業")
    assert similarity_industry(a, b) == 1.0


def test_industry_mismatch_0():
    a = _pmi("PMI-000000001", industry="製造業")
    b = _pmi("PMI-000000002", industry="IT サービス")
    assert similarity_industry(a, b) == 0.0


def test_size_adjacent_07():
    """。"""
    a = _pmi("PMI-000000001", size="100-300")
    b = _pmi("PMI-000000002", size="50-100")
    assert similarity_size(a, b) == 0.7


def test_size_two_step_04():
    """。"""
    a = _pmi("PMI-000000001", size="100-300")
    b = _pmi("PMI-000000002", size="500-1000")
    assert similarity_size(a, b) == 0.4


def test_size_three_plus_step_00():
    """。"""
    a = _pmi("PMI-000000001", size="under_50")
    b = _pmi("PMI-000000002", size="over_1000")
    assert similarity_size(a, b) == 0.0


def test_culture_keyword_partial_05():
    a = _pmi("PMI-000000001", culture="同族経営、 関西本社")
    b = _pmi("PMI-000000002", culture="同族経営、 関東本社")
    assert similarity_culture(a, b) == 0.5 # 同族 keyword 共有


def test_integration_type_categorical_full_only():
    a = _pmi("PMI-000000001", itype="tuck-in")
    b = _pmi("PMI-000000002", itype="standalone")
    assert similarity_integration_type(a, b) == 0.0 # partial overlap 不採用


def test_integration_type_exact_match():
    a = _pmi("PMI-000000001", itype="tuck-in")
    b = _pmi("PMI-000000002", itype="tuck-in")
    assert similarity_integration_type(a, b) == 1.0


def test_financial_adjacent_07():
    a = _pmi("PMI-000000001", financial="30-50")
    b = _pmi("PMI-000000002", financial="10-30")
    assert similarity_financial(a, b) == 0.7


# === compute_similarity (weight sum strict + aggregate) ===


def test_compute_similarity_perfect_match_aggregate_1():
    q = _pmi("PMI-000000001")
    c = _pmi("PMI-000000002") # 全 dim 同一
    score = compute_similarity(q, c)
    assert score.aggregate_score == 1.0


def test_compute_similarity_weight_sum_violation_raises():
    bad = PatternWeight(industry=0.5, culture=0.5, size=0.5, financial=0.5, integration_type=0.5)
    with pytest.raises(ValueError, match="PatternWeight sum"):
        compute_similarity(_pmi("PMI-000000001"), _pmi("PMI-000000002"), weight=bad)


def test_compute_similarity_score_breakdown():
    q = _pmi("PMI-000000001", industry="製造業", size="100-300", culture="同族経営、 関西", financial="30-50", itype="tuck-in")
    c = _pmi("PMI-000000002", industry="製造業", size="100-300", culture="同族経営、 関東", financial="30-50", itype="tuck-in")
    score = compute_similarity(q, c)
    # 期待: industry 1.0×0.30 + culture 0.5×0.25 + size 1.0×0.20 + IT 1.0×0.15 + financial 1.0×0.10 = 0.875
    assert abs(score.aggregate_score - 0.875) < 1e-6


# === rank_similar_cases ===


def test_rank_top_k_default_3():
    q = _pmi("PMI-000000001")
    candidates = [_pmi(f"PMI-00000{i:04d}") for i in range(2, 12)] # 10 candidates
    ranked = rank_similar_cases(q, candidates)
    assert len(ranked) == 3


def test_rank_self_exclude():
    q = _pmi("PMI-000000001")
    candidates = [q, _pmi("PMI-000000002"), _pmi("PMI-000000003")]
    ranked = rank_similar_cases(q, candidates, top_k=3)
    assert all(s.candidate_pmi_id != q.pmi_id for s in ranked)


def test_rank_aggregate_descending():
    q = _pmi("PMI-000000001", industry="製造業")
    c1 = _pmi("PMI-000000002", industry="製造業") # high
    c2 = _pmi("PMI-000000003", industry="IT サービス", size="over_1000", culture="雇われ", financial="over_100", itype="standalone") # low
    ranked = rank_similar_cases(q, [c1, c2], top_k=2)
    assert ranked[0].aggregate_score > ranked[1].aggregate_score


def test_rank_top_k_zero_raises():
    with pytest.raises(ValueError, match="top_k"):
        rank_similar_cases(_pmi("PMI-000000001"), [_pmi("PMI-000000002")], top_k=0)


def test_rank_empty_candidates():
    assert rank_similar_cases(_pmi("PMI-000000001"), [], top_k=3) == []


def test_rank_min_score_filter():
    q = _pmi("PMI-000000001", industry="製造業")
    c_far = _pmi("PMI-000000002", industry="IT サービス", size="over_1000", culture="雇われ", financial="over_100", itype="standalone")
    ranked = rank_similar_cases(q, [c_far], top_k=3, min_score=0.5)
    assert ranked == [] # far candidate filtered out

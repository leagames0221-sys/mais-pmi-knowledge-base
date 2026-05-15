"""5 dim weighted similarity detector (internal ADR § 3、 differentiation core、 2026-05-14 起草)

module boundaries 越境境界線 3 段階 順守:
- 段階 1 OS-primitives: なし (pure Python + Pydantic、 numerical 自作で literal 充足)
- 段階 2 business logic: 5 dim weighted similarity + categorical one-hot + ordinal distance + top-K rank (literal 自作 = differentiation)
- 段階 3: 該当なし

internal ADR PatternWeight schema 順守 (industry 0.30 / culture 0.25 / size 0.20 / integration_type 0.15 / financial 0.10)。
PoC = literal hardcode weight、 移植段階 = learning-based path 確保 (doctrine: future-proof)。
top-K = 2-3 (original proposal line 461 「過去のうち最も類似する 2-3 件」 literal 順守)。
"""
from __future__ import annotations

import sys
from typing import Optional, Sequence

from pydantic import BaseModel, Field

from ..schema.types import PMICase, PatternWeight

# Windows cp932 console UTF-8 reconfigure (T3 学び doctrine: analogical-recall inherit)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass


# ============================================================================
# Ordinal band ordering (size_band + financial_band 距離計算 SSoT、 internal ADR enum 同期)
# ============================================================================

# src/schema/types.py SizeBand Literal と同期 (under_50 < 50-100 < ... < over_1000)
SIZE_BAND_ORDER: tuple[str, ...] = (
    "under_50",
    "50-100",
    "100-300",
    "300-500",
    "500-1000",
    "over_1000",
)

# src/schema/types.py FinancialBand Literal と同期 (5-10 < 10-30 < ... < over_100)
FINANCIAL_BAND_ORDER: tuple[str, ...] = (
    "5-10",
    "10-30",
    "30-50",
    "50-100",
    "over_100",
)

# ordinal distance step → similarity score table (internal ADR § 3「隣接 band 0.7 / 2 step 0.4 / 3+ step 0.0」)
_ORDINAL_DISTANCE_SCORES: dict[int, float] = {0: 1.0, 1: 0.7, 2: 0.4}


def _ordinal_score(value_a: str, value_b: str, order: Sequence[str]) -> float:
    """ordinal band similarity (band order list 経由 step distance → score)。

    Returns:
        完全一致 = 1.0 / order 不適合 = 0.0 / 1 step = 0.7 / 2 step = 0.4 / 3+ step = 0.0
    """
    if value_a == value_b:
        return 1.0
    try:
        idx_a = order.index(value_a)
        idx_b = order.index(value_b)
    except ValueError:
        return 0.0
    step = abs(idx_a - idx_b)
    return _ORDINAL_DISTANCE_SCORES.get(step, 0.0)


def _categorical_score(
    value_a: str,
    value_b: str,
    partial_overlap_keywords: Optional[Sequence[str]] = None,
) -> float:
    """categorical one-hot match score (internal ADR § 3「完全一致 1.0 / partial overlap 0.5 / mismatch 0.0」)。

    Args:
        value_a, value_b: 比較対象 string
        partial_overlap_keywords: 両方の string 内に同一 keyword 存在で 0.5 partial overlap
    """
    if not value_a or not value_b:
        return 0.0
    if value_a == value_b:
        return 1.0
    a_lower = value_a.lower()
    b_lower = value_b.lower()
    if partial_overlap_keywords:
        for kw in partial_overlap_keywords:
            kw_lower = kw.lower()
            if kw_lower in a_lower and kw_lower in b_lower:
                return 0.5
    # 一方が他方に literal substring (例: "製造業 + 卸売" vs "製造業") → partial overlap
    if a_lower in b_lower or b_lower in a_lower:
        return 0.5
    return 0.0


# ============================================================================
# Per-dimension similarity functions (5 dim、 internal ADR § 3 順守)
# ============================================================================


def similarity_industry(a: PMICase, b: PMICase) -> float:
    """industry categorical similarity (substring overlap で partial 0.5 検出)。"""
    return _categorical_score(a.industry, b.industry)


def similarity_culture(a: PMICase, b: PMICase) -> float:
    """culture_profile categorical similarity (経営形態 + 地域 keyword で partial overlap 0.5)。

    keyword: 同族 / 創業 / 雇われ / 子会社 + 関西 / 関東 / 九州 / 東北 / 中部 (cross-PJ 多軸 cover)
    """
    keywords = ["同族", "創業", "雇われ", "子会社", "関西", "関東", "九州", "東北", "中部"]
    return _categorical_score(a.culture_profile, b.culture_profile, partial_overlap_keywords=keywords)


def similarity_size(a: PMICase, b: PMICase) -> float:
    """size_band ordinal similarity (隣接 band 0.7 / 2 step 0.4、 src/schema/types.py SizeBand 同期)。"""
    return _ordinal_score(a.size_band, b.size_band, SIZE_BAND_ORDER)


def similarity_financial(a: PMICase, b: PMICase) -> float:
    """financial_band ordinal similarity (隣接 band 0.7 / 2 step 0.4、 src/schema/types.py FinancialBand 同期)。"""
    return _ordinal_score(a.financial_band, b.financial_band, FINANCIAL_BAND_ORDER)


def similarity_integration_type(a: PMICase, b: PMICase) -> float:
    """integration_type categorical similarity (4 enum 完全一致 only、 partial なし = 統合 type 質的境界)。"""
    return _categorical_score(a.integration_type, b.integration_type)


# ============================================================================
# Score schema (transient retrieval result、 src/schema/types.py 7th type ではない light schema)
# ============================================================================


class SimilarityScore(BaseModel):
    """5 dim per-dim score + weighted aggregate (transient retrieval result)。"""

    query_pmi_id: str = Field(..., min_length=1)
    candidate_pmi_id: str = Field(..., min_length=1)
    industry_score: float = Field(..., ge=0.0, le=1.0)
    culture_score: float = Field(..., ge=0.0, le=1.0)
    size_score: float = Field(..., ge=0.0, le=1.0)
    integration_type_score: float = Field(..., ge=0.0, le=1.0)
    financial_score: float = Field(..., ge=0.0, le=1.0)
    aggregate_score: float = Field(..., ge=0.0, le=1.0)


# ============================================================================
# Weighted aggregate + top-K rank (internal ADR § 3 core)
# ============================================================================


def compute_similarity(
    query: PMICase,
    candidate: PMICase,
    weight: Optional[PatternWeight] = None,
) -> SimilarityScore:
    """5 dim weighted similarity (internal ADR PatternWeight default = hardcode、 移植 = learning-based)。

    Raises:
        ValueError: weight sum が 1.0 ± 1e-6 範囲外 (internal ADR PatternWeight schema 違反)
    """
    w = weight or PatternWeight()
    weight_sum = w.industry + w.culture + w.size + w.integration_type + w.financial
    if abs(weight_sum - 1.0) > 1e-6:
        raise ValueError(
            f"PatternWeight sum must equal 1.0, got {weight_sum:.6f} "
            "(internal ADR PatternWeight schema 違反、 移植 learning-based 段階の正規化忘れ candidate)"
        )

    industry = similarity_industry(query, candidate)
    culture = similarity_culture(query, candidate)
    size = similarity_size(query, candidate)
    integration_type = similarity_integration_type(query, candidate)
    financial = similarity_financial(query, candidate)

    aggregate = (
        industry * w.industry
        + culture * w.culture
        + size * w.size
        + integration_type * w.integration_type
        + financial * w.financial
    )
    aggregate_clamped = max(0.0, min(1.0, aggregate))
    return SimilarityScore(
        query_pmi_id=query.pmi_id,
        candidate_pmi_id=candidate.pmi_id,
        industry_score=industry,
        culture_score=culture,
        size_score=size,
        integration_type_score=integration_type,
        financial_score=financial,
        aggregate_score=aggregate_clamped,
    )


def rank_similar_cases(
    query: PMICase,
    candidates: Sequence[PMICase],
    top_k: int = 3,
    weight: Optional[PatternWeight] = None,
    min_score: float = 0.0,
) -> list[SimilarityScore]:
    """top-K similar case ranking (internal ADR § 3 + original proposal line 461「2-3 件」 literal 順守、 default k=3)。

    Args:
        query: query PMI case
        candidates: candidate pool (query 自身は self-exclude)
        top_k: top-K count (default 3、 original proposal line 461「過去のうち最も類似する 2-3 件」)
        weight: 5 dim PatternWeight (default = internal ADR hardcode)
        min_score: aggregate threshold filter (default 0.0 = filter 不発)
    Returns:
        sorted list[SimilarityScore] (aggregate desc、 length = min(top_k, qualifying candidates))
    Raises:
        ValueError: top_k < 1 / weight sum != 1.0
    """
    if top_k < 1:
        raise ValueError(f"top_k must be >= 1, got {top_k}")
    if not candidates:
        return []
    scores = [
        compute_similarity(query, candidate, weight=weight)
        for candidate in candidates
        if candidate.pmi_id != query.pmi_id  # self-exclude
    ]
    qualified = [s for s in scores if s.aggregate_score >= min_score]
    qualified.sort(key=lambda s: s.aggregate_score, reverse=True)
    return qualified[:top_k]


__all__ = [
    "SIZE_BAND_ORDER",
    "FINANCIAL_BAND_ORDER",
    "SimilarityScore",
    "similarity_industry",
    "similarity_culture",
    "similarity_size",
    "similarity_financial",
    "similarity_integration_type",
    "compute_similarity",
    "rank_similar_cases",
]

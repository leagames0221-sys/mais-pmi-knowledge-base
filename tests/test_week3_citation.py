"""tests for src/citation/citation_engine.py (internal ADR § 3 + § 9 順守、 13 test)"""
from __future__ import annotations

import pytest

from src.citation.citation_engine import (
    DEFAULT_CITATION_CHUNK_SIZE,
    DEFAULT_TOP_K,
    PMI_ID_PATTERN,
    REF_ID_PATTERN,
    CitationResponse,
    CitedChunk,
    _extract_ref_id,
    anthropic_citations_adapter_stub,
    format_citations,
)
from src.schema.types import RecommendationItem


# === Constants ===


def test_default_top_k_5():
    """internal ADR § 3 paper RAG 5 件 cover (PMI 「2-3 件」 と異なる)。"""
    assert DEFAULT_TOP_K == 5


def test_default_chunk_size_1024():
    assert DEFAULT_CITATION_CHUNK_SIZE == 1024


# === _extract_ref_id ===


def test_extract_ref_id_valid():
    assert _extract_ref_id("REF-000001-CHK-000003") == "REF-000001"


def test_extract_ref_id_invalid_format():
    assert _extract_ref_id("not-a-chunk-id") is None
    assert _extract_ref_id("REF-AAA001-CHK-000001") is None  # 数字以外 reject
    assert _extract_ref_id("REF-000001") is None  # CHK suffix なし
    assert _extract_ref_id("") is None


# === CitedChunk schema ===


def test_cited_chunk_valid():
    c = CitedChunk(
        ref_id="REF-000001",
        chunk_id="REF-000001-CHK-000003",
        text_excerpt="(redacted)",
        relevance_score=0.87,
    )
    assert c.ref_id == "REF-000001"


def test_cited_chunk_rejects_bad_ref_id():
    """REF_ID_PATTERN literal 強制 (BAD-XXXXXX reject)。"""
    with pytest.raises(Exception):
        CitedChunk(ref_id="BAD-000001", chunk_id="x", text_excerpt="t", relevance_score=0.5)


def test_cited_chunk_relevance_score_range():
    """score [0,1] 範囲外 reject。"""
    with pytest.raises(Exception):
        CitedChunk(ref_id="REF-000001", chunk_id="x", text_excerpt="t", relevance_score=1.5)


# === format_citations ===


def test_format_citations_empty():
    assert format_citations([]) == "(no recommendations)"


def test_format_citations_per_rank_categorize():
    """rank 1 = REF + PMI、 rank 2 = PMI only、 rank 3 = empty の per-rank categorize。"""
    items = [
        RecommendationItem(rank=1, recommendation_redacted="A", confidence=0.88, citation_array=["REF-000007", "PMI-000000019"]),
        RecommendationItem(rank=2, recommendation_redacted="B", confidence=0.65, citation_array=["PMI-000000003"]),
        RecommendationItem(rank=3, recommendation_redacted="C", confidence=0.55, citation_array=[]),
    ]
    out = format_citations(items)
    assert "papers=1" in out  # rank 1 REF-000007
    assert "cases=1" in out  # rank 1 PMI-000000019 (rank 2 も同様)
    assert "[no citation]" in out  # rank 3 empty
    assert "Rank 1" in out and "Rank 2" in out and "Rank 3" in out


def test_format_citations_confidence_displayed():
    items = [RecommendationItem(rank=1, recommendation_redacted="X", confidence=0.88, citation_array=["REF-000001"])]
    out = format_citations(items)
    assert "0.88" in out


# === REF + PMI id pattern ===


def test_ref_id_pattern_match():
    assert REF_ID_PATTERN.match("REF-000001") is not None
    assert REF_ID_PATTERN.match("REF-000001-CHK-x") is None  # extra suffix


def test_pmi_id_pattern_match():
    assert PMI_ID_PATTERN.match("PMI-000000001") is not None
    assert PMI_ID_PATTERN.match("PMI-000001") is None  # 6 桁 ≠ 9 桁


# === anthropic_citations_adapter_stub ===


def test_anthropic_adapter_stub_format():
    """Anthropic Citations API 2026 official request format stub 順守 (8 gate gate 8 swap path foundation)。"""
    c = CitedChunk(ref_id="REF-000001", chunk_id="REF-000001-CHK-000001", text_excerpt="abc", relevance_score=0.9, section_heading="Findings")
    response = CitationResponse(query_text_redacted="q", cited_chunks=[c], citation_array=["REF-000001"])
    payload = anthropic_citations_adapter_stub("query", response)
    assert "_stub_note" in payload  # Week 3 stub explicit marker
    assert payload["messages"][0]["content"][0]["type"] == "document"
    assert payload["messages"][0]["content"][0]["citations"]["enabled"] is True


def test_anthropic_adapter_empty_citation_response():
    response = CitationResponse(query_text_redacted="q", cited_chunks=[], citation_array=[])
    payload = anthropic_citations_adapter_stub("query", response)
    # 1 user text + 0 documents = 1 content block (query text)
    assert len(payload["messages"][0]["content"]) == 1
    assert payload["messages"][0]["content"][0]["type"] == "text"

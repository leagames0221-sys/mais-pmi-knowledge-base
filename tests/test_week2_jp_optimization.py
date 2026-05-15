"""tests for src/retrieval/jp_optimization.py"""
from __future__ import annotations

import pytest

from src.retrieval.jp_optimization import (
    PMI_DOMAIN_TERMS,
    Token,
    extract_pmi_terms,
    is_pmi_term,
    lookup_pmi_term,
    normalize_entity_name,
    reset_tagger_cache,
)


# === Dictionary integrity ===


def test_pmi_domain_terms_count_meets_requirement():
    """ = 32 件 actual)。"""
    assert len(PMI_DOMAIN_TERMS) >= 30


def test_pmi_domain_terms_has_critical_canonicals():
    """ IntegrationType + lifecycle critical terms 同期 verify。"""
    for canonical in ("tuck-in", "standalone", "merger_of_equals", "asset_purchase"):
        assert canonical in PMI_DOMAIN_TERMS
    for canonical in ("Day-1", "Day-100", "DD", "EBITDA"):
        assert canonical in PMI_DOMAIN_TERMS


def test_pmi_domain_terms_all_have_variants():
    """全 canonical に variant 1+ 件 存在 verify。"""
    for canonical, variants in PMI_DOMAIN_TERMS.items():
        assert isinstance(variants, list), f"{canonical} variants must be list"
        assert len(variants) >= 1, f"{canonical} needs ≥1 variant"


# === normalize_entity_name ===


def test_normalize_canonical_passes_through():
    assert normalize_entity_name("大手子会社") == "大手子会社"


def test_normalize_japanese_variant_to_canonical():
    assert normalize_entity_name("子会社") == "大手子会社"


def test_normalize_english_variant_to_canonical():
    assert normalize_entity_name("subsidiary") == "大手子会社"


def test_normalize_case_insensitive():
    assert normalize_entity_name("SUBSIDIARY") == "大手子会社"


def test_normalize_non_pmi_term_returns_stripped():
    assert normalize_entity_name(" 完全に未知の用語 ") == "完全に未知の用語"


def test_normalize_empty_string():
    assert normalize_entity_name("") == ""


# === lookup_pmi_term + is_pmi_term ===


def test_lookup_known_term():
    assert lookup_pmi_term("EBITDA") == "EBITDA"
    assert lookup_pmi_term("イービットダ") == "EBITDA"


def test_lookup_unknown_returns_none():
    assert lookup_pmi_term("未知用語") is None


def test_is_pmi_term_true_for_known():
    assert is_pmi_term("EBITDA") is True
    assert is_pmi_term("組合") is True


def test_is_pmi_term_false_for_unknown():
    assert is_pmi_term("コーヒー") is False


# === extract_pmi_terms (multi-word + 出現順保持) ===


def test_extract_pmi_terms_finds_multiple():
    result = extract_pmi_terms("Day-1 で組合存続 decision、 EBITDA margin 8%、 tuck in 形式")
    assert "Day-1" in result
    assert "組合" in result
    assert "EBITDA" in result
    assert "tuck-in" in result


def test_extract_pmi_terms_dedup():
    """同一 canonical を重複検出しない。"""
    result = extract_pmi_terms("EBITDA EBITDA EBITDA イービットダ")
    assert result.count("EBITDA") == 1


def test_extract_pmi_terms_empty_text():
    assert extract_pmi_terms("") == []


def test_extract_pmi_terms_no_match():
    assert extract_pmi_terms("コーヒーが好きです") == []


# === Token dataclass ===


def test_token_dataclass_frozen():
    t = Token(surface="EBITDA", base_form="EBITDA", pos="名詞", is_pmi_domain_term=True, canonical_form="EBITDA")
    with pytest.raises(Exception):
        t.surface = "modified" # type: ignore[misc]

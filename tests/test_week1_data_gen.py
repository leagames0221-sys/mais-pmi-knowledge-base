"""合成 PMI case data generator regression test"""
from __future__ import annotations

import random

from src.data_gen.generate_synthetic_pmi import (
    SYNTHETIC_SEED,
    generate_decisions,
    generate_assistant_queries,
    generate_outcomes,
    generate_papers,
    generate_patterns,
    generate_pmi_cases,
)


def _make_rng(seed: int = SYNTHETIC_SEED) -> random.Random:
    return random.Random(seed)


# ========== PMICase 生成 ==========

def test_pmi_count():
    rng = _make_rng()
    cases = generate_pmi_cases(30, None, rng) # fake unused in current impl
    assert len(cases) == 30


def test_pmi_id_pattern():
    rng = _make_rng()
    cases = generate_pmi_cases(30, None, rng)
    for c in cases:
        assert c.pmi_id.startswith("PMI-")
        assert len(c.pmi_id) == 13 # PMI- + 9 digits


def test_pmi_id_uniqueness():
    rng = _make_rng()
    cases = generate_pmi_cases(30, None, rng)
    ids = [c.pmi_id for c in cases]
    assert len(set(ids)) == 30


def test_pmi_seed_reproducibility():
    cases_1 = generate_pmi_cases(10, None, _make_rng())
    cases_2 = generate_pmi_cases(10, None, _make_rng())
    # 同 seed = literal 同 output
    assert [c.industry for c in cases_1] == [c.industry for c in cases_2]
    assert [c.size_band for c in cases_1] == [c.size_band for c in cases_2]


# ========== Decision 生成 ==========

def test_decisions_total_count():
    rng = _make_rng()
    cases = generate_pmi_cases(30, None, rng)
    decisions = generate_decisions(cases, 200, rng)
    assert len(decisions) == 200


def test_decisions_fk_to_pmi():
    rng = _make_rng()
    cases = generate_pmi_cases(30, None, rng)
    decisions = generate_decisions(cases, 200, rng)
    pmi_ids = {c.pmi_id for c in cases}
    for d in decisions:
        assert d.pmi_id in pmi_ids, f"Decision {d.dec_id} pmi_id {d.pmi_id} not in PMI cases"


def test_decisions_id_uniqueness():
    rng = _make_rng()
    cases = generate_pmi_cases(30, None, rng)
    decisions = generate_decisions(cases, 200, rng)
    ids = [d.dec_id for d in decisions]
    assert len(set(ids)) == 200


# ========== Outcome 生成 ==========

def test_outcomes_total_count():
    rng = _make_rng()
    cases = generate_pmi_cases(30, None, rng)
    decisions = generate_decisions(cases, 200, rng)
    outcomes = generate_outcomes(decisions, rng)
    assert len(outcomes) == 200


def test_outcomes_1to1_with_decisions():
    rng = _make_rng()
    cases = generate_pmi_cases(30, None, rng)
    decisions = generate_decisions(cases, 200, rng)
    outcomes = generate_outcomes(decisions, rng)
    dec_ids = {d.dec_id for d in decisions}
    out_dec_ids = {o.dec_id for o in outcomes}
    assert out_dec_ids == dec_ids # 1-to-1 mapping


def test_outcomes_class_validity():
    rng = _make_rng()
    cases = generate_pmi_cases(30, None, rng)
    decisions = generate_decisions(cases, 200, rng)
    outcomes = generate_outcomes(decisions, rng)
    valid_classes = {"success", "failure", "partial"}
    for o in outcomes:
        assert o.outcome_class in valid_classes


# ========== Pattern 生成 ==========

def test_patterns_count():
    rng = _make_rng()
    patterns = generate_patterns(20, rng)
    assert len(patterns) == 20


def test_patterns_default_weight_sum():
    rng = _make_rng()
    patterns = generate_patterns(20, rng)
    for p in patterns:
        s = (
            p.weight.industry + p.weight.size + p.weight.culture
            + p.weight.financial + p.weight.integration_type
        )
        assert abs(s - 1.0) < 0.01 # default weight sum literal 1.0


def test_patterns_confidence_range():
    rng = _make_rng()
    patterns = generate_patterns(20, rng)
    for p in patterns:
        assert 0.0 <= p.confidence <= 1.0


# ========== ReferencePaper 生成 ==========

def test_papers_count():
    rng = _make_rng()
    papers = generate_papers(50, None, rng)
    assert len(papers) == 50


def test_papers_publisher_validity():
    rng = _make_rng()
    papers = generate_papers(50, None, rng)
    valid_publishers = {"top-tier consulting firm", "top-tier PMI advisor", "top-tier consulting firm", "Other"}
    for p in papers:
        assert p.publisher in valid_publishers


def test_papers_chunk_count_range():
    rng = _make_rng()
    papers = generate_papers(50, None, rng)
    for p in papers:
        assert 3 <= len(p.chunks) <= 5


def test_papers_chunk_id_uniqueness():
    rng = _make_rng()
    papers = generate_papers(50, None, rng)
    chunk_ids = []
    for p in papers:
        chunk_ids.extend(c.chunk_id for c in p.chunks)
    assert len(set(chunk_ids)) == len(chunk_ids) # cross-paper uniqueness


# ========== AssistantQuery 生成 ==========

def test_assistant_count():
    rng = _make_rng()
    cases = generate_pmi_cases(30, None, rng)
    papers = generate_papers(50, None, rng)
    queries = generate_assistant_queries(10, cases, papers, rng)
    assert len(queries) == 10


def test_assistant_retrieved_cases_in_pmi():
    rng = _make_rng()
    cases = generate_pmi_cases(30, None, rng)
    papers = generate_papers(50, None, rng)
    queries = generate_assistant_queries(10, cases, papers, rng)
    pmi_ids = {c.pmi_id for c in cases}
    for q in queries:
        for case_id in q.retrieved_cases:
            assert case_id in pmi_ids


def test_assistant_retrieved_papers_in_papers():
    rng = _make_rng()
    cases = generate_pmi_cases(30, None, rng)
    papers = generate_papers(50, None, rng)
    queries = generate_assistant_queries(10, cases, papers, rng)
    paper_ids = {p.ref_id for p in papers}
    for q in queries:
        for paper_id in q.retrieved_papers:
            assert paper_id in paper_ids

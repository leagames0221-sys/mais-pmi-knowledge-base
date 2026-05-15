"""tests for src/operational/ (Week 4 sub-task 3、 6 type JSONL store、 13 test)"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from src.operational.store import (
    _table_path,
    get_decision,
    get_assistant_query,
    get_outcome,
    get_pattern,
    get_pmi_case,
    get_reference_paper,
    list_decisions,
    list_assistant_queries,
    list_outcomes,
    list_patterns,
    list_pmi_cases,
    list_reference_papers,
    store_decision,
    store_assistant_query,
    store_outcome,
    store_pattern,
    store_pmi_case,
    store_reference_paper,
)
from src.schema.types import (
    Decision,
    AssistantQuery,
    Outcome,
    Pattern,
    PatternDimension,
    PatternWeight,
    PMICase,
    RecommendationItem,
    ReferencePaper,
)


@pytest.fixture
def op_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


# === Helpers ===


def _make_pmi(i: int = 1) -> PMICase:
    return PMICase(
        pmi_id=f"PMI-{i:09d}",
        industry="製造業",
        size_band="100-300",
        culture_profile="同族経営、 関西本社",
        financial_band="30-50",
        integration_type="tuck-in",
        lifecycle_stage="final_outcome",
        summary_redacted=f"(redacted summary {i})",
        generated_at=datetime(2026, 5, 14),
    )


def _make_decision(i: int = 1) -> Decision:
    return Decision(
        dec_id=f"DEC-{i:06d}",
        pmi_id="PMI-000000001",
        decision_topic=f"Day-1 decision {i}",
        rationale_redacted=f"(rationale {i})",
        decision_at_day_n=-7,
        decision_maker_role="MAIS 担当",
        status="approved",
    )


# === PMICase ===


def test_pmi_case_round_trip(op_env: Path):
    case = _make_pmi(1)
    store_pmi_case(case)
    loaded = get_pmi_case("PMI-000000001")
    assert loaded is not None
    assert loaded.industry == "製造業"
    assert loaded.size_band == "100-300"


def test_pmi_case_list_multi(op_env: Path):
    store_pmi_case(_make_pmi(1))
    store_pmi_case(_make_pmi(2))
    store_pmi_case(_make_pmi(3))
    items = list_pmi_cases()
    assert len(items) == 3


def test_pmi_case_upsert(op_env: Path):
    """同 id で再 store → upsert (重複 insert なし)。"""
    case = _make_pmi(1)
    store_pmi_case(case)
    store_pmi_case(case) # second time
    assert len(list_pmi_cases()) == 1


def test_pmi_case_get_missing_none(op_env: Path):
    assert get_pmi_case("PMI-999999999") is None


def test_pmi_case_list_empty(op_env: Path):
    assert list_pmi_cases() == []


def test_pmi_case_list_limit(op_env: Path):
    for i in range(1, 6):
        store_pmi_case(_make_pmi(i))
    assert len(list_pmi_cases(limit=2)) == 2


# === Decision / Outcome / Pattern / ReferencePaper / AssistantQuery round-trip ===


def test_decision_round_trip(op_env: Path):
    dec = _make_decision(1)
    store_decision(dec)
    loaded = get_decision("DEC-000001")
    assert loaded is not None
    assert loaded.status == "approved"
    assert loaded.decision_topic == "Day-1 decision 1"
    assert len(list_decisions()) == 1


def test_outcome_round_trip(op_env: Path):
    out = Outcome(
        out_id="OUT-000001",
        dec_id="DEC-000001",
        measurable_kpi_delta={"retention_rate_90day": 0.92, "synergy_pct": 0.07},
        outcome_class="success",
        outcome_at_day_n=100,
        retrospective_redacted="(retrospective)",
    )
    store_outcome(out)
    loaded = get_outcome("OUT-000001")
    assert loaded is not None
    assert loaded.outcome_class == "success"
    assert loaded.measurable_kpi_delta["retention_rate_90day"] == 0.92


def test_pattern_round_trip(op_env: Path):
    pat = Pattern(
        pat_id="PAT-000001",
        pattern_name="retention pattern",
        pattern_dimension=PatternDimension(
            industry="製造業", size_band="100-300", culture_profile="同族",
            financial_band="30-50", integration_type="tuck-in",
        ),
        weight=PatternWeight(),
        cross_case_evidence_redacted="N=12",
        source_count=12,
        confidence=0.85,
    )
    store_pattern(pat)
    loaded = get_pattern("PAT-000001")
    assert loaded is not None
    assert loaded.source_count == 12


def test_reference_paper_round_trip(op_env: Path):
    ref = ReferencePaper(
        ref_id="REF-000001",
        paper_title_redacted="Beyond First 100 Days",
        publisher="top-tier PMI advisor",
        publication_year=2026,
        abstract_redacted="(abstract)",
        citation_url="synthetic://consulting-firm/2026/r1",
    )
    store_reference_paper(ref)
    loaded = get_reference_paper("REF-000001")
    assert loaded is not None
    assert loaded.publisher == "top-tier PMI advisor"


def test_assistant_query_round_trip(op_env: Path):
    lq = AssistantQuery(
        lil_id="LIL-000001",
        query_text_redacted="Day-1 query",
        retrieved_cases=["PMI-000000001"],
        retrieved_papers=["REF-000001"],
        recommendation_ranked=[
            RecommendationItem(rank=1, recommendation_redacted="r1", confidence=0.88, citation_array=["PMI-000000001"])
        ],
        user_role="junior_consultant",
    )
    store_assistant_query(lq)
    loaded = get_assistant_query("LIL-000001")
    assert loaded is not None
    assert loaded.user_role == "junior_consultant"
    assert len(loaded.recommendation_ranked) == 1


# === defensive paths ===


def test_unknown_table_raises(op_env: Path):
    with pytest.raises(ValueError, match="unknown table"):
        _table_path("nonexistent")


def test_atomic_rename_pattern(op_env: Path):
    """write 中 tmp file 残留なし (atomic rename verify)。"""
    store_pmi_case(_make_pmi(1))
    op_dir = op_env / "operational"
    tmp_files = list(op_dir.glob("*.tmp"))
    assert tmp_files == [] # no leftover tmp file

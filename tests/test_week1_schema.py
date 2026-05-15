"""T5 Pydantic schema 6 件 + helper class regression test (internal ADR 順守、 2026-05-14)

各 type:
- valid case (正常 instantiate)
- invalid ID pattern (ValidationError)
- field 範囲外 (day_n / confidence / publication_year 等)
- enum validation (status / outcome_class / publisher / user_role / lifecycle_stage / etc)
- T1-T4 FK pattern validation
- T5Output container 統合 test
"""
from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.schema.types import (
    Decision,
    AssistantQuery,
    Outcome,
    PMICase,
    PaperChunk,
    Pattern,
    PatternDimension,
    PatternWeight,
    RecommendationItem,
    ReferencePaper,
    T1SourcePair,
    T5Output,
)


# ========== Decision (DEC) ==========

def test_decision_valid():
    d = Decision(
        dec_id="DEC-000001",
        pmi_id="PMI-000000001",
        decision_topic="同族 + 組合あり Day-1 統合方針",
        rationale_redacted="(redacted rationale)",
        decision_at_day_n=-7,
        decision_maker_role="MAIS 担当 + 経営側オーナー",
        status="approved",
    )
    assert d.dec_id == "DEC-000001"
    assert d.status == "approved"


def test_decision_invalid_dec_id_pattern():
    with pytest.raises(ValidationError):
        Decision(
            dec_id="DEC-1",  # 6 digits 違反
            pmi_id="PMI-000000001",
            decision_topic="x",
            rationale_redacted="y",
            decision_at_day_n=0,
            decision_maker_role="z",
        )


def test_decision_invalid_pmi_id_pattern():
    with pytest.raises(ValidationError):
        Decision(
            dec_id="DEC-000001",
            pmi_id="PMI-001",  # 9 digits 違反
            decision_topic="x",
            rationale_redacted="y",
            decision_at_day_n=0,
            decision_maker_role="z",
        )


def test_decision_day_n_out_of_range():
    with pytest.raises(ValidationError):
        Decision(
            dec_id="DEC-000001",
            pmi_id="PMI-000000001",
            decision_topic="x",
            rationale_redacted="y",
            decision_at_day_n=200,  # le=100 違反
            decision_maker_role="z",
        )


# ========== Pattern (PAT) ==========

def test_pattern_valid():
    p = Pattern(
        pat_id="PAT-000001",
        pattern_name="同族経営 + 組合存続 = retention 高 pattern",
        pattern_dimension=PatternDimension(
            industry="製造業",
            size_band="100-300",
            culture_profile="同族 + 関西",
            financial_band="30-50",
            integration_type="tuck-in",
        ),
        cross_case_evidence_redacted="(N=12 cases、 retention 91% avg)",
        source_count=12,
        confidence=0.85,
    )
    assert p.weight.industry == 0.30
    assert p.weight.size == 0.20
    assert p.weight.culture == 0.25


def test_pattern_confidence_out_of_range():
    with pytest.raises(ValidationError):
        Pattern(
            pat_id="PAT-000001",
            pattern_name="x",
            pattern_dimension=PatternDimension(
                industry="x", size_band="100-300", culture_profile="x",
                financial_band="30-50", integration_type="tuck-in",
            ),
            cross_case_evidence_redacted="y",
            source_count=12,
            confidence=1.5,  # le=1.0 違反
        )


def test_pattern_weight_custom():
    w = PatternWeight(industry=0.4, size=0.2, culture=0.2, financial=0.1, integration_type=0.1)
    assert w.industry == 0.4


# ========== PMICase (PMI) ==========

def test_pmi_case_valid():
    p = PMICase(
        pmi_id="PMI-000000001",
        industry="製造業",
        size_band="100-300",
        culture_profile="同族 + 関西本社",
        financial_band="30-50",
        integration_type="tuck-in",
        lifecycle_stage="day100_complete",
        source_t1_pair=T1SourcePair(prof_id="PROF-000123", comp_id="COMP-00045"),
        source_t2_ddp_id="DDP-000007",
        source_t3_ip_id="IP-000000012",
        source_t4_cp_id="CP-000019",
        summary_redacted="(redacted summary)",
    )
    assert p.lifecycle_stage == "day100_complete"
    assert p.source_t1_pair.prof_id == "PROF-000123"


def test_pmi_case_invalid_lifecycle_stage():
    with pytest.raises(ValidationError):
        PMICase(
            pmi_id="PMI-000000001",
            industry="x", size_band="100-300", culture_profile="x",
            financial_band="30-50", integration_type="tuck-in",
            lifecycle_stage="invalid_stage",  # enum 違反
            summary_redacted="y",
        )


def test_pmi_case_optional_sources():
    """全 source_t* = Optional (sourcing 段階の早期 case でも literal valid)"""
    p = PMICase(
        pmi_id="PMI-000000001",
        industry="x", size_band="100-300", culture_profile="x",
        financial_band="30-50", integration_type="tuck-in",
        lifecycle_stage="matched",
        summary_redacted="y",
    )
    assert p.source_t1_pair is None
    assert p.source_t4_cp_id is None


def test_pmi_case_invalid_t4_cp_id():
    with pytest.raises(ValidationError):
        PMICase(
            pmi_id="PMI-000000001",
            industry="x", size_band="100-300", culture_profile="x",
            financial_band="30-50", integration_type="tuck-in",
            lifecycle_stage="day100_complete",
            source_t4_cp_id="CP-1",  # 6 digits 違反
            summary_redacted="y",
        )


# ========== Outcome (OUT) ==========

def test_outcome_valid():
    o = Outcome(
        out_id="OUT-000001",
        dec_id="DEC-000001",
        measurable_kpi_delta={
            "retention_rate_90day": 0.92,
            "union_engagement_score": 8.3,
            "cost_synergy_delta_pct": 0.07,
        },
        outcome_class="success",
        outcome_at_day_n=100,
        retrospective_redacted="(redacted retrospective)",
    )
    assert o.outcome_class == "success"
    assert o.measurable_kpi_delta["retention_rate_90day"] == 0.92


def test_outcome_invalid_class():
    with pytest.raises(ValidationError):
        Outcome(
            out_id="OUT-000001",
            dec_id="DEC-000001",
            measurable_kpi_delta={},
            outcome_class="maybe",  # enum 違反
            outcome_at_day_n=100,
            retrospective_redacted="y",
        )


# ========== ReferencePaper (REF) ==========

def test_reference_paper_valid():
    r = ReferencePaper(
        ref_id="REF-000001",
        paper_title_redacted="Beyond First 100 Days",
        publisher="top-tier PMI advisor",
        publication_year=2026,
        chunks=[
            PaperChunk(chunk_id="CHK-000001", page=3, text_redacted="x", embedding_id="emb_001")
        ],
        abstract_redacted="(redacted abstract)",
        citation_url="synthetic://consulting-firm/2026/post-deal-ai",
    )
    assert r.publisher == "top-tier PMI advisor"
    assert len(r.chunks) == 1


def test_reference_paper_invalid_publisher():
    with pytest.raises(ValidationError):
        ReferencePaper(
            ref_id="REF-000001",
            paper_title_redacted="x",
            publisher="Deloitte",  # enum 違反 (top-tier consulting firm/top-tier PMI advisor/top-tier consulting firm/Other)
            publication_year=2026,
            abstract_redacted="y",
            citation_url="z",
        )


def test_reference_paper_year_out_of_range():
    with pytest.raises(ValidationError):
        ReferencePaper(
            ref_id="REF-000001",
            paper_title_redacted="x",
            publisher="top-tier consulting firm",
            publication_year=1999,  # ge=2000 違反
            abstract_redacted="y",
            citation_url="z",
        )


# ========== AssistantQuery (LIL) ==========

def test_assistant_query_valid():
    q = AssistantQuery(
        lil_id="LIL-000001",
        query_text_redacted="(redacted query 200 字)",
        retrieved_cases=["PMI-000000012", "PMI-000000019"],
        retrieved_papers=["REF-000007", "REF-000023"],
        recommendation_ranked=[
            RecommendationItem(
                rank=1,
                recommendation_redacted="(redacted recommendation)",
                confidence=0.88,
                citation_array=["REF-000007", "PMI-000000012"],
            ),
        ],
        user_role="junior_consultant",
    )
    assert q.user_role == "junior_consultant"
    assert len(q.retrieved_cases) == 2


def test_assistant_query_invalid_user_role():
    with pytest.raises(ValidationError):
        AssistantQuery(
            lil_id="LIL-000001",
            query_text_redacted="x",
            user_role="ceo",  # enum 違反
        )


def test_assistant_query_invalid_recommendation_rank():
    with pytest.raises(ValidationError):
        AssistantQuery(
            lil_id="LIL-000001",
            query_text_redacted="x",
            recommendation_ranked=[
                RecommendationItem(
                    rank=11,  # le=10 違反
                    recommendation_redacted="y",
                    confidence=0.5,
                )
            ],
            user_role="junior_consultant",
        )


# ========== T5Output container ==========

def test_t5_output_valid():
    pmi = PMICase(
        pmi_id="PMI-000000001",
        industry="製造業",
        size_band="100-300",
        culture_profile="同族 + 関西",
        financial_band="30-50",
        integration_type="tuck-in",
        lifecycle_stage="final_outcome",
        summary_redacted="(redacted)",
    )
    out = T5Output(pmi_case=pmi)
    assert out.pmi_case.pmi_id == "PMI-000000001"
    assert out.decisions == []
    assert out.assistant_queries == []


def test_t5_output_full_collection():
    pmi = PMICase(
        pmi_id="PMI-000000001",
        industry="製造業", size_band="100-300", culture_profile="x",
        financial_band="30-50", integration_type="tuck-in",
        lifecycle_stage="final_outcome", summary_redacted="y",
    )
    dec = Decision(
        dec_id="DEC-000001", pmi_id="PMI-000000001",
        decision_topic="x", rationale_redacted="y",
        decision_at_day_n=0, decision_maker_role="z",
    )
    out_item = Outcome(
        out_id="OUT-000001", dec_id="DEC-000001",
        measurable_kpi_delta={"k": 0.5},
        outcome_class="success", outcome_at_day_n=100,
        retrospective_redacted="r",
    )
    container = T5Output(
        pmi_case=pmi,
        decisions=[dec],
        outcomes=[out_item],
    )
    assert len(container.decisions) == 1
    assert len(container.outcomes) == 1
    assert container.decisions[0].dec_id == "DEC-000001"


# ========== PII boundary basic test ==========

def test_pii_boundary_no_raw_field_in_operational_schema():
    """operational schema (本 module 全 type) に raw_* / *_full / *_name field が literal 存在しないことを literal verify (internal ADR + internal ADR PII/Op 分離順守)。"""
    import src.schema.types as types_module
    forbidden_field_keywords = [
        "raw_rationale", "raw_text", "raw_retrospective", "raw_query_text",
        "name_full", "decision_maker_name", "user_name", "paper_signatory",
        "raw_company_name", "raw_owner_name",
    ]
    # 全 BaseModel subclass の field を inspect
    for attr_name in dir(types_module):
        attr = getattr(types_module, attr_name)
        if hasattr(attr, "model_fields"):
            for field_name in attr.model_fields.keys():
                for forbidden in forbidden_field_keywords:
                    assert forbidden not in field_name, \
                        f"PII boundary violation: {attr_name}.{field_name} contains forbidden keyword '{forbidden}'"

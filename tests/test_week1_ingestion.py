"""T1-T4 → T5 ingestion regression test (Week 1、 internal ADR mapping rule 順守)"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.integration.ingest_t1_t4_output import (
    T1_T4_T5_MAPPING,
    ingest_all_t1_to_t4,
    ingest_t1_pair_to_pmi_source,
    ingest_t3_jp_pattern_to_pat,
    ingest_t4_cockpit_to_pmi,
    ingest_t4_driver_next_action,
)
from src.schema.types import Decision, Outcome, PMICase, Pattern, T1SourcePair


# ========== T4 CockpitProject → PMICase ==========

def test_t4_cp_to_pmi_basic():
    cp = {"cp_id": "CP-000019", "status": "final_outcome"}
    pmi = ingest_t4_cockpit_to_pmi(cp, pmi_index=0)
    assert pmi.pmi_id == "PMI-000000001"
    assert pmi.source_t4_cp_id == "CP-000019"
    assert pmi.lifecycle_stage == "final_outcome"


def test_t4_cp_to_pmi_with_t3_link():
    cp = {"cp_id": "CP-000020", "source_t3_ip_id": "IP-000000012", "status": "monitoring"}
    pmi = ingest_t4_cockpit_to_pmi(cp, pmi_index=5)
    assert pmi.pmi_id == "PMI-000000006"
    assert pmi.source_t3_ip_id == "IP-000000012"
    assert pmi.lifecycle_stage == "day100_complete"


def test_t4_cp_to_pmi_default_status():
    cp = {"cp_id": "CP-000021"}
    pmi = ingest_t4_cockpit_to_pmi(cp, pmi_index=10)
    assert pmi.lifecycle_stage == "day100_complete"  # default monitoring


# ========== T4 DriverInsight + NextAction → Decision + Outcome ==========

def test_t4_dr_na_completed_mapping():
    dr = {
        "dr_id": "DR-000001",
        "insight_statement_redacted": "(redacted insight)",
        "kpi_delta": {"retention_rate_90day": 0.92},
    }
    na = {
        "na_id": "NA-000001",
        "action_statement_redacted": "(redacted action)",
        "status": "completed",
        "priority_rank": 1,
        "due_day_n": 30,
    }
    dec, out = ingest_t4_driver_next_action("PMI-000000001", dr, na, dec_index=1, out_index=1)
    assert dec.status == "approved"
    assert out.outcome_class == "success"
    assert out.dec_id == dec.dec_id  # 1-to-1 link


def test_t4_dr_na_failed_mapping():
    dr = {"dr_id": "DR-000002", "insight_statement_redacted": "x", "kpi_delta": {}}
    na = {"na_id": "NA-000002", "action_statement_redacted": "y", "status": "failed", "due_day_n": 60}
    dec, out = ingest_t4_driver_next_action("PMI-000000001", dr, na, dec_index=2, out_index=2)
    assert dec.status == "rejected"
    assert out.outcome_class == "failure"


def test_t4_dr_na_in_progress_mapping():
    dr = {"dr_id": "DR-000003", "insight_statement_redacted": "x", "kpi_delta": {}}
    na = {"na_id": "NA-000003", "action_statement_redacted": "y", "status": "in_progress", "due_day_n": 45}
    dec, out = ingest_t4_driver_next_action("PMI-000000001", dr, na, dec_index=3, out_index=3)
    assert dec.status == "pending"
    assert out.outcome_class == "partial"


def test_t4_dr_na_kpi_delta_inherit():
    dr = {
        "dr_id": "DR-000004",
        "insight_statement_redacted": "x",
        "kpi_delta": {"retention_rate_90day": 0.85, "cost_synergy_delta_pct": 0.05},
    }
    na = {"na_id": "NA-000004", "action_statement_redacted": "y", "status": "completed", "due_day_n": 90}
    _, out = ingest_t4_driver_next_action("PMI-000000001", dr, na, dec_index=4, out_index=4)
    assert out.measurable_kpi_delta["retention_rate_90day"] == 0.85
    assert out.measurable_kpi_delta["cost_synergy_delta_pct"] == 0.05


# ========== T3 JPDay1Pattern → Pattern ==========

def test_t3_jpd1_to_pat_basic():
    jpd1 = {"axis": "union_relation", "severity": 75, "summary_redacted": "組合 retention high"}
    pat = ingest_t3_jp_pattern_to_pat(jpd1, pat_index=1, industry="製造業")
    assert pat.pat_id == "PAT-000001"
    assert "union_relation" in pat.pattern_name
    assert pat.pattern_dimension.industry == "製造業"


def test_t3_jpd1_severity_to_confidence():
    jpd1 = {"axis": "family_integration", "severity": 90, "summary_redacted": "x"}
    pat = ingest_t3_jp_pattern_to_pat(jpd1, pat_index=2)
    assert 0.85 <= pat.confidence <= 0.95  # severity 90 → confidence 0.90 cap 0.95


def test_t3_jpd1_low_severity_floor():
    jpd1 = {"axis": "trade_custom", "severity": 10, "summary_redacted": "x"}
    pat = ingest_t3_jp_pattern_to_pat(jpd1, pat_index=3)
    assert pat.confidence == 0.50  # severity 10 → 0.10、 max with floor 0.50


# ========== T1 pair ==========

def test_t1_pair_basic():
    pair = ingest_t1_pair_to_pmi_source("PROF-000123", "COMP-00045")
    assert isinstance(pair, T1SourcePair)
    assert pair.prof_id == "PROF-000123"
    assert pair.comp_id == "COMP-00045"


def test_t1_pair_invalid_prof():
    with pytest.raises(ValidationError):
        ingest_t1_pair_to_pmi_source("PROF-1", "COMP-00045")


# ========== ingest_all_t1_to_t4 entry ==========

def test_ingest_all_minimal():
    t4_cp = [{"cp_id": "CP-000001", "status": "final_outcome", "driver_insights": [], "next_actions": []}]
    out = ingest_all_t1_to_t4([], [], [], t4_cp)
    assert isinstance(out.pmi_case, PMICase)
    assert out.decisions == []
    assert out.outcomes == []
    assert out.patterns == []


def test_ingest_all_with_t1_t2_t3_t4():
    t1_pairs = [{"prof_id": "PROF-000123", "comp_id": "COMP-00045"}]
    t2_ddp = [{"ddp_id": "DDP-000007"}]
    t3_ip = [
        {
            "ip_id": "IP-000000012",
            "jp_day1_patterns": [
                {"axis": "union_relation", "severity": 80, "summary_redacted": "x"},
                {"axis": "bank_relation", "severity": 60, "summary_redacted": "y"},
            ],
        }
    ]
    t4_cp = [
        {
            "cp_id": "CP-000019",
            "source_t3_ip_id": "IP-000000012",
            "status": "final_outcome",
            "driver_insights": [
                {"dr_id": "DR-000001", "insight_statement_redacted": "i1", "kpi_delta": {"k": 0.9}},
                {"dr_id": "DR-000002", "insight_statement_redacted": "i2", "kpi_delta": {"k": 0.85}},
            ],
            "next_actions": [
                {"na_id": "NA-000001", "action_statement_redacted": "a1", "status": "completed", "due_day_n": 30},
                {"na_id": "NA-000002", "action_statement_redacted": "a2", "status": "in_progress", "due_day_n": 60},
            ],
        }
    ]
    out = ingest_all_t1_to_t4(t1_pairs, t2_ddp, t3_ip, t4_cp)
    assert out.pmi_case.source_t1_pair.prof_id == "PROF-000123"
    assert out.pmi_case.source_t2_ddp_id == "DDP-000007"
    assert out.pmi_case.source_t3_ip_id == "IP-000000012"
    assert out.pmi_case.source_t4_cp_id == "CP-000019"
    assert len(out.decisions) == 2
    assert len(out.outcomes) == 2
    assert len(out.patterns) == 2  # 2 jpd1 patterns


def test_ingest_all_missing_t4_raises():
    with pytest.raises(ValueError):
        ingest_all_t1_to_t4([], [], [], [])  # t4_cp_list 空


# ========== mapping SSoT ==========

def test_mapping_table_structure():
    assert "T1" in T1_T4_T5_MAPPING
    assert "T2" in T1_T4_T5_MAPPING
    assert "T3" in T1_T4_T5_MAPPING
    assert "T4" in T1_T4_T5_MAPPING
    assert "source" in T1_T4_T5_MAPPING["T1"]
    assert "lifecycle" in T1_T4_T5_MAPPING["T4"]


# ========== PII boundary ==========

def test_pii_boundary_no_raw_in_ingest_module():
    """ingest module で raw_* / *_full / *_name field を literal 生成しない verify。"""
    import src.integration.ingest_t1_t4_output as ingest_module
    source = ingest_module.__file__
    with open(source, encoding="utf-8") as f:
        content = f.read()
    forbidden = ["raw_rationale", "raw_retrospective", "raw_company_name", "decision_maker_name", "user_name"]
    for kw in forbidden:
        assert kw not in content, f"PII boundary violation: {kw} found in ingest module"

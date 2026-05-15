"""T1-T4 → T5 ingestion

T1 sourcing stage / T2 DD stage / T3 integration stage / T4 cockpit stage の各 API output dict を
T5 PMICase lifecycle entity + Decision + Outcome + Pattern + ReferencePaper に literal 変換。

mapping rule:
- T1 ProfileOp + CompanyOp pair → PMICase.source_t1_pair (lifecycle = matched / sourcing_complete)
- T2 DDP → PMICase.source_t2_ddp_id (lifecycle = dd_complete)、 Citation → ReferencePaper inherit candidate
- T3 IntegrationPlan → PMICase.source_t3_ip_id (lifecycle = day1_complete / integration_in_progress)、
  PlanNode + RiskScore → Decision + Outcome、 JPDay1Pattern → Pattern source
- T4 CockpitProject → PMICase.source_t4_cp_id (lifecycle = day100_complete / final_outcome)、
  DriverInsight + NextAction → Decision + Outcome、 SentimentEvent + VendorContract + RetentionRisk → PMICase dimension

入力 = dict (T1-T4 file の literal import 禁止、 cross-repo dependency 回避)、 出力 = T5 Pydantic instance。
PII boundary: T1-T4 既 redact 済 literal 前提 (T1-T4 ADR 順守)、 T5 で再 redact 不要。
"""
from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from src.schema.types import (
    Decision,
    Outcome,
    PMICase,
    Pattern,
    PatternDimension,
    PatternWeight,
    ReferencePaper,
    T1SourcePair,
    T5Output,
)

# === mapping table SSoT ===
T1_T4_T5_MAPPING = {
    "T1": {
        "source": "prof_id + comp_id pair → PMICase.source_t1_pair",
        "lifecycle": "matched / sourcing_complete",
    },
    "T2": {
        "source": "ddp_id → PMICase.source_t2_ddp_id",
        "lifecycle": "dd_complete",
        "extra": "answer + citation → Decision + ReferencePaper inherit",
    },
    "T3": {
        "source": "ip_id → PMICase.source_t3_ip_id",
        "lifecycle": "day1_complete / integration_in_progress",
        "extra": "plan_node + risk_score → Decision + Outcome、 jp_day1_pattern → Pattern source",
    },
    "T4": {
        "source": "cp_id → PMICase.source_t4_cp_id",
        "lifecycle": "day100_complete / final_outcome",
        "extra": "driver_insight + next_action → Decision + Outcome、 sentiment + vendor + retention → PMICase dimension",
    },
}


# === helper: PMI id generator (literal sequential、 PoC) ===
def _next_pmi_id(existing_count: int) -> str:
    return f"PMI-{existing_count + 1:09d}"


# === T4 CockpitProject → PMICase ===
def ingest_t4_cockpit_to_pmi(
    cp_dict: dict[str, Any],
    pmi_index: int,
    industry: str = "製造業",
    size_band: str = "100-300",
    culture_profile: str = "同族 + 関東",
    financial_band: str = "30-50",
    integration_type: str = "tuck-in",
) -> PMICase:
    """T4 CockpitProject dict → T5 PMICase (lifecycle = day100_complete or final_outcome)。

    cp_dict expected fields:
      - cp_id: "CP-XXXXXX"
      - source_t3_ip_id: "IP-XXXXXXXXX" (optional)
      - status: "monitoring" / "final_outcome"
    """
    cp_id = cp_dict["cp_id"]
    source_t3_ip_id = cp_dict.get("source_t3_ip_id")
    status = cp_dict.get("status", "monitoring")
    lifecycle = "final_outcome" if status == "final_outcome" else "day100_complete"

    return PMICase(
        pmi_id=_next_pmi_id(pmi_index),
        industry=industry,
        size_band=size_band,
        culture_profile=culture_profile,
        financial_band=financial_band,
        integration_type=integration_type,
        lifecycle_stage=lifecycle,
        source_t4_cp_id=cp_id,
        source_t3_ip_id=source_t3_ip_id,
        summary_redacted=f"(redacted summary、 from T4 CP {cp_id})",
        generated_at=datetime.now(timezone.utc),
    )


# === T4 DriverInsight + NextAction → Decision + Outcome ===
def ingest_t4_driver_next_action(
    pmi_id: str,
    driver_insight: dict[str, Any],
    next_action: dict[str, Any],
    dec_index: int,
    out_index: int,
) -> tuple[Decision, Outcome]:
    """T4 DriverInsight + NextAction pair → T5 Decision + Outcome 1:1 mapping。

    driver_insight expected:
      - dr_id: "DR-XXXXXX"
      - insight_statement_redacted: str
      - driver_factors: list[str]

    next_action expected:
      - na_id: "NA-XXXXXX"
      - action_statement_redacted: str
      - status: "completed" / "in_progress" / "failed"
      - priority_rank: int
      - due_day_n: int
    """
    dec_id = f"DEC-{dec_index:06d}"
    out_id = f"OUT-{out_index:06d}"

    # decision: NextAction status → Decision status mapping
    na_status = next_action.get("status", "in_progress")
    if na_status == "completed":
        dec_status = "approved"
    elif na_status == "failed":
        dec_status = "rejected"
    else:
        dec_status = "pending"

    decision = Decision(
        dec_id=dec_id,
        pmi_id=pmi_id,
        decision_topic=driver_insight.get("insight_statement_redacted", "(redacted)")[:200],
        rationale_redacted=next_action.get("action_statement_redacted", "(redacted)")[:500],
        decision_at_day_n=next_action.get("due_day_n", 0),
        decision_maker_role="MAIS 担当 + オーナー",
        status=dec_status,
    )

    # outcome class: NextAction status → outcome_class mapping
    if na_status == "completed":
        outcome_class = "success"
    elif na_status == "failed":
        outcome_class = "failure"
    else:
        outcome_class = "partial"

    outcome = Outcome(
        out_id=out_id,
        dec_id=dec_id,
        measurable_kpi_delta=driver_insight.get("kpi_delta", {}),
        outcome_class=outcome_class,
        outcome_at_day_n=next_action.get("due_day_n", 0) + 30,
        retrospective_redacted=f"(redacted retrospective、 from T4 DR {driver_insight.get('dr_id', 'unknown')})",
    )

    return decision, outcome


# === T3 JPDay1Pattern → Pattern source ===
def ingest_t3_jp_pattern_to_pat(
    jpd1: dict[str, Any],
    pat_index: int,
    industry: str = "製造業",
) -> Pattern:
    """T3 JPDay1Pattern → T5 Pattern source 変換。

    jpd1 expected:
      - axis: "union_relation" / "bank_relation" / "family_integration" / "business_practice" / "trade_custom"
      - severity: int 0-100
      - summary_redacted: str
    """
    axis = jpd1.get("axis", "family_integration")
    summary = jpd1.get("summary_redacted", "(redacted)")
    severity = jpd1.get("severity", 50)

    return Pattern(
        pat_id=f"PAT-{pat_index:06d}",
        pattern_name=f"jp_day1_{axis} pattern (from T3)",
        pattern_dimension=PatternDimension(
            industry=industry,
            size_band="100-300",
            culture_profile=f"jp_day1 axis: {axis}",
            financial_band="30-50",
            integration_type="tuck-in",
        ),
        weight=PatternWeight(),
        cross_case_evidence_redacted=summary[:500],
        source_count=max(1, severity // 10),
        confidence=min(0.95, max(0.50, severity / 100.0)),
    )


# === T1 ProfileOp + CompanyOp pair → PMICase.source_t1_pair ===
def ingest_t1_pair_to_pmi_source(
    prof_id: str,
    comp_id: str,
) -> T1SourcePair:
    """T1 ProfileOp + CompanyOp pair → PMICase.source_t1_pair 直接 mapping。"""
    return T1SourcePair(prof_id=prof_id, comp_id=comp_id)


# === T2 DDP → PMICase.source_t2_ddp_id mapping ===
# T2 Citation → ReferencePaper inherit candidate は ingestion 時に optional、 paper RAG phase で literal active 化


# === entry: T1-T4 全件統合 ingest ===
def ingest_all_t1_to_t4(
    t1_pairs: list[dict[str, str]],
    t2_ddp_list: list[dict[str, Any]],
    t3_ip_list: list[dict[str, Any]],
    t4_cp_list: list[dict[str, Any]],
    starting_pmi_index: int = 0,
    starting_dec_index: int = 1,
    starting_out_index: int = 1,
    starting_pat_index: int = 1,
) -> T5Output:
    """T1-T4 全件 dict input → T5Output container。 PoC scope = T4 主軸 (T1-T3 supplementary)。"""
    if not t4_cp_list:
        raise ValueError("ingest_all_t1_to_t4: t4_cp_list は literal 必須 (主軸 PMI case source)")

    # 1 PMI case を T4 主軸で literal 構築 (PoC scope = single PMI per call)
    cp = t4_cp_list[0]
    pmi_case = ingest_t4_cockpit_to_pmi(cp, starting_pmi_index)

    # T1 pair literal attach (optional、 first pair only)
    if t1_pairs:
        pair = t1_pairs[0]
        pmi_case.source_t1_pair = ingest_t1_pair_to_pmi_source(pair["prof_id"], pair["comp_id"])

    # T2 DDP literal attach (optional、 first DDP only)
    if t2_ddp_list:
        pmi_case.source_t2_ddp_id = t2_ddp_list[0]["ddp_id"]

    # Decision + Outcome 抽出 (T4 DR + NA pair)
    decisions: list[Decision] = []
    outcomes: list[Outcome] = []
    dec_idx = starting_dec_index
    out_idx = starting_out_index
    drivers = cp.get("driver_insights", [])
    actions = cp.get("next_actions", [])
    for dr, na in zip(drivers, actions):
        dec, out_item = ingest_t4_driver_next_action(
            pmi_case.pmi_id, dr, na, dec_idx, out_idx,
        )
        decisions.append(dec)
        outcomes.append(out_item)
        dec_idx += 1
        out_idx += 1

    # Pattern 抽出 (T3 JPDay1Pattern)
    patterns: list[Pattern] = []
    pat_idx = starting_pat_index
    for ip in t3_ip_list:
        for jpd1 in ip.get("jp_day1_patterns", []):
            patterns.append(ingest_t3_jp_pattern_to_pat(jpd1, pat_idx, industry=pmi_case.industry))
            pat_idx += 1

    return T5Output(
        pmi_case=pmi_case,
        decisions=decisions,
        outcomes=outcomes,
        patterns=patterns,
    )

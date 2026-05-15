"""T5 Object Type Pydantic schema

5/6 extend (DEC/PAT/PMI/REF/OUT、 internal Object Type natural extension) + 1/6 新規起草 (LIL、 audit trail specific 立証責任明記)。
PII/Op 分離全 type 順守、 operational layer のみ literal 定義 (vault layer は src/vault/ で別途)。
"""
from __future__ import annotations

from typing import Literal, Optional
from datetime import datetime

from pydantic import BaseModel, Field


# === Enums (literal 固定 vocabulary) ===

LifecycleStage = Literal[
    "matched", "sourcing_complete", "dd_complete",
    "day1_complete", "integration_in_progress",
    "day100_complete", "final_outcome",
]
SizeBand = Literal["under_50", "50-100", "100-300", "300-500", "500-1000", "over_1000"]
FinancialBand = Literal["5-10", "10-30", "30-50", "50-100", "over_100"]
IntegrationType = Literal["standalone", "tuck-in", "asset_purchase", "merger_of_equals"]
DecisionStatus = Literal["pending", "approved", "rejected", "superseded"]
OutcomeClass = Literal["success", "failure", "partial"]
Publisher = Literal["top-tier consulting firm", "top-tier PMI advisor", "top-tier consulting firm", "Other"]
UserRole = Literal["junior_consultant", "senior_consultant", "fde", "admin"]


# === ID prefix patterns ===
PMI_PATTERN = r"^PMI-[0-9]{9}$"
DEC_PATTERN = r"^DEC-[0-9]{6}$"
OUT_PATTERN = r"^OUT-[0-9]{6}$"
PAT_PATTERN = r"^PAT-[0-9]{6}$"
REF_PATTERN = r"^REF-[0-9]{6}$"
LIL_PATTERN = r"^LIL-[0-9]{6}$"
# T1-T4 reference patterns (foreign key validation 用)
PROF_PATTERN = r"^PROF-[0-9]{6}$"
COMP_PATTERN = r"^COMP-[0-9]{5}$"
DDP_PATTERN = r"^DDP-[0-9]{6}$"
IP_PATTERN = r"^IP-[0-9]{9}$"
CP_PATTERN = r"^CP-[0-9]{6}$"


# === Helper: T1 source pair (PROF + COMP) ===

class T1SourcePair(BaseModel):
    prof_id: str = Field(..., pattern=PROF_PATTERN)
    comp_id: str = Field(..., pattern=COMP_PATTERN)


# === 1. Decision (DEC、 internal Decision extend、 立証不要) ===

class Decision(BaseModel):
    """internal Decision extend。 PMI 案件内個別 decision の ADR-style 構造化。"""
    dec_id: str = Field(..., pattern=DEC_PATTERN)
    pmi_id: str = Field(..., pattern=PMI_PATTERN, description="FK to PMICase")
    decision_topic: str = Field(..., max_length=200)
    rationale_redacted: str = Field(..., max_length=500, description="Presidio redact 済、 raw_rationale は vault layer")
    decision_at_day_n: int = Field(..., ge=-90, le=100, description="PMI lifecycle day index (-30 〜 +100 範囲、 -90 まで pre-DD allow)")
    decision_maker_role: str = Field(..., max_length=100, description="redacted role、 名前 NG")
    status: DecisionStatus = "pending"


# === 2. Pattern (PAT、 internal Pattern extend、 立証不要) ===

class PatternDimension(BaseModel):
    industry: str
    size_band: SizeBand
    culture_profile: str = Field(..., max_length=200)
    financial_band: FinancialBand
    integration_type: IntegrationType


class PatternWeight(BaseModel):
    """5 dim weight (PoC = literal hardcode、 移植 = learning-based)。 sum = 1.0 必須。"""
    industry: float = Field(default=0.30, ge=0.0, le=1.0)
    size: float = Field(default=0.20, ge=0.0, le=1.0)
    culture: float = Field(default=0.25, ge=0.0, le=1.0)
    financial: float = Field(default=0.10, ge=0.0, le=1.0)
    integration_type: float = Field(default=0.15, ge=0.0, le=1.0)


class Pattern(BaseModel):
    """internal Pattern extend。 cross-case 抽出 PMI pattern。"""
    pat_id: str = Field(..., pattern=PAT_PATTERN)
    pattern_name: str = Field(..., max_length=200)
    pattern_dimension: PatternDimension
    weight: PatternWeight = Field(default_factory=PatternWeight)
    cross_case_evidence_redacted: str = Field(..., max_length=500, description="N=12 cases redact 済")
    source_count: int = Field(..., ge=1)
    confidence: float = Field(..., ge=0.0, le=1.0)


# === 3. PMICase (PMI、 internal Incident extend、 軽度立証) ===

class PMICase(BaseModel):
    """internal Incident extend。 PMI 案件 lifecycle 全段階 root entity。"""
    pmi_id: str = Field(..., pattern=PMI_PATTERN)
    industry: str = Field(..., max_length=100)
    size_band: SizeBand
    culture_profile: str = Field(..., max_length=300, description="redacted、 例: 同族 + 関西本社 + 創業 50 年")
    financial_band: FinancialBand
    integration_type: IntegrationType
    lifecycle_stage: LifecycleStage
    source_t1_pair: Optional[T1SourcePair] = None
    source_t2_ddp_id: Optional[str] = Field(default=None, pattern=DDP_PATTERN)
    source_t3_ip_id: Optional[str] = Field(default=None, pattern=IP_PATTERN)
    source_t4_cp_id: Optional[str] = Field(default=None, pattern=CP_PATTERN)
    summary_redacted: str = Field(..., max_length=300)
    generated_at: datetime = Field(default_factory=datetime.now)


# === 4. Outcome (OUT、 Pattern overlay extend、 中度立証) ===

class Outcome(BaseModel):
    """internal Pattern overlay extend。 Decision 結果 measurable KPI delta + outcome_class。"""
    out_id: str = Field(..., pattern=OUT_PATTERN)
    dec_id: str = Field(..., pattern=DEC_PATTERN, description="FK to Decision")
    measurable_kpi_delta: dict[str, float] = Field(
        ..., description="例: {retention_rate_90day: 0.92, union_engagement_score: 8.3, cost_synergy_delta_pct: 0.07}"
    )
    outcome_class: OutcomeClass
    outcome_at_day_n: int = Field(..., ge=-30, le=365)
    retrospective_redacted: str = Field(..., max_length=300)


# === 5. ReferencePaper (REF、 internal FileResource extend、 軽度立証) ===

class PaperChunk(BaseModel):
    """ReferencePaper 内 chunk (docling parse output + embed)。"""
    chunk_id: str = Field(..., pattern=r"^CHK-[0-9]{6}$")
    page: int = Field(..., ge=1)
    text_redacted: str = Field(..., max_length=2000)
    embedding_id: str = Field(..., max_length=100)


class ReferencePaper(BaseModel):
    """internal FileResource extend。 paper RAG ingestion entity (PoC = 合成 paper)。"""
    ref_id: str = Field(..., pattern=REF_PATTERN)
    paper_title_redacted: str = Field(..., max_length=300)
    publisher: Publisher
    publication_year: int = Field(..., ge=2000, le=2030)
    chunks: list[PaperChunk] = Field(default_factory=list)
    abstract_redacted: str = Field(..., max_length=500)
    citation_url: str = Field(..., max_length=300, description="PoC = synthetic://publisher/year/slug")


# === 6. AssistantQuery ===

class RecommendationItem(BaseModel):
    """Assistant recommendation ranked item。"""
    rank: int = Field(..., ge=1, le=10)
    recommendation_redacted: str = Field(..., max_length=500)
    confidence: float = Field(..., ge=0.0, le=1.0)
    citation_array: list[str] = Field(default_factory=list, description="list of REF-id / PMI-id citations")


class AssistantQuery(BaseModel):
    """新規起草。 doctrine: analogical-recall doctrine literal 実装基盤の query trace 専用 type。
    既存 14 internal type で literal cover 不能 (query log sequence + transient retrieval result + ranked recommendation 軸が unique)。
    """
    lil_id: str = Field(..., pattern=LIL_PATTERN)
    query_text_redacted: str = Field(
        ..., max_length=200,
        description="redacted、 user/customer name は entity-replaced、 raw_query_text は vault layer",
    )
    retrieved_cases: list[str] = Field(
        default_factory=list, description="top-K=2-3 PMI-id list",
    )
    retrieved_papers: list[str] = Field(
        default_factory=list, description="top-K=3-5 REF-id list",
    )
    recommendation_ranked: list[RecommendationItem] = Field(default_factory=list)
    audit_at: datetime = Field(default_factory=datetime.now)
    user_role: UserRole


# === T5Output container (Week 1 ingestion 結果 + Week 2-3 retrieval/Assistant 結果 統合) ===

class T5Output(BaseModel):
    """T5 単一 case 全 type collection (T1-T4 → T5 ingestion + Week 2-3 augmentation 結果)。"""
    pmi_case: PMICase
    decisions: list[Decision] = Field(default_factory=list)
    outcomes: list[Outcome] = Field(default_factory=list)
    patterns: list[Pattern] = Field(default_factory=list, description="cross-case 抽出 pattern、 PMI 単独でなく集合体")
    reference_papers: list[ReferencePaper] = Field(default_factory=list)
    assistant_queries: list[AssistantQuery] = Field(default_factory=list, description="audit trail")

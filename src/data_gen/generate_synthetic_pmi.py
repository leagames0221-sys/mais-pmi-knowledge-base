"""合成 PMI case data generator (Week 1、 Faker + 業種テンプレ + seed 固定)

internal ADR 順守、 6 Object Type で 30 PMI + 200 DEC + 200 OUT + 20 PAT + 50 paper 生成。
PII/Op 分離 operational layer のみ literal 生成 (vault layer 別途、 Week 4 で active)。
output: data/pmi_synthetic/ 配下 jsonl (.gitignore で literal exclude 済、 PoC artifact)。
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from faker import Faker

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
)

# === seed (doctrine: verify-priority 再現性) ===
SYNTHETIC_SEED = 20260514
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "pmi_synthetic"

# === 業種テンプレ (eval set 26 industry subset、 PoC scope は 12 種) ===
INDUSTRY_TEMPLATES = [
    "製造業", "出版", "小売", "IT サービス", "卸売",
    "物流", "建設", "飲食", "印刷", "食品製造",
    "化学", "医療法人",
]
SIZE_BANDS = ["under_50", "50-100", "100-300", "300-500", "500-1000", "over_1000"]
FINANCIAL_BANDS = ["5-10", "10-30", "30-50", "50-100", "over_100"]
INTEGRATION_TYPES = ["standalone", "tuck-in", "asset_purchase", "merger_of_equals"]
CULTURE_PROFILES = [
    "同族経営 + 関東", "同族経営 + 関西", "創業者経営 + 関東", "創業者経営 + 関西",
    "雇われ経営 + 東京", "雇われ経営 + 関西", "大手子会社 + 関東", "大手子会社 + multi-region",
]
LIFECYCLE_STAGES = [
    "matched", "sourcing_complete", "dd_complete",
    "day1_complete", "integration_in_progress",
    "day100_complete", "final_outcome",
]
DECISION_STATUSES = ["pending", "approved", "rejected", "superseded"]
OUTCOME_CLASSES = ["success", "failure", "partial"]
PUBLISHERS = ["top-tier consulting firm", "top-tier PMI advisor", "top-tier consulting firm", "Other"]
USER_ROLES = ["junior_consultant", "senior_consultant", "fde", "admin"]


# === Windows cp932 UTF-8 reconfigure (T3 学び cross-PJ universal pattern) ===
def _ensure_utf8_stdout() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# === ID generators ===
def _pmi_id(i: int) -> str:
    return f"PMI-{i:09d}"


def _dec_id(i: int) -> str:
    return f"DEC-{i:06d}"


def _out_id(i: int) -> str:
    return f"OUT-{i:06d}"


def _pat_id(i: int) -> str:
    return f"PAT-{i:06d}"


def _ref_id(i: int) -> str:
    return f"REF-{i:06d}"


def _lil_id(i: int) -> str:
    return f"LIL-{i:06d}"


def _chk_id(i: int) -> str:
    return f"CHK-{i:06d}"


# === PMICase 生成 ===
def generate_pmi_cases(count: int, fake: Faker, rng: random.Random) -> list[PMICase]:
    cases: list[PMICase] = []
    for i in range(1, count + 1):
        cases.append(PMICase(
            pmi_id=_pmi_id(i),
            industry=rng.choice(INDUSTRY_TEMPLATES),
            size_band=rng.choice(SIZE_BANDS),
            culture_profile=rng.choice(CULTURE_PROFILES) + f" + 創業 {rng.randint(20, 100)} 年",
            financial_band=rng.choice(FINANCIAL_BANDS),
            integration_type=rng.choice(INTEGRATION_TYPES),
            lifecycle_stage=rng.choice(LIFECYCLE_STAGES),
            source_t1_pair=T1SourcePair(
                prof_id=f"PROF-{rng.randint(1, 999999):06d}",
                comp_id=f"COMP-{rng.randint(1, 99999):05d}",
            ),
            source_t2_ddp_id=f"DDP-{rng.randint(1, 999999):06d}",
            source_t3_ip_id=f"IP-{rng.randint(1, 999999999):09d}",
            source_t4_cp_id=f"CP-{rng.randint(1, 999999):06d}",
            summary_redacted=f"(redacted PMI case summary、 case #{i}、 業種 / 規模 / 文化 / 統合 type 多軸 instance)",
            generated_at=datetime.now(timezone.utc),
        ))
    return cases


# === Decision 生成 (1 PMI に 約 6-7 件 = total 200) ===
def generate_decisions(pmi_cases: list[PMICase], total: int, rng: random.Random) -> list[Decision]:
    decisions: list[Decision] = []
    per_case = total // len(pmi_cases)
    extras = total % len(pmi_cases)
    counter = 1
    for idx, pmi in enumerate(pmi_cases):
        n = per_case + (1 if idx < extras else 0)
        for _ in range(n):
            decisions.append(Decision(
                dec_id=_dec_id(counter),
                pmi_id=pmi.pmi_id,
                decision_topic=rng.choice([
                    "Day-1 統合 governance 方針", "key talent retention package",
                    "vendor 統合 priority", "IT system migration sequence",
                    "ブランド統合 timing", "工場統廃合 schedule",
                    "取引銀行折衝 priority", "労使協議 timeline",
                ]),
                rationale_redacted=f"(redacted rationale、 decision #{counter})",
                decision_at_day_n=rng.randint(-30, 100),
                decision_maker_role=rng.choice(["MAIS 担当 + オーナー", "CFO + 外部 advisor", "CEO + 経営企画"]),
                status=rng.choice(DECISION_STATUSES),
            ))
            counter += 1
    return decisions


# === Outcome 生成 (1 Decision に 1 Outcome 対応、 total 200) ===
def generate_outcomes(decisions: list[Decision], rng: random.Random) -> list[Outcome]:
    outcomes: list[Outcome] = []
    for i, dec in enumerate(decisions, start=1):
        outcomes.append(Outcome(
            out_id=_out_id(i),
            dec_id=dec.dec_id,
            measurable_kpi_delta={
                "retention_rate_90day": round(rng.uniform(0.70, 0.98), 2),
                "union_engagement_score": round(rng.uniform(5.0, 9.5), 1),
                "cost_synergy_delta_pct": round(rng.uniform(-0.05, 0.20), 3),
            },
            outcome_class=rng.choice(OUTCOME_CLASSES),
            outcome_at_day_n=dec.decision_at_day_n + rng.randint(30, 90),
            retrospective_redacted=f"(redacted retrospective、 outcome #{i})",
        ))
    return outcomes


# === Pattern 生成 (cross-case 抽出 20 件) ===
def generate_patterns(count: int, rng: random.Random) -> list[Pattern]:
    patterns: list[Pattern] = []
    for i in range(1, count + 1):
        patterns.append(Pattern(
            pat_id=_pat_id(i),
            pattern_name=f"pattern #{i}: {rng.choice(INDUSTRY_TEMPLATES)} + {rng.choice(CULTURE_PROFILES)}",
            pattern_dimension=PatternDimension(
                industry=rng.choice(INDUSTRY_TEMPLATES),
                size_band=rng.choice(SIZE_BANDS),
                culture_profile=rng.choice(CULTURE_PROFILES),
                financial_band=rng.choice(FINANCIAL_BANDS),
                integration_type=rng.choice(INTEGRATION_TYPES),
            ),
            weight=PatternWeight(),
            cross_case_evidence_redacted=f"(N={rng.randint(5, 15)} cases、 redacted evidence、 pattern #{i})",
            source_count=rng.randint(5, 15),
            confidence=round(rng.uniform(0.60, 0.95), 2),
        ))
    return patterns


# === ReferencePaper 生成 (合成 paper 50 件、 publisher 4 種 + 各 paper 3-5 chunks) ===
def generate_papers(count: int, fake: Faker, rng: random.Random) -> list[ReferencePaper]:
    papers: list[ReferencePaper] = []
    chk_counter = 1
    paper_titles = [
        "Beyond First 100 Days", "Post-Merger Integration Playbook",
        "Synergy Capture Model", "Culture Integration Cross-Border",
        "HR Retention 36 Month Tracking", "Digital Integration for Traditional Sector",
        "SME M&A 100 Day Lessons", "Failure Pattern Analysis",
        "Day-30 KPI Tracking Framework", "Vendor Consolidation Best Practice",
    ]
    for i in range(1, count + 1):
        publisher = rng.choice(PUBLISHERS)
        title = rng.choice(paper_titles) + f" (Vol. {i})"
        chunk_count = rng.randint(3, 5)
        chunks: list[PaperChunk] = []
        for _ in range(chunk_count):
            chunks.append(PaperChunk(
                chunk_id=_chk_id(chk_counter),
                page=rng.randint(1, 50),
                text_redacted=f"(redacted paper chunk、 paper #{i}、 chunk_id={_chk_id(chk_counter)})",
                embedding_id=f"emb_{chk_counter:06d}",
            ))
            chk_counter += 1
        papers.append(ReferencePaper(
            ref_id=_ref_id(i),
            paper_title_redacted=title,
            publisher=publisher,
            publication_year=rng.randint(2020, 2026),
            chunks=chunks,
            abstract_redacted=f"(redacted abstract、 paper #{i}、 publisher={publisher})",
            citation_url=f"synthetic://{publisher.lower()}/{rng.randint(2020, 2026)}/paper-{i}",
        ))
    return papers


# === Assistant query 合成 (audit trail seed、 10 件) ===
def generate_assistant_queries(count: int, pmi_cases: list[PMICase], papers: list[ReferencePaper], rng: random.Random) -> list[AssistantQuery]:
    queries: list[AssistantQuery] = []
    for i in range(1, count + 1):
        topk_cases = rng.sample([p.pmi_id for p in pmi_cases], min(3, len(pmi_cases)))
        topk_papers = rng.sample([p.ref_id for p in papers], min(5, len(papers)))
        recs: list[RecommendationItem] = []
        for r in range(1, rng.randint(2, 4) + 1):
            recs.append(RecommendationItem(
                rank=r,
                recommendation_redacted=f"(redacted recommendation、 query #{i}、 rank {r})",
                confidence=round(rng.uniform(0.60, 0.95), 2),
                citation_array=rng.sample(topk_cases + topk_papers, min(2, len(topk_cases + topk_papers))),
            ))
        queries.append(AssistantQuery(
            lil_id=_lil_id(i),
            query_text_redacted=f"(redacted query #{i}、 多軸 PMI similar case retrieval)",
            retrieved_cases=topk_cases,
            retrieved_papers=topk_papers,
            recommendation_ranked=recs,
            audit_at=datetime.now(timezone.utc),
            user_role=rng.choice(USER_ROLES),
        ))
    return queries


# === serialize ===
def _to_jsonl_line(obj: Any) -> str:
    return obj.model_dump_json()


def write_jsonl(items: list[Any], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(_to_jsonl_line(item) + "\n")
    return len(items)


# === entry ===
def generate_all(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    n_pmi: int = 30,
    n_decisions: int = 200,
    n_patterns: int = 20,
    n_papers: int = 50,
    n_assistant: int = 10,
    seed: int = SYNTHETIC_SEED,
) -> dict[str, int]:
    """全 6 type 合成 data 生成 + jsonl write、 件数 dict 返却。"""
    _ensure_utf8_stdout()
    fake = Faker("ja_JP")
    Faker.seed(seed)
    rng = random.Random(seed)

    pmi_cases = generate_pmi_cases(n_pmi, fake, rng)
    decisions = generate_decisions(pmi_cases, n_decisions, rng)
    outcomes = generate_outcomes(decisions, rng)
    patterns = generate_patterns(n_patterns, rng)
    papers = generate_papers(n_papers, fake, rng)
    assistant_queries = generate_assistant_queries(n_assistant, pmi_cases, papers, rng)

    counts = {
        "pmi_cases": write_jsonl(pmi_cases, output_dir / "pmi_cases.jsonl"),
        "decisions": write_jsonl(decisions, output_dir / "decisions.jsonl"),
        "outcomes": write_jsonl(outcomes, output_dir / "outcomes.jsonl"),
        "patterns": write_jsonl(patterns, output_dir / "patterns.jsonl"),
        "papers": write_jsonl(papers, output_dir / "papers.jsonl"),
        "assistant_queries": write_jsonl(assistant_queries, output_dir / "assistant_queries.jsonl"),
    }
    return counts


if __name__ == "__main__":
    counts = generate_all()
    print("synthetic PMI data generated:")
    for k, v in counts.items():
        print(f"  {k}: {v}")

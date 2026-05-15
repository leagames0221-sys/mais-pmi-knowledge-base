"""合成 paper corpus 50 件 generator (internal ADR § 2 順守、 Faker + 業界 template 自作、 PII 不発設計)

module boundaries 段階 1 + 2:
- 段階 1: Faker (MIT、 lazy import) literal use OK
- 段階 2: top-tier consulting firm/top-tier PMI advisor/top-tier consulting firm 業界 template + Day-N retrospective + 5 dim categorical band 配備 (literal 自作)

PoC scope: PII 不発設計 (paper_signatory + acknowledgments_raw は vault 候補だが本 generator では generate しない、 redacted abstract のみ literal 配備)。
移植段階: 実 paper individual license confirm 必須 (doctrine: client-no-recovery)。
"""
from __future__ import annotations

import sys
from typing import Any

from ..retrieval.graphrag_native import check_pii_boundary

# Windows cp932 console UTF-8 reconfigure (T3 学び doctrine: analogical-recall inherit)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass


# ============================================================================
# Template constants (literal 自作、 top-tier consulting firm/top-tier PMI advisor/top-tier consulting firm 業界 PMI report 構造)
# ============================================================================

PUBLISHERS: tuple[str, ...] = ("top-tier consulting firm", "top-tier PMI advisor", "top-tier consulting firm", "Other")

PAPER_TITLE_TEMPLATES: tuple[str, ...] = (
    "Beyond First 100 Days — Generative AI in Post-Deal Integration",
    "PMI Playbook for Mid-Market Acquisitions in Japan {year}",
    "Cross-Border M&A Integration: 5 Capability Imperatives",
    "Day-1 Readiness Index for Manufacturing Mergers",
    "Cultural Integration Drivers in Family Business Acquisitions",
    "Synergy Capture Rates by Integration Type — Empirical Study",
    "AI-Enabled PMI: From Diligence to Day-100 Cockpit",
    "Retention as a Leading Indicator of M&A Success",
    "Tuck-in vs Merger-of-Equals: Operating Model Implications",
    "Post-Merger Integration Failures: 8 Anti-Patterns and Mitigations",
)

ABSTRACT_TEMPLATES: tuple[str, ...] = (
    (
        "This {publisher} report analyzes N={n} post-merger integration cases "
        "in the {industry} sector ({size_band} headcount range), with focus on "
        "{integration_type} deals. Key findings: retention rate at Day-90 was "
        "{retention:.0%}, cost synergy capture reached {cost_synergy:.0%} of target, "
        "and cultural integration delays explained {culture_drag:.0%} of timeline slippage. "
        "Methodology: redacted retrospective interviews + KPI deltas. "
        "(All identifying information redacted per {publisher} confidentiality policy.)"
    ),
    (
        "{publisher} reviewed {n} {industry} M&A transactions ({integration_type}) "
        "completed between {year_start}-{year_end}. Day-1 readiness score correlated "
        "{correlation:.2f} with Day-100 retention. Family-business acquisitions showed "
        "{culture_premium:.0%} higher retention when founder remained in advisory role. "
        "Report concludes: governance design + redacted decision log + cross-functional "
        "PMI office are the 3 capability imperatives. (Anonymized aggregate, no PII.)"
    ),
    (
        "Synergy capture analysis across {n} {industry} deals shows that "
        "{integration_type} structures captured {synergy_rate:.0%} of announced cost "
        "synergies within 24 months, vs {benchmark_rate:.0%} industry benchmark. "
        "AI-enabled vendor consolidation accelerated capture by {ai_uplift:.0%}. "
        "Risk: cultural fit assessment was the strongest predictor (β = {beta:.2f}). "
        "({publisher} {year} working paper, redacted findings.)"
    ),
)

SECTION_TEMPLATES: tuple[str, ...] = (
    "Executive Summary",
    "Methodology",
    "Findings: Day-1 Readiness",
    "Findings: Synergy Capture",
    "Findings: Cultural Integration",
    "Implications for PMI Office Design",
    "Limitations and Future Research",
    "Appendix A: Anonymized Case Vignettes",
)

INDUSTRY_OPTIONS: tuple[str, ...] = (
    "Manufacturing", "Industrial", "Consumer Goods", "Logistics",
    "Healthcare", "Financial Services", "Retail", "Wholesale",
    "Construction", "Food & Beverage", "Chemicals", "IT Services",
)

SIZE_BANDS: tuple[str, ...] = ("under_50", "50-100", "100-300", "300-500", "500-1000", "over_1000")
INTEGRATION_TYPES: tuple[str, ...] = ("standalone", "tuck-in", "asset_purchase", "merger_of_equals")


# ============================================================================
# Generator (Faker lazy import)
# ============================================================================


def _get_faker(seed: int = 42) -> Any:
    """Faker lazy singleton (test 環境で Faker 不在の場合 RuntimeError)。"""
    try:
        from faker import Faker  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Faker not installed (Week 1 requirements に既 pin 済、 internal ADR § 2)。 "
            "Run: pip install 'Faker>=20,<40'"
        ) from exc
    fake = Faker(["en_US", "ja_JP"])
    Faker.seed(seed)
    return fake


def _generate_abstract(template_idx: int, fake: Any, params: dict[str, Any]) -> str:
    """abstract template literal fill (PII redacted、 numeric KPI band 配備)。"""
    template = ABSTRACT_TEMPLATES[template_idx % len(ABSTRACT_TEMPLATES)]
    return template.format(**params)


def _generate_paper_markdown(
    title: str,
    publisher: str,
    year: int,
    abstract: str,
    sections: list[str],
    body_paragraphs_per_section: int = 3,
    fake: Any = None,
) -> str:
    """合成 paper markdown 構造化 (heading + abstract + section + redacted body)。"""
    lines: list[str] = [
        f"# {title}",
        "",
        f"**Publisher**: {publisher}　 **Year**: {year}　 **License**: synthetic (PoC only)",
        "",
        "## Abstract",
        "",
        abstract,
        "",
    ]
    for section in sections:
        lines.append(f"## {section}")
        lines.append("")
        for _ in range(body_paragraphs_per_section):
            if fake is not None:
                body = fake["en_US"].paragraph(nb_sentences=4) if isinstance(fake, dict) else fake.paragraph(nb_sentences=4)
            else:
                body = "(redacted body paragraph、 PoC synthetic content、 移植段階で実 paper individual license confirm)"
            lines.append(body)
            lines.append("")
    return "\n".join(lines)


def generate_synthetic_paper_corpus(
    n_papers: int = 50,
    seed: int = 42,
    start_ref_index: int = 1,
) -> list[dict[str, Any]]:
    """50 件 (default) 合成 paper corpus generate (Faker + 業界 template、 internal ADR § 2)。

    Args:
        n_papers: 生成件数 (default 50、 internal ADR § 2 順守)
        seed: Faker seed (default 42、 deterministic 担保)
        start_ref_index: REF id 開始 index (default 1 = REF-000001)

    Returns:
        list[{"ref_id": str, "title_redacted": str, "publisher": str, "publication_year": int,
              "abstract_redacted": str, "markdown": str, "sections": list[str]}]
        (src/schema/types.py ReferencePaper schema mapping 前 raw format)

    Raises:
        RuntimeError: Faker not installed
        ValueError: PII boundary violation in generated content (template bug detect 時)
    """
    if n_papers < 1:
        raise ValueError(f"n_papers must be >= 1, got {n_papers}")

    fake = _get_faker(seed=seed)
    papers: list[dict[str, Any]] = []

    for i in range(n_papers):
        ref_idx = start_ref_index + i
        ref_id = f"REF-{ref_idx:06d}"
        publisher = PUBLISHERS[i % len(PUBLISHERS)]
        year = 2020 + (i % 7)  # 2020-2026 spread
        industry = INDUSTRY_OPTIONS[i % len(INDUSTRY_OPTIONS)]
        size_band = SIZE_BANDS[i % len(SIZE_BANDS)]
        integration_type = INTEGRATION_TYPES[i % len(INTEGRATION_TYPES)]
        title_template = PAPER_TITLE_TEMPLATES[i % len(PAPER_TITLE_TEMPLATES)]
        title = title_template.format(year=year)
        # build deterministic KPI band per seed
        n_cases = 30 + (i * 7) % 200
        retention = 0.60 + ((i * 13) % 35) / 100.0
        cost_synergy = 0.35 + ((i * 17) % 50) / 100.0
        culture_drag = 0.10 + ((i * 19) % 30) / 100.0
        correlation = 0.40 + ((i * 11) % 50) / 100.0
        culture_premium = 0.05 + ((i * 23) % 30) / 100.0
        synergy_rate = 0.50 + ((i * 7) % 35) / 100.0
        benchmark_rate = 0.40 + ((i * 5) % 25) / 100.0
        ai_uplift = 0.10 + ((i * 3) % 30) / 100.0
        beta = 0.30 + ((i * 29) % 50) / 100.0

        abstract = _generate_abstract(
            i,
            fake,
            {
                "publisher": publisher,
                "n": n_cases,
                "industry": industry,
                "size_band": size_band,
                "integration_type": integration_type,
                "retention": retention,
                "cost_synergy": cost_synergy,
                "culture_drag": culture_drag,
                "correlation": correlation,
                "culture_premium": culture_premium,
                "year_start": year - 5,
                "year_end": year,
                "synergy_rate": synergy_rate,
                "benchmark_rate": benchmark_rate,
                "ai_uplift": ai_uplift,
                "beta": beta,
                "year": year,
            },
        )

        sections = list(SECTION_TEMPLATES)
        markdown = _generate_paper_markdown(
            title=title,
            publisher=publisher,
            year=year,
            abstract=abstract,
            sections=sections,
            body_paragraphs_per_section=2,
            fake=fake,
        )

        # PII boundary 二重防御 (template bug 検出時 raise、 generate 時点で literal verify)
        clean, detected = check_pii_boundary(markdown)
        if not clean:
            raise ValueError(
                f"PII boundary violation in generated paper {ref_id}: {detected}。 "
                "template bug suspect (internal ADR § 2 二重防御 evidence)"
            )

        papers.append(
            {
                "ref_id": ref_id,
                "title_redacted": title,
                "publisher": publisher,
                "publication_year": year,
                "abstract_redacted": abstract,
                "markdown": markdown,
                "sections": sections,
                "industry": industry,
                "size_band": size_band,
                "integration_type": integration_type,
                "citation_url": f"synthetic://{publisher.lower()}/{year}/{ref_id.lower()}",
            }
        )

    return papers


__all__ = [
    "PUBLISHERS",
    "PAPER_TITLE_TEMPLATES",
    "ABSTRACT_TEMPLATES",
    "SECTION_TEMPLATES",
    "INDUSTRY_OPTIONS",
    "SIZE_BANDS",
    "INTEGRATION_TYPES",
    "generate_synthetic_paper_corpus",
]

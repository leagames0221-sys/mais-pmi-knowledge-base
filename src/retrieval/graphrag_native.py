# Inspired by Microsoft GraphRAG (Apache-2.0, https://github.com/microsoft/graphrag) prompt
# template structure — decomposed prior art per doctrine: prior-art-first.
# NetworkX louvain_communities (BSD-3, NumFOCUS sponsored) thin wrapper.
# graph backend mode fix (2026-05-14): leiden_communities は NetworkX 3.6 で API dispatcher のみ
# (backend 必要、 NotImplementedError raise)、 louvain_communities = literal 標準実装
# (BSD-3、 backend 不要、 Leiden の前身 algorithm) に supersede。 doctrine: drift-prevention evidence。
"""GraphRAG コア要素 自作実装

module boundaries 越境境界線 3 段階 順守:
- 段階 1 OS-primitives: networkx (BSD-3) + anthropic SDK 経由 LLMProvider (literal use OK)
- 段階 2 business logic: 3 prompt 自作 + Ontology 80% gate + PII boundary check (literal 自作)
- 段階 3 framework 全体: Microsoft GraphRAG OSS 全体 inject 不採用 (decomposed prior art reference のみ)

graph backend mode fix history (2026-05-14):
- 旧: leiden_communities (NetworkX 3.6.1 で API dispatcher のみ、 backend 不在で NotImplementedError raise)
- 新: louvain_communities (NetworkX 標準実装 BSD-3、 backend 不要、 Leiden の前身 Louvain algorithm)
- 立証: PoC scope (entity count < 100) で Louvain disconnected community issue 不発、
  移植段階 = leidenalg (GPL viral 不採用) ではなく graspologic (R8 abandonment) でもなく、
  NetworkX backend 経由の leiden_communities active 化 path 確保 (doctrine: future-proof)
"""
from __future__ import annotations

import json
import re
import sys
from typing import TYPE_CHECKING, Literal

import networkx as nx
from pydantic import BaseModel, Field


def _strip_markdown_codeblock(text: str) -> str:
    """LLM response から markdown code block (```json ... ``` 等) を literal strip。

    PoC 段階 = OllamaProvider (gemma3:4b 等) で literal 観測される format、 ClaudeProvider は通常 fence なし。
    doctrine: future-proof: LLM 出力 format 差異吸収 (受託 deploy 段階で literal robust)。
    """
    stripped = text.strip()
    # ```json\n...\n``` or ```\n...\n``` を literal extract
    m = re.match(r"^```(?:json|JSON)?\s*\n(.*?)\n```\s*$", stripped, re.DOTALL)
    if m:
        return m.group(1).strip()
    return stripped

if TYPE_CHECKING:
    from ..llm.provider import LLMProvider

# Windows cp932 console UTF-8 reconfigure (T3 学び doctrine: analogical-recall)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8") # type: ignore[attr-defined]
    except Exception:
        pass


# ============================================================================
# Constants (Ontology gate + PII boundary 用 SSoT)
# ============================================================================

# existing internal 14 Object Type (internal/internal_kb/ontology/types.yaml inherit)
INTERNAL_OBJECT_TYPES: frozenset[str] = frozenset(
    {
        "PJ",
        "WO",
        "Skill",
        "FileResource",
        "Incident",
        "Decision",
        "Pattern",
        "Workaround",
        "Convention",
        "DoctrineRule",
        "InfoGovRule",
        "SecurityLayer",
        "BiasCandidate",
        "SynergyInteraction",
    }
)

# T5 6 type extend
T5_OBJECT_TYPES: frozenset[str] = frozenset(
    {
        "PMICase",
        "Outcome",
        "ReferencePaper",
        "AssistantQuery",
    }
)

# valid Object Type union (internal 14 + T5 4 新規/extend = 18 unique)
VALID_OBJECT_TYPES: frozenset[str] = INTERNAL_OBJECT_TYPES | T5_OBJECT_TYPES

# link_types 6 enum 固定
VALID_LINK_TYPES: frozenset[str] = frozenset(
    {
        "blocks",
        "caused_by",
        "solved_by",
        "related_to",
        "supersedes",
        "implements",
    }
)

# PII vault field 名
# detect 時 literal block + alert、 raw value embedding 完全禁止
# 設計 intent: literal compound field name (raw_*, *_real, *_full 等) を detect、
# 単語 "email" / "phone" 単独は generic noun のため不採用 (compound name で literal 充足、
# false positive 排除で受託 deploy 段階の academic paper 取込 path 確保、 doctrine: client-no-recovery)
VAULT_FIELDS: frozenset[str] = frozenset(
    {
        "name_full",
        "address_full",
        "raw_self_intro",
        "raw_description",
        "name_kana",
        "dob_exact",
        "contact_email",
        "contact_phone",
        "contact_person",
        "raw_text",
        "employee_name",
        "vendor_contact",
        "signatory_name",
        "client_company_name_real",
        "deal_consideration_real",
        "raw_rationale",
        "raw_retrospective",
        "raw_query_text",
        "raw_owner_name",
        "raw_owner_quote",
        "raw_cross_case_evidence",
        "decision_maker_name",
        "paper_signatory",
        "acknowledgments_raw",
        "raw_user_name",
    }
)

# Ontology validate gate threshold
ONTOLOGY_GATE_THRESHOLD: float = 0.80

# relationship confidence threshold
RELATIONSHIP_CONFIDENCE_THRESHOLD: float = 0.80

# community summary char limit
COMMUNITY_SUMMARY_MAX_LEN: int = 200


# ============================================================================
# Schema (retrieval layer 専用 light schema、 src/schema/types.py の 6 Object Type に subsequently mapping)
# ============================================================================


class Entity(BaseModel):
    """graphrag 抽出 entity (transient、 src/schema/types.py 6 Object Type に mapping)"""

    entity_id: str = Field(..., min_length=1, max_length=64)
    entity_type: str = Field(..., description="internal 14 or T5 4 Object Type、 適合 < 80% で block")
    entity_name_redacted: str = Field(..., max_length=200, description="PII redact 済 surface form")
    confidence: float = Field(..., ge=0.0, le=1.0)
    spans: list[tuple[int, int]] = Field(default_factory=list, description="source text 内 char index span")


class Relationship(BaseModel):
    """entity pair → 6 link_types 強制 mapping"""

    source_entity_id: str = Field(..., min_length=1)
    target_entity_id: str = Field(..., min_length=1)
    link_type: Literal[
        "blocks", "caused_by", "solved_by", "related_to", "supersedes", "implements"
    ]
    confidence: float = Field(..., ge=0.0, le=1.0)


class Community(BaseModel):
    """Louvain community (NetworkX louvain_communities 出力 thin wrapper、 graph backend mode fix supersede Leiden→Louvain)"""

    community_id: str = Field(..., min_length=1)
    member_entity_ids: list[str] = Field(..., min_length=1)
    size: int = Field(..., ge=1)


class CommunitySummary(BaseModel):
    """community summarization prompt 出力 (200 字 max、 PII redact 強制、 5 dim aggregation)"""

    community_id: str
    summary_redacted: str = Field(..., max_length=COMMUNITY_SUMMARY_MAX_LEN)
    dimension_aggregation: dict[str, str] = Field(
        default_factory=dict, description="5 dim categorical aggregation"
    )


# ============================================================================
# Prompts (3 prompt 自作、 OSS 全体 inject 不発、 module boundaries 段階 2)
# ============================================================================

ENTITY_EXTRACTION_SYSTEM_PROMPT = """\
あなたは PMI (Post-Merger Integration) domain の entity 抽出 expert です。

以下の Object Type のみ抽出可能 (適合外は抽出禁止、 Ontology 80% gate 強制):
- existing internal 14: PJ / WO / Skill / FileResource / Incident / Decision / Pattern / Workaround / Convention / DoctrineRule / InfoGovRule / SecurityLayer / BiasCandidate / SynergyInteraction
- T5 拡張: PMICase / Outcome / ReferencePaper / AssistantQuery

絶対禁止:
- 個人氏名 / 取引先実名 / 内部金額 を entity_name に含めること (PII redact 必須、 surface form は entity-replaced)
- 上記 Object Type 以外の type を出力すること
- confidence を hardcode 1.0 (overconfident) で返すこと、 evidence 強度に応じて 0.0-1.0 range で literal calibrate

出力 format (JSON array、 他テキスト一切禁止):
[
  {"entity_id": "E001", "entity_type": "Decision", "entity_name_redacted": "Day-1 組合存続 decision", "confidence": 0.85, "spans": [[123, 145]]},
  ...
]
"""

RELATIONSHIP_EXTRACTION_SYSTEM_PROMPT = """\
あなたは PMI domain の relationship 抽出 expert です。

絶対 rules:
- link_type は次の 6 enum のみ出力可: blocks / caused_by / solved_by / related_to / supersedes / implements
- 上記 6 enum 以外を出力した場合 literal block されます
- confidence は evidence 強度に応じ 0.0-1.0 で literal calibrate、 hardcode 禁止

mapping rule reference (PMI domain):
- PMICase → Outcome (因果) = caused_by
- Decision → Outcome (結果評価) = solved_by
- PMICase → Pattern (instance of) = implements
- ReferencePaper → PMICase (support) = related_to
- AssistantQuery → 任意 entity (retrieval link) = related_to
- Decision → Decision (時系列) = blocks / supersedes

出力 format (JSON array、 他テキスト一切禁止):
[
  {"source_entity_id": "E001", "target_entity_id": "E002", "link_type": "caused_by", "confidence": 0.78},
  ...
]
"""

COMMUNITY_SUMMARIZATION_SYSTEM_PROMPT = """\
あなたは PMI knowledge base の community summarization expert です。

community = NetworkX Leiden algorithm が抽出した dense entity cluster (関連性の強い entity 群)。

絶対 rules:
- summary は 200 字以内
- 個人氏名 / 取引先実名 / 内部金額 を含めない (PII redact 強制)
- 5 dim (industry / size_band / culture_profile / financial_band / integration_type) の categorical aggregation を抽出

出力 format (JSON object、 他テキスト一切禁止):
{
  "summary_redacted": "(200 字以内 summary、 PII redact 済)",
  "dimension_aggregation": {
    "industry": "製造業",
    "size_band": "100-300",
    "culture_profile": "同族 + 関西",
    "financial_band": "30-50",
    "integration_type": "tuck-in"
  }
}
"""


# ============================================================================
# PII boundary check
# ============================================================================


def check_pii_boundary(text: str) -> tuple[bool, list[str]]:
    """vault field 名 (27 件) 含む raw value detect。

    Returns:
        (clean, detected_fields)
        clean=True で boundary 通過、 False で block (raw value embedding 禁止)。
    """
    text_lower = text.lower()
    detected = sorted({field for field in VAULT_FIELDS if field.lower() in text_lower})
    return (len(detected) == 0, detected)


# ============================================================================
# Ontology validate gate
# ============================================================================


def validate_ontology_entities(
    entities: list[Entity],
    threshold: float = ONTOLOGY_GATE_THRESHOLD,
) -> tuple[bool, float, list[Entity]]:
    """entity_type 適合率 check (internal 14 + T5 4 = literal valid set)。

    Returns:
        (pass_, conformance_rate, rejected)
    """
    if not entities:
        return (True, 1.0, [])
    valid_count = sum(1 for e in entities if e.entity_type in VALID_OBJECT_TYPES)
    conformance_rate = valid_count / len(entities)
    rejected = [e for e in entities if e.entity_type not in VALID_OBJECT_TYPES]
    return (conformance_rate >= threshold, conformance_rate, rejected)


def validate_ontology_relationships(
    relationships: list[Relationship],
    threshold: float = RELATIONSHIP_CONFIDENCE_THRESHOLD,
) -> tuple[bool, float, list[Relationship]]:
    """link_type 6 enum 強制 mapping + confidence threshold check。

    Returns:
        (pass_, conformance_rate, rejected)
    """
    if not relationships:
        return (True, 1.0, [])
    valid_count = sum(
        1
        for r in relationships
        if r.link_type in VALID_LINK_TYPES and r.confidence >= threshold
    )
    conformance_rate = valid_count / len(relationships)
    rejected = [
        r
        for r in relationships
        if r.link_type not in VALID_LINK_TYPES or r.confidence < threshold
    ]
    return (conformance_rate >= threshold, conformance_rate, rejected)


# ============================================================================
# Entity extraction (LLM call、 LLMProvider Protocol 経由)
# ============================================================================


def extract_entities(text: str, llm: "LLMProvider") -> list[Entity]:
    """text → entity list (Entity Pydantic schema validated)。

    Raises:
        PIIBoundaryViolation: PII boundary block 時
        ValueError: LLM output が JSON array でない / schema invalid 時
    """
    clean, detected = check_pii_boundary(text)
    if not clean:
        raise PIIBoundaryViolation(
            f"PII boundary violation: vault fields detected in input text: {detected}. "
            "raw value embedding 禁止"
        )

    raw_response = llm.complete(
        prompt=text,
        system=ENTITY_EXTRACTION_SYSTEM_PROMPT,
        temperature=0.0,
        max_tokens=2000,
    )
    try:
        parsed = json.loads(_strip_markdown_codeblock(raw_response))
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise ValueError(
            f"LLM response must be a JSON array, got {type(parsed).__name__}"
        )
    return [Entity.model_validate(item) for item in parsed]


def extract_relationships(
    entities: list[Entity],
    text: str,
    llm: "LLMProvider",
) -> list[Relationship]:
    """entity pairs + source text → relationship list (6 link_types 強制 mapping)。

    Raises:
        ValueError: LLM output が JSON array でない / schema invalid 時 (link_type 6 enum 外も含む)
    """
    if len(entities) < 2:
        return []
    entity_summary = "\n".join(
        f"- {e.entity_id} ({e.entity_type}): {e.entity_name_redacted}" for e in entities
    )
    user_prompt = f"Source text:\n{text}\n\nEntities:\n{entity_summary}"
    raw_response = llm.complete(
        prompt=user_prompt,
        system=RELATIONSHIP_EXTRACTION_SYSTEM_PROMPT,
        temperature=0.0,
        max_tokens=2000,
    )
    try:
        parsed = json.loads(_strip_markdown_codeblock(raw_response))
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise ValueError(
            f"LLM response must be a JSON array, got {type(parsed).__name__}"
        )
    return [Relationship.model_validate(item) for item in parsed]


# ============================================================================
# Graph construction (NetworkX DiGraph、 entity = node + relationship = edge)
# ============================================================================


def build_entity_graph(
    entities: list[Entity],
    relationships: list[Relationship],
) -> nx.DiGraph:
    """entities + relationships → directed graph (NetworkX 段階 1 OS-primitives 利用)"""
    graph: nx.DiGraph = nx.DiGraph()
    for entity in entities:
        graph.add_node(
            entity.entity_id,
            entity_type=entity.entity_type,
            entity_name_redacted=entity.entity_name_redacted,
            confidence=entity.confidence,
        )
    for rel in relationships:
        if rel.source_entity_id in graph and rel.target_entity_id in graph:
            graph.add_edge(
                rel.source_entity_id,
                rel.target_entity_id,
                link_type=rel.link_type,
                confidence=rel.confidence,
            )
    return graph


# ============================================================================
# Community detection
# ============================================================================


def detect_communities(
    graph: nx.DiGraph,
    resolution: float = 1.0,
    threshold: float = 1e-07,
    seed: int | None = 42,
) -> list[Community]:
    """NetworkX louvain_communities thin wrapper (module boundaries 段階 1、 graph backend mode fix 2026-05-14 supersede)。

    NetworkX 3.6.1 公式実装 (BSD-3、 NumFOCUS sponsored、 T3/T4 既 inherit)。 backend 不要 = literal 標準実装、
    leiden_communities (API dispatcher のみ、 backend 必要、 NotImplementedError raise) から literal supersede。
    thin wrapper のみ、 業務 logic 注入禁止。

    Args:
        graph: NetworkX DiGraph (entity graph)
        resolution: modularity resolution (default 1.0 = standard Louvain)
        threshold: modularity gain threshold (NetworkX default 1e-07)
        seed: deterministic seed (test reproducibility 用)

    Raises:
        RuntimeError: NetworkX louvain_communities 不在時 (< 3.6 install 不正)
    """
    if graph.number_of_nodes() == 0:
        return []
    undirected = graph.to_undirected()
    louvain_fn = getattr(nx.community, "louvain_communities", None)
    if louvain_fn is None:
        raise RuntimeError(
            "networkx.community.louvain_communities not available. "
            f"Requires NetworkX >= 3.6 (detected: {nx.__version__}). "
            "Run: pip install -U 'networkx>=3.6,<4.0'"
        )
    community_sets = louvain_fn(
        undirected,
        resolution=resolution,
        threshold=threshold,
        seed=seed,
    )
    communities: list[Community] = []
    for idx, members in enumerate(community_sets):
        member_list = sorted(str(m) for m in members)
        if not member_list:
            continue
        communities.append(
            Community(
                community_id=f"C{idx:03d}",
                member_entity_ids=member_list,
                size=len(member_list),
            )
        )
    return communities


# ============================================================================
# Community summarization (LLM call、 LLMProvider Protocol 経由)
# ============================================================================


def summarize_community(
    community: Community,
    graph: nx.DiGraph,
    llm: "LLMProvider",
) -> CommunitySummary:
    """community → 200 字 summary (PII redact 強制、 5 dim aggregation)。

    Raises:
        ValueError: LLM output が JSON object でない / summary > 200 字 / schema invalid 時
    """
    member_lines: list[str] = []
    for node_id in community.member_entity_ids:
        if node_id not in graph:
            continue
        node_data = graph.nodes[node_id]
        member_lines.append(
            f"- {node_id} ({node_data.get('entity_type', '?')}): "
            f"{node_data.get('entity_name_redacted', '')}"
        )
    user_prompt = (
        f"Community {community.community_id} ({community.size} members):\n"
        + "\n".join(member_lines)
    )
    raw_response = llm.complete(
        prompt=user_prompt,
        system=COMMUNITY_SUMMARIZATION_SYSTEM_PROMPT,
        temperature=0.0,
        max_tokens=500,
    )
    try:
        parsed = json.loads(_strip_markdown_codeblock(raw_response))
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(
            f"LLM response must be a JSON object, got {type(parsed).__name__}"
        )
    parsed["community_id"] = community.community_id
    return CommunitySummary.model_validate(parsed)


# ============================================================================
# Exceptions
# ============================================================================


class PIIBoundaryViolation(ValueError):
    """PII vault field detect 時 raise"""


__all__ = [
    # constants
    "INTERNAL_OBJECT_TYPES",
    "T5_OBJECT_TYPES",
    "VALID_OBJECT_TYPES",
    "VALID_LINK_TYPES",
    "VAULT_FIELDS",
    "ONTOLOGY_GATE_THRESHOLD",
    "RELATIONSHIP_CONFIDENCE_THRESHOLD",
    "COMMUNITY_SUMMARY_MAX_LEN",
    # prompts
    "ENTITY_EXTRACTION_SYSTEM_PROMPT",
    "RELATIONSHIP_EXTRACTION_SYSTEM_PROMPT",
    "COMMUNITY_SUMMARIZATION_SYSTEM_PROMPT",
    # schemas
    "Entity",
    "Relationship",
    "Community",
    "CommunitySummary",
    # functions
    "check_pii_boundary",
    "validate_ontology_entities",
    "validate_ontology_relationships",
    "extract_entities",
    "extract_relationships",
    "build_entity_graph",
    "detect_communities",
    "summarize_community",
    # exceptions
    "PIIBoundaryViolation",
]

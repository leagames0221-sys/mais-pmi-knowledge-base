"""LangGraph state graph orchestrator

Module boundaries (3 tiers):
- Tier 1 OS-primitives: langgraph >=1.2.0,<2.0 + langgraph-checkpoint + langchain-core (CVE-2026-28277 fixed pin)
- Tier 2 business logic: 9-node business logic + conditional routing + multi-hop traversal (in-house)

Implementation follows the 9-stage DAG diagram below.

9-node DAG:
parse_query → extract_entities → ontology_validate_gate → pii_boundary_check
  → graph_traverse → similar_case_rank → community_summarize
  → assistant_recommend_placeholder → audit_log_emit
"""
from __future__ import annotations

import sys
from datetime import datetime
from typing import Any, Optional, TypedDict

import networkx as nx

from ..assistant.dialogue_orchestrate import (
    DEFAULT_AUDIT_DIR,
    AssistantCounter,
    AssistantDialogueRequest,
    emit_assistant_audit,
    assistant_recommend,
)
from ..llm.provider import LLMProvider
from ..retrieval.graphrag_native import (
    Community,
    CommunitySummary,
    Entity,
    ONTOLOGY_GATE_THRESHOLD,
    PIIBoundaryViolation,
    Relationship,
    build_entity_graph,
    check_pii_boundary,
    detect_communities,
    extract_entities as graphrag_extract_entities,
    extract_relationships as graphrag_extract_relationships,
    summarize_community,
    validate_ontology_entities,
    validate_ontology_relationships,
)
from ..retrieval.multi_axis_similar_cases import SimilarityScore, rank_similar_cases
from ..schema.types import AssistantQuery, PMICase, RecommendationItem

# Windows cp932 console UTF-8 reconfigure (T3 学び doctrine: analogical-recall inherit)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8") # type: ignore[attr-defined]
    except Exception:
        pass


# ============================================================================
# Multi-hop traversal default
# ============================================================================

DEFAULT_MAX_HOPS: int = 3
DEFAULT_WEIGHT_DECAY: float = 0.8


# ============================================================================
# State (TypedDict、 langgraph state graph state shape SSoT)
# ============================================================================


class OrchestratorState(TypedDict, total=False):
    """9 node state shape。

    total=False で literal partial state update (langgraph node return = partial dict)。
    """

    # input
    query_text_redacted: str
    user_role: str
    candidate_pmi_cases: list[PMICase]
    # context provided by caller
    llm: LLMProvider
    # extracted
    entities: list[Entity]
    relationships: list[Relationship]
    # gates
    ontology_gate_pass: bool
    ontology_conformance_rate: float
    pii_boundary_clean: bool
    pii_detected_fields: list[str]
    # graph + community
    graph: nx.DiGraph
    communities: list[Community]
    # ranked
    top_k_cases: list[SimilarityScore]
    community_summaries: list[CommunitySummary]
    # transient (rec list before AssistantQuery emit)
    pending_recommendations: list[RecommendationItem]
    # output
    assistant_query: Optional[AssistantQuery]
    # audit
    audit_log: list[dict[str, Any]]
    # routing flags
    route_blocked: bool
    route_reason: str


def _append_audit(state: OrchestratorState, entry: dict[str, Any]) -> list[dict[str, Any]]:
    return [*state.get("audit_log", []), {**entry, "at": datetime.now().isoformat()}]


# ============================================================================
# Node 1: parse_query
# ============================================================================


def node_parse_query(state: OrchestratorState) -> dict[str, Any]:
    """input validation + audit log entry。"""
    query = state.get("query_text_redacted", "")
    audit = _append_audit(state, {"step": "parse_query", "query_head": query[:50] if query else "(empty)"})
    if not query:
        return {"route_blocked": True, "route_reason": "empty query", "audit_log": audit}
    return {"audit_log": audit, "route_blocked": False, "route_reason": ""}


# ============================================================================
# Node 2: extract_entities
# ============================================================================


def node_extract_entities(state: OrchestratorState) -> dict[str, Any]:
    """entity + relationship 抽出 (PII boundary は graphrag_native 内部で check)。"""
    query = state["query_text_redacted"]
    llm = state["llm"]
    try:
        entities = graphrag_extract_entities(query, llm)
    except PIIBoundaryViolation as exc:
        audit = _append_audit(state, {"step": "extract_entities", "blocked": "pii", "msg": str(exc)[:200]})
        return {
            "entities": [],
            "relationships": [],
            "pii_boundary_clean": False,
            "pii_detected_fields": list(getattr(exc, "args", [str(exc)])),
            "route_blocked": True,
            "route_reason": f"PII boundary violation in query: {exc}",
            "audit_log": audit,
        }
    relationships: list[Relationship] = []
    if len(entities) >= 2:
        try:
            relationships = graphrag_extract_relationships(entities, query, llm)
        except ValueError:
            relationships = []
    rel_pass, rel_rate, rel_rejected = validate_ontology_relationships(relationships)
    audit = _append_audit(
        state,
        {
            "step": "extract_entities",
            "entity_count": len(entities),
            "relationship_count": len(relationships),
            "relationship_validate_pass": rel_pass,
            "relationship_rate": round(rel_rate, 3),
            "relationship_rejected_count": len(rel_rejected),
        },
    )
    return {"entities": entities, "relationships": relationships, "audit_log": audit}


# ============================================================================
# Node 3: ontology_validate_gate (entities 適合率 80% gate)
# ============================================================================


def node_ontology_validate_gate(state: OrchestratorState) -> dict[str, Any]:
    """Ontology validate gate (80% threshold)。 適合 < 80% で block + user gate prompt 用 flag set。"""
    entities = state.get("entities", [])
    pass_, rate, rejected = validate_ontology_entities(entities, threshold=ONTOLOGY_GATE_THRESHOLD)
    audit = _append_audit(
        state,
        {
            "step": "ontology_validate_gate",
            "pass": pass_,
            "rate": round(rate, 3),
            "rejected_count": len(rejected),
            "rejected_types": sorted({r.entity_type for r in rejected}),
        },
    )
    if not pass_:
        return {
            "ontology_gate_pass": False,
            "ontology_conformance_rate": rate,
            "route_blocked": True,
            "route_reason": (
                f"Ontology conformance {rate:.2%} < {ONTOLOGY_GATE_THRESHOLD:.0%} threshold "
                f"(rejected types: {sorted({r.entity_type for r in rejected})})"
            ),
            "audit_log": audit,
        }
    return {
        "ontology_gate_pass": True,
        "ontology_conformance_rate": rate,
        "audit_log": audit,
    }


# ============================================================================
# Node 4: pii_boundary_check (entity_name_redacted の vault field 含有 detect)
# ============================================================================


def node_pii_boundary_check(state: OrchestratorState) -> dict[str, Any]:
    """entity_name_redacted 全件 PII boundary check (graphrag entity extraction で漏れた場合の二重 防御)。"""
    entities = state.get("entities", [])
    detected_all: set[str] = set()
    for e in entities:
        clean, detected = check_pii_boundary(e.entity_name_redacted)
        if not clean:
            detected_all.update(detected)
    sorted_detected = sorted(detected_all)
    audit = _append_audit(
        state,
        {
            "step": "pii_boundary_check",
            "clean": len(detected_all) == 0,
            "detected_count": len(detected_all),
            "detected_fields": sorted_detected,
        },
    )
    if detected_all:
        return {
            "pii_boundary_clean": False,
            "pii_detected_fields": sorted_detected,
            "route_blocked": True,
            "route_reason": f"PII boundary violation in entity names: {sorted_detected}",
            "audit_log": audit,
        }
    return {
        "pii_boundary_clean": True,
        "pii_detected_fields": [],
        "audit_log": audit,
    }


# ============================================================================
# Node 5: graph_traverse (build_entity_graph + detect_communities)
# ============================================================================


def node_graph_traverse(state: OrchestratorState) -> dict[str, Any]:
    """graph build (NetworkX DiGraph) + Louvain community detection (graph backend mode fix、 leiden API dispatcher backend 不在 issue 回避)。"""
    entities = state.get("entities", [])
    relationships = state.get("relationships", [])
    graph = build_entity_graph(entities, relationships)
    communities: list[Community] = []
    if graph.number_of_nodes() > 0:
        try:
            communities = detect_communities(graph)
        except RuntimeError as exc:
            # NetworkX louvain_communities 不在時 (NetworkX < 3.6 install 不正)、 fail-loud
            audit = _append_audit(
                state,
                {"step": "graph_traverse", "error": "louvain_communities unavailable", "msg": str(exc)[:200]},
            )
            return {"graph": graph, "communities": [], "audit_log": audit, "route_blocked": True, "route_reason": str(exc)}
    audit = _append_audit(
        state,
        {
            "step": "graph_traverse",
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "communities": len(communities),
        },
    )
    return {"graph": graph, "communities": communities, "audit_log": audit}


# ============================================================================
# Node 6: similar_case_rank (5 dim weighted similarity top-K=3)
# ============================================================================


def node_similar_case_rank(state: OrchestratorState) -> dict[str, Any]:
    """5 dim weighted similarity top-K=3 rank。

    Week 2 PoC simplification: query PMICase は candidates[0] 仮置き
   。
    """
    candidates = state.get("candidate_pmi_cases", [])
    if not candidates:
        audit = _append_audit(
            state,
            {
                "step": "similar_case_rank",
                "top_k": 0,
                "note": "no candidates provided",
            },
        )
        return {"top_k_cases": [], "audit_log": audit}
    query_case = candidates[0]
    pool = candidates[1:]
    ranked = rank_similar_cases(query_case, pool, top_k=3)
    audit = _append_audit(
        state,
        {
            "step": "similar_case_rank",
            "top_k": len(ranked),
            "top_score": ranked[0].aggregate_score if ranked else None,
            "stub_query": "candidates[0]",
        },
    )
    return {"top_k_cases": ranked, "audit_log": audit}


# ============================================================================
# Node 7: community_summarize (各 community で LLM summarize)
# ============================================================================


def node_community_summarize(state: OrchestratorState) -> dict[str, Any]:
    """各 community に対し summarize_community call (200 字 max、 PII redact 強制)。"""
    communities = state.get("communities", [])
    graph = state.get("graph", nx.DiGraph())
    llm = state["llm"]
    summaries: list[CommunitySummary] = []
    fail_count = 0
    for community in communities:
        try:
            summary = summarize_community(community, graph, llm)
            summaries.append(summary)
        except ValueError:
            fail_count += 1 # malformed LLM response (Week 3 8 gate gate 2 silent fail = 0 verify)
    audit = _append_audit(
        state,
        {
            "step": "community_summarize",
            "summary_count": len(summaries),
            "total_communities": len(communities),
            "fail_count": fail_count,
        },
    )
    return {"community_summaries": summaries, "audit_log": audit}


# ============================================================================
# Node 8: assistant_recommend
# ============================================================================


def node_assistant_recommend(state: OrchestratorState) -> dict[str, Any]:
    """Assistant 型対話 full active。

    Week 2 stub (top_k → simple ranked) → Week 3 active (listwise CoT + audit log emit)。
    """
    llm = state["llm"]
    query_text = state.get("query_text_redacted", "")
    user_role_raw = state.get("user_role", "junior_consultant")
    valid_roles = {"junior_consultant", "senior_consultant", "fde", "admin"}
    user_role = user_role_raw if user_role_raw in valid_roles else "junior_consultant"
    top_k = state.get("top_k_cases", [])
    community_summaries = state.get("community_summaries", [])

    request = AssistantDialogueRequest(
        query_text_redacted=query_text[:200] if query_text else "(no query)",
        user_role=user_role, # type: ignore[arg-type]
    )
    try:
        recommendations = assistant_recommend(
            request=request,
            top_k_cases=top_k,
            community_summaries=community_summaries,
            retrieved_papers=[], # Week 3 末 RAG ingestion 配線で literal active、 Week 3 中間 = []
            llm=llm,
        )
    except ValueError:
        # LLM response 不正時 = Week 2 stub と同 fallback (top-K → simple ranked) で literal 退避
        recommendations = []
        for i, score in enumerate(top_k, start=1):
            recommendations.append(
                RecommendationItem(
                    rank=i,
                    recommendation_redacted=(
                        f"類似 case {score.candidate_pmi_id} (aggregate={score.aggregate_score:.3f}) を参照"
                    ),
                    confidence=score.aggregate_score,
                    citation_array=[score.candidate_pmi_id],
                )
            )

    audit = _append_audit(
        state,
        {
            "step": "assistant_recommend",
            "recommendation_count": len(recommendations),
            "stub": False, # Week 3 active
            "user_role": user_role,
        },
    )
    return {"pending_recommendations": recommendations, "audit_log": audit}


# legacy alias
node_assistant_recommend_placeholder = node_assistant_recommend


# ============================================================================
# Node 9: audit_log_emit (AssistantQuery schema literal emit)
# ============================================================================


def node_audit_log_emit(state: OrchestratorState) -> dict[str, Any]:
    """AssistantQuery schema literal emit (audit trail full)。 Week 3 で persistent storage active 化。"""
    query = state.get("query_text_redacted", "")
    top_k_cases = state.get("top_k_cases", [])
    pending_recs = state.get("pending_recommendations", [])
    user_role_raw = state.get("user_role", "junior_consultant")
    # LIL id は timestamp ms 末尾 6 桁
    lil_id = f"LIL-{int(datetime.now().timestamp() * 1000) % 1000000:06d}"
    valid_roles = {"junior_consultant", "senior_consultant", "fde", "admin"}
    role_final = user_role_raw if user_role_raw in valid_roles else "junior_consultant"
    assistant_query = AssistantQuery(
        lil_id=lil_id,
        query_text_redacted=query[:200],
        retrieved_cases=[s.candidate_pmi_id for s in top_k_cases],
        retrieved_papers=[], # Week 3 で RAG paper ingestion active
        recommendation_ranked=pending_recs,
        user_role=role_final, # type: ignore[arg-type]
    )
    audit = _append_audit(state, {"step": "audit_log_emit", "lil_id": lil_id})
    return {"assistant_query": assistant_query, "audit_log": audit}


# ============================================================================
# Conditional routing
# ============================================================================


def route_after_extract(state: OrchestratorState) -> str:
    """entity extraction 後の routing (PII block で literal END、 OK で ontology_validate_gate)。"""
    if state.get("route_blocked", False):
        return "blocked"
    return "ontology_validate_gate"


def route_after_ontology_gate(state: OrchestratorState) -> str:
    """Ontology gate 後の routing (適合 < 80% で literal END、 OK で pii_boundary_check)。"""
    if state.get("route_blocked", False):
        return "blocked"
    return "pii_boundary_check"


def route_after_pii_check(state: OrchestratorState) -> str:
    """PII boundary check 後の routing。"""
    if state.get("route_blocked", False):
        return "blocked"
    return "graph_traverse"


# ============================================================================
# Build state graph
# ============================================================================


def build_state_graph(checkpoint: Any = None) -> Any:
    """LangGraph state graph compile (lazy import で fugashi/louvain 同 pattern 順守、 graph backend mode fix supersede)。

    Args:
        checkpoint: langgraph-checkpoint 互換 saver (default None = memory-only)
    Returns:
        compiled CompiledStateGraph
    Raises:
        RuntimeError: langgraph not installed
    """
    try:
        from langgraph.graph import END, StateGraph # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "langgraph not installed。 "
            "Run: pip install 'langgraph>=1.2.0,<2.0'"
        ) from exc

    builder = StateGraph(OrchestratorState)

    # 9 node 登録
    builder.add_node("parse_query", node_parse_query)
    builder.add_node("extract_entities", node_extract_entities)
    builder.add_node("ontology_validate_gate", node_ontology_validate_gate)
    builder.add_node("pii_boundary_check", node_pii_boundary_check)
    builder.add_node("graph_traverse", node_graph_traverse)
    builder.add_node("similar_case_rank", node_similar_case_rank)
    builder.add_node("community_summarize", node_community_summarize)
    # node naming evolution: assistant_recommend_placeholder → assistant_recommend
    builder.add_node("assistant_recommend", node_assistant_recommend)
    builder.add_node("audit_log_emit", node_audit_log_emit)

    builder.set_entry_point("parse_query")
    builder.add_edge("parse_query", "extract_entities")
    builder.add_conditional_edges(
        "extract_entities",
        route_after_extract,
        {"ontology_validate_gate": "ontology_validate_gate", "blocked": END},
    )
    builder.add_conditional_edges(
        "ontology_validate_gate",
        route_after_ontology_gate,
        {"pii_boundary_check": "pii_boundary_check", "blocked": END},
    )
    builder.add_conditional_edges(
        "pii_boundary_check",
        route_after_pii_check,
        {"graph_traverse": "graph_traverse", "blocked": END},
    )
    builder.add_edge("graph_traverse", "similar_case_rank")
    builder.add_edge("similar_case_rank", "community_summarize")
    builder.add_edge("community_summarize", "assistant_recommend")
    builder.add_edge("assistant_recommend", "audit_log_emit")
    builder.add_edge("audit_log_emit", END)

    if checkpoint is not None:
        return builder.compile(checkpointer=checkpoint)
    return builder.compile()


# ============================================================================
# Multi-hop traversal helper
# ============================================================================


def multi_hop_traverse(
    graph: nx.DiGraph,
    start_node: str,
    max_hops: int = DEFAULT_MAX_HOPS,
    weight_decay: float = DEFAULT_WEIGHT_DECAY,
    link_type_filter: Optional[set[str]] = None,
) -> list[tuple[str, int, float]]:
    """multi-hop traversal (BFS + weight_decay hop × decay + cycle_detection visited set)。

    Args:
        graph: NetworkX DiGraph (graphrag_native.build_entity_graph 出力)
        start_node: traversal 開始 entity_id
        max_hops: 最大 hop
        weight_decay: hop ごと weight 減衰率 (default 0.8、 internal ontology 既存設定)
        link_type_filter: 対象 link_type set (None = 全 link_type allow)
    Returns:
        list[(entity_id, hop_count, accumulated_weight)]、 hop 順 + 同 hop 内は登録順、 start_node 自身 除外
    """
    if start_node not in graph or max_hops < 1:
        return []
    visited: set[str] = {start_node}
    frontier: list[tuple[str, float]] = [(start_node, 1.0)]
    results: list[tuple[str, int, float]] = []
    for hop in range(1, max_hops + 1):
        next_frontier: list[tuple[str, float]] = []
        for current_node, current_weight in frontier:
            new_weight = current_weight * weight_decay
            for neighbor in graph.successors(current_node):
                if neighbor in visited:
                    continue
                edge_data = graph.edges[current_node, neighbor]
                edge_link_type = edge_data.get("link_type")
                if link_type_filter is not None and edge_link_type not in link_type_filter:
                    continue
                edge_confidence = edge_data.get("confidence", 1.0)
                accumulated = new_weight * edge_confidence
                visited.add(neighbor)
                results.append((neighbor, hop, accumulated))
                next_frontier.append((neighbor, new_weight))
        frontier = next_frontier
        if not frontier:
            break
    return results


__all__ = [
    "DEFAULT_MAX_HOPS",
    "DEFAULT_WEIGHT_DECAY",
    "OrchestratorState",
    "node_parse_query",
    "node_extract_entities",
    "node_ontology_validate_gate",
    "node_pii_boundary_check",
    "node_graph_traverse",
    "node_similar_case_rank",
    "node_community_summarize",
    "node_assistant_recommend",
    "node_assistant_recommend_placeholder", # legacy alias preserved for backward compat
    "node_audit_log_emit",
    "route_after_extract",
    "route_after_ontology_gate",
    "route_after_pii_check",
    "build_state_graph",
    "multi_hop_traverse",
]

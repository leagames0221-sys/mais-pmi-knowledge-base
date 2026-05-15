"""tests for src/orchestrator/build_state_graph.py"""
from __future__ import annotations

import json

import networkx as nx
import pytest

from src.llm.provider import MockProvider
from src.orchestrator.build_state_graph import (
    DEFAULT_MAX_HOPS,
    DEFAULT_WEIGHT_DECAY,
    multi_hop_traverse,
    node_audit_log_emit,
    node_extract_entities,
    node_graph_traverse,
    node_assistant_recommend_placeholder,
    node_ontology_validate_gate,
    node_parse_query,
    node_pii_boundary_check,
    node_similar_case_rank,
    route_after_extract,
    route_after_ontology_gate,
    route_after_pii_check,
)
from src.retrieval.graphrag_native import Entity, Relationship
from src.retrieval.multi_axis_similar_cases import SimilarityScore


# === Constants ===


def test_default_max_hops_3():
    """ernal ontology 既存設定。"""
    assert DEFAULT_MAX_HOPS == 3


def test_default_weight_decay_08():
    """internal ontology 既存設定 inherit。"""
    assert DEFAULT_WEIGHT_DECAY == 0.8


# === multi_hop_traverse ===


def _build_chain_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_edge("A", "B", link_type="caused_by", confidence=0.9)
    g.add_edge("B", "C", link_type="implements", confidence=0.8)
    g.add_edge("C", "D", link_type="solved_by", confidence=0.7)
    g.add_edge("D", "E", link_type="related_to", confidence=0.6) # hop 4
    g.add_edge("B", "A", link_type="blocks", confidence=0.5) # cycle
    return g


def test_multi_hop_respects_max_hops():
    g = _build_chain_graph()
    paths = multi_hop_traverse(g, "A", max_hops=3)
    assert all(p[1] <= 3 for p in paths)
    assert "E" not in {p[0] for p in paths} # E is at hop 4 = out of range


def test_multi_hop_cycle_detection():
    g = _build_chain_graph()
    paths = multi_hop_traverse(g, "A", max_hops=3)
    # A は visited で自己 cycle 除外
    assert "A" not in {p[0] for p in paths}


def test_multi_hop_weight_decay_numeric():
    """hop k weight = 1.0 × decay^k × edge_confidence。"""
    g = _build_chain_graph()
    paths = multi_hop_traverse(g, "A", max_hops=3, weight_decay=0.8)
    nodes_to_weight = {p[0]: p[2] for p in paths}
    # B: 0.8 × 0.9 = 0.72
    assert abs(nodes_to_weight["B"] - 0.72) < 1e-6
    # C: 0.8 × 0.8 × 0.8 = 0.512
    assert abs(nodes_to_weight["C"] - 0.512) < 1e-6


def test_multi_hop_link_type_filter():
    g = _build_chain_graph()
    paths = multi_hop_traverse(g, "A", max_hops=3, link_type_filter={"caused_by", "implements"})
    assert {p[0] for p in paths} == {"B", "C"} # D edge solved_by literal 除外


def test_multi_hop_unknown_start_returns_empty():
    g = _build_chain_graph()
    assert multi_hop_traverse(g, "Z", max_hops=3) == []


def test_multi_hop_max_hops_zero_returns_empty():
    g = _build_chain_graph()
    assert multi_hop_traverse(g, "A", max_hops=0) == []


# === node_parse_query ===


def test_node_parse_query_normal():
    result = node_parse_query({"query_text_redacted": "Day-1 で組合存続"})
    assert result["route_blocked"] is False
    assert len(result["audit_log"]) == 1


def test_node_parse_query_empty_blocks():
    result = node_parse_query({"query_text_redacted": ""})
    assert result["route_blocked"] is True


# === node_extract_entities ===


def test_node_extract_entities_with_mock():
    fixture_entities = json.dumps([
        {"entity_id": "E1", "entity_type": "Decision", "entity_name_redacted": "Day-1 decision", "confidence": 0.9, "spans": []},
        {"entity_id": "E2", "entity_type": "Outcome", "entity_name_redacted": "retention 92", "confidence": 0.85, "spans": []},
    ])
    fixture_rels = json.dumps([
        {"source_entity_id": "E1", "target_entity_id": "E2", "link_type": "caused_by", "confidence": 0.85}
    ])
    llm = MockProvider(fixture={"entity 抽出": fixture_entities, "relationship": fixture_rels})
    state = {"query_text_redacted": "Day-1 PMI 統合 retention", "llm": llm}
    result = node_extract_entities(state)
    assert len(result["entities"]) == 2
    assert len(result["relationships"]) == 1


def test_node_extract_entities_pii_blocks():
    llm = MockProvider()
    state = {"query_text_redacted": "contains raw_query_text leak", "llm": llm}
    result = node_extract_entities(state)
    assert result["route_blocked"] is True
    assert result["pii_boundary_clean"] is False


# === node_ontology_validate_gate ===


def _entity(eid: str, etype: str, name: str = "redacted") -> Entity:
    return Entity(entity_id=eid, entity_type=etype, entity_name_redacted=name, confidence=0.9)


def test_node_ontology_gate_pass():
    state = {"entities": [_entity("E1", "Decision"), _entity("E2", "Outcome")]}
    result = node_ontology_validate_gate(state)
    assert result["ontology_gate_pass"] is True
    assert result["ontology_conformance_rate"] == 1.0


def test_node_ontology_gate_block():
    state = {"entities": [_entity("E1", "UnknownType"), _entity("E2", "UnknownType2")]}
    result = node_ontology_validate_gate(state)
    assert result["ontology_gate_pass"] is False
    assert result.get("route_blocked") is True


# === node_pii_boundary_check ===


def test_node_pii_check_clean():
    state = {"entities": [_entity("E1", "Decision", name="Day-1 decision")]}
    result = node_pii_boundary_check(state)
    assert result["pii_boundary_clean"] is True


def test_node_pii_check_leak_detect():
    state = {"entities": [_entity("E1", "Decision", name="contains raw_query_text leak")]}
    result = node_pii_boundary_check(state)
    assert result["pii_boundary_clean"] is False
    assert result.get("route_blocked") is True


# === node_graph_traverse ===


def test_node_graph_traverse_builds_graph():
    state = {
        "entities": [_entity("E1", "PMICase"), _entity("E2", "Outcome")],
        "relationships": [
            Relationship(source_entity_id="E1", target_entity_id="E2", link_type="caused_by", confidence=0.9)
        ],
    }
    result = node_graph_traverse(state)
    assert isinstance(result["graph"], nx.DiGraph)
    assert result["graph"].number_of_nodes() == 2


# === node_similar_case_rank ===


def test_node_similar_case_rank_empty_pool():
    result = node_similar_case_rank({"candidate_pmi_cases": []})
    assert result["top_k_cases"] == []


# === node_audit_log_emit ===


def test_node_audit_log_emit_creates_assistant_query():
    state = {
        "query_text_redacted": "Day-1 で組合存続",
        "top_k_cases": [
            SimilarityScore(
                query_pmi_id="PMI-000000001",
                candidate_pmi_id="PMI-000000002",
                industry_score=1.0,
                culture_score=0.5,
                size_score=1.0,
                integration_type_score=1.0,
                financial_score=1.0,
                aggregate_score=0.875,
            )
        ],
        "pending_recommendations": [],
        "user_role": "junior_consultant",
    }
    result = node_audit_log_emit(state)
    assert result["assistant_query"] is not None
    assert result["assistant_query"].lil_id.startswith("LIL-")
    assert "PMI-000000002" in result["assistant_query"].retrieved_cases


# === conditional routing ===


def test_route_after_extract_blocked():
    assert route_after_extract({"route_blocked": True}) == "blocked"


def test_route_after_extract_normal():
    assert route_after_extract({"route_blocked": False}) == "ontology_validate_gate"


def test_route_after_ontology_gate_blocked():
    assert route_after_ontology_gate({"route_blocked": True}) == "blocked"


def test_route_after_pii_check_normal():
    assert route_after_pii_check({"route_blocked": False}) == "graph_traverse"

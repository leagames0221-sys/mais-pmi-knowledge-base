"""tests for src/retrieval/graphrag_native.py (internal ADR § 1 + § 7 順守、 22 test)"""
from __future__ import annotations

import json

import pytest

from src.llm.provider import MockProvider
from src.retrieval.graphrag_native import (
    COMMUNITY_SUMMARY_MAX_LEN,
    INTERNAL_OBJECT_TYPES,
    ONTOLOGY_GATE_THRESHOLD,
    RELATIONSHIP_CONFIDENCE_THRESHOLD,
    T5_OBJECT_TYPES,
    VALID_LINK_TYPES,
    VALID_OBJECT_TYPES,
    VAULT_FIELDS,
    Community,
    Entity,
    PIIBoundaryViolation,
    Relationship,
    build_entity_graph,
    check_pii_boundary,
    extract_entities,
    extract_relationships,
    validate_ontology_entities,
    validate_ontology_relationships,
)


# === Constants integrity (internal ADR + internal ADR § 1 SSoT) ===


def test_internal_object_types_count():
    assert len(INTERNAL_OBJECT_TYPES) == 14


def test_t5_object_types_count():
    # internal ADR: internal 14 完全 inherit + T5 extend 4 (PMICase/Outcome/ReferencePaper/AssistantQuery)
    assert len(T5_OBJECT_TYPES) == 4
    assert "AssistantQuery" in T5_OBJECT_TYPES


def test_valid_object_types_union():
    assert VALID_OBJECT_TYPES == INTERNAL_OBJECT_TYPES | T5_OBJECT_TYPES


def test_link_types_6_enum():
    assert VALID_LINK_TYPES == frozenset(
        {"blocks", "caused_by", "solved_by", "related_to", "supersedes", "implements"}
    )


def test_vault_fields_contains_known_pii():
    for field in ("raw_query_text", "client_company_name_real", "deal_consideration_real"):
        assert field in VAULT_FIELDS


def test_thresholds_80_percent():
    assert ONTOLOGY_GATE_THRESHOLD == 0.80
    assert RELATIONSHIP_CONFIDENCE_THRESHOLD == 0.80


def test_community_summary_max_200_chars():
    assert COMMUNITY_SUMMARY_MAX_LEN == 200


# === PII boundary check ===


def test_pii_boundary_clean_text():
    clean, detected = check_pii_boundary("Day-1 で組合存続 redacted decision")
    assert clean is True
    assert detected == []


def test_pii_boundary_detect_vault_field():
    clean, detected = check_pii_boundary("contains raw_query_text leak")
    assert clean is False
    assert "raw_query_text" in detected


def test_pii_boundary_detect_multiple_fields():
    clean, detected = check_pii_boundary("text with client_company_name_real and deal_consideration_real")
    assert clean is False
    assert len(detected) == 2


# === Ontology validate gate (80% threshold) ===


def _entity(eid: str, etype: str, conf: float = 0.9) -> Entity:
    return Entity(entity_id=eid, entity_type=etype, entity_name_redacted=f"redacted {eid}", confidence=conf)


def test_validate_ontology_entities_100_percent_pass():
    entities = [_entity("E1", "Decision"), _entity("E2", "PMICase")]
    pass_, rate, rejected = validate_ontology_entities(entities)
    assert pass_ is True
    assert rate == 1.0
    assert rejected == []


def test_validate_ontology_entities_50_percent_block():
    entities = [_entity("E1", "Decision"), _entity("E2", "UnknownType")]
    pass_, rate, rejected = validate_ontology_entities(entities)
    assert pass_ is False
    assert rate == 0.5
    assert len(rejected) == 1


def test_validate_ontology_entities_empty_passes():
    pass_, rate, rejected = validate_ontology_entities([])
    assert pass_ is True
    assert rate == 1.0


# === Relationship validate (6 link_types 強制 mapping + 80% confidence) ===


def test_validate_ontology_relationships_pass():
    rels = [
        Relationship(source_entity_id="A", target_entity_id="B", link_type="caused_by", confidence=0.9),
        Relationship(source_entity_id="B", target_entity_id="C", link_type="implements", confidence=0.85),
    ]
    pass_, rate, rejected = validate_ontology_relationships(rels)
    assert pass_ is True
    assert rate == 1.0


def test_validate_ontology_relationships_low_confidence_rejected():
    rels = [
        Relationship(source_entity_id="A", target_entity_id="B", link_type="caused_by", confidence=0.5),
    ]
    pass_, rate, rejected = validate_ontology_relationships(rels)
    assert pass_ is False  # 1/1 = 0% pass < 80%
    assert len(rejected) == 1


def test_relationship_schema_rejects_invalid_link_type():
    # Pydantic Literal[...] = invalid link_type raises at schema validation
    with pytest.raises(Exception):
        Relationship(source_entity_id="A", target_entity_id="B", link_type="invalid_link", confidence=0.9)


# === extract_entities (MockProvider 経由) ===


def test_extract_entities_pii_boundary_raises():
    with pytest.raises(PIIBoundaryViolation):
        extract_entities("contains raw_query_text", MockProvider())


def test_extract_entities_with_mock_response():
    fixture_response = json.dumps([
        {"entity_id": "E001", "entity_type": "Decision", "entity_name_redacted": "Day-1 decision", "confidence": 0.9, "spans": []},
        {"entity_id": "E002", "entity_type": "Outcome", "entity_name_redacted": "retention 92%", "confidence": 0.85, "spans": []},
    ])
    llm = MockProvider(fixture={"PMI": fixture_response})
    entities = extract_entities("Day-1 PMI 統合", llm)
    assert len(entities) == 2
    assert entities[0].entity_type == "Decision"


def test_extract_entities_invalid_json_raises():
    llm = MockProvider(fixture={"PMI": "not valid json"})
    with pytest.raises(ValueError):
        extract_entities("Day-1 PMI 統合", llm)


def test_extract_entities_non_array_raises():
    llm = MockProvider(fixture={"PMI": '{"not": "array"}'})
    with pytest.raises(ValueError):
        extract_entities("Day-1 PMI 統合", llm)


# === extract_relationships ===


def test_extract_relationships_returns_empty_if_few_entities():
    rels = extract_relationships([_entity("E1", "Decision")], "text", MockProvider())
    assert rels == []


def test_extract_relationships_with_mock():
    fixture = json.dumps([
        {"source_entity_id": "E1", "target_entity_id": "E2", "link_type": "caused_by", "confidence": 0.8}
    ])
    entities = [_entity("E1", "PMICase"), _entity("E2", "Outcome")]
    llm = MockProvider(fixture={"relationship": fixture})
    rels = extract_relationships(entities, "text", llm)
    assert len(rels) == 1
    assert rels[0].link_type == "caused_by"


# === build_entity_graph (NetworkX 段階 1 OS-primitives 利用) ===


def test_build_entity_graph_nodes_and_edges():
    entities = [_entity("E1", "PMICase"), _entity("E2", "Outcome")]
    rels = [Relationship(source_entity_id="E1", target_entity_id="E2", link_type="caused_by", confidence=0.9)]
    g = build_entity_graph(entities, rels)
    assert g.number_of_nodes() == 2
    assert g.number_of_edges() == 1
    assert g.nodes["E1"]["entity_type"] == "PMICase"


def test_build_entity_graph_skips_dangling_edges():
    """relationship が存在しない entity を指す場合、 edge は skip (graph 整合性保持)。"""
    entities = [_entity("E1", "PMICase")]
    rels = [Relationship(source_entity_id="E1", target_entity_id="E_MISSING", link_type="caused_by", confidence=0.9)]
    g = build_entity_graph(entities, rels)
    assert g.number_of_nodes() == 1
    assert g.number_of_edges() == 0  # E_MISSING 不在で skip

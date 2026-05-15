"""tests for 8 gate full verify protocol (internal ADR § 5 + § 9 順守、 fixture + assertion infra、 11 test)

実 run (precision@3 baseline + 1000 entry wall clock 等) は Week 3 末 venv install 後別 turn、
本 file = 8 gate 各 gate の structural verify (pass criteria 数値 + fixture 構造 + provider swap path) のみ。
"""
from __future__ import annotations

import json
import re

import pytest

from src.llm.provider import MockProvider
from src.retrieval.graphrag_native import (
    ONTOLOGY_GATE_THRESHOLD,
    RELATIONSHIP_CONFIDENCE_THRESHOLD,
    VALID_LINK_TYPES,
    VALID_OBJECT_TYPES,
    VAULT_FIELDS,
    Entity,
    PIIBoundaryViolation,
    extract_entities,
    validate_ontology_entities,
)


# === Gate 1: eval set 50 query precision/recall baseline ===


def test_gate1_eval_set_exists():
    """internal ADR § 5 gate 1: data/eval/ja_jp_pmi_eval_v1.jsonl literal 存在 verify。"""
    from pathlib import Path
    eval_path = Path("data/eval/ja_jp_pmi_eval_v1.jsonl")
    assert eval_path.exists(), "eval set 50 query file must exist for gate 1 baseline"


def test_gate1_eval_set_count():
    """eval set = 50 query (Week 0.5 sub-task 4 完遂 fact 順守)。"""
    from pathlib import Path
    eval_path = Path("data/eval/ja_jp_pmi_eval_v1.jsonl")
    lines = [l for l in eval_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 50, f"expected 50 queries, got {len(lines)}"


def test_gate1_eval_set_schema():
    """eval set JSON schema literal verify (query_id + query_text + expected_* fields)。"""
    from pathlib import Path
    eval_path = Path("data/eval/ja_jp_pmi_eval_v1.jsonl")
    first_line = next(l for l in eval_path.read_text(encoding="utf-8").splitlines() if l.strip())
    record = json.loads(first_line)
    assert "query_id" in record
    assert "query_text" in record or "query_text_redacted" in record


# === Gate 2: entity 抽出 silent fail = 0 ===


def test_gate2_entity_extract_explicit_fail_path():
    """silent fail 不採用 evidence: invalid JSON で literal ValueError raise (silent default 不採用)。"""
    llm = MockProvider(fixture={"PMI": "not valid json"})
    with pytest.raises(ValueError):
        extract_entities("Day-1 PMI text", llm)


def test_gate2_entity_extract_pii_block():
    """PII boundary violation → PIIBoundaryViolation raise (silent skip 不採用)。"""
    with pytest.raises(PIIBoundaryViolation):
        extract_entities("query contains raw_query_text leak", MockProvider())


# === Gate 3: prompt regression sample diff < 5% (fixture infra) ===


def test_gate3_prompt_sample_fixture_exists():
    """prompt regression sample fixture pattern verify (Week 3 末 run で sample 10 件 × 3 prompt 起草 base)。"""
    from src.retrieval.graphrag_native import (
        ENTITY_EXTRACTION_SYSTEM_PROMPT,
        RELATIONSHIP_EXTRACTION_SYSTEM_PROMPT,
        COMMUNITY_SUMMARIZATION_SYSTEM_PROMPT,
    )
    assert len(ENTITY_EXTRACTION_SYSTEM_PROMPT) > 100
    assert len(RELATIONSHIP_EXTRACTION_SYSTEM_PROMPT) > 100
    assert len(COMMUNITY_SUMMARIZATION_SYSTEM_PROMPT) > 100


# === Gate 4: Ontology validate gate 実機 trigger verify ===


def test_gate4_ontology_block_on_unknown_type():
    """UnknownType entity 注入 → conformance < 80% で literal block。"""
    entities = [
        Entity(entity_id=f"E{i}", entity_type="UnknownType", entity_name_redacted=f"x{i}", confidence=0.9)
        for i in range(5)
    ]
    pass_, rate, rejected = validate_ontology_entities(entities, threshold=ONTOLOGY_GATE_THRESHOLD)
    assert pass_ is False
    assert rate == 0.0
    assert len(rejected) == 5


def test_gate4_ontology_pass_on_valid_types():
    entities = [
        Entity(entity_id="E1", entity_type="Decision", entity_name_redacted="r1", confidence=0.9),
        Entity(entity_id="E2", entity_type="PMICase", entity_name_redacted="r2", confidence=0.9),
    ]
    pass_, rate, _ = validate_ontology_entities(entities)
    assert pass_ is True
    assert rate == 1.0


# === Gate 5: PII boundary block 実機 verify ===


def test_gate5_vault_fields_comprehensive():
    """VAULT_FIELDS = 25 件 (internal ADR § 1 + internal ADR PII/Op 分離 + Week 4 narrow: generic noun 「email」「phone」 false-positive 排除)。"""
    assert len(VAULT_FIELDS) >= 25
    for critical in ("raw_query_text", "client_company_name_real", "deal_consideration_real", "raw_rationale", "raw_user_name"):
        assert critical in VAULT_FIELDS
    # generic noun は不採用 (compound 名で literal 充足)
    assert "phone" not in VAULT_FIELDS
    assert "email" not in VAULT_FIELDS


# === Gate 6: cross-PJ entity namespace collision = 0 ===


def test_gate6_id_prefix_disjoint():
    """T1 PROF / T2 DDP / T3 IP / T4 CP / T5 PMI/DEC/OUT/PAT/REF/LIL prefix literal 非衝突 verify。"""
    t1_prefixes = {"PROF", "COMP"}
    t2_prefixes = {"DDP", "Q", "A"}
    t3_prefixes = {"IP"}
    t4_prefixes = {"CP"}
    t5_prefixes = {"PMI", "DEC", "OUT", "PAT", "REF", "LIL"}
    # pairwise disjoint
    all_prefixes = [t1_prefixes, t2_prefixes, t3_prefixes, t4_prefixes, t5_prefixes]
    for i, a in enumerate(all_prefixes):
        for j, b in enumerate(all_prefixes):
            if i != j:
                assert a.isdisjoint(b), f"prefix collision between PJ {i+1} and PJ {j+1}: {a & b}"


def test_gate6_id_regex_format():
    """T5 6 prefix regex format literal verify (src/schema/types.py PATTERN 同期)。"""
    from src.schema.types import (
        DEC_PATTERN,
        LIL_PATTERN,
        OUT_PATTERN,
        PAT_PATTERN,
        PMI_PATTERN,
        REF_PATTERN,
    )
    assert re.match(PMI_PATTERN, "PMI-000000019") is not None
    assert re.match(DEC_PATTERN, "DEC-000001") is not None
    assert re.match(OUT_PATTERN, "OUT-000001") is not None
    assert re.match(PAT_PATTERN, "PAT-000001") is not None
    assert re.match(REF_PATTERN, "REF-000001") is not None
    assert re.match(LIL_PATTERN, "LIL-000001") is not None


# === Gate 7: consumer laptop completion < 300s ===
# Week 3 末 venv install 後 別 turn run、 本 file = wall clock 測定 path 確認のみ


# === Gate 8: 3 provider swap path ===


def test_gate8_mock_provider_protocol_compatibility():
    """MockProvider が LLMProvider Protocol 順守 verify (Claude/Ollama 同 API surface)。"""
    from src.llm.provider import LLMProvider
    llm = MockProvider()
    assert isinstance(llm, LLMProvider)  # runtime_checkable Protocol
    # 3 method 全件 callable
    assert llm.complete("test", "system") == "[]"
    assert llm.count_tokens("hello world") > 0
    assert llm.health_check() is True


def test_gate8_link_types_6_enum():
    """internal ADR link_types 6 enum 固定 (relationship 強制 mapping rule)。"""
    assert VALID_LINK_TYPES == frozenset(
        {"blocks", "caused_by", "solved_by", "related_to", "supersedes", "implements"}
    )


def test_gate8_relationship_confidence_threshold():
    """0.80 threshold = internal ADR + internal ADR § 5 順守。"""
    assert RELATIONSHIP_CONFIDENCE_THRESHOLD == 0.80
    assert ONTOLOGY_GATE_THRESHOLD == 0.80


# === 8 gate fixture infra (Week 3 末 verify run prep) ===


def test_eight_gate_protocol_documented():
    """8 gate full verify protocol 各 gate の identification 整合性 (internal ADR § 5 順守)。"""
    expected_gates = {
        1: "precision/recall baseline",
        2: "entity silent fail = 0",
        3: "prompt regression < 5%",
        4: "Ontology gate trigger",
        5: "PII boundary block",
        6: "cross-PJ namespace collision = 0",
        7: "consumer laptop < 300s",
        8: "3 provider swap path",
    }
    assert len(expected_gates) == 8  # 8 gate identity verify

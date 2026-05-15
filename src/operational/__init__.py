"""T5 Operational DB module (Week 4、 internal ADR PII/Op 分離 + internal ADR § 4 順守、 T1 inherit pattern)。

module boundaries:
- 段階 1 OS-primitives: なし (pure Python + Pydantic、 stdlib only)
- 段階 2 business logic: 6 type JSONL store (PMICase / Decision / Outcome / Pattern / ReferencePaper / AssistantQuery) + load_all + list_by + filter (literal 自作)

T5 operational scope (PII redact 済 = embedding / retrieval / assistant が literal 読む唯一の data source):
- pmi_cases.jsonl: PMICase (summary_redacted のみ、 client_company_name_real は vault)
- decisions.jsonl: Decision (rationale_redacted のみ、 raw_rationale は vault)
- outcomes.jsonl: Outcome (retrospective_redacted のみ、 raw_retrospective は vault)
- patterns.jsonl: Pattern (cross_case_evidence_redacted のみ、 raw_owner_name は vault)
- reference_papers.jsonl: ReferencePaper (abstract_redacted + chunks redacted のみ、 paper_signatory は vault)
- assistant_queries.jsonl: AssistantQuery (query_text_redacted のみ、 raw_query_text は vault)

import 禁止: ontology / retrieval / assistant / integration / pipeline / vault / citation / api / llm は本 module import 禁止 (PII/Op 分離 構造的 enforce、 systemPatterns.md SSoT)。
"""
from .store import (
    get_decision,
    get_assistant_query,
    get_outcome,
    get_pattern,
    get_pmi_case,
    get_reference_paper,
    list_decisions,
    list_assistant_queries,
    list_outcomes,
    list_patterns,
    list_pmi_cases,
    list_reference_papers,
    store_decision,
    store_assistant_query,
    store_outcome,
    store_pattern,
    store_pmi_case,
    store_reference_paper,
)

__all__ = [
    "get_decision",
    "get_assistant_query",
    "get_outcome",
    "get_pattern",
    "get_pmi_case",
    "get_reference_paper",
    "list_decisions",
    "list_assistant_queries",
    "list_outcomes",
    "list_patterns",
    "list_pmi_cases",
    "list_reference_papers",
    "store_decision",
    "store_assistant_query",
    "store_outcome",
    "store_pattern",
    "store_pmi_case",
    "store_reference_paper",
]

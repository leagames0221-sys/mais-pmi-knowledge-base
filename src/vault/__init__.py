"""T5 PII Vault module (Week 4、 internal ADR § 4 順守、 T1-T4 inherit pattern)。

module boundaries 段階 1 OS-primitives: cryptography.Fernet (PyCA 公式、 BSD)
module boundaries 段階 2 business logic: T5 PMI vault content (raw_query_text / raw_user_name / raw_rationale / raw_retrospective 等) + audit log emit (literal 自作)

T5 vault scope (PII/Op 分離 順守):
- raw_query_text: AssistantQuery.query_text_redacted の raw (Assistant 対話 audit)
- raw_user_name: AssistantQuery.user_name の raw (junior consultant 氏名)
- raw_rationale: Decision.rationale_redacted の raw
- raw_retrospective: Outcome.retrospective_redacted の raw
- client_company_name_real + deal_consideration_real: PMICase の raw
- raw_owner_name + raw_owner_quote: Pattern.cross_case_evidence_redacted の raw
- paper_signatory + acknowledgments_raw: ReferencePaper の raw

import 禁止: ontology / retrieval / assistant / integration / pipeline / operational / citation / api / llm は本 module literal import 禁止 (drift-check CI で boundary check、 systemPatterns.md SSoT)。
"""
from .store import (
    decrypt_from_vault,
    emit_audit,
    encrypt_to_vault,
    generate_key,
)

__all__ = [
    "decrypt_from_vault",
    "emit_audit",
    "encrypt_to_vault",
    "generate_key",
]

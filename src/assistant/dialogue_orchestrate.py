"""AI Assistant dialogue orchestration — full active implementation.

Module boundaries (3 tiers):
- Tier 1 OS-primitives: anthropic SDK via LLMProvider (direct use OK)
- Tier 2 business logic: listwise CoT prompt + AssistantCounter persistent + audit log emit + PII vault separation (in-house)
- Tier 3: not applicable

Pipeline evolution (Week 2 stub -> Week 3 active):
- Week 2 stub: top-K cases → simple ranked recommendation (timestamp ms 末尾 6 桁 LIL id)
- Week 3 active: top-K cases + community summaries + RAG paper chunks → LLM listwise CoT ranked + citation_array
  + AssistantCounter persistent storage (counter base) + 3 file 分離 audit (log/counter/vault)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from pydantic import BaseModel, Field

from ..llm.provider import LLMProvider
from ..retrieval.graphrag_native import CommunitySummary
from ..retrieval.multi_axis_similar_cases import SimilarityScore
from ..schema.types import AssistantQuery, RecommendationItem, UserRole

# Windows cp932 console UTF-8 reconfigure (T3 学び doctrine: analogical-recall inherit)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8") # type: ignore[attr-defined]
    except Exception:
        pass


# ============================================================================
# Constants
# ============================================================================

# LIL id 6 桁 counter 上限 (999999 → 移植段階で 9 桁拡張 path、 doctrine: future-proof)
LIL_COUNTER_MAX: int = 999999

# default audit dir (Week 4 移植段階で 顧客 sandbox path 上書き可)
DEFAULT_AUDIT_DIR: Path = Path("data/audit")

# top-K recommendations 件数 (original proposal line 461「2-3 件」 + RecommendationItem rank ≤ 10)
DEFAULT_TOP_K: int = 3


# ============================================================================
# AssistantDialogueRequest schema
# ============================================================================


class AssistantDialogueRequest(BaseModel):
    """Assistant 対話 request schema (audit trail 入口)。"""

    query_text_redacted: str = Field(..., min_length=1, max_length=200, description="PII redact 済 query")
    user_role: UserRole
    context_pmi_id: Optional[str] = Field(default=None, description="任意 context PMICase id")
    max_recommendations: int = Field(default=DEFAULT_TOP_K, ge=1, le=10)


# ============================================================================
# LISTWISE CoT prompt
# ============================================================================

LISTWISE_COT_SYSTEM_PROMPT = """\
あなたは M&A PMI 案件 expert です。 junior consultant の query に対し、 過去類似 case + cross-case pattern + reference paper から literal listwise CoT で recommendation を rank します。

絶対 rules:
- 出力 = ranked list、 各 item に reasoning step + confidence + citation_array (REF-id / PMI-id list)
- citation_array 不在の recommendation = literal 出力禁止 (doctrine: citation-required 順守)
- confidence は evidence 強度に応じ 0.0-1.0 で literal calibrate、 hardcode 禁止
- 個人氏名 / 取引先実名 / 内部金額 を recommendation_redacted に含めない (PII redact 強制)

listwise CoT reasoning step:
1. 各候補 (case + community summary + paper chunk) の relevance を query 5 dim (industry / size / culture / financial / integration_type) と照らし literal scoring
2. cross-case pattern match (PAT-XXXXXX) 該当時は literal surface
3. paper 引用は specific recommendation を裏付ける場合のみ literal cite
4. final ranking = relevance × confidence × pattern_strength の weighted aggregate

出力 format (JSON array、 他テキスト一切禁止):
[
  {
    "rank": 1,
    "recommendation_redacted": "(200 字以内 redacted recommendation、 reasoning step 内蔵)",
    "confidence": 0.85,
    "citation_array": ["PMI-000000019", "REF-000007"]
  },
  ...
]
"""


# ============================================================================
# AssistantCounter
# ============================================================================


class AssistantCounter:
    """LIL id counter persistent storage。

    jsonl tail-based + atomic write pattern (single-user PoC、 移植段階 = sqlite + row-level lock active 化 path)。
    """

    def __init__(self, audit_dir: Optional[Path] = None) -> None:
        self.audit_dir = Path(audit_dir) if audit_dir else DEFAULT_AUDIT_DIR
        self.counter_path = self.audit_dir / "assistant_counter.jsonl"

    def _read_current_counter(self) -> int:
        """jsonl tail から current counter literal probe。 file 不在 = 0 返却。"""
        if not self.counter_path.exists():
            return 0
        try:
            with self.counter_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
            if not lines:
                return 0
            last = json.loads(lines[-1].strip())
            value = int(last.get("counter", 0))
            return value
        except (json.JSONDecodeError, ValueError, OSError):
            # corruption fallback (8 gate gate 5 PII boundary block 実機 verify と pair で recovery path)
            return 0

    def _atomic_append(self, record: dict[str, object]) -> None:
        """jsonl 1 行 atomic append (file lock pattern stdlib only)。"""
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        # O_APPEND flag で literal atomic line write (single-line jsonl は 1 syscall append 想定)
        fd = os.open(
            str(self.counter_path),
            os.O_WRONLY | os.O_APPEND | os.O_CREAT,
            0o600,
        )
        try:
            os.write(fd, (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)

    def next_id(self) -> str:
        """次 LIL id 取得 + counter increment + persistent record append。

        Raises:
            RuntimeError: counter 上限到達 (999999、 doctrine: future-proof 9 桁拡張 trigger)
        """
        current = self._read_current_counter()
        next_value = current + 1
        if next_value > LIL_COUNTER_MAX:
            raise RuntimeError(
                f"LIL counter overflow: {next_value} > {LIL_COUNTER_MAX}。 "
                "doctrine: future-proof 9 桁拡張 trigger (AIQ-XXXXXXXXX format への migration)。"
            )
        lil_id = f"LIL-{next_value:06d}"
        record = {
            "counter": next_value,
            "lil_id": lil_id,
            "at": datetime.now().isoformat(),
        }
        self._atomic_append(record)
        return lil_id


# ============================================================================
# Assistant recommend
# ============================================================================


def _format_context(
    top_k_cases: Sequence[SimilarityScore],
    community_summaries: Sequence[CommunitySummary],
    retrieved_papers: Sequence[str],
) -> str:
    """LLM context block format (similar cases + community + paper)。"""
    blocks: list[str] = []
    if top_k_cases:
        blocks.append("## Similar PMI cases (multi-axis 5 dim weighted)")
        for i, score in enumerate(top_k_cases, start=1):
            blocks.append(
                f"{i}. {score.candidate_pmi_id} (aggregate={score.aggregate_score:.3f}, "
                f"industry={score.industry_score:.2f}, culture={score.culture_score:.2f}, "
                f"size={score.size_score:.2f}, integration={score.integration_type_score:.2f}, "
                f"financial={score.financial_score:.2f})"
            )
    if community_summaries:
        blocks.append("\n## Cross-case communities (Leiden algorithm)")
        for cs in community_summaries:
            blocks.append(f"- {cs.community_id}: {cs.summary_redacted} {cs.dimension_aggregation}")
    if retrieved_papers:
        blocks.append("\n## Reference papers")
        for ref_id in retrieved_papers:
            blocks.append(f"- {ref_id}")
    return "\n".join(blocks) if blocks else "(no context provided)"


def assistant_recommend(
    request: AssistantDialogueRequest,
    top_k_cases: Sequence[SimilarityScore],
    community_summaries: Sequence[CommunitySummary],
    retrieved_papers: Sequence[str],
    llm: LLMProvider,
) -> list[RecommendationItem]:
    """LLM listwise CoT で ranked recommendation 生成。

    Args:
        request: AssistantDialogueRequest (query + user_role + max_recommendations)
        top_k_cases: 多軸 weighted similarity top-K
        community_summaries: Leiden community summarization
        retrieved_papers: paper REF-id list
        llm: LLMProvider (MockProvider / ClaudeProvider / OllamaProvider)

    Returns:
        ranked RecommendationItem list (length ≤ request.max_recommendations)

    Raises:
        ValueError: LLM response が JSON array でない / Pydantic validation error
    """
    context_block = _format_context(top_k_cases, community_summaries, retrieved_papers)
    user_prompt = (
        f"# Junior consultant query\n{request.query_text_redacted}\n\n"
        f"# Available context\n{context_block}\n\n"
        f"# Instruction\n"
        f"以上 context から rank ≤ {request.max_recommendations} の ranked recommendation を listwise CoT で出力してください。"
    )
    raw_response = llm.complete(
        prompt=user_prompt,
        system=LISTWISE_COT_SYSTEM_PROMPT,
        temperature=0.0,
        max_tokens=2000,
    )
    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise ValueError(
            f"LLM response must be a JSON array, got {type(parsed).__name__}"
        )
    items: list[RecommendationItem] = []
    for raw_item in parsed:
        item = RecommendationItem.model_validate(raw_item)
        items.append(item)
    # rank 順 sort (defensive、 LLM 出力 rank が unsorted 時の正規化)
    items.sort(key=lambda r: r.rank)
    return items[: request.max_recommendations]


# ============================================================================
# Audit log emit
# ============================================================================


def emit_assistant_audit(
    request: AssistantDialogueRequest,
    recommendations: list[RecommendationItem],
    retrieved_cases: list[str],
    retrieved_papers: list[str],
    counter: AssistantCounter,
    raw_query_text: Optional[str] = None,
    user_name: Optional[str] = None,
) -> AssistantQuery:
    """AssistantQuery schema literal emit + 3 file 分離 audit。

    - operational audit (`assistant_log.jsonl`): PII redact 済 AssistantQuery
    - vault audit (`assistant_vault.jsonl`): raw_query_text + user_name separate file (Week 4 Fernet 暗号化 active)
    - counter (`assistant_counter.jsonl`): AssistantCounter.next_id 経由 literal append

    Args:
        raw_query_text: vault audit 用 raw query (None なら vault emit 不発)
        user_name: vault audit 用 user 氏名 (None なら vault emit 不発)
    """
    lil_id = counter.next_id()
    assistant_query = AssistantQuery(
        lil_id=lil_id,
        query_text_redacted=request.query_text_redacted,
        retrieved_cases=retrieved_cases,
        retrieved_papers=retrieved_papers,
        recommendation_ranked=recommendations,
        user_role=request.user_role,
    )

    # operational audit log emit
    log_path = counter.audit_dir / "assistant_log.jsonl"
    counter.audit_dir.mkdir(parents=True, exist_ok=True)
    log_record = assistant_query.model_dump(mode="json")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_record, ensure_ascii=False) + "\n")

    # vault audit (raw value 分離、 Week 4 Fernet 暗号化 active 化 trigger 点)
    if raw_query_text is not None or user_name is not None:
        vault_path = counter.audit_dir / "assistant_vault.jsonl"
        vault_record = {
            "lil_id": lil_id,
            "raw_query_text": raw_query_text,
            "user_name": user_name,
            "at": datetime.now().isoformat(),
        }
        with vault_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(vault_record, ensure_ascii=False) + "\n")

    return assistant_query


__all__ = [
    "LIL_COUNTER_MAX",
    "DEFAULT_AUDIT_DIR",
    "DEFAULT_TOP_K",
    "AssistantDialogueRequest",
    "LISTWISE_COT_SYSTEM_PROMPT",
    "AssistantCounter",
    "assistant_recommend",
    "emit_assistant_audit",
]

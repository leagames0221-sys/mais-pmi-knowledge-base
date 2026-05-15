"""Citation infra

module boundaries 越境境界線 3 段階 順守:
- 段階 1 OS-primitives: llama-index-core (MIT、 T2/T3/T4 inherit、 lazy import) + anthropic SDK (literal use OK)
- 段階 2 business logic: PaperIndex 経由 CitationEngine + REF-id mapping + format_citations + Anthropic Citations API swap path adapter (literal 自作)

Design:
- PoC primary path = native PaperIndex (faiss IndexFlatIP) 経由 citation (always testable、 LlamaIndex 不在環境で literal run 可能)
- LlamaIndex CitationQueryEngine bridge = build_llamaindex_citation_engine (lazy import、 移植段階 active path 確保)
- Anthropic Citations API 2026 official swap path = 8 gate gate 8 verify 連携 (Week 3 末)
"""
from __future__ import annotations

import re
import sys
from typing import Any, Optional, Sequence

from pydantic import BaseModel, Field

from ..ingestion.chunk_embed import PaperIndex, TextChunk
from ..llm.provider import LLMProvider
from ..schema.types import RecommendationItem

# Windows cp932 console UTF-8 reconfigure (T3 学び doctrine: analogical-recall inherit)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8") # type: ignore[attr-defined]
    except Exception:
        pass


# ============================================================================
# Constants
# ============================================================================

DEFAULT_TOP_K: int = 5
DEFAULT_CITATION_CHUNK_SIZE: int = 1024
REF_ID_PATTERN: re.Pattern[str] = re.compile(r"^REF-[0-9]{6}$")
PMI_ID_PATTERN: re.Pattern[str] = re.compile(r"^PMI-[0-9]{9}$")


# ============================================================================
# Citation schemas (transient retrieval result、 src/schema/types.py 7th type 不採用)
# ============================================================================


class CitedChunk(BaseModel):
    """1 件 chunk + REF-id citation (CitationResponse 構成要素)。"""

    ref_id: str = Field(..., pattern=r"^REF-[0-9]{6}$")
    chunk_id: str = Field(..., min_length=1, max_length=100)
    text_excerpt: str = Field(..., max_length=2000, description="redacted excerpt、 PII boundary 内")
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    section_heading: Optional[str] = None


class CitationResponse(BaseModel):
    """query → top-K citation 統合 response (assistant citation_array source)。"""

    query_text_redacted: str
    cited_chunks: list[CitedChunk]
    citation_array: list[str] = Field(default_factory=list, description="unique REF-id list (cited_chunks 由来)")


# ============================================================================
# CitationEngine (native PaperIndex 経由、 PoC primary path)
# ============================================================================


def _extract_ref_id(chunk_id: str) -> Optional[str]:
    """chunk_id 「REF-XXXXXX-CHK-YYYYYY」 → REF-XXXXXX literal extract。"""
    parts = chunk_id.split("-CHK-")
    if len(parts) != 2:
        return None
    candidate = parts[0]
    return candidate if REF_ID_PATTERN.match(candidate) else None


class CitationEngine:
    """PaperIndex 経由 citation generation。

    LlamaIndex CitationQueryEngine inherit pattern (T2/T3/T4 inherit): query → top-K chunks + citation_array + relevance score。
    PoC 段階 = PaperIndex (faiss IndexFlatIP) wrap、 移植段階 = build_llamaindex_citation_engine() で LlamaIndex bridge active。
    """

    def __init__(
        self,
        paper_index: PaperIndex,
        llm: Optional[LLMProvider] = None,
        citation_chunk_size: int = DEFAULT_CITATION_CHUNK_SIZE,
    ) -> None:
        self.paper_index = paper_index
        self.llm = llm
        self.citation_chunk_size = citation_chunk_size

    def query_with_citations(
        self,
        query_text_redacted: str,
        query_embedding: Sequence[float],
        top_k: int = DEFAULT_TOP_K,
    ) -> CitationResponse:
        """query embedding → top-K chunks + REF-id citation_array。

        Args:
            query_text_redacted: PII redact 済 query (audit log surface 用、 200 字 推奨)
            query_embedding: pre-computed embedding (sentence-transformers 等)
            top_k: top-K chunks (default 5、 original proposal line 461 PMI 「2-3 件」 と異なり paper RAG = 5 件 cover)
        """
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")
        results = self.paper_index.search(list(query_embedding), top_k=top_k)
        cited: list[CitedChunk] = []
        ref_ids_seen: list[str] = []
        for chunk, score in results:
            ref_id = _extract_ref_id(chunk.chunk_id)
            if ref_id is None:
                continue
            excerpt = chunk.text[: self.citation_chunk_size]
            cited.append(
                CitedChunk(
                    ref_id=ref_id,
                    chunk_id=chunk.chunk_id,
                    text_excerpt=excerpt,
                    relevance_score=max(0.0, min(1.0, float(score))),
                    section_heading=chunk.section_heading,
                )
            )
            if ref_id not in ref_ids_seen:
                ref_ids_seen.append(ref_id)
        return CitationResponse(
            query_text_redacted=query_text_redacted[:200],
            cited_chunks=cited,
            citation_array=ref_ids_seen,
        )


# ============================================================================
# LlamaIndex CitationQueryEngine bridge (lazy import、 移植段階 active path)
# ============================================================================


def build_llamaindex_citation_engine(
    paper_index: PaperIndex,
    citation_chunk_size: int = DEFAULT_CITATION_CHUNK_SIZE,
) -> Any:
    """LlamaIndex CitationQueryEngine literal bridge (lazy import、 移植段階 active)。

    PoC = stub return (CitationEngine native path 利用)、 移植段階 = literal LlamaIndex CitationQueryEngine + response_synthesizer + retriever 配線。

    Raises:
        RuntimeError: llama-index-core not installed
    """
    try:
        # llama-index-core lazy import
        import llama_index.core # type: ignore[import-not-found] # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "llama-index-core not installed。 "
            "Run: pip install 'llama-index-core>=0.14,<1.0'"
        ) from exc
    # 移植段階 = literal CitationQueryEngine 配線 (PoC = native CitationEngine 採用、 LlamaIndex 全体 inject 不採用 module boundaries 段階 3 順守)
    # 本 function は LlamaIndex 存在 verify + 移植 bridge stub return、 actual 配線は Week 4 移植段階で literal 起草
    return {"status": "llama_index_available", "paper_index": paper_index, "citation_chunk_size": citation_chunk_size}


# ============================================================================
# format_citations (Assistant recommendation citation_array → surface string)
# ============================================================================


def format_citations(items: Sequence[RecommendationItem]) -> str:
    """Assistant RecommendationItem list の citation_array を「[REF-000001, PMI-000000007]」 format で surface。

    Returns:
        rank 順 + citation_array が surface format で literal 列挙された string。
        items 空 = "(no recommendations)"。
    """
    if not items:
        return "(no recommendations)"
    lines: list[str] = []
    for item in items:
        if item.citation_array:
            citation_block = "[" + ", ".join(item.citation_array) + "]"
        else:
            citation_block = "[no citation]"
        # 検出: REF-id + PMI-id を category 別 surface (REF = paper、 PMI = case)
        ref_ids = [c for c in item.citation_array if REF_ID_PATTERN.match(c)]
        pmi_ids = [c for c in item.citation_array if PMI_ID_PATTERN.match(c)]
        meta_block = ""
        if ref_ids or pmi_ids:
            meta_parts: list[str] = []
            if ref_ids:
                meta_parts.append(f"papers={len(ref_ids)}")
            if pmi_ids:
                meta_parts.append(f"cases={len(pmi_ids)}")
            meta_block = " (" + " / ".join(meta_parts) + ")"
        lines.append(
            f"Rank {item.rank} (conf={item.confidence:.2f}){meta_block}: "
            f"{item.recommendation_redacted}\n → cite: {citation_block}"
        )
    return "\n\n".join(lines)


# ============================================================================
# Anthropic Citations API swap path foundation (8 gate gate 8 連携、 Week 3 末 verify)
# ============================================================================


def anthropic_citations_adapter_stub(query: str, response: CitationResponse) -> dict[str, Any]:
    """Anthropic Citations API (2026 official) swap path stub。

    Week 3 = stub return (8 gate gate 8 swap path verify foundation)、 Week 4 移植段階 = literal anthropic.messages.create with citations=True 配線。

    Returns:
        Anthropic Citations API request payload format (literal stub、 actual call は移植段階)
    """
    documents = [
        {
            "type": "document",
            "source": {"type": "text", "data": chunk.text_excerpt},
            "title": chunk.ref_id,
            "context": chunk.section_heading or "(no section)",
            "citations": {"enabled": True},
        }
        for chunk in response.cited_chunks
    ]
    return {
        "model_hint": "claude-haiku-4-5",
        "messages": [
            {
                "role": "user",
                "content": [
                    *documents,
                    {"type": "text", "text": query},
                ],
            }
        ],
        "_stub_note": "Week 3 foundation、 Week 4 移植段階で literal anthropic SDK call + citations=True active",
    }


__all__ = [
    "DEFAULT_TOP_K",
    "DEFAULT_CITATION_CHUNK_SIZE",
    "REF_ID_PATTERN",
    "PMI_ID_PATTERN",
    "CitedChunk",
    "CitationResponse",
    "CitationEngine",
    "build_llamaindex_citation_engine",
    "format_citations",
    "anthropic_citations_adapter_stub",
]

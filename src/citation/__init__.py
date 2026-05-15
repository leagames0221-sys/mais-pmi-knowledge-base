"""citation module (internal ADR § 3 順守、 LlamaIndex CitationQueryEngine inherit pattern + REF-id mapping)。

Week 3 active:
- citation_engine.py: CitationEngine (PaperIndex 経由 query + citation_array) + format_citations + LlamaIndex bridge stub + Anthropic Citations API swap path foundation

module boundaries 越境境界線 3 段階 順守:
- 段階 1 OS-primitives: llama-index-core (MIT、 T2/T3/T4 inherit、 lazy import) + anthropic SDK (literal use OK)
- 段階 2 business logic: REF-id mapping + citation_array format + 8 gate gate 8 swap path adapter (literal 自作)
"""
from .citation_engine import (
    CitationEngine,
    CitationResponse,
    CitedChunk,
    build_llamaindex_citation_engine,
    format_citations,
)

__all__ = [
    "CitationEngine",
    "CitationResponse",
    "CitedChunk",
    "build_llamaindex_citation_engine",
    "format_citations",
]

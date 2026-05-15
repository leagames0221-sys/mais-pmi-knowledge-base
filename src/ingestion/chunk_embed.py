"""chunk + embed pipeline

module boundaries:
- 段階 1 OS-primitives: sentence-transformers + faiss-cpu (literal use OK、 cross-PJ python-ml-stack Standard Pin)
- 段階 2 business logic: chunking algorithm + PaperIndex class (literal 自作、 LlamaIndex SentenceSplitter decomposed prior art)
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Optional

# Windows cp932 console UTF-8 reconfigure (T3 学び doctrine: analogical-recall inherit)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8") # type: ignore[attr-defined]
    except Exception:
        pass


# ============================================================================
# Constants
# ============================================================================

DEFAULT_CHUNK_SIZE: int = 1000
DEFAULT_OVERLAP: int = 200
DEFAULT_EMBEDDING_MODEL: str = "sentence-transformers/multilingual-e5-large"


# ============================================================================
# Chunk schema (transient、 src/schema/types.py PaperChunk と pair)
# ============================================================================


@dataclass
class TextChunk:
    """段落単位 chunk (PaperChunk schema mapping 前 transient)。"""

    chunk_id: str
    text: str
    char_start: int
    char_end: int
    section_heading: Optional[str] = None
    embedding: Optional[list[float]] = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# chunk_paper (LlamaIndex SentenceSplitter pattern 自作)
# ============================================================================


def chunk_paper(
    markdown: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    ref_id: str = "REF-000000",
) -> list[TextChunk]:
    """markdown → list[TextChunk] (段落単位 chunking + char count window、 LlamaIndex SentenceSplitter pattern 自作)。

    algorithm:
    1. 段落 split (改行 2+ 連続で split)
    2. 段落 buffer に accumulate、 chunk_size 超過で flush
    3. flush 時 overlap char 分 を次 chunk へ inherit
    4. chunk_id = {ref_id}-CHK-XXXXXX (6 桁 zero-padded)

    Raises:
        ValueError: chunk_size <= overlap (overlap が chunk size 以上で literal infinite loop)
    """
    if chunk_size <= overlap:
        raise ValueError(
            f"chunk_size ({chunk_size}) must be > overlap ({overlap})、 infinite loop 防御"
        )
    if not markdown:
        return []

    # 段落 split (空行 2+ 連続で literal break)
    paragraphs = [p.strip() for p in markdown.split("\n\n") if p.strip()]
    chunks: list[TextChunk] = []
    buffer: list[str] = []
    buffer_char_count = 0
    char_pos = 0
    chunk_index = 1

    def emit_chunk(text_segment: str, start: int, end: int) -> None:
        nonlocal chunk_index
        chunks.append(
            TextChunk(
                chunk_id=f"{ref_id}-CHK-{chunk_index:06d}",
                text=text_segment,
                char_start=start,
                char_end=end,
            )
        )
        chunk_index += 1

    for paragraph in paragraphs:
        para_len = len(paragraph)
        if buffer_char_count + para_len + 2 > chunk_size and buffer:
            # flush current buffer
            chunk_text = "\n\n".join(buffer)
            chunk_start = char_pos
            chunk_end = char_pos + len(chunk_text)
            emit_chunk(chunk_text, chunk_start, chunk_end)
            # overlap inherit: tail char overlap 分を次 chunk へ literal carry
            tail = chunk_text[-overlap:] if overlap < len(chunk_text) else chunk_text
            buffer = [tail]
            buffer_char_count = len(tail)
            char_pos = chunk_end - len(tail)
        buffer.append(paragraph)
        buffer_char_count += para_len + 2 # +2 for \n\n separator

    if buffer:
        chunk_text = "\n\n".join(buffer)
        emit_chunk(chunk_text, char_pos, char_pos + len(chunk_text))

    return chunks


# ============================================================================
# embed_chunks (sentence-transformers + faiss thin wrapper、 段階 1 OS-primitives)
# ============================================================================


def embed_chunks(
    chunks: list[TextChunk],
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 32,
) -> list[TextChunk]:
    """chunks → embedding 注入 (sentence-transformers thin wrapper、 段階 1)。

    Raises:
        RuntimeError: sentence-transformers not installed
    """
    if not chunks:
        return chunks
    try:
        from sentence_transformers import SentenceTransformer # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers not installed。 "
            "Run: pip install 'sentence-transformers>=5.4,<6.0' 'transformers>=5.0,<6.0'"
        ) from exc

    model = SentenceTransformer(model_name)
    texts = [c.text for c in chunks]
    embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=False)
    for chunk, emb in zip(chunks, embeddings):
        chunk.embedding = emb.tolist() if hasattr(emb, "tolist") else list(emb)
    return chunks


# ============================================================================
# PaperIndex (faiss IndexFlatIP thin wrapper、 段階 1 + 段階 2 light schema)
# ============================================================================


class PaperIndex:
    """faiss IndexFlatIP thin wrapper + chunk_id reverse lookup。

    PoC scope: in-memory IndexFlatIP (≤ 数万 chunk literal cover、 doctrine: consumer-hw)、 移植段階 = IndexIVFFlat path 確保。
    """

    def __init__(self, dim: int) -> None:
        self.dim = dim
        self.chunks: list[TextChunk] = []
        self._faiss_index: Any = None

    def _build_index(self) -> Any:
        try:
            import faiss # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "faiss-cpu not installed。 "
                "Run: pip install 'faiss-cpu>=1.8,<2.0'"
            ) from exc
        return faiss.IndexFlatIP(self.dim)

    def add(self, chunks: list[TextChunk]) -> None:
        """chunks に embedding 必須、 IndexFlatIP literal append。"""
        try:
            import numpy as np # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("numpy required for PaperIndex") from exc
        if not chunks:
            return
        if self._faiss_index is None:
            self._faiss_index = self._build_index()
        for chunk in chunks:
            if chunk.embedding is None:
                raise ValueError(f"chunk {chunk.chunk_id} has no embedding、 embed_chunks() を先に call")
        vectors = np.array([c.embedding for c in chunks], dtype="float32")
        # IP は normalized で cosine 等価、 L2 normalize literal apply
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vectors = vectors / norms
        self._faiss_index.add(vectors)
        self.chunks.extend(chunks)

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[tuple[TextChunk, float]]:
        """query embedding → top-K (chunk, score) (cosine via normalized IP)。"""
        if self._faiss_index is None or not self.chunks:
            return []
        try:
            import numpy as np # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("numpy required") from exc
        query = np.array([query_embedding], dtype="float32")
        norm = np.linalg.norm(query)
        if norm > 0:
            query = query / norm
        scores, indices = self._faiss_index.search(query, top_k)
        results: list[tuple[TextChunk, float]] = []
        for idx, score in zip(indices[0], scores[0]):
            if 0 <= idx < len(self.chunks):
                results.append((self.chunks[idx], float(score)))
        return results


__all__ = [
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_OVERLAP",
    "DEFAULT_EMBEDDING_MODEL",
    "TextChunk",
    "chunk_paper",
    "embed_chunks",
    "PaperIndex",
]

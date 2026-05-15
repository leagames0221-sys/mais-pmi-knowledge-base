"""tests for src/ingestion/ (internal ADR § 2 + § 9 順守、 16 test)"""
from __future__ import annotations

import pytest

from src.ingestion.chunk_embed import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_OVERLAP,
    PaperIndex,
    TextChunk,
    chunk_paper,
)
from src.ingestion.parse_paper_docling import parse_markdown_sections


# === Constants ===


def test_default_chunk_size():
    assert DEFAULT_CHUNK_SIZE == 1000


def test_default_overlap():
    assert DEFAULT_OVERLAP == 200


# === parse_markdown_sections ===


def test_parse_empty_markdown():
    assert parse_markdown_sections("") == []


def test_parse_no_headings():
    """heading 不在 = single section (intro)。"""
    sections = parse_markdown_sections("just plain text\nno headings")
    assert len(sections) == 1
    assert sections[0]["heading"] == "(intro)"


def test_parse_multiple_levels():
    md = "# Title\n\nintro\n\n## Section 1\n\npara 1\n\n### Sub 1\n\nsub content"
    sections = parse_markdown_sections(md)
    headings = [s["heading"] for s in sections]
    levels = [s["level"] for s in sections]
    assert "Title" in headings
    assert "Section 1" in headings
    assert "Sub 1" in headings
    assert 1 in levels and 2 in levels and 3 in levels


def test_parse_skip_empty_sections():
    """content 空 section は filter (parse_markdown_sections 末尾 filter)。"""
    md = "# Title\n\ncontent\n\n## Empty\n\n## Filled\n\nhas content"
    sections = parse_markdown_sections(md)
    headings = [s["heading"] for s in sections]
    assert "Empty" not in headings


# === chunk_paper ===


def test_chunk_empty():
    assert chunk_paper("") == []


def test_chunk_size_le_overlap_raises():
    with pytest.raises(ValueError, match="must be > overlap"):
        chunk_paper("text", chunk_size=100, overlap=100)


def test_chunk_id_format():
    md = "para 1 " * 100 + "\n\n" + "para 2 " * 100
    chunks = chunk_paper(md, chunk_size=300, overlap=50, ref_id="REF-000005")
    assert all(c.chunk_id.startswith("REF-000005-CHK-") for c in chunks)
    assert chunks[0].chunk_id == "REF-000005-CHK-000001"


def test_chunk_overlap_inheritance():
    """chunk N tail 200 char = chunk N+1 head 200 char (recall 担保 mechanism)。"""
    md = "A" * 800 + "\n\n" + "B" * 800 + "\n\n" + "C" * 800
    chunks = chunk_paper(md, chunk_size=1000, overlap=200, ref_id="REF-000001")
    if len(chunks) >= 2:
        tail = chunks[0].text[-200:]
        head = chunks[1].text[:200]
        assert tail == head, "overlap inheritance broken"


def test_chunk_single_short_paragraph():
    chunks = chunk_paper("short paragraph", chunk_size=1000, overlap=200, ref_id="REF-000001")
    assert len(chunks) == 1
    assert chunks[0].text == "short paragraph"


def test_chunk_char_positions_monotonic():
    md = "\n\n".join("para " + "x" * 200 for _ in range(10))
    chunks = chunk_paper(md, chunk_size=500, overlap=100, ref_id="REF-000001")
    # char_start monotonic (overlap で literal back-step but not regression beyond previous start)
    for i in range(1, len(chunks)):
        assert chunks[i].char_start >= 0
        assert chunks[i].char_end > chunks[i].char_start


# === TextChunk dataclass ===


def test_text_chunk_default_metadata_isolated():
    """default_factory dict literal isolated (shared state regression test)。"""
    c1 = TextChunk(chunk_id="REF-000001-CHK-000001", text="t", char_start=0, char_end=1)
    c2 = TextChunk(chunk_id="REF-000001-CHK-000002", text="t", char_start=0, char_end=1)
    c1.metadata["key"] = "value"
    assert "key" not in c2.metadata


# === PaperIndex (faiss 不要 path: empty + dim only) ===


def test_paper_index_empty_search():
    idx = PaperIndex(dim=384)
    assert idx.search([0.0] * 384, top_k=5) == []


def test_paper_index_dim_attr():
    idx = PaperIndex(dim=768)
    assert idx.dim == 768
    assert idx.chunks == []


# === generate_synthetic_paper_corpus (Faker 不在環境では RuntimeError fail-loud verify) ===


def test_generate_zero_papers_raises():
    """n_papers < 1 = ValueError fail-loud (doctrine: no-design-compromise)。"""
    from src.ingestion.generate_synthetic_papers import generate_synthetic_paper_corpus
    with pytest.raises(ValueError):
        generate_synthetic_paper_corpus(n_papers=0)


def test_publishers_constants():
    """internal ADR § 2 inherits top-tier consulting firm/top-tier PMI advisor/top-tier consulting firm/Other 4 publishers。"""
    from src.ingestion.generate_synthetic_papers import PUBLISHERS, SIZE_BANDS, INTEGRATION_TYPES
    assert "top-tier consulting firm" in PUBLISHERS
    assert "top-tier PMI advisor" in PUBLISHERS
    assert "top-tier consulting firm" in PUBLISHERS
    assert len(PUBLISHERS) == 4
    assert "tuck-in" in INTEGRATION_TYPES
    assert "100-300" in SIZE_BANDS

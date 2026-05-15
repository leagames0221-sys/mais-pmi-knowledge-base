"""ingestion module。

Week 3 active:
- parse_paper_docling.py: docling PDF parse → markdown sections (PoC = 合成 markdown 直接 input path、 移植 = 実 PDF + license confirm)
- chunk_embed.py: chunk_paper (1000 char + overlap 200、 段落単位) + embed_chunks (sentence-transformers + faiss-cpu IndexFlatIP)
- generate_synthetic_papers.py: 50 件 合成 paper corpus (Faker + top-tier consulting firm/top-tier PMI advisor/top-tier consulting firm 業界 template + Day-N retrospective + 5 dim band)

module boundaries 越境境界線 3 段階 順守:
- 段階 1 OS-primitives: docling (MIT) + sentence-transformers + faiss-cpu (MIT) + Faker (literal use OK)
- 段階 2 business logic: chunking + PII 二重防御 + 合成 corpus template + REF id assignment (literal 自作)
"""
from .chunk_embed import PaperIndex, chunk_paper, embed_chunks
from .generate_synthetic_papers import generate_synthetic_paper_corpus
from .parse_paper_docling import parse_paper_docling, parse_markdown_sections

__all__ = [
    "PaperIndex",
    "chunk_paper",
    "embed_chunks",
    "generate_synthetic_paper_corpus",
    "parse_paper_docling",
    "parse_markdown_sections",
]

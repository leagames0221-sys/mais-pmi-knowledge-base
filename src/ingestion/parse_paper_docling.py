"""PDF paper parse via docling

module boundaries 段階 1: docling (MIT、 IBM Research 公式 OSS) literal use OK、 thin wrapper のみ。
PoC = 合成 markdown 直接 input path 利用、 移植段階 = 実 PDF + license individual confirm 必須 (doctrine: client-no-recovery)。
"""
from __future__ import annotations

import sys
from typing import Any

from ..retrieval.graphrag_native import VAULT_FIELDS, check_pii_boundary

# Windows cp932 console UTF-8 reconfigure (T3 学び doctrine: analogical-recall inherit)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8") # type: ignore[attr-defined]
    except Exception:
        pass


def parse_paper_docling(pdf_path: str) -> str:
    """PDF → markdown thin wrapper (docling.document_converter literal 利用、 段階 1 OS-primitives)。

    Args:
        pdf_path: PDF file path (PoC = 合成 PDF 不在のため markdown 直接 input path に literal route、
                  移植段階 = 実 PDF + license individual confirm)
    Returns:
        parsed markdown string
    Raises:
        RuntimeError: docling not installed
        ValueError: PII boundary violation in parsed content (vault field detect 時)
    """
    try:
        from docling.document_converter import DocumentConverter # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "docling not installed。 "
            "Run: pip install 'docling>=2.0,<3.0'"
        ) from exc

    converter = DocumentConverter()
    result = converter.convert(pdf_path)
    markdown = result.document.export_to_markdown()

    # PII boundary 二重防御 (parsed content の vault field detect、 paper_signatory + acknowledgments_raw 等)
    clean, detected = check_pii_boundary(markdown)
    if not clean:
        raise ValueError(
            f"PII boundary violation in parsed paper: vault fields detected: {detected}。 "
            "raw value embedding 禁止"
        )
    return markdown


def parse_markdown_sections(markdown: str) -> list[dict[str, Any]]:
    """markdown → section list (PoC = 段落 split、 移植 = docling section heading 構造化)。

    Returns:
        list[{"heading": str, "content": str, "level": int}]
    """
    if not markdown:
        return []
    sections: list[dict[str, Any]] = []
    current_heading = "(intro)"
    current_level = 0
    current_buffer: list[str] = []

    def flush() -> None:
        nonlocal current_buffer
        if current_buffer:
            sections.append(
                {
                    "heading": current_heading,
                    "content": "\n".join(current_buffer).strip(),
                    "level": current_level,
                }
            )
            current_buffer = []

    for line in markdown.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            heading_text = stripped.lstrip("#").strip()
            flush()
            current_heading = heading_text or "(unnamed)"
            current_level = level
        else:
            current_buffer.append(line)
    flush()
    # filter empty content sections
    return [s for s in sections if s["content"]]


__all__ = ["parse_paper_docling", "parse_markdown_sections"]

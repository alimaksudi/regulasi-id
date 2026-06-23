"""PDF text extraction via PyMuPDF. No OCR for born-digital OJK PDFs."""

from __future__ import annotations


def extract_text(path: str) -> tuple[str, int]:
    """Return (text_with_page_markers, page_count)."""
    import pymupdf  # fitz

    doc = pymupdf.open(path)
    try:
        parts: list[str] = []
        for i, page in enumerate(doc):
            parts.append(f"[[page {i + 1}]]")
            parts.append(page.get_text())
        return "\n".join(parts), doc.page_count
    finally:
        doc.close()

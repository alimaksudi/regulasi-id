"""Classify a PDF by how much text PyMuPDF pulled out of it.

OJK post-2013 PDFs are born-digital, so most score born_digital and skip OCR.
"""

from __future__ import annotations

BORN_DIGITAL_MIN_CPP = 200  # chars per page
SCANNED_CLEAN_MIN_CPP = 20


def classify(text: str, page_count: int) -> str:
    chars_per_page = len(text.strip()) / max(page_count, 1)
    if chars_per_page >= BORN_DIGITAL_MIN_CPP:
        return "born_digital"
    if chars_per_page >= SCANNED_CLEAN_MIN_CPP:
        return "scanned_clean"
    return "image_only"

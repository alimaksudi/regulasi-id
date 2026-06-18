"""Score extraction quality 0..1. Jobs below QUALITY_FLAG_THRESHOLD are flagged."""

from __future__ import annotations

from typing import Protocol


class _Node(Protocol):
    node_type: str
    content_text: str | None


def score_extraction(nodes: list[_Node], pdf_page_count: int) -> float:
    if not nodes:
        return 0.0

    pasal_count = sum(1 for n in nodes if n.node_type == "pasal")
    content_chars = sum(len(n.content_text or "") for n in nodes)
    chars_per_page = content_chars / max(pdf_page_count, 1)

    has_bab = any(n.node_type == "bab" for n in nodes)
    has_ayat = any(n.node_type == "ayat" for n in nodes)

    pasal_score = min(1.0, pasal_count / 10)         # 10+ pasals = full
    density_score = min(1.0, chars_per_page / 200)   # 200 chars/page = full
    structure_score = (0.5 if has_bab else 0) + (0.5 if has_ayat else 0)

    return round(pasal_score * 0.4 + density_score * 0.4 + structure_score * 0.2, 3)

"""Upsert the OJK FAQ (one per work, where available)."""

from __future__ import annotations

from ..crawler.db import get_client


def load_faq(work_id: int, text: str, pdf_url: str | None = None) -> None:
    get_client().table("faqs").upsert(
        {"work_id": work_id, "content_text": text, "source_pdf_url": pdf_url},
        on_conflict="work_id",
    ).execute()

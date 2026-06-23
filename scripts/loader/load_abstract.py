"""Upsert the OJK abstract (one per work)."""

from __future__ import annotations

from ..crawler.db import get_client


def load_abstract(work_id: int, text: str, pdf_url: str | None = None) -> None:
    get_client().table("abstracts").upsert(
        {"work_id": work_id, "content_text": text, "source_pdf_url": pdf_url},
        on_conflict="work_id",
    ).execute()

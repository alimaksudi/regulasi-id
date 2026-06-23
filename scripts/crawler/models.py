"""Pydantic models passed between crawler, parser, and loader."""

from __future__ import annotations

from pydantic import BaseModel


class ParsedNode(BaseModel):
    node_type: str  # bab | bagian | paragraf | pasal | ayat | preamble | ...
    number: str | None = None
    heading: str | None = None
    content_text: str | None = None
    sort_order: int = 0
    depth: int = 0  # 0 = top-level; used for breadth-first insertion
    parent_index: int | None = None  # index into the flat node list


class ParsedWork(BaseModel):
    title_id: str
    number: str
    year: int
    regulation_type: str
    sector: str | None = None
    status: str = "berlaku"
    tentang: str | None = None
    frbr_uri: str | None = None
    source_url: str | None = None
    source_pdf_url: str | None = None
    extraction_quality: float | None = None
    nodes: list[ParsedNode] = []


class CrawlJob(BaseModel):
    # sector_code / regulation_type are optional: claim_jobs() returns a subset.
    id: int | None = None
    sector_code: str | None = None
    regulation_type: str | None = None
    source_url: str = ""
    detail_uuid: str | None = None
    pdf_uuid: str | None = None
    abstract_uuid: str | None = None
    faq_uuid: str | None = None
    status: str = "pending"
    retry_count: int = 0
    work_id: int | None = None
    listing_metadata: dict | None = None  # title/number/year/status from the listing

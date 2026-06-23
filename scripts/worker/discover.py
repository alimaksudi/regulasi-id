"""Discover regulations from the JDIH JSON endpoint and seed crawl_jobs.

The listing page is a client-side DataTable; its rows come from ListDataPeraturan
as JSON. Each row's first cell is an <a> linking to the detail page, whose URL holds
the detail UUID. The PDF download UUID is read later, from the detail page.
"""

from __future__ import annotations

import asyncio
import re

from ..crawler import config, source_registry, state

DETAIL_HREF_RE = re.compile(
    r"/Detail/([0-9a-fA-F-]{36})/(\d+)/(\d+)", re.IGNORECASE
)
TAG_RE = re.compile(r"<[^>]+>")
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")

# JDIH status label -> works.status value
STATUS_MAP = {
    "berlaku": "berlaku",
    "tidak berlaku": "tidak_berlaku",
    "dicabut": "dicabut",
    "diubah": "diubah",
}


def row_metadata(row: list) -> dict:
    """Clean title/number/year/status/tentang from a listing row."""
    title = re.sub(r"\s+", " ", TAG_RE.sub("", row[0] or "")).strip()
    year_m = YEAR_RE.search(title)
    # "Tentang" appears in mixed case in real titles; split case-insensitively.
    tentang_m = re.search(r"\btentang\b", title, re.IGNORECASE)
    tentang = title[tentang_m.end():].strip() if tentang_m else None
    status_raw = (row[7] or "").strip().lower() if len(row) > 7 else ""
    return {
        "title": title,
        "number": str(row[1]).strip() if len(row) > 1 and row[1] else None,
        "year": int(year_m.group(1)) if year_m else None,
        "status": STATUS_MAP.get(status_raw, "berlaku"),
        "tentang": tentang,
    }


def row_to_job(row: list, sector: str, reg_type: str) -> dict | None:
    """Turn one aaData row into a crawl_jobs record, or None if it has no detail link."""
    if not row:
        return None
    anchor = row[0] or ""
    m = DETAIL_HREF_RE.search(anchor)
    if not m:
        return None
    uuid, sektor, jenis = m.group(1), m.group(2), m.group(3)
    return {
        "sector_code": sector,
        "regulation_type": reg_type,
        "source_url": source_registry.detail_url(uuid, sektor, jenis),
        "detail_uuid": uuid,
        "status": "pending",
        "listing_metadata": row_metadata(row),
    }


async def discover(
    sectors: list[str],
    types: list[str] | None = None,
    dry_run: bool = False,
) -> int:
    import httpx

    types = types or source_registry.DEFAULT_TYPES
    seeded = 0

    async with httpx.AsyncClient(
        headers={**config.HEADERS, "X-Requested-With": "XMLHttpRequest"},
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        verify=config.VERIFY_SSL,
        follow_redirects=True,
    ) as client:
        for sector in sectors:
            for reg_type in types:
                resp = await client.get(source_registry.data_url(sector, reg_type))
                resp.raise_for_status()
                rows = resp.json().get("aaData") or []
                for row in rows:
                    job = row_to_job(row, sector, reg_type)
                    if not job:
                        continue
                    if not dry_run:
                        state.upsert_job(job)
                    seeded += 1
                await asyncio.sleep(config.REQUEST_DELAY_SECONDS)

    return seeded

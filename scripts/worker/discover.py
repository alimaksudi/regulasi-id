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

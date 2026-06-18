"""Crawl JDIH listing pages and seed crawl_jobs with detail-page UUIDs."""

from __future__ import annotations

import asyncio
import re

from ..crawler import config, source_registry, state

# Detail links look like /web/ViewPeraturan/Detail/{uuid}/00/00
DETAIL_RE = re.compile(
    r"/web/ViewPeraturan/Detail/([0-9a-fA-F-]{36})", re.IGNORECASE
)


async def discover(
    sectors: list[str],
    types: list[str] | None = None,
    dry_run: bool = False,
) -> int:
    import httpx

    types = types or source_registry.DEFAULT_TYPES
    seeded = 0

    async with httpx.AsyncClient(
        headers=config.HEADERS,
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        verify=config.VERIFY_SSL,
        follow_redirects=True,
    ) as client:
        for sector in sectors:
            for reg_type in types:
                url = source_registry.listing_url(sector, reg_type)
                resp = await client.get(url)
                resp.raise_for_status()
                uuids = set(DETAIL_RE.findall(resp.text))
                for uuid in uuids:
                    if dry_run:
                        seeded += 1
                        continue
                    state.upsert_job(
                        {
                            "sector_code": sector,
                            "regulation_type": reg_type,
                            "source_url": source_registry.detail_url(uuid),
                            "detail_uuid": uuid,
                            "status": "pending",
                        }
                    )
                    seeded += 1
                await asyncio.sleep(config.REQUEST_DELAY_SECONDS)

    return seeded

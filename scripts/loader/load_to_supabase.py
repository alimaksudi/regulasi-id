"""Upsert a parsed work and its nodes. Nodes are inserted breadth-first so a
parent row always exists before its children reference it."""

from __future__ import annotations

from functools import lru_cache

from ..crawler.db import get_client
from ..crawler.models import ParsedNode, ParsedWork


@lru_cache(maxsize=64)
def _lookup_id(table: str, code: str) -> int | None:
    res = get_client().table(table).select("id").eq("code", code).limit(1).execute()
    rows = res.data or []
    return rows[0]["id"] if rows else None


def load_work(work: ParsedWork) -> int:
    sb = get_client()
    frbr = work.frbr_uri or (
        f"/akn/id/act/{work.regulation_type.lower()}/{work.year}/{work.number}"
    )
    row = {
        "sector_id": _lookup_id("sectors", work.sector) if work.sector else None,
        "regulation_type_id": _lookup_id("regulation_types", work.regulation_type),
        "frbr_uri": frbr,
        "title_id": work.title_id,
        "number": work.number,
        "year": work.year,
        "status": work.status,
        "tentang": work.tentang,
        "source_url": work.source_url,
        "source_pdf_url": work.source_pdf_url,
        "extraction_quality": work.extraction_quality,
    }
    res = sb.table("works").upsert(row, on_conflict="frbr_uri").execute()
    return res.data[0]["id"]


def load_nodes_by_level(work_id: int, nodes: list[ParsedNode]) -> dict[int, int]:
    """Insert nodes depth by depth. Returns list-index -> database-id."""
    sb = get_client()
    # Replace any prior nodes for this work (re-extraction is idempotent).
    sb.table("document_nodes").delete().eq("work_id", work_id).execute()

    index_to_id: dict[int, int] = {}
    max_depth = max((n.depth for n in nodes), default=-1)
    for depth in range(max_depth + 1):
        batch = [i for i, n in enumerate(nodes) if n.depth == depth]
        if not batch:
            continue
        rows = [
            {
                "work_id": work_id,
                "parent_id": (
                    index_to_id.get(nodes[i].parent_index)
                    if nodes[i].parent_index is not None
                    else None
                ),
                "node_type": nodes[i].node_type,
                "number": nodes[i].number,
                "heading": nodes[i].heading,
                "content_text": nodes[i].content_text,
                "sort_order": nodes[i].sort_order,
            }
            for i in batch
        ]
        res = sb.table("document_nodes").insert(rows).execute()
        for i, returned in zip(batch, res.data or []):
            index_to_id[i] = returned["id"]
    return index_to_id

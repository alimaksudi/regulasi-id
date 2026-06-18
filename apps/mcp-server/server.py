"""regulasi-id MCP server.

Gives Claude grounded access to OJK regulations: exact article text with source
citations, status checks, and curated compliance checklists. Hybrid search via the
search_regulations() RPC. Cache and rate limiting via Upstash Redis (cross-instance).

Clients (Supabase, Redis, rate limiters) are created lazily so the module imports
without environment or network access, which keeps it testable.
"""

from __future__ import annotations

import base64
import json
import os
import re
from functools import lru_cache
from typing import Any

import structlog
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

log = structlog.get_logger()

mcp = FastMCP("regulasi-id")

DISCLAIMER = (
    "Informasi ini bukan nasihat hukum. Selalu verifikasi dengan sumber resmi OJK. "
    "regulasi-id mencakup sebagian regulasi OJK."
)

STATUS_EXPLANATION = {
    "berlaku": "Peraturan ini masih berlaku.",
    "diubah": "Peraturan ini telah diubah sebagian; sebagian ketentuan masih berlaku.",
    "dicabut": "Peraturan ini telah dicabut dan tidak berlaku lagi.",
    "tidak_berlaku": "Peraturan ini sudah tidak berlaku.",
}

# How an incoming relationship reads from the target regulation's point of view.
INCOMING_LABEL = {
    "mengubah": "Diubah oleh",
    "mencabut": "Dicabut oleh",
    "mencabut_sebagian": "Dicabut sebagian oleh",
    "melaksanakan": "Dilaksanakan oleh",
    "dasar_hukum": "Menjadi dasar hukum bagi",
    "terkait": "Terkait dengan",
}


# --- lazy clients -----------------------------------------------------------

@lru_cache(maxsize=1)
def get_supabase():
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    anon = os.environ["SUPABASE_ANON_KEY"]
    service = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if service and anon == service:
        raise RuntimeError(
            "Refusing to start: SUPABASE_ANON_KEY equals the service role key. "
            "The MCP server must use the anon key only."
        )
    return create_client(url, anon)


@lru_cache(maxsize=1)
def get_redis():
    from upstash_redis import Redis

    return Redis(
        url=os.environ["UPSTASH_REDIS_REST_URL"],
        token=os.environ["UPSTASH_REDIS_REST_TOKEN"],
    )


@lru_cache(maxsize=None)
def get_ratelimit(prefix: str, max_requests: int, window: str):
    from upstash_ratelimit import Ratelimit, SlidingWindow

    return Ratelimit(
        redis=get_redis(),
        limiter=SlidingWindow(max_requests=max_requests, window=_window_seconds(window)),
        prefix=f"rl:{prefix}",
    )


def _window_seconds(window: str) -> int:
    unit = window[-1]
    value = int(window[:-1])
    return value * {"s": 1, "m": 60, "h": 3600}[unit]


# --- cross-cutting helpers --------------------------------------------------

def _client_ip() -> str:
    try:
        from fastmcp.server.dependencies import get_http_request

        req = get_http_request()
        fwd = req.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        return req.client.host if req.client else "unknown"
    except Exception:
        return "global"


def _enforce_limit(prefix: str, max_requests: int, window: str) -> None:
    """Raise ToolError when over the limit. Fail open if the limiter backend is down."""
    try:
        rl = get_ratelimit(prefix, max_requests, window)
        result = rl.limit(f"{prefix}:{_client_ip()}")
        allowed = getattr(result, "allowed", True)
    except ToolError:
        raise
    except Exception as exc:
        log.warning("ratelimit_unavailable", prefix=prefix, error=str(exc))
        return
    if not allowed:
        raise ToolError("Terlalu banyak permintaan. Coba lagi dalam beberapa saat.")


def _cache_get(key: str) -> Any | None:
    try:
        raw = get_redis().get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        log.warning("cache_get_failed", key=key, error=str(exc))
        return None


def _cache_set(key: str, value: Any, ttl: int) -> None:
    try:
        get_redis().set(key, json.dumps(value), ex=ttl)
    except Exception as exc:
        log.warning("cache_set_failed", key=key, error=str(exc))


def _type_from_frbr(frbr: str | None) -> str | None:
    # /akn/id/act/pojk/2022/10 -> POJK
    if not frbr:
        return None
    parts = frbr.strip("/").split("/")
    return parts[3].upper() if len(parts) >= 6 else None


def _encode_cursor(year: int, node_id: int) -> str:
    return base64.b64encode(json.dumps({"year": year, "id": node_id}).encode()).decode()


def _decode_cursor(cursor: str) -> dict | None:
    try:
        obj = json.loads(base64.b64decode(cursor).decode())
        if isinstance(obj.get("year"), int) and isinstance(obj.get("id"), int):
            return obj
        return None
    except Exception:
        return None


def _pasal_label(node_type: str | None, node_number: str | None) -> str | None:
    if not node_type or not node_number:
        return None
    if node_type == "pasal":
        return f"Pasal {node_number}"
    return f"{node_type} {node_number}"


def _work_lookup(sb, regulation_type: str, number: str, year: int):
    """Single work row by type code + number + year, or None."""
    res = (
        sb.table("works")
        .select(
            "id, frbr_uri, title_id, number, year, status, date_enacted, "
            "regulation_types!inner(code), sectors(code)"
        )
        .eq("regulation_types.code", regulation_type.upper())
        .eq("number", str(number))
        .eq("year", year)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


# --- tools ------------------------------------------------------------------

@mcp.tool
def search_regulations(
    query: str,
    sector: str | None = None,
    regulation_type: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    status: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Hybrid search over OJK regulations (FTS + RRF). Indonesian query preferred,
    e.g. "kredit pemilikan rumah" not "home loan". Entry point for legal questions."""
    _enforce_limit("search", 30, "60s")
    try:
        limit = max(1, min(int(limit), 50))
        sb = get_supabase()
        res = sb.rpc(
            "search_regulations",
            {
                "p_query": query,
                "p_sector": sector,
                "p_type": regulation_type.upper() if regulation_type else None,
                "p_year_from": year_from,
                "p_year_to": year_to,
                "p_status": status,
                "p_limit": limit,
                # MCP runs without an embedding provider: FTS layers only.
                "p_query_embedding": None,
            },
        ).execute()
        rows = res.data or []

        # The RPC does not return sector; resolve it for the matched works.
        work_ids = list({r["work_id"] for r in rows})
        sectors: dict[int, str | None] = {}
        if work_ids:
            sres = sb.table("works").select("id, sectors(code)").in_("id", work_ids).execute()
            for w in sres.data or []:
                sec = w.get("sectors")
                sectors[w["id"]] = sec.get("code") if isinstance(sec, dict) else None

        return [
            {
                "title": r.get("title_id"),
                "frbr_uri": r.get("frbr_uri"),
                "regulation_type": _type_from_frbr(r.get("frbr_uri")),
                "sector": sectors.get(r["work_id"]),
                "year": r.get("year"),
                "pasal": _pasal_label(r.get("node_type"), r.get("node_number")),
                "snippet": r.get("snippet"),
                "status": r.get("status"),
                "relevance_score": r.get("score"),
                "semantic_used": False,
                "disclaimer": DISCLAIMER,
            }
            for r in rows
        ]
    except ToolError:
        raise
    except Exception as exc:
        _capture(exc)
        return [{"error": "Gagal melakukan pencarian. Coba lagi.", "disclaimer": DISCLAIMER}]


@mcp.tool
def get_article(regulation_type: str, number: str, year: int, article_number: str) -> dict:
    """Exact text of one article (Pasal) for citation. Verify status with
    get_regulation_status before citing. number and article_number are strings."""
    _enforce_limit("article", 60, "60s")
    cache_key = f"article:{regulation_type.upper()}:{number}:{year}:{article_number}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        sb = get_supabase()
        work = _work_lookup(sb, regulation_type, number, year)
        if not work:
            return {"error": "Regulasi tidak ditemukan.", "disclaimer": DISCLAIMER}

        pres = (
            sb.table("document_nodes")
            .select("id, number, content_text, sort_order")
            .eq("work_id", work["id"])
            .eq("node_type", "pasal")
            .eq("number", str(article_number))
            .limit(1)
            .execute()
        )
        pasal_rows = pres.data or []
        if not pasal_rows:
            return {"error": f"Pasal {article_number} tidak ditemukan.", "disclaimer": DISCLAIMER}
        pasal = pasal_rows[0]

        ayat_res = (
            sb.table("document_nodes")
            .select("number, content_text, sort_order")
            .eq("parent_id", pasal["id"])
            .eq("node_type", "ayat")
            .order("sort_order")
            .execute()
        )
        ayat = [
            {"number": a.get("number"), "text": a.get("content_text")}
            for a in (ayat_res.data or [])
        ]

        chapter = _nearest_chapter(sb, work["id"], pasal.get("sort_order"))
        cross_refs = _cross_references(pasal.get("content_text"), str(article_number))

        result = {
            "title": work.get("title_id"),
            "frbr_uri": work.get("frbr_uri"),
            "article_number": pasal.get("number"),
            "chapter": chapter,
            "content_text": pasal.get("content_text"),
            "ayat": ayat,
            "cross_references": cross_refs,
            "status": work.get("status"),
            "disclaimer": DISCLAIMER,
        }
        _cache_set(cache_key, result, 3600)
        return result
    except ToolError:
        raise
    except Exception as exc:
        _capture(exc)
        return {"error": "Gagal mengambil pasal. Coba lagi.", "disclaimer": DISCLAIMER}


@mcp.tool
def get_regulation_status(regulation_type: str, number: str, year: int) -> dict:
    """Whether a regulation is still in force, and what amended or revoked it.
    Always check before citing; a revoked regulation silently misleads."""
    _enforce_limit("status", 60, "60s")
    cache_key = f"status:{regulation_type.upper()}:{number}:{year}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        sb = get_supabase()
        work = _work_lookup(sb, regulation_type, number, year)
        if not work:
            return {"error": "Regulasi tidak ditemukan.", "disclaimer": DISCLAIMER}

        rel_res = (
            sb.table("work_relationships")
            .select(
                "relationship_types!inner(code, name_id), "
                "works!work_relationships_from_work_id_fkey(title_id, number, year, "
                "regulation_types!inner(code))"
            )
            .eq("to_work_id", work["id"])
            .execute()
        )
        amendments = []
        for r in rel_res.data or []:
            rt = r.get("relationship_types") or {}
            src = r.get("works") or {}
            src_type = (src.get("regulation_types") or {}).get("code")
            short = (
                f"{src_type} {src.get('number')}/{src.get('year')}"
                if src_type
                else None
            )
            amendments.append(
                {
                    "relationship": INCOMING_LABEL.get(rt.get("code"), rt.get("name_id")),
                    "regulation": short,
                    "full_title": src.get("title_id"),
                }
            )

        result = {
            "title": work.get("title_id"),
            "frbr_uri": work.get("frbr_uri"),
            "status": work.get("status"),
            "status_explanation": STATUS_EXPLANATION.get(work.get("status"), ""),
            "date_enacted": work.get("date_enacted"),
            "amendments": amendments,
            "disclaimer": DISCLAIMER,
        }
        _cache_set(cache_key, result, 3600)
        return result
    except ToolError:
        raise
    except Exception as exc:
        _capture(exc)
        return {"error": "Gagal memeriksa status. Coba lagi.", "disclaimer": DISCLAIMER}


@mcp.tool
def get_compliance_checklist(sector: str, business_type: str | None = None) -> dict:
    """Curated regulations that apply to a sector and business type, by priority.
    The differentiating feature: answers "what applies to my business"."""
    _enforce_limit("compliance", 30, "60s")
    try:
        sb = get_supabase()
        query = (
            sb.table("compliance_mappings")
            .select(
                "priority, notes, business_type, sectors!inner(code), "
                "works!inner(frbr_uri, title_id, number, year, status, "
                "regulation_types!inner(code))"
            )
            .eq("sectors.code", sector)
        )
        if business_type:
            query = query.or_(f"business_type.eq.{business_type},business_type.is.null")
        res = query.execute()

        order = {"required": 0, "recommended": 1, "conditional": 2}
        rows = sorted(res.data or [], key=lambda m: order.get(m.get("priority"), 9))
        required = [
            {
                "frbr_uri": (m.get("works") or {}).get("frbr_uri"),
                "title": (m.get("works") or {}).get("title_id"),
                "regulation_type": ((m.get("works") or {}).get("regulation_types") or {}).get("code"),
                "number": (m.get("works") or {}).get("number"),
                "year": (m.get("works") or {}).get("year"),
                "status": (m.get("works") or {}).get("status"),
                "priority": m.get("priority"),
                "notes": m.get("notes"),
            }
            for m in rows
        ]
        return {
            "sector": sector,
            "business_type": business_type,
            "required_regulations": required,
            "disclaimer": DISCLAIMER,
        }
    except ToolError:
        raise
    except Exception as exc:
        _capture(exc)
        return {"error": "Gagal mengambil checklist. Coba lagi.", "disclaimer": DISCLAIMER}


@mcp.tool
def list_regulations(
    sector: str | None = None,
    regulation_type: str | None = None,
    year: int | None = None,
    status: str | None = None,
    cursor: str | None = None,
    per_page: int = 20,
) -> dict:
    """Browse and discover regulations (cursor-paginated). For specific legal
    questions use search_regulations instead."""
    _enforce_limit("list", 30, "60s")
    try:
        per_page = max(1, min(int(per_page), 100))
        sb = get_supabase()

        def apply(q):
            if sector:
                q = q.eq("sectors.code", sector)
            if regulation_type:
                q = q.eq("regulation_types.code", regulation_type.upper())
            if year:
                q = q.eq("year", year)
            if status:
                q = q.eq("status", status)
            return q

        sector_embed = "sectors!inner(code)" if sector else "sectors(code)"
        select = (
            f"id, frbr_uri, title_id, number, year, status, "
            f"regulation_types!inner(code), {sector_embed}"
        )

        count_res = apply(
            sb.table("works").select(select, count="exact", head=True)
        ).execute()
        total = count_res.count or 0

        q = apply(
            sb.table("works")
            .select(select)
            .order("year", desc=True)
            .order("id", desc=True)
            .limit(per_page + 1)
        )
        if cursor:
            cur = _decode_cursor(cursor)
            if cur:
                q = q.or_(f"year.lt.{cur['year']},and(year.eq.{cur['year']},id.lt.{cur['id']})")
        rows = (q.execute().data) or []

        next_cursor = None
        if len(rows) > per_page:
            last = rows[per_page - 1]
            next_cursor = _encode_cursor(last["year"], last["id"])
            rows = rows[:per_page]

        regulations = [
            {
                "frbr_uri": r.get("frbr_uri"),
                "title": r.get("title_id"),
                "regulation_type": (r.get("regulation_types") or {}).get("code"),
                "sector": (r.get("sectors") or {}).get("code") if r.get("sectors") else None,
                "number": r.get("number"),
                "year": r.get("year"),
                "status": r.get("status"),
            }
            for r in rows
        ]
        return {
            "total": total,
            "next_cursor": next_cursor,
            "regulations": regulations,
            "disclaimer": DISCLAIMER,
        }
    except ToolError:
        raise
    except Exception as exc:
        _capture(exc)
        return {"error": "Gagal mengambil daftar. Coba lagi.", "disclaimer": DISCLAIMER}


@mcp.tool
def ping() -> str:
    """Health check. Reports regulation count and embedding coverage."""
    cached = _cache_get("ping:stats")
    if cached is not None:
        return cached
    try:
        sb = get_supabase()
        works = sb.table("works").select("id", count="exact", head=True).execute()
        nodes = sb.table("document_nodes").select("id", count="exact", head=True).execute()
        embedded = (
            sb.table("document_nodes")
            .select("id", count="exact", head=True)
            .not_.is_("embedding", "null")
            .execute()
        )
        total_nodes = nodes.count or 0
        coverage = round((embedded.count or 0) / total_nodes * 100) if total_nodes else 0
        msg = (
            f"regulasi-id MCP v1.0. Database: {works.count or 0} regulations, "
            f"{coverage}% embedding coverage."
        )
        _cache_set("ping:stats", msg, 300)
        return msg
    except Exception as exc:
        _capture(exc)
        return "regulasi-id MCP v1.0. Status unavailable."


def _nearest_chapter(sb, work_id: int, sort_order: int | None) -> str | None:
    """Closest preceding BAB heading for a node, as 'BAB V - KELEMBAGAAN'."""
    if sort_order is None:
        return None
    res = (
        sb.table("document_nodes")
        .select("number, heading, sort_order")
        .eq("work_id", work_id)
        .eq("node_type", "bab")
        .lte("sort_order", sort_order)
        .order("sort_order", desc=True)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return None
    bab = rows[0]
    label = f"BAB {bab.get('number')}" if bab.get("number") else "BAB"
    return f"{label} - {bab['heading']}" if bab.get("heading") else label


def _cross_references(content: str | None, self_number: str) -> list[dict]:
    """Pasal references inside the article text, excluding self-references."""
    if not content:
        return []
    seen: set[str] = set()
    refs = []
    for m in re.finditer(r"Pasal\s+(\d+[A-Za-z]?)", content):
        num = m.group(1)
        if num == self_number or num in seen:
            continue
        seen.add(num)
        start = max(0, m.start() - 30)
        refs.append({"pasal": num, "context": content[start:m.end()].strip()})
    return refs


def _capture(exc: Exception) -> None:
    log.error("tool_error", error=str(exc))
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:
        pass


def _init_sentry() -> None:
    dsn = os.environ.get("SENTRY_DSN")
    if dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=dsn, traces_sample_rate=0.1)


if __name__ == "__main__":
    _init_sentry()
    # Validate the anon/service-role guard at startup, not at first request.
    get_supabase()
    port = int(os.getenv("PORT") or "8000")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)

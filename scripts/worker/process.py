"""Async parallel batch processor: detail page -> PDFs -> parse -> score -> load."""

from __future__ import annotations

import asyncio
import re
import tempfile

from ..crawler import config, source_registry, state
from ..crawler import retry as retry_mod
from ..crawler.models import CrawlJob, ParsedWork
from ..loader.load_abstract import load_abstract
from ..loader.load_faq import load_faq
from ..loader.load_to_supabase import load_nodes_by_level, load_work
from ..parser.extract_pymupdf import extract_text
from ..parser.parse_structure import parse_structure
from ..parser.quality_scorer import score_extraction

# Download links: /Web/ViewPeraturan/DownloadDokumen/{uuid}. On the real JDIH site
# the link text is usually empty, so labels cannot be relied on for classification.
DOWNLOAD_RE = re.compile(r"DownloadDokumen/([0-9a-fA-F-]{36})", re.IGNORECASE)
DOWNLOAD_LABELED_RE = re.compile(
    r'DownloadDokumen/([0-9a-fA-F-]{36})["\'][^>]*>\s*([^<]*)', re.IGNORECASE
)
TITLE_RE = re.compile(r"(?:Tentang|tentang)\s*[:\-]?\s*(.+)")
NUMBER_RE = re.compile(r"Nomor\s+([0-9A-Za-z./-]+)", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def extract_download_uuids(html: str) -> dict:
    """Return all download UUIDs in page order plus any that carry an explicit label.

    A detail page can hold several documents (regulation, abstract, FAQ) and the link
    text is usually empty, so order/labels alone can't tell which is the regulation.
    The main PDF is chosen later by which one actually parses as a regulation.
    """
    ordered: list[str] = []
    for uuid in DOWNLOAD_RE.findall(html):
        if uuid not in ordered:
            ordered.append(uuid)

    labeled: dict[str, str] = {}
    for uuid, label in DOWNLOAD_LABELED_RE.findall(html):
        lbl = label.strip().lower()
        if "abstrak" in lbl:
            labeled["abstrak"] = uuid
        elif "faq" in lbl:
            labeled["faq"] = uuid
        elif "peraturan" in lbl:
            labeled["peraturan"] = uuid

    return {"ordered": ordered, "labeled": labeled}


def select_main_pdf(candidates: list[tuple[str, int]]) -> str | None:
    """Pick the document with the most Pasal; that is the regulation itself,
    not its abstract or FAQ. candidates is (uuid, pasal_count)."""
    return max(candidates, key=lambda c: c[1])[0] if candidates else None


def extract_work_meta(html: str, fallback_type: str) -> dict:
    title_m = TITLE_RE.search(html)
    number_m = NUMBER_RE.search(html)
    year_m = YEAR_RE.search(html)
    return {
        "title_id": title_m.group(1).strip() if title_m else "(judul tidak diketahui)",
        "number": number_m.group(1) if number_m else "0",
        "year": int(year_m.group(0)) if year_m else 0,
        "regulation_type": fallback_type,
    }


async def process_batch(jobs: list[CrawlJob], concurrency: int = 5) -> None:
    semaphore = asyncio.Semaphore(concurrency)

    async def process_one(job: CrawlJob) -> None:
        async with semaphore:
            try:
                await download_and_parse(job)
            except Exception as exc:  # noqa: BLE001
                handle_failure(job, exc)

    await asyncio.gather(*[process_one(j) for j in jobs])


async def download_and_parse(job: CrawlJob) -> None:
    import httpx

    async with httpx.AsyncClient(
        headers=config.HEADERS,
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        verify=config.VERIFY_SSL,
        follow_redirects=True,
    ) as client:
        detail_html = (await client.get(job.source_url)).text
        docs = extract_download_uuids(detail_html)
        labeled = docs["labeled"]

        # Candidate main-PDF UUIDs: an explicit job/label wins, else try every
        # download on the page and let the parser decide which is the regulation.
        if job.pdf_uuid:
            candidates = [job.pdf_uuid]
        elif labeled.get("peraturan"):
            candidates = [labeled["peraturan"]]
        else:
            candidates = docs["ordered"]
        if not candidates:
            raise ValueError("No PDF download UUID on detail page")

        abstract_uuid = job.abstract_uuid or labeled.get("abstrak")
        faq_uuid = job.faq_uuid or labeled.get("faq")

        candidate_blobs = await asyncio.gather(*[_download(client, u) for u in candidates])
        abstract_pdf, faq_pdf = await asyncio.gather(
            _download(client, abstract_uuid),
            _download(client, faq_uuid),
        )

    # Parse each candidate; the regulation is the one with the most Pasal.
    parsed = []
    for uuid, blob in zip(candidates, candidate_blobs):
        c_text, c_pages = _extract(blob)
        c_nodes = parse_structure(c_text)
        c_pasal = sum(1 for n in c_nodes if n.node_type == "pasal")
        parsed.append((uuid, c_text, c_pages, c_nodes, c_pasal))

    pdf_uuid = select_main_pdf([(p[0], p[4]) for p in parsed])
    text, page_count, nodes = next((p[1], p[2], p[3]) for p in parsed if p[0] == pdf_uuid)
    quality = score_extraction(nodes, page_count)

    if quality < config.QUALITY_FLAG_THRESHOLD:
        state.update_status(job.id, "flagged")
        return

    # Prefer the clean listing metadata captured at discovery; fall back to the
    # detail page only when it is missing.
    md = job.listing_metadata or {}
    if md.get("title"):
        meta = {
            "title_id": md["title"],
            "number": md.get("number") or "0",
            "year": md.get("year") or 0,
            "regulation_type": job.regulation_type or "POJK",
        }
        status = md.get("status") or "berlaku"
        tentang = md.get("tentang")
    else:
        meta = extract_work_meta(detail_html, job.regulation_type or "POJK")
        status = "berlaku"
        tentang = None

    work = ParsedWork(
        sector=job.sector_code,
        source_url=job.source_url,
        source_pdf_url=source_registry.download_url(pdf_uuid),
        status=status,
        tentang=tentang,
        extraction_quality=quality,
        nodes=nodes,
        **meta,
    )
    work_id = load_work(work)
    load_nodes_by_level(work_id, nodes)

    if abstract_pdf:
        abstract_text, _ = _extract(abstract_pdf)
        load_abstract(work_id, abstract_text, source_registry.download_url(abstract_uuid))
    if faq_pdf:
        faq_text, _ = _extract(faq_pdf)
        load_faq(work_id, faq_text, source_registry.download_url(faq_uuid))

    state.mark_loaded(job.id, work_id, quality)


def handle_failure(job: CrawlJob, error: Exception) -> None:
    _capture(error)
    retry_count = job.retry_count + 1
    next_retry = retry_mod.next_retry_at(retry_count)
    if next_retry is None:
        state.update_status(job.id, "dead", str(error))
    else:
        state.update_retry(job.id, retry_count, next_retry, str(error))


async def _download(client, uuid: str | None) -> bytes | None:
    if not uuid:
        return None
    resp = await client.get(source_registry.download_url(uuid))
    resp.raise_for_status()
    return resp.content


def _extract(pdf_bytes: bytes | None) -> tuple[str, int]:
    if not pdf_bytes:
        return "", 0
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(pdf_bytes)
        f.flush()
        return extract_text(f.name)


def _capture(error: Exception) -> None:
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(error)
    except Exception:
        pass

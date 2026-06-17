# Data Pipeline

Crawls jdih.ojk.go.id, downloads PDFs, parses structure, scores extraction quality, loads into Supabase. Async parallel workers with exponential backoff and change detection.

---

## CLI Reference

All commands from project root:

```bash
# Discovery — crawl listing pages, seed crawl_jobs
python -m scripts.worker.run discover --sectors perbankan,fintech

# Process — download, parse, quality-score, load (5 concurrent workers)
python -m scripts.worker.run process --batch-size 20 --concurrency 5

# Discover then process in one command
python -m scripts.worker.run full --sectors perbankan --concurrency 5

# Continuous loop (Railway service)
python -m scripts.worker.run continuous --discovery-first

# Embedding generation (run after initial load, incremental)
python -m scripts.worker.run embed --batch-size 100

# Retry failed jobs (respects exponential backoff schedule)
python -m scripts.worker.run retry --limit 100

# Reset dead-letter jobs back to pending (manual override)
python -m scripts.worker.run reset-dead --sector fintech

# Stats
python -m scripts.worker.run stats
```

Flags: `--dry-run`, `--concurrency N`, `--max-runtime N` (seconds), `--ignore-freshness`, `--freshness-hours N`.

---

## Pipeline Flow

```
jdih.ojk.go.id
  Listing page: /Web/ViewPeraturan/Index?sektor=01&jenisPeraturan=06
        │
        ▼ discover.py — extract detail page UUIDs
  crawl_jobs [status: pending]
        │
        ▼ process.py — claim_jobs() atomically (FOR UPDATE SKIP LOCKED)
  Detail page: /web/ViewPeraturan/Detail/{uuid}/00/00
        │ Extract: title, number, year, status, pdf_uuid, abstract_uuid, faq_uuid
        │
        │ [Change detection] — skip if JDIH last-modified ≤ works.updated_at
        │        → crawl_jobs [status: skipped]
        │
        ▼ Async parallel downloads (asyncio.gather, semaphore=5)
  Main PDF    ← /Web/ViewPeraturan/DownloadDokumen/{pdf_uuid}
  Abstract    ← /Web/ViewPeraturan/DownloadDokumen/{abstract_uuid}
  FAQ (if present) ← /Web/ViewPeraturan/DownloadDokumen/{faq_uuid}
        │ Upload to Supabase Storage (regulation-pdfs bucket)
        │
        ▼ parser/extract_pymupdf.py — text extraction
  Raw text with page markers
        │
        ▼ parser/parse_structure.py — regex state machine
  Node tree: BAB → Bagian → Pasal → Ayat
        │
        ▼ parser/quality_scorer.py
  quality_score: 0.0–1.0
        │ [Score < 0.3] → crawl_jobs [status: flagged] → admin review queue
        │
        ▼ loader/load_to_supabase.py — breadth-first upsert
  works + document_nodes (embedding = NULL, FTS auto-generated)
        │
        ▼ loader/load_abstract.py + load_faq.py
  abstracts + faqs tables
        │
  crawl_jobs [status: loaded, extraction_quality: 0.87]
        │
  (later, separate pass)
        ▼ scripts/embeddings/generate.py
  document_nodes.embedding = vector(1536)  [batch, 100/call]
```

---

## Job State Machine

```
pending
  │ claim_jobs() — FOR UPDATE SKIP LOCKED
  ▼
crawling  ─── (> 15 min stuck) ──→ auto-reset to pending
  │
  ├── unchanged (change detection) ──→ skipped
  │
  ▼ (download + parse + quality check)
downloaded
  │
  ├── quality < 0.3 ──→ flagged (admin review)
  │
  ▼ (loaded to DB)
loaded
  │
  └── (embedding generated async)
      document_nodes.embedding populated

  failed (retry with exponential backoff)
    retry_count=1: retry after 5 min
    retry_count=2: retry after 30 min
    retry_count=3: retry after 2h
    retry_count=4: retry after 8h
    retry_count=5+: status=dead (manual review)
```

---

## Async Parallel Workers

Download and parse happen concurrently — not single-threaded.

```python
# worker/process.py
async def process_batch(jobs: list[CrawlJob], concurrency: int = 5) -> None:
    semaphore = asyncio.Semaphore(concurrency)

    async def process_one(job: CrawlJob) -> None:
        async with semaphore:
            try:
                await download_and_parse(job)
            except Exception as e:
                await handle_failure(job, e)

    await asyncio.gather(*[process_one(j) for j in jobs])

async def download_and_parse(job: CrawlJob) -> None:
    async with httpx.AsyncClient(timeout=60) as client:
        # Parallel downloads within a single job
        main_pdf, abstract_pdf, faq_pdf = await asyncio.gather(
            download_pdf(client, job.pdf_uuid),
            download_pdf(client, job.abstract_uuid),
            download_pdf(client, job.faq_uuid) if job.faq_uuid else asyncio.sleep(0),
        )
    # ... parse, score, load
```

---

## Exponential Backoff

```python
# crawler/retry.py
BACKOFF_SCHEDULE = [
    timedelta(minutes=5),   # retry 1
    timedelta(minutes=30),  # retry 2
    timedelta(hours=2),     # retry 3
    timedelta(hours=8),     # retry 4
]
MAX_RETRIES = len(BACKOFF_SCHEDULE)

async def handle_failure(job: CrawlJob, error: Exception) -> None:
    sentry_sdk.capture_exception(error)
    retry_count = job.retry_count + 1

    if retry_count > MAX_RETRIES:
        await update_job_status(job.id, "dead", str(error))
        return

    next_retry = datetime.now(UTC) + BACKOFF_SCHEDULE[retry_count - 1]
    await update_job_retry(job.id, retry_count, next_retry, str(error))
```

---

## Change Detection

Before downloading, check if the regulation changed since last scrape.

```python
# worker/discover.py
async def should_download(job: CrawlJob, detail_page_html: str) -> bool:
    last_modified_str = extract_last_modified(detail_page_html)
    if not last_modified_str:
        return True  # can't determine, always download

    last_modified = parse_date(last_modified_str)
    if not job.work_id:
        return True  # never loaded before

    work_updated_at = await get_work_updated_at(job.work_id)
    if last_modified <= work_updated_at:
        await update_job_status(job.id, "skipped")
        return False

    return True
```

---

## Quality Scoring

Every parsed document is scored 0–1. Score stored in `crawl_jobs.extraction_quality` and `works.extraction_quality`.

```python
# parser/quality_scorer.py
def score_extraction(nodes: list[Node], pdf_page_count: int) -> float:
    if not nodes:
        return 0.0

    pasal_nodes = [n for n in nodes if n.node_type == "pasal"]
    pasal_count = len(pasal_nodes)

    content_chars = sum(len(n.content_text or "") for n in nodes)
    chars_per_page = content_chars / max(pdf_page_count, 1)

    has_bab = any(n.node_type == "bab" for n in nodes)
    has_ayat = any(n.node_type == "ayat" for n in nodes)

    # Score components
    pasal_score = min(1.0, pasal_count / 10)       # 10+ pasals = full score
    density_score = min(1.0, chars_per_page / 200)  # 200 chars/page = full score
    structure_score = (0.5 if has_bab else 0) + (0.5 if has_ayat else 0)

    return round(pasal_score * 0.4 + density_score * 0.4 + structure_score * 0.2, 3)
```

Jobs with score < 0.3 are flagged, not loaded. Admin reviews flagged jobs at `/admin/scraper` and can force-load or discard.

---

## Embedding Generation

Separate pass after initial load. Incremental — only generates for nodes with `embedding IS NULL`.

```python
# scripts/embeddings/generate.py
async def generate_embeddings(batch_size: int = 100) -> None:
    client = openai.AsyncOpenAI()

    while True:
        nodes = await fetch_nodes_without_embeddings(limit=batch_size)
        if not nodes:
            break

        texts = [f"{n.node_type} {n.number or ''}\n{n.content_text or ''}" for n in nodes]

        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
            dimensions=1536,
        )

        embeddings = [e.embedding for e in response.data]
        await batch_update_embeddings(
            [(node.id, emb) for node, emb in zip(nodes, embeddings)]
        )

        log.info("embeddings_generated", count=len(nodes))
```

Use `text-embedding-3-small` (1536 dimensions, ~$0.02/1M tokens). Switch to `text-embedding-3-large` (3072 dimensions) if recall is insufficient.

---

## JDIH Scraping Details

### URL Patterns

```
Listing: http://jdih.ojk.go.id/Web/ViewPeraturan/Index?sektor={sector}&jenisPeraturan={type}
Detail:  http://jdih.ojk.go.id/web/ViewPeraturan/Detail/{uuid}/00/00
PDF:     http://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/{uuid}
```

### Sector + type code matrix

| Sector | sektor | Reg type | jenisPeraturan |
|--------|--------|----------|----------------|
| Perbankan | 01 | POJK | 06 |
| Pasar Modal | 02 | SEOJK | 07 |
| IKNB | 08 | KEOJK | 08 |
| Fintech | 10 | UU | 01 |
| Dana Pensiun | 06 | | |
| Perasuransian | 04 | | |

### UUID extraction

Detail page UUID (in URL) ≠ PDF download UUID (in page HTML).

```html
<!-- Extract these from detail page HTML -->
<a href="/Web/ViewPeraturan/DownloadDokumen/{pdf_uuid}">Peraturan</a>
<a href="/Web/ViewPeraturan/DownloadDokumen/{abstract_uuid}">Abstrak</a>
<a href="/Web/ViewPeraturan/DownloadDokumen/{faq_uuid}">FAQ</a>  <!-- may be absent -->
```

### JS rendering check

Verify listing pages during implementation:

```python
import httpx
r = httpx.get("http://jdih.ojk.go.id/Web/ViewPeraturan/Index?sektor=01&jenisPeraturan=06")
# If regulation links in r.text → use httpx (preferred)
# If empty → use Playwright (headless Chrome)
```

If Playwright is needed: add `playwright>=1.40` to `requirements.txt` and `chromium` to the Dockerfile.

---

## Directory Reference

| Path | Purpose |
|------|---------|
| `crawler/config.py` | HTTP client config: headers, delays, timeouts, SSL |
| `crawler/db.py` | Supabase service-role client singleton |
| `crawler/models.py` | `CrawlJob`, `ParsedWork`, `ParsedNode` Pydantic models |
| `crawler/state.py` | DB ops: `upsert_job`, `claim_jobs`, `update_status`, `update_retry` |
| `crawler/retry.py` | Exponential backoff schedule + `handle_failure()` |
| `crawler/source_registry.py` | Sector × type matrix to crawl |
| `worker/run.py` | CLI entrypoint (typer) |
| `worker/discover.py` | Listing page crawler → seeds crawl_jobs |
| `worker/process.py` | Async parallel batch processor |
| `parser/extract_pymupdf.py` | `extract_text(path)` → `(text, page_count)` |
| `parser/classify_pdf.py` | `born_digital \| scanned_clean \| image_only` |
| `parser/parse_structure.py` | Regex state machine → node tree |
| `parser/quality_scorer.py` | `score_extraction(nodes, page_count)` → 0–1 |
| `loader/load_to_supabase.py` | `load_work()`, `load_nodes_by_level()` (breadth-first) |
| `loader/load_abstract.py` | `load_abstract(work_id, text, pdf_url)` |
| `loader/load_faq.py` | `load_faq(work_id, text, pdf_url)` |
| `embeddings/generate.py` | Batch embedding generation, incremental |
| `agent/verify_suggestion.py` | Gemini Flash suggestion verification |
| `agent/apply_revision.py` | Python wrapper for `apply_revision()` SQL |

---

## Gotchas

- **UUID mismatch.** Detail page URL UUID ≠ PDF download UUID. Always extract download UUIDs from the HTML.
- **FAQ is optional.** Handle `faq_uuid = None`. Most pre-2020 POJKs don't have FAQs.
- **Rate limit the crawler.** 1–2s between requests. This is a government server.
- **Geo-blocking.** Some OJK services block non-Indonesian IPs. Test from an Indonesian VPN if requests fail with 403.
- **Dedup on source_url.** `crawl_jobs` has `UNIQUE(source_url)`. Use `ON CONFLICT DO NOTHING` when seeding.
- **Breadth-first node insertion.** Insert parent nodes before children. `load_nodes_by_level()` groups by depth and inserts depth 0 first, then depth 1, etc.
- **Embedding is NOT regenerated by `apply_revision()`.** After content update, `embedding` is set to `NULL`. Run `scripts/embeddings/generate.py` afterwards to regenerate.
- **Quality scorer calibration.** Initial thresholds (0.3 = flag) may need tuning after seeing real OJK PDFs. Adjust `QUALITY_FLAG_THRESHOLD` in `worker/process.py`.
- **Supabase anon key has 3s statement timeout.** Pipeline uses service role key — no timeout issue. But never accidentally use anon key in scripts.

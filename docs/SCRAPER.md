# Data Pipeline

Crawls jdih.ojk.go.id, downloads PDFs, parses structure, loads into Supabase.

---

## CLI Reference

All commands run from the project root:

```bash
python -m scripts.worker.run discover --sectors perbankan,fintech  # Crawl listing pages → seed crawl_jobs
python -m scripts.worker.run process --batch-size 20               # Download, parse, load pending jobs
python -m scripts.worker.run full --sectors perbankan              # Discover then process
python -m scripts.worker.run continuous --discovery-first          # Loop forever (Railway service)
python -m scripts.worker.run reprocess --force                     # Re-extract from existing PDFs
python -m scripts.worker.run retry-failed --limit 100              # Reset failed jobs to pending
python -m scripts.worker.run stats                                 # Show pipeline stats
```

Flags: `--dry-run`, `--batch-size N`, `--max-runtime N` (seconds), `--ignore-freshness`, `--freshness-hours N`.

---

## Pipeline Flow

```
jdih.ojk.go.id
  Listing page: /Web/ViewPeraturan/Index?sektor=01&jenisPeraturan=06
        │
        ▼ discover.py — extract detail page UUIDs
  crawl_jobs [status: pending, detail_uuid set]
        │
        ▼ process.py — claim_jobs() atomically
  Detail page: /web/ViewPeraturan/Detail/{uuid}/00/00
        │ Scrape: title, number, year, status, date_enacted, pdf_uuid, abstract_uuid, faq_uuid
        │
        ▼ Download PDFs
  Main PDF: /Web/ViewPeraturan/DownloadDokumen/{pdf_uuid}
  Abstract: /Web/ViewPeraturan/DownloadDokumen/{abstract_uuid}
  FAQ:      /Web/ViewPeraturan/DownloadDokumen/{faq_uuid}  (if present)
        │ Upload to Supabase Storage (regulation-pdfs bucket)
        │
        ▼ parser/extract_pymupdf.py — text extraction
  Raw text with page boundary markers
        │
        ▼ parser/parse_structure.py — regex state machine
  Node tree: BAB → Bagian → Pasal → Ayat
        │
        ▼ loader/load_to_supabase.py — breadth-first upsert
  works + document_nodes in DB (FTS auto-generated)
        │
        ▼ loader/load_abstract.py — abstract text
  abstracts table
        │
        ▼ loader/load_faq.py — FAQ text (if present)
  faqs table
        │
  crawl_jobs [status: loaded]
```

---

## Job State Machine

```
pending
  │ claim_jobs() — FOR UPDATE SKIP LOCKED
  ▼
crawling  ─── (> 15 min stuck) ──→ auto-reset to pending
  │
  ▼ detail page scraped
downloaded
  │
  ▼ PDF parsed
parsed
  │
  ▼ loaded to DB
loaded
  │
  ├── failed (at any step — error_message stored in DB)
```

---

## JDIH Scraping Details

### URL Patterns

```
Listing pages (sector × regulation type):
  http://jdih.ojk.go.id/Web/ViewPeraturan/Index?sektor={sector}&jenisPeraturan={type}

Detail pages (UUID from listing href):
  http://jdih.ojk.go.id/web/ViewPeraturan/Detail/{uuid}/00/00
  → contains: title, number, year, effective date, download UUIDs for PDF/abstract/FAQ

PDF downloads (UUID from detail page):
  http://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/{uuid}
  → direct binary PDF, no auth required
```

### Sector and type codes

| Sector | sektor param | Reg type | jenisPeraturan |
|--------|-------------|----------|----------------|
| Perbankan | 01 | POJK | 06 |
| Pasar Modal | 02 | SEOJK | 07 |
| IKNB | 08 | | |
| Fintech | 10 | | |
| Dana Pensiun | 06 | | |
| Perasuransian | 04 | | |

### Extracting UUIDs from detail pages

The detail page HTML contains download buttons. Pattern to look for:
```html
<!-- Main regulation PDF -->
<a href="/Web/ViewPeraturan/DownloadDokumen/{pdf_uuid}">Peraturan</a>

<!-- Abstract PDF -->
<a href="/Web/ViewPeraturan/DownloadDokumen/{abstract_uuid}">Abstrak</a>

<!-- FAQ PDF (not always present) -->
<a href="/Web/ViewPeraturan/DownloadDokumen/{faq_uuid}">FAQ</a>
```

Note: the UUID in the detail page URL (`/Detail/{uuid}/00/00`) is the **detail page UUID**, not the PDF UUID. The PDF UUIDs are different and are extracted from the download links in the detail page HTML.

### Listing page rendering

**Unknown at implementation time:** verify whether listing pages are:
- Static HTML (httpx works) — preferred
- JavaScript-rendered (need Playwright)

Test first:
```python
import httpx
r = httpx.get("http://jdih.ojk.go.id/Web/ViewPeraturan/Index?sektor=01&jenisPeraturan=06")
# If regulation links are in r.text → httpx is sufficient
# If r.text has no regulation entries → need Playwright
```

---

## PDF Quality

OJK regulations post-2013 are **born-digital** (PDF-1.7, embedded TrueType fonts, machine-readable text). PyMuPDF extracts text directly — no OCR pipeline needed.

```python
import fitz  # pymupdf

doc = fitz.open("path/to/pojk.pdf")
for page in doc:
    text = page.get_text()  # Works directly on OJK PDFs
```

Pre-2013 regulations may be scanned. Use `parser/classify_pdf.py` to detect and flag — skip or queue for OCR separately.

---

## Extraction Version

Bump `EXTRACTION_VERSION` in `worker/process.py` when parser logic changes. `reprocess` command re-extracts jobs with outdated version numbers.

Current: **v1**

---

## Directory Reference

| Path | Purpose |
|------|---------|
| `crawler/config.py` | HTTP headers, delays, SSL context |
| `crawler/db.py` | Supabase singleton client (service role) |
| `crawler/models.py` | `CrawlJob` pydantic model |
| `crawler/state.py` | Job state: `upsert_job`, `claim_pending_jobs`, `update_status` |
| `crawler/source_registry.py` | JDIH sector/type combinations to crawl |
| `worker/run.py` | CLI entrypoint |
| `worker/discover.py` | Listing page crawler → seeds crawl_jobs |
| `worker/process.py` | PDF → DB pipeline per job |
| `parser/extract_pymupdf.py` | `extract_text(path)` → `(text, page_count)` |
| `parser/classify_pdf.py` | `classify_pdf(path)` → `born_digital \| scanned_clean \| image_only` |
| `parser/parse_structure.py` | `parse_structure(text)` → node tree |
| `loader/load_to_supabase.py` | `load_work()`, `load_nodes_by_level()` |
| `loader/load_abstract.py` | `load_abstract(work_id, text, pdf_url)` |
| `loader/load_faq.py` | `load_faq(work_id, text, pdf_url)` |
| `agent/verify_suggestion.py` | Gemini Flash verification of suggestions |
| `agent/apply_revision.py` | Python wrapper for `apply_revision()` SQL function |

---

## Gotchas

- **UUID mismatch.** `/Detail/{uuid}/00/00` UUID ≠ PDF download UUID. Extract download UUIDs from the detail page HTML, not from the URL.
- **FAQ is optional.** Not all POJKs have a FAQ document. Handle `faq_uuid = None` gracefully.
- **Rate limiting.** 1–2 second delay between requests. OJK site is government-hosted — be respectful.
- **Geo-blocking risk.** Some OJK systems are Indonesia-only. If scraping from outside Indonesia, use an Indonesian VPN or proxy.
- **Dedup on source_url.** `crawl_jobs` has `UNIQUE(source_url)`. Use upsert (`ON CONFLICT DO NOTHING`) when seeding jobs.
- **Node insertion is breadth-first.** `load_nodes_by_level()` inserts depth-1 nodes first, then depth-2, etc. This avoids FK ordering issues (parent must exist before child).
- **Abstract text is structured.** OJK abstract PDFs follow a consistent template. Consider parsing them into structured fields (latar belakang, ruang lingkup, pokok pengaturan) rather than raw text.

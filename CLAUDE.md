# CLAUDE.md

regulasi-id — Open, AI-native Indonesian financial regulatory platform. MCP server + web app giving Claude grounded access to OJK (Otoritas Jasa Keuangan) regulations. Production-grade: hybrid search, distributed caching, full observability.

**Repo:** `alimaksudi/regulasi-id` | **Live:** https://regulasi.id (planned) | **MCP:** Railway (planned)

---

## Architecture

Monorepo with three main pieces:

| Component | Path | Tech |
|-----------|------|------|
| Web app | `apps/web/` | Next.js (App Router), React 19, TypeScript, Tailwind v4, shadcn/ui, Zod |
| MCP server | `apps/mcp-server/` | Python 3.12+, FastMCP, supabase-py, Upstash Redis |
| Data pipeline | `scripts/` | Python — crawler (jdih.ojk.go.id), parser (PyMuPDF), async loader, Gemini verification |
| Database | `packages/supabase/migrations/` | Supabase (PostgreSQL + pgvector + PgBouncer) |

### Key directories

```
apps/web/src/app/[locale]/       — Public pages (/, /search, /regulasi/[type]/[slug], /sektor/[sector])
apps/web/src/app/admin/          — Admin pages (NOT under [locale])
apps/web/src/components/         — React components (PascalCase.tsx)
apps/web/src/lib/                — Utilities, Supabase clients (server.ts, client.ts, service.ts)
apps/web/src/lib/schemas/        — Zod schemas for all API inputs
apps/web/src/lib/cache/          — Upstash Redis cache helpers
apps/web/src/lib/ratelimit/      — Upstash rate limiter helpers
apps/web/src/i18n/               — i18n config (routing.ts, request.ts)
apps/web/messages/               — Translation files (id.json, en.json)
apps/mcp-server/server.py        — MCP tools: search_regulations, get_article, get_regulation_status, get_compliance_checklist, list_regulations
apps/mcp-server/cache.py         — Upstash Redis cache (TTL-based, distributed)
apps/mcp-server/ratelimit.py     — Upstash Redis rate limiter (sliding window, cross-instance)
scripts/crawler/                 — jdih.ojk.go.id scraper
scripts/parser/                  — PDF parsing (PyMuPDF) + quality scorer
scripts/worker/                  — Orchestration CLI (discover, process, continuous) — async/concurrent
scripts/embeddings/              — Embedding generation (OpenAI/Gemini) for pgvector hybrid search
scripts/agent/                   — Gemini verification agent
packages/supabase/migrations/    — All SQL migrations (sequential, NNN_description.sql)
```

---

## Commands

```bash
# Web app (from apps/web/)
npm run dev          # Dev server (port 3000)
npm run build        # Production build
npm run lint         # ESLint
npm run test         # Vitest watch
npm run test:run     # Vitest single run (CI)
npm run test:e2e     # Playwright E2E

# MCP server (from apps/mcp-server/)
python server.py     # Start MCP server (needs SUPABASE_URL, SUPABASE_ANON_KEY, UPSTASH_REDIS_URL, UPSTASH_REDIS_TOKEN)

# Data pipeline (from project root)
python -m scripts.worker.run discover --sectors perbankan,fintech
python -m scripts.worker.run process --batch-size 20 --concurrency 5
python -m scripts.worker.run full --sectors perbankan
python -m scripts.worker.run continuous
python -m scripts.worker.run embed --batch-size 100   # Generate embeddings for pgvector
python -m scripts.worker.run stats
```

Migrations are applied directly to Supabase via the SQL editor. Always test against a test Supabase project in CI before applying to production.

---

## Database Schema

All tables have RLS enabled with public read policies for regulatory data.

### Core tables

| Table | Purpose |
|-------|---------|
| `sectors` | OJK regulatory sectors (perbankan, pasar-modal, iknb, fintech, dana-pensiun, perasuransian) |
| `regulation_types` | Regulation types: POJK, SEOJK, KEOJK, UU, PP, PERPRES — with hierarchy levels |
| `works` | Individual regulations. Has `slug`, `sector_id`, `frbr_uri`, metadata. `search_fts` TSVECTOR GENERATED ALWAYS |
| `document_nodes` | Hierarchical structure: BAB > Bagian > Pasal > Ayat. `content_text` + `fts` TSVECTOR + `embedding vector(1536)` |
| `abstracts` | Official OJK abstract documents (one per POJK). Downloaded from JDIH alongside the main PDF |
| `faqs` | Official OJK FAQ documents (one per POJK where available). Useful for compliance context |
| `revisions` | **Append-only** audit log for content changes. Never UPDATE or DELETE rows |
| `suggestions` | Crowd-sourced corrections. Anyone submits, admin approves |
| `work_relationships` | Cross-references between regulations (mengubah, mencabut, melaksanakan, etc.) |
| `compliance_mappings` | Curated table: sector + business_type → applicable works. Powers `get_compliance_checklist()` |
| `crawl_jobs` | Scraper job queue. State machine: pending → crawling → downloaded → parsed → loaded / failed |
| `discovery_progress` | Crawl freshness cache per (sector, regulation_type) pair |
| `search_analytics` | Log of queries — what was searched, how many results, zero-result queries |

### Regulation type hierarchy

```
UU (Undang-Undang)                 level 1 — source authority for OJK
PP (Peraturan Pemerintah)          level 2
PERPRES (Peraturan Presiden)       level 3
POJK (Peraturan OJK)               level 4 — primary OJK instrument
SEOJK (Surat Edaran OJK)           level 5 — circular/technical guidance
KEOJK (Keputusan OJK)              level 6 — specific decisions
```

### Critical invariant: content mutations

**Never UPDATE `document_nodes.content_text` directly.** All mutations go through `apply_revision()` SQL function:
1. INSERT into `revisions` (old + new content, reason, actor)
2. UPDATE `document_nodes.content_text` (FTS auto-updates via GENERATED ALWAYS; embedding regenerated by background job)
3. UPDATE `suggestions.status` if triggered by a suggestion

All steps in a single transaction.

### Search: `search_regulations()` — hybrid

**Do not clone Pasal.id's keyword-only approach.** We use 4-layer hybrid search:

- **Layer 1:** Identity fast path — exact regulation identifiers ("POJK 10 2022"), score 1000, early exit
- **Layer 2:** Works FTS — `works.search_fts` TSVECTOR for title/topic queries, score 1–15
- **Layer 3:** Content FTS — `document_nodes.fts` (websearch → plainto → ILIKE), score 0.01–0.5
- **Layer 4:** Semantic — cosine similarity on `document_nodes.embedding` (pgvector), score 0–1

**RRF reranking:** final results sorted by Reciprocal Rank Fusion combining FTS rank and vector similarity rank. This handles synonyms and concept queries FTS alone cannot.

Embeddings generated by `scripts/embeddings/generate.py` on ingest and stored in `document_nodes.embedding vector(1536)`. Regenerated on content change.

```sql
-- pgvector operator (cosine distance)
SELECT id, content_text, 1 - (embedding <=> $query_embedding) AS similarity
FROM document_nodes
ORDER BY embedding <=> $query_embedding
LIMIT 50;
```

### Materialized views

Never compute aggregations on every request. Refresh every 15 minutes via pg_cron.

```sql
CREATE MATERIALIZED VIEW mv_sector_stats AS
SELECT s.code, s.name_id, count(w.id) AS regulation_count,
       count(CASE WHEN w.status = 'berlaku' THEN 1 END) AS berlaku_count
FROM sectors s LEFT JOIN works w ON w.sector_id = s.id
GROUP BY s.id, s.code, s.name_id;

CREATE UNIQUE INDEX ON mv_sector_stats(code);

-- Refresh job (pg_cron, migration 021)
SELECT cron.schedule('refresh-sector-stats', '*/15 * * * *',
  'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_sector_stats');
```

### Connection pooling

Always connect via **PgBouncer** (transaction mode). Supabase enables this in Settings → Database → Connection pooling. Use the pooler connection string (`db.xxx.supabase.co:6543`), not the direct connection (`db.xxx.supabase.co:5432`).

Direct connection is only for migrations — PgBouncer incompatible with `SET` commands in migration SQL.

---

## Coding Conventions

### TypeScript / Next.js

- **Server Components by default.** Only `"use client"` for interactivity.
- **Supabase access:** `@supabase/ssr`. Use `getUser()` on server, never trust `getSession()`.
- **File naming:** `kebab-case.tsx` for routes, `PascalCase.tsx` for components.
- **Styling:** Tailwind utility classes only.
- **UI language:** Indonesian primary, English secondary.
- **Admin auth:** `requireAdmin()` from `src/lib/admin-auth.ts`.
- **Validation:** All API route inputs validated with Zod schemas from `src/lib/schemas/`. Return 400 with Zod error details on validation failure — never trust raw `req.json()`.
- **Rate limiting:** Use `src/lib/ratelimit/` (Upstash, distributed) — not in-memory.
- **Caching:** Use `src/lib/cache/` (Upstash) for hot data. Vercel ISR for page-level.
- **Error tracking:** `Sentry.captureException(err)` in all catch blocks in API routes. Wrap Server Component trees in Sentry `ErrorBoundary`.
- **Tracing:** Use `@vercel/otel` — spans auto-created for Server Components + API routes.
- **Pagination:** Cursor-based on all list endpoints. Never offset pagination on public APIs.

```typescript
// Correct: Zod validation on API route
import { z } from "zod"

const SearchSchema = z.object({
  q: z.string().min(1).max(500),
  sector: z.string().optional(),
  limit: z.coerce.number().int().min(1).max(50).default(10),
})

export async function GET(req: Request) {
  const parsed = SearchSchema.safeParse(Object.fromEntries(new URL(req.url).searchParams))
  if (!parsed.success) return Response.json({ error: parsed.error.flatten() }, { status: 400 })
  // ...
}
```

### i18n

Uses `next-intl` with `localePrefix: 'as-needed'`. Indonesian (default) has no URL prefix. English uses `/en` prefix.

- **Config:** `src/i18n/routing.ts`, `src/i18n/request.ts`
- **Messages:** `messages/id.json` (source of truth), `messages/en.json`
- **Middleware:** `src/middleware.ts` (excludes `/api`, `/admin`, static files)
- **Server Components:** Use `getTranslations` with `await` for async components, `useTranslations` for sync
- **Client Components:** Use `useTranslations` from `next-intl`
- **setRequestLocale:** Required at top of every Server Component page
- **CRITICAL:** Async Server Components MUST use `getTranslations` with `await`, never `useTranslations`

### Python

- Python 3.12+. Type hints on all function signatures.
- `httpx` with async/await for HTTP.
- `asyncio.gather` for concurrent downloads in the pipeline — not single-threaded.
- Prefer functions over classes.
- PDF extraction: `pymupdf`. OJK PDFs are born-digital — no OCR needed for post-2013 regulations.
- Embeddings: `openai` or `google.genai` — batch requests, 100 nodes per call max.
- Gemini agent: `from google import genai`. Advisory only — admin must approve suggestions.
- Error handling: structured logging with `structlog`, Sentry in all `except` blocks.

```python
# Correct: parallel PDF downloads
async def process_job(job: CrawlJob) -> None:
    async with httpx.AsyncClient() as client:
        main_pdf, abstract_pdf, faq_pdf = await asyncio.gather(
            download_pdf(client, job.pdf_uuid),
            download_pdf(client, job.abstract_uuid),
            download_pdf(client, job.faq_uuid) if job.faq_uuid else asyncio.sleep(0),
        )
```

### SQL migrations

- Numbered sequentially: `packages/supabase/migrations/NNN_description.sql`
- Always glob `packages/supabase/migrations/*.sql` to verify next number before creating.
- Always add indexes for WHERE/JOIN/ORDER BY columns — including `vector_cosine_ops` for pgvector columns.
- Always enable RLS on new tables. Add public read policy for regulatory data.
- Computed columns use `GENERATED ALWAYS AS`.
- `CREATE OR REPLACE FUNCTION` drops `SET search_path`. Always re-apply `ALTER FUNCTION ... SET search_path = 'public', 'extensions'` after definition.
- Migrations are tested in CI against a test Supabase project before merging. Do not apply to production until CI passes.
- Use the **direct connection** (port 5432) for migrations — PgBouncer (port 6543) breaks `SET` commands.

---

## OJK JDIH Scraper Details

### URL patterns

```
Listing pages:
  http://jdih.ojk.go.id/Web/ViewPeraturan/Index?sektor={sector_code}&jenisPeraturan={type_code}

Detail pages (UUID-based):
  http://jdih.ojk.go.id/web/ViewPeraturan/Detail/{uuid}/00/00

PDF download:
  http://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/{uuid}
```

### Sector codes (JDIH internal)

| Sector | JDIH sektor param |
|--------|-------------------|
| Perbankan | 01 |
| Pasar Modal | 02 |
| IKNB | 08 |
| Fintech | 10 |

### PDF quality

OJK PDFs (post-2013) are **born-digital, machine-readable**. No OCR required. Every extracted document is scored by `parser/quality_scorer.py`:

```python
def score_extraction(nodes: list[Node], pdf_page_count: int) -> float:
    pasal_count = len([n for n in nodes if n.node_type == "pasal"])
    content_chars = sum(len(n.content_text or "") for n in nodes)
    chars_per_page = content_chars / max(pdf_page_count, 1)
    # Good extraction: >100 chars/page, >0 pasals
    return min(1.0, (pasal_count / 10) * 0.5 + (chars_per_page / 200) * 0.5)
```

Jobs with quality score < 0.3 are flagged for manual review — never silently loaded.

### Change detection

Before re-downloading a regulation, compare the detail page's last-modified date against `works.updated_at`. Skip download if unchanged — saves bandwidth and avoids overwriting clean extractions.

### Retry policy

Exponential backoff on failures — not simple reset-to-pending:

```
Attempt 1: immediate
Attempt 2: 5 min
Attempt 3: 30 min
Attempt 4: 2 hours
Attempt 5+: dead letter queue (manual review)
```

---

## Environment Variables

| File | Key vars |
|------|----------|
| `.env` (root) | `SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY` |
| `apps/web/.env.local` | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `ADMIN_EMAILS`, `NEXT_PUBLIC_SITE_URL`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_DSN`, `NEXT_PUBLIC_PLAUSIBLE_DOMAIN` |
| `apps/mcp-server/.env` | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `SENTRY_DSN` |
| `scripts/.env` | `SUPABASE_URL`, `SUPABASE_KEY` (= SERVICE_ROLE_KEY), `GEMINI_API_KEY`, `OPENAI_API_KEY`, `SENTRY_DSN` |

**`SUPABASE_KEY` in scripts = `SUPABASE_SERVICE_ROLE_KEY` (bypasses RLS). Never expose to browser.**

---

## Deployment

- **Web:** Vercel (auto-deploys from `main`). Run `vercel link --project regulasi-id-web --yes` from monorepo root, then `vercel --prod --yes`.
- **MCP server:** Railway (Dockerfile at `apps/mcp-server/Dockerfile`).
- **Database:** Supabase (Singapore region). Always connect via PgBouncer (port 6543) from app code; direct (port 5432) for migrations only.
- **Redis:** Upstash (serverless Redis, global). Free tier sufficient for MVP.
- **Embeddings:** Generated by pipeline worker on ingest — not real-time.
- **Git:** Push to `main` directly.

---

## Observability

| Tool | What it covers |
|------|---------------|
| Sentry | Runtime errors — web, MCP server, pipeline |
| `@vercel/otel` + OpenTelemetry | Distributed traces on API routes + Server Components |
| Plausible | Privacy-friendly product analytics (search volume, popular sectors) |
| `search_analytics` table | Zero-result queries — direct product backlog input |
| Vercel dashboard | Web vitals, function duration, cold starts |
| Railway logs | MCP server + pipeline worker logs (structured JSON via `structlog`) |

---

## Domain Glossary

| Term | Meaning |
|------|---------|
| POJK | Peraturan OJK — primary regulatory instrument issued by OJK Board of Commissioners |
| SEOJK | Surat Edaran OJK — circular letters providing technical/implementation guidance |
| KEOJK | Keputusan OJK — specific decisions/determinations by OJK |
| Pasal | Article — primary searchable unit within a regulation |
| Ayat | Sub-article, numbered (1), (2), (3) within a Pasal |
| BAB | Chapter — top-level grouping |
| Bagian | Section — sub-grouping within a BAB |
| OJK | Otoritas Jasa Keuangan — Indonesia's integrated financial services authority |
| IKNB | Industri Keuangan Non-Bank — non-bank financial institutions |
| Berlaku / Dicabut / Diubah | In force / Revoked / Amended |
| RRF | Reciprocal Rank Fusion — algorithm for combining keyword + semantic search ranks |

---

## Gotchas

- **Listing pages may be JavaScript-rendered.** Verify during scraper development — may need Playwright instead of httpx.
- **UUID mismatch.** The UUID in the detail page URL differs from the PDF download UUID. Scrape both from the detail page HTML.
- **pgvector index type.** Use `ivfflat` (approximate, fast) for > 100k vectors, `hnsw` for best recall. Start with `hnsw` — rebuild if query latency exceeds 100ms.
- **Embedding dimension must match index.** If you change models (e.g., 1536 → 3072), drop and rebuild the vector index and regenerate all embeddings.
- **Upstash rate limiter is cross-instance.** Unlike in-memory rate limiting, this correctly enforces limits across all Railway instances. Use `@upstash/ratelimit` in Next.js and `upstash-py` in MCP server.
- **PgBouncer + transactions.** `LISTEN/NOTIFY` and `SET` statements don't work through PgBouncer in transaction mode. Use direct connection for those.
- **Cursor pagination implementation.** Encode cursors as base64(`last_id:last_sort_value`) — never expose raw integers. Use `WHERE (year, id) < (cursor_year, cursor_id)` for stable cursor pagination.
- **Materialized view refresh is concurrent.** `REFRESH MATERIALIZED VIEW CONCURRENTLY` requires a unique index. Without it, the refresh blocks reads.
- **RLS blocks empty results.** If a table returns no data, check that an RLS policy exists.
- **i18n async/sync distinction.** Using `useTranslations` in async Server Components causes build error. Use `getTranslations` with `await`.
- **i18n navigation imports.** Public pages must import from `@/i18n/routing`, not `next/link`.
- **Zod + Next.js searchParams.** `URLSearchParams.get()` returns `string | null`. Use `z.string().optional()` or `z.coerce.number()` — Zod handles the coercion.
- **Sentry source maps.** Vercel automatically uploads source maps to Sentry when `SENTRY_AUTH_TOKEN` is set. Do not commit source maps to git.
- **Embedding regeneration on content update.** `apply_revision()` updates `content_text` but does NOT regenerate embeddings synchronously. A background job (`scripts/embeddings/regenerate.py`) must run after bulk revisions to keep pgvector index fresh.

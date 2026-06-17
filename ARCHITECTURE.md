# Architecture

## System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                │
│  Browser → Next.js Web App (Vercel / regulasi.id)                       │
│  Claude Desktop/Code → MCP Server (Railway)                              │
│  3rd-party developers → REST API (/api/v1/) + OpenAPI spec              │
└──────────────────────────────────────────────────────────────────────────┘
                 │                         │
                 ▼                         ▼
┌────────────────────────┐   ┌──────────────────────────────────────────┐
│   Next.js Web App      │   │   FastMCP Server (Python)                │
│   Vercel               │   │   Railway                                │
│   ISR + SSR + Edge     │   │   5 tools                                │
│   @vercel/otel traces  │   │   Upstash Redis rate limiter + cache     │
│   Sentry errors        │   │   Sentry errors + structlog              │
│   Plausible analytics  │   │                                          │
│   Zod input validation │   │                                          │
│   Upstash rate limiter │   │                                          │
└────────────────────────┘   └──────────────────────────────────────────┘
                 │                         │
                 └─────────────┬───────────┘
                               ▼
          ┌────────────────────────────────────────────┐
          │         Upstash Redis (global)             │
          │  - Distributed rate limiting               │
          │  - Shared cache (TTL-based, cross-instance)│
          │  - Session hot data                        │
          └────────────────────────────────────────────┘
                               │
                               ▼
          ┌────────────────────────────────────────────┐
          │          Supabase (PostgreSQL)             │
          │  PgBouncer (port 6543) — app connections   │
          │  Direct (port 5432) — migrations only      │
          │                                            │
          │  Core tables: sectors, regulation_types    │
          │  works (TSVECTOR search_fts)               │
          │  document_nodes (TSVECTOR fts +            │
          │                  vector(1536) embedding)   │
          │  abstracts, faqs, work_relationships       │
          │  revisions, suggestions                    │
          │  compliance_mappings, crawl_jobs           │
          │  search_analytics                          │
          │                                            │
          │  Materialized views (refresh every 15min)  │
          │  mv_sector_stats, mv_type_stats            │
          │                                            │
          │  RPCs: search_regulations() hybrid         │
          │       apply_revision(), claim_jobs()       │
          │  Supabase Auth (admin only)                │
          │  Supabase Storage (PDFs)                   │
          └────────────────────────────────────────────┘
                               │
          ┌────────────────────▼───────────────────────┐
          │         Data Pipeline (Python)             │
          │  async workers (asyncio.gather)            │
          │  jdih.ojk.go.id crawler                   │
          │  PDF parser (PyMuPDF) + quality scorer     │
          │  Embedding generator (batch)               │
          │  Supabase loader                           │
          │  Exponential backoff on failures           │
          │  Change detection (skip unchanged PDFs)    │
          └────────────────────────────────────────────┘
```

---

## Component Detail

### 1. Next.js Web App (`apps/web/`)

**Rendering strategy:**
- Server Components by default — direct Supabase queries, no useEffect data fetching
- ISR (Incremental Static Regeneration) on regulation pages (24h TTL)
- Streaming responses on search (first result appears before all are loaded)
- `"use client"` only for interactive elements

**Page structure:**
```
app/
├── layout.tsx                    — Root: fonts, global CSS, lang attr, Sentry + OTel
├── [locale]/
│   ├── layout.tsx                — Locale: title template, OG metadata, Plausible
│   ├── page.tsx                  — Landing (ISR 1h)
│   ├── search/page.tsx           — Search results (dynamic, streaming, noindex)
│   ├── regulasi/[type]/[slug]/   — Regulation reader (ISR 24h)
│   │   └── koreksi/[nodeId]/     — Correction form (client)
│   ├── sektor/[sector]/          — Browse by sector (ISR 1h, from mv_sector_stats)
│   ├── jenis/[type]/             — Browse by regulation type
│   ├── connect/page.tsx          — MCP setup guide
│   └── api-docs/page.tsx         — Live OpenAPI docs (Swagger UI)
└── admin/                        — Admin dashboard (no locale, auth-gated)
    ├── login/
    ├── suggestions/
    ├── regulasi/
    ├── compliance/               — Manage compliance_mappings
    └── scraper/
```

**Three Supabase clients:**

| File | Context | Key | Notes |
|------|---------|-----|-------|
| `lib/supabase/server.ts` | Server Components + Route Handlers | Anon | Respects RLS |
| `lib/supabase/client.ts` | Client Components | Anon | Browser |
| `lib/supabase/service.ts` | Admin API routes only | Service role | Bypasses RLS — never import elsewhere |

**Rate limiting:** Upstash `@upstash/ratelimit` with sliding window. One limiter per endpoint class (search, list, suggestions). Config in `lib/ratelimit/index.ts`.

**Input validation:** Every API route parses inputs through a Zod schema before any DB call. Schemas in `lib/schemas/`. Invalid input returns 400 with structured Zod error.

**Observability:**
- `@vercel/otel` — automatic traces on all API routes and Server Components
- Sentry — runtime error capture; wrap all catch blocks with `Sentry.captureException()`
- Plausible — privacy-first analytics; no cookies, GDPR-compliant

---

### 2. MCP Server (`apps/mcp-server/server.py`)

FastMCP Python server. Stateless — no user sessions. All caching via Upstash Redis (distributed, survives deploys, shared across instances).

**Tools:**

```
search_regulations(query, sector?, regulation_type?, year_from?, year_to?, status?, limit?)
  → Calls search_regulations() Supabase RPC (hybrid: FTS + pgvector + RRF)
  → Returns: [{ title, frbr_uri, type, sector, year, pasal, snippet, status, score, disclaimer }]
  → Rate limit: 30/min/IP (Upstash)
  → No cache (results evolve as DB grows)
  → Logs query + result_count to search_analytics table

get_article(regulation_type, number, year, article_number)
  → Direct lookup: works → document_nodes (pasal) → children (ayat)
  → Returns: { title, frbr_uri, pasal, content, ayat, cross_references, status, disclaimer }
  → Rate limit: 60/min/IP
  → Cache: Upstash, TTL 1h, key = "article:{type}:{number}:{year}:{pasal}"

get_regulation_status(regulation_type, number, year)
  → Lookup work + work_relationships JOIN relationship_types
  → Returns: { title, status, explanation, amendments, implemented_by, related, disclaimer }
  → Rate limit: 60/min/IP
  → Cache: Upstash, TTL 1h, key = "status:{type}:{number}:{year}"

get_compliance_checklist(sector, business_type?)
  → compliance_mappings JOIN works JOIN sectors
  → Returns: { sector, business_type, required_regulations, disclaimer }
  → Rate limit: 30/min/IP
  → No cache (mappings updated by admin)

list_regulations(sector?, regulation_type?, year?, status?, cursor?, per_page?)
  → Filtered, cursor-paginated works query
  → Returns: { total, next_cursor, regulations: [...], disclaimer }
  → Rate limit: 30/min/IP

ping()
  → Health check: works count + embedding coverage %
```

**Rate limiting:** `upstash-py` `Ratelimit` — sliding window, Redis-backed. Cross-instance safe — 3 Railway instances each enforce the same shared limit.

**Error handling:** Sentry SDK initialized at startup. All tool exceptions captured before returning error response to Claude.

---

### 3. Data Pipeline (`scripts/`)

**Async parallel workers — not single-threaded:**

```python
# worker/process.py
async def process_batch(jobs: list[CrawlJob]) -> None:
    semaphore = asyncio.Semaphore(5)   # max 5 concurrent downloads

    async def process_one(job):
        async with semaphore:
            await download_and_parse(job)

    await asyncio.gather(*[process_one(j) for j in jobs])
```

**Exponential backoff on failure:**

```
Attempt 1: immediate
Attempt 2: 5 min delay
Attempt 3: 30 min delay
Attempt 4: 2 hours delay
Attempt 5+: status = 'dead' → manual review queue
```

**Quality scoring:** Every parsed document receives a quality score (0–1) based on pasal count, chars/page ratio, structure depth. Score stored in `crawl_jobs.extraction_quality`. Jobs with score < 0.3 skipped on load, flagged in admin dashboard.

**Change detection:** Compare JDIH detail page `last-modified` header against `works.updated_at`. Skip download if unchanged. Log "skipped:unchanged" in crawl_jobs.

**Embedding generation (separate pass):**
```bash
python -m scripts.worker.run embed --batch-size 100
```
Runs after initial load. Generates `document_nodes.embedding vector(1536)` via OpenAI `text-embedding-3-small`. Batched 100 nodes per API call. Incremental — only generates for nodes with `embedding IS NULL`.

**Job state machine:**
```
pending
  │ claim_jobs() — FOR UPDATE SKIP LOCKED
  ▼
crawling ── (> 15 min stuck) → auto-reset to pending
  │
  ├── (unchanged) → skipped
  ▼
downloaded
  │
  ├── (quality < 0.3) → flagged (manual review)
  ▼
parsed
  │
  ▼
loaded
  │
  ├── failed (retry 1–4, then dead)
```

---

## Database Schema

### Entity Relationships

```
sectors (1) ──────────────────────── (*) works
regulation_types (1) ─────────────── (*) works
works (1) ─────────────────────────── (*) document_nodes
works (1) ─────────────────────────── (0/1) abstracts
works (1) ─────────────────────────── (0/1) faqs
works (*) ──── work_relationships ──── (*) works
document_nodes (1) ─────────────────── (*) revisions
document_nodes (1) ─────────────────── (*) suggestions
sectors + works ──── compliance_mappings
```

### Key table shapes

**`works`**
```sql
id                    SERIAL PRIMARY KEY
sector_id             INTEGER REFERENCES sectors(id)
regulation_type_id    INTEGER REFERENCES regulation_types(id)
frbr_uri              TEXT UNIQUE          -- /akn/id/act/pojk/2022/10
slug                  TEXT UNIQUE          -- pojk-10-2022 (auto-generated trigger)
title_id              TEXT                 -- Full Indonesian title
number                TEXT                 -- "10" (not integer — can be "10/P1")
year                  INTEGER
status                TEXT                 -- berlaku | diubah | dicabut | tidak_berlaku
date_enacted          DATE
source_url            TEXT                 -- jdih.ojk.go.id detail page URL
source_pdf_url        TEXT                 -- Supabase Storage URL
content_verified      BOOLEAN DEFAULT false
extraction_quality    FLOAT                -- 0–1 from quality scorer
subject_tags          TEXT[]
search_text           TEXT                 -- denormalized trigger-maintained
search_fts            TSVECTOR GENERATED ALWAYS AS (to_tsvector('indonesian', ...)) STORED
```

**`document_nodes`**
```sql
id                    BIGSERIAL PRIMARY KEY
work_id               INTEGER REFERENCES works(id)
parent_id             BIGINT REFERENCES document_nodes(id)
node_type             TEXT  -- bab | bagian | paragraf | pasal | ayat | preamble | penjelasan_pasal
number                TEXT  -- "1", "81", "81A"
heading               TEXT
content_text          TEXT
sort_order            BIGINT
pdf_page_start        INTEGER
embedding             vector(1536)         -- pgvector, cosine similarity
fts                   TSVECTOR GENERATED ALWAYS AS (to_tsvector('indonesian', COALESCE(content_text,''))) STORED
```

**`search_analytics`**
```sql
id                    BIGSERIAL PRIMARY KEY
query                 TEXT NOT NULL
sector_filter         TEXT
result_count          INTEGER
zero_results          BOOLEAN GENERATED ALWAYS AS (result_count = 0) STORED
source                TEXT  -- 'web' | 'api' | 'mcp'
created_at            TIMESTAMPTZ DEFAULT NOW()
```

**Indexes:**
```sql
-- pgvector (document_nodes)
CREATE INDEX idx_nodes_embedding ON document_nodes USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- Standard
CREATE INDEX idx_works_fts ON works USING GIN(search_fts);
CREATE INDEX idx_nodes_fts ON document_nodes USING GIN(fts);
CREATE INDEX idx_works_trgm ON works USING GIN(title_id gin_trgm_ops);
CREATE INDEX idx_analytics_zero ON search_analytics(zero_results) WHERE zero_results = true;
```

---

## Hybrid Search Function

```sql
-- Migration 013: search_regulations()
-- 4-layer: identity → works FTS → content FTS → pgvector
-- Results combined by RRF (Reciprocal Rank Fusion)

CREATE OR REPLACE FUNCTION search_regulations(
  p_query          TEXT,
  p_sector         TEXT DEFAULT NULL,
  p_type           TEXT DEFAULT NULL,
  p_year_from      INT  DEFAULT NULL,
  p_year_to        INT  DEFAULT NULL,
  p_status         TEXT DEFAULT NULL,
  p_limit          INT  DEFAULT 10,
  p_query_embedding vector(1536) DEFAULT NULL  -- caller generates embedding, passes here
) RETURNS TABLE(...) AS $$
-- Layer 1: identity fast path (score 1000, early exit)
-- Layer 2: works FTS
-- Layer 3: content FTS (websearch → plainto → ILIKE)
-- Layer 4: vector similarity (if p_query_embedding provided)
-- Final: RRF rank fusion, dedup by work_id, top p_limit
$$ LANGUAGE plpgsql;
```

The caller (MCP server / API route) generates the query embedding before calling the RPC, so the DB function receives a ready `vector(1536)`. This avoids a round-trip.

---

## API Design

### Public REST API — all Zod-validated, cursor-paginated, OpenAPI-documented

```
GET /api/v1/search
  Validates: q (required), sector, type, year_from, year_to, status, limit (1-50)
  Returns: { query, total, results: [...], query_embedding_used: bool }

GET /api/v1/regulations
  Validates: sector, type, year, status, cursor, per_page (1-100)
  Returns: { total, next_cursor, regulations: [...] }

GET /api/v1/regulations/[...frbr]
  Returns: { work, nodes: [...] }

GET /api/v1/sectors
  Returns from materialized view mv_sector_stats — no live DB hit
  Cache-Control: public, max-age=900, stale-while-revalidate=3600

GET /api/v1/compliance
  ?sector=&business_type=
  Returns: { sector, business_type, required: [...] }

POST /api/suggestions
  Validates: work_id, node_id, current_content, suggested_content, reason, email?
  Rate limited: 10/IP/hour (Upstash)

GET /api/openapi.json
  Auto-generated OpenAPI 3.1 spec from Zod schemas
  Powers /api-docs page (Swagger UI)
```

### Cursor pagination

```typescript
// Encode cursor
const cursor = Buffer.from(JSON.stringify({ year: work.year, id: work.id })).toString("base64url")

// Decode and query
const { year, id } = JSON.parse(Buffer.from(cursor, "base64url").toString())
const query = sb.from("works").select("*")
  .or(`year.lt.${year},and(year.eq.${year},id.lt.${id})`)
  .order("year", { ascending: false })
  .order("id", { ascending: false })
  .limit(per_page)
```

### Admin API (`/api/admin/`) — Service role, `requireAdmin()` enforced

```
GET  /api/admin/suggestions
POST /api/admin/suggestions/[id]/apply
POST /api/admin/suggestions/[id]/reject
POST /api/admin/suggestions/[id]/verify
GET  /api/admin/compliance                  — List compliance_mappings
POST /api/admin/compliance                  — Add mapping
DELETE /api/admin/compliance/[id]           — Remove mapping
GET  /api/admin/scraper/stats
POST /api/admin/scraper/trigger
GET  /api/admin/analytics                   — Zero-result queries, top searches
POST /api/admin/revalidate                  — ISR revalidation by slug
```

---

## Authentication & Authorization

```
Public users: No auth. Anon key. RLS: read on works, document_nodes, abstracts, faqs, etc.
Suggestions: Anonymous POST. Rate limited 10/IP/hour. No account required.

Admin:
  /admin/* page
    → requireAdmin() [admin-auth.ts]
      → supabase.auth.getUser()     ← JWT from cookie
        → email in ADMIN_EMAILS env var?
          ✓ proceed  |  ✗ redirect /admin/login

Admin API routes: createServiceClient() (service role). Never in Server Components or browser.
Middleware: i18n routing only. Does NOT protect routes. Auth is per-page/route.
```

---

## Deployment

### Web App (Vercel)
- Auto-deploys from `main` push
- Root directory: `apps/web`
- Required env: Supabase (anon), Upstash Redis, Sentry DSN, Admin emails, Plausible domain
- `@vercel/otel` auto-instruments without config

### MCP Server (Railway)
- Dockerfile: `apps/mcp-server/Dockerfile`
- Transport: `streamable-http` on `$PORT`
- No trailing slash on `/mcp` — 307 redirect breaks Claude Code HTTP transport
- Required env: Supabase (anon), Upstash Redis, Sentry DSN

### Database (Supabase)
- Region: Singapore (ap-southeast-1)
- Extensions: `pg_trgm`, `unaccent`, `vector`, `pg_cron`
- App connections via PgBouncer (port 6543, transaction mode)
- Migrations via direct connection (port 5432)
- Migrations tested in CI before production apply

### Data Pipeline (Railway)
- Command: `python -m scripts.worker.run continuous --discovery-first`
- Separate Railway service from MCP server
- Required env: Supabase (service role), Gemini, OpenAI (for embeddings), Sentry

### Redis (Upstash)
- Single Upstash database — global, serverless
- Used by: web app (rate limiting), MCP server (caching + rate limiting)
- No Redis client to manage — Upstash REST API

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Hybrid search (FTS + pgvector + RRF) | Keyword FTS alone misses synonyms and concept queries. Vector search alone misses exact article lookups. RRF fusion gives the best of both without a separate vector DB. |
| Upstash Redis (not in-memory) | In-memory rate limiting breaks with multiple Railway instances. Upstash is serverless, requires no cluster management, works from Edge functions. |
| Cursor pagination (not offset) | Offset pagination is O(N) on large tables and breaks under concurrent inserts. Cursor pagination is O(log N) and stable. |
| Zod on all inputs | Prevents a class of SQL injection and tsquery crashes. Structured validation errors improve debugging. |
| OpenAPI from Zod | Single source of truth — schema validates input AND generates API docs. No drift between docs and implementation. |
| PgBouncer for app connections | OJK corpus will reach ~5M document nodes. Direct connections exhaust Postgres max_connections under concurrent search load. |
| Materialized views for stats | `COUNT(*) GROUP BY sector` on a 5M-row table is expensive. Materialized view is O(1) read, 15-min refresh lag is acceptable for landing page stats. |
| Embedding generation as pipeline step | Real-time embedding on ingest would serialize the pipeline. Batch generation is 10× cheaper via OpenAI batch API and doesn't block regulation availability. |
| Quality scorer on extraction | Silent bad extractions corrupt search. Better to flag and review than to pollute the index with garbled text. |
| `compliance_mappings` curated (not auto) | Auto-extraction of compliance requirements is legally risky — a missed requirement is a liability. Start curated, high quality over completeness. |
| `search_analytics` table | Zero-result queries are the most honest signal for what content is missing. Log them, read them weekly. |

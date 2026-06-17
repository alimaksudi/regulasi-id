# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                            │
│  Browser → Next.js Web App (Vercel / regulasi.id)              │
│  Claude Desktop/Code → MCP Server (Railway)                     │
│  3rd-party developers → REST API (/api/v1/)                    │
└─────────────────────────────────────────────────────────────────┘
               │                        │
               ▼                        ▼
┌──────────────────────┐  ┌─────────────────────────────────────┐
│  Next.js Web App     │  │  FastMCP Server (Python)            │
│  Vercel              │  │  Railway                            │
│  ISR + SSR + Edge    │  │  6 tools (search, get, list, etc.) │
└──────────────────────┘  └─────────────────────────────────────┘
               │                        │
               └──────────┬─────────────┘
                          ▼
           ┌──────────────────────────────────┐
           │       Supabase (PostgreSQL)      │
           │  - sectors, regulation_types     │
           │  - works, document_nodes         │
           │  - abstracts, faqs               │
           │  - work_relationships            │
           │  - revisions, suggestions        │
           │  - search_regulations() RPC      │
           │  - Supabase Auth (admin only)    │
           │  - Supabase Storage (PDFs)       │
           └──────────────────────────────────┘
                          │
           ┌──────────────▼───────────────────┐
           │     Data Pipeline (Python)       │
           │  jdih.ojk.go.id                 │
           │  ↓ crawler (listing + detail)   │
           │  ↓ PDF download                 │
           │  ↓ parser (PyMuPDF)             │
           │  ↓ loader (Supabase)            │
           └──────────────────────────────────┘
```

---

## Component Detail

### 1. Next.js Web App (`apps/web/`)

**Rendering strategy:**
- Server Components by default — direct Supabase queries, no useEffect
- ISR (Incremental Static Regeneration) on regulation pages (24h TTL)
- `"use client"` only for interactive elements (search bar, correction form, share button)

**Page structure:**
```
app/
├── layout.tsx                    — Root: fonts, global CSS, lang attr
├── [locale]/
│   ├── layout.tsx                — Locale: title template, OG metadata
│   ├── page.tsx                  — Landing (ISR 1h)
│   ├── search/page.tsx           — Search results (dynamic, noindex)
│   ├── regulasi/[type]/[slug]/   — Regulation reader (ISR 24h)
│   │   └── koreksi/[nodeId]/     — Correction form (client)
│   ├── sektor/[sector]/          — Browse by sector
│   ├── jenis/[type]/             — Browse by regulation type
│   ├── connect/page.tsx          — MCP setup guide
│   └── api-docs/page.tsx         — API documentation
└── admin/                        — Admin dashboard (no locale, auth-gated)
    ├── login/
    ├── suggestions/
    ├── regulasi/
    └── scraper/
```

**Three Supabase clients:**
| File | Context | Key |
|------|---------|-----|
| `lib/supabase/server.ts` | Server Components + Route Handlers | Anon (respects RLS) |
| `lib/supabase/client.ts` | Client Components | Anon (browser) |
| `lib/supabase/service.ts` | Admin API routes only | Service role (bypasses RLS) |

---

### 2. MCP Server (`apps/mcp-server/server.py`)

Single-file Python FastMCP server. Stateless — no user sessions. Regulation type codes cached in-memory on first call. All tools enforce `SUPABASE_ANON_KEY` at startup.

**Tools:**
```
search_regulations(query, sector?, regulation_type?, year_from?, year_to?, status?, limit?)
  → Calls search_regulations() Supabase RPC
  → Returns: [{ title, frbr_uri, type, sector, year, pasal, snippet, status, score }]

get_article(regulation_type, number, year, article_number)
  → Direct lookup: works → document_nodes (pasal) → document_nodes (ayat children)
  → Returns: { title, frbr_uri, pasal, content, ayat, cross_references, status }
  → Cached 1h per (type, number, year, article)

get_regulation_status(regulation_type, number, year)
  → Lookup work + work_relationships with relationship_types join
  → Returns: { title, status, explanation, amendments, implemented_by, related }
  → Cached 1h per regulation

get_compliance_checklist(sector, business_type?)
  → Queries compliance_mappings + works JOIN sectors
  → Returns: { sector, business_type, required_regulations: [{ pojk, seojk[], description, priority }] }

list_regulations(sector?, regulation_type?, year?, status?, search?, page?, per_page?)
  → Filtered, paginated works query
  → Returns: { total, page, per_page, regulations: [...] }

ping()
  → Health check with works count
```

**Rate limits:** 30/min for search/list, 60/min for get, no limit for ping.
**Caches:** TTL 1h for get_article and get_regulation_status, 5min for works count.

---

### 3. Data Pipeline (`scripts/`)

**Job state machine:**
```
pending → crawling → downloaded → parsed → loaded
                               ↘ failed (stored with error message)
```

**Pipeline flow per job:**
```
jdih.ojk.go.id/Web/ViewPeraturan/Index?sektor=X&jenisPeraturan=Y
  ↓ discover.py — crawl listing pages → seed crawl_jobs
jdih.ojk.go.id/web/ViewPeraturan/Detail/{uuid}/00/00
  ↓ process.py — scrape detail page → extract metadata + download UUIDs
jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/{uuid}
  ↓ Download main PDF + abstract PDF + FAQ PDF (if present)
  ↓ upload to Supabase Storage (regulation-pdfs bucket)
  ↓ parser/extract_pymupdf.py — text extraction (born-digital, no OCR)
  ↓ parser/parse_structure.py — regex state machine → node tree (BAB/Pasal/Ayat)
  ↓ loader/load_to_supabase.py — upsert works + document_nodes
  ↓ loader/load_abstract.py — upsert abstract text into abstracts table
  ↓ loader/load_faq.py — upsert FAQ text into faqs table
crawl_jobs status → loaded
```

**Concurrency:** Jobs claimed atomically via `claim_jobs()` SQL function (`FOR UPDATE SKIP LOCKED`). Stuck jobs (> 15 min in `crawling`) auto-recovered.

---

## Database Schema

### Entity Relationship

```
sectors (1) ──────────────────── (*) works
regulation_types (1) ────────── (*) works
works (1) ─────────────────────── (*) document_nodes
works (1) ─────────────────────── (0/1) abstracts
works (1) ─────────────────────── (0/1) faqs
works (*) ──── work_relationships ──── (*) works
document_nodes (1) ──────────── (*) revisions
document_nodes (1) ──────────── (*) suggestions
```

### Key table shapes

**`works`**
```sql
id                    SERIAL PRIMARY KEY
sector_id             INTEGER REFERENCES sectors(id)
regulation_type_id    INTEGER REFERENCES regulation_types(id)
frbr_uri              TEXT UNIQUE          -- /akn/id/act/pojk/2022/10
slug                  TEXT UNIQUE          -- pojk-10-2022 (auto-generated)
title_id              TEXT                 -- Full Indonesian title
number                TEXT                 -- "10" (not integer — can be "10/P1")
year                  INTEGER
status                TEXT                 -- berlaku | diubah | dicabut
date_enacted          DATE
source_url            TEXT                 -- jdih.ojk.go.id detail page URL
source_pdf_url        TEXT                 -- Supabase Storage URL
content_verified      BOOLEAN DEFAULT false
search_text           TEXT                 -- denormalized for FTS
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
pdf_page_end          INTEGER
fts                   TSVECTOR GENERATED ALWAYS AS (to_tsvector('indonesian', COALESCE(content_text,''))) STORED
```

**`abstracts`**
```sql
id                    SERIAL PRIMARY KEY
work_id               INTEGER REFERENCES works(id) UNIQUE
content_text          TEXT
source_pdf_url        TEXT
created_at            TIMESTAMPTZ DEFAULT NOW()
```

**`faqs`**
```sql
id                    SERIAL PRIMARY KEY
work_id               INTEGER REFERENCES works(id) UNIQUE
content_text          TEXT  -- structured Q&A text
source_pdf_url        TEXT
created_at            TIMESTAMPTZ DEFAULT NOW()
```

**`compliance_mappings`**
```sql
id                    SERIAL PRIMARY KEY
sector_id             INTEGER REFERENCES sectors(id)
business_type         TEXT  -- 'p2p-lending' | 'digital-bank' | 'insurance' | null (applies to all)
work_id               INTEGER REFERENCES works(id)
priority              TEXT  -- 'required' | 'recommended' | 'conditional'
notes                 TEXT  -- Human-readable notes about why this applies
```

---

## API Design

### Public REST API (`/api/v1/`)

All public endpoints have CORS enabled and in-memory rate limiting (60/min per IP).

```
GET /api/v1/search
  ?q=            required — search query in Indonesian
  &sector=       filter: perbankan, pasar-modal, fintech, iknb, dana-pensiun, perasuransian
  &type=         filter: POJK, SEOJK, KEOJK (multi-value: POJK,SEOJK)
  &year=         exact year match
  &year_from=    range lower bound
  &status=       berlaku | diubah | dicabut (multi-value)
  &limit=        1–50 (default 10)
Response: { query, total, results: [{ work_id, snippet, score, matching_pasals, work }] }

GET /api/v1/regulations
  ?sector=&type=&year=&status=&page=&per_page=
Response: { total, page, per_page, regulations: [...] }

GET /api/v1/regulations/[...frbr]
  # e.g. /api/v1/regulations/akn/id/act/pojk/2022/10
Response: { work, nodes: [...] }

GET /api/v1/sectors
Response: { sectors: [{ code, name_id, name_en, regulation_count }] }

POST /api/suggestions
  Body: { work_id, node_id, current_content, suggested_content, reason, email? }
  Rate limited: 10/IP/hour
Response: { id, status: 'pending' }
```

### Admin API (`/api/admin/`) — Auth required

```
GET  /api/admin/suggestions          — List pending suggestions
POST /api/admin/approve-suggestion   — Approve + apply revision
POST /api/admin/reject-suggestion    — Reject with note
POST /api/admin/verify-suggestion    — Trigger Gemini AI verification
GET  /api/admin/scraper/stats        — Pipeline stats
POST /api/admin/scraper/trigger      — Manually trigger scraper run
POST /api/admin/revalidate           — ISR revalidation
```

---

## Authentication & Authorization

**Public users:** No auth. Supabase anon key. RLS allows public read on `works`, `document_nodes`, `abstracts`, `faqs`, `work_relationships`, `sectors`, `regulation_types`.

**Corrections:** Anonymous POST to `/api/suggestions`. Rate limited 10/IP/hour. No account required.

**Admin:**
```
Admin → /admin/* page
  → requireAdmin() [admin-auth.ts]
    → supabase.auth.getUser()     ← JWT from cookie
      → check email in ADMIN_EMAILS env var
        ✓ proceed  |  ✗ redirect /admin/login
```

Admin API routes use `createServiceClient()` (service role key). Never used in Server Components or browser code.

Middleware (`middleware.ts`) handles i18n only — does NOT protect routes. Auth is per-page/route.

---

## Deployment

### Web App (Vercel)
- Auto-deploys from `main` push
- Root directory in Vercel: `apps/web`
- CLI: `vercel link --project regulasi-id-web --yes` (from monorepo root), then `vercel --prod --yes`
- Custom domain: `regulasi.id`

### MCP Server (Railway)
- Dockerfile: `apps/mcp-server/Dockerfile` (`python:3.12-slim`)
- Transport: `streamable-http` on `$PORT`
- No trailing slash on `/mcp` endpoint — 307 redirect breaks Claude Code HTTP transport

### Database (Supabase)
- Region: Singapore (ap-southeast-1) — closest to Indonesia
- Extensions required: `pg_trgm`, `unaccent`
- Migrations: applied via Supabase SQL Editor in sequence

### Data Pipeline (Railway)
- Dockerfile: `scripts/worker/Dockerfile`
- Command: `python -m scripts.worker.run continuous --discovery-first`

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| No vector search | Keyword FTS with Indonesian stemming is sufficient for exact regulation lookup. Add pgvector in v2 if needed. |
| PyMuPDF not OCR | OJK PDFs post-2013 are born-digital. OCR adds complexity without benefit for target corpus. |
| Abstracts + FAQs as separate tables | OJK provides these as separate documents per POJK. Useful for compliance context independently from full regulation text. |
| `compliance_mappings` as curated table | Auto-extraction of "what regulations apply to me" is hard to get right. Start with manually curated, high-quality mappings. |
| Per-process MCP rate limiting | Sufficient for initial Railway single-instance deploy. Add Redis if scaling to multiple instances. |
| Admin email allowlist in env | Safe for open-source. No admin user management UI needed for MVP. |

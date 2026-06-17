# Architecture

## System Overview

```
┌───────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                 │
│  Browser → TanStack Start Web App (Vercel / regulasi.id)                 │
│  Claude Desktop/Code → MCP Server (Railway)                               │
│  3rd-party developers → REST API (api.regulasi.id) + OpenAPI spec        │
└───────────────────────────────────────────────────────────────────────────┘
                 │                           │
                 ▼                           ▼
┌──────────────────────────┐   ┌──────────────────────────────────────────┐
│   TanStack Start         │   │   Hono.js API                           │
│   (Vite SSR + React 19)  │   │   Cloudflare Workers                    │
│   Vercel                 │   │   api.regulasi.id                       │
│                          │   │                                          │
│   shadcn/ui components   │   │   POST /api/v1/search                   │
│   Lucide icons           │   │     → generate embedding (OpenAI)       │
│   TanStack Router        │   │     → call search_regulations() RPC     │
│   TanStack Query         │   │   GET  /api/v1/regulations              │
│   Zustand (client state) │   │   GET  /api/v1/sectors                  │
│   React Hook Form + Zod  │   │   GET  /api/v1/compliance               │
│   Sentry + Plausible     │   │   POST /api/suggestions                 │
│   createServerFn() → SSR │   │   /api/admin/* (auth-gated)             │
└──────────────────────────┘   │                                          │
          │                    │   Zod validation on every route          │
          │                    │   Upstash rate limiting                  │
          │                    │   Sentry error capture                   │
          │                    └──────────────────────────────────────────┘
          │                                  │
          └──────────────────┬───────────────┘
                             ▼
        ┌────────────────────────────────────────────┐
        │         Upstash Redis (global edge)        │
        │  Rate limiting (web + API + MCP)           │
        │  Cache (search results, article text)      │
        └────────────────────────────────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────────┐
        │          Supabase (PostgreSQL)             │
        │  PgBouncer port 6543 — app connections     │
        │  Direct port 5432 — migrations only        │
        │                                            │
        │  works (search_fts TSVECTOR)               │
        │  document_nodes (fts TSVECTOR +            │
        │                  embedding vector(1536))   │
        │  abstracts, faqs, work_relationships       │
        │  revisions (append-only), suggestions      │
        │  compliance_mappings, crawl_jobs           │
        │  search_analytics                          │
        │  mv_sector_stats (materialized, 15min)     │
        │                                            │
        │  search_regulations() — 4-layer hybrid     │
        │  apply_revision(), claim_jobs()            │
        │  Supabase Auth (admin only)                │
        │  Supabase Storage (PDFs)                   │
        └────────────────────────────────────────────┘
                             │
        ┌────────────────────▼───────────────────────┐
        │         Data Pipeline (Python)             │
        │  async workers (asyncio.gather, sem=5)     │
        │  jdih.ojk.go.id crawler                   │
        │  PyMuPDF parser + quality scorer           │
        │  OpenAI batch embedding generator          │
        │  Supabase loader (breadth-first)           │
        │  Exponential backoff (5m→30m→2h→8h→dead)  │
        │  Change detection (skip unchanged PDFs)    │
        └────────────────────────────────────────────┘
                             │
        ┌────────────────────▼───────────────────────┐
        │  FastMCP Server (Python) — Railway         │
        │  search_regulations, get_article           │
        │  get_regulation_status                     │
        │  get_compliance_checklist                  │
        │  list_regulations, ping                    │
        │  Upstash Redis (cache + rate limiting)     │
        └────────────────────────────────────────────┘
```

---

## Component Detail

### 1. TanStack Start Web App (`apps/web/`)

**Why TanStack Start:** Vite-native framework with SSR. Full control over the stack — no Next.js opinions. Regulation detail pages are SSR-rendered and cached at the CDN edge for SEO. Search is server-rendered on first load, then client-side with TanStack Query.

**Rendering strategy:**

| Page | Strategy |
|------|---------|
| Landing (`/`) | SSR + CDN cache 1h |
| Search (`/search?q=...`) | SSR (first render) + TanStack Query (subsequent searches) |
| Regulation detail (`/regulasi/pojk/pojk-10-2022`) | SSR + CDN cache 24h, revalidated on deploy |
| Sector browse (`/sektor/fintech`) | SSR + CDN cache 1h |
| Admin pages | Client-side only (auth-gated, no public cache) |

**Route structure:**
```
app/routes/
├── __root.tsx              — Root: fonts, meta tags, Sentry init, Plausible script
├── index.tsx               — Landing page
├── search.tsx              — Search (q, sector, type, year, status as typed URL params)
├── regulasi/
│   └── $type.$slug.tsx     — Regulation reader
│       └── koreksi/
│           └── $nodeId.tsx — Correction form
├── sektor/
│   └── $sector.tsx         — Browse by sector
├── jenis/
│   └── $type.tsx           — Browse by regulation type
├── connect.tsx             — MCP setup guide
└── admin/
    ├── __layout.tsx        — Auth check: redirect to /admin/login if no session
    ├── index.tsx           — Dashboard (counts, zero-result queries, recent suggestions)
    ├── suggestions.tsx     — Suggestion queue
    ├── compliance.tsx      — Compliance mappings CRUD
    ├── scraper.tsx         — Crawl job queue + stats
    └── analytics.tsx       — Search analytics
```

**Data fetching patterns:**

```typescript
// SSR: server function in loader (runs on server at request time)
const getRegulationFn = createServerFn({ method: "GET" })
  .validator(z.object({ slug: z.string() }))
  .handler(async ({ data }) => {
    const sb = createSupabaseServerClient()
    return sb.from("works").select("*").eq("slug", data.slug).single()
  })

export const Route = createFileRoute("/regulasi/$type/$slug")({
  loader: ({ params }) => getRegulationFn({ data: { slug: params.slug } }),
})

// Client-side: TanStack Query for live search
const { data } = useQuery({
  queryKey: ["search", query, filters],
  queryFn: () => apiClient.search({ q: query, ...filters }),
  staleTime: 60_000,
  placeholderData: keepPreviousData,
})
```

**Component library:**

shadcn/ui as the base — all components in `app/components/ui/`. Custom components in `app/components/`. Naming conventions:
- `app/components/ui/Button.tsx` — shadcn primitive (generated by CLI, can be modified)
- `app/components/RegulationCard.tsx` — domain component built on top of shadcn
- `app/components/SearchBar.tsx` — feature component

Icons: Lucide React. `import { Search, FileText, ChevronRight } from "lucide-react"`. Never use other icon libraries.

**State management:**

| State type | Tool |
|-----------|------|
| Server data | TanStack Query (`useQuery`, `useMutation`) |
| URL state | TanStack Router (`useSearch`, `useNavigate`) |
| Client-only UI state | Zustand store |
| Form state | React Hook Form + Zod |

---

### 2. Hono.js API (`apps/api/`)

Deployed to Cloudflare Workers. Runs at the edge globally — < 50ms cold start.

**Why Cloudflare Workers instead of Next.js API routes:**
- Near-zero cold start (V8 isolates, not containers)
- Globally distributed — regulation queries from Jakarta hit a nearby Workers edge node
- Handles the server-side secret operations: OpenAI API calls for embeddings, service role Supabase for admin
- Decoupled from the frontend framework — can be evolved independently

**Route structure:**
```
POST /api/v1/search              — hybrid search (generates embedding server-side)
GET  /api/v1/regulations         — list with cursor pagination
GET  /api/v1/regulations/:frbr   — single regulation with nodes
GET  /api/v1/sectors             — from mv_sector_stats (Upstash cached 15min)
GET  /api/v1/compliance          — compliance checklist by sector + business_type
POST /api/suggestions            — submit correction (rate limited 10/IP/hour)
GET  /api/openapi.json           — OpenAPI 3.1 spec
GET  /admin/*                    — admin operations (JWT auth required)
```

**Request lifecycle:**
```
Request → CORS middleware → Rate limiter (Upstash) → Zod validator → Handler → Sentry (on error) → Response
```

**Wrangler config (`wrangler.toml`):**
```toml
name = "regulasi-id-api"
main = "src/index.ts"
compatibility_date = "2025-06-01"
compatibility_flags = ["nodejs_compat"]

[vars]
ENVIRONMENT = "production"

# Secrets (via wrangler secret put):
# SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY
# OPENAI_API_KEY, UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN
# SENTRY_DSN, ADMIN_JWT_SECRET
```

---

### 3. MCP Server (`apps/mcp-server/server.py`)

FastMCP Python server on Railway. Full details in `docs/MCP.md`. Tools:

```
search_regulations(query, sector?, type?, year_from?, year_to?, status?, limit?)
get_article(regulation_type, number, year, article_number)
get_regulation_status(regulation_type, number, year)
get_compliance_checklist(sector, business_type?)
list_regulations(sector?, type?, year?, status?, cursor?, per_page?)
ping()
```

Rate limiting and caching via Upstash Redis — cross-instance safe.

---

### 4. Data Pipeline (`scripts/`)

Async parallel workers. Full details in `docs/SCRAPER.md`.

Key points:
- `asyncio.gather` with `Semaphore(5)` for concurrent PDF downloads
- Exponential backoff: 5min → 30min → 2h → 8h → dead
- Change detection: skip unchanged regulations
- Quality scorer: flag extractions with score < 0.3
- Embedding generation: separate pass, batch 100 nodes/OpenAI call

---

## Database ER

```
sectors (1) ──────────── (*) works
regulation_types (1) ─── (*) works
works (1) ──────────────── (*) document_nodes  [embedding vector(1536)]
works (1) ──────────────── (0/1) abstracts
works (1) ──────────────── (0/1) faqs
works (*) ─── work_relationships ─── (*) works
document_nodes (1) ──────── (*) revisions      [append-only]
document_nodes (1) ──────── (*) suggestions
sectors + works ──── compliance_mappings
works ────────────── crawl_jobs
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| TanStack Start over Next.js | Vite-native = faster dev iteration. Same SSR capability. No framework lock-in on data fetching (bring your own: TanStack Query). Cleaner mental model — `createServerFn` is explicit, not magic. |
| Hono on Cloudflare Workers | Near-zero cold start vs Lambda's 200ms+. Global edge — Indonesian users hit Singapore or Asia nodes. Secrets never touch the browser. Workers are cheaper than Lambda at scale. |
| Hybrid search (FTS + pgvector + RRF) | Keyword FTS misses synonyms ("kredit konsumtif" ≠ "kredit tanpa agunan"). Vector alone misses exact article lookups. RRF fusion gives the best of both without a separate vector DB. |
| Upstash Redis | Serverless Redis compatible with Cloudflare Workers (REST API). Shared rate limiting and cache across web + API + MCP — single source of truth. |
| Cursor pagination | Offset is O(N) scan on large tables. Cursor is O(log N). More importantly, offset pages go stale when new rows are inserted — cursor doesn't. |
| Zod shared schemas | `packages/shared/schemas/` — same Zod schema validates API input (Hono) AND generates TypeScript types for the frontend client. Single source of truth. |
| Materialized views for stats | `COUNT(*) GROUP BY sector` on a 5M-row table is expensive. Materialized view = O(1) read at query time, 15-min refresh lag is acceptable for landing page. |
| Quality scorer on extraction | Silent bad extractions corrupt search index. Better to flag and review than load garbled text. |
| Compliance mappings curated | Auto-extracting "what applies to my business" is legally risky. A missed required regulation is a liability. Start curated, high quality over completeness. |
| `search_analytics` table | Zero-result queries are the most honest product signal. Log every query. Read weekly. |

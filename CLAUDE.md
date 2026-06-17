# CLAUDE.md

regulasi-id — Open, AI-native Indonesian financial regulatory platform. MCP server + web app giving Claude grounded access to OJK (Otoritas Jasa Keuangan) regulations. Production-grade: hybrid search, distributed caching, full observability.

**Repo:** `alimaksudi/regulasi-id` | **Live:** https://regulasi.id (planned) | **MCP:** Railway (planned)

---

## Architecture

Monorepo with four main pieces:

| Component | Path | Tech |
|-----------|------|------|
| Web app | `apps/web/` | TanStack Start (Vite, SSR), React 19, TypeScript, Tailwind v4, shadcn/ui, Lucide, TanStack Query |
| API server | `apps/api/` | Hono.js on Cloudflare Workers — search, suggestions, admin endpoints |
| MCP server | `apps/mcp-server/` | Python 3.12+, FastMCP, supabase-py, Upstash Redis |
| Data pipeline | `scripts/` | Python — crawler, parser (PyMuPDF), async loader, Gemini verification |
| Database | `packages/supabase/migrations/` | Supabase (PostgreSQL + pgvector + PgBouncer) |

### Key directories

```
apps/web/
├── app/
│   ├── routes/
│   │   ├── __root.tsx              — Root layout: fonts, global CSS, Sentry, Plausible
│   │   ├── index.tsx               — Landing page (SSR, ISR-like via CDN cache)
│   │   ├── search.tsx              — Search results (SSR)
│   │   ├── regulasi/
│   │   │   └── $type.$slug.tsx     — Regulation detail (SSR + CDN cache 24h)
│   │   ├── sektor/
│   │   │   └── $sector.tsx         — Browse by sector (SSR)
│   │   ├── connect.tsx             — MCP setup guide
│   │   └── admin/
│   │       ├── __layout.tsx        — Admin layout (auth-gated)
│   │       ├── index.tsx           — Dashboard
│   │       ├── suggestions.tsx     — Suggestion queue
│   │       ├── compliance.tsx      — Compliance mappings
│   │       └── scraper.tsx         — Crawl job queue
│   ├── components/                 — React components (PascalCase.tsx, shadcn + custom)
│   ├── lib/
│   │   ├── supabase.ts             — Supabase browser client (anon key)
│   │   ├── api.ts                  — Typed Hono API client
│   │   ├── schemas/                — Zod schemas shared with API
│   │   └── i18n.ts                 — i18n setup (next-intl or custom)
│   ├── hooks/                      — Custom React hooks
│   └── styles/
│       └── globals.css             — Tailwind v4 + CSS custom properties
├── app.config.ts                   — TanStack Start / Vite config
├── package.json
└── tsconfig.json

apps/api/
├── src/
│   ├── index.ts                    — Hono entry point, route registration
│   ├── routes/
│   │   ├── search.ts               — POST /api/v1/search (hybrid: FTS + embeddings)
│   │   ├── regulations.ts          — GET /api/v1/regulations, /api/v1/regulations/:frbr
│   │   ├── sectors.ts              — GET /api/v1/sectors
│   │   ├── compliance.ts           — GET /api/v1/compliance
│   │   ├── suggestions.ts          — POST /api/suggestions
│   │   └── admin/                  — Admin API routes (auth-gated)
│   ├── middleware/
│   │   ├── ratelimit.ts            — Upstash rate limiter
│   │   ├── auth.ts                 — Admin JWT verification
│   │   └── cors.ts                 — CORS headers
│   └── lib/
│       ├── supabase.ts             — Supabase client (service role for admin)
│       ├── embeddings.ts           — OpenAI embedding generation
│       └── cache.ts                — Upstash cache helpers
├── wrangler.toml                   — Cloudflare Workers config
└── package.json

apps/mcp-server/server.py           — MCP: search_regulations, get_article, get_regulation_status, get_compliance_checklist, list_regulations
scripts/crawler/                    — jdih.ojk.go.id scraper
scripts/parser/                     — PDF parsing (PyMuPDF) + quality scorer
scripts/worker/                     — Orchestration CLI (discover, process, continuous)
scripts/embeddings/                 — Embedding generation for pgvector
scripts/agent/                      — Gemini verification agent
packages/supabase/migrations/       — SQL migrations (NNN_description.sql)
```

---

## Commands

```bash
# Web app (from apps/web/)
npm run dev          # Vite dev server with SSR (port 3000)
npm run build        # Production build (SSR + static assets)
npm run preview      # Preview production build locally
npm run lint         # ESLint
npm run test         # Vitest watch
npm run test:run     # Vitest single run (CI)
npm run test:e2e     # Playwright E2E

# API server (from apps/api/)
npm run dev          # Wrangler dev server (port 8787)
npm run deploy       # Deploy to Cloudflare Workers
npm run test         # Vitest for Cloudflare Workers

# MCP server (from apps/mcp-server/)
python server.py     # Start MCP server (port 8000)

# Data pipeline (from project root)
python -m scripts.worker.run discover --sectors perbankan,fintech
python -m scripts.worker.run process --batch-size 20 --concurrency 5
python -m scripts.worker.run embed --batch-size 100
python -m scripts.worker.run stats
```

---

## Database Schema

All tables have RLS enabled with public read policies.

### Core tables

| Table | Purpose |
|-------|---------|
| `sectors` | OJK sectors (perbankan, pasar-modal, iknb, fintech, dana-pensiun, perasuransian) |
| `regulation_types` | POJK, SEOJK, KEOJK, UU, PP, PERPRES with hierarchy levels |
| `works` | Regulations. `search_fts` TSVECTOR GENERATED ALWAYS |
| `document_nodes` | BAB > Bagian > Pasal > Ayat. `fts` TSVECTOR + `embedding vector(1536)` |
| `abstracts` | OJK abstract PDFs (one per POJK) |
| `faqs` | OJK FAQ PDFs (one per POJK where available) |
| `revisions` | **Append-only** audit log. Never UPDATE or DELETE |
| `suggestions` | Crowd-sourced corrections — anyone submits, admin approves |
| `work_relationships` | Cross-references (mengubah, mencabut, melaksanakan, etc.) |
| `compliance_mappings` | Curated: sector + business_type → applicable works |
| `crawl_jobs` | Scraper queue: pending → crawling → downloaded → parsed → loaded / failed |
| `discovery_progress` | Crawl freshness cache |
| `search_analytics` | Query log — zero-result queries drive content backlog |

### Critical invariant: content mutations

**Never UPDATE `document_nodes.content_text` directly.** Always use `apply_revision()`:
1. INSERT into `revisions` (old + new content, reason, actor)
2. UPDATE `document_nodes.content_text` (sets `embedding = NULL` — triggers regen)
3. UPDATE `suggestions.status` if triggered by a suggestion

All in one transaction.

### Search: `search_regulations()` — hybrid

4-layer search with RRF reranking:
- **Layer 1:** Identity fast path — regulation identifiers ("POJK 10 2022"), score 1000, early exit
- **Layer 2:** Works FTS — `works.search_fts` TSVECTOR, score 1–15
- **Layer 3:** Content FTS — `document_nodes.fts` (websearch → plainto → ILIKE), score 0.01–0.5
- **Layer 4:** Semantic — cosine similarity on `document_nodes.embedding` (pgvector), score 0–1

The API server generates the query embedding before calling the RPC — one round-trip.

---

## Coding Conventions

### TypeScript / TanStack Start

- **Server functions for SSR data.** Use `createServerFn()` to fetch data on the server — not `useEffect`. Runs at request time (or CDN cache hit).
- **TanStack Query for client data.** Use `useQuery()` for data that updates client-side (admin dashboard, search with live filters).
- **Type-safe routing.** Use `useNavigate`, `useSearch`, `useParams`, `Link` from `@tanstack/react-router` — never from `react-router-dom`.
- **Zod on server functions.** Validate all inputs to `createServerFn()` with Zod. Same schemas shared with Hono API via `packages/shared/schemas/`.
- **File naming:** `kebab-case.tsx` for routes, `PascalCase.tsx` for components.
- **Styling:** Tailwind utility classes only. Never inline styles or CSS modules.
- **Icons:** `lucide-react` exclusively. Size: `size={16}` (inline), `size={20}` (standalone), `size={24}` (hero).
- **UI components:** shadcn/ui as the base layer. Extend in `app/components/ui/`. Don't modify shadcn primitives — compose on top.
- **Admin auth:** Check Supabase session server-side in the admin layout server function. Redirect to `/admin/login` if unauthorized.
- **Error tracking:** `Sentry.captureException(err)` in all catch blocks.

```typescript
// Correct: server function for SSR data
import { createServerFn } from "@tanstack/start"
import { z } from "zod"

const getRegulationFn = createServerFn({ method: "GET" })
  .validator(z.object({ slug: z.string() }))
  .handler(async ({ data }) => {
    const sb = createSupabaseServerClient()
    const { data: work } = await sb
      .from("works")
      .select("*, regulation_types(*), sectors(*)")
      .eq("slug", data.slug)
      .single()
    return work
  })

// In route component
export const Route = createFileRoute("/regulasi/$type/$slug")({
  loader: ({ params }) => getRegulationFn({ data: { slug: params.slug } }),
  component: RegulationPage,
})

function RegulationPage() {
  const regulation = Route.useLoaderData()
  // ...
}
```

```typescript
// Correct: TanStack Query for client-side search
import { useQuery } from "@tanstack/react-query"
import { apiClient } from "~/lib/api"

function SearchResults({ query }: { query: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["search", query],
    queryFn: () => apiClient.search({ q: query }),
    staleTime: 60_000,
  })
  // ...
}
```

### Hono.js / Cloudflare Workers

- **Runtime:** Cloudflare Workers (V8 isolates). No Node.js APIs — use Web APIs only.
- **Validation:** `@hono/zod-validator` middleware on every route.
- **Rate limiting:** Upstash `@upstash/ratelimit` via REST API (Workers-compatible).
- **Supabase:** Use `@supabase/supabase-js` with the service role key in Workers bindings — never in frontend code.
- **Embeddings:** Call OpenAI API from Workers using `fetch()` — no SDK needed.
- **CORS:** Applied globally in middleware, not per-route.

```typescript
// apps/api/src/routes/search.ts
import { Hono } from "hono"
import { zValidator } from "@hono/zod-validator"
import { SearchSchema } from "../../packages/shared/schemas"
import { generateEmbedding } from "../lib/embeddings"
import { rateLimiter } from "../middleware/ratelimit"

const search = new Hono()

search.post("/",
  rateLimiter({ max: 60, window: "60s" }),
  zValidator("json", SearchSchema),
  async (c) => {
    const { q, sector, limit } = c.req.valid("json")
    const embedding = await generateEmbedding(q, c.env.OPENAI_API_KEY)
    const sb = createSupabaseClient(c.env)
    const { data } = await sb.rpc("search_regulations", {
      p_query: q,
      p_sector: sector ?? null,
      p_limit: limit,
      p_query_embedding: embedding,
    })
    return c.json({ query: q, results: data })
  }
)
```

### Python

- Python 3.12+. Type hints on all function signatures.
- `httpx` with async/await for HTTP. `asyncio.gather` for parallel downloads.
- PDF extraction: `pymupdf`. No OCR for post-2013 OJK PDFs.
- Embeddings: OpenAI batch API, 100 nodes per call max.
- Gemini agent: advisory only — admin must approve.
- Structured logging: `structlog` JSON logs (visible in Railway dashboard).

### SQL migrations

- Next number: always glob `packages/supabase/migrations/*.sql` first.
- RLS + public read policy on every new table.
- Indexes for all WHERE/JOIN/ORDER BY columns.
- pgvector columns: `hnsw` index with `vector_cosine_ops`.
- `CREATE OR REPLACE FUNCTION` always followed by `ALTER FUNCTION ... SET search_path = 'public', 'extensions'`.
- Migrations tested in CI against a test Supabase project before merging.
- App connects via PgBouncer (port 6543). Migrations via direct (port 5432).

---

## OJK JDIH Scraper

### URL patterns

```
Listing:  http://jdih.ojk.go.id/Web/ViewPeraturan/Index?sektor={code}&jenisPeraturan={code}
Detail:   http://jdih.ojk.go.id/web/ViewPeraturan/Detail/{uuid}/00/00
PDF:      http://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/{uuid}
```

### Sector codes

| Sector | jdih sektor | Reg type | jdih jenisPeraturan |
|--------|------------|----------|---------------------|
| Perbankan | 01 | POJK | 06 |
| Pasar Modal | 02 | SEOJK | 07 |
| IKNB | 08 | | |
| Fintech | 10 | | |

PDF quality: OJK post-2013 PDFs are born-digital. PyMuPDF extracts text directly — no OCR. Quality scored 0–1 after extraction; score < 0.3 flagged for admin review.

---

## Environment Variables

| File | Key vars |
|------|----------|
| `apps/web/.env.local` | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL` (Hono), `VITE_SENTRY_DSN`, `VITE_PLAUSIBLE_DOMAIN` |
| `apps/api/.dev.vars` | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `SENTRY_DSN`, `ADMIN_EMAILS` |
| `apps/api/wrangler.toml` | Non-secret config only (account_id, compatibility_date) |
| `apps/mcp-server/.env` | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `SENTRY_DSN` |
| `scripts/.env` | `SUPABASE_URL`, `SUPABASE_KEY` (service role), `GEMINI_API_KEY`, `OPENAI_API_KEY` |

Secrets in `apps/api` go in `.dev.vars` locally, Cloudflare Worker secrets in production (`wrangler secret put KEY`).

---

## Deployment

- **Web:** Vercel (TanStack Start SSR adapter for Vercel). Auto-deploys from `main`.
- **API:** Cloudflare Workers (`wrangler deploy`). Near-zero cold start, global edge.
- **MCP:** Railway (FastMCP Python, Dockerfile).
- **Database:** Supabase Singapore. PgBouncer for app connections.
- **Redis:** Upstash (serverless, global).

---

## Observability

| Tool | Coverage |
|------|---------|
| Sentry | Errors in web, API (Workers), MCP, pipeline |
| Plausible | Privacy-first product analytics (no cookies, GDPR-clean) |
| `@opentelemetry/api` | Traces on API routes (Cloudflare Workers OTEL exporter) |
| `search_analytics` table | Zero-result queries — product backlog |
| Cloudflare Analytics | Workers request volume, error rate, p99 duration |
| Railway logs | MCP server + pipeline worker (structlog JSON) |

---

## Domain Glossary

| Term | Meaning |
|------|---------|
| POJK | Peraturan OJK — primary OJK regulatory instrument |
| SEOJK | Surat Edaran OJK — technical/implementation circulars |
| Pasal | Article — primary searchable unit |
| Ayat | Sub-article (1), (2), (3) within a Pasal |
| BAB | Chapter — top-level grouping |
| OJK | Otoritas Jasa Keuangan — Indonesia's financial regulator |
| RRF | Reciprocal Rank Fusion — combines keyword + semantic search ranks |
| createServerFn | TanStack Start's SSR data-fetching primitive |

---

## Gotchas

- **Workers runtime ≠ Node.js.** No `fs`, `path`, `crypto` (use `crypto.subtle`), no `Buffer` (use `TextEncoder`). Test locally with `wrangler dev` not `ts-node`.
- **Workers cold start for pgvector.** The embedding round-trip (OpenAI API call) adds ~200ms to search. Cache the query embedding in Upstash by query hash to avoid redundant calls.
- **TanStack Start SSR hydration.** Data fetched in `loader` must be JSON-serializable — no Date objects, no class instances. Serialize to ISO string and deserialize in component.
- **TanStack Router type safety.** Use `z.object()` in `validateSearch` on routes that accept query params — otherwise TypeScript won't know the shape of `useSearch()`.
- **shadcn/ui with Vite.** Use `npx shadcn@latest init` with the Vite preset. Component files go in `app/components/ui/`. Don't use the Next.js preset.
- **Supabase browser client in SSR.** TanStack Start runs code on server and client. Use `createServerFn()` for server-only DB calls. Never import the service role client into any file that could be bundled for the browser.
- **Cloudflare Workers env bindings.** Secrets are accessed via `c.env.SECRET_NAME` in Hono, not `process.env`. Add to `.dev.vars` for local and `wrangler secret put` for production.
- **pgvector index type.** Use `hnsw` for best recall. `ivfflat` is faster to build but requires `ANALYZE` and has lower recall at index creation time.
- **Upstash Redis in Workers.** Use `@upstash/redis` with the REST API client — the TCP client doesn't work in Workers (no TCP sockets). Verified: REST client works from Workers.
- **RLS blocks empty results.** New table with no RLS policy returns `[]` silently — not an error.
- **`SUPABASE_KEY` = `SUPABASE_SERVICE_ROLE_KEY`.** Scripts env uses `SUPABASE_KEY` as shorthand. Same value. Never expose to browser.
- **Embedding regeneration after content change.** `apply_revision()` sets `embedding = NULL`. Background job regenerates. During the gap, semantic search for that node falls back to FTS. Acceptable trade-off.
- **Wrangler routes config.** The Hono API is deployed to `api.regulasi.id/*` (not `regulasi.id/api/*`). Web app at `regulasi.id/*`. Separate Workers — avoid proxying through the web app.

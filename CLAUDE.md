# CLAUDE.md

regulasi-id — Open, AI-native Indonesian financial regulatory platform. MCP server + web app giving Claude grounded access to OJK (Otoritas Jasa Keuangan) regulations.

**Repo:** `alimaksudi/regulasi-id` | **Live:** https://regulasi.id (planned) | **MCP:** Railway (planned)

---

## Architecture

Monorepo with three main pieces:

| Component | Path | Tech |
|-----------|------|------|
| Web app | `apps/web/` | Next.js (App Router), React 19, TypeScript, Tailwind v4, shadcn/ui |
| MCP server | `apps/mcp-server/` | Python 3.12+, FastMCP, supabase-py |
| Data pipeline | `scripts/` | Python — crawler (jdih.ojk.go.id), parser (PyMuPDF), loader, Gemini verification |
| Database | `packages/supabase/migrations/` | Supabase (PostgreSQL) |

### Key directories

```
apps/web/src/app/[locale]/       — Public pages (/, /search, /regulasi/[type]/[slug], /sektor/[sector])
apps/web/src/app/admin/          — Admin pages (NOT under [locale])
apps/web/src/components/         — React components (PascalCase.tsx)
apps/web/src/lib/                — Utilities, Supabase clients (server.ts, client.ts, service.ts)
apps/web/src/i18n/               — i18n config (routing.ts, request.ts)
apps/web/messages/               — Translation files (id.json, en.json)
apps/mcp-server/server.py        — MCP tools: search_regulations, get_article, get_regulation_status, get_compliance_checklist, list_regulations
scripts/crawler/                 — jdih.ojk.go.id scraper
scripts/parser/                  — PDF parsing (PyMuPDF)
scripts/worker/                  — Orchestration CLI (discover, process, continuous)
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
npm run test         # Vitest

# MCP server (from apps/mcp-server/)
python server.py     # Start MCP server (needs SUPABASE_URL + SUPABASE_ANON_KEY)

# Data pipeline (from project root)
python -m scripts.worker.run discover --sectors perbankan,fintech
python -m scripts.worker.run process --batch-size 20
python -m scripts.worker.run full --sectors perbankan
python -m scripts.worker.run continuous
python -m scripts.worker.run stats
```

Migrations are applied directly to Supabase via the SQL editor or `supabase db push` — not run locally.

---

## Database Schema

All tables have RLS enabled with public read policies for regulatory data.

### Core tables

| Table | Purpose |
|-------|---------|
| `sectors` | OJK regulatory sectors (perbankan, pasar-modal, iknb, fintech, dana-pensiun, perasuransian) |
| `regulation_types` | Regulation types: POJK, SEOJK, KEOJK, UU, PP, PERPRES, etc. with hierarchy levels |
| `works` | Individual regulations. Has `slug`, `sector_id`, `frbr_uri`, metadata, parse quality fields. `search_text` maintained by trigger, `search_fts` TSVECTOR GENERATED ALWAYS |
| `document_nodes` | Hierarchical document structure: BAB > Bagian > Pasal > Ayat. Content in `content_text`, `fts` TSVECTOR auto-generated |
| `abstracts` | Official OJK abstract documents (one per POJK). Downloaded from JDIH alongside the main PDF |
| `faqs` | Official OJK FAQ documents (one per POJK where available). Plain text, useful for compliance context |
| `revisions` | **Append-only** audit log for content changes. Never UPDATE or DELETE rows |
| `suggestions` | Crowd-sourced corrections. Anyone submits, admin approves |
| `work_relationships` | Cross-references between regulations (mengubah, mencabut, melaksanakan, etc.) |
| `crawl_jobs` | Scraper job queue. State machine: pending → crawling → downloaded → parsed → loaded / failed |
| `discovery_progress` | Crawl freshness cache per (sector, regulation_type) pair |

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
2. UPDATE `document_nodes.content_text` (FTS auto-updates via GENERATED ALWAYS)
3. UPDATE `suggestions.status` if triggered by a suggestion

All steps in a single transaction.

### Search: `search_regulations()`

3-layer search identical to Pasal.id's `search_legal_chunks()`:
- **Layer 1:** Identity fast path — detects regulation identifiers ("POJK 10 2022", "SEOJK 19/2023"), score 1000, early exit
- **Layer 2:** Works FTS — searches `works.search_fts` for title/topic queries, score 1–15
- **Layer 3:** Content FTS — 3-tier fallback on `document_nodes.fts` (websearch → plainto → ILIKE), score 0.01–0.5

Input sanitized to prevent tsquery crashes. Function name stable — all consumers call via `.rpc("search_regulations")`.

---

## Coding Conventions

### TypeScript / Next.js

- **Server Components by default.** Only `"use client"` for interactivity.
- **Supabase access:** `@supabase/ssr`. Use `getUser()` on server, never trust `getSession()`.
- **File naming:** `kebab-case.tsx` for routes, `PascalCase.tsx` for components.
- **Styling:** Tailwind utility classes only.
- **UI language:** Indonesian primary, English secondary.
- **Admin auth:** `requireAdmin()` from `src/lib/admin-auth.ts` — checks Supabase auth + `ADMIN_EMAILS` env var.

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
- Prefer functions over classes.
- PDF extraction: `pymupdf`. OJK PDFs are born-digital — no OCR needed for post-2013 regulations.
- Gemini agent: `from google import genai`. Advisory only — admin must approve suggestions.

### SQL migrations

- Numbered sequentially: `packages/supabase/migrations/NNN_description.sql`
- Always glob `packages/supabase/migrations/*.sql` to verify next number before creating.
- Always add indexes for WHERE/JOIN/ORDER BY columns.
- Always enable RLS on new tables. Add public read policy for regulatory data.
- Computed columns use `GENERATED ALWAYS AS`.
- `CREATE OR REPLACE FUNCTION` drops `SET search_path`. Always re-apply `ALTER FUNCTION ... SET search_path = 'public', 'extensions'` after definition.

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

### Regulation type codes (JDIH internal)

| Type | JDIH jenisPeraturan param |
|------|--------------------------|
| UU | 01 |
| POJK | 06 |
| SEOJK | 07 |

### PDF quality

OJK PDFs (post-2013) are **born-digital, machine-readable**. PDF-1.7 format with embedded TrueType fonts. PyMuPDF extracts text directly — no OCR required. Pre-2013 regulations may be scanned; classify and handle separately.

### Additional documents per regulation

Each POJK detail page offers three downloadable documents:
1. **Peraturan** (main regulation PDF) — always present
2. **Abstrak** (abstract PDF) — summary of the regulation — always present
3. **FAQ** (FAQ PDF) — Q&A guidance — present for most recent POJKs

Download and index all three. The abstract and FAQ are especially useful for compliance context and should be stored in the `abstracts` and `faqs` tables.

### Scraping notes

- Listing pages may require a JavaScript-capable client (verify during implementation)
- UUID for detail page is the key — PDF UUID differs from detail page UUID
- Rate limit: 1–2 second delay between requests
- Geo-blocking possible from non-Indonesian IPs — test with Indonesian VPN if needed

---

## Environment Variables

| File | Key vars |
|------|----------|
| `.env` (root) | `SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY` |
| `apps/web/.env.local` | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `ADMIN_EMAILS`, `NEXT_PUBLIC_SITE_URL` |
| `apps/mcp-server/.env` | `SUPABASE_URL`, `SUPABASE_ANON_KEY` |
| `scripts/.env` | `SUPABASE_URL`, `SUPABASE_KEY` (= SERVICE_ROLE_KEY), `GEMINI_API_KEY` |

**`SUPABASE_KEY` in scripts = `SUPABASE_SERVICE_ROLE_KEY` (bypasses RLS). Never expose to browser.**

---

## Deployment

- **Web:** Vercel (auto-deploys from `main`). Run `vercel link --project regulasi-id-web --yes` from monorepo root, then `vercel --prod --yes`.
- **MCP server:** Railway (Dockerfile at `apps/mcp-server/Dockerfile`).
- **Database:** Supabase (Singapore region recommended — closest to Indonesia).
- **Git:** Push to `main` directly.

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
| Berlaku | In force |
| Dicabut | Revoked |
| Diubah | Amended |
| Mengubah | Amends (relationship type) |
| Melaksanakan | Implements (relationship type) |

---

## Gotchas

- **Listing pages may be JavaScript-rendered.** Verify during scraper development — may need Playwright/Selenium instead of httpx.
- **UUID mismatch.** The UUID in the detail page URL differs from the UUID used in the PDF download URL. Scrape both from the detail page HTML.
- **Abstract/FAQ UUIDs.** Each supplementary document has its own download UUID, separate from the main regulation PDF UUID.
- **RLS blocks empty results.** If a table returns no data, check that an RLS policy exists.
- **`SUPABASE_KEY` naming.** Scripts use `SUPABASE_KEY` but root `.env` calls it `SUPABASE_SERVICE_ROLE_KEY`. Same value.
- **No OCR needed for modern regulations.** OJK PDFs post-2013 are born-digital. Don't add OCR complexity unless you specifically target pre-2013 documents.
- **Pre-OJK regulations.** Some POJK regulate things previously governed by Bank Indonesia (BI) regulations. The `work_relationships` table handles `menggantikan` (replaces) relationships.
- **SEOJK references POJK by title, not number.** When parsing relationship text, match by both number+year and partial title.
- **Compliance checklist is sector-wide.** `get_compliance_checklist()` should return all POJKs + SEOJKs that apply to a given sector and business type — not just ones explicitly tagged. This requires a `compliance_mappings` table or a curated tagging system.
- **i18n async/sync distinction.** Using `useTranslations` in async Server Components causes build error. Use `getTranslations` with `await`.
- **i18n navigation imports.** Public pages must import from `@/i18n/routing`, not `next/link`.
- **Local build fails on prerender.** `npm run build` errors if `NEXT_PUBLIC_SUPABASE_URL` isn't set. Use `npx tsc --noEmit` for local TypeScript check.

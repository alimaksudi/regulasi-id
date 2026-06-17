# Contributing

---

## Getting Started

1. Read `CLAUDE.md` — the single source of truth for architecture, conventions, and gotchas.
2. Set up the environment: `docs/SETUP.md`
3. Find an issue or create one before starting large changes.

---

## Development Workflow

```bash
# Feature branch
git checkout -b feat/short-description

# Run all services in three terminals:
cd apps/web && npm run dev      # → localhost:3000
cd apps/api && wrangler dev     # → localhost:8787
cd apps/mcp-server && python server.py   # → localhost:8000/mcp

# Before committing:
cd apps/web && npm run lint && npm run test:run
cd apps/api && npm run lint && npm run test

# Commit and push
git push origin feat/short-description
```

---

## PR Requirements

All PRs must pass CI before merge. The checklist below is what CI enforces — and what reviewers will check.

### Checklist

**General**
- [ ] `npm run lint` passes (web + api — zero errors, warnings only if pre-existing)
- [ ] All new code has tests (unit or integration, in the appropriate `*.test.ts`)
- [ ] No `console.log` left in production paths (structured logging via `structlog` in Python, Sentry capture in Workers)
- [ ] No hardcoded secrets, URLs, or environment-specific values

**TypeScript / Frontend**
- [ ] No `any` types introduced without a comment explaining why
- [ ] `createServerFn()` for all SSR data fetching — never `useEffect` for initial data
- [ ] Navigation uses `Link`, `useRouter`, `useNavigate` from `@tanstack/react-router` — not browser `window.location`
- [ ] Icons from `lucide-react` only — no other icon library
- [ ] Warm stone neutrals only (`stone-*`) — no `gray-*`, `slate-*`, `zinc-*`

**Hono API**
- [ ] Every new route has a `zValidator("json", Schema)` or `zValidator("query", Schema)` middleware — no raw `c.req.json()` without validation
- [ ] Rate limiting via Upstash on mutating endpoints (`POST`, `DELETE`)
- [ ] Secrets accessed via `c.env.SECRET_NAME` — never from `process.env` (Workers runtime doesn't have `process.env`)
- [ ] No `Date.now()` or `Math.random()` in module scope — V8 isolates may reuse global state between requests
- [ ] `c.executionCtx.waitUntil()` for fire-and-forget work (analytics logging, cache warming) — never floating promises
- [ ] `wrangler dev` tested locally before PR — don't submit untested Workers code

**Database**
- [ ] New SQL migrations: verify next number with `ls packages/supabase/migrations/ | sort | tail -5` before creating
- [ ] RLS enabled on every new table: `ALTER TABLE x ENABLE ROW LEVEL SECURITY`
- [ ] Public read policy for legal data tables: `CREATE POLICY "Public read" ON x FOR SELECT USING (true)`
- [ ] Indexes for every WHERE/JOIN/ORDER BY column
- [ ] `document_nodes.content_text` mutations ONLY via `apply_revision()` — never direct UPDATE
- [ ] No `COUNT(*)` on large tables via anon role (3s timeout) — use RPC with extended timeout or materialized view
- [ ] pgvector: when `content_text` changes, `embedding` must be nulled to signal background backfill

**Migration CI**
- [ ] Migration applied to test Supabase project in CI before production
- [ ] Heavy migrations (ALTER TABLE on large table): split into steps, set `statement_timeout = '600s'`

**MCP Server (Python)**
- [ ] New tool added to `server.json` and `public/llms.txt`
- [ ] Upstash cache key follows pattern: `{tool}:{hash(args)}`
- [ ] Rate limit checked before DB call
- [ ] Sentry error capture on exceptions

**Scraper / Pipeline (Python)**
- [ ] Type hints on all new functions
- [ ] New importers of changed functions: grep all `.py` files for uses before renaming/deleting
- [ ] Quality scorer called on all new extractions — nothing loaded with score < 0.3 without manual review flag
- [ ] Exponential backoff respected: don't retry immediately on failure

---

## What Belongs in a PR vs a Separate Issue

Keep PRs focused. If you discover a related problem while working:
- Small fix (< 10 lines): include in the same PR with a note
- Larger fix: open a separate issue, link it in your PR description

---

## Commit Style

```
feat(search): add semantic search layer with RRF reranking
fix(api): handle empty embedding response from OpenAI
docs(mcp): document get_compliance_checklist parameters
chore(deps): upgrade hono to 4.x
```

Format: `type(scope): short imperative description`

Types: `feat`, `fix`, `docs`, `test`, `chore`, `refactor`, `perf`

Scopes match component paths: `web`, `api`, `mcp`, `pipeline`, `db`, `search`

---

## Code Review Turnaround

Maintainer reviews within 2 business days (Jakarta time, WIB). For urgent compliance-related fixes, tag the issue `urgent` and ping in the PR description.

---

## Not Accepted

- Features not discussed in an issue first (for anything > small bug fix)
- Changes that break the `search_regulations()` function signature — 3 consumers depend on it (web, API, MCP)
- Direct `UPDATE document_nodes SET content_text = ...` — always via `apply_revision()`
- Removing Zod validation from existing routes
- Adding non-Lucide icon libraries
- Cool neutral colors (`gray-*`, `slate-*`, `zinc-*`) in UI components

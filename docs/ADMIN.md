# Admin Guide

The admin interface is at `https://regulasi.id/admin`. It is client-side only — not SSR, not indexed, not cached. Requires Supabase Auth login with an email in `ADMIN_EMAILS`.

Admin API routes run in the Hono.js Worker at `api.regulasi.id/api/admin/*`. All admin API requests require a `Authorization: Bearer <jwt>` header. The JWT is issued by Supabase Auth on login and verified server-side in Cloudflare Workers — the Worker uses `SUPABASE_SERVICE_ROLE_KEY` for admin DB operations.

---

## Admin Pages

| Route | Purpose |
|-------|---------|
| `/admin` | Dashboard — active work count, zero-result queries, recent suggestions |
| `/admin/suggestions` | Suggestion review queue |
| `/admin/compliance` | Compliance mapping CRUD |
| `/admin/scraper` | Crawl job monitor |
| `/admin/analytics` | Search analytics |

---

## Admin API Routes (Hono.js)

All routes require `Authorization: Bearer <supabase-jwt>`. Worker verifies JWT against Supabase and checks `ADMIN_EMAILS`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/admin/suggestions` | Pending suggestions (paginated) |
| `POST` | `/api/admin/suggestions/:id/approve` | Approve + apply via `apply_revision()` |
| `POST` | `/api/admin/suggestions/:id/reject` | Reject with optional reason |
| `GET` | `/api/admin/compliance` | All compliance mappings |
| `POST` | `/api/admin/compliance` | Create new mapping |
| `PUT` | `/api/admin/compliance/:id` | Update mapping |
| `DELETE` | `/api/admin/compliance/:id` | Delete mapping |
| `GET` | `/api/admin/analytics` | Search analytics summary |
| `GET` | `/api/admin/jobs` | Crawl job queue |
| `POST` | `/api/admin/jobs/:id/retry` | Requeue a failed job |
| `POST` | `/api/admin/revalidate` | Purge Upstash cache keys by pattern |

---

## Suggestion Review Workflow

Suggestions come from public `POST /api/suggestions`. They go into `suggestions` table with `status: 'pending'`.

### Reviewing

1. `/admin/suggestions` — lists all pending suggestions, sorted by newest first
2. Each card shows: regulation title, article number, current text (highlighted diff), suggested text, submitter email (if provided)
3. **Approve:** calls `POST /api/admin/suggestions/:id/approve`
   - Worker calls `apply_revision()` in a single transaction
   - `document_nodes.content_text` is updated
   - `revisions` row inserted (audit trail)
   - `suggestions.status` set to `approved`
   - `document_nodes.embedding` nulled (triggers background backfill)
4. **Reject:** calls `POST /api/admin/suggestions/:id/reject` with optional note
   - `suggestions.status` set to `rejected`
   - No content change

### Important: `apply_revision()` is atomic

`apply_revision()` runs all three steps — `INSERT revisions`, `UPDATE document_nodes.content_text`, `UPDATE suggestions.status` — in a single transaction. If any step fails, everything rolls back. Never manually UPDATE `document_nodes.content_text` from admin scripts.

---

## Compliance Mappings

Compliance mappings (`compliance_mappings` table) power `GET /api/v1/compliance` and the `get_compliance_checklist` MCP tool.

### Schema

```sql
compliance_mappings (
  id            bigint primary key,
  sector        text,                   -- 'fintech', 'perbankan', etc.
  business_type text,                   -- 'p2p-lending', NULL means sector-wide
  work_id       bigint references works,
  priority      text,                   -- 'required', 'recommended', 'informational'
  notes         text                    -- optional human-readable explanation
)
```

### Adding a mapping

Via `/admin/compliance` → New Mapping, or direct SQL:

```sql
INSERT INTO compliance_mappings (sector, business_type, work_id, priority, notes)
VALUES (
  'fintech',
  'p2p-lending',
  (SELECT id FROM works WHERE slug = 'pojk-10-2022'),
  'required',
  'Primary licensing regulation for P2P lending (LPBBTI) operators under OJK'
);
```

### When a regulation is revoked

No manual cleanup needed. `GET /api/v1/compliance` filters `WHERE works.status != 'dicabut'` automatically. The revoked regulation disappears from compliance lists when its status is updated in `works`.

### Seeding priority

1. Fintech (highest user demand): POJK + SEOJK for P2P lending, payment systems, digital banking
2. Perbankan: capital adequacy, risk management
3. IKNB: insurance, pension funds

---

## Search Analytics

`/admin/analytics` pulls from the `search_analytics` table.

### Key metrics to monitor weekly

```sql
-- Top zero-result queries (content gap signals)
SELECT query, COUNT(*) as count
FROM search_analytics
WHERE zero_results = true
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY query
ORDER BY count DESC
LIMIT 20;

-- Failed sector searches (missing content)
SELECT sector, COUNT(*) as count
FROM search_analytics
WHERE zero_results = true
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY sector
ORDER BY count DESC;

-- Most popular successful queries
SELECT query, COUNT(*) as count, AVG(response_ms) as avg_ms
FROM search_analytics
WHERE zero_results = false
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY query
ORDER BY count DESC
LIMIT 20;
```

Zero-result queries are the most actionable product signal: they show what regulations users need that aren't in the system yet.

---

## Crawl Job Monitor

`/admin/scraper` shows:
- Active jobs (status = `processing`)
- Failed jobs (status = `failed`, `dead`) with retry count and last error
- Backlog (status = `pending`) by sector

### Retrying failed jobs

Via UI: Jobs tab → Filter Failed → select → Retry.

Via API:
```bash
curl -X POST https://api.regulasi.id/api/admin/jobs/123/retry \
  -H "Authorization: Bearer $ADMIN_JWT"
```

Resets job to `pending` and clears `next_retry_at` so the worker picks it up immediately.

### Job status reference

| Status | Meaning |
|--------|---------|
| `pending` | Waiting in queue |
| `processing` | Claimed by a worker |
| `done` | Successfully parsed and loaded |
| `failed` | Errored — will retry (exponential backoff) |
| `dead` | Failed 4+ times — will NOT retry automatically |
| `skipped` | Unchanged since last crawl — no re-parse needed |

---

## Cache Management

Upstash Redis cache TTLs:
- `emb:{hash}` — query embeddings, 1h
- `sector:all` — sector stats, 15min
- `article:{id}` — article content, 24h
- `compliance:{sector}:{type}` — compliance list, 1h

To purge after bulk content update:
```bash
curl -X POST https://api.regulasi.id/api/admin/revalidate \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"pattern": "article:*"}'
```

---

## Login / Auth

Admin uses Supabase Auth directly. No special admin user table — only email allowlist via `ADMIN_EMAILS` env var in Cloudflare Workers.

To add an admin:
1. `wrangler secret put ADMIN_EMAILS` with new comma-separated value: `admin@example.com,other@example.com`
2. The new admin must sign up at `/admin/login` to create a Supabase Auth account

To remove an admin: remove their email from `ADMIN_EMAILS`, redeploy. Their existing JWT fails validation immediately on next request.

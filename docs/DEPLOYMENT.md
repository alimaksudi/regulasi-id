# Deployment

Four services, three platforms:

| Service | Platform | Trigger |
|---------|----------|---------|
| Web app | Vercel | Auto on `main` push |
| MCP server | Railway | Auto on `main` push |
| Data pipeline worker | Railway | Cron + manual |
| Redis | Upstash | Managed (no deploy) |

---

## Web App — Vercel

### First-time setup

```bash
npm install -g vercel
vercel login

# From MONOREPO ROOT (never from apps/web/)
vercel link --project regulasi-id-web --yes
```

Vercel project settings (dashboard):
- Root directory: `apps/web`
- Framework: Next.js
- Node version: 20.x

### Required environment variables (Vercel dashboard)

```
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
ADMIN_EMAILS
NEXT_PUBLIC_SITE_URL=https://regulasi.id
UPSTASH_REDIS_REST_URL
UPSTASH_REDIS_REST_TOKEN
SENTRY_DSN
NEXT_PUBLIC_SENTRY_DSN
SENTRY_AUTH_TOKEN         ← for source map upload
NEXT_PUBLIC_PLAUSIBLE_DOMAIN=regulasi.id
```

### Deploy

```bash
# From MONOREPO ROOT
vercel --prod --yes
```

Auto-deploy fires on every `main` push — manual deploy only needed when env vars changed without code change.

### Rollback

```bash
vercel rollback                      # previous deployment
vercel rollback <deployment-url>     # specific deployment
```

Or via Vercel dashboard → Deployments → Promote to Production.

### ISR revalidation

After bulk DB updates, revalidate ISR cache for affected pages:

```bash
curl -X POST https://regulasi.id/api/admin/revalidate \
  -H "Cookie: your-session-cookie" \
  -d '{"slug": "pojk-10-2022"}'
```

### Preview deploys

Every PR gets a preview URL. Preview uses production env vars — be careful if your branch writes to the DB.

---

## MCP Server — Railway

### First-time setup

1. Railway → New Project → Deploy from GitHub → `alimaksudi/regulasi-id`
2. Root directory: `apps/mcp-server`
3. Railway auto-detects Dockerfile

### Environment variables (Railway dashboard)

```
SUPABASE_URL
SUPABASE_ANON_KEY     ← anon key ONLY — never service role
UPSTASH_REDIS_REST_URL
UPSTASH_REDIS_REST_TOKEN
SENTRY_DSN
PORT                  ← set automatically by Railway
```

### No trailing slash rule

```
✓  https://xxx.up.railway.app/mcp
✗  https://xxx.up.railway.app/mcp/
```

Railway 307-redirects the trailing slash form, which breaks Claude Code's HTTP transport.

### Update MCP URL in 5 places

When Railway URL changes:
1. `apps/web/src/app/[locale]/connect/page.tsx`
2. `apps/web/src/app/[locale]/page.tsx`
3. `server.json`
4. `apps/web/public/llms.txt`
5. `README.md`

### Rollback

Railway dashboard → Deployments → previous deploy → Redeploy.

---

## Data Pipeline Worker — Railway

Same Railway project, separate service (Add Service → Worker from same repo).

Start command:
```
python -m scripts.worker.run continuous --discovery-first
```

### Environment variables

```
SUPABASE_URL
SUPABASE_KEY          ← service role — bypasses RLS for writes
GEMINI_API_KEY
OPENAI_API_KEY        ← for embedding generation
SENTRY_DSN
```

### Cron jobs (Railway Cron)

```
# Weekly discovery — Monday 2am WIB (UTC+7 = Sunday 19:00 UTC)
0 19 * * 0   python -m scripts.worker.run discover --sectors all

# Daily embedding backfill — 3am WIB (8pm UTC)
0 20 * * *   python -m scripts.worker.run embed --batch-size 200
```

### Manual operations

```bash
# From Railway service console or local:
python -m scripts.worker.run stats
python -m scripts.worker.run retry           # retry failed jobs
python -m scripts.worker.run reset-dead      # reset dead jobs for manual review
python -m scripts.worker.run embed --batch-size 500
```

---

## Database — Supabase

### Applying migrations

Use the **direct connection** (port 5432) for migrations — PgBouncer incompatible with migration `SET` commands.

```bash
# Verify next migration number
ls packages/supabase/migrations/ | sort | tail -5

# Apply via Supabase SQL Editor (recommended)
# Or via psql:
psql "postgresql://postgres:[password]@db.xxx.supabase.co:5432/postgres" -f packages/supabase/migrations/021_description.sql
```

Heavy migrations (ALTER TABLE on large tables):
```sql
SET statement_timeout = '600s';
-- then the migration SQL
```

**Rule:** Never apply to production until migration CI passes on the PR.

### Backups

Supabase Pro provides daily automated backups. Before any destructive migration:

Supabase dashboard → Settings → Database → Backups → Download.

### RLS verification

After every migration that adds a table:

```sql
-- Check RLS enabled
SELECT tablename, rowsecurity FROM pg_tables
WHERE schemaname = 'public' AND tablename = 'your_table';
-- rowsecurity must be 't'

-- Check public read policy exists
SELECT policyname, cmd FROM pg_policies
WHERE tablename = 'your_table';

-- Verify with anon key (should return data, not [])
-- Run in Supabase SQL Editor → switch role to 'anon'
```

### PgBouncer monitoring

Watch connection count — if approaching the limit, connections queue and latency spikes.

Supabase dashboard → Reports → Database → Connections.

Free plan: 60 direct connections. Pro: 500. PgBouncer multiplexes these so the app can have thousands of "connections" through the pooler.

### Materialized view refresh

pg_cron runs the refresh every 15 minutes automatically (migration 020). To force refresh:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_sector_stats;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_type_stats;
```

---

## Redis — Upstash

No infra to manage. Upstash is serverless — scales automatically.

### Monitoring

Upstash dashboard → Analytics:
- Commands/sec — rate limiting activity
- Hit rate — cache effectiveness (target > 50% for `get_article`)
- Memory — should stay under 256MB on free tier

If cache hit rate for `get_article` is low, TTL may be too short or cache key is wrong.

### Flush cache

In emergencies (stale data after bulk update):

```bash
# Redis CLI via Upstash dashboard console
FLUSHDB
```

Or selectively:
```bash
# Flush all article caches
SCAN 0 MATCH "article:*" COUNT 100
# Then DEL each key
```

---

## Domain — regulasi.id

DNS via Vercel Domains. Add CNAME:
```
regulasi.id → cname.vercel-dns.com
```

SSL auto-managed by Vercel (Let's Encrypt, auto-renews).

---

## Sentry Setup

Both web and MCP server send errors to Sentry. Configure:

1. Create two Sentry projects: `regulasi-id-web` and `regulasi-id-mcp`
2. Add `SENTRY_AUTH_TOKEN` to Vercel env — Vercel auto-uploads source maps on deploy
3. Set alert rules: email on new issue, Slack on regression

In code — web (`src/app/layout.tsx`):
```typescript
import * as Sentry from "@sentry/nextjs"
Sentry.init({ dsn: process.env.NEXT_PUBLIC_SENTRY_DSN })
```

In code — MCP server (`server.py`):
```python
import sentry_sdk
sentry_sdk.init(dsn=os.environ["SENTRY_DSN"])
```

---

## Observability Stack

| Signal | Tool | Where |
|--------|------|-------|
| Errors | Sentry | Web + MCP + pipeline |
| Traces | `@vercel/otel` + OpenTelemetry | Web API routes + Server Components |
| Product analytics | Plausible | Web (privacy-first, no cookies) |
| Search analytics | `search_analytics` table | DB — read weekly |
| Pipeline health | Railway logs (structlog JSON) | Worker service |
| DB performance | Supabase dashboard → Slow queries | Production DB |
| Uptime | UptimeRobot on `/api/v1/sectors` | Alert on downtime |
| Redis | Upstash dashboard | Cache hit rate, command rate |

---

## Monitoring Queries

```sql
-- Stuck jobs (crawler may be down)
SELECT count(*) FROM crawl_jobs
WHERE status = 'crawling' AND claimed_at < NOW() - INTERVAL '1 hour';

-- Failed jobs by sector
SELECT sector_code, count(*) FROM crawl_jobs
WHERE status = 'failed'
GROUP BY sector_code ORDER BY count DESC;

-- Zero-result searches (missing content signals)
SELECT query, count(*) FROM search_analytics
WHERE zero_results = true AND created_at > NOW() - INTERVAL '7 days'
GROUP BY query ORDER BY count DESC LIMIT 20;

-- Embedding coverage
SELECT
  count(*) FILTER (WHERE embedding IS NOT NULL) AS with_embedding,
  count(*) AS total,
  round(count(*) FILTER (WHERE embedding IS NOT NULL)::numeric / count(*) * 100, 1) AS coverage_pct
FROM document_nodes WHERE node_type = 'pasal';
```

---

## Secrets Rotation

If any key is compromised:

**Supabase anon key** (low urgency — public key):
1. Regenerate in Supabase → Settings → API
2. Update Vercel env → redeploy
3. Update Railway (MCP) → redeploy

**Supabase service role key** (high urgency — bypasses RLS):
1. Regenerate immediately
2. Update Vercel env → redeploy
3. Update Railway (worker) → redeploy
4. Update local `scripts/.env` on all machines
5. Check Sentry for any suspicious requests logged before rotation

**Upstash token:**
1. Rotate in Upstash dashboard
2. Update Vercel + Railway (both services)

**OpenAI/Gemini API key:**
1. Revoke in provider dashboard
2. Issue new key
3. Update Railway (worker) → redeploy

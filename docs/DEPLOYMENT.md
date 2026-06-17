# Deployment

Four services across three platforms:

| Service | Platform | Trigger |
|---------|----------|---------|
| Web app (TanStack Start SSR) | Vercel | Auto on `main` push |
| API (Hono.js) | Cloudflare Workers | `wrangler deploy` (manual or CI) |
| MCP server (FastMCP Python) | Railway | Auto on `main` push |
| Data pipeline worker | Railway | Cron + manual |

---

## Web App — Vercel (TanStack Start SSR)

### First-time setup

```bash
npm install -g vercel
vercel login

# From MONOREPO ROOT (not apps/web/)
vercel link --project regulasi-id-web --yes
```

TanStack Start's Vercel adapter (`@tanstack/start-adapter-vercel`) handles SSR automatically. No `serverless.js` or `api/` config needed — Vite build output is Vercel-compatible.

### Vercel project settings (dashboard)

- Root directory: `apps/web`
- Framework: Other (TanStack Start manages its own build)
- Build command: `npm run build`
- Output directory: `.output` (auto-detected by adapter)

### Environment variables (Vercel dashboard)

```
VITE_SUPABASE_URL
VITE_SUPABASE_ANON_KEY
VITE_API_URL=https://api.regulasi.id
VITE_SENTRY_DSN
VITE_PLAUSIBLE_DOMAIN=regulasi.id
```

Note: `VITE_*` prefix exposes variables to the browser bundle. Never put secrets in `VITE_*` vars.

### Deploy

```bash
# From MONOREPO ROOT
vercel --prod --yes
```

Auto-deploy fires on every `main` push.

### CDN caching

TanStack Start server functions set `Cache-Control` headers. Vercel respects these for edge caching:

```typescript
// In route loader
export const Route = createFileRoute("/regulasi/$type/$slug")({
  head: () => ({
    meta: [],
    links: [],
  }),
  loader: async ({ params }) => {
    // Set cache headers from server function
    setResponseHeader("Cache-Control", "public, max-age=86400, stale-while-revalidate=3600")
    return getRegulationFn({ data: { slug: params.slug } })
  },
})
```

### Rollback

```bash
vercel rollback                    # previous deployment
vercel rollback <deployment-url>   # specific deployment
```

Or Vercel dashboard → Deployments → Promote to Production.

---

## API — Cloudflare Workers (Hono.js)

### First-time setup

```bash
cd apps/api
npm install
wrangler login
```

`wrangler.toml`:
```toml
name = "regulasi-id-api"
main = "src/index.ts"
compatibility_date = "2025-06-01"
compatibility_flags = ["nodejs_compat"]

[vars]
ENVIRONMENT = "production"

[[routes]]
pattern = "api.regulasi.id/*"
zone_name = "regulasi.id"
```

### Set production secrets

```bash
cd apps/api

wrangler secret put SUPABASE_URL
wrangler secret put SUPABASE_ANON_KEY
wrangler secret put SUPABASE_SERVICE_ROLE_KEY
wrangler secret put OPENAI_API_KEY
wrangler secret put UPSTASH_REDIS_REST_URL
wrangler secret put UPSTASH_REDIS_REST_TOKEN
wrangler secret put SENTRY_DSN
wrangler secret put ADMIN_JWT_SECRET
wrangler secret put ADMIN_EMAILS
```

### Deploy

```bash
cd apps/api
wrangler deploy
```

First deploy: also configure the custom domain in Cloudflare dashboard → Workers & Pages → Custom Domains → `api.regulasi.id`.

### Local development

```bash
cd apps/api
wrangler dev    # → http://localhost:8787

# With a specific port
wrangler dev --port 8787
```

Local dev uses `.dev.vars` for secrets (never committed).

### Rollback

```bash
wrangler rollback   # rolls back to previous Workers deployment
```

Or Cloudflare dashboard → Workers & Pages → select deployment → Rollback.

### Logs + observability

```bash
wrangler tail   # live log streaming from production Workers
```

Cloudflare dashboard → Workers → Analytics: request volume, error rate, CPU time, p99 latency.

---

## MCP Server — Railway (FastMCP Python)

### First-time setup

1. Railway → New Project → Deploy from GitHub → `alimaksudi/regulasi-id`
2. Root directory: `apps/mcp-server`
3. Railway detects Dockerfile automatically

### Environment variables (Railway dashboard)

```
SUPABASE_URL
SUPABASE_ANON_KEY     ← anon key ONLY — never service role key
UPSTASH_REDIS_REST_URL
UPSTASH_REDIS_REST_TOKEN
SENTRY_DSN
PORT                  ← set automatically by Railway
```

### No trailing slash

```
✓  https://xxx.up.railway.app/mcp
✗  https://xxx.up.railway.app/mcp/
```

Update in 5 places when URL changes: `connect.tsx`, `index.tsx` (landing MCP card), `server.json`, `public/llms.txt`, `README.md`.

### Rollback

Railway dashboard → Deployments → previous deploy → Redeploy.

---

## Data Pipeline Worker — Railway

Separate Railway service (same project). Start command:

```
python -m scripts.worker.run continuous --discovery-first --concurrency 5
```

### Environment variables

```
SUPABASE_URL
SUPABASE_KEY          ← service role key — bypasses RLS for writes
GEMINI_API_KEY
OPENAI_API_KEY        ← for embedding generation
SENTRY_DSN
```

### Cron jobs (Railway Cron)

```
# Weekly JDIH discovery — Monday 2am WIB = Sunday 19:00 UTC
0 19 * * 0   python -m scripts.worker.run discover --sectors all

# Daily embedding backfill — 3am WIB = 8pm UTC
0 20 * * *   python -m scripts.worker.run embed --batch-size 200

# Daily materialized view refresh (backup if pg_cron fails)
0 21 * * *   python -m scripts.worker.run refresh-views
```

---

## Database — Supabase

### Applying migrations

Always use the **direct connection** (port 5432) for migrations — PgBouncer in transaction mode is incompatible with `SET` statements.

```bash
# Verify next migration number first
ls packages/supabase/migrations/ | sort | tail -5

# Apply via Supabase SQL Editor (recommended for complex migrations)
# Or via psql (for CI):
psql "postgresql://postgres:[password]@db.xxx.supabase.co:5432/postgres" \
  -f packages/supabase/migrations/022_new_migration.sql
```

### Migration CI

Before applying to production, CI applies migrations to a test Supabase project and runs integration tests. See `docs/TESTING.md` for the workflow.

**Rule:** Never apply a migration to production until CI passes.

### Backups

Supabase Pro: daily automated backups. Before any destructive migration:
Supabase dashboard → Settings → Database → Backups → Download.

### PgBouncer

App connections use PgBouncer (port 6543, transaction mode):
- Web app: `VITE_SUPABASE_URL` (uses anon key, PgBouncer via Supabase JS client)
- API: `SUPABASE_URL` in Workers env (anon key for public routes, service role for admin)
- Pipeline: direct connection (port 5432) for bulk inserts with transactions

Monitor connection count: Supabase dashboard → Reports → Database → Connections.

---

## Redis — Upstash

Serverless Redis. No infra to manage.

### Monitoring (Upstash dashboard)

- Commands/sec — normal range for regulasi-id: ~20–200/sec
- Hit rate for `article:*` keys — target > 60%
- Memory — should stay < 100MB on free tier

### Flush all caches (emergency)

```bash
# Via Upstash dashboard console
FLUSHDB
```

Or selectively (e.g., after bulk content update):
```bash
# Cloudflare Workers script or local:
for key in $(redis-cli --scan --pattern "article:*"); do redis-cli DEL $key; done
```

---

## Domain Configuration

| Subdomain | Points to | Purpose |
|-----------|-----------|---------|
| `regulasi.id` | Vercel | Web app (SSR) |
| `api.regulasi.id` | Cloudflare Workers | REST API (Hono) |

DNS (Cloudflare, set from Cloudflare dashboard since regulasi.id nameservers point to Cloudflare):
```
regulasi.id         CNAME   cname.vercel-dns.com    # proxied: OFF (Vercel manages SSL)
api.regulasi.id     CNAME   (managed by Workers route config)
```

SSL auto-managed: Vercel (Let's Encrypt) for `regulasi.id`, Cloudflare for `api.regulasi.id`.

---

## CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml
on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: cd apps/web && npm ci && npm run test:run
      - run: cd apps/api && npm ci && npm run test
      - name: Apply migrations to test DB
        run: |
          for f in $(ls packages/supabase/migrations/*.sql | sort); do
            psql "${{ secrets.SUPABASE_TEST_DB_URL }}" -f "$f"
          done

  deploy-api:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: cd apps/api && npm ci
      - run: cd apps/api && npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

  # Web deploy: Vercel auto-deploys on push to main (no CI step needed)
```

---

## Observability

| Signal | Tool | Location |
|--------|------|----------|
| Frontend errors | Sentry | Web app (React ErrorBoundary) |
| API errors | Sentry | Cloudflare Workers (via fetch to Sentry API) |
| MCP errors | Sentry | Python SDK |
| Pipeline errors | Sentry | Python SDK + structlog |
| API request metrics | Cloudflare Analytics | Workers dashboard |
| Web vitals | Vercel Analytics | Vercel dashboard |
| Product analytics | Plausible | `https://plausible.io/regulasi.id` |
| Search analytics | DB table | `search_analytics` — read in admin dashboard |
| Redis | Upstash dashboard | Hit rate, commands/sec |
| DB performance | Supabase dashboard | Slow query log (> 100ms) |
| Uptime | UptimeRobot | `https://api.regulasi.id/api/v1/sectors` |

---

## Secrets Rotation

**Service role key compromised (critical):**
1. Supabase → Settings → API → Regenerate service_role key
2. Update Railway worker → redeploy
3. Update Cloudflare Workers secret → `wrangler secret put SUPABASE_SERVICE_ROLE_KEY`
4. Update local `scripts/.env`
5. Audit Sentry for suspicious requests before rotation

**OpenAI key compromised:**
1. Revoke at platform.openai.com
2. Issue new key
3. `wrangler secret put OPENAI_API_KEY` → redeploy Workers
4. Update Railway worker

**Upstash token compromised:**
1. Rotate in Upstash dashboard
2. Update Vercel env + `wrangler secret put` + Railway env
3. Redeploy all three services

# Deployment

Three services, three platforms:

| Service | Platform | Trigger |
|---------|----------|---------|
| Web app | Vercel | Auto on push to `main` |
| MCP server | Railway | Auto on push to `main` |
| Data pipeline | Railway (worker) | Cron or manual trigger |

---

## Web App — Vercel

### First-time setup

```bash
npm install -g vercel
vercel login

# From MONOREPO ROOT (not apps/web/)
vercel link --project regulasi-id-web --yes
```

Vercel project settings (set via dashboard):
- Root directory: `apps/web`
- Framework preset: Next.js
- Node version: 20.x
- Build command: `npm run build` (default)
- Output directory: `.next` (default)

### Environment variables (set in Vercel dashboard)

```
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
ADMIN_EMAILS
NEXT_PUBLIC_SITE_URL=https://regulasi.id
```

### Deploy

```bash
# From MONOREPO ROOT
vercel --prod --yes
```

Auto-deploy is on — pushing to `main` triggers a production deploy automatically. Run manual deploy only when you need to force a redeploy without a code change (e.g., after updating env vars).

### Rollback

```bash
vercel rollback                    # roll back to previous deployment
vercel rollback <deployment-url>   # roll back to specific deployment
```

Or from Vercel dashboard: Deployments → find previous → Promote to Production.

### Preview deploys

Every PR automatically gets a preview URL: `https://regulasi-id-git-{branch}-{team}.vercel.app`. Preview deploys use the same env vars as production — be careful if your branch writes to the DB.

---

## MCP Server — Railway

### First-time setup

1. Create a Railway account → New Project → Deploy from GitHub
2. Select `alimaksudi/regulasi-id` repo
3. Set root directory: `apps/mcp-server`
4. Railway auto-detects `Dockerfile`

### Environment variables (set in Railway dashboard)

```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJ...anon_key   ← NOT service role key
```

`PORT` is set automatically by Railway.

### The no-trailing-slash rule

The deployed MCP URL must not have a trailing slash:

```
✓  https://xxx.up.railway.app/mcp
✗  https://xxx.up.railway.app/mcp/
```

Railway returns a 307 redirect for the trailing-slash form, which breaks Claude Code's HTTP transport.

### Update MCP URL in 5 places

When the Railway URL changes, update all of these:
1. `apps/web/src/app/[locale]/connect/page.tsx`
2. `apps/web/src/app/[locale]/page.tsx` (landing MCP card)
3. `server.json`
4. `apps/web/public/llms.txt`
5. `README.md`

### Rollback

Railway keeps deployment history. From Railway dashboard: Deployments → previous deploy → Redeploy.

---

## Data Pipeline Worker — Railway

### Setup

Same Railway project, separate service. Root directory: project root (not `scripts/`).

Start command:
```bash
python -m scripts.worker.run continuous --discovery-first
```

### Environment variables

```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...service_role_key   ← service role, bypasses RLS
GEMINI_API_KEY=AIzaSy...
```

### Running manually

```bash
# SSH into Railway service or run locally
python -m scripts.worker.run stats
python -m scripts.worker.run discover --sectors fintech
python -m scripts.worker.run process --batch-size 5
python -m scripts.worker.run retry-failed
```

### Cron (Railway Cron)

Set a Railway Cron job to run discovery weekly:
```
0 2 * * 1   python -m scripts.worker.run discover --sectors all
```

(Monday 2am — after OJK publishes new regulations over the weekend)

---

## Supabase

### Applying migrations

Migrations are applied manually via Supabase SQL Editor — they are NOT run by any CI or deploy step.

```bash
# Verify the next migration number
ls packages/supabase/migrations/ | sort | tail -5

# Then open Supabase SQL Editor and paste + run the .sql file
```

For heavy migrations (ALTER TABLE on large tables):
```sql
-- Prepend to the migration:
SET statement_timeout = '600s';
```

Run steps individually if needed — each ALTER TABLE separately.

### Backups

Supabase provides daily automated backups on Pro plan. Before any migration that drops/renames columns, download a manual backup:

Supabase dashboard → Settings → Database → Backups → Download.

### RLS check

After applying a migration that adds a new table, verify RLS is enabled and the public read policy exists:

```sql
-- Check RLS enabled
SELECT tablename, rowsecurity FROM pg_tables
WHERE schemaname = 'public' AND tablename = 'your_new_table';

-- Check policy exists
SELECT * FROM pg_policies WHERE tablename = 'your_new_table';

-- Quick test with anon key (should return data)
SELECT count(*) FROM your_new_table;  -- run as anon role
```

---

## Domain

`regulasi.id` → managed via Vercel Domains.

DNS: add CNAME record pointing `regulasi.id` to `cname.vercel-dns.com`.

SSL is managed automatically by Vercel (Let's Encrypt).

---

## Monitoring

| What | Where |
|------|-------|
| Web errors | Vercel dashboard → Functions logs |
| MCP server logs | Railway dashboard → service logs |
| Pipeline errors | `crawl_jobs` table — rows with `status='failed'` and `error_message` |
| DB query performance | Supabase dashboard → Reports → Slow queries |
| API uptime | Add UptimeRobot or Better Uptime on `https://regulasi.id/api/v1/sectors` |

### Alert on crawl failures

```sql
-- Jobs stuck in 'crawling' for > 1 hour = something is wrong
SELECT count(*) FROM crawl_jobs
WHERE status = 'crawling' AND claimed_at < NOW() - INTERVAL '1 hour';
```

Set a Railway Cron job to run a health check script and alert to Slack/email if this count > 0.

---

## Secrets Rotation

If a Supabase key is compromised:

1. Supabase dashboard → Settings → API → Regenerate key
2. Update in Vercel env vars → Redeploy
3. Update in Railway env vars for MCP server → Redeploy
4. Update in Railway env vars for worker → Redeploy
5. Update local `.env` files on all dev machines

The `SUPABASE_ANON_KEY` is public (exposed in browser). Rotating it is low urgency. The `SUPABASE_SERVICE_ROLE_KEY` bypasses RLS — rotate immediately if leaked.

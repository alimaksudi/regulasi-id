# Setup Guide

Complete environment setup from zero to running locally.

---

## Prerequisites

```bash
node --version    # 18+
python3 --version # 3.12+
gh --version      # GitHub CLI
```

```bash
brew install node python@3.12 gh git
```

---

## 1. Supabase Project

1. Go to https://supabase.com/dashboard → New Project
   - Name: `regulasi-id`
   - Region: `Southeast Asia (Singapore)` — closest to Indonesia
   - Password: generate strong, save it

2. Enable extensions in SQL Editor:
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS vector;    -- pgvector for embeddings
CREATE EXTENSION IF NOT EXISTS pg_cron;   -- materialized view refresh
```

3. Enable **PgBouncer** in Settings → Database → Connection pooling → Enable.
   Note both the pooler connection string (port 6543) and the direct connection (port 5432).

4. From Settings → API, copy:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`

---

## 2. Upstash Redis

1. Go to https://upstash.com → New Database
   - Name: `regulasi-id`
   - Region: `Singapore` (ap-southeast-1) — matches Supabase
   - Type: Regional (free tier)

2. From the database dashboard, copy:
   - `UPSTASH_REDIS_REST_URL`
   - `UPSTASH_REDIS_REST_TOKEN`

Used by both the web app and MCP server for distributed rate limiting and caching.

---

## 3. Sentry

1. Go to https://sentry.io → New Project
   - Platform: Next.js (for web), Python (for MCP + scripts)
   - Create both projects, note both DSNs.

2. Copy:
   - `SENTRY_DSN` (web — also used as `NEXT_PUBLIC_SENTRY_DSN`)
   - `SENTRY_DSN` for MCP server / pipeline (same project or separate)

---

## 4. Apply Migrations

Apply migrations via Supabase SQL Editor using the **direct connection** (port 5432). Apply in order:

```bash
ls packages/supabase/migrations/ | sort
```

Copy each `.sql` file into the SQL Editor and run sequentially. The pgvector `hnsw` index build may take 30–60 seconds on larger tables — normal.

---

## 5. Environment Files

**Root `.env`** (never commit):
```env
SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
GEMINI_API_KEY=AIzaSy...
OPENAI_API_KEY=sk-...
```

**`apps/web/.env.local`**:
```env
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
ADMIN_EMAILS=your@email.com
NEXT_PUBLIC_SITE_URL=http://localhost:3000
UPSTASH_REDIS_REST_URL=https://xxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=xxx
SENTRY_DSN=https://xxx@sentry.io/yyy
NEXT_PUBLIC_SENTRY_DSN=https://xxx@sentry.io/yyy
NEXT_PUBLIC_PLAUSIBLE_DOMAIN=localhost
```

**`apps/mcp-server/.env`**:
```env
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJ...anon_key   ← NOT service role
UPSTASH_REDIS_REST_URL=https://xxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=xxx
SENTRY_DSN=https://xxx@sentry.io/yyy
```

**`scripts/.env`**:
```env
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...service_role_key   ← bypasses RLS
GEMINI_API_KEY=AIzaSy...
OPENAI_API_KEY=sk-...
SENTRY_DSN=https://xxx@sentry.io/yyy
```

---

## 6. Web App

```bash
cd apps/web
npm install
npm run dev         # → http://localhost:3000
```

TypeScript check (doesn't require Vercel env):
```bash
npx tsc --noEmit
```

---

## 7. MCP Server

```bash
cd apps/mcp-server
pip install -r requirements.txt
python server.py    # → http://localhost:8000/mcp
```

Connect to Claude Code:
```bash
claude mcp add --transport http regulasi-id http://localhost:8000/mcp
```

Test tools:
```bash
python -m pytest test_server.py -v
```

---

## 8. Data Pipeline

```bash
# From project root
pip install -r scripts/requirements.txt

# Verify JDIH is reachable
python -m scripts.worker.run stats

# Discover regulations (seeds crawl_jobs)
python -m scripts.worker.run discover --sectors fintech --dry-run

# Process first batch (5 concurrent)
python -m scripts.worker.run process --batch-size 5 --concurrency 2

# Generate embeddings for pgvector
python -m scripts.worker.run embed --batch-size 50
```

---

## 9. Vercel Deployment

```bash
npm install -g vercel
vercel login

# From MONOREPO ROOT — not apps/web/
vercel link --project regulasi-id-web --yes
vercel --prod --yes
```

Vercel project settings:
- Root directory: `apps/web`
- Framework: Next.js
- Add all env vars from `apps/web/.env.local`
- Add `SENTRY_AUTH_TOKEN` for automatic source map upload

---

## 10. Railway Deployment

**MCP server:**
1. Railway → New Project → Deploy from GitHub → `alimaksudi/regulasi-id`
2. Root directory: `apps/mcp-server`
3. Add env vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `SENTRY_DSN`
4. Note deployed URL — no trailing slash

**Worker:**
1. Railway → same project → Add Service → Worker
2. Start command: `python -m scripts.worker.run continuous --discovery-first`
3. Add env vars: `SUPABASE_URL`, `SUPABASE_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `SENTRY_DSN`

---

## Verify Everything Works

```bash
# DB + pgvector
python -c "
import os; from dotenv import load_dotenv; load_dotenv('scripts/.env')
from supabase import create_client
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
print('works:', sb.table('works').select('id', count='exact').execute().count)
r = sb.rpc('search_regulations', {'p_query': 'fintech', 'p_limit': 1}).execute()
print('search works:', bool(r.data))
"

# Upstash Redis (from web app context)
node -e "
const { Redis } = require('@upstash/redis')
const r = new Redis({ url: process.env.UPSTASH_REDIS_REST_URL, token: process.env.UPSTASH_REDIS_REST_TOKEN })
r.ping().then(v => console.log('Redis:', v))
"

# MCP ping
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"ping","arguments":{}},"id":1}'

# Search API
curl "http://localhost:3000/api/v1/search?q=fintech"

# OpenAPI spec
curl "http://localhost:3000/api/openapi.json" | jq '.info'
```

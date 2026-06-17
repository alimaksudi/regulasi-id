# Setup Guide

Complete environment setup from zero to running locally.

---

## Prerequisites

```bash
node --version    # 20+
python3 --version # 3.12+
gh --version      # GitHub CLI
```

```bash
brew install node python@3.12 gh git
```

---

## 1. Supabase Project

1. https://supabase.com/dashboard → New Project
   - Name: `regulasi-id`, Region: `Southeast Asia (Singapore)`, save the password

2. SQL Editor → enable extensions:
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS vector;    -- pgvector
CREATE EXTENSION IF NOT EXISTS pg_cron;   -- materialized view refresh
```

3. Settings → Database → Connection pooling → Enable PgBouncer (transaction mode)

4. Settings → API → copy: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`

---

## 2. Upstash Redis

1. https://upstash.com → New Database → Singapore → Regional
2. Copy: `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`

Used by web app (TanStack Query persistence), Hono API (rate limiting), MCP server (caching).

---

## 3. Cloudflare Account

1. https://dash.cloudflare.com → sign up (free tier works)
2. Install Wrangler:
```bash
npm install -g wrangler
wrangler login
```

---

## 4. Sentry

1. https://sentry.io → New Projects: `regulasi-id-web` (React), `regulasi-id-api` (Node), `regulasi-id-mcp` (Python)
2. Copy each DSN

---

## 5. Apply Migrations

Via Supabase SQL Editor (direct connection, port 5432 — not PgBouncer):

```bash
ls packages/supabase/migrations/ | sort
```

Apply each `.sql` file in numerical order. The hnsw index build takes ~30s on first run — normal.

---

## 6. Environment Files

**`apps/web/.env.local`**:
```env
VITE_SUPABASE_URL=https://xxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...
VITE_API_URL=http://localhost:8787
VITE_SENTRY_DSN=https://xxx@sentry.io/yyy
VITE_PLAUSIBLE_DOMAIN=localhost
```

**`apps/api/.dev.vars`** (local secrets for Wrangler):
```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJ...anon_key
SUPABASE_SERVICE_ROLE_KEY=eyJ...service_role_key
OPENAI_API_KEY=sk-...
UPSTASH_REDIS_REST_URL=https://xxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=xxx
SENTRY_DSN=https://xxx@sentry.io/yyy
ADMIN_EMAILS=your@email.com
```

**`apps/mcp-server/.env`**:
```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJ...anon_key
UPSTASH_REDIS_REST_URL=https://xxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=xxx
SENTRY_DSN=https://xxx@sentry.io/yyy
```

**`scripts/.env`**:
```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...service_role_key
GEMINI_API_KEY=AIzaSy...
OPENAI_API_KEY=sk-...
```

---

## 7. Web App

```bash
cd apps/web
npm install
npm run dev       # → http://localhost:3000
```

Add shadcn/ui components (first time):
```bash
npx shadcn@latest init
# Vite preset, Stone base color, CSS variables: yes
npx shadcn@latest add button card input badge dialog table select textarea
```

---

## 8. API Server

```bash
cd apps/api
npm install
npm run dev       # → http://localhost:8787 (Wrangler dev server)
```

Test an endpoint:
```bash
curl -X POST http://localhost:8787/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"q": "fintech", "limit": 5}'
```

---

## 9. MCP Server

```bash
cd apps/mcp-server
pip install -r requirements.txt
python server.py   # → http://localhost:8000/mcp
```

Connect to Claude Code:
```bash
claude mcp add --transport http regulasi-id http://localhost:8000/mcp
```

---

## 10. Data Pipeline

```bash
pip install -r scripts/requirements.txt

# Test discovery (dry run)
python -m scripts.worker.run discover --sectors fintech --dry-run

# Process first 5 regulations
python -m scripts.worker.run process --batch-size 5 --concurrency 2

# Generate embeddings
python -m scripts.worker.run embed --batch-size 50
```

---

## 11. Deployment

### Web app (Vercel + TanStack Start)

```bash
# From MONOREPO ROOT
vercel link --project regulasi-id-web --yes
vercel --prod --yes
```

TanStack Start Vercel adapter handles SSR automatically.

### API (Cloudflare Workers)

```bash
cd apps/api

# Set production secrets
wrangler secret put SUPABASE_URL
wrangler secret put SUPABASE_SERVICE_ROLE_KEY
wrangler secret put OPENAI_API_KEY
wrangler secret put UPSTASH_REDIS_REST_URL
wrangler secret put UPSTASH_REDIS_REST_TOKEN
wrangler secret put SENTRY_DSN
wrangler secret put ADMIN_EMAILS

# Deploy
wrangler deploy
```

Custom domain: add `api.regulasi.id` as a Workers route in Cloudflare dashboard.

---

## Verify Everything Works

```bash
# Supabase + pgvector
python -c "
from dotenv import load_dotenv; load_dotenv('scripts/.env')
import os; from supabase import create_client
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
r = sb.rpc('search_regulations', {'p_query': 'fintech', 'p_limit': 1}).execute()
print('hybrid search:', bool(r.data), '| score:', r.data[0].get('score') if r.data else None)
"

# Hono API
curl http://localhost:8787/api/v1/sectors
curl -X POST http://localhost:8787/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"q":"p2p lending","limit":3}'

# OpenAPI spec
curl http://localhost:8787/api/openapi.json | python3 -m json.tool | head -20

# Web app
open http://localhost:3000

# MCP ping
python -c "
import httpx, json
r = httpx.post('http://localhost:8000/mcp',
  json={'jsonrpc':'2.0','method':'tools/call','params':{'name':'ping','arguments':{}},'id':1})
print(r.json()['result'])
"

# Upstash (from apps/api context)
node -e "
require('dotenv').config({path:'.dev.vars'})
const {Redis} = require('@upstash/redis')
const r = new Redis({url:process.env.UPSTASH_REDIS_REST_URL, token:process.env.UPSTASH_REDIS_REST_TOKEN})
r.ping().then(v=>console.log('Redis:', v))
"
```

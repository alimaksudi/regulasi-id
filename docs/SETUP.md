# Setup Guide

Complete environment setup from zero to running locally.

---

## Prerequisites

```bash
node --version   # 18+
python3 --version  # 3.12+
docker --version   # any recent
gh --version       # GitHub CLI
```

Install if missing:
```bash
brew install node python@3.12 docker gh git
```

---

## 1. Supabase Project

1. Go to https://supabase.com/dashboard → New Project
2. Settings:
   - Name: `regulasi-id`
   - Region: `Southeast Asia (Singapore)`
   - Password: generate strong, save it

3. Enable extensions in SQL Editor:
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
```

4. From Settings → API, copy:
   - `SUPABASE_URL` (project URL)
   - `SUPABASE_ANON_KEY` (anon public key)
   - `SUPABASE_SERVICE_ROLE_KEY` (service_role secret key — never expose to browser)

---

## 2. Apply Migrations

In Supabase SQL Editor, apply each migration in order:

```bash
ls packages/supabase/migrations/  # check order
```

Copy each `.sql` file content into the SQL Editor and run. Apply in numerical order (001, 002, ...).

---

## 3. Environment Files

**Root `.env`** (create manually, never commit):
```env
SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
GEMINI_API_KEY=AIzaSy...
```

**`apps/web/.env.local`**:
```env
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
ADMIN_EMAILS=your@email.com
NEXT_PUBLIC_SITE_URL=http://localhost:3000
```

**`apps/mcp-server/.env`**:
```env
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJ...anon_key
```

**`scripts/.env`**:
```env
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...service_role_key
GEMINI_API_KEY=AIzaSy...
```

---

## 4. Web App

```bash
cd apps/web
npm install
npm run dev        # → http://localhost:3000
```

TypeScript check (local build fails without Vercel env vars):
```bash
npx tsc --noEmit
```

---

## 5. MCP Server

```bash
cd apps/mcp-server
pip install -r requirements.txt
python server.py   # → http://localhost:8000/mcp
```

Connect to Claude Code:
```bash
claude mcp add --transport http regulasi-id http://localhost:8000/mcp
```

Test:
```bash
python -m pytest test_server.py -v
```

---

## 6. Data Pipeline

```bash
# From project root
pip install -r scripts/requirements.txt

# Discover regulations from jdih.ojk.go.id
python -m scripts.worker.run discover --sectors perbankan,fintech

# Process first batch (download PDFs, parse, load to DB)
python -m scripts.worker.run process --batch-size 5

# Check stats
python -m scripts.worker.run stats
```

---

## 7. Vercel Deployment

```bash
npm install -g vercel
vercel login

# From MONOREPO ROOT (not apps/web/)
vercel link --project regulasi-id-web --yes
vercel --prod --yes
```

Vercel project settings:
- Root directory: `apps/web`
- Framework: Next.js
- Add all environment variables from `apps/web/.env.local`

---

## 8. Railway Deployment (MCP Server)

1. Create Railway account → New Project → Deploy from GitHub
2. Set root directory: `apps/mcp-server`
3. Railway auto-detects Dockerfile
4. Add environment variables:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
5. Note the deployed URL: `https://xxx.up.railway.app/mcp` (no trailing slash)

---

## Verify Everything Works

```bash
# DB connection
python -c "
import os; from dotenv import load_dotenv; load_dotenv('scripts/.env')
from supabase import create_client
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
print(sb.table('works').select('id', count='exact').execute().count, 'works in DB')
"

# MCP server
curl http://localhost:8000/mcp

# Web app
open http://localhost:3000

# Search API
curl "http://localhost:3000/api/v1/search?q=fintech"
```

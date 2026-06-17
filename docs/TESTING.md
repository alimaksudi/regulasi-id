# Testing

---

## Overview

| Layer | Tool | When |
|-------|------|------|
| Web unit/component | Vitest + React Testing Library | `npm run test` |
| API unit | Vitest | `npm run test` in `apps/api/` |
| API integration | Vitest + Miniflare | `npm run test:integration` |
| DB / SQL | psql against test Supabase | CI only |
| E2E | Playwright | `npm run test:e2e` |
| Load | k6 | Pre-release manual runs |

---

## Web App (`apps/web/`)

```bash
npm run test         # Vitest unit tests (watch mode)
npm run test:run     # Single run (for CI)
npm run test:e2e     # Playwright end-to-end
```

### Unit / component tests

```typescript
// app/components/StatusBadge.test.tsx
import { render, screen } from "@testing-library/react"
import { StatusBadge } from "~/components/StatusBadge"

test("berlaku status shows green label", () => {
  render(<StatusBadge status="berlaku" />)
  expect(screen.getByText("Berlaku")).toBeInTheDocument()
  expect(screen.getByText("Berlaku").closest("span")).toHaveClass("text-[--status-berlaku]")
})

test("dicabut status shows red label", () => {
  render(<StatusBadge status="dicabut" />)
  expect(screen.getByText("Dicabut")).toBeInTheDocument()
})
```

### TanStack Router testing

TanStack Start routes are tested with `createMemoryHistory` and a router wrapper:

```typescript
import { RouterProvider, createRouter, createMemoryHistory } from "@tanstack/react-router"
import { routeTree } from "~/routeTree.gen"

function renderWithRouter(url: string) {
  const router = createRouter({ routeTree, history: createMemoryHistory({ initialEntries: [url] }) })
  return render(<RouterProvider router={router} />)
}

test("search page shows results", async () => {
  renderWithRouter("/search?q=fintech")
  await screen.findByRole("list", { name: /hasil pencarian/i })
})
```

---

## Hono API (`apps/api/`)

```bash
cd apps/api
npm run test              # Vitest unit tests
npm run test:integration  # Integration tests via Miniflare
```

### Unit tests (with Miniflare)

Miniflare provides a local Cloudflare Workers runtime for testing — runs the actual Hono handler without deploying.

```typescript
// src/routes/search.test.ts
import { unstable_dev } from "wrangler"
import type { UnstableDevWorker } from "wrangler"

let worker: UnstableDevWorker

beforeAll(async () => {
  worker = await unstable_dev("src/index.ts", {
    experimental: { disableExperimentalWarning: true },
    vars: {
      SUPABASE_URL: process.env.TEST_SUPABASE_URL!,
      SUPABASE_ANON_KEY: process.env.TEST_SUPABASE_ANON_KEY!,
      OPENAI_API_KEY: process.env.TEST_OPENAI_API_KEY ?? "sk-test",
      UPSTASH_REDIS_REST_URL: process.env.TEST_UPSTASH_URL!,
      UPSTASH_REDIS_REST_TOKEN: process.env.TEST_UPSTASH_TOKEN!,
    },
  })
})

afterAll(async () => { await worker.stop() })

test("POST /api/v1/search returns results for valid query", async () => {
  const resp = await worker.fetch("/api/v1/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ q: "fintech", limit: 5 }),
  })
  expect(resp.status).toBe(200)
  const data = await resp.json()
  expect(data).toHaveProperty("results")
  expect(Array.isArray(data.results)).toBe(true)
})

test("POST /api/v1/search rejects missing q", async () => {
  const resp = await worker.fetch("/api/v1/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ limit: 5 }),
  })
  expect(resp.status).toBe(400)
  const data = await resp.json()
  expect(data.code).toBe("VALIDATION_ERROR")
  expect(data.details).toHaveProperty("q")
})

test("rate limit returns 429 after 60 requests", async () => {
  const requests = Array.from({ length: 65 }, () =>
    worker.fetch("/api/v1/search", {
      method: "POST",
      headers: { "Content-Type": "application/json", "CF-Connecting-IP": "1.2.3.4" },
      body: JSON.stringify({ q: "test", limit: 1 }),
    })
  )
  const responses = await Promise.all(requests)
  const statuses = responses.map(r => r.status)
  expect(statuses.filter(s => s === 429).length).toBeGreaterThan(0)
})
```

### Zod validation tests

```typescript
import { SearchSchema } from "../src/lib/schemas"

test("SearchSchema requires q to be between 1-500 chars", () => {
  expect(SearchSchema.safeParse({ q: "" }).success).toBe(false)
  expect(SearchSchema.safeParse({ q: "a".repeat(501) }).success).toBe(false)
  expect(SearchSchema.safeParse({ q: "fintech" }).success).toBe(true)
})

test("SearchSchema limits must be 1-50", () => {
  expect(SearchSchema.safeParse({ q: "test", limit: 0 }).success).toBe(false)
  expect(SearchSchema.safeParse({ q: "test", limit: 51 }).success).toBe(false)
  expect(SearchSchema.safeParse({ q: "test", limit: 10 }).success).toBe(true)
})
```

---

## Database Integration

Applied to a **test Supabase project** (separate from production). Never run against production.

### Migration CI

```yaml
# .github/workflows/ci.yml
- name: Apply migrations to test DB
  env:
    SUPABASE_TEST_DB_URL: ${{ secrets.SUPABASE_TEST_DB_URL }}
  run: |
    for f in $(ls packages/supabase/migrations/*.sql | sort); do
      echo "Applying $f..."
      psql "$SUPABASE_TEST_DB_URL" -f "$f"
    done
```

Test Supabase project needs the same extensions as production:
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_cron;
```

### `search_regulations()` correctness

```python
# tests/integration/test_search.py
def test_fintech_p2p_lending_returns_pojk_10_2022(supabase):
    """Layer 1 identity match: regulation code lookup."""
    result = supabase.rpc("search_regulations", {
        "p_query": "pojk 10 2022",
        "p_limit": 5,
        "p_query_embedding": None,
    }).execute()
    assert result.data, "Expected at least one result"
    assert result.data[0]["score"] == 1000, "Identity match should score 1000"
    assert "pojk-10-2022" in result.data[0]["slug"]

def test_semantic_query_finds_p2p_regulation(supabase, openai_client):
    """Layer 4 semantic: vector search for synonym."""
    embedding = openai_client.embeddings.create(
        input="layanan pinjam meminjam uang berbasis teknologi",
        model="text-embedding-3-small"
    ).data[0].embedding

    result = supabase.rpc("search_regulations", {
        "p_query": "layanan pinjam meminjam uang berbasis teknologi",
        "p_limit": 5,
        "p_query_embedding": embedding,
    }).execute()
    slugs = [r["slug"] for r in result.data]
    assert "pojk-10-2022" in slugs, "POJK 10/2022 must appear in P2P lending semantic search"

def test_zero_result_logged_to_analytics(supabase):
    """Zero-result queries must appear in search_analytics."""
    query = "peraturan tidak ada sama sekali xyzzy12345"
    supabase.rpc("search_regulations", {
        "p_query": query,
        "p_limit": 5,
        "p_query_embedding": None,
    }).execute()
    analytics = supabase.table("search_analytics").select("*").eq("query", query).execute()
    assert analytics.data
    assert analytics.data[0]["zero_results"] == True
```

### `apply_revision()` correctness

```python
def test_apply_revision_immutable_history(supabase_admin):
    """apply_revision must insert into revisions and update content_text atomically."""
    node_id = 1  # known test node
    original = supabase_admin.table("document_nodes").select("content_text").eq("id", node_id).single().execute()

    supabase_admin.rpc("apply_revision", {
        "p_node_id": node_id,
        "p_new_content": "Konten yang diperbarui untuk pengujian",
        "p_reason": "Test correction",
        "p_actor": "test-runner",
    }).execute()

    updated = supabase_admin.table("document_nodes").select("content_text, embedding").eq("id", node_id).single().execute()
    assert updated.data["content_text"] == "Konten yang diperbarui untuk pengujian"
    assert updated.data["embedding"] is None, "apply_revision must null embedding for backfill"

    revisions = supabase_admin.table("revisions").select("*").eq("node_id", node_id).order("created_at", desc=True).limit(1).execute()
    assert revisions.data
    assert revisions.data[0]["old_content"] == original.data["content_text"]
```

### Concurrent job claiming (SKIP LOCKED)

```python
import asyncio

async def test_claim_jobs_no_duplicate_claims(supabase_admin):
    """Two concurrent workers must not claim the same job."""
    supabase_admin.table("crawl_jobs").insert([
        {"regulation_type": "POJK", "status": "pending"} for _ in range(10)
    ]).execute()

    async def claim():
        return supabase_admin.rpc("claim_jobs", {"p_limit": 3}).execute().data

    results = await asyncio.gather(*[claim() for _ in range(4)])
    all_claimed_ids = [job["id"] for batch in results for job in batch]
    assert len(all_claimed_ids) == len(set(all_claimed_ids)), "Duplicate job claims detected"
```

---

## End-to-End (Playwright)

```bash
cd apps/web
npm run test:e2e     # All E2E tests
npm run test:e2e -- --headed  # With visible browser
```

### Critical flows

```typescript
// tests/e2e/search.spec.ts
import { test, expect } from "@playwright/test"

test("search for 'fintech' returns at least 5 results", async ({ page }) => {
  await page.goto("/search?q=fintech")
  await page.waitForSelector("[data-testid='search-result']")
  const results = await page.$$("[data-testid='search-result']")
  expect(results.length).toBeGreaterThanOrEqual(5)
})

test("regulation detail page renders pasal content", async ({ page }) => {
  await page.goto("/regulasi/pojk/pojk-10-2022")
  await page.waitForSelector("h1")
  expect(await page.title()).toContain("LPBBTI")
  const pasals = await page.$$("[data-testid='pasal-content']")
  expect(pasals.length).toBeGreaterThan(0)
})

test("correction form submits successfully", async ({ page }) => {
  await page.goto("/regulasi/pojk/pojk-10-2022")
  await page.click("[data-testid='report-correction-btn']")
  await page.fill("[name='suggested_content']", "Konten yang benar untuk pengujian ini.")
  await page.fill("[name='reason']", "Alasan koreksi untuk pengujian.")
  await page.click("button[type='submit']")
  await expect(page.locator("[data-testid='success-toast']")).toBeVisible()
})

test("zero-result search shows empty state", async ({ page }) => {
  await page.goto("/search?q=xyzzy12345notaregulation")
  await page.waitForSelector("[data-testid='empty-state']")
  const empty = await page.$("[data-testid='empty-state']")
  expect(empty).toBeTruthy()
})

test("sector browse page loads fintech regulations", async ({ page }) => {
  await page.goto("/sektor/fintech")
  await page.waitForSelector("[data-testid='regulation-card']")
  const cards = await page.$$("[data-testid='regulation-card']")
  expect(cards.length).toBeGreaterThan(0)
})
```

---

## Load Testing (k6)

Pre-release manual run only. Tests production-like query volume.

```javascript
// tests/load/search.js
import http from "k6/http"
import { check } from "k6"

export const options = {
  vus: 50,
  duration: "30s",
  thresholds: {
    http_req_duration: ["p(95)<2000"],   // 95th percentile < 2 seconds
    http_req_failed: ["rate<0.01"],       // < 1% error rate
  },
}

const QUERIES = ["fintech", "perbankan", "pojk 10 2022", "modal minimum p2p", "asuransi jiwa"]

export default function () {
  const q = QUERIES[Math.floor(Math.random() * QUERIES.length)]
  const resp = http.post(
    "https://api.regulasi.id/api/v1/search",
    JSON.stringify({ q, limit: 10 }),
    { headers: { "Content-Type": "application/json" } }
  )
  check(resp, {
    "status 200": (r) => r.status === 200,
    "has results field": (r) => JSON.parse(r.body).results !== undefined,
    "response < 2s": (r) => r.timings.duration < 2000,
  })
}
```

Run:
```bash
k6 run tests/load/search.js
```

If `p(95)` approaches 2s, check Supabase slow query log. Common culprits: FTS on large result sets, hnsw index not being used (check `EXPLAIN ANALYZE`).

---

## Test Data Seed

```bash
python scripts/seed_test_db.py
```

Seeds 50 realistic OJK regulations (POJK + SEOJK) across 5 sectors with realistic article structure. Includes:
- 3 known regulations with specific slugs for E2E tests (`pojk-10-2022`, `pojk-77-2016`, `seojk-12-2018`)
- Compliance mappings for fintech/p2p-lending
- A suggestion in `pending` state for admin tests
- Pre-generated embeddings stored in fixture JSON — no OpenAI calls during seed

```python
# scripts/seed_test_db.py
import json, os
from supabase import create_client

def seed():
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    fixture = json.load(open("tests/fixtures/seed_data.json"))
    sb.table("works").upsert(fixture["works"], on_conflict="slug").execute()
    sb.table("document_nodes").upsert(fixture["nodes"], on_conflict="id").execute()
    sb.table("compliance_mappings").upsert(fixture["mappings"]).execute()
    print(f"Seeded {len(fixture['works'])} works, {len(fixture['nodes'])} nodes")

if __name__ == "__main__":
    seed()
```

---

## What NOT to test

- Tailwind CSS class names — test behavior, not presentation
- shadcn/ui internals — trust the library
- SQL migration idempotency — migrations are append-only, never re-run
- OpenAI embedding quality — non-deterministic; test that the API call was made with correct inputs

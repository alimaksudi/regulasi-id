# Testing

Four layers: unit, integration, E2E, and load tests. Migrations tested in CI before production.

---

## Running Tests

```bash
# Unit + integration (from apps/web/)
cd apps/web
npm run test          # Vitest watch mode
npm run test:run      # Single run (CI)
npm run test:coverage # With coverage

# MCP server (from apps/mcp-server/)
cd apps/mcp-server
python -m pytest -v
python -m pytest test_server.py::test_rate_limiter -v  # specific test

# E2E (dev server must be running)
cd apps/web
npm run test:e2e

# Load test
cd tests/load
k6 run search.js --vus 50 --duration 30s
```

---

## Unit Tests — Vitest

Location: `apps/web/src/**/*.test.ts`

### What to test

- Search result grouping (`src/lib/search.ts` — `groupResultsByWork`)
- Slug parsing (`src/lib/works.ts` — `parseSlug`, `generateSlug`)
- FRBR URI construction
- Cursor encode/decode (`src/lib/pagination.ts`)
- Status label mapping
- Metadata helpers (`src/lib/i18n-metadata.ts` — `getAlternates`)
- Zod schema validation (valid + invalid inputs for each API route schema)

### Example

```typescript
// src/lib/pagination.test.ts
import { describe, it, expect } from "vitest"
import { encodeCursor, decodeCursor } from "./pagination"

describe("cursor pagination", () => {
  it("encodes and decodes cursor stably", () => {
    const original = { year: 2022, id: 42 }
    const cursor = encodeCursor(original)
    expect(decodeCursor(cursor)).toEqual(original)
  })

  it("cursor is base64url (no +/= chars)", () => {
    const cursor = encodeCursor({ year: 2022, id: 42 })
    expect(cursor).not.toMatch(/[+/=]/)
  })
})

// src/lib/schemas/search.test.ts
import { describe, it, expect } from "vitest"
import { SearchSchema } from "./search"

describe("SearchSchema", () => {
  it("rejects missing q", () => {
    const result = SearchSchema.safeParse({})
    expect(result.success).toBe(false)
    expect(result.error?.flatten().fieldErrors.q).toBeDefined()
  })

  it("coerces limit string to number", () => {
    const result = SearchSchema.safeParse({ q: "fintech", limit: "5" })
    expect(result.success).toBe(true)
    expect(result.data?.limit).toBe(5)
  })

  it("clamps limit to 50", () => {
    const result = SearchSchema.safeParse({ q: "test", limit: "999" })
    expect(result.success).toBe(false)
  })
})
```

---

## Integration Tests — Vitest + real Supabase

Location: `apps/web/src/**/*.integration.test.ts`

Uses a dedicated test Supabase project. Set in `apps/web/.env.test`:

```env
SUPABASE_TEST_URL=https://test-project.supabase.co
SUPABASE_TEST_ANON_KEY=eyJ...
SUPABASE_TEST_SERVICE_KEY=eyJ...
```

### What to test

**Search:**
- `search_regulations` RPC returns results for known Indonesian queries
- Identity fast path: `"pojk 10 2022"` returns score 1000
- Hybrid search: `"pendanaan bersama"` finds `LPBBTI` (synonym mapping)
- Zero-result queries are logged to `search_analytics`
- Sector filter reduces result set
- Status filter excludes dicabut regulations

**Works:**
- `getWorkBySlug` resolves all three slug formats
- ISR cache tag invalidation works after `revalidateTag`

**Suggestions:**
- POST to `/api/suggestions` creates a row with `status=pending`
- Rate limit blocks after 10 requests/hour

**apply_revision:**
- Atomically creates revision + updates content + marks suggestion approved
- Node `embedding` is set to NULL after revision (triggers regen)

**RLS:**
- Anon key cannot read `crawl_jobs`
- Anon key cannot read `revisions`
- Anon key can read `works`, `document_nodes`, `abstracts`

**claim_jobs:**
- Two concurrent calls don't claim the same job (SKIP LOCKED test)

```typescript
// src/lib/search.integration.test.ts
describe("search_regulations RPC", () => {
  it("identity path: 'pojk 10 2022' scores 1000", async () => {
    const { data } = await sb.rpc("search_regulations", {
      p_query: "pojk 10 2022", p_limit: 1
    })
    expect(data[0].score).toBe(1000)
  })

  it("hybrid: concept query finds relevant regulations", async () => {
    const { data } = await sb.rpc("search_regulations", {
      p_query: "layanan pinjam meminjam uang berbasis teknologi", p_limit: 5
    })
    expect(data.length).toBeGreaterThan(0)
    // Should find POJK 10/2022 (LPBBTI) even without exact term match
    expect(data.some((r: any) => r.number === "10" && r.year === 2022)).toBe(true)
  })

  it("logs zero-result queries to search_analytics", async () => {
    const before = await sbService.from("search_analytics")
      .select("id", { count: "exact" }).eq("zero_results", true).execute()

    await sb.rpc("search_regulations", { p_query: "zxzxzxzx_nonexistent_term", p_limit: 10 })

    const after = await sbService.from("search_analytics")
      .select("id", { count: "exact" }).eq("zero_results", true).execute()

    expect(after.count).toBe(before.count! + 1)
  })
})
```

---

## MCP Server Tests — pytest

Location: `apps/mcp-server/test_server.py`

### What to test

- All 5 tools return valid response shapes
- `search_regulations`: hybrid path + identity path
- `get_article`: exact text, correct ayat structure
- `get_regulation_status`: correct for berlaku, dicabut regulations
- `get_compliance_checklist`: non-empty for `sector=fintech`
- Rate limiter: blocks after limit (mock Upstash or use test Redis)
- Cache: second `get_article` call hits Redis (verify with mock)
- Startup: server refuses to start with service role key as anon key

```python
# test_server.py
import pytest
from unittest.mock import patch, AsyncMock
from fastmcp.testing import MCPTestClient
from server import mcp

@pytest.fixture
def client():
    return MCPTestClient(mcp)

def test_ping_includes_coverage(client):
    result = client.call_tool("ping")
    assert "embedding coverage" in result.lower()

def test_search_returns_semantic_flag(client):
    result = client.call_tool("search_regulations", {"query": "pembiayaan modal kerja"})
    assert isinstance(result, list)
    if result:
        assert "semantic_used" in result[0]

def test_get_article_ayat_structure(client):
    # Use a known regulation in test DB
    result = client.call_tool("get_article", {
        "regulation_type": "POJK", "number": "10", "year": 2022, "article_number": "1"
    })
    assert "ayat" in result
    assert isinstance(result["ayat"], list)

@patch("server.redis")
def test_get_article_caches_result(mock_redis, client):
    mock_redis.get.return_value = None  # cold cache
    mock_redis.set = AsyncMock()

    client.call_tool("get_article", {
        "regulation_type": "POJK", "number": "10", "year": 2022, "article_number": "1"
    })
    mock_redis.set.assert_called_once()  # cached after first call

def test_rate_limit_blocks_after_limit(client):
    # 30 calls should pass, 31st should raise
    for _ in range(30):
        client.call_tool("search_regulations", {"query": "test"})
    with pytest.raises(Exception, match="Rate limit"):
        client.call_tool("search_regulations", {"query": "test"})
```

---

## E2E Tests — Playwright

Location: `apps/web/e2e/`

```bash
npx playwright install chromium  # first time
npm run test:e2e
```

### Critical paths

**Search flow (must pass on every PR):**
```
1. Homepage loads, search box visible
2. Type "penyelenggaraan fintech" → results within 2s
3. First result: title + regulation type badge + status badge
4. Click result → regulation detail page
5. Title, number, year, status all visible
6. At least 5 pasals loaded with non-empty content text
7. "Laporkan Kesalahan" button visible
```

**Hybrid search — semantic test:**
```
1. Search "modal minimum p2p" (not exact article text)
2. Results include POJK 10/2022 (known to contain modal requirements)
3. Snippet highlights the relevant content
```

**Browse by sector:**
```
1. /sektor — 6 sector cards, each with regulation count
2. Click "Fintech" → /sektor/fintech
3. List shows ≥1 regulation
4. Year filter works
5. Type filter (POJK) reduces results
```

**Regulation detail:**
```
1. /regulasi/pojk/pojk-10-2022 loads
2. Status badge: Berlaku (green)
3. BAB navigation: clicking BAB I scrolls to section
4. Pasal numbers in font-mono
5. "Lihat PDF" → valid Supabase Storage URL
6. Amendment banner if regulation has relationships
```

**Suggestion submission:**
```
1. Open any pasal
2. Click "Laporkan Kesalahan"
3. Fill: current (pre-filled), suggestion, reason
4. Submit → "Terima kasih" confirmation
5. DB: suggestions table has new row with status=pending
```

**API docs:**
```
1. /api-docs loads Swagger UI
2. GET /api/v1/search is listed
3. "Try it out" → "fintech" query → results appear
```

**404 handling:**
```
1. /regulasi/pojk/pojk-99999-2099 → 404 page, not crash
2. /api/v1/regulations/akn/id/act/pojk/9999/0 → JSON { error: "Not found" }
3. /api/v1/search (no q) → 400 with Zod error details
```

**Mobile (375px viewport):**
```
1. Nav collapses to hamburger
2. Search full-width
3. Regulation cards readable, no horizontal overflow
4. Pasal content readable
```

### Playwright config

```typescript
// playwright.config.ts
export default {
  testDir: "./e2e",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    locale: "id-ID",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile",  use: { ...devices["iPhone 12"] } },
  ],
}
```

---

## Load Tests — k6

Location: `tests/load/`

Test under realistic concurrent load before launch.

```javascript
// tests/load/search.js
import http from "k6/http"
import { sleep, check } from "k6"

const BASE = __ENV.BASE_URL || "https://regulasi.id"
const QUERIES = ["fintech", "perbankan modal", "pojk 10 2022", "kredit konsumtif", "asuransi jiwa"]

export let options = {
  stages: [
    { duration: "30s", target: 10 },   // ramp up
    { duration: "60s", target: 50 },   // sustained load
    { duration: "10s", target: 0 },    // ramp down
  ],
  thresholds: {
    http_req_duration: ["p(95)<2000"],  // 95th percentile < 2s
    http_req_failed:   ["rate<0.01"],   // < 1% errors
  },
}

export default function () {
  const q = QUERIES[Math.floor(Math.random() * QUERIES.length)]
  const res = http.get(`${BASE}/api/v1/search?q=${encodeURIComponent(q)}&limit=10`)
  check(res, {
    "status 200":    (r) => r.status === 200,
    "has results":   (r) => JSON.parse(r.body).results?.length > 0,
    "response < 2s": (r) => r.timings.duration < 2000,
  })
  sleep(1)
}
```

```bash
# Install k6
brew install k6

# Local load test
k6 run tests/load/search.js --vus 50 --duration 30s

# Against staging
k6 run tests/load/search.js --vus 50 --duration 60s \
  -e BASE_URL=https://staging.regulasi.id
```

Targets: p95 search < 2s, p95 detail < 500ms, error rate < 1% at 50 concurrent users.

---

## Migration CI

Every migration is applied to a test Supabase project in CI. Block merge if migration fails.

```yaml
# .github/workflows/ci.yml
jobs:
  db-migrations:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Apply migrations to test DB
        env:
          SUPABASE_DB_URL: ${{ secrets.SUPABASE_TEST_DB_URL }}  # direct, port 5432
        run: |
          for f in $(ls packages/supabase/migrations/*.sql | sort); do
            echo "Applying $f..."
            psql "$SUPABASE_DB_URL" -f "$f"
          done

  test-web:
    runs-on: ubuntu-latest
    needs: db-migrations
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: cd apps/web && npm ci
      - run: cd apps/web && npm run lint
      - run: cd apps/web && npx tsc --noEmit
      - run: cd apps/web && npm run test:run
      env:
        SUPABASE_TEST_URL: ${{ secrets.SUPABASE_TEST_URL }}
        SUPABASE_TEST_ANON_KEY: ${{ secrets.SUPABASE_TEST_ANON_KEY }}
        UPSTASH_REDIS_REST_URL: ${{ secrets.UPSTASH_TEST_REDIS_URL }}
        UPSTASH_REDIS_REST_TOKEN: ${{ secrets.UPSTASH_TEST_REDIS_TOKEN }}

  test-mcp:
    runs-on: ubuntu-latest
    needs: db-migrations
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: cd apps/mcp-server && pip install -r requirements.txt
      - run: cd apps/mcp-server && python -m pytest -v
      env:
        SUPABASE_URL: ${{ secrets.SUPABASE_TEST_URL }}
        SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_TEST_ANON_KEY }}
        UPSTASH_REDIS_REST_URL: ${{ secrets.UPSTASH_TEST_REDIS_URL }}
        UPSTASH_REDIS_REST_TOKEN: ${{ secrets.UPSTASH_TEST_REDIS_TOKEN }}
```

**Rule:** Never apply a migration to production until it passes migration CI.

---

## Test Data

Dedicated test Supabase project (separate from production). Seed script: `scripts/seed_test_db.py`.

Minimum seed:
- 3 sectors: fintech, perbankan, pasar-modal
- 5 regulations across sectors — including 1 dicabut, 1 diubah, 3 berlaku
- 1 regulation with `work_relationships` (diubah_oleh)
- 30+ pasals with real content text
- 5 embeddings (pgvector) for semantic search test
- 1 compliance_mapping for sector=fintech, business_type=p2p-lending
- 1 pending suggestion

---

## Coverage Targets

| Layer | Target | Run in CI |
|-------|--------|-----------|
| Unit (Vitest) | 80% on `src/lib/` | Yes |
| Integration | All RPC calls, all API routes | Yes |
| E2E critical paths | All paths listed above | Yes (staging) |
| MCP tools | All 5 tools + rate limiter + cache | Yes |
| Load | p95 < 2s at 50 VUs | Before launch only |
| Migration | Every migration applies cleanly | Yes, on every PR |

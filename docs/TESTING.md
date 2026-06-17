# Testing

Three layers: unit tests, integration tests, and E2E tests.

---

## Running Tests

```bash
# Unit + integration (from apps/web/)
cd apps/web
npm run test          # Vitest watch mode
npm run test:run      # Single run (CI)
npm run test:coverage # With coverage report

# MCP server tests (from apps/mcp-server/)
cd apps/mcp-server
python -m pytest -v

# E2E (from apps/web/, requires dev server running)
npm run test:e2e      # Playwright
```

---

## Unit Tests — Vitest

Location: `apps/web/src/**/*.test.ts`

### What to unit test

- Search result grouping logic (`src/lib/search.ts` — `groupResultsByWork`)
- Slug parsing (`src/lib/works.ts` — `parseSlug`, `generateSlug`)
- FRBR URI construction
- Status label mapping
- Metadata helpers (`src/lib/i18n-metadata.ts` — `getAlternates`)
- Input sanitization (query param validation in API routes)

### Example

```typescript
// src/lib/search.test.ts
import { describe, it, expect } from "vitest"
import { groupResultsByWork } from "./search"

describe("groupResultsByWork", () => {
  it("keeps highest-score chunk per work", () => {
    const chunks = [
      { work_id: 1, score: 5, snippet: "a" },
      { work_id: 1, score: 12, snippet: "b" },
      { work_id: 2, score: 3, snippet: "c" },
    ]
    const result = groupResultsByWork(chunks)
    expect(result).toHaveLength(2)
    expect(result[0].score).toBe(12)
  })

  it("sorts by score descending", () => {
    // ...
  })
})
```

---

## Integration Tests — Vitest + real Supabase

Location: `apps/web/src/**/*.integration.test.ts`

These hit the real Supabase test project (separate from production). Set `SUPABASE_TEST_URL` and `SUPABASE_TEST_ANON_KEY` in `apps/web/.env.test`.

### What to integration test

- `search_regulations` RPC returns results for known queries
- `getWorkBySlug` resolves all three slug formats (direct, parseSlug fallback, strip trailing year)
- `apply_revision` atomically updates node + inserts revision row
- `claim_jobs` uses `SKIP LOCKED` correctly under concurrent workers
- RLS: anon key cannot read `crawl_jobs`, can read `works`

### Example

```typescript
// src/lib/works.integration.test.ts
import { describe, it, expect } from "vitest"
import { createClient } from "@supabase/supabase-js"

const sb = createClient(process.env.SUPABASE_TEST_URL!, process.env.SUPABASE_TEST_ANON_KEY!)

describe("search_regulations RPC", () => {
  it("returns results for 'fintech'", async () => {
    const { data, error } = await sb.rpc("search_regulations", { p_query: "fintech", p_limit: 5 })
    expect(error).toBeNull()
    expect(data.length).toBeGreaterThan(0)
  })

  it("identity fast-path: 'pojk 10 2022' returns POJK 10/2022 at score 1000", async () => {
    const { data } = await sb.rpc("search_regulations", { p_query: "pojk 10 2022", p_limit: 1 })
    expect(data[0].score).toBe(1000)
    expect(data[0].number).toBe("10")
  })
})
```

---

## MCP Server Tests — pytest

Location: `apps/mcp-server/test_server.py`

### What to test

- All 5 tools return valid response shapes
- `search_regulations` returns results for known queries
- `get_article` returns exact pasal text
- `get_regulation_status` returns correct status for a known revoked regulation
- `get_compliance_checklist` returns non-empty for `sector=fintech`
- Rate limiter blocks after limit
- Cache: second call returns cached result (check TTL key exists)
- Server refuses to start with `SUPABASE_SERVICE_ROLE_KEY` as `SUPABASE_ANON_KEY`

```python
# test_server.py
import pytest
from fastmcp.testing import MCPTestClient
from server import mcp

@pytest.fixture
def client():
    return MCPTestClient(mcp)

def test_ping(client):
    result = client.call_tool("ping")
    assert "regulasi-id" in result

def test_search_returns_results(client):
    result = client.call_tool("search_regulations", {"query": "kredit"})
    assert len(result) > 0
    assert "frbr_uri" in result[0]

def test_unknown_regulation_returns_404_message(client):
    result = client.call_tool("get_article", {
        "regulation_type": "POJK",
        "number": "999",
        "year": 1900,
        "article_number": "1"
    })
    assert "not found" in result.get("error", "").lower()
```

---

## E2E Tests — Playwright

Location: `apps/web/e2e/`

Run against `http://localhost:3000` (dev server) or staging URL.

```bash
npx playwright install  # first time
npm run test:e2e
```

### Test plan

#### Search flow (critical path)
```
1. Land on homepage → search box is visible and focused
2. Type "penyelenggaraan fintech" → results appear within 2s
3. First result has a regulation title, type badge, and status badge
4. Click result → navigate to regulation detail page
5. Detail page shows: title, number, year, status, full pasal list
6. Pasal text is readable and not empty
7. "Laporkan Kesalahan" button opens suggestion modal
```

#### Browse by sector
```
1. Navigate to /sektor
2. Six sector cards are visible
3. Click "Fintech" → /sektor/fintech loads
4. Regulation list shows at least 1 result
5. Filter by year works (reduces result count)
6. Filter by type "POJK" works
```

#### Regulation detail
```
1. Navigate to /regulasi/pojk/pojk-10-2022 (or known test slug)
2. Title is displayed in full Indonesian
3. Status badge shows correct status
4. BAB structure is navigable (clicking BAB scrolls to section)
5. Pasal numbers are in font-mono
6. "Lihat PDF" link points to a valid Supabase Storage URL
```

#### MCP connect page
```
1. Navigate to /connect
2. Copy button copies correct MCP URL to clipboard
3. URL has no trailing slash
```

#### Suggestion submission
```
1. Open any pasal detail
2. Click "Laporkan Kesalahan"
3. Fill in suggestion form
4. Submit → success message appears
5. DB: suggestions table has 1 new row with status=pending
```

#### 404 handling
```
1. /regulasi/pojk/pojk-99999-2099 → shows a 404 page, not a crash
2. /api/v1/regulations/akn/id/act/pojk/9999/0 → returns JSON { error: "Not found" }
```

#### Responsive (mobile 375px)
```
1. Header nav collapses to hamburger
2. Search input spans full width
3. Regulation card text doesn't overflow
4. Pasal content is readable without horizontal scroll
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
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["iPhone 12"] } },
  ],
}
```

---

## CI Pipeline

```yaml
# .github/workflows/ci.yml
jobs:
  test:
    runs-on: ubuntu-latest
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

  test-mcp:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: cd apps/mcp-server && pip install -r requirements.txt
      - run: cd apps/mcp-server && python -m pytest -v
      env:
        SUPABASE_URL: ${{ secrets.SUPABASE_TEST_URL }}
        SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_TEST_ANON_KEY }}
```

---

## Test Data

Use a dedicated Supabase **test project** (separate from production). Seed it with:

- At least 3 regulations across 2 sectors
- One regulation with status `dicabut` and a `diubah_oleh` relationship
- At least 10 pasals with content text
- One entry in `compliance_mappings` for `sector=fintech`

Seed script: `scripts/seed_test_db.py`

---

## Coverage Targets

| Layer | Target |
|-------|--------|
| Unit (Vitest) | 80% on `src/lib/` |
| Integration | All API routes, all RPC calls |
| E2E | All critical paths above — no exceptions |
| MCP | All 5 tools + rate limiter + cache |

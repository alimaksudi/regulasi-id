# Public REST API

**Base URL:** `https://api.regulasi.id`

Deployed on Cloudflare Workers (Hono.js). Runs at the edge — near-zero cold start, global distribution.

All inputs validated with Zod. All list endpoints cursor-paginated. OpenAPI 3.1 spec at `/api/openapi.json`. Interactive docs at `https://regulasi.id/api-docs`.

---

## Why Hono on Workers (not Next.js API routes)

- Cloudflare Workers have < 1ms cold starts (V8 isolates) vs Next.js serverless 200ms+
- Server-side secrets (OpenAI API key for embeddings) never touch the browser
- Globally distributed — Indonesian users hit Singapore/Asia edge nodes
- Independently deployable from the frontend

---

## Authentication

Public endpoints: no auth. Rate limited via Upstash Redis (shared across all edge instances — not in-memory).

Admin endpoints: require `Authorization: Bearer <jwt>` header. JWT issued by Supabase Auth on login, verified server-side in Cloudflare Workers.

---

## Search

`POST /api/v1/search`

Hybrid search: generates a query embedding server-side (OpenAI), then calls `search_regulations()` with both the text query and embedding. RRF reranking combines keyword and semantic scores.

**Why POST:** the query embedding generation happens server-side before the DB call. GET doesn't carry a body cleanly across edge infrastructure.

### Request body (Zod-validated)

```json
{
  "q": "modal minimum p2p lending",
  "sector": "fintech",
  "type": "POJK",
  "year_from": 2020,
  "year_to": null,
  "status": "berlaku",
  "limit": 10
}
```

| Field | Type | Constraints |
|-------|------|-------------|
| `q` | string | required, 1–500 chars |
| `sector` | string | optional, enum |
| `type` | string | optional, comma-separated enum |
| `year_from` | integer | optional, 1945–2099 |
| `year_to` | integer | optional, ≥ year_from |
| `status` | string | optional, comma-separated enum |
| `limit` | integer | 1–50, default 10 |

### Response

```json
{
  "query": "modal minimum p2p lending",
  "total": 5,
  "semantic_used": true,
  "results": [
    {
      "work_id": 42,
      "snippet": "...modal disetor paling sedikit sebesar <mark>Rp50.000.000.000</mark>...",
      "score": 14.7,
      "rrf_rank": 1,
      "matching_pasals": ["Pasal 24", "Pasal 25"],
      "work": {
        "frbr_uri": "/akn/id/act/pojk/2022/10",
        "title": "POJK tentang Penyelenggaraan Layanan Pendanaan Bersama Berbasis Teknologi Informasi",
        "number": "10",
        "year": 2022,
        "status": "berlaku",
        "type": "POJK",
        "sector": "fintech"
      }
    }
  ]
}
```

Rate limit: 60/min/IP. Embedding cached in Upstash by query hash (TTL 1h) — repeated queries don't call OpenAI.

---

## List Regulations

`GET /api/v1/regulations`

Cursor-based pagination. Stable under concurrent inserts. O(log N) regardless of depth.

### Query params

| Param | Description |
|-------|-------------|
| `sector` | Filter by sector code |
| `type` | Filter by regulation type (multi: `POJK,SEOJK`) |
| `year` | Exact year |
| `year_from` | Range lower bound |
| `year_to` | Range upper bound |
| `status` | `berlaku` \| `diubah` \| `dicabut` |
| `cursor` | Opaque cursor from previous `next_cursor` |
| `per_page` | 1–100, default 20 |

### Response

```json
{
  "total": 487,
  "next_cursor": "eyJ5ZWFyIjoyMDIyLCJpZCI6NDJ9",
  "regulations": [
    {
      "frbr_uri": "/akn/id/act/pojk/2022/10",
      "title": "...",
      "number": "10",
      "year": 2022,
      "status": "berlaku",
      "type": "POJK",
      "sector": "fintech",
      "date_enacted": "2022-03-28"
    }
  ]
}
```

Pass `cursor` from `next_cursor` in the next request. `next_cursor` is `null` when exhausted.

---

## Get Regulation

`GET /api/v1/regulations/akn/id/act/pojk/2022/10`

Full regulation with hierarchical nodes. CDN-cached 24h by `Cache-Control` header.

### Response

```json
{
  "work": {
    "frbr_uri": "/akn/id/act/pojk/2022/10",
    "title": "POJK tentang Penyelenggaraan LPBBTI",
    "number": "10",
    "year": 2022,
    "status": "berlaku",
    "date_enacted": "2022-03-28",
    "source_url": "http://jdih.ojk.go.id/...",
    "sector": "fintech",
    "type": "POJK",
    "has_abstract": true,
    "has_faq": true,
    "related": [
      { "relationship": "Mengubah", "frbr_uri": "/akn/id/act/pojk/2016/77", "title": "..." }
    ]
  },
  "nodes": [
    { "id": 1234, "node_type": "bab", "number": "I", "heading": "KETENTUAN UMUM", "sort_order": 100 },
    { "id": 1235, "node_type": "pasal", "number": "1", "content_text": "Dalam Peraturan ini...", "sort_order": 200 }
  ]
}
```

---

## Sectors

`GET /api/v1/sectors`

Served from Upstash cache (populated from `mv_sector_stats`). Cache TTL 15 min. No DB hit on cache hit.

`Cache-Control: public, max-age=900, stale-while-revalidate=3600`

### Response

```json
{
  "sectors": [
    {
      "code": "fintech",
      "name_id": "Teknologi Finansial",
      "name_en": "Financial Technology",
      "regulation_count": 47,
      "berlaku_count": 39,
      "latest_year": 2025
    }
  ]
}
```

---

## Compliance Checklist

`GET /api/v1/compliance?sector=fintech&business_type=p2p-lending`

Returns curated list of applicable regulations from `compliance_mappings` table.

### Response

```json
{
  "sector": "fintech",
  "business_type": "p2p-lending",
  "required_regulations": [
    {
      "frbr_uri": "/akn/id/act/pojk/2022/10",
      "title": "POJK tentang LPBBTI",
      "type": "POJK",
      "number": "10",
      "year": 2022,
      "status": "berlaku",
      "priority": "required",
      "notes": "Primary licensing regulation for P2P lending (LPBBTI) operators"
    }
  ]
}
```

---

## Submit Correction

`POST /api/suggestions`

Rate limited: 10/IP/hour (Upstash).

### Request body

```json
{
  "work_id": 42,
  "node_id": 1235,
  "current_content": "Dalam Peraturan ini yang dimaksud dengan...",
  "suggested_content": "Dalam Peraturan Otoritas Jasa Keuangan ini yang dimaksud dengan...",
  "reason": "Kata 'Otoritas Jasa Keuangan' tidak lengkap",
  "email": "user@example.com"
}
```

### Response

```json
{ "id": 99, "status": "pending" }
```

---

## OpenAPI

`GET /api/openapi.json`

Auto-generated OpenAPI 3.1 spec from Zod schemas via `@hono/zod-openapi`. Interactive Swagger UI at `https://regulasi.id/api-docs`.

Schemas shared between API validation and frontend TypeScript types via `packages/shared/schemas/`. Single source of truth — no schema drift.

---

## Error Format

```json
{
  "error": "Human-readable message in Indonesian",
  "code": "VALIDATION_ERROR",
  "details": {
    "q": ["Wajib diisi"],
    "limit": ["Maksimal 50"]
  }
}
```

HTTP status codes:
- `400` — Zod validation failure (with `details`)
- `404` — Not found
- `429` — Rate limit exceeded (with `retry_after_seconds`)
- `500` — Internal error (Sentry reference ID)

---

## Rate Limits

Upstash Redis sliding window. Enforced across all Cloudflare edge instances.

| Endpoint | Limit | Window |
|----------|-------|--------|
| `POST /api/v1/search` | 60 | 1 min |
| `GET /api/v1/regulations` | 60 | 1 min |
| `GET /api/v1/regulations/*` | 120 | 1 min |
| `GET /api/v1/sectors` | no limit | edge cached |
| `GET /api/v1/compliance` | 60 | 1 min |
| `POST /api/suggestions` | 10 | 1 hour |

High-volume API consumers: contact for an API key tier with lifted limits.

---

## CORS

```
Access-Control-Allow-Origin: https://regulasi.id
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization
```

For local development, Wrangler dev allows `http://localhost:3000`.

---

## Hono Implementation Pattern

```typescript
// apps/api/src/routes/search.ts
import { Hono } from "hono"
import { zValidator } from "@hono/zod-validator"
import { SearchSchema } from "@regulasi-id/shared/schemas"

const search = new Hono<{ Bindings: Env }>()

search.post("/",
  zValidator("json", SearchSchema),
  async (c) => {
    const body = c.req.valid("json")

    // 1. Check rate limit
    const ip = c.req.header("CF-Connecting-IP") ?? "unknown"
    const { success } = await checkRateLimit(c.env, `search:${ip}`, { max: 60, window: "60s" })
    if (!success) return c.json({ error: "Terlalu banyak permintaan. Coba lagi nanti." }, 429)

    // 2. Cache embedding by query hash
    const embeddingKey = `emb:${hashQuery(body.q)}`
    let embedding = await getCache<number[]>(c.env, embeddingKey)
    if (!embedding) {
      embedding = await generateEmbedding(body.q, c.env.OPENAI_API_KEY)
      await setCache(c.env, embeddingKey, embedding, { ex: 3600 })
    }

    // 3. Call hybrid search RPC
    const sb = createSupabaseClient(c.env.SUPABASE_URL, c.env.SUPABASE_ANON_KEY)
    const { data, error } = await sb.rpc("search_regulations", {
      p_query: body.q,
      p_sector: body.sector ?? null,
      p_limit: body.limit,
      p_query_embedding: embedding,
    })

    if (error) {
      await captureError(error, c.env.SENTRY_DSN)
      return c.json({ error: "Pencarian gagal. Coba lagi." }, 500)
    }

    // 4. Log to analytics (fire-and-forget)
    c.executionCtx.waitUntil(
      logSearchAnalytics(sb, { query: body.q, result_count: data.length, source: "api" })
    )

    return c.json({ query: body.q, total: data.length, semantic_used: true, results: data })
  }
)
```

---

## URL Formats

**FRBR URI:** `/akn/id/act/{type}/{year}/{number}`
- `/akn/id/act/pojk/2022/10`

**Slug:** `{type}-{number}-{year}`
- `pojk-10-2022`

Web URL: `https://regulasi.id/regulasi/pojk/pojk-10-2022`
API URL: `https://api.regulasi.id/api/v1/regulations/akn/id/act/pojk/2022/10`

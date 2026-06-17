# Public REST API

Base URL: `https://regulasi.id/api/v1`

All inputs validated with Zod. All list endpoints use cursor pagination. OpenAPI 3.1 spec at `/api/openapi.json`. Interactive docs at `/api-docs`.

---

## Authentication

Public endpoints: no auth required.
Rate limits: Upstash Redis sliding window — shared across all server instances (not in-memory).

---

## Search

`GET /api/v1/search`

Hybrid search: TSVECTOR keyword + pgvector semantic + RRF reranking. Handles synonyms and concept queries that keyword-only search misses.

### Parameters (Zod-validated)

| Param | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `q` | string | required, 1–500 chars | Search query. Indonesian preferred. |
| `sector` | string | optional | `perbankan`, `pasar-modal`, `fintech`, `iknb`, `dana-pensiun`, `perasuransian`. Comma-separated for multi. |
| `type` | string | optional | `POJK`, `SEOJK`, `KEOJK`, `UU`, `PP`. Comma-separated. |
| `year` | integer | optional, 1945–2099 | Exact year. Mutually exclusive with `year_from`. |
| `year_from` | integer | optional | Lower bound year. |
| `year_to` | integer | optional | Upper bound year. |
| `status` | string | optional | `berlaku`, `diubah`, `dicabut`. Comma-separated. |
| `limit` | integer | 1–50, default 10 | Max results. |

### Response

```json
{
  "query": "p2p lending modal minimum",
  "total": 7,
  "semantic_used": true,
  "results": [
    {
      "work_id": 42,
      "snippet": "...modal disetor paling sedikit sebesar <mark>Rp50.000.000.000</mark>...",
      "score": 14.7,
      "rrf_rank": 1,
      "matching_pasals": ["Pasal 24", "Pasal 25"],
      "total_chunks": 12,
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

### Rate limit

60 requests/minute/IP. Response on limit: `429` with `retry_after_seconds`.

### Example

```bash
curl "https://regulasi.id/api/v1/search?q=kredit+pemilikan+rumah&sector=perbankan&status=berlaku"
curl "https://regulasi.id/api/v1/search?q=modal+minimum+fintech&type=POJK,SEOJK&year_from=2020"
```

---

## List Regulations

`GET /api/v1/regulations`

Cursor-based pagination. Stable under concurrent inserts. O(log N) regardless of page depth.

### Parameters

| Param | Type | Description |
|-------|------|-------------|
| `sector` | string | Filter by sector |
| `type` | string | Filter by regulation type |
| `year` | integer | Filter by exact year |
| `year_from` | integer | Year range lower bound |
| `year_to` | integer | Year range upper bound |
| `status` | string | `berlaku` \| `diubah` \| `dicabut` |
| `cursor` | string | Opaque cursor from `next_cursor` in previous response |
| `per_page` | integer | 1–100, default 20 |

### Response

```json
{
  "total": 487,
  "next_cursor": "eyJ5ZWFyIjoyMDIyLCJpZCI6NDJ9",
  "regulations": [
    {
      "frbr_uri": "/akn/id/act/pojk/2022/10",
      "title": "POJK tentang Penyelenggaraan Layanan Pendanaan Bersama Berbasis Teknologi Informasi",
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

`next_cursor` is `null` when there are no more pages. Pass it as `cursor=` on the next request.

---

## Get Regulation

`GET /api/v1/regulations/{frbr_path}`

Full regulation content. ISR-cached at the edge (24h).

### Path

```
/api/v1/regulations/akn/id/act/pojk/2022/10
→ POJK No. 10 Tahun 2022
```

### Response

```json
{
  "work": {
    "frbr_uri": "/akn/id/act/pojk/2022/10",
    "title": "POJK tentang Penyelenggaraan Layanan Pendanaan Bersama Berbasis Teknologi Informasi",
    "number": "10",
    "year": 2022,
    "status": "berlaku",
    "date_enacted": "2022-03-28",
    "source_url": "http://jdih.ojk.go.id/...",
    "sector": "fintech",
    "type": "POJK",
    "has_abstract": true,
    "has_faq": true
  },
  "nodes": [
    {
      "id": 1234,
      "node_type": "bab",
      "number": "I",
      "heading": "KETENTUAN UMUM",
      "content_text": null,
      "sort_order": 100,
      "parent_id": null
    },
    {
      "id": 1235,
      "node_type": "pasal",
      "number": "1",
      "heading": null,
      "content_text": "Dalam Peraturan ini yang dimaksud dengan...",
      "sort_order": 200,
      "parent_id": 1234
    }
  ]
}
```

---

## Sectors

`GET /api/v1/sectors`

Served from materialized view `mv_sector_stats`. O(1) — no live DB aggregation.

**Cache-Control:** `public, max-age=900, stale-while-revalidate=3600`

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
    },
    {
      "code": "perbankan",
      "name_id": "Perbankan",
      "name_en": "Banking",
      "regulation_count": 183,
      "berlaku_count": 147,
      "latest_year": 2025
    }
  ]
}
```

---

## Compliance Checklist

`GET /api/v1/compliance`

Returns all regulations applicable to a given sector and business type. Backed by the curated `compliance_mappings` table.

### Parameters

| Param | Type | Description |
|-------|------|-------------|
| `sector` | string | required |
| `business_type` | string | optional — returns sector-wide if omitted |

### Response

```json
{
  "sector": "fintech",
  "business_type": "p2p-lending",
  "required_regulations": [
    {
      "frbr_uri": "/akn/id/act/pojk/2022/10",
      "title": "POJK tentang Penyelenggaraan Layanan Pendanaan Bersama Berbasis Teknologi Informasi",
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

Rate limited: 10 requests/IP/hour (Upstash).

### Request body (Zod-validated)

```json
{
  "work_id": 42,
  "node_id": 1235,
  "current_content": "Dalam Peraturan ini yang dimaksud dengan...",
  "suggested_content": "Dalam Peraturan Otoritas Jasa Keuangan ini yang dimaksud dengan...",
  "reason": "Kata 'Otoritas Jasa Keuangan' hilang dari teks",
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

Auto-generated OpenAPI 3.1 spec from Zod schemas. No drift between validation and docs.

Interactive Swagger UI at `/api-docs`.

---

## Error Format

```json
{
  "error": "Human-readable message",
  "code": "VALIDATION_ERROR",
  "details": {
    "q": ["Required"],
    "limit": ["Must be between 1 and 50"]
  }
}
```

HTTP status codes:
- `400` — Zod validation failure (includes `details` field)
- `404` — Not found
- `429` — Rate limit exceeded (includes `retry_after_seconds`)
- `500` — Internal server error (reference ID from Sentry)

---

## Rate Limits

Upstash Redis sliding window — enforced across all server instances.

| Endpoint | Limit | Window |
|----------|-------|--------|
| `GET /api/v1/search` | 60 req | 1 min |
| `GET /api/v1/regulations` | 60 req | 1 min |
| `GET /api/v1/regulations/*` | 120 req | 1 min |
| `GET /api/v1/sectors` | no limit | — (edge-cached) |
| `GET /api/v1/compliance` | 60 req | 1 min |
| `POST /api/suggestions` | 10 req | 1 hour |

High-volume consumers: contact us for an API key tier with higher limits.

---

## CORS

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization
```

---

## URL formats

**FRBR URI:**
```
/akn/id/act/{type}/{year}/{number}
→ /akn/id/act/pojk/2022/10
```

**Slug:**
```
{type}-{number}-{year}
→ pojk-10-2022
```

Web URL: `https://regulasi.id/regulasi/pojk/pojk-10-2022`

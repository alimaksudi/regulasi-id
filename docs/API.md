# Public REST API

Base URL: `https://regulasi.id/api/v1`

All endpoints are public (no authentication), CORS-enabled, and rate-limited to 60 requests/minute per IP.

---

## Search

`GET /api/v1/search`

Full-text search across all OJK regulations.

### Parameters

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `q` | string | Yes | Search query. Indonesian preferred. |
| `sector` | string | No | `perbankan`, `pasar-modal`, `fintech`, `iknb`, `dana-pensiun`, `perasuransian`. Multi-value: `perbankan,fintech` |
| `type` | string | No | `POJK`, `SEOJK`, `KEOJK`, `UU`, `PP`. Multi-value: `POJK,SEOJK` |
| `year` | integer | No | Exact year (1945–present). Mutually exclusive with `year_from`. |
| `year_from` | integer | No | Lower bound year. |
| `status` | string | No | `berlaku`, `diubah`, `dicabut`. Multi-value: `berlaku,diubah` |
| `limit` | integer | No | 1–50. Default 10. |

### Response

```json
{
  "query": "p2p lending pendanaan",
  "total": 3,
  "results": [
    {
      "work_id": 42,
      "snippet": "...pendanaan bersama berbasis teknologi...",
      "score": 12.4,
      "matching_pasals": ["Pasal 1", "Pasal 5"],
      "total_chunks": 8,
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

### Example

```bash
curl "https://regulasi.id/api/v1/search?q=kredit+pemilikan+rumah&sector=perbankan&status=berlaku&limit=5"

curl "https://regulasi.id/api/v1/search?q=modal+minimum&type=POJK,SEOJK&year_from=2020"
```

---

## List Regulations

`GET /api/v1/regulations`

Browse regulations with optional filters.

### Parameters

| Param | Type | Description |
|-------|------|-------------|
| `sector` | string | Filter by sector |
| `type` | string | Filter by regulation type |
| `year` | integer | Filter by year |
| `status` | string | `berlaku` \| `diubah` \| `dicabut` |
| `page` | integer | Default 1 |
| `per_page` | integer | 1–100. Default 20. |

### Response

```json
{
  "total": 487,
  "page": 1,
  "per_page": 20,
  "regulations": [
    {
      "frbr_uri": "/akn/id/act/pojk/2022/10",
      "title": "...",
      "number": "10",
      "year": 2022,
      "status": "berlaku",
      "type": "POJK",
      "sector": "fintech"
    }
  ]
}
```

---

## Get Regulation

`GET /api/v1/regulations/{frbr_path}`

Get full regulation content by FRBR URI.

### Path

The FRBR path is everything after `/api/v1/regulations`:

```
/api/v1/regulations/akn/id/act/pojk/2022/10
→ frbr_uri: /akn/id/act/pojk/2022/10
```

### Response

```json
{
  "work": {
    "frbr_uri": "/akn/id/act/pojk/2022/10",
    "title": "...",
    "number": "10",
    "year": 2022,
    "status": "berlaku",
    "date_enacted": "2022-03-28",
    "source_url": "http://jdih.ojk.go.id/...",
    "sector": "fintech",
    "type": "POJK"
  },
  "nodes": [
    {
      "id": 1234,
      "node_type": "bab",
      "number": "I",
      "heading": "KETENTUAN UMUM",
      "content_text": null,
      "sort_order": 100
    },
    {
      "id": 1235,
      "node_type": "pasal",
      "number": "1",
      "heading": null,
      "content_text": "Dalam Peraturan ini yang dimaksud dengan...",
      "sort_order": 200
    }
  ]
}
```

---

## List Sectors

`GET /api/v1/sectors`

### Response

```json
{
  "sectors": [
    {
      "code": "fintech",
      "name_id": "Teknologi Finansial",
      "name_en": "Financial Technology",
      "regulation_count": 47
    },
    {
      "code": "perbankan",
      "name_id": "Perbankan",
      "name_en": "Banking",
      "regulation_count": 183
    }
  ]
}
```

---

## Submit Correction

`POST /api/suggestions`

Rate limited: 10 requests per IP per hour.

### Request body

```json
{
  "work_id": 42,
  "node_id": 1235,
  "current_content": "Dalam Peraturan ini yang dimaksud dengan...",
  "suggested_content": "Dalam Peraturan Otoritas Jasa Keuangan ini yang dimaksud dengan...",
  "reason": "Teks tidak lengkap, kata 'Otoritas Jasa Keuangan' hilang",
  "email": "user@example.com"
}
```

### Response

```json
{ "id": 99, "status": "pending" }
```

---

## Error Format

All errors follow this shape:

```json
{
  "error": "Human-readable error message",
  "code": "INVALID_PARAMETER"  // optional
}
```

HTTP status codes:
- `400` — Invalid parameters
- `404` — Regulation not found
- `429` — Rate limit exceeded (includes `retry_after_seconds`)
- `500` — Internal server error

---

## Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/api/v1/search` | 60 req | 1 min |
| `/api/v1/regulations` | 60 req | 1 min |
| `/api/v1/regulations/*` | 60 req | 1 min |
| `/api/v1/sectors` | 60 req | 1 min |
| `/api/suggestions` | 10 req | 1 hour |

Rate limiting is in-memory per server instance (not distributed).

---

## CORS

All `/api/v1/` endpoints return:
```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, OPTIONS
Access-Control-Allow-Headers: Content-Type
```

---

## FRBR URI Format

```
/akn/id/act/{type}/{year}/{number}

Examples:
  /akn/id/act/pojk/2022/10
  /akn/id/act/seojk/2023/19
  /akn/id/act/uu/2011/21
```

## Slug Format

```
{type}-{number}-{year}

Examples:
  pojk-10-2022
  seojk-19-2023
  uu-21-2011
```

Used in web URLs: `https://regulasi.id/regulasi/pojk/pojk-10-2022`

# MCP Server

Gives Claude grounded access to OJK regulations. Prevents hallucination by returning exact article text with source citations.

---

## Connect

```bash
# Local development
claude mcp add --transport http regulasi-id http://localhost:8000/mcp

# Production
claude mcp add --transport http regulasi-id https://your-railway-url.up.railway.app/mcp
```

No trailing slash on `/mcp` — Railway's 307 redirect breaks Claude Code's HTTP transport.

---

## Tools

### `search_regulations`

Entry point for any legal question. Search first, then get exact text.

```python
search_regulations(
    query: str,              # Indonesian preferred: "kredit pemilikan rumah" not "home loan"
    sector: str | None,      # perbankan | pasar-modal | fintech | iknb | dana-pensiun | perasuransian
    regulation_type: str | None,  # POJK | SEOJK | KEOJK | UU | PP | PERPRES
    year_from: int | None,
    year_to: int | None,
    status: str | None,      # berlaku | diubah | dicabut
    limit: int = 10,         # max 50
) -> list[dict]
```

Returns:
```json
[
  {
    "title": "POJK tentang Penyelenggaraan Layanan Pendanaan Bersama Berbasis Teknologi Informasi",
    "frbr_uri": "/akn/id/act/pojk/2022/10",
    "regulation_type": "POJK",
    "sector": "fintech",
    "year": 2022,
    "pasal": "Pasal 1",
    "snippet": "...<mark>pendanaan</mark> bersama...",
    "status": "berlaku",
    "relevance_score": 12.4,
    "disclaimer": "..."
  }
]
```

Rate limit: 30/min. No cache (results change as DB grows).

---

### `get_article`

Exact article text for citation. Always call `get_regulation_status` after this to verify the law is still in force.

```python
get_article(
    regulation_type: str,   # "POJK"
    number: str,            # "10" (string, not int)
    year: int,              # 2022
    article_number: str,    # "1" or "81A"
) -> dict
```

Returns:
```json
{
  "title": "...",
  "frbr_uri": "...",
  "article_number": "1",
  "chapter": "BAB I - KETENTUAN UMUM",
  "content_id": "Pasal 1\nDalam Peraturan ini yang dimaksud dengan...",
  "ayat": [
    { "number": "1", "text": "Teknologi Finansial..." },
    { "number": "2", "text": "Penyelenggara adalah..." }
  ],
  "cross_references": [
    { "pasal": "5", "ayat": "2" }
  ],
  "status": "berlaku",
  "disclaimer": "..."
}
```

Rate limit: 60/min. Cache: 1h TTL per (type, number, year, article).

---

### `get_regulation_status`

Check before citing. A revoked regulation is misleading.

```python
get_regulation_status(
    regulation_type: str,  # "POJK"
    number: str,           # "77"
    year: int,             # 2016
) -> dict
```

Returns:
```json
{
  "title": "...",
  "frbr_uri": "...",
  "status": "dicabut",
  "status_explanation": "This regulation has been revoked and is no longer in force.",
  "date_enacted": "2016-12-29",
  "amendments": [
    {
      "relationship": "Revoked by",
      "law": "POJK 34/2025",
      "full_title": "POJK tentang Penyelenggaraan Teknologi Informasi..."
    }
  ],
  "related_laws": [],
  "disclaimer": "..."
}
```

Rate limit: 60/min. Cache: 1h TTL.

---

### `get_compliance_checklist`

The differentiating feature. Returns all regulations that apply to a specific business type.

```python
get_compliance_checklist(
    sector: str,              # "fintech"
    business_type: str | None # "p2p-lending" | "digital-bank" | "insurance-broker" | None
) -> dict
```

Returns:
```json
{
  "sector": "fintech",
  "business_type": "p2p-lending",
  "required_regulations": [
    {
      "frbr_uri": "/akn/id/act/pojk/2022/10",
      "title": "POJK tentang LPBBTI",
      "regulation_type": "POJK",
      "number": "10",
      "year": 2022,
      "status": "berlaku",
      "priority": "required",
      "notes": "Primary licensing regulation for P2P lending platforms",
      "implementing_circulars": [
        {
          "frbr_uri": "/akn/id/act/seojk/2023/19",
          "title": "SEOJK tentang Laporan LPBBTI",
          "priority": "required"
        }
      ]
    }
  ],
  "disclaimer": "..."
}
```

Rate limit: 30/min. No cache (compliance_mappings table may be updated).

---

### `list_regulations`

For browsing/discovery. Use `search_regulations` for specific legal questions.

```python
list_regulations(
    sector: str | None,
    regulation_type: str | None,
    year: int | None,
    status: str | None,      # berlaku | diubah | dicabut
    search: str | None,       # title keyword filter
    page: int = 1,
    per_page: int = 20,       # max 100
) -> dict
```

Returns:
```json
{
  "total": 142,
  "page": 1,
  "per_page": 20,
  "regulations": [
    {
      "frbr_uri": "...",
      "title": "...",
      "regulation_type": "POJK",
      "sector": "fintech",
      "number": "10",
      "year": 2022,
      "status": "berlaku"
    }
  ],
  "disclaimer": "..."
}
```

Rate limit: 30/min.

---

### `ping`

Health check.

```python
ping() -> str
# "regulasi-id MCP server running. Database has 487 regulations loaded."
```

---

## Recommended Workflow

```
1. search_regulations(query)    → Find relevant regulations
2. get_article(type, num, year, pasal)  → Get exact text for citation
3. get_regulation_status(type, num, year)  → Verify still in force
4. list_regulations(sector=...)  → Browse if search returns nothing
```

**Citation format:** Always cite as `Pasal X POJK No. Y Tahun Z`
Example: `Pasal 1 angka 7 POJK No. 10 Tahun 2022 tentang LPBBTI`

---

## Implementation Notes

### Architecture

Single file (`server.py`) with:
- All tools (5 total)
- `TTLCache` — simple dict with per-key expiry (1h for get tools, 5min for counts)
- `RateLimiter` — per-instance sliding window per tool
- Regulation type + sector caches (populated on first call, held in memory)
- `SUPABASE_ANON_KEY` enforced at startup — server refuses to start with service role key

### Caching

```python
_article_cache = TTLCache(ttl_seconds=3600, maxsize=2000)
_status_cache  = TTLCache(ttl_seconds=3600, maxsize=2000)
_count_cache   = TTLCache(ttl_seconds=300,  maxsize=10)
```

Rate limiters are per-server-process — not distributed. With multiple Railway instances, effective limits are N× per user. Add Redis if scaling.

### Disclaimer

Every response includes:
```
"Informasi ini bukan nasihat hukum. Selalu verifikasi dengan sumber resmi OJK. Database regulasi-id mencakup sebagian regulasi OJK."
```

---

## Deployment

```dockerfile
# apps/mcp-server/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser
CMD ["python", "server.py"]
```

```python
# End of server.py
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
```

Railway environment variables required:
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `PORT` (set automatically by Railway)

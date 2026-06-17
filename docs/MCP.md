# MCP Server

Gives Claude grounded access to OJK regulations. Prevents hallucination by returning exact article text with source citations. Distributed rate limiting and caching via Upstash Redis — safe to run multiple Railway instances.

---

## Connect

```bash
# Local development
claude mcp add --transport http regulasi-id http://localhost:8000/mcp

# Production
claude mcp add --transport http regulasi-id https://your-railway-url.up.railway.app/mcp
```

No trailing slash on `/mcp` — Railway returns a 307 redirect which breaks Claude Code's HTTP transport.

---

## Tools

### `search_regulations`

Entry point for any legal question. Uses hybrid search (FTS + pgvector + RRF). Handles concept queries and synonyms that keyword-only search misses.

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
    "pasal": "Pasal 24",
    "snippet": "...modal disetor paling sedikit sebesar <mark>Rp50.000.000.000</mark>...",
    "status": "berlaku",
    "relevance_score": 14.7,
    "semantic_used": true,
    "disclaimer": "..."
  }
]
```

Rate limit: 30/min (Upstash, cross-instance). Not cached.

---

### `get_article`

Exact article text for citation. Always verify status with `get_regulation_status` before citing.

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
  "article_number": "24",
  "chapter": "BAB V - KELEMBAGAAN",
  "content_text": "Pasal 24\nPenyelenggara wajib memiliki modal disetor...",
  "ayat": [
    { "number": "1", "text": "Modal disetor paling sedikit sebesar Rp50.000.000.000..." },
    { "number": "2", "text": "Modal disetor sebagaimana dimaksud pada ayat (1)..." }
  ],
  "cross_references": [
    { "pasal": "25", "context": "sebagaimana dimaksud dalam Pasal 25" }
  ],
  "status": "berlaku",
  "disclaimer": "..."
}
```

Rate limit: 60/min. Cache: Upstash, TTL 1h, key `article:{type}:{number}:{year}:{pasal}`.

---

### `get_regulation_status`

Check before citing. A revoked regulation silently misleads.

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
  "status_explanation": "Peraturan ini telah dicabut dan tidak berlaku lagi.",
  "date_enacted": "2016-12-29",
  "amendments": [
    {
      "relationship": "Dicabut oleh",
      "regulation": "POJK 10/2022",
      "full_title": "POJK tentang Penyelenggaraan Layanan Pendanaan Bersama Berbasis Teknologi Informasi"
    }
  ],
  "disclaimer": "..."
}
```

Rate limit: 60/min. Cache: Upstash, TTL 1h.

---

### `get_compliance_checklist`

The differentiating feature. Returns all regulations that apply to a specific business type, ordered by priority.

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
      "notes": "Primary licensing regulation for P2P lending platforms"
    },
    {
      "frbr_uri": "/akn/id/act/seojk/2023/19",
      "title": "SEOJK tentang Laporan LPBBTI",
      "regulation_type": "SEOJK",
      "number": "19",
      "year": 2023,
      "status": "berlaku",
      "priority": "required",
      "notes": "Implementing circular — reporting requirements"
    }
  ],
  "disclaimer": "..."
}
```

Rate limit: 30/min. Not cached (`compliance_mappings` updated by admin).

---

### `list_regulations`

Browsing and discovery. Use `search_regulations` for specific legal questions.

```python
list_regulations(
    sector: str | None,
    regulation_type: str | None,
    year: int | None,
    status: str | None,
    cursor: str | None,   # opaque cursor for pagination
    per_page: int = 20,   # max 100
) -> dict
```

Returns:
```json
{
  "total": 487,
  "next_cursor": "eyJ5ZWFyIjoyMDIyLCJpZCI6NDJ9",
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

Health check. Returns works count and embedding coverage.

```python
ping() -> str
# "regulasi-id MCP v1.0. Database: 487 regulations, 94% embedding coverage."
```

---

## Recommended Workflow

```
1. search_regulations(query)              → find relevant regulations
2. get_article(type, num, year, pasal)    → get exact text for citation
3. get_regulation_status(type, num, year) → verify still in force
4. list_regulations(sector=...)           → browse if search returns nothing
```

**Citation format:** `Pasal X POJK No. Y Tahun Z tentang [topic]`
Example: `Pasal 24 ayat (1) POJK No. 10 Tahun 2022 tentang LPBBTI`

---

## Implementation

### Architecture

Single file `server.py` with:
- All 5 tools
- Upstash Redis via `upstash-py` for caching and rate limiting
- Sentry SDK for error tracking
- `structlog` for structured JSON logs (visible in Railway dashboard)
- Startup check: refuses to start with service role key as anon key

### Caching (Upstash Redis)

**Not in-memory** — cache is shared across all Railway instances and survives deploys.

```python
from upstash_redis import Redis

redis = Redis(url=os.environ["UPSTASH_REDIS_REST_URL"],
              token=os.environ["UPSTASH_REDIS_REST_TOKEN"])

# Set with TTL
redis.set(f"article:{cache_key}", json.dumps(result), ex=3600)

# Get
cached = redis.get(f"article:{cache_key}")
if cached:
    return json.loads(cached)
```

TTLs:
- `get_article` results: 3600s (1h)
- `get_regulation_status` results: 3600s (1h)
- Works count (ping): 300s (5min)
- Search results: not cached

### Rate limiting (Upstash)

```python
from upstash_ratelimit import Ratelimit, SlidingWindow

ratelimit = Ratelimit(
    redis=redis,
    limiter=SlidingWindow(max_requests=30, window="60s"),
)

result = ratelimit.limit(f"search:{client_ip}")
if not result.allowed:
    raise ToolError(f"Rate limit exceeded. Retry after {result.reset}s.")
```

Per-tool limits enforced separately. Cross-instance safe.

### Error handling

```python
import sentry_sdk

sentry_sdk.init(dsn=os.environ["SENTRY_DSN"])

@mcp.tool()
def get_article(...):
    try:
        result = _fetch_article(...)
        return result
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return {"error": "Internal error fetching article. Please try again."}
```

### Disclaimer

Every tool response includes:
```
"Informasi ini bukan nasihat hukum. Selalu verifikasi dengan sumber resmi OJK. regulasi-id mencakup sebagian regulasi OJK."
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
EXPOSE 8000
CMD ["python", "server.py"]
```

```python
# server.py bottom
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
```

### Required Railway environment variables

```
SUPABASE_URL
SUPABASE_ANON_KEY           ← anon key only, NOT service role
UPSTASH_REDIS_REST_URL
UPSTASH_REDIS_REST_TOKEN
SENTRY_DSN
PORT                        ← set automatically by Railway
```

### `requirements.txt`

```
fastmcp>=2.0
supabase>=2.0
upstash-redis>=1.0
upstash-ratelimit>=1.0
sentry-sdk>=2.0
structlog>=24.0
httpx>=0.27
```

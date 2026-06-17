# Database Design

PostgreSQL via Supabase. All tables have RLS enabled. App connections via PgBouncer. Hybrid search via TSVECTOR + pgvector.

---

## Required Extensions

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- trigram similarity
CREATE EXTENSION IF NOT EXISTS unaccent;  -- accent-insensitive search
CREATE EXTENSION IF NOT EXISTS vector;    -- pgvector for embeddings
CREATE EXTENSION IF NOT EXISTS pg_cron;   -- scheduled materialized view refresh
```

---

## Connection Pooling

Always use PgBouncer (transaction mode) from application code. Only use direct connection for migrations.

| Usage | Host | Port |
|-------|------|------|
| App code (web, MCP, scripts query) | `db.xxx.supabase.co` (pooler) | `6543` |
| Migrations | `db.xxx.supabase.co` (direct) | `5432` |

PgBouncer is enabled in Supabase → Settings → Database → Connection pooling.

**Why:** Direct connections exhaust `max_connections` (100 on free plan, 500 on Pro) under concurrent search load. PgBouncer multiplexes thousands of app connections onto a small pool.

**Limitation:** `LISTEN/NOTIFY`, `SET`, and advisory locks don't work through PgBouncer in transaction mode — use direct connection for those.

---

## Migration Order

```
001 — pg extensions + sectors + regulation_types + relationship_types
002 — works table + slug generation trigger + search_text trigger
003 — document_nodes table (with pgvector embedding column)
004 — work_relationships table
005 — abstracts table
006 — faqs table
007 — revisions table
008 — suggestions table
009 — compliance_mappings table
010 — crawl_jobs table + claim_jobs() function
011 — discovery_progress table
012 — search_analytics table
013 — search function (search_regulations() — hybrid FTS + vector + RRF)
014 — FTS indexes (GIN on works.search_fts, document_nodes.fts)
015 — trigram index (pg_trgm on works.title_id)
016 — pgvector index (hnsw on document_nodes.embedding)
017 — RLS policies
018 — apply_revision() function
019 — materialized views (mv_sector_stats, mv_type_stats)
020 — pg_cron jobs (refresh materialized views every 15 min)
021 — search_path hardening on all functions
```

---

## Tables

### `sectors`

```sql
CREATE TABLE sectors (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(30) UNIQUE NOT NULL,
    name_id     VARCHAR(100) NOT NULL,
    name_en     VARCHAR(100),
    jdih_code   VARCHAR(5)
);

INSERT INTO sectors (code, name_id, name_en, jdih_code) VALUES
    ('perbankan',     'Perbankan',                  'Banking',                     '01'),
    ('pasar-modal',   'Pasar Modal',                'Capital Markets',             '02'),
    ('iknb',          'Industri Keuangan Non-Bank', 'Non-Bank Financial Industry', '08'),
    ('fintech',       'Teknologi Finansial',         'Financial Technology',        '10'),
    ('dana-pensiun',  'Dana Pensiun',               'Pension Funds',               '06'),
    ('perasuransian', 'Perasuransian',              'Insurance',                   '04');
```

### `regulation_types`

```sql
CREATE TABLE regulation_types (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(20) UNIQUE NOT NULL,
    name_id         VARCHAR(100) NOT NULL,
    name_en         VARCHAR(100),
    hierarchy_level INTEGER NOT NULL,
    jdih_code       VARCHAR(5)
);

INSERT INTO regulation_types (code, name_id, name_en, hierarchy_level, jdih_code) VALUES
    ('UU',      'Undang-Undang',            'Law',                  1, '01'),
    ('PP',      'Peraturan Pemerintah',     'Government Regulation',2, '02'),
    ('PERPRES', 'Peraturan Presiden',       'Presidential Reg.',    3, '03'),
    ('POJK',    'Peraturan OJK',           'OJK Regulation',       4, '06'),
    ('SEOJK',   'Surat Edaran OJK',        'OJK Circular',         5, '07'),
    ('KEOJK',   'Keputusan OJK',           'OJK Decision',         6, '08');
```

### `works`

```sql
CREATE TABLE works (
    id                  SERIAL PRIMARY KEY,
    sector_id           INTEGER REFERENCES sectors(id),
    regulation_type_id  INTEGER NOT NULL REFERENCES regulation_types(id),
    frbr_uri            TEXT UNIQUE,
    slug                TEXT UNIQUE,
    title_id            TEXT NOT NULL,
    number              TEXT NOT NULL,
    year                INTEGER NOT NULL,
    status              TEXT DEFAULT 'berlaku',  -- berlaku | diubah | dicabut | tidak_berlaku
    date_enacted        DATE,
    source_url          TEXT,
    source_pdf_url      TEXT,
    content_verified    BOOLEAN DEFAULT false,
    extraction_quality  FLOAT,                   -- 0–1 from quality scorer
    subject_tags        TEXT[],
    tentang             TEXT,
    search_text         TEXT,
    search_fts          TSVECTOR GENERATED ALWAYS AS (
                            to_tsvector('indonesian', COALESCE(search_text, ''))
                        ) STORED,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_works_search_fts  ON works USING GIN(search_fts);
CREATE INDEX idx_works_sector      ON works(sector_id);
CREATE INDEX idx_works_type        ON works(regulation_type_id);
CREATE INDEX idx_works_year        ON works(year);
CREATE INDEX idx_works_status      ON works(status);
CREATE INDEX idx_works_slug        ON works(slug);
CREATE INDEX idx_works_trgm        ON works USING GIN(title_id gin_trgm_ops);
-- Composite for cursor pagination
CREATE INDEX idx_works_cursor      ON works(year DESC, id DESC);
```

### `document_nodes`

Hierarchical document structure. Hybrid search happens here: FTS + pgvector embeddings.

```sql
CREATE TABLE document_nodes (
    id              BIGSERIAL PRIMARY KEY,
    work_id         INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    parent_id       BIGINT REFERENCES document_nodes(id),
    node_type       TEXT NOT NULL,  -- bab | bagian | paragraf | pasal | ayat | preamble | penjelasan_pasal | aturan | lampiran
    number          TEXT,
    heading         TEXT,
    content_text    TEXT,
    sort_order      BIGINT,
    pdf_page_start  INTEGER,
    pdf_page_end    INTEGER,
    embedding       vector(1536),   -- pgvector, text-embedding-3-small or equivalent
    fts             TSVECTOR GENERATED ALWAYS AS (
                        to_tsvector('indonesian', COALESCE(content_text, ''))
                    ) STORED,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_nodes_work        ON document_nodes(work_id);
CREATE INDEX idx_nodes_fts         ON document_nodes USING GIN(fts);
CREATE INDEX idx_nodes_type        ON document_nodes(node_type);
CREATE INDEX idx_nodes_parent      ON document_nodes(parent_id);
CREATE INDEX idx_nodes_sort        ON document_nodes(work_id, sort_order);
-- pgvector HNSW index (approximate nearest neighbor, cosine)
CREATE INDEX idx_nodes_embedding   ON document_nodes
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
-- Partial index for embedding backfill tracking
CREATE INDEX idx_nodes_no_embedding ON document_nodes(id) WHERE embedding IS NULL;
```

**pgvector index parameters:**
- `m = 16` — graph connectivity (16–64 range; higher = better recall, slower build)
- `ef_construction = 64` — build-time search width (64–200; higher = better quality, slower build)
- At query time, set `SET hnsw.ef_search = 100` for better recall on precision-sensitive queries

**When to rebuild:** If average query latency > 100ms or recall drops below 90%, rebuild the index:
```sql
REINDEX INDEX CONCURRENTLY idx_nodes_embedding;
```

### `abstracts`

```sql
CREATE TABLE abstracts (
    id              SERIAL PRIMARY KEY,
    work_id         INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE UNIQUE,
    content_text    TEXT,
    source_pdf_url  TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### `faqs`

```sql
CREATE TABLE faqs (
    id              SERIAL PRIMARY KEY,
    work_id         INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE UNIQUE,
    content_text    TEXT,
    source_pdf_url  TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### `revisions` (append-only)

Never UPDATE or DELETE rows here. Ever.

```sql
CREATE TABLE revisions (
    id              BIGSERIAL PRIMARY KEY,
    node_id         BIGINT NOT NULL REFERENCES document_nodes(id),
    old_content     TEXT,
    new_content     TEXT NOT NULL,
    reason          TEXT,
    actor           TEXT,  -- 'system' | 'admin:email' | 'agent:gemini'
    suggestion_id   INTEGER REFERENCES suggestions(id),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### `suggestions`

```sql
CREATE TABLE suggestions (
    id                      SERIAL PRIMARY KEY,
    work_id                 INTEGER NOT NULL REFERENCES works(id),
    node_id                 BIGINT NOT NULL REFERENCES document_nodes(id),
    node_type               TEXT,
    node_number             TEXT,
    current_content         TEXT NOT NULL,
    suggested_content       TEXT NOT NULL,
    user_reason             TEXT,
    submitter_email         TEXT,
    submitter_ip            TEXT,
    status                  TEXT DEFAULT 'pending',  -- pending | verified | approved | rejected
    agent_decision          TEXT,
    agent_confidence        FLOAT,
    agent_modified_content  TEXT,
    agent_response          JSONB,
    admin_note              TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);
```

### `compliance_mappings`

Curated. Powers `get_compliance_checklist()`. See `docs/COMPLIANCE_MAPPINGS.md` for curation guide.

```sql
CREATE TABLE compliance_mappings (
    id              SERIAL PRIMARY KEY,
    sector_id       INTEGER NOT NULL REFERENCES sectors(id),
    business_type   TEXT,           -- null = sector-wide
    work_id         INTEGER NOT NULL REFERENCES works(id),
    priority        TEXT NOT NULL,  -- required | recommended | conditional
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_compliance_sector   ON compliance_mappings(sector_id);
CREATE INDEX idx_compliance_business ON compliance_mappings(business_type);
CREATE INDEX idx_compliance_work     ON compliance_mappings(work_id);
```

### `crawl_jobs`

```sql
CREATE TABLE crawl_jobs (
    id                  SERIAL PRIMARY KEY,
    sector_code         TEXT NOT NULL,
    regulation_type     TEXT NOT NULL,
    source_url          TEXT NOT NULL,
    detail_uuid         TEXT,
    pdf_uuid            TEXT,
    abstract_uuid       TEXT,
    faq_uuid            TEXT,
    status              TEXT DEFAULT 'pending',  -- pending | crawling | downloaded | parsed | loaded | failed | dead | skipped
    error_message       TEXT,
    retry_count         INTEGER DEFAULT 0,
    next_retry_at       TIMESTAMPTZ,
    extraction_version  INTEGER DEFAULT 1,
    extraction_quality  FLOAT,
    work_id             INTEGER REFERENCES works(id),
    claimed_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_crawl_jobs_url    ON crawl_jobs(source_url);
CREATE INDEX idx_crawl_jobs_status        ON crawl_jobs(status);
CREATE INDEX idx_crawl_jobs_next_retry    ON crawl_jobs(next_retry_at) WHERE status = 'failed';
CREATE INDEX idx_crawl_jobs_dead          ON crawl_jobs(id) WHERE status = 'dead';
```

### `search_analytics`

Every search is logged here. Read weekly to find zero-result queries and missing content.

```sql
CREATE TABLE search_analytics (
    id              BIGSERIAL PRIMARY KEY,
    query           TEXT NOT NULL,
    sector_filter   TEXT,
    type_filter     TEXT,
    result_count    INTEGER NOT NULL DEFAULT 0,
    zero_results    BOOLEAN GENERATED ALWAYS AS (result_count = 0) STORED,
    embedding_used  BOOLEAN DEFAULT false,
    source          TEXT,  -- 'web' | 'api' | 'mcp'
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_analytics_zero    ON search_analytics(created_at) WHERE zero_results = true;
CREATE INDEX idx_analytics_source  ON search_analytics(source, created_at);
```

---

## Materialized Views

Refresh every 15 minutes via pg_cron. Never query `COUNT(*)` on large tables in real-time.

```sql
CREATE MATERIALIZED VIEW mv_sector_stats AS
SELECT
    s.code, s.name_id, s.name_en,
    count(w.id)                                                      AS regulation_count,
    count(CASE WHEN w.status = 'berlaku' THEN 1 END)                AS berlaku_count,
    count(CASE WHEN w.status = 'dicabut' THEN 1 END)                AS dicabut_count,
    max(w.year)                                                      AS latest_year
FROM sectors s LEFT JOIN works w ON w.sector_id = s.id
GROUP BY s.id, s.code, s.name_id, s.name_en;

CREATE UNIQUE INDEX ON mv_sector_stats(code);

CREATE MATERIALIZED VIEW mv_type_stats AS
SELECT
    rt.code, rt.name_id, rt.hierarchy_level,
    count(w.id)       AS regulation_count,
    min(w.year)       AS earliest_year,
    max(w.year)       AS latest_year
FROM regulation_types rt LEFT JOIN works w ON w.regulation_type_id = rt.id
GROUP BY rt.id, rt.code, rt.name_id, rt.hierarchy_level;

CREATE UNIQUE INDEX ON mv_type_stats(code);

-- pg_cron refresh job
SELECT cron.schedule('refresh-stats', '*/15 * * * *',
  $$REFRESH MATERIALIZED VIEW CONCURRENTLY mv_sector_stats;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_type_stats;$$);
```

---

## Critical SQL Functions

### `apply_revision()`

```sql
CREATE OR REPLACE FUNCTION apply_revision(
    p_node_id       BIGINT,
    p_new_content   TEXT,
    p_reason        TEXT,
    p_actor         TEXT,
    p_suggestion_id INTEGER DEFAULT NULL
) RETURNS VOID
SET search_path = 'public', 'extensions'
AS $$
BEGIN
    INSERT INTO revisions (node_id, old_content, new_content, reason, actor, suggestion_id)
    SELECT p_node_id, content_text, p_new_content, p_reason, p_actor, p_suggestion_id
    FROM document_nodes WHERE id = p_node_id;

    -- embedding column is NOT updated here — background regenerate job picks it up
    -- (nodes with content updated but embedding from old content have a stale embedding)
    UPDATE document_nodes
    SET content_text = p_new_content, embedding = NULL  -- NULL signals background regen
    WHERE id = p_node_id;

    IF p_suggestion_id IS NOT NULL THEN
        UPDATE suggestions SET status = 'approved', updated_at = NOW()
        WHERE id = p_suggestion_id;
    END IF;
END;
$$ LANGUAGE plpgsql;
```

### `claim_jobs()`

```sql
CREATE OR REPLACE FUNCTION claim_jobs(
    batch_size   INT DEFAULT 10,
    worker_id    TEXT DEFAULT NULL
)
RETURNS TABLE(id INT, source_url TEXT, detail_uuid TEXT, pdf_uuid TEXT, abstract_uuid TEXT, faq_uuid TEXT)
SET search_path = 'public', 'extensions'
AS $$
BEGIN
    RETURN QUERY
    UPDATE crawl_jobs SET
        status = 'crawling',
        claimed_at = NOW(),
        updated_at = NOW()
    WHERE crawl_jobs.id IN (
        SELECT cj.id FROM crawl_jobs cj
        WHERE (cj.status = 'pending')
           OR (cj.status = 'failed' AND cj.next_retry_at <= NOW())
           OR (cj.status = 'crawling' AND cj.claimed_at < NOW() - INTERVAL '15 minutes')
        ORDER BY cj.created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT batch_size
    )
    RETURNING crawl_jobs.id, crawl_jobs.source_url, crawl_jobs.detail_uuid,
              crawl_jobs.pdf_uuid, crawl_jobs.abstract_uuid, crawl_jobs.faq_uuid;
END;
$$ LANGUAGE plpgsql;
```

### `search_regulations()` — hybrid

4-layer hybrid search with RRF. Full implementation in `migrations/013_search_function.sql`.

Signature:
```sql
CREATE OR REPLACE FUNCTION search_regulations(
    p_query           TEXT,
    p_sector          TEXT DEFAULT NULL,
    p_type            TEXT DEFAULT NULL,
    p_year_from       INT  DEFAULT NULL,
    p_year_to         INT  DEFAULT NULL,
    p_status          TEXT DEFAULT NULL,
    p_limit           INT  DEFAULT 10,
    p_query_embedding vector(1536) DEFAULT NULL
) RETURNS TABLE(
    work_id     INT,
    frbr_uri    TEXT,
    title_id    TEXT,
    number      TEXT,
    year        INT,
    status      TEXT,
    snippet     TEXT,
    score       FLOAT,
    node_id     BIGINT,
    node_type   TEXT,
    node_number TEXT
) ...
```

---

## RLS Policies

```sql
-- Public read on all regulatory content
ALTER TABLE sectors ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON sectors FOR SELECT USING (true);

ALTER TABLE regulation_types ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON regulation_types FOR SELECT USING (true);

ALTER TABLE works ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON works FOR SELECT USING (true);

ALTER TABLE document_nodes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON document_nodes FOR SELECT USING (true);

ALTER TABLE abstracts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON abstracts FOR SELECT USING (true);

ALTER TABLE faqs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON faqs FOR SELECT USING (true);

ALTER TABLE work_relationships ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON work_relationships FOR SELECT USING (true);

ALTER TABLE compliance_mappings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON compliance_mappings FOR SELECT USING (true);

-- search_analytics: service role only (no PII in logs but still restricted)
ALTER TABLE search_analytics ENABLE ROW LEVEL SECURITY;

-- Suggestions: public write, service role reads
ALTER TABLE suggestions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public insert" ON suggestions FOR INSERT WITH CHECK (true);

-- crawl_jobs, revisions: service role only
ALTER TABLE crawl_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE revisions ENABLE ROW LEVEL SECURITY;
```

---

## Migration CI

Migrations are tested in CI before applying to production:

```yaml
# .github/workflows/db.yml
- name: Apply migrations to test DB
  env:
    SUPABASE_DB_URL: ${{ secrets.SUPABASE_TEST_DB_URL }}  # direct connection, port 5432
  run: |
    for f in packages/supabase/migrations/*.sql; do
      psql "$SUPABASE_DB_URL" -f "$f"
    done

- name: Run integration tests against test DB
  run: cd apps/web && npm run test:run
  env:
    SUPABASE_TEST_URL: ${{ secrets.SUPABASE_TEST_URL }}
    SUPABASE_TEST_ANON_KEY: ${{ secrets.SUPABASE_TEST_ANON_KEY }}
```

**Rule:** Never apply a migration to production that hasn't passed CI.

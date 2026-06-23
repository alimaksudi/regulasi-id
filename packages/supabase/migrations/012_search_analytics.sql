-- 012 — search_analytics (every query logged; zero-result queries drive the backlog)

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

CREATE INDEX idx_analytics_zero   ON search_analytics(created_at) WHERE zero_results = true;
CREATE INDEX idx_analytics_source ON search_analytics(source, created_at);

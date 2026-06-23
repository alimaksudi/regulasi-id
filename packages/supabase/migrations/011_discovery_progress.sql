-- 011 — discovery_progress (crawl freshness cache)
-- Designed here; named in the migration plan and table list but not given a DDL
-- block. One row per (sector, regulation type) listing page the crawler walks, so a
-- re-crawl can skip listings that have not changed and resume where it stopped.

CREATE TABLE discovery_progress (
    id                  SERIAL PRIMARY KEY,
    sector_code         TEXT NOT NULL,
    regulation_type     TEXT NOT NULL,
    last_page           INTEGER DEFAULT 0,
    total_found         INTEGER DEFAULT 0,
    last_discovered_at  TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (sector_code, regulation_type)
);

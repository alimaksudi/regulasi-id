-- 010 — crawl_jobs + claim_jobs()

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

CREATE UNIQUE INDEX idx_crawl_jobs_url     ON crawl_jobs(source_url);
CREATE INDEX        idx_crawl_jobs_status  ON crawl_jobs(status);
CREATE INDEX        idx_crawl_jobs_next_retry ON crawl_jobs(next_retry_at) WHERE status = 'failed';
CREATE INDEX        idx_crawl_jobs_dead    ON crawl_jobs(id) WHERE status = 'dead';

-- Atomically claim a batch of jobs. SKIP LOCKED lets many workers pull disjoint
-- batches without blocking each other. Also reclaims jobs stuck in 'crawling' for
-- more than 15 minutes (a crashed worker).
CREATE OR REPLACE FUNCTION claim_jobs(
    batch_size   INT DEFAULT 10,
    worker_id    TEXT DEFAULT NULL
)
RETURNS TABLE(id INT, source_url TEXT, detail_uuid TEXT, pdf_uuid TEXT, abstract_uuid TEXT, faq_uuid TEXT)
SET search_path = 'public', 'extensions'
LANGUAGE plpgsql
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
$$;

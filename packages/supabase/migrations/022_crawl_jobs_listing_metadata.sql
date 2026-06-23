-- 022 — carry listing metadata from discovery into processing.
-- The JDIH listing JSON has clean title/number/year/status; keeping it on the job
-- avoids re-deriving those from the (unreliable) detail-page HTML at load time.

ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS listing_metadata JSONB;

-- claim_jobs() must return the new column, so drop and recreate it.
DROP FUNCTION IF EXISTS claim_jobs(int, text);

CREATE OR REPLACE FUNCTION claim_jobs(
    batch_size   INT DEFAULT 10,
    worker_id    TEXT DEFAULT NULL
)
RETURNS TABLE(
    id INT, source_url TEXT, detail_uuid TEXT, pdf_uuid TEXT,
    abstract_uuid TEXT, faq_uuid TEXT, listing_metadata JSONB
)
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
              crawl_jobs.pdf_uuid, crawl_jobs.abstract_uuid, crawl_jobs.faq_uuid,
              crawl_jobs.listing_metadata;
END;
$$;

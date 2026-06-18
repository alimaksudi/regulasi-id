-- 020 — pg_cron: refresh the stats materialized views every 15 minutes.
-- CONCURRENTLY avoids locking readers and needs the unique indexes from 019.

SELECT cron.schedule('refresh-stats', '*/15 * * * *',
  $$REFRESH MATERIALIZED VIEW CONCURRENTLY mv_sector_stats;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_type_stats;$$);

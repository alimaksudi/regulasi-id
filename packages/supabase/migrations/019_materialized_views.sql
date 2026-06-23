-- 019 — materialized views for landing-page stats (refreshed by pg_cron in 020).
-- Unique index on each is required for REFRESH MATERIALIZED VIEW CONCURRENTLY.

CREATE MATERIALIZED VIEW mv_sector_stats AS
SELECT
    s.code, s.name_id, s.name_en,
    count(w.id)                                       AS regulation_count,
    count(CASE WHEN w.status = 'berlaku' THEN 1 END)  AS berlaku_count,
    count(CASE WHEN w.status = 'dicabut' THEN 1 END)  AS dicabut_count,
    max(w.year)                                       AS latest_year
FROM sectors s LEFT JOIN works w ON w.sector_id = s.id
GROUP BY s.id, s.code, s.name_id, s.name_en;

CREATE UNIQUE INDEX ON mv_sector_stats(code);

CREATE MATERIALIZED VIEW mv_type_stats AS
SELECT
    rt.code, rt.name_id, rt.hierarchy_level,
    count(w.id)  AS regulation_count,
    min(w.year)  AS earliest_year,
    max(w.year)  AS latest_year
FROM regulation_types rt LEFT JOIN works w ON w.regulation_type_id = rt.id
GROUP BY rt.id, rt.code, rt.name_id, rt.hierarchy_level;

CREATE UNIQUE INDEX ON mv_type_stats(code);

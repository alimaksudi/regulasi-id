-- 013 — search_regulations() hybrid search
--
-- DATABASE.md gives the signature and points here for the body. Four layers:
--   Layer 1  identity fast path  — "POJK 10 2022" style lookups, score 1000, early exit
--   Layer 2  works FTS           — works.search_fts
--   Layer 3  content FTS         — document_nodes.fts
--   Layer 4  semantic            — cosine distance on document_nodes.embedding
-- Layers 2 to 4 are fused with Reciprocal Rank Fusion (k = 60). The caller passes a
-- pre-computed query embedding; with NULL embedding the function degrades to FTS only.
--
-- NOTE: untested against real data. Build the GIN/HNSW indexes (014, 016) and load
-- content before judging recall or latency.

SET search_path TO public, extensions;

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
)
SET search_path = 'public', 'extensions'
LANGUAGE plpgsql
AS $$
DECLARE
    v_types     TEXT[] := CASE WHEN p_type   IS NULL THEN NULL ELSE regexp_split_to_array(upper(p_type), '\s*,\s*') END;
    v_statuses  TEXT[] := CASE WHEN p_status IS NULL THEN NULL ELSE regexp_split_to_array(lower(p_status), '\s*,\s*') END;
    v_id_type   TEXT;
    v_id_year   TEXT;
    v_id_number TEXT;
BEGIN
    -- Better recall from the HNSW index on precision-sensitive queries.
    PERFORM set_config('hnsw.ef_search', '100', true);

    -- Layer 1: identity fast path. Pull a type token, a 4-digit year, and a remaining
    -- short number out of the raw query. Only short-circuit when all three are present.
    v_id_type   := upper(substring(p_query from '(?i)\y(POJK|SEOJK|KEOJK|PERPRES|UU|PP)\y'));
    v_id_year   := substring(p_query from '\y((?:19|20)\d{2})\y');
    v_id_number := substring(regexp_replace(p_query, '\y(?:19|20)\d{2}\y', ' ', 'g') from '\y(\d{1,4})\y');

    IF v_id_type IS NOT NULL AND v_id_year IS NOT NULL AND v_id_number IS NOT NULL THEN
        RETURN QUERY
        SELECT w.id, w.frbr_uri, w.title_id, w.number, w.year, w.status,
               left(COALESCE(w.tentang, w.title_id), 300) AS snippet,
               1000.0::FLOAT AS score,
               NULL::BIGINT, NULL::TEXT, NULL::TEXT
        FROM works w
        JOIN regulation_types rt ON rt.id = w.regulation_type_id
        WHERE rt.code = v_id_type
          AND w.year = v_id_year::INT
          AND w.number = v_id_number
          AND (p_sector IS NULL OR w.sector_id = (SELECT s.id FROM sectors s WHERE s.code = p_sector))
        LIMIT p_limit;

        IF FOUND THEN
            RETURN;
        END IF;
    END IF;

    -- Layers 2 to 4, fused with RRF.
    RETURN QUERY
    WITH
    q AS (
        SELECT websearch_to_tsquery('indonesian', p_query) AS tsq
    ),
    eligible AS (
        SELECT w.id AS eid
        FROM works w
        WHERE (p_sector IS NULL OR w.sector_id = (SELECT s.id FROM sectors s WHERE s.code = p_sector))
          AND (v_types IS NULL OR EXISTS (
                SELECT 1 FROM regulation_types rt
                WHERE rt.id = w.regulation_type_id AND rt.code = ANY(v_types)))
          AND (p_year_from IS NULL OR w.year >= p_year_from)
          AND (p_year_to   IS NULL OR w.year <= p_year_to)
          AND (v_statuses  IS NULL OR w.status = ANY(v_statuses))
    ),
    -- Layer 2: works-level FTS
    wfts AS (
        SELECT w.id AS wid,
               row_number() OVER (ORDER BY ts_rank(w.search_fts, q.tsq) DESC) AS rnk
        FROM works w, q
        WHERE w.search_fts @@ q.tsq
          AND w.id IN (SELECT eid FROM eligible)
        LIMIT 50
    ),
    -- Layer 3: content-level FTS, best node per work
    content AS (
        SELECT dn.work_id AS wid, dn.id AS nid, dn.node_type AS ntype, dn.number AS nnum,
               ts_rank(dn.fts, q.tsq) AS s
        FROM document_nodes dn, q
        WHERE dn.fts @@ q.tsq
          AND dn.work_id IN (SELECT eid FROM eligible)
    ),
    cbest AS (
        SELECT DISTINCT ON (wid) wid, nid, ntype, nnum,
               row_number() OVER (ORDER BY s DESC) AS rnk
        FROM content
        ORDER BY wid, s DESC
    ),
    -- Layer 4: semantic, best node per work
    sem AS (
        SELECT dn.work_id AS wid, dn.id AS nid, dn.node_type AS ntype, dn.number AS nnum,
               1 - (dn.embedding <=> p_query_embedding) AS sim
        FROM document_nodes dn
        WHERE p_query_embedding IS NOT NULL
          AND dn.embedding IS NOT NULL
          AND dn.work_id IN (SELECT eid FROM eligible)
        ORDER BY dn.embedding <=> p_query_embedding
        LIMIT 100
    ),
    sbest AS (
        SELECT DISTINCT ON (wid) wid, nid, ntype, nnum,
               row_number() OVER (ORDER BY sim DESC) AS rnk
        FROM sem
        ORDER BY wid, sim DESC
    ),
    fused AS (
        SELECT u.wid,
               sum(u.rrf) AS sc,
               (array_agg(u.nid   ORDER BY u.rrf DESC) FILTER (WHERE u.nid IS NOT NULL))[1] AS nid,
               (array_agg(u.ntype ORDER BY u.rrf DESC) FILTER (WHERE u.nid IS NOT NULL))[1] AS ntype,
               (array_agg(u.nnum  ORDER BY u.rrf DESC) FILTER (WHERE u.nid IS NOT NULL))[1] AS nnum
        FROM (
            SELECT wid, 1.0/(60 + rnk) AS rrf, NULL::BIGINT AS nid, NULL::TEXT AS ntype, NULL::TEXT AS nnum FROM wfts
            UNION ALL
            SELECT wid, 1.0/(60 + rnk), nid, ntype, nnum FROM cbest
            UNION ALL
            SELECT wid, 1.0/(60 + rnk), nid, ntype, nnum FROM sbest
        ) u
        GROUP BY u.wid
    )
    SELECT
        w.id,
        w.frbr_uri,
        w.title_id,
        w.number,
        w.year,
        w.status,
        ts_headline('indonesian',
            COALESCE(dn.content_text, w.tentang, w.title_id),
            (SELECT tsq FROM q),
            'StartSel=<mark>, StopSel=</mark>, MaxFragments=2, MinWords=5, MaxWords=24'
        ) AS snippet,
        f.sc::FLOAT,
        f.nid,
        f.ntype,
        f.nnum
    FROM fused f
    JOIN works w ON w.id = f.wid
    LEFT JOIN document_nodes dn ON dn.id = f.nid
    ORDER BY f.sc DESC, w.year DESC, w.id DESC
    LIMIT p_limit;
END;
$$;

-- 014 — FTS indexes (GIN on the generated tsvector columns)
-- Built after bulk load. In production against a live table, use
-- CREATE INDEX CONCURRENTLY (cannot run inside a transaction block).

CREATE INDEX idx_works_search_fts ON works USING GIN(search_fts);
CREATE INDEX idx_nodes_fts        ON document_nodes USING GIN(fts);

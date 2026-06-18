-- 003 — document_nodes (hierarchical content + pgvector embedding)
-- The GIN index on fts (014) and the HNSW index on embedding (016) are deferred
-- so they build faster after bulk load. Only btree indexes here.

-- vector type lives in the extensions schema.
SET search_path TO public, extensions;

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
    embedding       vector(1536),
    fts             TSVECTOR GENERATED ALWAYS AS (
                        to_tsvector('indonesian', COALESCE(content_text, ''))
                    ) STORED,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_nodes_work   ON document_nodes(work_id);
CREATE INDEX idx_nodes_type   ON document_nodes(node_type);
CREATE INDEX idx_nodes_parent ON document_nodes(parent_id);
CREATE INDEX idx_nodes_sort   ON document_nodes(work_id, sort_order);
-- Partial index for the embedding backfill job to find nodes still missing an embedding.
CREATE INDEX idx_nodes_no_embedding ON document_nodes(id) WHERE embedding IS NULL;

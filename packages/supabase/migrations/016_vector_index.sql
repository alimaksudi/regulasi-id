-- 016 — pgvector HNSW index on document_nodes.embedding (cosine)
-- m = 16 graph connectivity, ef_construction = 64 build-time search width.
-- Query time recall is tuned with SET hnsw.ef_search (done inside search_regulations).
-- vector_cosine_ops comes from pgvector in the extensions schema.

SET search_path TO public, extensions;

CREATE INDEX idx_nodes_embedding ON document_nodes
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

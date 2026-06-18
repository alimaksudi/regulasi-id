-- 015 — trigram index on works.title_id (fuzzy title matching, ILIKE acceleration)
-- gin_trgm_ops comes from pg_trgm in the extensions schema.

SET search_path TO public, extensions;

CREATE INDEX idx_works_trgm ON works USING GIN(title_id gin_trgm_ops);

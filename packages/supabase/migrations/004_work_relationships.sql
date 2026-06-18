-- 004 — work_relationships
-- Designed here; DATABASE.md names this table in the migration plan and ER diagram
-- but does not give a DDL block. A relationship is a directed edge between two works,
-- typed by relationship_types (001). to_work_id is nullable because the crawler often
-- finds a cross reference to a regulation that is not in the database yet; in that case
-- the raw citation text is kept in to_work_citation.

CREATE TABLE work_relationships (
    id                    SERIAL PRIMARY KEY,
    from_work_id          INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    to_work_id            INTEGER REFERENCES works(id) ON DELETE SET NULL,
    relationship_type_id  INTEGER NOT NULL REFERENCES relationship_types(id),
    to_work_citation      TEXT,  -- raw reference text when to_work_id is unresolved
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_work_rel_from ON work_relationships(from_work_id);
CREATE INDEX idx_work_rel_to   ON work_relationships(to_work_id);
CREATE INDEX idx_work_rel_type ON work_relationships(relationship_type_id);
-- Avoid duplicate edges of the same type between the same two works.
CREATE UNIQUE INDEX idx_work_rel_unique
    ON work_relationships(from_work_id, to_work_id, relationship_type_id)
    WHERE to_work_id IS NOT NULL;

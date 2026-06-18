-- 007 — revisions (append-only audit log). Never UPDATE or DELETE rows here.
-- DATABASE.md declares suggestion_id with an inline FK to suggestions, but suggestions
-- is created in 008. The column is created here and the FK is added in 008.

CREATE TABLE revisions (
    id              BIGSERIAL PRIMARY KEY,
    node_id         BIGINT NOT NULL REFERENCES document_nodes(id),
    old_content     TEXT,
    new_content     TEXT NOT NULL,
    reason          TEXT,
    actor           TEXT,  -- 'system' | 'admin:email' | 'agent:gemini'
    suggestion_id   INTEGER,  -- FK added in 008 once suggestions exists
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_revisions_node ON revisions(node_id);

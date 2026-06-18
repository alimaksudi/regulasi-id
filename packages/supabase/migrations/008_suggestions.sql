-- 008 — suggestions (crowd-sourced corrections). Also closes the revisions FK
-- that could not be declared in 007.

CREATE TABLE suggestions (
    id                      SERIAL PRIMARY KEY,
    work_id                 INTEGER NOT NULL REFERENCES works(id),
    node_id                 BIGINT NOT NULL REFERENCES document_nodes(id),
    node_type               TEXT,
    node_number             TEXT,
    current_content         TEXT NOT NULL,
    suggested_content       TEXT NOT NULL,
    user_reason             TEXT,
    submitter_email         TEXT,
    submitter_ip            TEXT,
    status                  TEXT DEFAULT 'pending',  -- pending | verified | approved | rejected
    agent_decision          TEXT,
    agent_confidence        FLOAT,
    agent_modified_content  TEXT,
    agent_response          JSONB,
    admin_note              TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_suggestions_status ON suggestions(status);
CREATE INDEX idx_suggestions_work   ON suggestions(work_id);
CREATE INDEX idx_suggestions_node   ON suggestions(node_id);

ALTER TABLE revisions
    ADD CONSTRAINT revisions_suggestion_id_fkey
    FOREIGN KEY (suggestion_id) REFERENCES suggestions(id);

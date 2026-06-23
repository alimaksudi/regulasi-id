-- 005 — abstracts (one OJK abstract PDF per work)

CREATE TABLE abstracts (
    id              SERIAL PRIMARY KEY,
    work_id         INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE UNIQUE,
    content_text    TEXT,
    source_pdf_url  TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

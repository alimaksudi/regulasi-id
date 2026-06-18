-- 006 — faqs (one OJK FAQ PDF per work, where available)

CREATE TABLE faqs (
    id              SERIAL PRIMARY KEY,
    work_id         INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE UNIQUE,
    content_text    TEXT,
    source_pdf_url  TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

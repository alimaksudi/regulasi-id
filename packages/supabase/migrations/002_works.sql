-- 002 — works table + slug trigger + search_text trigger
-- The GIN index on search_fts (014) and the trigram index on title_id (015) are
-- deferred so they can be built after bulk load. Only btree indexes here.

CREATE TABLE works (
    id                  SERIAL PRIMARY KEY,
    sector_id           INTEGER REFERENCES sectors(id),
    regulation_type_id  INTEGER NOT NULL REFERENCES regulation_types(id),
    frbr_uri            TEXT UNIQUE,
    slug                TEXT UNIQUE,
    title_id            TEXT NOT NULL,
    number              TEXT NOT NULL,
    year                INTEGER NOT NULL,
    status              TEXT DEFAULT 'berlaku',  -- berlaku | diubah | dicabut | tidak_berlaku
    date_enacted        DATE,
    source_url          TEXT,
    source_pdf_url      TEXT,
    content_verified    BOOLEAN DEFAULT false,
    extraction_quality  FLOAT,
    subject_tags        TEXT[],
    tentang             TEXT,
    search_text         TEXT,
    search_fts          TSVECTOR GENERATED ALWAYS AS (
                            to_tsvector('indonesian', COALESCE(search_text, ''))
                        ) STORED,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_works_sector  ON works(sector_id);
CREATE INDEX idx_works_type    ON works(regulation_type_id);
CREATE INDEX idx_works_year    ON works(year);
CREATE INDEX idx_works_status  ON works(status);
CREATE INDEX idx_works_slug    ON works(slug);
CREATE INDEX idx_works_cursor  ON works(year DESC, id DESC);  -- cursor pagination

-- Derives slug and search_text on write. search_fts (generated) recomputes from
-- search_text automatically after this BEFORE trigger runs.
CREATE OR REPLACE FUNCTION works_set_derived() RETURNS TRIGGER
SET search_path = 'public', 'extensions'
LANGUAGE plpgsql
AS $$
DECLARE
    v_type_code TEXT;
BEGIN
    SELECT code INTO v_type_code FROM regulation_types WHERE id = NEW.regulation_type_id;

    -- slug is set once and then stable (it is a public URL).
    IF NEW.slug IS NULL THEN
        NEW.slug := trim(BOTH '-' FROM regexp_replace(
            lower(v_type_code || '-' || NEW.number || '-' || NEW.year::text),
            '[^a-z0-9]+', '-', 'g'
        ));
    END IF;

    NEW.search_text := concat_ws(' ',
        NEW.title_id,
        NEW.tentang,
        v_type_code,
        NEW.number,
        NEW.year::text,
        array_to_string(NEW.subject_tags, ' ')
    );

    IF TG_OP = 'UPDATE' THEN
        NEW.updated_at := now();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_works_set_derived
    BEFORE INSERT OR UPDATE ON works
    FOR EACH ROW EXECUTE FUNCTION works_set_derived();

-- 009 — compliance_mappings (curated sector + business_type -> applicable works)

CREATE TABLE compliance_mappings (
    id              SERIAL PRIMARY KEY,
    sector_id       INTEGER NOT NULL REFERENCES sectors(id),
    business_type   TEXT,           -- null = sector-wide
    work_id         INTEGER NOT NULL REFERENCES works(id),
    priority        TEXT NOT NULL,  -- required | recommended | conditional
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_compliance_sector   ON compliance_mappings(sector_id);
CREATE INDEX idx_compliance_business ON compliance_mappings(business_type);
CREATE INDEX idx_compliance_work     ON compliance_mappings(work_id);

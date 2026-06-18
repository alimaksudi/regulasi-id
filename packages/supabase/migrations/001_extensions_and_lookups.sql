-- 001 — extensions + lookup tables (sectors, regulation_types, relationship_types)
-- Run via direct connection (port 5432), not PgBouncer.
-- RLS for these tables is applied later in migration 017.

-- Extensions live in the `extensions` schema (Supabase convention). Functions that
-- reference them set search_path = 'public', 'extensions'.
CREATE SCHEMA IF NOT EXISTS extensions;

CREATE EXTENSION IF NOT EXISTS pg_trgm   WITH SCHEMA extensions;  -- trigram similarity
CREATE EXTENSION IF NOT EXISTS unaccent  WITH SCHEMA extensions;  -- accent-insensitive search
CREATE EXTENSION IF NOT EXISTS vector    WITH SCHEMA extensions;  -- pgvector for embeddings
-- pg_cron installs into its own `cron` schema and is only used by migration 020.
-- On some Supabase plans it must be enabled from the dashboard first.
CREATE EXTENSION IF NOT EXISTS pg_cron;


-- sectors
CREATE TABLE sectors (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(30) UNIQUE NOT NULL,
    name_id     VARCHAR(100) NOT NULL,
    name_en     VARCHAR(100),
    jdih_code   VARCHAR(5)
);

INSERT INTO sectors (code, name_id, name_en, jdih_code) VALUES
    ('perbankan',     'Perbankan',                  'Banking',                     '01'),
    ('pasar-modal',   'Pasar Modal',                'Capital Markets',             '02'),
    ('iknb',          'Industri Keuangan Non-Bank', 'Non-Bank Financial Industry', '08'),
    ('fintech',       'Teknologi Finansial',        'Financial Technology',        '10'),
    ('dana-pensiun',  'Dana Pensiun',               'Pension Funds',               '06'),
    ('perasuransian', 'Perasuransian',              'Insurance',                   '04')
ON CONFLICT (code) DO NOTHING;


-- regulation_types
CREATE TABLE regulation_types (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(20) UNIQUE NOT NULL,
    name_id         VARCHAR(100) NOT NULL,
    name_en         VARCHAR(100),
    hierarchy_level INTEGER NOT NULL,
    jdih_code       VARCHAR(5)
);

INSERT INTO regulation_types (code, name_id, name_en, hierarchy_level, jdih_code) VALUES
    ('UU',      'Undang-Undang',        'Law',                   1, '01'),
    ('PP',      'Peraturan Pemerintah', 'Government Regulation',  2, '02'),
    ('PERPRES', 'Peraturan Presiden',   'Presidential Reg.',      3, '03'),
    ('POJK',    'Peraturan OJK',        'OJK Regulation',         4, '06'),
    ('SEOJK',   'Surat Edaran OJK',     'OJK Circular',           5, '07'),
    ('KEOJK',   'Keputusan OJK',        'OJK Decision',           6, '08')
ON CONFLICT (code) DO NOTHING;


-- relationship_types
-- Lookup for work_relationships (added in migration 004). Cross-references between
-- regulations are directed edges; we seed both forward verbs and their inverses so
-- both endpoints of an edge can be labelled in the UI.
CREATE TABLE relationship_types (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(30) UNIQUE NOT NULL,
    name_id     VARCHAR(100) NOT NULL,
    name_en     VARCHAR(100)
);

INSERT INTO relationship_types (code, name_id, name_en) VALUES
    ('mengubah',          'Mengubah',          'Amends'),
    ('diubah_oleh',       'Diubah oleh',       'Amended by'),
    ('mencabut',          'Mencabut',          'Revokes'),
    ('dicabut_oleh',      'Dicabut oleh',      'Revoked by'),
    ('mencabut_sebagian', 'Mencabut sebagian', 'Partially revokes'),
    ('melaksanakan',      'Melaksanakan',      'Implements'),
    ('dasar_hukum',       'Dasar hukum',       'Legal basis'),
    ('terkait',           'Terkait',           'Related')
ON CONFLICT (code) DO NOTHING;

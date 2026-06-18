-- Idempotent sample data for local testing. Safe to re-run.
TRUNCATE works, document_nodes, compliance_mappings RESTART IDENTITY CASCADE;

INSERT INTO works (sector_id, regulation_type_id, title_id, number, year, tentang, status)
SELECT s.id, rt.id, 'POJK tentang Penyelenggaraan Layanan Pendanaan Bersama Berbasis Teknologi Informasi',
       '10', 2022, 'Layanan Pendanaan Bersama Berbasis Teknologi Informasi (LPBBTI)', 'berlaku'
FROM sectors s, regulation_types rt WHERE s.code='fintech' AND rt.code='POJK';

INSERT INTO works (sector_id, regulation_type_id, title_id, number, year, tentang, status)
SELECT s.id, rt.id, 'POJK tentang Bank Umum', '12', 2021, 'Bank Umum', 'berlaku'
FROM sectors s, regulation_types rt WHERE s.code='perbankan' AND rt.code='POJK';

INSERT INTO document_nodes (work_id, node_type, number, heading, content_text, sort_order) VALUES
 (1,'bab','V','KELEMBAGAAN',NULL,2000),
 (1,'pasal','24',NULL,'Penyelenggara wajib memiliki modal disetor paling sedikit sebesar Rp25.000.000.000,00 (dua puluh lima miliar rupiah).',2400),
 (1,'ayat','1',NULL,'Modal disetor sebagaimana dimaksud dalam Pasal 24 wajib dipenuhi pada saat pendirian.',2410),
 (1,'pasal','1',NULL,'Dalam Peraturan Otoritas Jasa Keuangan ini yang dimaksud dengan Layanan Pendanaan Bersama.',100);

INSERT INTO compliance_mappings (sector_id, business_type, work_id, priority, notes)
SELECT s.id, 'p2p-lending', 1, 'required', 'Regulasi utama perizinan P2P lending (LPBBTI).'
FROM sectors s WHERE s.code='fintech';

-- frbr_uri is normally set by the pipeline loader; set it here for the seeded rows.
UPDATE works w SET frbr_uri = '/akn/id/act/' || lower(rt.code) || '/' || w.year || '/' || w.number
FROM regulation_types rt WHERE rt.id = w.regulation_type_id AND w.frbr_uri IS NULL;

REFRESH MATERIALIZED VIEW mv_sector_stats;
REFRESH MATERIALIZED VIEW mv_type_stats;

-- 017 — RLS policies
-- Public read on regulatory content. Write paths (suggestions insert) are open;
-- everything else (analytics, crawl_jobs, revisions, discovery_progress) is service
-- role only: RLS enabled with no policy, so anon/authenticated see nothing while the
-- service role key bypasses RLS.

-- public read
ALTER TABLE sectors ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON sectors FOR SELECT USING (true);

ALTER TABLE regulation_types ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON regulation_types FOR SELECT USING (true);

ALTER TABLE relationship_types ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON relationship_types FOR SELECT USING (true);

ALTER TABLE works ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON works FOR SELECT USING (true);

ALTER TABLE document_nodes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON document_nodes FOR SELECT USING (true);

ALTER TABLE abstracts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON abstracts FOR SELECT USING (true);

ALTER TABLE faqs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON faqs FOR SELECT USING (true);

ALTER TABLE work_relationships ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON work_relationships FOR SELECT USING (true);

ALTER TABLE compliance_mappings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON compliance_mappings FOR SELECT USING (true);

-- public insert, service role reads
ALTER TABLE suggestions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public insert" ON suggestions FOR INSERT WITH CHECK (true);

-- service role only (RLS on, no policy)
ALTER TABLE search_analytics   ENABLE ROW LEVEL SECURITY;
ALTER TABLE crawl_jobs         ENABLE ROW LEVEL SECURITY;
ALTER TABLE revisions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE discovery_progress ENABLE ROW LEVEL SECURITY;

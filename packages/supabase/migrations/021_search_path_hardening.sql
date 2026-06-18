-- 021 — search_path hardening on all functions.
-- Each function already sets search_path in its definition; this pins it explicitly
-- as a defense-in-depth pass and a single place to audit. A fixed search_path stops
-- a malicious object in a caller-controlled schema from shadowing a referenced one.

SET search_path TO public, extensions;

ALTER FUNCTION works_set_derived()                                              SET search_path = 'public', 'extensions';
ALTER FUNCTION claim_jobs(int, text)                                            SET search_path = 'public', 'extensions';
ALTER FUNCTION apply_revision(bigint, text, text, text, integer)                SET search_path = 'public', 'extensions';
ALTER FUNCTION search_regulations(text, text, text, int, int, text, int, vector) SET search_path = 'public', 'extensions';

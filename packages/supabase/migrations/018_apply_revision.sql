-- 018 — apply_revision(): the only sanctioned path to mutate node content.
-- Writes the audit row, updates content, nulls the embedding (background regen),
-- and closes the suggestion if one triggered the change. All in one transaction.

CREATE OR REPLACE FUNCTION apply_revision(
    p_node_id       BIGINT,
    p_new_content   TEXT,
    p_reason        TEXT,
    p_actor         TEXT,
    p_suggestion_id INTEGER DEFAULT NULL
) RETURNS VOID
SET search_path = 'public', 'extensions'
AS $$
BEGIN
    INSERT INTO revisions (node_id, old_content, new_content, reason, actor, suggestion_id)
    SELECT p_node_id, content_text, p_new_content, p_reason, p_actor, p_suggestion_id
    FROM document_nodes WHERE id = p_node_id;

    UPDATE document_nodes
    SET content_text = p_new_content, embedding = NULL  -- NULL signals background regen
    WHERE id = p_node_id;

    IF p_suggestion_id IS NOT NULL THEN
        UPDATE suggestions SET status = 'approved', updated_at = NOW()
        WHERE id = p_suggestion_id;
    END IF;
END;
$$ LANGUAGE plpgsql;

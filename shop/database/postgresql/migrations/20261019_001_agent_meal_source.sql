-- Preserve existing packages; only new Agent exports carry a signed source proof.
ALTER TABLE fa_shop_recommendation_package
    ADD COLUMN IF NOT EXISTS agent_source_proof_json text NOT NULL DEFAULT '{}';

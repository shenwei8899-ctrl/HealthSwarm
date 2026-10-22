-- Preserve existing identities. Unknown history stays unknown; no approval or login is inferred.
ALTER TABLE fa_shop_external_identity
    ADD COLUMN IF NOT EXISTS external_account_id varchar(32) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS external_account_name varchar(100) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS last_login_channel varchar(16) NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS last_seen_at bigint NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_wechat_verified_at bigint NOT NULL DEFAULT 0;

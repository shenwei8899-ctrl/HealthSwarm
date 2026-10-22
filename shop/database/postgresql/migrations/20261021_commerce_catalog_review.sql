BEGIN;
ALTER TABLE fa_shop_ingredient_sku_map ADD COLUMN IF NOT EXISTS source_ref text NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS fa_shop_catalog_review_log (
    id bigserial PRIMARY KEY,
    resource_type varchar(40) NOT NULL,
    resource_id bigint NOT NULL,
    admin_id bigint NOT NULL,
    before_json text NOT NULL,
    after_json text NOT NULL,
    createtime bigint NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shop_catalog_review_resource ON fa_shop_catalog_review_log(resource_type,resource_id);
COMMIT;

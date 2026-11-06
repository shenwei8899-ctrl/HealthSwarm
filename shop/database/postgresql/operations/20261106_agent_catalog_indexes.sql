-- Run separately from a transaction after checking the real query plan.
-- The search uses case-insensitive substring matching on these fields.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX CONCURRENTLY IF NOT EXISTS fa_shop_goods_agent_title_trgm
  ON fa_shop_goods USING gin ((regexp_replace(title, '[[:space:]]+', '', 'g')) gin_trgm_ops)
  WHERE agent_visible = 1 AND catalog_status = 'published' AND status = 'normal' AND deletetime IS NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS fa_shop_goods_sku_label_trgm
  ON fa_shop_goods_sku USING gin ((regexp_replace(sku_id, '[[:space:]]+', '', 'g')) gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS fa_shop_goods_sku_code_trgm
  ON fa_shop_goods_sku USING gin ((regexp_replace(sku_code, '[[:space:]]+', '', 'g')) gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS fa_shop_category_agent_name_trgm
  ON fa_shop_category USING gin ((regexp_replace(name, '[[:space:]]+', '', 'g')) gin_trgm_ops)
  WHERE status = 'normal' AND agent_visible = 1;

CREATE INDEX CONCURRENTLY IF NOT EXISTS fa_shop_ingredient_name_trgm
  ON fa_shop_ingredient USING gin ((regexp_replace(name, '[[:space:]]+', '', 'g')) gin_trgm_ops)
  WHERE status = 'normal' AND deletetime IS NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS fa_shop_ingredient_code_trgm
  ON fa_shop_ingredient USING gin ((regexp_replace(ingredient_code, '[[:space:]]+', '', 'g')) gin_trgm_ops)
  WHERE status = 'normal' AND deletetime IS NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS fa_shop_ingredient_alias_name_trgm
  ON fa_shop_ingredient_alias USING gin ((regexp_replace(alias, '[[:space:]]+', '', 'g')) gin_trgm_ops)
  WHERE status = 'normal';

CREATE INDEX CONCURRENTLY IF NOT EXISTS fa_shop_goods_business_category_trgm
  ON fa_shop_goods USING gin ((regexp_replace(business_category_code, '[[:space:]]+', '', 'g')) gin_trgm_ops)
  WHERE agent_visible = 1 AND catalog_status = 'published' AND status = 'normal' AND deletetime IS NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS fa_shop_ingredient_restriction_name
  ON fa_shop_ingredient (lower(regexp_replace(name, '[[:space:]]+', '', 'g')))
  WHERE status = 'normal' AND deletetime IS NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS fa_shop_ingredient_alias_restriction_name
  ON fa_shop_ingredient_alias (lower(regexp_replace(alias, '[[:space:]]+', '', 'g')))
  WHERE status = 'normal';

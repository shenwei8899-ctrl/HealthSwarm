SET NAMES utf8mb4;
SET @now = UNIX_TIMESTAMP();

-- Supply price is maintained on the supply relationship; inventory adjustment is
-- performed from an individual warehouse stock row. Keep no duplicate menu entry.
UPDATE fa_auth_rule
SET ismenu=0, updatetime=@now
WHERE name IN ('shop/supplier_price', 'shop/inventory_adjustment');

-- A platform SKU can be held in the same warehouse by multiple suppliers.
ALTER TABLE fa_shop_warehouse_sku
  DROP INDEX uk_warehouse_goods_sku,
  ADD UNIQUE KEY uk_warehouse_supplier_sku (warehouse_id, supplier_id, supplier_sku_id, goods_id, goods_sku_id),
  ADD KEY idx_warehouse_goods_sku (warehouse_id, goods_id, goods_sku_id);

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260927_015','合并重复供货与库存菜单，支持同仓多供应商 SKU 分库存',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

SET NAMES utf8mb4;
SET @now = UNIX_TIMESTAMP();

-- 仅修复 20260924_012 早期重复执行产生的 MOCK 商品及其从属演示记录。
CREATE TEMPORARY TABLE `tmp_mock_duplicate_goods` AS
SELECT duplicate_goods.id
FROM `fa_shop_goods` duplicate_goods
JOIN `fa_shop_goods` retained_goods
  ON retained_goods.goods_sn=duplicate_goods.goods_sn AND retained_goods.id<duplicate_goods.id
WHERE duplicate_goods.goods_sn LIKE 'MOCK_NUTRITION_%';

DELETE flow FROM `fa_shop_stock_flow` flow
JOIN `fa_shop_warehouse_sku` stock ON stock.id=flow.warehouse_sku_id
JOIN `tmp_mock_duplicate_goods` duplicate_goods ON duplicate_goods.id=stock.goods_id;
DELETE batch FROM `fa_shop_stock_batch` batch
JOIN `fa_shop_warehouse_sku` stock ON stock.id=batch.warehouse_sku_id
JOIN `tmp_mock_duplicate_goods` duplicate_goods ON duplicate_goods.id=stock.goods_id;
DELETE stock FROM `fa_shop_warehouse_sku` stock
JOIN `tmp_mock_duplicate_goods` duplicate_goods ON duplicate_goods.id=stock.goods_id;
DELETE supplier_sku FROM `fa_shop_supplier_sku` supplier_sku
JOIN `tmp_mock_duplicate_goods` duplicate_goods ON duplicate_goods.id=supplier_sku.goods_id;
DELETE map FROM `fa_shop_ingredient_product_map` map
JOIN `tmp_mock_duplicate_goods` duplicate_goods ON duplicate_goods.id=map.goods_id;
DELETE substitute FROM `fa_shop_goods_substitute` substitute
JOIN `tmp_mock_duplicate_goods` duplicate_goods
  ON duplicate_goods.id=substitute.goods_id OR duplicate_goods.id=substitute.substitute_goods_id;
DELETE sku_ext FROM `fa_shop_sku_ext` sku_ext
JOIN `tmp_mock_duplicate_goods` duplicate_goods ON duplicate_goods.id=sku_ext.goods_id;
DELETE goods_ext FROM `fa_shop_goods_ext` goods_ext
JOIN `tmp_mock_duplicate_goods` duplicate_goods ON duplicate_goods.id=goods_ext.goods_id;
DELETE sku FROM `fa_shop_goods_sku` sku
JOIN `tmp_mock_duplicate_goods` duplicate_goods ON duplicate_goods.id=sku.goods_id;
DELETE goods FROM `fa_shop_goods` goods
JOIN `tmp_mock_duplicate_goods` duplicate_goods ON duplicate_goods.id=goods.id;
DROP TEMPORARY TABLE `tmp_mock_duplicate_goods`;

-- 重放已修正的演示数据时，剩余数据由 012 的可重复语句维护。
INSERT INTO `fa_shop_schema_migration` (`version`,`description`,`applied_at`)
VALUES ('20260924_013','修复早期重复执行产生的 MOCK 营养商品演示数据',@now)
ON DUPLICATE KEY UPDATE `description`=VALUES(`description`),`applied_at`=VALUES(`applied_at`);

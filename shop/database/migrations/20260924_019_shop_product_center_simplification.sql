SET NAMES utf8mb4;
SET @now=UNIX_TIMESTAMP();
SET @product_center=(SELECT id FROM fa_auth_rule WHERE name='shop/product_center' LIMIT 1);

UPDATE fa_auth_rule
SET ismenu=0,updatetime=@now
WHERE pid=@product_center
  AND name NOT IN ('shop/goods','shop/ingredient','shop/ingredient_product_map');

UPDATE fa_auth_rule
SET pid=@product_center,ismenu=1,status='normal',updatetime=@now
WHERE name IN ('shop/goods','shop/ingredient','shop/ingredient_product_map');

UPDATE fa_auth_rule SET title='商品管理',weigh=80,updatetime=@now WHERE name='shop/goods';
UPDATE fa_auth_rule SET title='标准食材库',weigh=79,updatetime=@now WHERE name='shop/ingredient';
UPDATE fa_auth_rule SET title='食材商品匹配',weigh=78,updatetime=@now WHERE name='shop/ingredient_product_map';

UPDATE fa_auth_rule
SET ismenu=0,updatetime=@now
WHERE name IN ('shop/category','shop/brand','shop/attribute','shop/spec_sku','shop/spec','shop/sku_template','shop/goods_substitute');

SET @goods_rule=(SELECT id FROM fa_auth_rule WHERE name='shop/goods' LIMIT 1);
INSERT INTO fa_auth_rule
(`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`)
VALUES
('file',@goods_rule,'shop/goods/supplychain','查看供应链详情','fa fa-sitemap',0,@now,@now,0,'normal')
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),icon=VALUES(icon),ismenu=0,status='normal',updatetime=@now;

UPDATE fa_auth_group SET rules=(
  SELECT GROUP_CONCAT(id ORDER BY id) FROM fa_auth_rule
  WHERE name='shop'
     OR name REGEXP '^shop/(product_center|goods|goods_sku|goods_sku_spec|goods_substitute|category|brand|attribute|attribute_value|spec|spec_sku|spec_value|sku_template|ingredient|ingredient_product_map|supplier_sku)(/|$)'
),updatetime=@now WHERE name='商城运营';

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260924_019','商品中心精简为商品管理、标准食材库和食材商品匹配，并聚合供应链详情',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

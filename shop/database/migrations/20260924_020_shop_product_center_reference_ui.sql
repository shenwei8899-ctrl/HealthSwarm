SET NAMES utf8mb4;
SET @now=UNIX_TIMESTAMP();
SET @product_center=(SELECT id FROM fa_auth_rule WHERE name='shop/product_center' LIMIT 1);

UPDATE fa_auth_rule
SET ismenu=0,updatetime=@now
WHERE pid=@product_center
  AND name NOT IN ('shop/goods','shop/category','shop/attribute','shop/brand');

UPDATE fa_auth_rule
SET pid=@product_center,ismenu=1,status='normal',updatetime=@now
WHERE name IN ('shop/goods','shop/category','shop/attribute','shop/brand');

UPDATE fa_auth_rule SET title='商品列表',icon='fa fa-list-alt',weigh=80,updatetime=@now WHERE name='shop/goods';
UPDATE fa_auth_rule SET title='商品分类',icon='fa fa-sitemap',weigh=79,updatetime=@now WHERE name='shop/category';
UPDATE fa_auth_rule SET title='商品类型',icon='fa fa-tags',weigh=78,updatetime=@now WHERE name='shop/attribute';
UPDATE fa_auth_rule SET title='品牌管理',icon='fa fa-copyright',weigh=77,updatetime=@now WHERE name='shop/brand';

UPDATE fa_auth_group SET rules=(
  SELECT GROUP_CONCAT(id ORDER BY id) FROM fa_auth_rule
  WHERE name='shop'
     OR name REGEXP '^shop/(product_center|goods|goods_sku|goods_sku_spec|goods_substitute|category|brand|attribute|attribute_value|spec|spec_sku|spec_value|sku_template|ingredient|ingredient_product_map|supplier_sku)(/|$)'
),updatetime=@now WHERE name='商城运营';

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260924_020','商品中心按参考后台调整为商品列表、商品分类、商品类型和品牌管理',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

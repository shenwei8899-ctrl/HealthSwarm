SET NAMES utf8mb4;
SET @now = UNIX_TIMESTAMP();

-- 演示数据全部使用 MOCK_ 编码；真实主数据导入后可按编码整批替换。
INSERT INTO `fa_shop_goods`
(`category_id`,`goods_sn`,`title`,`subtitle`,`keywords`,`description`,`marketprice`,`price`,`stocks`,`sales`,`spectype`,`weight`,`isvirtual`,`weigh`,`createtime`,`updatetime`,`status`)
SELECT v.* FROM (
  SELECT 0 AS category_id, 'MOCK_NUTRITION_OAT' AS goods_sn, '演示-即食燕麦片 500g' AS title, 'MOCK 演示营养食材' AS subtitle, '燕麦,全谷物,演示' AS keywords, '用于商城供应链流程演示的模拟商品' AS description, 29.90 AS marketprice, 24.90 AS price, 120 AS stocks, 0 AS sales, 1 AS spectype, 0 AS weight, 0 AS isvirtual, 100 AS weigh, @now AS createtime, @now AS updatetime, 'normal' AS status
  UNION ALL SELECT 0, 'MOCK_NUTRITION_MILK', '演示-高钙纯牛奶 250ml x 12', 'MOCK 演示营养食材', '牛奶,高钙,演示', '用于商城供应链流程演示的模拟商品', 79.90, 69.90, 100, 0, 1, 0, 0, 99, @now, @now, 'normal'
  UNION ALL SELECT 0, 'MOCK_NUTRITION_EGG', '演示-谷物鲜鸡蛋 10枚', 'MOCK 演示营养食材', '鸡蛋,蛋白质,演示', '用于商城供应链流程演示的模拟商品', 22.90, 19.90, 80, 0, 1, 0, 0, 98, @now, @now, 'normal'
  UNION ALL SELECT 0, 'MOCK_NUTRITION_TOFU', '演示-有机北豆腐 400g', 'MOCK 演示营养食材', '豆腐,植物蛋白,演示', '用于商城供应链流程演示的模拟商品', 12.90, 9.90, 60, 0, 1, 0, 0, 97, @now, @now, 'normal'
  UNION ALL SELECT 0, 'MOCK_NUTRITION_BANANA', '演示-香蕉 1kg', 'MOCK 演示营养食材', '香蕉,水果,演示', '用于商城供应链流程演示的模拟商品', 18.90, 15.90, 8, 0, 1, 0, 0, 96, @now, @now, 'normal'
) AS v
LEFT JOIN `fa_shop_goods` g ON g.goods_sn=v.goods_sn
WHERE g.id IS NULL;

INSERT INTO `fa_shop_goods_sku`
(`goods_id`,`goods_sn`,`sku_id`,`image`,`price`,`marketprice`,`stocks`,`sales`,`weigh`,`createtime`,`updatetime`)
SELECT g.id,g.goods_sn,'DEFAULT','',g.price,g.marketprice,g.stocks,0,g.weigh,@now,@now
FROM `fa_shop_goods` g
WHERE g.goods_sn LIKE 'MOCK_NUTRITION_%'
  AND NOT EXISTS (SELECT 1 FROM `fa_shop_goods_sku` s WHERE s.goods_id=g.id AND s.sku_id='DEFAULT');

INSERT INTO `fa_shop_goods_ext`
(`goods_id`,`product_type`,`composition_json`,`allergen_tags_json`,`applicable_tags_json`,`origin`,`storage_condition`,`shelf_life_days`,`delivery_scope_type`,`createtime`,`updatetime`)
SELECT g.id,'INGREDIENT',
       CASE g.goods_sn
         WHEN 'MOCK_NUTRITION_OAT' THEN JSON_ARRAY('燕麦')
         WHEN 'MOCK_NUTRITION_MILK' THEN JSON_ARRAY('生牛乳')
         WHEN 'MOCK_NUTRITION_EGG' THEN JSON_ARRAY('鸡蛋')
         WHEN 'MOCK_NUTRITION_TOFU' THEN JSON_ARRAY('大豆','饮用水')
         ELSE JSON_ARRAY('香蕉') END,
       CASE g.goods_sn
         WHEN 'MOCK_NUTRITION_MILK' THEN JSON_ARRAY('milk')
         WHEN 'MOCK_NUTRITION_EGG' THEN JSON_ARRAY('egg')
         WHEN 'MOCK_NUTRITION_TOFU' THEN JSON_ARRAY('soy')
         ELSE JSON_ARRAY() END,
       JSON_ARRAY('家庭营养','MOCK'), 'MOCK 演示产地',
       CASE WHEN g.goods_sn IN ('MOCK_NUTRITION_MILK','MOCK_NUTRITION_TOFU') THEN '冷藏 2-6℃' ELSE '阴凉干燥处' END,
       CASE WHEN g.goods_sn='MOCK_NUTRITION_TOFU' THEN 7 WHEN g.goods_sn='MOCK_NUTRITION_BANANA' THEN 10 ELSE 180 END,
       'ALL',@now,@now
FROM `fa_shop_goods` g WHERE g.goods_sn LIKE 'MOCK_NUTRITION_%'
ON DUPLICATE KEY UPDATE `product_type`=VALUES(`product_type`),`composition_json`=VALUES(`composition_json`),`allergen_tags_json`=VALUES(`allergen_tags_json`),`applicable_tags_json`=VALUES(`applicable_tags_json`),`origin`=VALUES(`origin`),`storage_condition`=VALUES(`storage_condition`),`shelf_life_days`=VALUES(`shelf_life_days`),`delivery_scope_type`=VALUES(`delivery_scope_type`),`updatetime`=@now;

INSERT INTO `fa_shop_sku_ext`
(`goods_id`,`goods_sku_id`,`barcode`,`unit`,`net_quantity`,`net_unit`,`reference_cost_price`,`safety_stock`,`batch_enabled`,`expiry_enabled`,`createtime`,`updatetime`)
SELECT g.id,s.id,CONCAT('MOCK-BARCODE-',g.id),'件',
       CASE g.goods_sn WHEN 'MOCK_NUTRITION_OAT' THEN 500 WHEN 'MOCK_NUTRITION_MILK' THEN 3000 WHEN 'MOCK_NUTRITION_EGG' THEN 10 WHEN 'MOCK_NUTRITION_TOFU' THEN 400 ELSE 1000 END,
       CASE WHEN g.goods_sn='MOCK_NUTRITION_EGG' THEN '枚' ELSE 'g' END,
       ROUND(g.price*0.62,2),CASE WHEN g.goods_sn='MOCK_NUTRITION_BANANA' THEN 20 ELSE 30 END,1,1,@now,@now
FROM `fa_shop_goods` g JOIN `fa_shop_goods_sku` s ON s.goods_id=g.id AND s.sku_id='DEFAULT'
WHERE g.goods_sn LIKE 'MOCK_NUTRITION_%'
ON DUPLICATE KEY UPDATE `barcode`=VALUES(`barcode`),`unit`=VALUES(`unit`),`net_quantity`=VALUES(`net_quantity`),`net_unit`=VALUES(`net_unit`),`reference_cost_price`=VALUES(`reference_cost_price`),`safety_stock`=VALUES(`safety_stock`),`batch_enabled`=1,`expiry_enabled`=1,`updatetime`=@now;

INSERT INTO `fa_shop_ingredient` (`code`,`name`,`category`,`default_unit`,`aliases_json`,`status`,`createtime`,`updatetime`) VALUES
('MOCK_INGREDIENT_OAT','燕麦','全谷物','g',JSON_ARRAY('燕麦片'),'normal',@now,@now),
('MOCK_INGREDIENT_MILK','牛奶','乳制品','ml',JSON_ARRAY('纯牛奶'),'normal',@now,@now),
('MOCK_INGREDIENT_EGG','鸡蛋','蛋类','枚',JSON_ARRAY('鲜鸡蛋'),'normal',@now,@now),
('MOCK_INGREDIENT_TOFU','北豆腐','豆制品','g',JSON_ARRAY('豆腐'),'normal',@now,@now),
('MOCK_INGREDIENT_BANANA','香蕉','水果','g',JSON_ARRAY('香蕉果肉'),'normal',@now,@now)
ON DUPLICATE KEY UPDATE `name`=VALUES(`name`),`category`=VALUES(`category`),`aliases_json`=VALUES(`aliases_json`),`status`='normal',`updatetime`=@now;

INSERT INTO `fa_shop_ingredient_product_map`
(`ingredient_id`,`goods_id`,`goods_sku_id`,`content_quantity`,`content_unit`,`conversion_rate`,`priority`,`is_substitute`,`status`,`createtime`,`updatetime`)
SELECT i.id,g.id,s.id,
       CASE g.goods_sn WHEN 'MOCK_NUTRITION_OAT' THEN 500 WHEN 'MOCK_NUTRITION_MILK' THEN 3000 WHEN 'MOCK_NUTRITION_EGG' THEN 10 WHEN 'MOCK_NUTRITION_TOFU' THEN 400 ELSE 1000 END,
       CASE WHEN g.goods_sn='MOCK_NUTRITION_MILK' THEN 'ml' WHEN g.goods_sn='MOCK_NUTRITION_EGG' THEN '枚' ELSE 'g' END,
       1.000000,100,0,'normal',@now,@now
FROM `fa_shop_ingredient` i
JOIN `fa_shop_goods` g ON g.goods_sn=CONCAT('MOCK_NUTRITION_',SUBSTRING(i.code,17))
JOIN `fa_shop_goods_sku` s ON s.goods_id=g.id AND s.sku_id='DEFAULT'
WHERE i.code LIKE 'MOCK_INGREDIENT_%'
ON DUPLICATE KEY UPDATE `content_quantity`=VALUES(`content_quantity`),`content_unit`=VALUES(`content_unit`),`conversion_rate`=VALUES(`conversion_rate`),`priority`=VALUES(`priority`),`is_substitute`=0,`status`='normal',`updatetime`=@now;

INSERT INTO `fa_shop_goods_substitute`
(`goods_id`,`goods_sku_id`,`substitute_goods_id`,`substitute_goods_sku_id`,`priority`,`status`,`createtime`,`updatetime`)
SELECT oat.id,oatSku.id,tofu.id,tofuSku.id,50,'normal',@now,@now
FROM `fa_shop_goods` oat JOIN `fa_shop_goods_sku` oatSku ON oatSku.goods_id=oat.id AND oatSku.sku_id='DEFAULT'
JOIN `fa_shop_goods` tofu ON tofu.goods_sn='MOCK_NUTRITION_TOFU' JOIN `fa_shop_goods_sku` tofuSku ON tofuSku.goods_id=tofu.id AND tofuSku.sku_id='DEFAULT'
WHERE oat.goods_sn='MOCK_NUTRITION_OAT'
ON DUPLICATE KEY UPDATE `priority`=VALUES(`priority`),`status`='normal',`updatetime`=@now;

INSERT INTO `fa_shop_supplier`
(`code`,`name`,`company_name`,`contact_name`,`contact_mobile`,`fulfillment_mode`,`settlement_mode`,`api_type`,`priority`,`status`,`createtime`,`updatetime`)
VALUES
('MOCK_SUPPLIER_FRESH','演示-鲜食直供商','MOCK 演示鲜食供应商','演示联系人','13800001001','SUPPLIER_DIRECT','MONTHLY','MANUAL',100,'normal',@now,@now),
('MOCK_SUPPLIER_PANTRY','演示-家庭营养仓','MOCK 演示营养供应商','演示联系人','13800001002','PLATFORM_WAREHOUSE','MONTHLY','MANUAL',90,'normal',@now,@now)
ON DUPLICATE KEY UPDATE `name`=VALUES(`name`),`fulfillment_mode`=VALUES(`fulfillment_mode`),`priority`=VALUES(`priority`),`status`='normal',`updatetime`=@now;

SET @fresh_supplier=(SELECT id FROM `fa_shop_supplier` WHERE code='MOCK_SUPPLIER_FRESH');
SET @pantry_supplier=(SELECT id FROM `fa_shop_supplier` WHERE code='MOCK_SUPPLIER_PANTRY');
INSERT INTO `fa_shop_warehouse`
(`code`,`name`,`owner_type`,`owner_id`,`warehouse_type`,`address`,`contact_name`,`contact_mobile`,`status`,`createtime`,`updatetime`)
VALUES
('MOCK_WH_FRESH','演示-鲜食直发仓','SUPPLIER',@fresh_supplier,'VIRTUAL_DIRECT','MOCK 演示地址','演示联系人','13800001001','normal',@now,@now),
('MOCK_WH_PANTRY','演示-家庭营养仓','SUPPLIER',@pantry_supplier,'PHYSICAL','MOCK 演示地址','演示联系人','13800001002','normal',@now,@now)
ON DUPLICATE KEY UPDATE `owner_id`=VALUES(`owner_id`),`name`=VALUES(`name`),`status`='normal',`updatetime`=@now;

INSERT INTO `fa_shop_supplier_sku`
(`supplier_id`,`goods_id`,`goods_sku_id`,`supplier_goods_code`,`supplier_sku_code`,`supply_price`,`min_order_qty`,`delivery_days`,`fulfillment_mode`,`priority`,`last_sync_time`,`sync_status`,`status`,`createtime`,`updatetime`)
SELECT @fresh_supplier,g.id,s.id,CONCAT('MOCK-F-G-',g.id),CONCAT('MOCK-F-S-',s.id),ROUND(g.price*0.58,2),1,1,'SUPPLIER_DIRECT',100,@now,'SUCCESS','normal',@now,@now
FROM `fa_shop_goods` g JOIN `fa_shop_goods_sku` s ON s.goods_id=g.id AND s.sku_id='DEFAULT' WHERE g.goods_sn LIKE 'MOCK_NUTRITION_%'
ON DUPLICATE KEY UPDATE `supply_price`=VALUES(`supply_price`),`delivery_days`=1,`priority`=100,`status`='normal',`last_sync_time`=@now,`sync_status`='SUCCESS',`updatetime`=@now;
INSERT INTO `fa_shop_supplier_sku`
(`supplier_id`,`goods_id`,`goods_sku_id`,`supplier_goods_code`,`supplier_sku_code`,`supply_price`,`min_order_qty`,`delivery_days`,`fulfillment_mode`,`priority`,`last_sync_time`,`sync_status`,`status`,`createtime`,`updatetime`)
SELECT @pantry_supplier,g.id,s.id,CONCAT('MOCK-P-G-',g.id),CONCAT('MOCK-P-S-',s.id),ROUND(g.price*0.54,2),1,2,'PLATFORM_WAREHOUSE',90,@now,'SUCCESS','normal',@now,@now
FROM `fa_shop_goods` g JOIN `fa_shop_goods_sku` s ON s.goods_id=g.id AND s.sku_id='DEFAULT' WHERE g.goods_sn LIKE 'MOCK_NUTRITION_%'
ON DUPLICATE KEY UPDATE `supply_price`=VALUES(`supply_price`),`delivery_days`=2,`priority`=90,`status`='normal',`last_sync_time`=@now,`sync_status`='SUCCESS',`updatetime`=@now;

SET @fresh_warehouse=(SELECT id FROM `fa_shop_warehouse` WHERE code='MOCK_WH_FRESH');
SET @pantry_warehouse=(SELECT id FROM `fa_shop_warehouse` WHERE code='MOCK_WH_PANTRY');
INSERT INTO `fa_shop_warehouse_sku`
(`warehouse_id`,`supplier_id`,`supplier_sku_id`,`goods_id`,`goods_sku_id`,`on_hand_qty`,`locked_qty`,`unavailable_qty`,`in_transit_qty`,`version`,`last_sync_time`,`createtime`,`updatetime`)
SELECT @fresh_warehouse,@fresh_supplier,ss.id,g.id,s.id,
       CASE WHEN g.goods_sn='MOCK_NUTRITION_BANANA' THEN 8 ELSE 80 END,0,0,0,0,@now,@now,@now
FROM `fa_shop_goods` g JOIN `fa_shop_goods_sku` s ON s.goods_id=g.id AND s.sku_id='DEFAULT'
JOIN `fa_shop_supplier_sku` ss ON ss.supplier_id=@fresh_supplier AND ss.goods_id=g.id AND ss.goods_sku_id=s.id
WHERE g.goods_sn LIKE 'MOCK_NUTRITION_%'
ON DUPLICATE KEY UPDATE `supplier_sku_id`=VALUES(`supplier_sku_id`),`on_hand_qty`=VALUES(`on_hand_qty`),`locked_qty`=0,`unavailable_qty`=0,`in_transit_qty`=0,`last_sync_time`=@now,`updatetime`=@now;
INSERT INTO `fa_shop_warehouse_sku`
(`warehouse_id`,`supplier_id`,`supplier_sku_id`,`goods_id`,`goods_sku_id`,`on_hand_qty`,`locked_qty`,`unavailable_qty`,`in_transit_qty`,`version`,`last_sync_time`,`createtime`,`updatetime`)
SELECT @pantry_warehouse,@pantry_supplier,ss.id,g.id,s.id,120,0,0,0,0,@now,@now,@now
FROM `fa_shop_goods` g JOIN `fa_shop_goods_sku` s ON s.goods_id=g.id AND s.sku_id='DEFAULT'
JOIN `fa_shop_supplier_sku` ss ON ss.supplier_id=@pantry_supplier AND ss.goods_id=g.id AND ss.goods_sku_id=s.id
WHERE g.goods_sn LIKE 'MOCK_NUTRITION_%'
ON DUPLICATE KEY UPDATE `supplier_sku_id`=VALUES(`supplier_sku_id`),`on_hand_qty`=VALUES(`on_hand_qty`),`locked_qty`=0,`unavailable_qty`=0,`in_transit_qty`=0,`last_sync_time`=@now,`updatetime`=@now;

INSERT INTO `fa_shop_supplier_delivery_region`
(`supplier_id`,`province_id`,`city_id`,`area_id`,`shipping_fee`,`free_shipping_amount`,`delivery_days`,`status`,`createtime`,`updatetime`)
VALUES (@fresh_supplier,0,0,0,6.00,99.00,1,'normal',@now,@now),(@pantry_supplier,0,0,0,0.00,59.00,2,'normal',@now,@now)
ON DUPLICATE KEY UPDATE `shipping_fee`=VALUES(`shipping_fee`),`free_shipping_amount`=VALUES(`free_shipping_amount`),`delivery_days`=VALUES(`delivery_days`),`status`='normal',`updatetime`=@now;

INSERT INTO `fa_shop_stock_batch`
(`warehouse_sku_id`,`batch_no`,`production_date`,`expiry_date`,`cost_price`,`on_hand_qty`,`locked_qty`,`unavailable_qty`,`status`,`createtime`,`updatetime`)
SELECT ws.id,CONCAT('MOCK-BATCH-',ws.id),CURDATE()-INTERVAL 3 DAY,
       CASE WHEN g.goods_sn='MOCK_NUTRITION_TOFU' THEN CURDATE()+INTERVAL 4 DAY WHEN g.goods_sn='MOCK_NUTRITION_BANANA' THEN CURDATE()+INTERVAL 5 DAY ELSE CURDATE()+INTERVAL 120 DAY END,
       ss.supply_price,ws.on_hand_qty,0,0,'normal',@now,@now
FROM `fa_shop_warehouse_sku` ws JOIN `fa_shop_goods` g ON g.id=ws.goods_id JOIN `fa_shop_supplier_sku` ss ON ss.id=ws.supplier_sku_id
WHERE ws.warehouse_id IN (@fresh_warehouse,@pantry_warehouse) AND g.goods_sn LIKE 'MOCK_NUTRITION_%'
ON DUPLICATE KEY UPDATE `production_date`=VALUES(`production_date`),`expiry_date`=VALUES(`expiry_date`),`cost_price`=VALUES(`cost_price`),`on_hand_qty`=VALUES(`on_hand_qty`),`locked_qty`=0,`unavailable_qty`=0,`status`='normal',`updatetime`=@now;

INSERT INTO `fa_shop_stock_flow`
(`flow_sn`,`warehouse_sku_id`,`supplier_id`,`warehouse_id`,`goods_id`,`goods_sku_id`,`biz_type`,`biz_no`,`change_on_hand`,`change_locked`,`before_on_hand`,`after_on_hand`,`before_locked`,`after_locked`,`operator_type`,`operator_id`,`remark`,`createtime`)
SELECT CONCAT('MOCK-INITIAL-',ws.id),ws.id,ws.supplier_id,ws.warehouse_id,ws.goods_id,ws.goods_sku_id,'INITIAL_IN','MOCK_CATALOG_20260924',ws.on_hand_qty,0,0,ws.on_hand_qty,0,0,'MIGRATION',0,'MOCK 演示期初库存',@now
FROM `fa_shop_warehouse_sku` ws JOIN `fa_shop_goods` g ON g.id=ws.goods_id
WHERE g.goods_sn LIKE 'MOCK_NUTRITION_%' AND ws.warehouse_id IN (@fresh_warehouse,@pantry_warehouse)
ON DUPLICATE KEY UPDATE `after_on_hand`=VALUES(`after_on_hand`),`remark`=VALUES(`remark`),`createtime`=@now;

SET @mock_user=COALESCE((SELECT id FROM `fa_user` ORDER BY id LIMIT 1),0);
INSERT INTO `fa_shop_shopping_list`
(`list_sn`,`user_id`,`menu_version_id`,`list_version`,`source_hash`,`status`,`confirmed_at`,`createtime`,`updatetime`)
VALUES ('MOCK_LIST_WEEKLY_NUTRITION',@mock_user,'MOCK_MENU_WEEK_01',1,SHA2('MOCK_MENU_WEEK_01',256),'CONFIRMED',@now,@now,@now)
ON DUPLICATE KEY UPDATE `status`='CONFIRMED',`confirmed_at`=@now,`updatetime`=@now;
SET @mock_list=(SELECT id FROM `fa_shop_shopping_list` WHERE list_sn='MOCK_LIST_WEEKLY_NUTRITION');
INSERT INTO `fa_shop_shopping_list_item`
(`shopping_list_id`,`ingredient_id`,`required_quantity`,`home_quantity`,`net_quantity`,`unit`,`source_refs_json`,`constraint_result_json`,`selected_goods_id`,`selected_goods_sku_id`,`selected_supplier_id`,`purchase_quantity`,`covered_quantity`,`shortage_quantity`,`excess_quantity`,`purchase_mode`,`substitution_confirmed`,`createtime`,`updatetime`)
SELECT @mock_list,i.id,
       CASE i.code WHEN 'MOCK_INGREDIENT_OAT' THEN 500 WHEN 'MOCK_INGREDIENT_MILK' THEN 3000 WHEN 'MOCK_INGREDIENT_EGG' THEN 10 WHEN 'MOCK_INGREDIENT_TOFU' THEN 400 ELSE 1000 END,
       0,
       CASE i.code WHEN 'MOCK_INGREDIENT_OAT' THEN 500 WHEN 'MOCK_INGREDIENT_MILK' THEN 3000 WHEN 'MOCK_INGREDIENT_EGG' THEN 10 WHEN 'MOCK_INGREDIENT_TOFU' THEN 400 ELSE 1000 END,
       i.default_unit,JSON_ARRAY('MOCK_MENU_WEEK_01'),JSON_OBJECT('mock',true,'status','matched'),g.id,s.id,@fresh_supplier,1,
       CASE i.code WHEN 'MOCK_INGREDIENT_OAT' THEN 500 WHEN 'MOCK_INGREDIENT_MILK' THEN 3000 WHEN 'MOCK_INGREDIENT_EGG' THEN 10 WHEN 'MOCK_INGREDIENT_TOFU' THEN 400 ELSE 1000 END,
       0,0,'PLATFORM',0,@now,@now
FROM `fa_shop_ingredient` i JOIN `fa_shop_goods` g ON g.goods_sn=CONCAT('MOCK_NUTRITION_',SUBSTRING(i.code,17))
JOIN `fa_shop_goods_sku` s ON s.goods_id=g.id AND s.sku_id='DEFAULT'
WHERE i.code LIKE 'MOCK_INGREDIENT_%'
  AND NOT EXISTS (SELECT 1 FROM `fa_shop_shopping_list_item` li WHERE li.shopping_list_id=@mock_list AND li.ingredient_id=i.id);

INSERT INTO `fa_shop_schema_migration` (`version`,`description`,`applied_at`)
VALUES ('20260924_012','MOCK 营养商品、食材、双供应商、库存和购物清单演示数据',@now)
ON DUPLICATE KEY UPDATE `description`=VALUES(`description`),`applied_at`=VALUES(`applied_at`);

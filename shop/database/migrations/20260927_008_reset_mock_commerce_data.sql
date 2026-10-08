SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS=0;
SET @now = UNIX_TIMESTAMP();

-- Remove transaction and fulfillment data before deleting product masters.
DELETE FROM fa_shop_refund_transaction;
DELETE FROM fa_shop_payment_transaction;
DELETE FROM fa_shop_aftersales_inspection;
DELETE FROM fa_shop_aftersales_ext;
DELETE FROM fa_shop_order_substitution;
DELETE FROM fa_shop_stock_reservation_adjustment;
DELETE FROM fa_shop_stock_reservation;
DELETE FROM fa_shop_order_shipment_item;
DELETE FROM fa_shop_order_shipment;
DELETE FROM fa_shop_order_status_log;
DELETE FROM fa_shop_order_goods_ext;
DELETE FROM fa_shop_order_supplier;
DELETE FROM fa_shop_order_snapshot;
DELETE FROM fa_shop_order_ext;
DELETE FROM fa_shop_order_aftersales;
DELETE FROM fa_shop_order_electronics;
DELETE FROM fa_shop_order_action;
DELETE FROM fa_shop_subscribe_log;
DELETE FROM fa_shop_order_goods;
DELETE FROM fa_shop_order;
DELETE FROM fa_shop_supplier_reconciliation;

DELETE FROM fa_shop_cart_ext;
DELETE FROM fa_shop_carts;
DELETE FROM fa_shop_shopping_list_item;
DELETE FROM fa_shop_shopping_list;
DELETE FROM fa_shop_collect;
DELETE FROM fa_shop_comment;

DELETE FROM fa_shop_stock_batch;
DELETE FROM fa_shop_stock_flow;
DELETE FROM fa_shop_warehouse_sku;
DELETE FROM fa_shop_supplier_sku;
DELETE FROM fa_shop_goods_substitute;
DELETE FROM fa_shop_ingredient_product_map;
DELETE FROM fa_shop_goods_sku_spec;
DELETE FROM fa_shop_sku_ext;
DELETE FROM fa_shop_goods_attr;
DELETE FROM fa_shop_goods_ext;
DELETE FROM fa_shop_goods_sku;
DELETE FROM fa_shop_goods;

ALTER TABLE fa_shop_order AUTO_INCREMENT=1;
ALTER TABLE fa_shop_order_goods AUTO_INCREMENT=1;
ALTER TABLE fa_shop_goods AUTO_INCREMENT=1;
ALTER TABLE fa_shop_goods_sku AUTO_INCREMENT=1;
ALTER TABLE fa_shop_supplier_sku AUTO_INCREMENT=1;
ALTER TABLE fa_shop_warehouse_sku AUTO_INCREMENT=1;
ALTER TABLE fa_shop_stock_batch AUTO_INCREMENT=1;
ALTER TABLE fa_shop_stock_flow AUTO_INCREMENT=1;
ALTER TABLE fa_shop_shopping_list AUTO_INCREMENT=1;
ALTER TABLE fa_shop_shopping_list_item AUTO_INCREMENT=1;

-- Rebuild a small coherent nutrition catalog.
INSERT INTO fa_shop_goods
(`category_id`,`goods_sn`,`title`,`subtitle`,`keywords`,`description`,`marketprice`,`price`,`stocks`,`sales`,`spectype`,`weight`,`isvirtual`,`weigh`,`createtime`,`updatetime`,`status`) VALUES
(21,'MOCK_NUTRITION_OAT','演示-即食燕麦片 500g','MOCK 演示营养食材','燕麦,全谷物,演示','用于商城供应链流程演示的模拟商品',29.90,24.90,120,0,1,0,0,100,@now,@now,'normal'),
(31,'MOCK_NUTRITION_MILK','演示-高钙纯牛奶 250ml x 12','MOCK 演示营养食材','牛奶,高钙,演示','用于商城供应链流程演示的模拟商品',79.90,69.90,100,0,1,0,0,99,@now,@now,'normal'),
(13,'MOCK_NUTRITION_EGG','演示-谷物鲜鸡蛋 10枚','MOCK 演示营养食材','鸡蛋,蛋白质,演示','用于商城供应链流程演示的模拟商品',22.90,19.90,80,0,1,0,0,98,@now,@now,'normal'),
(32,'MOCK_NUTRITION_TOFU','演示-有机北豆腐 400g','MOCK 演示营养食材','豆腐,植物蛋白,演示','用于商城供应链流程演示的模拟商品',12.90,9.90,60,0,1,0,0,97,@now,@now,'normal'),
(14,'MOCK_NUTRITION_BANANA','演示-香蕉 1kg','MOCK 演示营养食材','香蕉,水果,演示','用于商城供应链流程演示的模拟商品',18.90,15.90,40,0,1,0,0,96,@now,@now,'normal');

INSERT INTO fa_shop_goods_sku
(`goods_id`,`goods_sn`,`sku_id`,`image`,`price`,`marketprice`,`stocks`,`sales`,`weigh`,`createtime`,`updatetime`)
SELECT id,goods_sn,'DEFAULT','',price,marketprice,stocks,0,weigh,@now,@now
FROM fa_shop_goods;

INSERT INTO fa_shop_goods_ext
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
       JSON_ARRAY('家庭营养','MOCK'),'MOCK 演示产地',
       CASE WHEN g.goods_sn IN ('MOCK_NUTRITION_MILK','MOCK_NUTRITION_TOFU') THEN '冷藏 2-6℃' ELSE '阴凉干燥处' END,
       CASE WHEN g.goods_sn='MOCK_NUTRITION_TOFU' THEN 7 WHEN g.goods_sn='MOCK_NUTRITION_BANANA' THEN 10 ELSE 180 END,
       'ALL',@now,@now
FROM fa_shop_goods g;

INSERT INTO fa_shop_sku_ext
(`goods_id`,`goods_sku_id`,`barcode`,`unit`,`net_quantity`,`net_unit`,`reference_cost_price`,`safety_stock`,`batch_enabled`,`expiry_enabled`,`createtime`,`updatetime`)
SELECT g.id,s.id,CONCAT('MOCK-BARCODE-',g.id),'件',
       CASE g.goods_sn WHEN 'MOCK_NUTRITION_OAT' THEN 500 WHEN 'MOCK_NUTRITION_MILK' THEN 3000 WHEN 'MOCK_NUTRITION_EGG' THEN 10 WHEN 'MOCK_NUTRITION_TOFU' THEN 400 ELSE 1000 END,
       CASE WHEN g.goods_sn='MOCK_NUTRITION_EGG' THEN '枚' ELSE 'g' END,
       ROUND(g.price*0.62,2),CASE WHEN g.goods_sn='MOCK_NUTRITION_BANANA' THEN 20 ELSE 30 END,1,1,@now,@now
FROM fa_shop_goods g JOIN fa_shop_goods_sku s ON s.goods_id=g.id;

INSERT INTO fa_shop_ingredient_product_map
(`ingredient_id`,`goods_id`,`goods_sku_id`,`content_quantity`,`content_unit`,`conversion_rate`,`priority`,`is_substitute`,`status`,`createtime`,`updatetime`)
SELECT i.id,g.id,s.id,
       CASE g.goods_sn WHEN 'MOCK_NUTRITION_OAT' THEN 500 WHEN 'MOCK_NUTRITION_MILK' THEN 3000 WHEN 'MOCK_NUTRITION_EGG' THEN 10 WHEN 'MOCK_NUTRITION_TOFU' THEN 400 ELSE 1000 END,
       CASE WHEN g.goods_sn='MOCK_NUTRITION_MILK' THEN 'ml' WHEN g.goods_sn='MOCK_NUTRITION_EGG' THEN '枚' ELSE 'g' END,
       1.000000,100,0,'normal',@now,@now
FROM fa_shop_ingredient i
JOIN fa_shop_goods g ON g.goods_sn=CONCAT('MOCK_NUTRITION_',SUBSTRING(i.code,17))
JOIN fa_shop_goods_sku s ON s.goods_id=g.id
WHERE i.code LIKE 'MOCK_INGREDIENT_%';

INSERT INTO fa_shop_goods_substitute
(`goods_id`,`goods_sku_id`,`substitute_goods_id`,`substitute_goods_sku_id`,`priority`,`status`,`createtime`,`updatetime`)
SELECT oat.id,oat_sku.id,tofu.id,tofu_sku.id,50,'normal',@now,@now
FROM fa_shop_goods oat
JOIN fa_shop_goods_sku oat_sku ON oat_sku.goods_id=oat.id
JOIN fa_shop_goods tofu ON tofu.goods_sn='MOCK_NUTRITION_TOFU'
JOIN fa_shop_goods_sku tofu_sku ON tofu_sku.goods_id=tofu.id
WHERE oat.goods_sn='MOCK_NUTRITION_OAT';

SET @fresh_supplier=(SELECT id FROM fa_shop_supplier WHERE code='MOCK_SUPPLIER_FRESH' LIMIT 1);
SET @pantry_supplier=(SELECT id FROM fa_shop_supplier WHERE code='MOCK_SUPPLIER_PANTRY' LIMIT 1);
SET @fresh_warehouse=(SELECT id FROM fa_shop_warehouse WHERE code='MOCK_WH_FRESH' LIMIT 1);
SET @pantry_warehouse=(SELECT id FROM fa_shop_warehouse WHERE code='MOCK_WH_PANTRY' LIMIT 1);

INSERT INTO fa_shop_supplier_sku
(`supplier_id`,`goods_id`,`goods_sku_id`,`supplier_goods_code`,`supplier_sku_code`,`supply_price`,`min_order_qty`,`delivery_days`,`fulfillment_mode`,`priority`,`last_sync_time`,`sync_status`,`status`,`createtime`,`updatetime`)
SELECT @fresh_supplier,g.id,s.id,CONCAT('MOCK-F-G-',g.id),CONCAT('MOCK-F-S-',s.id),ROUND(g.price*0.58,2),1,1,'SUPPLIER_DIRECT',100,@now,'SUCCESS','normal',@now,@now
FROM fa_shop_goods g JOIN fa_shop_goods_sku s ON s.goods_id=g.id;

INSERT INTO fa_shop_supplier_sku
(`supplier_id`,`goods_id`,`goods_sku_id`,`supplier_goods_code`,`supplier_sku_code`,`supply_price`,`min_order_qty`,`delivery_days`,`fulfillment_mode`,`priority`,`last_sync_time`,`sync_status`,`status`,`createtime`,`updatetime`)
SELECT @pantry_supplier,g.id,s.id,CONCAT('MOCK-P-G-',g.id),CONCAT('MOCK-P-S-',s.id),ROUND(g.price*0.54,2),1,2,'PLATFORM_WAREHOUSE',90,@now,'SUCCESS','normal',@now,@now
FROM fa_shop_goods g JOIN fa_shop_goods_sku s ON s.goods_id=g.id;

INSERT INTO fa_shop_warehouse_sku
(`warehouse_id`,`supplier_id`,`supplier_sku_id`,`goods_id`,`goods_sku_id`,`on_hand_qty`,`locked_qty`,`unavailable_qty`,`in_transit_qty`,`version`,`last_sync_time`,`createtime`,`updatetime`)
SELECT @fresh_warehouse,@fresh_supplier,ss.id,g.id,s.id,
       CASE WHEN g.goods_sn='MOCK_NUTRITION_BANANA' THEN 40 ELSE 80 END,0,0,0,0,@now,@now,@now
FROM fa_shop_goods g
JOIN fa_shop_goods_sku s ON s.goods_id=g.id
JOIN fa_shop_supplier_sku ss ON ss.supplier_id=@fresh_supplier AND ss.goods_id=g.id AND ss.goods_sku_id=s.id;

INSERT INTO fa_shop_warehouse_sku
(`warehouse_id`,`supplier_id`,`supplier_sku_id`,`goods_id`,`goods_sku_id`,`on_hand_qty`,`locked_qty`,`unavailable_qty`,`in_transit_qty`,`version`,`last_sync_time`,`createtime`,`updatetime`)
SELECT @pantry_warehouse,@pantry_supplier,ss.id,g.id,s.id,120,0,0,0,0,@now,@now,@now
FROM fa_shop_goods g
JOIN fa_shop_goods_sku s ON s.goods_id=g.id
JOIN fa_shop_supplier_sku ss ON ss.supplier_id=@pantry_supplier AND ss.goods_id=g.id AND ss.goods_sku_id=s.id;

INSERT INTO fa_shop_stock_batch
(`warehouse_sku_id`,`batch_no`,`production_date`,`expiry_date`,`cost_price`,`on_hand_qty`,`locked_qty`,`unavailable_qty`,`status`,`createtime`,`updatetime`)
SELECT ws.id,CONCAT('MOCK-BATCH-',ws.id),CURDATE()-INTERVAL 3 DAY,
       CASE WHEN g.goods_sn='MOCK_NUTRITION_TOFU' THEN CURDATE()+INTERVAL 4 DAY WHEN g.goods_sn='MOCK_NUTRITION_BANANA' THEN CURDATE()+INTERVAL 5 DAY ELSE CURDATE()+INTERVAL 120 DAY END,
       ss.supply_price,ws.on_hand_qty,0,0,'normal',@now,@now
FROM fa_shop_warehouse_sku ws
JOIN fa_shop_goods g ON g.id=ws.goods_id
JOIN fa_shop_supplier_sku ss ON ss.id=ws.supplier_sku_id;

INSERT INTO fa_shop_stock_flow
(`flow_sn`,`warehouse_sku_id`,`supplier_id`,`warehouse_id`,`goods_id`,`goods_sku_id`,`biz_type`,`biz_no`,`change_on_hand`,`change_locked`,`before_on_hand`,`after_on_hand`,`before_locked`,`after_locked`,`operator_type`,`operator_id`,`remark`,`createtime`)
SELECT CONCAT('MOCK-INITIAL-',ws.id),ws.id,ws.supplier_id,ws.warehouse_id,ws.goods_id,ws.goods_sku_id,'INITIAL_IN','MOCK_CATALOG_RESET',ws.on_hand_qty,0,0,ws.on_hand_qty,0,0,'MIGRATION',0,'MOCK 演示期初库存',@now
FROM fa_shop_warehouse_sku ws;

SET @mock_user=COALESCE((SELECT id FROM fa_user ORDER BY id LIMIT 1),0);
INSERT INTO fa_shop_shopping_list
(`list_sn`,`user_id`,`menu_version_id`,`list_version`,`source_hash`,`status`,`confirmed_at`,`createtime`,`updatetime`)
VALUES ('MOCK_LIST_WEEKLY_NUTRITION',@mock_user,'MOCK_MENU_WEEK_01',1,SHA2('MOCK_MENU_WEEK_01',256),'CONFIRMED',@now,@now,@now);
SET @mock_list=LAST_INSERT_ID();

INSERT INTO fa_shop_shopping_list_item
(`shopping_list_id`,`ingredient_id`,`required_quantity`,`home_quantity`,`net_quantity`,`unit`,`source_refs_json`,`constraint_result_json`,`selected_goods_id`,`selected_goods_sku_id`,`selected_supplier_id`,`purchase_quantity`,`covered_quantity`,`shortage_quantity`,`excess_quantity`,`purchase_mode`,`substitution_confirmed`,`createtime`,`updatetime`)
SELECT @mock_list,i.id,
       CASE i.code WHEN 'MOCK_INGREDIENT_OAT' THEN 500 WHEN 'MOCK_INGREDIENT_MILK' THEN 3000 WHEN 'MOCK_INGREDIENT_EGG' THEN 10 WHEN 'MOCK_INGREDIENT_TOFU' THEN 400 ELSE 1000 END,
       0,
       CASE i.code WHEN 'MOCK_INGREDIENT_OAT' THEN 500 WHEN 'MOCK_INGREDIENT_MILK' THEN 3000 WHEN 'MOCK_INGREDIENT_EGG' THEN 10 WHEN 'MOCK_INGREDIENT_TOFU' THEN 400 ELSE 1000 END,
       i.default_unit,JSON_ARRAY('MOCK_MENU_WEEK_01'),JSON_OBJECT('mock',true,'status','matched'),g.id,s.id,@fresh_supplier,1,
       CASE i.code WHEN 'MOCK_INGREDIENT_OAT' THEN 500 WHEN 'MOCK_INGREDIENT_MILK' THEN 3000 WHEN 'MOCK_INGREDIENT_EGG' THEN 10 WHEN 'MOCK_INGREDIENT_TOFU' THEN 400 ELSE 1000 END,
       0,0,'PLATFORM',0,@now,@now
FROM fa_shop_ingredient i
JOIN fa_shop_goods g ON g.goods_sn=CONCAT('MOCK_NUTRITION_',SUBSTRING(i.code,17))
JOIN fa_shop_goods_sku s ON s.goods_id=g.id
WHERE i.code LIKE 'MOCK_INGREDIENT_%';

SET FOREIGN_KEY_CHECKS=1;

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260927_008','清空商品 SKU 订单库存并重建营养商城 MOCK 数据',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

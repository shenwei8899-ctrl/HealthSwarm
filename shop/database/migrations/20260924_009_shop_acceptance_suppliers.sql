SET NAMES utf8mb4;
SET @now = UNIX_TIMESTAMP();

INSERT INTO `fa_shop_supplier` (`code`,`name`,`company_name`,`contact_name`,`contact_mobile`,`fulfillment_mode`,`settlement_mode`,`api_type`,`priority`,`status`,`createtime`,`updatetime`)
VALUES
('ACCEPTANCE_SUPPLIER_A','本地验收供应商A','本地验收数据-供应商A','','','SUPPLIER_DIRECT','MONTHLY','MANUAL',100,'normal',@now,@now),
('ACCEPTANCE_SUPPLIER_B','本地验收供应商B','本地验收数据-供应商B','','','SUPPLIER_DIRECT','MONTHLY','MANUAL',90,'normal',@now,@now)
ON DUPLICATE KEY UPDATE `name`=VALUES(`name`),`priority`=VALUES(`priority`),`status`='normal',`updatetime`=@now;

SET @supplier_a = (SELECT `id` FROM `fa_shop_supplier` WHERE `code`='ACCEPTANCE_SUPPLIER_A');
SET @supplier_b = (SELECT `id` FROM `fa_shop_supplier` WHERE `code`='ACCEPTANCE_SUPPLIER_B');

INSERT INTO `fa_shop_warehouse` (`code`,`name`,`owner_type`,`owner_id`,`warehouse_type`,`status`,`createtime`,`updatetime`)
VALUES
('ACCEPTANCE_WH_A','本地验收供应商A直发仓','SUPPLIER',@supplier_a,'VIRTUAL_DIRECT','normal',@now,@now),
('ACCEPTANCE_WH_B','本地验收供应商B直发仓','SUPPLIER',@supplier_b,'VIRTUAL_DIRECT','normal',@now,@now)
ON DUPLICATE KEY UPDATE `owner_id`=VALUES(`owner_id`),`status`='normal',`updatetime`=@now;

SET @warehouse_a = (SELECT `id` FROM `fa_shop_warehouse` WHERE `code`='ACCEPTANCE_WH_A');
SET @warehouse_b = (SELECT `id` FROM `fa_shop_warehouse` WHERE `code`='ACCEPTANCE_WH_B');
SET @goods_id = (SELECT `id` FROM `fa_shop_goods` WHERE `status`='normal' ORDER BY `id` LIMIT 1);
SET @sku_id = COALESCE((SELECT `id` FROM `fa_shop_goods_sku` WHERE `goods_id`=@goods_id ORDER BY `id` LIMIT 1),0);

INSERT INTO `fa_shop_supplier_sku` (`supplier_id`,`goods_id`,`goods_sku_id`,`supplier_goods_code`,`supplier_sku_code`,`supply_price`,`min_order_qty`,`delivery_days`,`fulfillment_mode`,`priority`,`last_sync_time`,`sync_status`,`status`,`createtime`,`updatetime`)
SELECT @supplier_a,@goods_id,@sku_id,CONCAT('A-G-',@goods_id),CONCAT('A-S-',@sku_id),5.80,1,1,'SUPPLIER_DIRECT',100,@now,'SUCCESS','normal',@now,@now FROM DUAL WHERE @goods_id IS NOT NULL
ON DUPLICATE KEY UPDATE `supply_price`=VALUES(`supply_price`),`priority`=VALUES(`priority`),`status`='normal',`updatetime`=@now;
INSERT INTO `fa_shop_supplier_sku` (`supplier_id`,`goods_id`,`goods_sku_id`,`supplier_goods_code`,`supplier_sku_code`,`supply_price`,`min_order_qty`,`delivery_days`,`fulfillment_mode`,`priority`,`last_sync_time`,`sync_status`,`status`,`createtime`,`updatetime`)
SELECT @supplier_b,@goods_id,@sku_id,CONCAT('B-G-',@goods_id),CONCAT('B-S-',@sku_id),5.50,1,2,'SUPPLIER_DIRECT',90,@now,'SUCCESS','normal',@now,@now FROM DUAL WHERE @goods_id IS NOT NULL
ON DUPLICATE KEY UPDATE `supply_price`=VALUES(`supply_price`),`priority`=VALUES(`priority`),`status`='normal',`updatetime`=@now;

SET @supplier_sku_a = (SELECT `id` FROM `fa_shop_supplier_sku` WHERE `supplier_id`=@supplier_a AND `goods_id`=@goods_id AND `goods_sku_id`=@sku_id);
SET @supplier_sku_b = (SELECT `id` FROM `fa_shop_supplier_sku` WHERE `supplier_id`=@supplier_b AND `goods_id`=@goods_id AND `goods_sku_id`=@sku_id);

INSERT INTO `fa_shop_warehouse_sku` (`warehouse_id`,`supplier_id`,`supplier_sku_id`,`goods_id`,`goods_sku_id`,`on_hand_qty`,`locked_qty`,`unavailable_qty`,`in_transit_qty`,`version`,`last_sync_time`,`createtime`,`updatetime`)
SELECT @warehouse_a,@supplier_a,@supplier_sku_a,@goods_id,@sku_id,100,0,0,0,0,@now,@now,@now FROM DUAL WHERE @goods_id IS NOT NULL
ON DUPLICATE KEY UPDATE `supplier_id`=VALUES(`supplier_id`),`supplier_sku_id`=VALUES(`supplier_sku_id`),`last_sync_time`=@now,`updatetime`=@now;

SET @warehouse_sku_a = (SELECT `id` FROM `fa_shop_warehouse_sku` WHERE `warehouse_id`=@warehouse_a AND `goods_id`=@goods_id AND `goods_sku_id`=@sku_id);
SET @warehouse_sku_b = (SELECT `id` FROM `fa_shop_warehouse_sku` WHERE `warehouse_id`=@warehouse_b AND `goods_id`=@goods_id AND `goods_sku_id`=@sku_id);
INSERT IGNORE INTO `fa_shop_stock_flow` (`flow_sn`,`warehouse_sku_id`,`supplier_id`,`warehouse_id`,`goods_id`,`goods_sku_id`,`biz_type`,`biz_no`,`change_on_hand`,`change_locked`,`before_on_hand`,`after_on_hand`,`before_locked`,`after_locked`,`operator_type`,`operator_id`,`remark`,`createtime`)
SELECT CONCAT('ACCEPTANCE_INITIAL_A_',@warehouse_sku_a),@warehouse_sku_a,@supplier_a,@warehouse_a,@goods_id,@sku_id,'INITIAL_IN','ACCEPTANCE_SUPPLIER_A',100,0,0,100,0,0,'SYSTEM',0,'本地验收供应商A期初库存',@now FROM DUAL WHERE @warehouse_sku_a IS NOT NULL;
INSERT IGNORE INTO `fa_shop_stock_flow` (`flow_sn`,`warehouse_sku_id`,`supplier_id`,`warehouse_id`,`goods_id`,`goods_sku_id`,`biz_type`,`biz_no`,`change_on_hand`,`change_locked`,`before_on_hand`,`after_on_hand`,`before_locked`,`after_locked`,`operator_type`,`operator_id`,`remark`,`createtime`)
SELECT CONCAT('ACCEPTANCE_INITIAL_B_',@warehouse_sku_b),@warehouse_sku_b,@supplier_b,@warehouse_b,@goods_id,@sku_id,'INITIAL_IN','ACCEPTANCE_SUPPLIER_B',80,0,0,80,0,0,'SYSTEM',0,'本地验收供应商B期初库存',@now FROM DUAL WHERE @warehouse_sku_b IS NOT NULL;
INSERT INTO `fa_shop_warehouse_sku` (`warehouse_id`,`supplier_id`,`supplier_sku_id`,`goods_id`,`goods_sku_id`,`on_hand_qty`,`locked_qty`,`unavailable_qty`,`in_transit_qty`,`version`,`last_sync_time`,`createtime`,`updatetime`)
SELECT @warehouse_b,@supplier_b,@supplier_sku_b,@goods_id,@sku_id,80,0,0,0,0,@now,@now,@now FROM DUAL WHERE @goods_id IS NOT NULL
ON DUPLICATE KEY UPDATE `supplier_id`=VALUES(`supplier_id`),`supplier_sku_id`=VALUES(`supplier_sku_id`),`last_sync_time`=@now,`updatetime`=@now;

INSERT INTO `fa_shop_supplier_delivery_region` (`supplier_id`,`province_id`,`city_id`,`area_id`,`shipping_fee`,`free_shipping_amount`,`delivery_days`,`status`,`createtime`,`updatetime`)
VALUES
(@supplier_a,0,0,0,6.00,99.00,1,'normal',@now,@now),
(@supplier_b,0,0,0,4.00,79.00,2,'normal',@now,@now)
ON DUPLICATE KEY UPDATE `shipping_fee`=VALUES(`shipping_fee`),`free_shipping_amount`=VALUES(`free_shipping_amount`),`delivery_days`=VALUES(`delivery_days`),`status`='normal',`updatetime`=@now;

INSERT INTO `fa_shop_schema_migration` (`version`,`description`,`applied_at`)
VALUES ('20260924_009','两家本地验收供应商及同SKU多供应商数据',@now)
ON DUPLICATE KEY UPDATE `description`=VALUES(`description`);

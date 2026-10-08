SET NAMES utf8mb4;
SET @now = UNIX_TIMESTAMP();

INSERT INTO `fa_auth_group` (`pid`,`name`,`rules`,`createtime`,`updatetime`,`status`)
SELECT 1,'商城运营','',@now,@now,'normal' FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM `fa_auth_group` WHERE `name`='商城运营');
INSERT INTO `fa_auth_group` (`pid`,`name`,`rules`,`createtime`,`updatetime`,`status`)
SELECT 1,'订单客服','',@now,@now,'normal' FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM `fa_auth_group` WHERE `name`='订单客服');
INSERT INTO `fa_auth_group` (`pid`,`name`,`rules`,`createtime`,`updatetime`,`status`)
SELECT 1,'供应商运营','',@now,@now,'normal' FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM `fa_auth_group` WHERE `name`='供应商运营');
INSERT INTO `fa_auth_group` (`pid`,`name`,`rules`,`createtime`,`updatetime`,`status`)
SELECT 1,'仓库人员','',@now,@now,'normal' FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM `fa_auth_group` WHERE `name`='仓库人员');
INSERT INTO `fa_auth_group` (`pid`,`name`,`rules`,`createtime`,`updatetime`,`status`)
SELECT 1,'财务人员','',@now,@now,'normal' FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM `fa_auth_group` WHERE `name`='财务人员');

UPDATE `fa_auth_group` SET `rules`=(SELECT GROUP_CONCAT(`id` ORDER BY `id`) FROM `fa_auth_rule` WHERE `name`='shop' OR `name` REGEXP '^shop/(goods|category|brand|attribute|spec|sku_template|ingredient|ingredient_product_map|supplier_sku)(/|$)'),`updatetime`=@now WHERE `name`='商城运营';
UPDATE `fa_auth_group` SET `rules`=(SELECT GROUP_CONCAT(`id` ORDER BY `id`) FROM `fa_auth_rule` WHERE `name`='shop' OR `name` REGEXP '^shop/(order|order_aftersales|order_supplier|order_shipment|refund_transaction)(/|$)'),`updatetime`=@now WHERE `name`='订单客服';
UPDATE `fa_auth_group` SET `rules`=(SELECT GROUP_CONCAT(`id` ORDER BY `id`) FROM `fa_auth_rule` WHERE `name`='shop' OR `name` REGEXP '^shop/(supplier|supplier_sku|supplier_delivery_region|supplier_sync_log|supplier_sync_job|order_supplier|order_shipment)(/|$)'),`updatetime`=@now WHERE `name`='供应商运营';
UPDATE `fa_auth_group` SET `rules`=(SELECT GROUP_CONCAT(`id` ORDER BY `id`) FROM `fa_auth_rule` WHERE `name`='shop' OR `name` REGEXP '^shop/(warehouse|warehouse_sku|stock_reservation|stock_flow|order_supplier|order_shipment)(/|$)'),`updatetime`=@now WHERE `name`='仓库人员';
UPDATE `fa_auth_group` SET `rules`=(SELECT GROUP_CONCAT(`id` ORDER BY `id`) FROM `fa_auth_rule` WHERE `name`='shop' OR `name` REGEXP '^shop/(order|order_aftersales|refund_transaction|supplier_sync_log)(/|$)'),`updatetime`=@now WHERE `name`='财务人员';

CREATE TABLE IF NOT EXISTS `fa_shop_admin_supplier_scope` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `admin_id` int unsigned NOT NULL,
  `supplier_id` int unsigned NOT NULL,
  `createtime` bigint unsigned NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_admin_supplier` (`admin_id`,`supplier_id`),
  KEY `idx_supplier` (`supplier_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='后台账号供应商数据范围';

INSERT INTO `fa_shop_schema_migration` (`version`,`description`,`applied_at`)
VALUES ('20260924_008','商城运营、客服、供应商、仓库和财务岗位权限',@now)
ON DUPLICATE KEY UPDATE `description`=VALUES(`description`);

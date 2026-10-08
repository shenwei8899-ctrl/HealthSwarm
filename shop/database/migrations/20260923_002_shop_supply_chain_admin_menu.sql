SET NAMES utf8mb4;

SET @now = UNIX_TIMESTAMP();
SET @shop_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop' LIMIT 1);

UPDATE `fa_auth_rule`
SET `title` = '商城供应链', `updatetime` = @now
WHERE `id` = @shop_pid;

UPDATE `fa_auth_rule`
SET `ismenu` = 1, `updatetime` = @now
WHERE `name` IN ('shop/spec', 'shop/sku_template', 'shop/attribute', 'shop/brand');

INSERT IGNORE INTO `fa_auth_rule`
(`type`,`pid`,`name`,`title`,`icon`,`url`,`condition`,`remark`,`ismenu`,`menutype`,`extend`,`py`,`pinyin`,`createtime`,`updatetime`,`weigh`,`status`)
VALUES
('file',@shop_pid,'shop/ingredient','标准食材库','fa fa-leaf','','','','1',NULL,'','','',@now,@now,65,'normal'),
('file',@shop_pid,'shop/ingredient_product_map','食材商品映射','fa fa-random','','','','1',NULL,'','','',@now,@now,64,'normal'),
('file',@shop_pid,'shop/supplier','供应商管理','fa fa-building','','','','1',NULL,'','','',@now,@now,63,'normal'),
('file',@shop_pid,'shop/supplier_sku','供应商商品','fa fa-cubes','','','','1',NULL,'','','',@now,@now,62,'normal'),
('file',@shop_pid,'shop/supplier_delivery_region','供应商配送区域','fa fa-map','','','','1',NULL,'','','',@now,@now,61,'normal'),
('file',@shop_pid,'shop/supplier_sync_log','供应商同步日志','fa fa-exchange','','','只读审计数据','1',NULL,'','','',@now,@now,60,'normal'),
('file',@shop_pid,'shop/warehouse','仓库管理','fa fa-home','','','','1',NULL,'','','',@now,@now,59,'normal'),
('file',@shop_pid,'shop/warehouse_sku','仓库库存','fa fa-cubes','','','只读库存视图','1',NULL,'','','',@now,@now,58,'normal'),
('file',@shop_pid,'shop/stock_reservation','库存锁定','fa fa-lock','','','只读审计数据','1',NULL,'','','',@now,@now,57,'normal'),
('file',@shop_pid,'shop/stock_flow','库存流水','fa fa-list-alt','','','只读审计数据','1',NULL,'','','',@now,@now,56,'normal'),
('file',@shop_pid,'shop/order_supplier','供应商履约子单','fa fa-sitemap','','','只读履约视图','1',NULL,'','','',@now,@now,55,'normal'),
('file',@shop_pid,'shop/order_shipment','物流包裹','fa fa-truck','','','只读履约视图','1',NULL,'','','',@now,@now,54,'normal');

SET @ingredient_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/ingredient' LIMIT 1);
INSERT IGNORE INTO `fa_auth_rule` (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@ingredient_pid,'shop/ingredient/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@ingredient_pid,'shop/ingredient/add','添加','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@ingredient_pid,'shop/ingredient/edit','编辑','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@ingredient_pid,'shop/ingredient/del','删除','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@ingredient_pid,'shop/ingredient/multi','批量更新','fa fa-circle-o',0,@now,@now,0,'normal');

SET @ingredient_map_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/ingredient_product_map' LIMIT 1);
INSERT IGNORE INTO `fa_auth_rule` (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@ingredient_map_pid,'shop/ingredient_product_map/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@ingredient_map_pid,'shop/ingredient_product_map/add','添加','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@ingredient_map_pid,'shop/ingredient_product_map/edit','编辑','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@ingredient_map_pid,'shop/ingredient_product_map/del','删除','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@ingredient_map_pid,'shop/ingredient_product_map/multi','批量更新','fa fa-circle-o',0,@now,@now,0,'normal');

SET @supplier_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/supplier' LIMIT 1);
INSERT IGNORE INTO `fa_auth_rule` (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@supplier_pid,'shop/supplier/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@supplier_pid,'shop/supplier/add','添加','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@supplier_pid,'shop/supplier/edit','编辑','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@supplier_pid,'shop/supplier/del','删除','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@supplier_pid,'shop/supplier/multi','批量更新','fa fa-circle-o',0,@now,@now,0,'normal');

SET @supplier_sku_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/supplier_sku' LIMIT 1);
INSERT IGNORE INTO `fa_auth_rule` (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@supplier_sku_pid,'shop/supplier_sku/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@supplier_sku_pid,'shop/supplier_sku/add','添加','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@supplier_sku_pid,'shop/supplier_sku/edit','编辑','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@supplier_sku_pid,'shop/supplier_sku/del','删除','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@supplier_sku_pid,'shop/supplier_sku/multi','批量更新','fa fa-circle-o',0,@now,@now,0,'normal');

SET @delivery_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/supplier_delivery_region' LIMIT 1);
INSERT IGNORE INTO `fa_auth_rule` (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@delivery_pid,'shop/supplier_delivery_region/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@delivery_pid,'shop/supplier_delivery_region/add','添加','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@delivery_pid,'shop/supplier_delivery_region/edit','编辑','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@delivery_pid,'shop/supplier_delivery_region/del','删除','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@delivery_pid,'shop/supplier_delivery_region/multi','批量更新','fa fa-circle-o',0,@now,@now,0,'normal');

SET @warehouse_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/warehouse' LIMIT 1);
INSERT IGNORE INTO `fa_auth_rule` (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@warehouse_pid,'shop/warehouse/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@warehouse_pid,'shop/warehouse/add','添加','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@warehouse_pid,'shop/warehouse/edit','编辑','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@warehouse_pid,'shop/warehouse/del','删除','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@warehouse_pid,'shop/warehouse/multi','批量更新','fa fa-circle-o',0,@now,@now,0,'normal');

SET @supplier_sync_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/supplier_sync_log' LIMIT 1);
SET @warehouse_sku_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/warehouse_sku' LIMIT 1);
SET @reservation_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/stock_reservation' LIMIT 1);
SET @stock_flow_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/stock_flow' LIMIT 1);
SET @order_supplier_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/order_supplier' LIMIT 1);
SET @shipment_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/order_shipment' LIMIT 1);

INSERT IGNORE INTO `fa_auth_rule` (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@supplier_sync_pid,'shop/supplier_sync_log/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@warehouse_sku_pid,'shop/warehouse_sku/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@reservation_pid,'shop/stock_reservation/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@stock_flow_pid,'shop/stock_flow/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@order_supplier_pid,'shop/order_supplier/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@shipment_pid,'shop/order_shipment/index','查看','fa fa-circle-o',0,@now,@now,0,'normal');

INSERT INTO `fa_shop_schema_migration` (`version`,`description`,`applied_at`)
VALUES ('20260923_002','商城多供应商、库存和履约管理后台菜单及权限',@now)
ON DUPLICATE KEY UPDATE `description`=VALUES(`description`);

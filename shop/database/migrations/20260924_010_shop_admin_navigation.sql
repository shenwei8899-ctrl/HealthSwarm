SET NAMES utf8mb4;
SET @now = UNIX_TIMESTAMP();
SET @shop_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop' LIMIT 1);

UPDATE `fa_auth_rule`
SET `title` = '商城管理', `updatetime` = @now
WHERE `id` = @shop_pid;

INSERT INTO `fa_auth_rule`
(`type`,`pid`,`name`,`title`,`icon`,`url`,`condition`,`remark`,`ismenu`,`menutype`,`extend`,`py`,`pinyin`,`createtime`,`updatetime`,`weigh`,`status`)
VALUES
('file',@shop_pid,'shop/product_center','商品中心','fa fa-cube','','','商品和食材资料管理',1,NULL,'','','',@now,@now,80,'normal'),
('file',@shop_pid,'shop/supplier_center','供应商中心','fa fa-building','','','供货关系与同步管理',1,NULL,'','','',@now,@now,79,'normal'),
('file',@shop_pid,'shop/inventory_center','库存中心','fa fa-archive','','','仓库、库存和预警管理',1,NULL,'','','',@now,@now,78,'normal'),
('file',@shop_pid,'shop/shopping_list_center','购物清单','fa fa-list-check','','','菜单食材购物清单管理',1,NULL,'','','',@now,@now,77,'normal'),
('file',@shop_pid,'shop/order_center','订单中心','fa fa-shopping-bag','','','用户订单与履约订单管理',1,NULL,'','','',@now,@now,76,'normal'),
('file',@shop_pid,'shop/delivery_center','配送中心','fa fa-truck','','','拣货、出库和物流管理',1,NULL,'','','',@now,@now,75,'normal'),
('file',@shop_pid,'shop/aftersale_center','售后中心','fa fa-undo','','','退款、退货和验收管理',1,NULL,'','','',@now,@now,74,'normal'),
('file',@shop_pid,'shop/report_center','报表中心','fa fa-line-chart','','','销售、履约和库存分析',1,NULL,'','','',@now,@now,73,'normal')
ON DUPLICATE KEY UPDATE `title`=VALUES(`title`),`icon`=VALUES(`icon`),`ismenu`=1,`status`='normal',`updatetime`=@now;

SET @product_center = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/product_center' LIMIT 1);
SET @supplier_center = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/supplier_center' LIMIT 1);
SET @inventory_center = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/inventory_center' LIMIT 1);
SET @shopping_list_center = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/shopping_list_center' LIMIT 1);
SET @order_center = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/order_center' LIMIT 1);
SET @delivery_center = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/delivery_center' LIMIT 1);
SET @aftersale_center = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/aftersale_center' LIMIT 1);
SET @report_center = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/report_center' LIMIT 1);

UPDATE `fa_auth_rule` SET `pid`=@product_center,`updatetime`=@now
WHERE `name` IN ('shop/goods','shop/category','shop/brand','shop/attribute','shop/spec','shop/sku_template','shop/ingredient','shop/ingredient_product_map');
UPDATE `fa_auth_rule` SET `pid`=@supplier_center,`updatetime`=@now
WHERE `name` IN ('shop/supplier','shop/supplier_sku','shop/supplier_delivery_region','shop/supplier_sync_log');
UPDATE `fa_auth_rule` SET `pid`=@inventory_center,`updatetime`=@now
WHERE `name` IN ('shop/warehouse','shop/warehouse_sku','shop/stock_reservation','shop/stock_flow');
UPDATE `fa_auth_rule` SET `pid`=@order_center,`updatetime`=@now
WHERE `name` IN ('shop/order','shop/order_supplier');
UPDATE `fa_auth_rule` SET `pid`=@delivery_center,`updatetime`=@now
WHERE `name` IN ('shop/order_shipment');
UPDATE `fa_auth_rule` SET `pid`=@aftersale_center,`updatetime`=@now
WHERE `name` IN ('shop/order_aftersales','shop/refund_transaction');
UPDATE `fa_auth_rule` SET `pid`=@report_center,`updatetime`=@now
WHERE `name` IN ('shop/report');

UPDATE `fa_auth_group`
SET `rules`=CONCAT_WS(',', NULLIF(`rules`, ''), @product_center)
WHERE `name`='商城运营' AND FIND_IN_SET(CONVERT(@product_center USING utf8mb4) COLLATE utf8mb4_general_ci, `rules`)=0;
UPDATE `fa_auth_group`
SET `rules`=CONCAT_WS(',', NULLIF(`rules`, ''), @supplier_center)
WHERE `name`='供应商运营' AND FIND_IN_SET(CONVERT(@supplier_center USING utf8mb4) COLLATE utf8mb4_general_ci, `rules`)=0;
UPDATE `fa_auth_group`
SET `rules`=CONCAT_WS(',', NULLIF(`rules`, ''), @inventory_center)
WHERE `name`='仓库人员' AND FIND_IN_SET(CONVERT(@inventory_center USING utf8mb4) COLLATE utf8mb4_general_ci, `rules`)=0;
UPDATE `fa_auth_group`
SET `rules`=CONCAT_WS(',', NULLIF(`rules`, ''),
    IF(FIND_IN_SET(CONVERT(@order_center USING utf8mb4) COLLATE utf8mb4_general_ci, `rules`)=0,@order_center,NULL),
    IF(FIND_IN_SET(CONVERT(@delivery_center USING utf8mb4) COLLATE utf8mb4_general_ci, `rules`)=0,@delivery_center,NULL),
    IF(FIND_IN_SET(CONVERT(@aftersale_center USING utf8mb4) COLLATE utf8mb4_general_ci, `rules`)=0,@aftersale_center,NULL))
WHERE `name`='订单客服';
UPDATE `fa_auth_group`
SET `rules`=CONCAT_WS(',', NULLIF(`rules`, ''),
    IF(FIND_IN_SET(CONVERT(@aftersale_center USING utf8mb4) COLLATE utf8mb4_general_ci, `rules`)=0,@aftersale_center,NULL),
    IF(FIND_IN_SET(CONVERT(@report_center USING utf8mb4) COLLATE utf8mb4_general_ci, `rules`)=0,@report_center,NULL))
WHERE `name`='财务人员';

INSERT INTO `fa_shop_schema_migration` (`version`,`description`,`applied_at`)
VALUES ('20260924_010','商城供应链后台八大业务中心导航',@now)
ON DUPLICATE KEY UPDATE `description`=VALUES(`description`),`applied_at`=VALUES(`applied_at`);

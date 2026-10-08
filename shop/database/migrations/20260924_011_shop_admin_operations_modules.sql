SET NAMES utf8mb4;
SET @now = UNIX_TIMESTAMP();
SET @product_center = (SELECT `id` FROM `fa_auth_rule` WHERE `name`='shop/product_center' LIMIT 1);
SET @inventory_center = (SELECT `id` FROM `fa_auth_rule` WHERE `name`='shop/inventory_center' LIMIT 1);
SET @shopping_list_center = (SELECT `id` FROM `fa_auth_rule` WHERE `name`='shop/shopping_list_center' LIMIT 1);

INSERT INTO `fa_auth_rule` (`type`,`pid`,`name`,`title`,`icon`,`url`,`condition`,`remark`,`ismenu`,`menutype`,`extend`,`py`,`pinyin`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@product_center,'shop/goods_substitute','替代商品关系','fa fa-random','','','维护商品与 SKU 级替代关系',1,NULL,'','','',@now,@now,63,'normal'),
('file',@shopping_list_center,'shop/shopping_list','清单查询','fa fa-list','','','菜单购物清单审计视图',1,NULL,'','','',@now,@now,70,'normal'),
('file',@inventory_center,'shop/stock_batch','批次与效期','fa fa-calendar-check-o','','','批次库存和效期审计视图',1,NULL,'','','',@now,@now,54,'normal')
ON DUPLICATE KEY UPDATE `pid`=VALUES(`pid`),`title`=VALUES(`title`),`ismenu`=1,`status`='normal',`updatetime`=@now;

SET @substitute_pid=(SELECT `id` FROM `fa_auth_rule` WHERE `name`='shop/goods_substitute' LIMIT 1);
SET @shopping_list_pid=(SELECT `id` FROM `fa_auth_rule` WHERE `name`='shop/shopping_list' LIMIT 1);
SET @stock_batch_pid=(SELECT `id` FROM `fa_auth_rule` WHERE `name`='shop/stock_batch' LIMIT 1);
INSERT INTO `fa_auth_rule` (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@substitute_pid,'shop/goods_substitute/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@substitute_pid,'shop/goods_substitute/add','添加','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@substitute_pid,'shop/goods_substitute/edit','编辑','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@substitute_pid,'shop/goods_substitute/del','删除','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@substitute_pid,'shop/goods_substitute/multi','批量更新','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@shopping_list_pid,'shop/shopping_list/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@stock_batch_pid,'shop/stock_batch/index','查看','fa fa-circle-o',0,@now,@now,0,'normal')
ON DUPLICATE KEY UPDATE `pid`=VALUES(`pid`),`title`=VALUES(`title`),`status`='normal',`updatetime`=@now;

UPDATE `fa_auth_group` SET `rules`=CONCAT_WS(',',NULLIF(`rules`,''),@substitute_pid) WHERE `name`='商城运营' AND FIND_IN_SET(CONVERT(@substitute_pid USING utf8mb4) COLLATE utf8mb4_general_ci,`rules`)=0;
UPDATE `fa_auth_group` SET `rules`=CONCAT_WS(',',NULLIF(`rules`,''),@stock_batch_pid) WHERE `name`='仓库人员' AND FIND_IN_SET(CONVERT(@stock_batch_pid USING utf8mb4) COLLATE utf8mb4_general_ci,`rules`)=0;

INSERT INTO `fa_shop_schema_migration` (`version`,`description`,`applied_at`) VALUES ('20260924_011','替代商品、购物清单和批次效期后台模块',@now)
ON DUPLICATE KEY UPDATE `description`=VALUES(`description`),`applied_at`=VALUES(`applied_at`);

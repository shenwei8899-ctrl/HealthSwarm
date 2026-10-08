SET NAMES utf8mb4;
SET @now = UNIX_TIMESTAMP();
SET @list_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name`='shop/shopping_list' LIMIT 1);
INSERT INTO `fa_auth_rule` (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`)
VALUES ('file',@list_pid,'shop/shopping_list/detail','查看匹配明细','fa fa-circle-o',0,@now,@now,0,'normal')
ON DUPLICATE KEY UPDATE `pid`=VALUES(`pid`),`title`=VALUES(`title`),`status`='normal',`updatetime`=@now;
SET @detail_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name`='shop/shopping_list/detail' LIMIT 1);
UPDATE `fa_auth_group`
SET `rules`=CONCAT_WS(',',NULLIF(`rules`,''),@detail_pid)
WHERE `name`='商城运营' AND FIND_IN_SET(CONVERT(@detail_pid USING utf8mb4) COLLATE utf8mb4_general_ci,`rules`)=0;
INSERT INTO `fa_shop_schema_migration` (`version`,`description`,`applied_at`)
VALUES ('20260924_014','购物清单匹配明细后台查看权限',@now)
ON DUPLICATE KEY UPDATE `description`=VALUES(`description`),`applied_at`=VALUES(`applied_at`);

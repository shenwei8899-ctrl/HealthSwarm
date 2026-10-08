SET NAMES utf8mb4;
SET @now = UNIX_TIMESTAMP();
SET @shop_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop' LIMIT 1);

INSERT IGNORE INTO `fa_auth_rule`
(`type`,`pid`,`name`,`title`,`icon`,`url`,`condition`,`remark`,`ismenu`,`menutype`,`extend`,`py`,`pinyin`,`createtime`,`updatetime`,`weigh`,`status`)
VALUES
('file',@shop_pid,'shop/supplier_sync_job','供应商同步任务','fa fa-refresh','','','支持失败重试和人工补偿',1,NULL,'','','',@now,@now,60,'normal'),
('file',@shop_pid,'shop/refund_transaction','退款事务','fa fa-money','','','支持本地补偿和人工确认',1,NULL,'','','',@now,@now,53,'normal');

SET @sync_job_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/supplier_sync_job' LIMIT 1);
SET @refund_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/refund_transaction' LIMIT 1);
SET @warehouse_sku_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/warehouse_sku' LIMIT 1);
SET @order_pid = (SELECT `id` FROM `fa_auth_rule` WHERE `name` = 'shop/order' LIMIT 1);

INSERT IGNORE INTO `fa_auth_rule` (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@sync_job_pid,'shop/supplier_sync_job/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@sync_job_pid,'shop/supplier_sync_job/retry','重试','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@sync_job_pid,'shop/supplier_sync_job/complete','人工补偿','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@refund_pid,'shop/refund_transaction/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@refund_pid,'shop/refund_transaction/reconcile','本地补偿','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@refund_pid,'shop/refund_transaction/confirm','人工确认','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@warehouse_sku_pid,'shop/warehouse_sku/adjust','库存调整','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@order_pid,'shop/order/package_deliver','分包发货','fa fa-circle-o',0,@now,@now,0,'normal');

INSERT INTO `fa_shop_schema_migration` (`version`,`description`,`applied_at`)
VALUES ('20260924_007','供应商同步、退款补偿和库存调整后台权限',@now)
ON DUPLICATE KEY UPDATE `description`=VALUES(`description`);

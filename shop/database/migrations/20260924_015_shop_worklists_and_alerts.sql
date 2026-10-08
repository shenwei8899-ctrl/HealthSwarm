SET NAMES utf8mb4;
SET @now=UNIX_TIMESTAMP();
SET @order_center=(SELECT id FROM fa_auth_rule WHERE name='shop/order_center' LIMIT 1);
SET @delivery_center=(SELECT id FROM fa_auth_rule WHERE name='shop/delivery_center' LIMIT 1);
SET @inventory_center=(SELECT id FROM fa_auth_rule WHERE name='shop/inventory_center' LIMIT 1);
SET @report_center=(SELECT id FROM fa_auth_rule WHERE name='shop/report_center' LIMIT 1);

UPDATE fa_auth_rule SET title='用户主订单',updatetime=@now WHERE name='shop/order';
UPDATE fa_auth_rule SET title='供应商履约子单',updatetime=@now WHERE name='shop/order_supplier';
UPDATE fa_auth_rule SET title='物流包裹',updatetime=@now WHERE name='shop/order_shipment';

INSERT INTO fa_auth_rule (`type`,`pid`,`name`,`title`,`icon`,`url`,`condition`,`remark`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@order_center,'shop/order_pending_payment','待支付','fa fa-clock-o','shop/order/index?worklist=pending_payment','','待支付订单工作台',1,@now,@now,68,'normal'),
('file',@order_center,'shop/order_preparing','待备货','fa fa-cubes','shop/order/index?worklist=preparing','','已支付待履约订单工作台',1,@now,@now,67,'normal'),
('file',@order_center,'shop/order_shipping','配送中','fa fa-truck','shop/order/index?worklist=shipping','','配送中订单工作台',1,@now,@now,66,'normal'),
('file',@order_center,'shop/order_completed','已完成','fa fa-check-circle','shop/order/index?worklist=completed','','已完成订单工作台',1,@now,@now,65,'normal'),
('file',@order_center,'shop/order_cancelled','已取消','fa fa-ban','shop/order/index?worklist=cancelled','','已取消和已关闭订单工作台',1,@now,@now,64,'normal'),
('file',@order_center,'shop/order_exception','订单异常','fa fa-exclamation-triangle','shop/order/index?worklist=exception','','售后和异常订单工作台',1,@now,@now,63,'normal'),
('file',@delivery_center,'shop/delivery_picking','待拣货','fa fa-list-alt','shop/order_supplier/index?worklist=picking','','待接单和待拣货子单',1,@now,@now,70,'normal'),
('file',@delivery_center,'shop/delivery_outbound','待出库','fa fa-sign-out','shop/order_supplier/index?worklist=outbound','','备货和部分发货子单',1,@now,@now,69,'normal'),
('file',@delivery_center,'shop/delivery_exception','配送异常','fa fa-exclamation-circle','shop/order_supplier/index?worklist=exception','','拒绝和取消的履约子单',1,@now,@now,67,'normal'),
('file',@inventory_center,'shop/low_stock','低库存预警','fa fa-warning','shop/low_stock/index','','按 SKU 安全库存展示补货缺口',1,@now,@now,53,'normal'),
('file',@report_center,'shop/expiry_alert','临期预警','fa fa-calendar-times-o','shop/expiry_alert/index?days=30','','批次临期和过期预警',1,@now,@now,60,'normal')
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),icon=VALUES(icon),url=VALUES(url),remark=VALUES(remark),ismenu=1,status='normal',updatetime=@now;

SET @low_stock=(SELECT id FROM fa_auth_rule WHERE name='shop/low_stock' LIMIT 1);
SET @expiry_alert=(SELECT id FROM fa_auth_rule WHERE name='shop/expiry_alert' LIMIT 1);
INSERT INTO fa_auth_rule (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@low_stock,'shop/low_stock/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@expiry_alert,'shop/expiry_alert/index','查看','fa fa-circle-o',0,@now,@now,0,'normal')
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),status='normal',updatetime=@now;

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260924_015','订单配送状态工作台、低库存和临期预警',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

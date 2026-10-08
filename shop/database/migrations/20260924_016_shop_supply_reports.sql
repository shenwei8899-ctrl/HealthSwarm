SET NAMES utf8mb4;
SET @now=UNIX_TIMESTAMP();
SET @report_center=(SELECT id FROM fa_auth_rule WHERE name='shop/report_center' LIMIT 1);
UPDATE fa_auth_rule SET title='统计概览',updatetime=@now WHERE name='shop/report';
INSERT INTO fa_auth_rule (`type`,`pid`,`name`,`title`,`icon`,`url`,`condition`,`remark`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@report_center,'shop/report_product_sales','商品销售','fa fa-line-chart','shop/supply_report/index?report=product_sales','','商品销量、销售额和订单数',1,@now,@now,59,'normal'),
('file',@report_center,'shop/report_orders','订单报表','fa fa-shopping-bag','shop/supply_report/index?report=orders','','按业务状态汇总订单',1,@now,@now,58,'normal'),
('file',@report_center,'shop/report_supplier_fulfillment','供应商履约','fa fa-building','shop/supply_report/index?report=supplier_fulfillment','','供应商子单履约与供货金额',1,@now,@now,57,'normal'),
('file',@report_center,'shop/report_inventory','库存报表','fa fa-archive','shop/supply_report/index?report=inventory','','按仓库汇总库存结构',1,@now,@now,56,'normal'),
('file',@report_center,'shop/report_refunds','退款售后','fa fa-undo','shop/supply_report/index?report=refunds','','退款状态、金额和重试次数',1,@now,@now,55,'normal')
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),icon=VALUES(icon),url=VALUES(url),remark=VALUES(remark),ismenu=1,status='normal',updatetime=@now;
INSERT INTO fa_auth_rule (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`)
VALUES ('file',@report_center,'shop/supply_report/index','查看供应链报表','fa fa-circle-o',0,@now,@now,0,'normal')
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),status='normal',updatetime=@now;
INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES ('20260924_016','供应链商品、订单、履约、库存、退款和临期报表',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

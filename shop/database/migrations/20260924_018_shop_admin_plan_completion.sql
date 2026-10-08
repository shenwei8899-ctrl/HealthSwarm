SET NAMES utf8mb4;
SET @now=UNIX_TIMESTAMP();

CREATE TABLE IF NOT EXISTS `fa_shop_supplier_reconciliation` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reconciliation_sn` varchar(64) NOT NULL COMMENT '对账单号',
  `supplier_id` int unsigned NOT NULL COMMENT '供应商ID',
  `period_start` date NOT NULL COMMENT '账期开始',
  `period_end` date NOT NULL COMMENT '账期结束',
  `order_count` int unsigned NOT NULL DEFAULT '0' COMMENT '履约子单数',
  `goods_amount` decimal(14,2) unsigned NOT NULL DEFAULT '0.00' COMMENT '商品销售额',
  `supply_amount` decimal(14,2) unsigned NOT NULL DEFAULT '0.00' COMMENT '供货结算额',
  `refund_amount` decimal(14,2) unsigned NOT NULL DEFAULT '0.00' COMMENT '退款扣减额',
  `payable_amount` decimal(14,2) unsigned NOT NULL DEFAULT '0.00' COMMENT '应付金额',
  `status` enum('DRAFT','CONFIRMED','DISPUTED','PAID') NOT NULL DEFAULT 'DRAFT',
  `confirmed_at` bigint unsigned DEFAULT NULL,
  `paid_at` bigint unsigned DEFAULT NULL,
  `admin_id` int unsigned NOT NULL DEFAULT '0',
  `remark` varchar(500) NOT NULL DEFAULT '',
  `createtime` bigint unsigned NOT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_reconciliation_sn` (`reconciliation_sn`),
  UNIQUE KEY `uk_supplier_period` (`supplier_id`,`period_start`,`period_end`),
  KEY `idx_status_period` (`status`,`period_end`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='供应商对账单';

SET @product_center=(SELECT id FROM fa_auth_rule WHERE name='shop/product_center' LIMIT 1);
SET @supplier_center=(SELECT id FROM fa_auth_rule WHERE name='shop/supplier_center' LIMIT 1);
SET @inventory_center=(SELECT id FROM fa_auth_rule WHERE name='shop/inventory_center' LIMIT 1);
SET @shopping_list_center=(SELECT id FROM fa_auth_rule WHERE name='shop/shopping_list_center' LIMIT 1);

UPDATE fa_auth_rule SET title='商品管理',updatetime=@now WHERE name='shop/goods';
UPDATE fa_auth_rule SET title='商品分类',updatetime=@now WHERE name='shop/category';
UPDATE fa_auth_rule SET title='品牌管理',updatetime=@now WHERE name='shop/brand';
UPDATE fa_auth_rule SET title='属性管理',updatetime=@now WHERE name='shop/attribute';
UPDATE fa_auth_rule SET title='配送区域及时效',updatetime=@now WHERE name='shop/supplier_delivery_region';
UPDATE fa_auth_rule SET title='数据同步记录',updatetime=@now WHERE name='shop/supplier_sync_log';
UPDATE fa_auth_rule SET title='SKU 库存查询',updatetime=@now WHERE name='shop/warehouse_sku';
UPDATE fa_auth_rule SET title='批次/效期',updatetime=@now WHERE name='shop/stock_batch';
UPDATE fa_auth_rule SET title='清单查询',updatetime=@now WHERE name='shop/shopping_list';

UPDATE fa_auth_rule SET ismenu=0,updatetime=@now
WHERE name IN ('shop/spec','shop/sku_template','shop/report','shop/refund_transaction','shop/supplier_sync_job');

INSERT INTO fa_auth_rule (`type`,`pid`,`name`,`title`,`icon`,`url`,`condition`,`remark`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@product_center,'shop/spec_sku','规格与 SKU','fa fa-cubes','shop/spec_sku/index','','规格定义、模板与商品 SKU 统一查询',1,@now,@now,74,'normal'),
('file',@supplier_center,'shop/supplier_reconciliation','供应商对账','fa fa-calculator','shop/supplier_reconciliation/index','','按账期汇总履约供货额和退款扣减',1,@now,@now,64,'normal'),
('file',@inventory_center,'shop/inventory_adjustment','库存调整','fa fa-sliders','shop/warehouse_sku/index?worklist=adjust','','人工调整实物、不可售和在途库存',1,@now,@now,54,'normal'),
('file',@shopping_list_center,'shop/shopping_list_matching','匹配结果','fa fa-check-circle','shop/shopping_list/index?worklist=matching','','全部食材已完成商品匹配的购物清单',1,@now,@now,69,'normal'),
('file',@shopping_list_center,'shop/shopping_list_exception','匹配异常','fa fa-exclamation-triangle','shop/shopping_list/index?worklist=exception','','存在未匹配商品或采购缺口的购物清单',1,@now,@now,68,'normal')
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),icon=VALUES(icon),url=VALUES(url),remark=VALUES(remark),ismenu=1,status='normal',updatetime=@now;

SET @spec_sku=(SELECT id FROM fa_auth_rule WHERE name='shop/spec_sku' LIMIT 1);
SET @supplier_reconciliation=(SELECT id FROM fa_auth_rule WHERE name='shop/supplier_reconciliation' LIMIT 1);
INSERT INTO fa_auth_rule (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@spec_sku,'shop/spec_sku/index','查看规格与 SKU','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@supplier_reconciliation,'shop/supplier_reconciliation/index','查看对账单','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@supplier_reconciliation,'shop/supplier_reconciliation/generate','生成对账单','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@supplier_reconciliation,'shop/supplier_reconciliation/confirm','确认对账单','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@supplier_reconciliation,'shop/supplier_reconciliation/dispute','标记争议','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@supplier_reconciliation,'shop/supplier_reconciliation/markpaid','确认付款','fa fa-circle-o',0,@now,@now,0,'normal')
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),status='normal',updatetime=@now;

UPDATE fa_auth_group SET rules=(
  SELECT GROUP_CONCAT(id ORDER BY id) FROM fa_auth_rule
  WHERE name='shop' OR name REGEXP '^shop/(product|shopping_list|goods|category|brand|attribute|spec|spec_sku|sku_template|ingredient)'
),updatetime=@now WHERE name='商城运营';
UPDATE fa_auth_group SET rules=(
  SELECT GROUP_CONCAT(id ORDER BY id) FROM fa_auth_rule
  WHERE name='shop' OR name REGEXP '^shop/(supplier|supplier_reconciliation|delivery|order_supplier|order_shipment)'
),updatetime=@now WHERE name='供应商运营';
UPDATE fa_auth_group SET rules=(
  SELECT GROUP_CONCAT(id ORDER BY id) FROM fa_auth_rule
  WHERE name='shop' OR name REGEXP '^shop/(inventory|warehouse|stock|low_stock|delivery|order_supplier|order_shipment)'
),updatetime=@now WHERE name='仓库人员';
UPDATE fa_auth_group SET rules=(
  SELECT GROUP_CONCAT(id ORDER BY id) FROM fa_auth_rule
  WHERE name='shop' OR name REGEXP '^shop/(aftersale|report|supply_report|expiry_alert|refund|order|supplier_reconciliation)'
),updatetime=@now WHERE name='财务人员';

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260924_018','按改造方案收口后台菜单、购物清单工作台、库存调整和供应商对账',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

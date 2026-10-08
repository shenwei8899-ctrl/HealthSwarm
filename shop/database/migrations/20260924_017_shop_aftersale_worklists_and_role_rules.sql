SET NAMES utf8mb4;
SET @now=UNIX_TIMESTAMP();
SET @supplier_center=(SELECT id FROM fa_auth_rule WHERE name='shop/supplier_center' LIMIT 1);
SET @aftersale_center=(SELECT id FROM fa_auth_rule WHERE name='shop/aftersale_center' LIMIT 1);

UPDATE fa_auth_rule SET title='售后记录',url='shop/order_aftersales/index?worklist=records',updatetime=@now WHERE name='shop/order_aftersales';
INSERT INTO fa_auth_rule (`type`,`pid`,`name`,`title`,`icon`,`url`,`condition`,`remark`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@supplier_center,'shop/supplier_price','供货价格','fa fa-cny','shop/supplier_sku/index?pricing=1','','供应商 SKU 供货价格维护',1,@now,@now,67,'normal'),
('file',@aftersale_center,'shop/aftersale_refund','退款申请','fa fa-money','shop/order_aftersales/index?worklist=refund','','待处理退款申请',1,@now,@now,70,'normal'),
('file',@aftersale_center,'shop/aftersale_return','退货退款','fa fa-reply','shop/order_aftersales/index?worklist=return','','退货退款申请及进度',1,@now,@now,69,'normal'),
('file',@aftersale_center,'shop/aftersale_inspection','退货验收','fa fa-check-square-o','shop/order_aftersales/index?worklist=inspection','','已寄回待验收退货',1,@now,@now,68,'normal')
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),icon=VALUES(icon),url=VALUES(url),remark=VALUES(remark),ismenu=1,status='normal',updatetime=@now;

UPDATE fa_auth_group SET rules=(
  SELECT GROUP_CONCAT(id ORDER BY id) FROM fa_auth_rule
  WHERE name='shop' OR name REGEXP '^shop/(product|shopping_list|goods|category|brand|attribute|spec|sku_template|ingredient)'
),updatetime=@now WHERE name='商城运营';
UPDATE fa_auth_group SET rules=(
  SELECT GROUP_CONCAT(id ORDER BY id) FROM fa_auth_rule
  WHERE name='shop' OR name REGEXP '^shop/(order|delivery|aftersale|refund)'
),updatetime=@now WHERE name='订单客服';
UPDATE fa_auth_group SET rules=(
  SELECT GROUP_CONCAT(id ORDER BY id) FROM fa_auth_rule
  WHERE name='shop' OR name REGEXP '^shop/(supplier|delivery|order_supplier|order_shipment)'
),updatetime=@now WHERE name='供应商运营';
UPDATE fa_auth_group SET rules=(
  SELECT GROUP_CONCAT(id ORDER BY id) FROM fa_auth_rule
  WHERE name='shop' OR name REGEXP '^shop/(inventory|warehouse|stock|low_stock|delivery|order_supplier|order_shipment)'
),updatetime=@now WHERE name='仓库人员';
UPDATE fa_auth_group SET rules=(
  SELECT GROUP_CONCAT(id ORDER BY id) FROM fa_auth_rule
  WHERE name='shop' OR name REGEXP '^shop/(aftersale|report|supply_report|expiry_alert|refund|order)'
),updatetime=@now WHERE name='财务人员';

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260924_017','供货价格、售后工作台及业务角色权限',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

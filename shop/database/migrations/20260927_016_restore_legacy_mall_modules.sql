SET NAMES utf8mb4;
SET SESSION group_concat_max_len = 100000;
SET @now = UNIX_TIMESTAMP();
SET @shop_pid = (SELECT id FROM fa_auth_rule WHERE name='shop' LIMIT 1);

-- Restore the legacy storefront-management entries removed during the initial
-- supply-chain simplification. The supply-chain business centers remain intact.
CREATE TEMPORARY TABLE tmp_legacy_shop_menu (
  name varchar(100) NOT NULL PRIMARY KEY,
  title varchar(100) NOT NULL,
  icon varchar(50) NOT NULL,
  weigh int NOT NULL DEFAULT 0,
  remark varchar(255) NOT NULL DEFAULT ''
) ENGINE=MEMORY DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO tmp_legacy_shop_menu (name,title,icon,weigh,remark) VALUES
('shop/guarantee','服务保障','fa fa-asterisk',49,''),
('shop/freight','运费模板','fa fa-sticky-note-o',49,''),
('shop/comment','评论管理','fa fa-commenting-o',47,''),
('shop/electronics_order','电子面单','fa fa-sticky-note-o',47,''),
('shop/collect','收藏管理','fa fa-heart',46,''),
('shop/address','收货地址','fa fa-map-signs',44,''),
('shop/exchange','积分兑换','fa fa-pinterest',45,''),
('shop/coupon','优惠券管理','fa fa-jpy',45,''),
('shop/navigation','导航配置','fa fa-th',38,''),
('shop/menu','菜单管理','fa fa-navicon',36,''),
('shop/theme','移动端预览','fa fa-mobile',32,''),
('shop/config','配置管理','fa fa-cog',55,''),
('shop/block','区块管理','fa fa-th-large',16,''),
('shop/page','单页管理','fa fa-file',15,''),
('shop/search_log','搜索记录管理','fa fa-history',15,''),
('shop/template_msg','模板消息','fa fa-comment',15,''),
('shop/area','地区管理','fa fa-map-marker',14,''),
('shop/card','卡片模板','fa fa-file-photo-o',15,''),
('shop/supplier_sync_job','供应商同步任务','fa fa-refresh',60,'支持失败重试和人工补偿');

INSERT INTO fa_auth_rule
(`type`,`pid`,`name`,`title`,`icon`,`url`,`condition`,`remark`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`)
SELECT 'file',@shop_pid,name,title,icon,'','',remark,1,@now,@now,weigh,'normal'
FROM tmp_legacy_shop_menu
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),icon=VALUES(icon),remark=VALUES(remark),ismenu=1,status='normal',weigh=VALUES(weigh),updatetime=@now;

INSERT INTO fa_auth_rule (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`)
SELECT 'file',rule.id,CONCAT(menu.name,'/index'),'查看','fa fa-circle-o',0,@now,@now,0,'normal'
FROM tmp_legacy_shop_menu menu
JOIN fa_auth_rule rule ON rule.name=menu.name
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),status='normal',updatetime=@now;

INSERT INTO fa_auth_rule (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`)
SELECT 'file',rule.id,CONCAT(menu.name,'/',action.action_name),action.action_title,'fa fa-circle-o',0,@now,@now,0,'normal'
FROM tmp_legacy_shop_menu menu
JOIN fa_auth_rule rule ON rule.name=menu.name
JOIN (
  SELECT 'add' AS action_name,'添加' AS action_title
  UNION ALL SELECT 'edit','编辑'
  UNION ALL SELECT 'del','删除'
  UNION ALL SELECT 'multi','批量更新'
) action
WHERE menu.name NOT IN ('shop/theme','shop/config','shop/supplier_sync_job')
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),status='normal',updatetime=@now;

-- Re-expose legacy product-management pages whose menu records were retained.
UPDATE fa_auth_rule SET ismenu=1,status='normal',updatetime=@now
WHERE name IN (
  'shop/goods_sku','shop/goods_sku_spec','shop/spec','shop/spec_value','shop/sku_template',
  'shop/attribute','shop/attribute_value','shop/freight_items','shop/shipper','shop/order_goods',
  'shop/order_action','shop/goods_substitute','shop/refund_transaction','shop/report'
);

-- The earlier cleanup removed this list permission while retaining its parent.
INSERT INTO fa_auth_rule (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`)
SELECT 'file',id,'shop/goods_sku/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'
FROM fa_auth_rule WHERE name='shop/goods_sku'
ON DUPLICATE KEY UPDATE pid=VALUES(pid),status='normal',updatetime=@now;

UPDATE fa_auth_group
SET rules=(SELECT GROUP_CONCAT(id ORDER BY id) FROM fa_auth_rule WHERE name='shop' OR name LIKE 'shop/%'),updatetime=@now
WHERE name='商城运营' AND rules<>'*';

DROP TEMPORARY TABLE tmp_legacy_shop_menu;

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260927_016','恢复旧商城后台模块、页面权限与侧栏入口',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

SET NAMES utf8mb4;
SET SESSION group_concat_max_len = 100000;
SET @now = UNIX_TIMESTAMP();
SET @shop_pid = (SELECT id FROM fa_auth_rule WHERE name = 'shop' LIMIT 1);

-- Restore every complete module that still has permission children.
UPDATE fa_auth_rule
SET ismenu = 1, status = 'normal', updatetime = @now
WHERE name IN (
  'shop/goods_sku','shop/goods_sku_spec','shop/spec_value','shop/freight_items',
  'shop/shipper','shop/exchange_order','shop/user_coupon','shop/coupon_condition',
  'shop/attribute_value','shop/order_goods','shop/order_action','shop/ingredient',
  'shop/attribute','shop/ingredient_product_map','shop/spec_sku','shop/goods_substitute',
  'shop/spec','shop/sku_template','shop/refund_transaction','shop/report'
);

CREATE TEMPORARY TABLE tmp_restore_shop_menu (
  name varchar(100) NOT NULL PRIMARY KEY,
  title varchar(100) NOT NULL,
  icon varchar(50) NOT NULL DEFAULT 'fa fa-circle-o',
  weigh int NOT NULL DEFAULT 0,
  remark varchar(255) NOT NULL DEFAULT ''
) ENGINE=MEMORY DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO tmp_restore_shop_menu (name,title,icon,weigh,remark) VALUES
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
('shop/block','区块管理','fa fa-th-large',16,'用于管理站点的自定义区块内容'),
('shop/page','单页管理','fa fa-file',15,'用于管理网站单页面'),
('shop/search_log','搜索记录管理','fa fa-history',15,'用于管理网站搜索记录'),
('shop/template_msg','模板消息','fa fa-comment',15,'用于发送消息通知用户'),
('shop/area','地区管理','fa fa-map-marker',14,''),
('shop/card','卡片模板','fa fa-file-photo-o',15,''),
('shop/supplier_sync_job','供应商同步任务','fa fa-refresh',60,'支持失败重试和人工补偿');

INSERT INTO fa_auth_rule
(`type`,`pid`,`name`,`title`,`icon`,`url`,`condition`,`remark`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`)
SELECT 'file',@shop_pid,name,title,icon,'','',remark,1,@now,@now,weigh,'normal'
FROM tmp_restore_shop_menu
ON DUPLICATE KEY UPDATE
  pid=VALUES(pid),title=VALUES(title),icon=VALUES(icon),remark=VALUES(remark),
  ismenu=1,status='normal',weigh=VALUES(weigh),updatetime=@now;

-- Every restored module has a list page.
INSERT INTO fa_auth_rule
(`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`)
SELECT 'file',r.id,CONCAT(m.name,'/index'),'查看','fa fa-circle-o',0,@now,@now,0,'normal'
FROM tmp_restore_shop_menu m
JOIN fa_auth_rule r ON r.name=m.name
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),status='normal',updatetime=@now;

-- Standard CRUD permissions for modules that expose the standard management pages.
INSERT INTO fa_auth_rule
(`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`)
SELECT 'file',r.id,CONCAT(m.name,'/',a.action_name),a.action_title,'fa fa-circle-o',0,@now,@now,0,'normal'
FROM tmp_restore_shop_menu m
JOIN fa_auth_rule r ON r.name=m.name
JOIN (
  SELECT 'add' action_name,'添加' action_title
  UNION ALL SELECT 'edit','编辑'
  UNION ALL SELECT 'del','删除'
  UNION ALL SELECT 'multi','批量更新'
) a
WHERE m.name NOT IN ('shop/theme','shop/config','shop/supplier_sync_job')
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),status='normal',updatetime=@now;

CREATE TEMPORARY TABLE tmp_restore_shop_extra_rule (
  parent_name varchar(100) NOT NULL,
  action_name varchar(50) NOT NULL,
  action_title varchar(100) NOT NULL,
  PRIMARY KEY (parent_name,action_name)
) ENGINE=MEMORY DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO tmp_restore_shop_extra_rule (parent_name,action_name,action_title) VALUES
('shop/comment','reply','回复'),
('shop/address','recyclebin','回收站'),
('shop/address','restore','还原'),
('shop/address','destroy','真实删除'),
('shop/exchange','creategoods','生成商品'),
('shop/page','recyclebin','回收站'),
('shop/page','restore','还原'),
('shop/page','destroy','真实删除'),
('shop/area','import','导入'),
('shop/area','refresh','刷新'),
('shop/supplier_sync_job','retry','重试'),
('shop/supplier_sync_job','complete','人工补偿');

INSERT INTO fa_auth_rule
(`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`)
SELECT 'file',r.id,CONCAT(e.parent_name,'/',e.action_name),e.action_title,'fa fa-circle-o',0,@now,@now,0,'normal'
FROM tmp_restore_shop_extra_rule e
JOIN fa_auth_rule r ON r.name=e.parent_name
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),status='normal',updatetime=@now;

-- Let the mall operator inspect every restored module while the final scope is reviewed.
UPDATE fa_auth_group
SET rules=(
  SELECT GROUP_CONCAT(id ORDER BY id)
  FROM fa_auth_rule
  WHERE name='shop' OR name LIKE 'shop/%'
),updatetime=@now
WHERE name='商城运营';

DROP TEMPORARY TABLE tmp_restore_shop_extra_rule;
DROP TEMPORARY TABLE tmp_restore_shop_menu;

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260927_002','恢复全部商城后台模块供功能范围评估',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

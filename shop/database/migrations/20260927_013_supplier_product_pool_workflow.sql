SET NAMES utf8mb4;
SET SESSION group_concat_max_len = 100000;
SET @now = UNIX_TIMESTAMP();

CREATE TABLE IF NOT EXISTS `fa_shop_supplier_product_pool` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `supplier_id` int unsigned NOT NULL,
  `supplier_goods_code` varchar(100) NOT NULL DEFAULT '',
  `supplier_sku_code` varchar(100) NOT NULL,
  `title` varchar(255) NOT NULL DEFAULT '',
  `spec_text` varchar(500) NOT NULL DEFAULT '',
  `barcode` varchar(100) NOT NULL DEFAULT '',
  `image` varchar(255) NOT NULL DEFAULT '',
  `supply_price` decimal(12,2) unsigned NOT NULL DEFAULT '0.00',
  `min_order_qty` int unsigned NOT NULL DEFAULT '1',
  `delivery_days` int unsigned NOT NULL DEFAULT '0',
  `fulfillment_mode` enum('PLATFORM_WAREHOUSE','SUPPLIER_DIRECT') NOT NULL DEFAULT 'SUPPLIER_DIRECT',
  `source_payload_json` json DEFAULT NULL,
  `goods_id` int unsigned NOT NULL DEFAULT '0',
  `goods_sku_id` int unsigned NOT NULL DEFAULT '0',
  `match_status` enum('PENDING','AUTO_MATCHED','MATCHED','IGNORED') NOT NULL DEFAULT 'PENDING',
  `match_method` varchar(30) NOT NULL DEFAULT 'NONE',
  `match_note` varchar(500) NOT NULL DEFAULT '',
  `sync_status` enum('SUCCESS','FAILED') NOT NULL DEFAULT 'SUCCESS',
  `last_sync_time` bigint unsigned DEFAULT NULL,
  `status` enum('normal','offline') NOT NULL DEFAULT 'normal',
  `createtime` bigint unsigned NOT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_supplier_sku` (`supplier_id`,`supplier_sku_code`),
  KEY `idx_match_status` (`match_status`,`supplier_id`),
  KEY `idx_goods_sku` (`goods_id`,`goods_sku_id`),
  KEY `idx_barcode` (`barcode`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='供应商原始商品池与平台匹配结果';

SET @supplier_center = (SELECT id FROM fa_auth_rule WHERE name='shop/supplier_center' LIMIT 1);
INSERT INTO fa_auth_rule (`type`,`pid`,`name`,`title`,`icon`,`url`,`condition`,`remark`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@supplier_center,'shop/supplier_product_pool','供应商商品池','fa fa-inbox','','','供应商同步商品的待匹配和关联工作台',1,@now,@now,80,'normal')
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),icon=VALUES(icon),remark=VALUES(remark),ismenu=1,status='normal',updatetime=@now;

SET @pool_pid = (SELECT id FROM fa_auth_rule WHERE name='shop/supplier_product_pool' LIMIT 1);
INSERT INTO fa_auth_rule (`type`,`pid`,`name`,`title`,`icon`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`) VALUES
('file',@pool_pid,'shop/supplier_product_pool/index','查看','fa fa-circle-o',0,@now,@now,0,'normal'),
('file',@pool_pid,'shop/supplier_product_pool/match','关联平台 SKU','fa fa-link',0,@now,@now,0,'normal'),
('file',@pool_pid,'shop/supplier_product_pool/createplatform','创建平台商品草稿','fa fa-plus',0,@now,@now,0,'normal'),
('file',@pool_pid,'shop/supplier_product_pool/ignore','忽略','fa fa-ban',0,@now,@now,0,'normal')
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),status='normal',updatetime=@now;

UPDATE fa_auth_rule SET title='已关联供货',icon='fa fa-link',updatetime=@now WHERE name='shop/supplier_sku';

SET @pool_permissions = (SELECT GROUP_CONCAT(id ORDER BY id) FROM fa_auth_rule WHERE name='shop/supplier_product_pool' OR name LIKE 'shop/supplier_product_pool/%');
UPDATE fa_auth_group g
SET rules=CONCAT_WS(',',NULLIF(g.rules,''),@pool_permissions)
WHERE g.name IN ('商城运营','供应商运营')
  AND g.rules<>'*'
  AND NOT FIND_IN_SET(CONVERT(@pool_pid USING utf8mb4) COLLATE utf8mb4_general_ci,g.rules);

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260927_013','供应商商品池、商品匹配及平台商品草稿流程',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

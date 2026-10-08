SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `fa_shop_stock_reservation_adjustment` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `adjustment_sn` varchar(64) NOT NULL COMMENT '幂等调整流水号',
  `reservation_id` bigint unsigned NOT NULL COMMENT '库存锁定记录ID',
  `order_goods_id` int unsigned NOT NULL DEFAULT '0' COMMENT '订单商品ID',
  `aftersales_id` int unsigned NOT NULL DEFAULT '0' COMMENT '售后单ID',
  `adjustment_type` enum('RELEASE','DEDUCT') NOT NULL COMMENT '释放或实际出库',
  `quantity` int unsigned NOT NULL COMMENT '调整数量',
  `biz_no` varchar(100) NOT NULL COMMENT '幂等业务号',
  `remark` varchar(500) NOT NULL DEFAULT '',
  `createtime` bigint unsigned NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_adjustment_sn` (`adjustment_sn`),
  KEY `idx_reservation_type` (`reservation_id`,`adjustment_type`),
  KEY `idx_order_goods` (`order_goods_id`),
  KEY `idx_aftersales` (`aftersales_id`),
  KEY `idx_biz_no` (`biz_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='库存锁定部分释放及出库明细';

CREATE TABLE IF NOT EXISTS `fa_shop_aftersales_inspection` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `inspection_sn` varchar(64) NOT NULL COMMENT '质检幂等流水号',
  `aftersales_id` int unsigned NOT NULL COMMENT '售后单ID',
  `supplier_order_id` bigint unsigned NOT NULL COMMENT '供应商子单ID',
  `warehouse_sku_id` bigint unsigned NOT NULL COMMENT '退回仓库库存ID',
  `accepted_quantity` int unsigned NOT NULL DEFAULT '0' COMMENT '合格可售数量',
  `rejected_quantity` int unsigned NOT NULL DEFAULT '0' COMMENT '不合格不可售数量',
  `status` enum('ACCEPTED','PARTIAL','REJECTED') NOT NULL,
  `biz_no` varchar(100) NOT NULL COMMENT '幂等业务号',
  `operator_type` varchar(30) NOT NULL DEFAULT 'ADMIN',
  `operator_id` int unsigned NOT NULL DEFAULT '0',
  `remark` varchar(500) NOT NULL DEFAULT '',
  `createtime` bigint unsigned NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_inspection_sn` (`inspection_sn`),
  UNIQUE KEY `uk_aftersales` (`aftersales_id`),
  UNIQUE KEY `uk_biz_no` (`biz_no`),
  KEY `idx_supplier_order` (`supplier_order_id`),
  KEY `idx_warehouse_sku` (`warehouse_sku_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='售后退货质检及库存去向';

INSERT INTO `fa_shop_schema_migration` (`version`,`description`,`applied_at`)
VALUES ('20260923_003','部分售后库存锁定调整与退货质检审计',UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `description`=VALUES(`description`);

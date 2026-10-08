SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `fa_shop_schema_migration` (
  `version` varchar(64) NOT NULL COMMENT '迁移版本',
  `description` varchar(255) NOT NULL DEFAULT '' COMMENT '迁移说明',
  `applied_at` bigint unsigned NOT NULL COMMENT '执行时间',
  PRIMARY KEY (`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='商城数据库迁移记录';

CREATE TABLE IF NOT EXISTS `fa_shop_goods_ext` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `goods_id` int unsigned NOT NULL COMMENT '商品ID',
  `product_type` enum('NORMAL','INGREDIENT','BUNDLE') NOT NULL DEFAULT 'NORMAL' COMMENT '商品类型',
  `composition_json` json DEFAULT NULL COMMENT '商品组成',
  `allergen_tags_json` json DEFAULT NULL COMMENT '过敏原标签',
  `applicable_tags_json` json DEFAULT NULL COMMENT '适用标签',
  `origin` varchar(255) NOT NULL DEFAULT '' COMMENT '产地',
  `storage_condition` varchar(255) NOT NULL DEFAULT '' COMMENT '储存条件',
  `shelf_life_days` int unsigned NOT NULL DEFAULT '0' COMMENT '保质期天数',
  `delivery_scope_type` enum('ALL','REGION','SUPPLIER') NOT NULL DEFAULT 'SUPPLIER' COMMENT '配送范围类型',
  `createtime` bigint unsigned DEFAULT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_goods_id` (`goods_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='商品扩展资料';

CREATE TABLE IF NOT EXISTS `fa_shop_sku_ext` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `goods_id` int unsigned NOT NULL COMMENT '商品ID',
  `goods_sku_id` int unsigned NOT NULL DEFAULT '0' COMMENT 'SKU ID，0表示无规格商品',
  `barcode` varchar(100) NOT NULL DEFAULT '' COMMENT '条码',
  `unit` varchar(30) NOT NULL DEFAULT '份' COMMENT '销售单位',
  `net_quantity` decimal(14,3) unsigned NOT NULL DEFAULT '0.000' COMMENT '单份净含量',
  `net_unit` varchar(20) NOT NULL DEFAULT 'g' COMMENT '净含量单位',
  `reference_cost_price` decimal(12,2) unsigned NOT NULL DEFAULT '0.00' COMMENT '平台参考成本',
  `safety_stock` int unsigned NOT NULL DEFAULT '0' COMMENT '安全库存',
  `batch_enabled` tinyint unsigned NOT NULL DEFAULT '0' COMMENT '是否启用批次',
  `expiry_enabled` tinyint unsigned NOT NULL DEFAULT '0' COMMENT '是否启用效期',
  `createtime` bigint unsigned DEFAULT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_goods_sku` (`goods_id`,`goods_sku_id`),
  KEY `idx_barcode` (`barcode`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='商品SKU扩展资料';

CREATE TABLE IF NOT EXISTS `fa_shop_ingredient` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(64) NOT NULL COMMENT '标准食材编码',
  `name` varchar(100) NOT NULL COMMENT '标准食材名称',
  `category` varchar(100) NOT NULL DEFAULT '' COMMENT '食材分类',
  `default_unit` varchar(20) NOT NULL DEFAULT 'g' COMMENT '默认标准单位',
  `aliases_json` json DEFAULT NULL COMMENT '同义词',
  `status` enum('normal','hidden') NOT NULL DEFAULT 'normal',
  `createtime` bigint unsigned DEFAULT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_code` (`code`),
  KEY `idx_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='标准食材库';

CREATE TABLE IF NOT EXISTS `fa_shop_ingredient_product_map` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `ingredient_id` int unsigned NOT NULL COMMENT '标准食材ID',
  `goods_id` int unsigned NOT NULL COMMENT '商品ID',
  `goods_sku_id` int unsigned NOT NULL DEFAULT '0' COMMENT 'SKU ID，0表示无规格商品',
  `content_quantity` decimal(14,3) unsigned NOT NULL DEFAULT '0.000' COMMENT '一份商品覆盖食材量',
  `content_unit` varchar(20) NOT NULL DEFAULT 'g' COMMENT '覆盖量单位',
  `conversion_rate` decimal(18,6) unsigned NOT NULL DEFAULT '1.000000' COMMENT '转为食材默认单位的系数',
  `priority` int NOT NULL DEFAULT '0' COMMENT '人工优先级',
  `is_substitute` tinyint unsigned NOT NULL DEFAULT '0' COMMENT '是否仅作为替代项',
  `status` enum('normal','hidden') NOT NULL DEFAULT 'normal',
  `createtime` bigint unsigned DEFAULT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ingredient_goods_sku` (`ingredient_id`,`goods_id`,`goods_sku_id`),
  KEY `idx_goods_sku` (`goods_id`,`goods_sku_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='食材与商品SKU映射';

CREATE TABLE IF NOT EXISTS `fa_shop_goods_substitute` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `goods_id` int unsigned NOT NULL,
  `goods_sku_id` int unsigned NOT NULL DEFAULT '0',
  `substitute_goods_id` int unsigned NOT NULL,
  `substitute_goods_sku_id` int unsigned NOT NULL DEFAULT '0',
  `priority` int NOT NULL DEFAULT '0',
  `status` enum('normal','hidden') NOT NULL DEFAULT 'normal',
  `createtime` bigint unsigned DEFAULT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_goods_substitute` (`goods_id`,`goods_sku_id`,`substitute_goods_id`,`substitute_goods_sku_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='商品替代关系';

CREATE TABLE IF NOT EXISTS `fa_shop_supplier` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(64) NOT NULL COMMENT '供应商编码',
  `name` varchar(150) NOT NULL COMMENT '供应商名称',
  `company_name` varchar(200) NOT NULL DEFAULT '' COMMENT '主体名称',
  `contact_name` varchar(60) NOT NULL DEFAULT '' COMMENT '联系人',
  `contact_mobile` varchar(30) NOT NULL DEFAULT '' COMMENT '联系电话',
  `fulfillment_mode` enum('PLATFORM_WAREHOUSE','SUPPLIER_DIRECT','MIXED') NOT NULL DEFAULT 'SUPPLIER_DIRECT' COMMENT '履约模式',
  `settlement_mode` varchar(50) NOT NULL DEFAULT '' COMMENT '结算方式',
  `api_type` enum('NONE','HTTP','MANUAL','FILE') NOT NULL DEFAULT 'MANUAL' COMMENT '对接方式',
  `api_config_encrypted` text COMMENT '加密接口配置',
  `priority` int NOT NULL DEFAULT '0' COMMENT '默认优先级',
  `status` enum('normal','disabled') NOT NULL DEFAULT 'normal',
  `createtime` bigint unsigned DEFAULT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_code` (`code`),
  KEY `idx_status_priority` (`status`,`priority`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='供应商';

CREATE TABLE IF NOT EXISTS `fa_shop_supplier_sku` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `supplier_id` int unsigned NOT NULL COMMENT '供应商ID',
  `goods_id` int unsigned NOT NULL COMMENT '商品ID',
  `goods_sku_id` int unsigned NOT NULL DEFAULT '0' COMMENT 'SKU ID，0表示无规格商品',
  `supplier_goods_code` varchar(100) NOT NULL DEFAULT '' COMMENT '供应商商品编码',
  `supplier_sku_code` varchar(100) NOT NULL DEFAULT '' COMMENT '供应商SKU编码',
  `supply_price` decimal(12,2) unsigned NOT NULL DEFAULT '0.00' COMMENT '供货价',
  `min_order_qty` int unsigned NOT NULL DEFAULT '1' COMMENT '起订量',
  `delivery_days` int unsigned NOT NULL DEFAULT '0' COMMENT '预计配送天数',
  `fulfillment_mode` enum('PLATFORM_WAREHOUSE','SUPPLIER_DIRECT') NOT NULL DEFAULT 'SUPPLIER_DIRECT',
  `priority` int NOT NULL DEFAULT '0',
  `last_sync_time` bigint unsigned DEFAULT NULL,
  `sync_status` enum('PENDING','SUCCESS','FAILED') NOT NULL DEFAULT 'PENDING',
  `status` enum('normal','paused','offline') NOT NULL DEFAULT 'normal',
  `createtime` bigint unsigned DEFAULT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_supplier_goods_sku` (`supplier_id`,`goods_id`,`goods_sku_id`),
  KEY `idx_goods_sku_status` (`goods_id`,`goods_sku_id`,`status`),
  KEY `idx_supplier_code` (`supplier_id`,`supplier_sku_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='供应商SKU供货关系';

CREATE TABLE IF NOT EXISTS `fa_shop_supplier_delivery_region` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `supplier_id` int unsigned NOT NULL,
  `province_id` int unsigned NOT NULL DEFAULT '0',
  `city_id` int unsigned NOT NULL DEFAULT '0',
  `area_id` int unsigned NOT NULL DEFAULT '0',
  `shipping_fee` decimal(12,2) unsigned NOT NULL DEFAULT '0.00',
  `free_shipping_amount` decimal(12,2) unsigned NOT NULL DEFAULT '0.00',
  `delivery_days` int unsigned NOT NULL DEFAULT '0',
  `status` enum('normal','disabled') NOT NULL DEFAULT 'normal',
  `createtime` bigint unsigned DEFAULT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_supplier_region` (`supplier_id`,`province_id`,`city_id`,`area_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='供应商配送区域';

CREATE TABLE IF NOT EXISTS `fa_shop_supplier_sync_log` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `supplier_id` int unsigned NOT NULL,
  `sync_type` enum('PRODUCT','PRICE','STOCK','DELIVERY','ORDER','AFTERSALE') NOT NULL,
  `biz_key` varchar(150) NOT NULL DEFAULT '',
  `request_id` varchar(100) NOT NULL DEFAULT '',
  `request_json` json DEFAULT NULL,
  `response_json` json DEFAULT NULL,
  `status` enum('SUCCESS','FAILED') NOT NULL,
  `error_message` varchar(1000) NOT NULL DEFAULT '',
  `retry_count` int unsigned NOT NULL DEFAULT '0',
  `createtime` bigint unsigned NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_supplier_type_time` (`supplier_id`,`sync_type`,`createtime`),
  KEY `idx_status_time` (`status`,`createtime`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='供应商同步日志';

CREATE TABLE IF NOT EXISTS `fa_shop_warehouse` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `code` varchar(64) NOT NULL COMMENT '仓库编码',
  `name` varchar(120) NOT NULL COMMENT '仓库名称',
  `owner_type` enum('PLATFORM','SUPPLIER') NOT NULL DEFAULT 'PLATFORM',
  `owner_id` int unsigned NOT NULL DEFAULT '0' COMMENT '供应商ID，平台仓为0',
  `warehouse_type` enum('PHYSICAL','VIRTUAL_DIRECT') NOT NULL DEFAULT 'PHYSICAL',
  `province_id` int unsigned NOT NULL DEFAULT '0',
  `city_id` int unsigned NOT NULL DEFAULT '0',
  `area_id` int unsigned NOT NULL DEFAULT '0',
  `address` varchar(255) NOT NULL DEFAULT '',
  `contact_name` varchar(60) NOT NULL DEFAULT '',
  `contact_mobile` varchar(30) NOT NULL DEFAULT '',
  `status` enum('normal','disabled') NOT NULL DEFAULT 'normal',
  `createtime` bigint unsigned DEFAULT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_code` (`code`),
  KEY `idx_owner` (`owner_type`,`owner_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='仓库';

CREATE TABLE IF NOT EXISTS `fa_shop_warehouse_sku` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `warehouse_id` int unsigned NOT NULL,
  `supplier_id` int unsigned NOT NULL DEFAULT '0',
  `supplier_sku_id` int unsigned NOT NULL DEFAULT '0',
  `goods_id` int unsigned NOT NULL,
  `goods_sku_id` int unsigned NOT NULL DEFAULT '0' COMMENT 'SKU ID，0表示无规格商品',
  `on_hand_qty` int unsigned NOT NULL DEFAULT '0',
  `locked_qty` int unsigned NOT NULL DEFAULT '0',
  `unavailable_qty` int unsigned NOT NULL DEFAULT '0',
  `in_transit_qty` int unsigned NOT NULL DEFAULT '0',
  `version` int unsigned NOT NULL DEFAULT '0',
  `last_sync_time` bigint unsigned DEFAULT NULL,
  `createtime` bigint unsigned DEFAULT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_warehouse_goods_sku` (`warehouse_id`,`goods_id`,`goods_sku_id`),
  KEY `idx_supplier_sku` (`supplier_id`,`supplier_sku_id`),
  KEY `idx_goods_sku` (`goods_id`,`goods_sku_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='仓库商品库存';

CREATE TABLE IF NOT EXISTS `fa_shop_stock_batch` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `warehouse_sku_id` bigint unsigned NOT NULL,
  `batch_no` varchar(100) NOT NULL,
  `production_date` date DEFAULT NULL,
  `expiry_date` date DEFAULT NULL,
  `cost_price` decimal(12,2) unsigned NOT NULL DEFAULT '0.00',
  `on_hand_qty` int unsigned NOT NULL DEFAULT '0',
  `locked_qty` int unsigned NOT NULL DEFAULT '0',
  `unavailable_qty` int unsigned NOT NULL DEFAULT '0',
  `status` enum('normal','expired','disabled') NOT NULL DEFAULT 'normal',
  `createtime` bigint unsigned DEFAULT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_warehouse_sku_batch` (`warehouse_sku_id`,`batch_no`),
  KEY `idx_expiry` (`expiry_date`,`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='库存批次';

CREATE TABLE IF NOT EXISTS `fa_shop_stock_reservation` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reservation_sn` varchar(64) NOT NULL,
  `biz_key` varchar(100) NOT NULL COMMENT '幂等业务键',
  `order_sn` varchar(50) NOT NULL DEFAULT '',
  `supplier_order_sn` varchar(64) NOT NULL DEFAULT '',
  `warehouse_sku_id` bigint unsigned NOT NULL,
  `goods_id` int unsigned NOT NULL,
  `goods_sku_id` int unsigned NOT NULL DEFAULT '0',
  `quantity` int unsigned NOT NULL,
  `status` enum('LOCKED','RELEASED','DEDUCTED') NOT NULL DEFAULT 'LOCKED',
  `expiretime` bigint unsigned DEFAULT NULL,
  `released_at` bigint unsigned DEFAULT NULL,
  `deducted_at` bigint unsigned DEFAULT NULL,
  `createtime` bigint unsigned NOT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_reservation_sn` (`reservation_sn`),
  UNIQUE KEY `uk_biz_warehouse_sku` (`biz_key`,`warehouse_sku_id`),
  KEY `idx_order_status` (`order_sn`,`status`),
  KEY `idx_expire_status` (`expiretime`,`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='库存锁定';

CREATE TABLE IF NOT EXISTS `fa_shop_stock_flow` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `flow_sn` varchar(64) NOT NULL,
  `warehouse_sku_id` bigint unsigned NOT NULL,
  `supplier_id` int unsigned NOT NULL DEFAULT '0',
  `warehouse_id` int unsigned NOT NULL,
  `goods_id` int unsigned NOT NULL,
  `goods_sku_id` int unsigned NOT NULL DEFAULT '0',
  `biz_type` varchar(40) NOT NULL,
  `biz_no` varchar(100) NOT NULL DEFAULT '',
  `change_on_hand` int NOT NULL DEFAULT '0',
  `change_locked` int NOT NULL DEFAULT '0',
  `before_on_hand` int unsigned NOT NULL,
  `after_on_hand` int unsigned NOT NULL,
  `before_locked` int unsigned NOT NULL,
  `after_locked` int unsigned NOT NULL,
  `operator_type` varchar(30) NOT NULL DEFAULT 'SYSTEM',
  `operator_id` int unsigned NOT NULL DEFAULT '0',
  `remark` varchar(500) NOT NULL DEFAULT '',
  `createtime` bigint unsigned NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_flow_sn` (`flow_sn`),
  KEY `idx_warehouse_sku_time` (`warehouse_sku_id`,`createtime`),
  KEY `idx_biz` (`biz_type`,`biz_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='库存流水';

CREATE TABLE IF NOT EXISTS `fa_shop_shopping_list` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `list_sn` varchar(64) NOT NULL,
  `user_id` int unsigned NOT NULL,
  `menu_version_id` varchar(100) NOT NULL,
  `list_version` int unsigned NOT NULL DEFAULT '1',
  `source_hash` char(64) NOT NULL DEFAULT '',
  `status` enum('DRAFT','CONFIRMED','ORDERED','EXPIRED') NOT NULL DEFAULT 'DRAFT',
  `confirmed_at` bigint unsigned DEFAULT NULL,
  `createtime` bigint unsigned NOT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_list_sn` (`list_sn`),
  UNIQUE KEY `uk_user_menu_version` (`user_id`,`menu_version_id`,`list_version`),
  KEY `idx_user_status` (`user_id`,`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='菜单购物清单';

CREATE TABLE IF NOT EXISTS `fa_shop_shopping_list_item` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `shopping_list_id` bigint unsigned NOT NULL,
  `ingredient_id` int unsigned NOT NULL,
  `required_quantity` decimal(14,3) unsigned NOT NULL,
  `home_quantity` decimal(14,3) unsigned NOT NULL DEFAULT '0.000',
  `net_quantity` decimal(14,3) unsigned NOT NULL,
  `unit` varchar(20) NOT NULL,
  `source_refs_json` json DEFAULT NULL,
  `constraint_result_json` json DEFAULT NULL,
  `selected_goods_id` int unsigned NOT NULL DEFAULT '0',
  `selected_goods_sku_id` int unsigned NOT NULL DEFAULT '0',
  `selected_supplier_id` int unsigned NOT NULL DEFAULT '0',
  `purchase_quantity` int unsigned NOT NULL DEFAULT '0',
  `covered_quantity` decimal(14,3) unsigned NOT NULL DEFAULT '0.000',
  `shortage_quantity` decimal(14,3) unsigned NOT NULL DEFAULT '0.000',
  `excess_quantity` decimal(14,3) unsigned NOT NULL DEFAULT '0.000',
  `purchase_mode` enum('PLATFORM','SELF_PURCHASE','SKIP') NOT NULL DEFAULT 'PLATFORM',
  `substitution_confirmed` tinyint unsigned NOT NULL DEFAULT '0',
  `createtime` bigint unsigned NOT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_list` (`shopping_list_id`),
  KEY `idx_ingredient` (`ingredient_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='购物清单明细';

CREATE TABLE IF NOT EXISTS `fa_shop_order_ext` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `order_id` int unsigned NOT NULL,
  `order_sn` varchar(50) NOT NULL,
  `user_id` int unsigned NOT NULL,
  `idempotency_key` varchar(100) NOT NULL,
  `shopping_list_id` bigint unsigned NOT NULL DEFAULT '0',
  `shopping_list_version` int unsigned NOT NULL DEFAULT '0',
  `biz_status` varchar(40) NOT NULL DEFAULT 'PENDING_PAYMENT',
  `fulfillment_status` varchar(40) NOT NULL DEFAULT 'PENDING',
  `refund_status` varchar(40) NOT NULL DEFAULT 'NONE',
  `trace_id` varchar(64) NOT NULL DEFAULT '',
  `version` int unsigned NOT NULL DEFAULT '0',
  `createtime` bigint unsigned NOT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_order_id` (`order_id`),
  UNIQUE KEY `uk_order_sn` (`order_sn`),
  UNIQUE KEY `uk_user_idempotency` (`user_id`,`idempotency_key`),
  KEY `idx_user_status` (`user_id`,`biz_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单扩展及幂等控制';

CREATE TABLE IF NOT EXISTS `fa_shop_order_supplier` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `supplier_order_sn` varchar(64) NOT NULL,
  `order_id` int unsigned NOT NULL,
  `order_sn` varchar(50) NOT NULL,
  `supplier_id` int unsigned NOT NULL,
  `warehouse_id` int unsigned NOT NULL,
  `fulfillment_mode` enum('PLATFORM_WAREHOUSE','SUPPLIER_DIRECT') NOT NULL,
  `goods_amount` decimal(12,2) unsigned NOT NULL DEFAULT '0.00',
  `shipping_fee` decimal(12,2) unsigned NOT NULL DEFAULT '0.00',
  `supply_amount` decimal(12,2) unsigned NOT NULL DEFAULT '0.00',
  `status` varchar(40) NOT NULL DEFAULT 'PENDING_ASSIGN',
  `accepted_at` bigint unsigned DEFAULT NULL,
  `preparing_at` bigint unsigned DEFAULT NULL,
  `shipping_at` bigint unsigned DEFAULT NULL,
  `completed_at` bigint unsigned DEFAULT NULL,
  `cancelled_at` bigint unsigned DEFAULT NULL,
  `createtime` bigint unsigned NOT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_supplier_order_sn` (`supplier_order_sn`),
  UNIQUE KEY `uk_order_supplier_warehouse` (`order_id`,`supplier_id`,`warehouse_id`),
  KEY `idx_supplier_status` (`supplier_id`,`status`),
  KEY `idx_order_sn` (`order_sn`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='供应商履约子单';

CREATE TABLE IF NOT EXISTS `fa_shop_order_goods_ext` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `order_goods_id` int unsigned NOT NULL,
  `supplier_order_id` bigint unsigned NOT NULL,
  `supplier_id` int unsigned NOT NULL,
  `supplier_sku_id` int unsigned NOT NULL,
  `warehouse_id` int unsigned NOT NULL,
  `shopping_list_item_id` bigint unsigned NOT NULL DEFAULT '0',
  `ingredient_id` int unsigned NOT NULL DEFAULT '0',
  `supply_price` decimal(12,2) unsigned NOT NULL DEFAULT '0.00',
  `goods_snapshot_json` json NOT NULL,
  `delivery_snapshot_json` json DEFAULT NULL,
  `shipped_quantity` int unsigned NOT NULL DEFAULT '0',
  `refunded_quantity` int unsigned NOT NULL DEFAULT '0',
  `createtime` bigint unsigned NOT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_order_goods` (`order_goods_id`),
  KEY `idx_supplier_order` (`supplier_order_id`),
  KEY `idx_supplier` (`supplier_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单商品供应商及快照扩展';

CREATE TABLE IF NOT EXISTS `fa_shop_order_snapshot` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `order_id` int unsigned NOT NULL,
  `order_sn` varchar(50) NOT NULL,
  `snapshot_type` enum('CHECKOUT','ORDER','PAYMENT','FULFILLMENT','AFTERSALE') NOT NULL,
  `snapshot_json` json NOT NULL,
  `createtime` bigint unsigned NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_order_type` (`order_id`,`snapshot_type`),
  KEY `idx_order_sn` (`order_sn`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单不可变快照';

CREATE TABLE IF NOT EXISTS `fa_shop_order_status_log` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `order_id` int unsigned NOT NULL,
  `order_sn` varchar(50) NOT NULL,
  `supplier_order_id` bigint unsigned NOT NULL DEFAULT '0',
  `status_type` enum('ORDER','PAYMENT','FULFILLMENT','REFUND','SUPPLIER_ORDER') NOT NULL,
  `from_status` varchar(40) NOT NULL DEFAULT '',
  `to_status` varchar(40) NOT NULL,
  `biz_no` varchar(100) NOT NULL DEFAULT '',
  `operator_type` varchar(30) NOT NULL DEFAULT 'SYSTEM',
  `operator_id` int unsigned NOT NULL DEFAULT '0',
  `remark` varchar(500) NOT NULL DEFAULT '',
  `createtime` bigint unsigned NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_order_time` (`order_id`,`createtime`),
  KEY `idx_supplier_order` (`supplier_order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单状态日志';

CREATE TABLE IF NOT EXISTS `fa_shop_order_shipment` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `shipment_sn` varchar(64) NOT NULL,
  `supplier_order_id` bigint unsigned NOT NULL,
  `order_id` int unsigned NOT NULL,
  `order_sn` varchar(50) NOT NULL,
  `shipper_code` varchar(50) NOT NULL DEFAULT '',
  `shipper_name` varchar(100) NOT NULL DEFAULT '',
  `logistic_code` varchar(100) NOT NULL DEFAULT '',
  `status` enum('PENDING','SHIPPED','RECEIVED','CANCELLED') NOT NULL DEFAULT 'PENDING',
  `shipping_at` bigint unsigned DEFAULT NULL,
  `received_at` bigint unsigned DEFAULT NULL,
  `createtime` bigint unsigned NOT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_shipment_sn` (`shipment_sn`),
  KEY `idx_supplier_order` (`supplier_order_id`),
  KEY `idx_logistic_code` (`logistic_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单物流包裹';

CREATE TABLE IF NOT EXISTS `fa_shop_order_shipment_item` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `shipment_id` bigint unsigned NOT NULL,
  `order_goods_id` int unsigned NOT NULL,
  `quantity` int unsigned NOT NULL,
  `createtime` bigint unsigned NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_shipment_goods` (`shipment_id`,`order_goods_id`),
  KEY `idx_order_goods` (`order_goods_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='物流包裹商品';

CREATE TABLE IF NOT EXISTS `fa_shop_payment_transaction` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `payment_sn` varchar(64) NOT NULL,
  `order_id` int unsigned NOT NULL,
  `order_sn` varchar(50) NOT NULL,
  `channel` varchar(30) NOT NULL,
  `channel_transaction_id` varchar(100) NOT NULL DEFAULT '',
  `amount` decimal(12,2) unsigned NOT NULL,
  `status` enum('CREATED','PENDING','SUCCESS','FAILED','CLOSED','REFUNDING','REFUNDED') NOT NULL DEFAULT 'CREATED',
  `request_json` json DEFAULT NULL,
  `callback_json` json DEFAULT NULL,
  `paid_at` bigint unsigned DEFAULT NULL,
  `createtime` bigint unsigned NOT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_payment_sn` (`payment_sn`),
  UNIQUE KEY `uk_channel_transaction` (`channel`,`channel_transaction_id`),
  KEY `idx_order_status` (`order_id`,`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='支付及回调幂等记录';

CREATE TABLE IF NOT EXISTS `fa_shop_aftersales_ext` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `aftersales_id` int unsigned NOT NULL,
  `supplier_order_id` bigint unsigned NOT NULL,
  `supplier_id` int unsigned NOT NULL,
  `warehouse_id` int unsigned NOT NULL,
  `return_status` enum('NONE','PENDING','SHIPPED','RECEIVED','ACCEPTED','REJECTED') NOT NULL DEFAULT 'NONE',
  `restock_quantity` int unsigned NOT NULL DEFAULT '0',
  `idempotency_key` varchar(100) NOT NULL DEFAULT '',
  `createtime` bigint unsigned NOT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_aftersales` (`aftersales_id`),
  UNIQUE KEY `uk_supplier_idempotency` (`supplier_id`,`idempotency_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='售后供应商及入库扩展';

CREATE TABLE IF NOT EXISTS `fa_shop_order_substitution` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `order_id` int unsigned NOT NULL,
  `order_goods_id` int unsigned NOT NULL,
  `from_supplier_id` int unsigned NOT NULL,
  `from_goods_id` int unsigned NOT NULL,
  `from_goods_sku_id` int unsigned NOT NULL DEFAULT '0',
  `to_supplier_id` int unsigned NOT NULL DEFAULT '0',
  `to_goods_id` int unsigned NOT NULL,
  `to_goods_sku_id` int unsigned NOT NULL DEFAULT '0',
  `constraint_result_json` json DEFAULT NULL,
  `price_difference` decimal(12,2) NOT NULL DEFAULT '0.00',
  `status` enum('PENDING_CONFIRM','CONFIRMED','REJECTED','EXPIRED') NOT NULL DEFAULT 'PENDING_CONFIRM',
  `confirmed_at` bigint unsigned DEFAULT NULL,
  `createtime` bigint unsigned NOT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_order_status` (`order_id`,`status`),
  KEY `idx_order_goods` (`order_goods_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='订单缺货替代确认';

INSERT INTO `fa_shop_warehouse`
  (`code`,`name`,`owner_type`,`owner_id`,`warehouse_type`,`status`,`createtime`,`updatetime`)
VALUES
  ('PLATFORM-DEFAULT','平台默认仓','PLATFORM',0,'PHYSICAL','normal',UNIX_TIMESTAMP(),UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `name`=VALUES(`name`),`updatetime`=VALUES(`updatetime`);

INSERT IGNORE INTO `fa_shop_sku_ext`
  (`goods_id`,`goods_sku_id`,`unit`,`net_unit`,`createtime`,`updatetime`)
SELECT g.id, COALESCE(s.id,0), '份', 'g', UNIX_TIMESTAMP(), UNIX_TIMESTAMP()
FROM `fa_shop_goods` g
LEFT JOIN `fa_shop_goods_sku` s ON s.goods_id = g.id;

INSERT IGNORE INTO `fa_shop_warehouse_sku`
  (`warehouse_id`,`supplier_id`,`supplier_sku_id`,`goods_id`,`goods_sku_id`,`on_hand_qty`,`locked_qty`,`unavailable_qty`,`in_transit_qty`,`version`,`createtime`,`updatetime`)
SELECT w.id, 0, 0, g.id, COALESCE(s.id,0), COALESCE(s.stocks,g.stocks,0), 0, 0, 0, 0, UNIX_TIMESTAMP(), UNIX_TIMESTAMP()
FROM `fa_shop_goods` g
LEFT JOIN `fa_shop_goods_sku` s ON s.goods_id = g.id
JOIN `fa_shop_warehouse` w ON w.code = 'PLATFORM-DEFAULT';

INSERT IGNORE INTO `fa_shop_stock_flow`
  (`flow_sn`,`warehouse_sku_id`,`supplier_id`,`warehouse_id`,`goods_id`,`goods_sku_id`,`biz_type`,`biz_no`,`change_on_hand`,`change_locked`,`before_on_hand`,`after_on_hand`,`before_locked`,`after_locked`,`operator_type`,`operator_id`,`remark`,`createtime`)
SELECT CONCAT('INIT-',ws.id), ws.id, ws.supplier_id, ws.warehouse_id, ws.goods_id, ws.goods_sku_id,
       'INITIAL_IN', '20260923_001', ws.on_hand_qty, 0, 0, ws.on_hand_qty, 0, 0,
       'MIGRATION', 0, '从Shop原库存迁移的期初库存', UNIX_TIMESTAMP()
FROM `fa_shop_warehouse_sku` ws;

INSERT INTO `fa_shop_schema_migration` (`version`,`description`,`applied_at`)
VALUES ('20260923_001','商品、食材、多供应商、库存、购物清单、订单履约核心结构',UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `description`=VALUES(`description`);


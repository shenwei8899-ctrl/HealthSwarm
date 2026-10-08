SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `fa_shop_supplier_sync_job` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `job_sn` varchar(64) NOT NULL,
  `supplier_id` int unsigned NOT NULL,
  `sync_type` enum('PRODUCT','PRICE','STOCK','DELIVERY','ORDER','ACCEPT','SHIPPING','AFTERSALE') NOT NULL,
  `direction` enum('INBOUND','OUTBOUND') NOT NULL DEFAULT 'INBOUND',
  `biz_key` varchar(150) NOT NULL,
  `payload_json` json NOT NULL,
  `response_json` json DEFAULT NULL,
  `status` enum('PENDING','RUNNING','SUCCESS','FAILED','MANUAL_REQUIRED') NOT NULL DEFAULT 'PENDING',
  `attempts` int unsigned NOT NULL DEFAULT '0',
  `max_attempts` int unsigned NOT NULL DEFAULT '5',
  `next_retry_at` bigint unsigned DEFAULT NULL,
  `last_error` varchar(1000) NOT NULL DEFAULT '',
  `completed_at` bigint unsigned DEFAULT NULL,
  `createtime` bigint unsigned NOT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_job_sn` (`job_sn`),
  UNIQUE KEY `uk_supplier_type_biz` (`supplier_id`,`sync_type`,`biz_key`),
  KEY `idx_status_retry` (`status`,`next_retry_at`),
  KEY `idx_supplier_time` (`supplier_id`,`createtime`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='供应商同步任务与重试队列';

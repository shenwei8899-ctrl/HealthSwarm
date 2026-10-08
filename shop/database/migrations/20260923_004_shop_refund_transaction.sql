SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `fa_shop_refund_transaction` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `refund_sn` varchar(64) NOT NULL COMMENT '稳定退款幂等单号',
  `aftersales_id` int unsigned NOT NULL,
  `order_id` int unsigned NOT NULL,
  `order_sn` varchar(50) NOT NULL,
  `channel` varchar(30) NOT NULL DEFAULT 'manual',
  `amount` decimal(12,2) unsigned NOT NULL,
  `local_action` enum('REFUND_ONLY','RETURN_REFUND') NOT NULL,
  `local_payload_json` json DEFAULT NULL,
  `external_required` tinyint unsigned NOT NULL DEFAULT '0',
  `status` enum('CREATED','PROCESSING','EXTERNAL_SUCCESS','COMPLETED','FAILED') NOT NULL DEFAULT 'CREATED',
  `gateway_refund_id` varchar(100) NOT NULL DEFAULT '',
  `request_json` json DEFAULT NULL,
  `response_json` json DEFAULT NULL,
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `error_message` varchar(1000) NOT NULL DEFAULT '',
  `next_retry_at` bigint unsigned DEFAULT NULL,
  `external_succeeded_at` bigint unsigned DEFAULT NULL,
  `completed_at` bigint unsigned DEFAULT NULL,
  `createtime` bigint unsigned NOT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_refund_sn` (`refund_sn`),
  UNIQUE KEY `uk_aftersales` (`aftersales_id`),
  KEY `idx_status_retry` (`status`,`next_retry_at`),
  KEY `idx_order` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='支付退款与本地售后补偿事务';

INSERT INTO `fa_shop_schema_migration` (`version`,`description`,`applied_at`)
VALUES ('20260923_004','支付退款幂等与本地售后补偿事务',UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `description`=VALUES(`description`);

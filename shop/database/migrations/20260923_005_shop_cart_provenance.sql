SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `fa_shop_cart_ext` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `cart_id` int unsigned NOT NULL,
  `user_id` int unsigned NOT NULL,
  `shopping_list_id` bigint unsigned NOT NULL,
  `shopping_list_item_id` bigint unsigned NOT NULL,
  `ingredient_id` int unsigned NOT NULL,
  `preferred_supplier_id` int unsigned NOT NULL DEFAULT '0',
  `selected_supplier_id` int unsigned NOT NULL DEFAULT '0',
  `shopping_list_version` int unsigned NOT NULL,
  `source_hash` char(64) NOT NULL,
  `createtime` bigint unsigned NOT NULL,
  `updatetime` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_cart_id` (`cart_id`),
  UNIQUE KEY `uk_user_list_item` (`user_id`,`shopping_list_item_id`),
  KEY `idx_shopping_list` (`shopping_list_id`),
  KEY `idx_ingredient` (`ingredient_id`),
  KEY `idx_selected_supplier` (`selected_supplier_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='购物车购物清单及供应商来源';

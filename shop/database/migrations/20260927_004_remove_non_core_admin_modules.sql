SET NAMES utf8mb4;
SET SESSION group_concat_max_len = 100000;
SET @now = UNIX_TIMESTAMP();

DELETE FROM fa_auth_rule
WHERE name='shop/goods_sku/index'
   OR name REGEXP '^shop/(spec_sku|report|theme|navigation|menu|block|page|search_log|template_msg|comment|collect|coupon|coupon_condition|user_coupon|exchange|exchange_order|area)(/|$)';

-- Remove deleted permission ids from every role while preserving all remaining rights.
UPDATE fa_auth_group g
SET rules=COALESCE((
  SELECT GROUP_CONCAT(r.id ORDER BY r.id)
  FROM fa_auth_rule r
  WHERE FIND_IN_SET(r.id,g.rules)
),'')
WHERE g.rules<>'*';

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260927_004','删除非一期主链路的后台管理模块并保留共享数据及前台接口',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

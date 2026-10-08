SET NAMES utf8mb4;
SET SESSION group_concat_max_len = 100000;
SET @now = UNIX_TIMESTAMP();

DELETE FROM fa_auth_rule
WHERE name IN (
  'shop/order_pending_payment',
  'shop/order_preparing',
  'shop/order_shipping',
  'shop/order_completed',
  'shop/order_cancelled',
  'shop/order_exception'
);

-- Remove deleted menu ids from non-super-admin roles.
UPDATE fa_auth_group g
SET rules=COALESCE((
  SELECT GROUP_CONCAT(r.id ORDER BY r.id)
  FROM fa_auth_rule r
  WHERE FIND_IN_SET(r.id,g.rules)
),'')
WHERE g.rules<>'*';

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260927_009','订单状态快捷菜单合并至用户主订单页面',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

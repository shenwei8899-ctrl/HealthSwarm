SET @now = UNIX_TIMESTAMP();

UPDATE fa_auth_rule
SET ismenu = 0, updatetime = @now
WHERE name = 'shop/attribute';

INSERT INTO fa_shop_schema_migration (`version`, `description`, `applied_at`) VALUES
('20260927_001', '商品中心隐藏重复的商品类型菜单并保留底层规格模板能力', @now)
ON DUPLICATE KEY UPDATE description = VALUES(description), applied_at = VALUES(applied_at);

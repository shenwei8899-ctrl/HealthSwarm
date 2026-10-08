SET NAMES utf8mb4;
SET @now = UNIX_TIMESTAMP();

-- FastAdmin uses the wildcard rule for the unrestricted administrator group.
-- Migration 20260927_004 originally recalculated it as an empty id list.
UPDATE fa_auth_group
SET rules='*'
WHERE id=1 AND rules='';

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260927_005','恢复超级管理员通配权限并防止菜单被清空',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

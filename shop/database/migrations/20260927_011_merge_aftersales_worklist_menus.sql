SET NAMES utf8mb4;
SET SESSION group_concat_max_len = 100000;
SET @now = UNIX_TIMESTAMP();
SET @aftersale_center = (SELECT id FROM fa_auth_rule WHERE name='shop/aftersale_center' LIMIT 1);
SET @aftersales_management = (SELECT id FROM fa_auth_rule WHERE name='shop/order_aftersales' LIMIT 1);

UPDATE fa_auth_rule
SET pid=@aftersale_center,
    title='售后管理',
    icon='fa fa-reply',
    url='shop/order_aftersales/index?worklist=refund',
    remark='退款、退货、验收和售后记录统一工作台',
    ismenu=1,
    status='normal',
    weigh=80,
    updatetime=@now
WHERE id=@aftersales_management;

-- Roles that could access any previous worklist keep access to the merged entry.
UPDATE fa_auth_group g
SET rules=CONCAT_WS(',',NULLIF(g.rules,''),@aftersales_management)
WHERE g.rules<>'*'
  AND NOT FIND_IN_SET(CONVERT(@aftersales_management USING utf8mb4) COLLATE utf8mb4_general_ci,g.rules)
  AND EXISTS (
    SELECT 1
    FROM fa_auth_rule r
    WHERE r.name IN ('shop/aftersale_refund','shop/aftersale_return','shop/aftersale_inspection')
      AND FIND_IN_SET(CONVERT(r.id USING utf8mb4) COLLATE utf8mb4_general_ci,g.rules)
  );

DELETE FROM fa_auth_rule
WHERE name IN ('shop/aftersale_refund','shop/aftersale_return','shop/aftersale_inspection');

UPDATE fa_auth_group g
SET rules=COALESCE((
  SELECT GROUP_CONCAT(r.id ORDER BY r.id)
  FROM fa_auth_rule r
  WHERE FIND_IN_SET(CONVERT(r.id USING utf8mb4) COLLATE utf8mb4_general_ci,g.rules)
),'')
WHERE g.rules<>'*';

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260927_011','售后工作项合并至售后管理统一入口',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

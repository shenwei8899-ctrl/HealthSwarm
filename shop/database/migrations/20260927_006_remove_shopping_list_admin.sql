SET NAMES utf8mb4;
SET SESSION group_concat_max_len = 100000;
SET @now = UNIX_TIMESTAMP();

DELETE FROM fa_auth_rule
WHERE name='shop/shopping_list_center'
   OR name REGEXP '^shop/shopping_list(/|$)'
   OR name IN ('shop/shopping_list_matching','shop/shopping_list_exception');

UPDATE fa_auth_group g
SET rules=COALESCE((
  SELECT GROUP_CONCAT(r.id ORDER BY r.id)
  FROM fa_auth_rule r
  WHERE FIND_IN_SET(r.id,g.rules)
),'')
WHERE g.rules<>'*';

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260927_006','删除管理后台购物清单模块并保留前台数据和接口',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

SET NAMES utf8mb4;
SET SESSION group_concat_max_len = 100000;
SET @now = UNIX_TIMESTAMP();
SET @delivery_center = (SELECT id FROM fa_auth_rule WHERE name='shop/delivery_center' LIMIT 1);

INSERT INTO fa_auth_rule
(`type`,`pid`,`name`,`title`,`icon`,`url`,`condition`,`remark`,`ismenu`,`createtime`,`updatetime`,`weigh`,`status`)
VALUES
('file',@delivery_center,'shop/delivery_management','配送管理','fa fa-truck','shop/order_supplier/index?worklist=picking','','拣货、出库、物流包裹和配送异常统一工作台',1,@now,@now,80,'normal')
ON DUPLICATE KEY UPDATE pid=VALUES(pid),title=VALUES(title),icon=VALUES(icon),url=VALUES(url),remark=VALUES(remark),ismenu=1,status='normal',updatetime=@now;

SET @delivery_management = (SELECT id FROM fa_auth_rule WHERE name='shop/delivery_management' LIMIT 1);

-- Roles that could access any previous delivery entry keep access to the merged entry.
UPDATE fa_auth_group g
SET rules=CONCAT_WS(',',NULLIF(g.rules,''),@delivery_management)
WHERE g.rules<>'*'
  AND NOT FIND_IN_SET(CONVERT(@delivery_management USING utf8mb4) COLLATE utf8mb4_general_ci,g.rules)
  AND EXISTS (
    SELECT 1
    FROM fa_auth_rule r
    WHERE r.name IN ('shop/delivery_picking','shop/delivery_outbound','shop/order_shipment','shop/delivery_exception')
      AND FIND_IN_SET(CONVERT(r.id USING utf8mb4) COLLATE utf8mb4_general_ci,g.rules)
  );

DELETE FROM fa_auth_rule
WHERE name IN ('shop/delivery_picking','shop/delivery_outbound','shop/delivery_exception');

-- The package route remains available to the merged page but no longer appears separately.
UPDATE fa_auth_rule
SET ismenu=0,updatetime=@now
WHERE name='shop/order_shipment';

UPDATE fa_auth_group g
SET rules=COALESCE((
  SELECT GROUP_CONCAT(r.id ORDER BY r.id)
  FROM fa_auth_rule r
  WHERE FIND_IN_SET(CONVERT(r.id USING utf8mb4) COLLATE utf8mb4_general_ci,g.rules)
),'')
WHERE g.rules<>'*';

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260927_010','配送工作项合并至配送管理统一入口',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

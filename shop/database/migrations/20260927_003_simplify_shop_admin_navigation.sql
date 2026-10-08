SET NAMES utf8mb4;
SET @now = UNIX_TIMESTAMP();
SET @shop = (SELECT id FROM fa_auth_rule WHERE name='shop' LIMIT 1);
SET @product = (SELECT id FROM fa_auth_rule WHERE name='shop/product_center' LIMIT 1);
SET @supplier = (SELECT id FROM fa_auth_rule WHERE name='shop/supplier_center' LIMIT 1);
SET @inventory = (SELECT id FROM fa_auth_rule WHERE name='shop/inventory_center' LIMIT 1);
SET @shopping = (SELECT id FROM fa_auth_rule WHERE name='shop/shopping_list_center' LIMIT 1);
SET @orders = (SELECT id FROM fa_auth_rule WHERE name='shop/order_center' LIMIT 1);
SET @delivery = (SELECT id FROM fa_auth_rule WHERE name='shop/delivery_center' LIMIT 1);
SET @aftersale = (SELECT id FROM fa_auth_rule WHERE name='shop/aftersale_center' LIMIT 1);
SET @reports = (SELECT id FROM fa_auth_rule WHERE name='shop/report_center' LIMIT 1);

-- The root contains only the eight business centers. Legacy mall, technical and
-- mobile-decoration modules remain available to dependent routes but not as menus.
UPDATE fa_auth_rule SET ismenu=0,updatetime=@now WHERE pid=@shop;
UPDATE fa_auth_rule SET ismenu=1,status='normal',updatetime=@now
WHERE name IN (
  'shop/product_center','shop/supplier_center','shop/inventory_center','shop/shopping_list_center',
  'shop/order_center','shop/delivery_center','shop/aftersale_center','shop/report_center'
);

UPDATE fa_auth_rule SET ismenu=0,updatetime=@now
WHERE pid IN (@product,@supplier,@inventory,@shopping,@orders,@delivery,@aftersale,@reports);

UPDATE fa_auth_rule SET ismenu=1,status='normal',updatetime=@now
WHERE name IN (
  'shop/goods','shop/category','shop/ingredient','shop/ingredient_product_map','shop/brand',
  'shop/supplier','shop/supplier_sku','shop/supplier_price','shop/supplier_delivery_region','shop/supplier_sync_log','shop/supplier_reconciliation',
  'shop/warehouse','shop/warehouse_sku','shop/stock_reservation','shop/stock_flow','shop/inventory_adjustment','shop/low_stock','shop/stock_batch',
  'shop/shopping_list','shop/shopping_list_matching','shop/shopping_list_exception',
  'shop/order','shop/order_supplier','shop/order_pending_payment','shop/order_preparing','shop/order_shipping','shop/order_completed','shop/order_cancelled','shop/order_exception',
  'shop/delivery_picking','shop/delivery_outbound','shop/order_shipment','shop/delivery_exception',
  'shop/aftersale_refund','shop/aftersale_return','shop/aftersale_inspection','shop/order_aftersales',
  'shop/report_product_sales','shop/report_orders','shop/report_supplier_fulfillment','shop/report_inventory','shop/report_refunds','shop/expiry_alert'
);

UPDATE fa_auth_rule SET weigh=80,updatetime=@now WHERE name='shop/goods';
UPDATE fa_auth_rule SET weigh=79,updatetime=@now WHERE name='shop/category';
UPDATE fa_auth_rule SET weigh=78,updatetime=@now WHERE name='shop/ingredient';
UPDATE fa_auth_rule SET weigh=77,updatetime=@now WHERE name='shop/ingredient_product_map';
UPDATE fa_auth_rule SET weigh=76,updatetime=@now WHERE name='shop/brand';

UPDATE fa_auth_rule SET weigh=80,updatetime=@now WHERE name='shop/supplier';
UPDATE fa_auth_rule SET weigh=79,updatetime=@now WHERE name='shop/supplier_sku';
UPDATE fa_auth_rule SET weigh=78,updatetime=@now WHERE name='shop/supplier_price';
UPDATE fa_auth_rule SET weigh=77,updatetime=@now WHERE name='shop/supplier_delivery_region';
UPDATE fa_auth_rule SET weigh=76,updatetime=@now WHERE name='shop/supplier_sync_log';
UPDATE fa_auth_rule SET weigh=75,updatetime=@now WHERE name='shop/supplier_reconciliation';

UPDATE fa_auth_rule SET weigh=80,updatetime=@now WHERE name='shop/warehouse';
UPDATE fa_auth_rule SET weigh=79,updatetime=@now WHERE name='shop/warehouse_sku';
UPDATE fa_auth_rule SET weigh=78,updatetime=@now WHERE name='shop/stock_reservation';
UPDATE fa_auth_rule SET weigh=77,updatetime=@now WHERE name='shop/stock_flow';
UPDATE fa_auth_rule SET weigh=76,updatetime=@now WHERE name='shop/inventory_adjustment';
UPDATE fa_auth_rule SET weigh=75,updatetime=@now WHERE name='shop/low_stock';
UPDATE fa_auth_rule SET weigh=74,updatetime=@now WHERE name='shop/stock_batch';

UPDATE fa_auth_rule SET weigh=80,updatetime=@now WHERE name='shop/shopping_list';
UPDATE fa_auth_rule SET weigh=79,updatetime=@now WHERE name='shop/shopping_list_matching';
UPDATE fa_auth_rule SET weigh=78,updatetime=@now WHERE name='shop/shopping_list_exception';

UPDATE fa_auth_rule SET weigh=80,updatetime=@now WHERE name='shop/order';
UPDATE fa_auth_rule SET weigh=79,updatetime=@now WHERE name='shop/order_supplier';
UPDATE fa_auth_rule SET weigh=78,updatetime=@now WHERE name='shop/order_pending_payment';
UPDATE fa_auth_rule SET weigh=77,updatetime=@now WHERE name='shop/order_preparing';
UPDATE fa_auth_rule SET weigh=76,updatetime=@now WHERE name='shop/order_shipping';
UPDATE fa_auth_rule SET weigh=75,updatetime=@now WHERE name='shop/order_completed';
UPDATE fa_auth_rule SET weigh=74,updatetime=@now WHERE name='shop/order_cancelled';
UPDATE fa_auth_rule SET weigh=73,updatetime=@now WHERE name='shop/order_exception';

UPDATE fa_auth_rule SET weigh=80,updatetime=@now WHERE name='shop/delivery_picking';
UPDATE fa_auth_rule SET weigh=79,updatetime=@now WHERE name='shop/delivery_outbound';
UPDATE fa_auth_rule SET weigh=78,updatetime=@now WHERE name='shop/order_shipment';
UPDATE fa_auth_rule SET weigh=77,updatetime=@now WHERE name='shop/delivery_exception';

UPDATE fa_auth_rule SET weigh=80,updatetime=@now WHERE name='shop/aftersale_refund';
UPDATE fa_auth_rule SET weigh=79,updatetime=@now WHERE name='shop/aftersale_return';
UPDATE fa_auth_rule SET weigh=78,updatetime=@now WHERE name='shop/aftersale_inspection';
UPDATE fa_auth_rule SET weigh=77,updatetime=@now WHERE name='shop/order_aftersales';

UPDATE fa_auth_rule SET weigh=80,updatetime=@now WHERE name='shop/report_product_sales';
UPDATE fa_auth_rule SET weigh=79,updatetime=@now WHERE name='shop/report_orders';
UPDATE fa_auth_rule SET weigh=78,updatetime=@now WHERE name='shop/report_supplier_fulfillment';
UPDATE fa_auth_rule SET weigh=77,updatetime=@now WHERE name='shop/report_inventory';
UPDATE fa_auth_rule SET weigh=76,updatetime=@now WHERE name='shop/report_refunds';
UPDATE fa_auth_rule SET weigh=75,updatetime=@now WHERE name='shop/expiry_alert';

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260927_003','商城后台收敛为八个业务中心并隐藏技术及旧商城模块',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

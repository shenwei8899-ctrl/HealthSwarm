SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS=0;
SET @now = UNIX_TIMESTAMP();

-- The seed is rerunnable while it is being deployed: only MOCK-prefixed data is replaced.
DELETE FROM fa_shop_refund_transaction WHERE order_sn LIKE 'MOCK-ORD-%';
DELETE FROM fa_shop_payment_transaction WHERE order_sn LIKE 'MOCK-ORD-%';
DELETE FROM fa_shop_aftersales_inspection WHERE biz_no LIKE 'MOCK-%';
DELETE FROM fa_shop_aftersales_ext WHERE idempotency_key LIKE 'MOCK-%';
DELETE FROM fa_shop_order_aftersales WHERE order_id IN (SELECT id FROM fa_shop_order WHERE order_sn LIKE 'MOCK-ORD-%');
DELETE FROM fa_shop_order_shipment_item WHERE shipment_id IN (SELECT id FROM fa_shop_order_shipment WHERE order_sn LIKE 'MOCK-ORD-%');
DELETE FROM fa_shop_order_shipment WHERE order_sn LIKE 'MOCK-ORD-%';
DELETE FROM fa_shop_stock_reservation WHERE order_sn LIKE 'MOCK-ORD-%';
DELETE FROM fa_shop_order_status_log WHERE order_sn LIKE 'MOCK-ORD-%';
DELETE FROM fa_shop_order_supplier WHERE order_sn LIKE 'MOCK-ORD-%';
DELETE FROM fa_shop_order_snapshot WHERE order_sn LIKE 'MOCK-ORD-%';
DELETE FROM fa_shop_order_ext WHERE order_sn LIKE 'MOCK-ORD-%';
DELETE FROM fa_shop_order_action WHERE order_sn LIKE 'MOCK-ORD-%';
DELETE FROM fa_shop_order_goods WHERE order_sn LIKE 'MOCK-ORD-%';
DELETE FROM fa_shop_order WHERE order_sn LIKE 'MOCK-ORD-%';
DELETE FROM fa_shop_supplier_sync_log WHERE biz_key LIKE 'MOCK-%';
DELETE FROM fa_shop_supplier_reconciliation WHERE reconciliation_sn LIKE 'MOCK-REC-%';
DELETE FROM fa_shop_stock_flow WHERE flow_sn LIKE 'MOCK-LOW-STOCK-%';
DELETE FROM fa_shop_brand WHERE name IN ('演示-谷物优选','演示-鲜食农场','演示-家庭乳品');

SET @mock_user=COALESCE((SELECT id FROM fa_user ORDER BY id LIMIT 1),1);
SET @fresh_supplier=(SELECT id FROM fa_shop_supplier WHERE code='MOCK_SUPPLIER_FRESH' LIMIT 1);
SET @pantry_supplier=(SELECT id FROM fa_shop_supplier WHERE code='MOCK_SUPPLIER_PANTRY' LIMIT 1);
SET @fresh_warehouse=(SELECT id FROM fa_shop_warehouse WHERE code='MOCK_WH_FRESH' LIMIT 1);
SET @pantry_warehouse=(SELECT id FROM fa_shop_warehouse WHERE code='MOCK_WH_PANTRY' LIMIT 1);
SET @mock_list=COALESCE((SELECT id FROM fa_shop_shopping_list WHERE list_sn='MOCK_LIST_WEEKLY_NUTRITION' LIMIT 1),0);

SET @oat=(SELECT id FROM fa_shop_goods WHERE goods_sn='MOCK_NUTRITION_OAT' LIMIT 1);
SET @milk=(SELECT id FROM fa_shop_goods WHERE goods_sn='MOCK_NUTRITION_MILK' LIMIT 1);
SET @egg=(SELECT id FROM fa_shop_goods WHERE goods_sn='MOCK_NUTRITION_EGG' LIMIT 1);
SET @tofu=(SELECT id FROM fa_shop_goods WHERE goods_sn='MOCK_NUTRITION_TOFU' LIMIT 1);
SET @banana=(SELECT id FROM fa_shop_goods WHERE goods_sn='MOCK_NUTRITION_BANANA' LIMIT 1);
SET @oat_sku=(SELECT id FROM fa_shop_goods_sku WHERE goods_id=@oat LIMIT 1);
SET @milk_sku=(SELECT id FROM fa_shop_goods_sku WHERE goods_id=@milk LIMIT 1);
SET @egg_sku=(SELECT id FROM fa_shop_goods_sku WHERE goods_id=@egg LIMIT 1);
SET @tofu_sku=(SELECT id FROM fa_shop_goods_sku WHERE goods_id=@tofu LIMIT 1);
SET @banana_sku=(SELECT id FROM fa_shop_goods_sku WHERE goods_id=@banana LIMIT 1);

-- Brand data for the Product Center.
INSERT INTO fa_shop_brand (`name`,`image`,`createtime`,`updatetime`,`weigh`) VALUES
('演示-谷物优选','',@now,@now,100),
('演示-鲜食农场','',@now,@now,90),
('演示-家庭乳品','',@now,@now,80);
SET @grain_brand=(SELECT id FROM fa_shop_brand WHERE name='演示-谷物优选' LIMIT 1);
SET @fresh_brand=(SELECT id FROM fa_shop_brand WHERE name='演示-鲜食农场' LIMIT 1);
SET @dairy_brand=(SELECT id FROM fa_shop_brand WHERE name='演示-家庭乳品' LIMIT 1);
UPDATE fa_shop_goods SET brand_id=@grain_brand WHERE id=@oat;
UPDATE fa_shop_goods SET brand_id=@dairy_brand WHERE id=@milk;
UPDATE fa_shop_goods SET brand_id=@fresh_brand WHERE id IN (@egg,@tofu,@banana);

-- Supplier integration history: success and failure samples are both visible.
INSERT INTO fa_shop_supplier_sync_log
(`supplier_id`,`sync_type`,`biz_key`,`request_id`,`request_json`,`response_json`,`status`,`error_message`,`retry_count`,`createtime`) VALUES
(@fresh_supplier,'PRODUCT','MOCK-PRODUCT-001','MOCK-REQ-001',JSON_OBJECT('mode','incremental'),JSON_OBJECT('received',5),'SUCCESS','',0,@now-7200),
(@pantry_supplier,'PRICE','MOCK-PRICE-001','MOCK-REQ-002',JSON_OBJECT('sku_count',5),JSON_OBJECT('updated',5),'SUCCESS','',0,@now-6600),
(@fresh_supplier,'STOCK','MOCK-STOCK-001','MOCK-REQ-003',JSON_OBJECT('warehouse','fresh'),JSON_OBJECT('updated',5),'SUCCESS','',0,@now-6000),
(@pantry_supplier,'DELIVERY','MOCK-DELIVERY-001','MOCK-REQ-004',JSON_OBJECT('region','全国'),JSON_OBJECT('updated',2),'SUCCESS','',0,@now-5400),
(@fresh_supplier,'ORDER','MOCK-ORDER-SYNC-001','MOCK-REQ-005',JSON_OBJECT('order_sn','MOCK-ORD-1004'),JSON_OBJECT('accepted',true),'SUCCESS','',0,@now-4800),
(@fresh_supplier,'AFTERSALE','MOCK-AFTERSALE-SYNC-001','MOCK-REQ-006',JSON_OBJECT('order_sn','MOCK-ORD-1009'),JSON_OBJECT('accepted',true),'SUCCESS','',0,@now-4200),
(@pantry_supplier,'STOCK','MOCK-STOCK-FAILED-001','MOCK-REQ-007',JSON_OBJECT('warehouse','pantry'),JSON_OBJECT('code','TIMEOUT'),'FAILED','演示：供应商接口超时',2,@now-3600);

INSERT INTO fa_shop_order
(`order_sn`,`user_id`,`receiver`,`address`,`zipcode`,`mobile`,`amount`,`discount`,`shippingfee`,`goodsprice`,`saleamount`,`payamount`,`paytype`,`method`,`transactionid`,`expressname`,`expressno`,`createtime`,`updatetime`,`expiretime`,`paytime`,`refundtime`,`shippingtime`,`receivetime`,`canceltime`,`orderstate`,`shippingstate`,`paystate`,`memo`,`status`) VALUES
('MOCK-ORD-1001',@mock_user,'演示用户','演示地址：幸福路 1 号','','13800000001',24.90,0,0,24.90,24.90,0,'manual','mock','','','',@now-864000,@now-864000,@now+1800,NULL,NULL,NULL,NULL,NULL,0,0,0,'待支付演示订单','normal'),
('MOCK-ORD-1002',@mock_user,'演示用户','演示地址：幸福路 2 号','','13800000002',69.90,0,0,69.90,69.90,69.90,'manual','mock','MOCK-TX-1002','','',@now-777600,@now-7200,NULL,@now-760000,NULL,NULL,NULL,NULL,0,0,1,'待备货演示订单','normal'),
('MOCK-ORD-1003',@mock_user,'演示用户','演示地址：幸福路 3 号','','13800000003',19.90,0,0,19.90,19.90,19.90,'manual','mock','MOCK-TX-1003','','',@now-691200,@now-6800,NULL,@now-680000,NULL,NULL,NULL,NULL,0,0,1,'待出库演示订单','normal'),
('MOCK-ORD-1004',@mock_user,'演示用户','演示地址：幸福路 4 号','','13800000004',9.90,0,0,9.90,9.90,9.90,'manual','mock','MOCK-TX-1004','顺丰速运','MOCK-SF-1004',@now-604800,@now-6200,NULL,@now-590000,NULL,@now-580000,NULL,NULL,0,1,1,'配送中演示订单','normal'),
('MOCK-ORD-1005',@mock_user,'演示用户','演示地址：幸福路 5 号','','13800000005',15.90,0,0,15.90,15.90,15.90,'manual','mock','MOCK-TX-1005','京东物流','MOCK-JD-1005',@now-518400,@now-5000,NULL,@now-510000,NULL,@now-490000,@now-400000,NULL,3,2,1,'已完成演示订单','normal'),
('MOCK-ORD-1006',@mock_user,'演示用户','演示地址：幸福路 6 号','','13800000006',24.90,0,0,24.90,24.90,0,'manual','mock','','','',@now-432000,@now-4000,NULL,NULL,NULL,NULL,NULL,@now-420000,1,0,0,'已取消演示订单','normal'),
('MOCK-ORD-1007',@mock_user,'演示用户','演示地址：幸福路 7 号','','13800000007',69.90,0,0,69.90,69.90,69.90,'manual','mock','MOCK-TX-1007','','',@now-345600,@now-3200,NULL,@now-340000,NULL,NULL,NULL,NULL,4,0,1,'退款申请演示订单','normal'),
('MOCK-ORD-1008',@mock_user,'演示用户','演示地址：幸福路 8 号','','13800000008',19.90,0,0,19.90,19.90,19.90,'manual','mock','MOCK-TX-1008','中通快递','MOCK-ZT-1008',@now-259200,@now-2600,NULL,@now-250000,NULL,@now-240000,NULL,NULL,4,1,1,'退货退款演示订单','normal'),
('MOCK-ORD-1009',@mock_user,'演示用户','演示地址：幸福路 9 号','','13800000009',9.90,0,0,9.90,9.90,9.90,'manual','mock','MOCK-TX-1009','圆通速递','MOCK-YT-1009',@now-172800,@now-2000,NULL,@now-170000,NULL,@now-160000,NULL,NULL,4,1,1,'退货验收演示订单','normal'),
('MOCK-ORD-1010',@mock_user,'演示用户','演示地址：幸福路 10 号','','13800000010',15.90,0,0,15.90,15.90,15.90,'manual','mock','MOCK-TX-1010','京东物流','MOCK-JD-1010',@now-86400,@now-1200,NULL,@now-85000,@now-600,@now-80000,@now-60000,NULL,3,2,1,'售后完成演示订单','normal');

INSERT INTO fa_shop_order_goods
(`order_sn`,`goods_sn`,`goods_id`,`goods_sku_id`,`title`,`nums`,`marketprice`,`price`,`realprice`,`salestate`,`commentstate`,`attrdata`,`image`,`weight`) VALUES
('MOCK-ORD-1001','MOCK_NUTRITION_OAT',@oat,@oat_sku,'演示-即食燕麦片 500g',1,29.90,24.90,24.90,0,0,'默认规格','',0),
('MOCK-ORD-1002','MOCK_NUTRITION_MILK',@milk,@milk_sku,'演示-高钙纯牛奶 250ml x 12',1,79.90,69.90,69.90,0,0,'默认规格','',0),
('MOCK-ORD-1003','MOCK_NUTRITION_EGG',@egg,@egg_sku,'演示-谷物鲜鸡蛋 10枚',1,22.90,19.90,19.90,0,0,'默认规格','',0),
('MOCK-ORD-1004','MOCK_NUTRITION_TOFU',@tofu,@tofu_sku,'演示-有机北豆腐 400g',1,12.90,9.90,9.90,0,0,'默认规格','',0),
('MOCK-ORD-1005','MOCK_NUTRITION_BANANA',@banana,@banana_sku,'演示-香蕉 1kg',1,18.90,15.90,15.90,0,1,'默认规格','',0),
('MOCK-ORD-1006','MOCK_NUTRITION_OAT',@oat,@oat_sku,'演示-即食燕麦片 500g',1,29.90,24.90,24.90,0,0,'默认规格','',0),
('MOCK-ORD-1007','MOCK_NUTRITION_MILK',@milk,@milk_sku,'演示-高钙纯牛奶 250ml x 12',1,79.90,69.90,69.90,2,0,'默认规格','',0),
('MOCK-ORD-1008','MOCK_NUTRITION_EGG',@egg,@egg_sku,'演示-谷物鲜鸡蛋 10枚',1,22.90,19.90,19.90,3,0,'默认规格','',0),
('MOCK-ORD-1009','MOCK_NUTRITION_TOFU',@tofu,@tofu_sku,'演示-有机北豆腐 400g',1,12.90,9.90,9.90,3,0,'默认规格','',0),
('MOCK-ORD-1010','MOCK_NUTRITION_BANANA',@banana,@banana_sku,'演示-香蕉 1kg',1,18.90,15.90,15.90,4,1,'默认规格','',0);

INSERT INTO fa_shop_order_ext
(`order_id`,`order_sn`,`user_id`,`idempotency_key`,`shopping_list_id`,`shopping_list_version`,`biz_status`,`fulfillment_status`,`refund_status`,`trace_id`,`version`,`createtime`,`updatetime`)
SELECT id,order_sn,user_id,CONCAT('MOCK-IDEMP-',order_sn),@mock_list,1,
CASE order_sn WHEN 'MOCK-ORD-1001' THEN 'PENDING_PAYMENT' WHEN 'MOCK-ORD-1002' THEN 'PAID' WHEN 'MOCK-ORD-1003' THEN 'PREPARING' WHEN 'MOCK-ORD-1004' THEN 'SHIPPING' WHEN 'MOCK-ORD-1005' THEN 'COMPLETED' WHEN 'MOCK-ORD-1006' THEN 'CANCELLED' WHEN 'MOCK-ORD-1010' THEN 'COMPLETED' ELSE 'AFTERSALE' END,
CASE order_sn WHEN 'MOCK-ORD-1001' THEN 'PENDING' WHEN 'MOCK-ORD-1002' THEN 'ACCEPTED' WHEN 'MOCK-ORD-1003' THEN 'PREPARING' WHEN 'MOCK-ORD-1004' THEN 'SHIPPED' WHEN 'MOCK-ORD-1006' THEN 'CANCELLED' ELSE 'COMPLETED' END,
CASE WHEN order_sn='MOCK-ORD-1010' THEN 'COMPLETED' WHEN order_sn IN ('MOCK-ORD-1007','MOCK-ORD-1008','MOCK-ORD-1009') THEN 'PROCESSING' ELSE 'NONE' END,
CONCAT('MOCK-TRACE-',id),0,createtime,@now
FROM fa_shop_order WHERE order_sn LIKE 'MOCK-ORD-%';

INSERT INTO fa_shop_order_supplier
(`supplier_order_sn`,`order_id`,`order_sn`,`supplier_id`,`warehouse_id`,`fulfillment_mode`,`goods_amount`,`shipping_fee`,`supply_amount`,`status`,`accepted_at`,`preparing_at`,`shipping_at`,`completed_at`,`cancelled_at`,`createtime`,`updatetime`)
SELECT CONCAT('MOCK-SUB-',RIGHT(o.order_sn,4)),o.id,o.order_sn,
CASE WHEN RIGHT(o.order_sn,1) IN ('2','4','6','8','0') THEN @pantry_supplier ELSE @fresh_supplier END,
CASE WHEN RIGHT(o.order_sn,1) IN ('2','4','6','8','0') THEN @pantry_warehouse ELSE @fresh_warehouse END,
CASE WHEN RIGHT(o.order_sn,1) IN ('2','4','6','8','0') THEN 'PLATFORM_WAREHOUSE' ELSE 'SUPPLIER_DIRECT' END,
og.realprice,0,ROUND(og.realprice*0.60,2),
CASE o.order_sn WHEN 'MOCK-ORD-1001' THEN 'PENDING_ACCEPT' WHEN 'MOCK-ORD-1002' THEN 'ACCEPTED' WHEN 'MOCK-ORD-1003' THEN 'PREPARING' WHEN 'MOCK-ORD-1004' THEN 'SHIPPED' WHEN 'MOCK-ORD-1005' THEN 'COMPLETED' WHEN 'MOCK-ORD-1006' THEN 'CANCELLED' WHEN 'MOCK-ORD-1007' THEN 'REJECTED' WHEN 'MOCK-ORD-1008' THEN 'COMPLETED' WHEN 'MOCK-ORD-1009' THEN 'COMPLETED' ELSE 'COMPLETED' END,
CASE WHEN o.order_sn<>'MOCK-ORD-1001' THEN o.createtime+600 ELSE NULL END,
CASE WHEN o.order_sn IN ('MOCK-ORD-1003','MOCK-ORD-1004','MOCK-ORD-1005','MOCK-ORD-1008','MOCK-ORD-1009','MOCK-ORD-1010') THEN o.createtime+1200 ELSE NULL END,
CASE WHEN o.shippingstate>0 THEN o.shippingtime ELSE NULL END,
CASE WHEN o.order_sn IN ('MOCK-ORD-1005','MOCK-ORD-1008','MOCK-ORD-1009','MOCK-ORD-1010') THEN COALESCE(o.receivetime,o.shippingtime+3600) ELSE NULL END,
CASE WHEN o.order_sn IN ('MOCK-ORD-1006','MOCK-ORD-1007') THEN o.createtime+1800 ELSE NULL END,o.createtime,@now
FROM fa_shop_order o JOIN fa_shop_order_goods og ON og.order_sn=o.order_sn WHERE o.order_sn LIKE 'MOCK-ORD-%';

INSERT INTO fa_shop_order_shipment
(`shipment_sn`,`supplier_order_id`,`order_id`,`order_sn`,`shipper_code`,`shipper_name`,`logistic_code`,`status`,`shipping_at`,`received_at`,`createtime`,`updatetime`)
SELECT CONCAT('MOCK-SHIP-',RIGHT(sub.order_sn,4)),sub.id,sub.order_id,sub.order_sn,
'MOCK','演示物流',CONCAT('MOCK-LOG-',RIGHT(sub.order_sn,4)),
CASE WHEN sub.order_sn='MOCK-ORD-1004' THEN 'SHIPPED' ELSE 'RECEIVED' END,
COALESCE(o.shippingtime,o.createtime+2400),CASE WHEN sub.order_sn='MOCK-ORD-1004' THEN NULL ELSE COALESCE(o.receivetime,o.createtime+86400) END,
o.createtime+2400,@now
FROM fa_shop_order_supplier sub JOIN fa_shop_order o ON o.id=sub.order_id
WHERE sub.order_sn IN ('MOCK-ORD-1004','MOCK-ORD-1005','MOCK-ORD-1008','MOCK-ORD-1009','MOCK-ORD-1010');

INSERT INTO fa_shop_order_shipment_item (`shipment_id`,`order_goods_id`,`quantity`,`createtime`)
SELECT ship.id,og.id,og.nums,ship.createtime FROM fa_shop_order_shipment ship JOIN fa_shop_order_goods og ON og.order_sn=ship.order_sn WHERE ship.order_sn LIKE 'MOCK-ORD-%';

SET @order7=(SELECT id FROM fa_shop_order WHERE order_sn='MOCK-ORD-1007');
SET @order8=(SELECT id FROM fa_shop_order WHERE order_sn='MOCK-ORD-1008');
SET @order9=(SELECT id FROM fa_shop_order WHERE order_sn='MOCK-ORD-1009');
SET @order10=(SELECT id FROM fa_shop_order WHERE order_sn='MOCK-ORD-1010');
SET @og7=(SELECT id FROM fa_shop_order_goods WHERE order_sn='MOCK-ORD-1007');
SET @og8=(SELECT id FROM fa_shop_order_goods WHERE order_sn='MOCK-ORD-1008');
SET @og9=(SELECT id FROM fa_shop_order_goods WHERE order_sn='MOCK-ORD-1009');
SET @og10=(SELECT id FROM fa_shop_order_goods WHERE order_sn='MOCK-ORD-1010');

INSERT INTO fa_shop_order_aftersales
(`order_id`,`order_goods_id`,`user_id`,`type`,`nums`,`realprice`,`shippingfee`,`refund`,`reason`,`images`,`mark`,`status`,`expressname`,`expressno`,`createtime`,`updatetime`) VALUES
(@order7,@og7,@mock_user,1,1,69.90,0,69.90,'演示：商品未发货申请退款','','等待客服审核',1,'','',@now-3000,@now-3000),
(@order8,@og8,@mock_user,2,1,19.90,0,19.90,'演示：商品不符合预期','','等待用户寄回',1,'','',@now-2400,@now-2400),
(@order9,@og9,@mock_user,2,1,9.90,0,9.90,'演示：包装破损','','已寄回等待验收',2,'圆通速递','MOCK-RETURN-1009',@now-1800,@now-900),
(@order10,@og10,@mock_user,1,1,15.90,0,15.90,'演示：配送延误','','退款已完成',2,'','',@now-1200,@now-600);

SET @as7=(SELECT id FROM fa_shop_order_aftersales WHERE order_id=@order7 ORDER BY id DESC LIMIT 1);
SET @as8=(SELECT id FROM fa_shop_order_aftersales WHERE order_id=@order8 ORDER BY id DESC LIMIT 1);
SET @as9=(SELECT id FROM fa_shop_order_aftersales WHERE order_id=@order9 ORDER BY id DESC LIMIT 1);
SET @as10=(SELECT id FROM fa_shop_order_aftersales WHERE order_id=@order10 ORDER BY id DESC LIMIT 1);
SET @sub7=(SELECT id FROM fa_shop_order_supplier WHERE order_id=@order7 LIMIT 1);
SET @sub8=(SELECT id FROM fa_shop_order_supplier WHERE order_id=@order8 LIMIT 1);
SET @sub9=(SELECT id FROM fa_shop_order_supplier WHERE order_id=@order9 LIMIT 1);
SET @sub10=(SELECT id FROM fa_shop_order_supplier WHERE order_id=@order10 LIMIT 1);
SET @tofu_ws=(SELECT id FROM fa_shop_warehouse_sku WHERE warehouse_id=@fresh_warehouse AND goods_sku_id=@tofu_sku LIMIT 1);

INSERT INTO fa_shop_aftersales_ext
(`aftersales_id`,`supplier_order_id`,`supplier_id`,`warehouse_id`,`return_status`,`restock_quantity`,`idempotency_key`,`createtime`,`updatetime`) VALUES
(@as7,@sub7,@fresh_supplier,@fresh_warehouse,'NONE',0,'MOCK-AS-1007',@now-3000,@now),
(@as8,@sub8,@pantry_supplier,@pantry_warehouse,'PENDING',0,'MOCK-AS-1008',@now-2400,@now),
(@as9,@sub9,@fresh_supplier,@fresh_warehouse,'SHIPPED',0,'MOCK-AS-1009',@now-1800,@now),
(@as10,@sub10,@pantry_supplier,@pantry_warehouse,'NONE',0,'MOCK-AS-1010',@now-1200,@now);

INSERT INTO fa_shop_aftersales_inspection
(`inspection_sn`,`aftersales_id`,`supplier_order_id`,`warehouse_sku_id`,`accepted_quantity`,`rejected_quantity`,`status`,`biz_no`,`operator_type`,`operator_id`,`remark`,`createtime`) VALUES
('MOCK-INSP-1009',@as9,@sub9,@tofu_ws,1,0,'ACCEPTED','MOCK-INSP-BIZ-1009','ADMIN',1,'演示：退货商品验收合格',@now-600);

INSERT INTO fa_shop_refund_transaction
(`refund_sn`,`aftersales_id`,`order_id`,`order_sn`,`channel`,`amount`,`local_action`,`local_payload_json`,`external_required`,`status`,`gateway_refund_id`,`request_json`,`response_json`,`attempt_count`,`error_message`,`next_retry_at`,`external_succeeded_at`,`completed_at`,`createtime`,`updatetime`) VALUES
('MOCK-REF-1007',@as7,@order7,'MOCK-ORD-1007','manual',69.90,'REFUND_ONLY',JSON_OBJECT('mock',true),0,'CREATED','',JSON_OBJECT('reason','pending review'),NULL,0,'',NULL,NULL,NULL,@now-3000,@now-3000),
('MOCK-REF-1009',@as9,@order9,'MOCK-ORD-1009','manual',9.90,'RETURN_REFUND',JSON_OBJECT('inspection','accepted'),0,'PROCESSING','',JSON_OBJECT('mock',true),NULL,1,'',@now+3600,NULL,NULL,@now-600,@now-600),
('MOCK-REF-1010',@as10,@order10,'MOCK-ORD-1010','manual',15.90,'REFUND_ONLY',JSON_OBJECT('mock',true),0,'COMPLETED','MOCK-GATEWAY-1010',JSON_OBJECT('mock',true),JSON_OBJECT('success',true),1,'',NULL,@now-700,@now-600,@now-1200,@now-600);

INSERT INTO fa_shop_payment_transaction
(`payment_sn`,`order_id`,`order_sn`,`channel`,`channel_transaction_id`,`amount`,`status`,`request_json`,`callback_json`,`paid_at`,`createtime`,`updatetime`)
SELECT CONCAT('MOCK-PAY-',RIGHT(order_sn,4)),id,order_sn,'manual',transactionid,payamount,
CASE WHEN order_sn='MOCK-ORD-1010' THEN 'REFUNDED' ELSE 'SUCCESS' END,
JSON_OBJECT('mock',true),JSON_OBJECT('success',true),paytime,createtime,@now
FROM fa_shop_order WHERE order_sn LIKE 'MOCK-ORD-%' AND paystate=1;

INSERT INTO fa_shop_order_snapshot (`order_id`,`order_sn`,`snapshot_type`,`snapshot_json`,`createtime`)
SELECT id,order_sn,'ORDER',JSON_OBJECT('mock',true,'order_sn',order_sn,'amount',saleamount),createtime FROM fa_shop_order WHERE order_sn LIKE 'MOCK-ORD-%';

INSERT INTO fa_shop_order_status_log
(`order_id`,`order_sn`,`supplier_order_id`,`status_type`,`from_status`,`to_status`,`biz_no`,`operator_type`,`operator_id`,`remark`,`createtime`)
SELECT o.id,o.order_sn,sub.id,'ORDER','CREATED',ext.biz_status,CONCAT('MOCK-STATUS-',RIGHT(o.order_sn,4)),'SYSTEM',0,'演示订单状态记录',o.createtime
FROM fa_shop_order o JOIN fa_shop_order_ext ext ON ext.order_id=o.id JOIN fa_shop_order_supplier sub ON sub.order_id=o.id WHERE o.order_sn LIKE 'MOCK-ORD-%';

INSERT INTO fa_shop_order_action (`order_sn`,`operator`,`memo`,`createtime`)
SELECT order_sn,'MOCK','创建演示订单',createtime FROM fa_shop_order WHERE order_sn LIKE 'MOCK-ORD-%';

-- Inventory reservations cover locked, released, and deducted states.
SET @oat_ws=(SELECT id FROM fa_shop_warehouse_sku WHERE warehouse_id=@fresh_warehouse AND goods_sku_id=@oat_sku LIMIT 1);
SET @milk_ws=(SELECT id FROM fa_shop_warehouse_sku WHERE warehouse_id=@pantry_warehouse AND goods_sku_id=@milk_sku LIMIT 1);
SET @egg_ws=(SELECT id FROM fa_shop_warehouse_sku WHERE warehouse_id=@fresh_warehouse AND goods_sku_id=@egg_sku LIMIT 1);
SET @banana_ws=(SELECT id FROM fa_shop_warehouse_sku WHERE warehouse_id=@fresh_warehouse AND goods_sku_id=@banana_sku LIMIT 1);
UPDATE fa_shop_warehouse_sku SET locked_qty=0 WHERE id IN (@oat_ws,@milk_ws,@egg_ws,@banana_ws);
UPDATE fa_shop_stock_batch SET locked_qty=0 WHERE warehouse_sku_id IN (@oat_ws,@milk_ws,@egg_ws,@banana_ws);
UPDATE fa_shop_warehouse_sku SET locked_qty=1 WHERE id IN (@oat_ws,@milk_ws);
UPDATE fa_shop_stock_batch SET locked_qty=1 WHERE warehouse_sku_id IN (@oat_ws,@milk_ws);

INSERT INTO fa_shop_stock_reservation
(`reservation_sn`,`biz_key`,`order_sn`,`supplier_order_sn`,`warehouse_sku_id`,`goods_id`,`goods_sku_id`,`quantity`,`status`,`expiretime`,`released_at`,`deducted_at`,`createtime`,`updatetime`) VALUES
('MOCK-RES-1001','MOCK-BIZ-1001','MOCK-ORD-1001','MOCK-SUB-1001',@oat_ws,@oat,@oat_sku,1,'LOCKED',@now+1800,NULL,NULL,@now-3600,@now),
('MOCK-RES-1002','MOCK-BIZ-1002','MOCK-ORD-1002','MOCK-SUB-1002',@milk_ws,@milk,@milk_sku,1,'LOCKED',@now+7200,NULL,NULL,@now-3000,@now),
('MOCK-RES-1004','MOCK-BIZ-1004','MOCK-ORD-1004','MOCK-SUB-1004',@tofu_ws,@tofu,@tofu_sku,1,'DEDUCTED',NULL,NULL,@now-1800,@now-7200,@now),
('MOCK-RES-1006','MOCK-BIZ-1006','MOCK-ORD-1006','MOCK-SUB-1006',@oat_ws,@oat,@oat_sku,1,'RELEASED',NULL,@now-2400,NULL,@now-4800,@now);

-- Make one SKU genuinely low-stock so the alert workspace is not empty.
SET @banana_before=(SELECT on_hand_qty FROM fa_shop_warehouse_sku WHERE id=@banana_ws);
UPDATE fa_shop_warehouse_sku SET on_hand_qty=18,updatetime=@now WHERE id=@banana_ws;
UPDATE fa_shop_stock_batch SET on_hand_qty=18,updatetime=@now WHERE warehouse_sku_id=@banana_ws;
INSERT INTO fa_shop_stock_flow
(`flow_sn`,`warehouse_sku_id`,`supplier_id`,`warehouse_id`,`goods_id`,`goods_sku_id`,`biz_type`,`biz_no`,`change_on_hand`,`change_locked`,`before_on_hand`,`after_on_hand`,`before_locked`,`after_locked`,`operator_type`,`operator_id`,`remark`,`createtime`) VALUES
('MOCK-LOW-STOCK-001',@banana_ws,@fresh_supplier,@fresh_warehouse,@banana,@banana_sku,'ADJUST','MOCK-LOW-STOCK',CAST(18 AS SIGNED)-CAST(@banana_before AS SIGNED),0,@banana_before,18,0,0,'MIGRATION',0,'演示：制造低库存预警样本',@now);

INSERT INTO fa_shop_supplier_reconciliation
(`reconciliation_sn`,`supplier_id`,`period_start`,`period_end`,`order_count`,`goods_amount`,`supply_amount`,`refund_amount`,`payable_amount`,`status`,`confirmed_at`,`paid_at`,`admin_id`,`remark`,`createtime`,`updatetime`) VALUES
('MOCK-REC-FRESH-DRAFT',@fresh_supplier,CURDATE()-INTERVAL 30 DAY,CURDATE()-INTERVAL 16 DAY,3,105.70,63.42,0,63.42,'DRAFT',NULL,NULL,1,'演示：待确认对账单',@now-7200,@now),
('MOCK-REC-PANTRY-CONFIRMED',@pantry_supplier,CURDATE()-INTERVAL 30 DAY,CURDATE()-INTERVAL 16 DAY,3,95.70,57.42,9.90,47.52,'CONFIRMED',@now-3600,NULL,1,'演示：已确认对账单',@now-7000,@now),
('MOCK-REC-FRESH-DISPUTED',@fresh_supplier,CURDATE()-INTERVAL 15 DAY,CURDATE(),2,89.80,53.88,15.90,37.98,'DISPUTED',@now-1800,NULL,1,'演示：金额待复核',@now-3400,@now),
('MOCK-REC-PANTRY-PAID',@pantry_supplier,CURDATE()-INTERVAL 60 DAY,CURDATE()-INTERVAL 31 DAY,2,79.80,47.88,0,47.88,'PAID',@now-90000,@now-86400,1,'演示：已付款对账单',@now-100000,@now);

SET FOREIGN_KEY_CHECKS=1;

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260927_012','补齐管理后台商品供应库存订单配送售后报表 MOCK 数据',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

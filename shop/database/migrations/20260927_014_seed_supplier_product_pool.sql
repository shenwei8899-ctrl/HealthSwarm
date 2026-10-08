SET NAMES utf8mb4;
SET @now = UNIX_TIMESTAMP();

-- Existing supply relations become historical matched source products.
INSERT INTO fa_shop_supplier_product_pool
(`supplier_id`,`supplier_goods_code`,`supplier_sku_code`,`title`,`spec_text`,`barcode`,`image`,`supply_price`,`min_order_qty`,`delivery_days`,`fulfillment_mode`,`source_payload_json`,`goods_id`,`goods_sku_id`,`match_status`,`match_method`,`match_note`,`sync_status`,`last_sync_time`,`status`,`createtime`,`updatetime`)
SELECT ss.supplier_id,ss.supplier_goods_code,ss.supplier_sku_code,g.title,COALESCE(s.sku_id,'DEFAULT'),COALESCE(ext.barcode,''),COALESCE(s.image,''),ss.supply_price,ss.min_order_qty,ss.delivery_days,ss.fulfillment_mode,
JSON_OBJECT('seed','existing_supply_relation'),ss.goods_id,ss.goods_sku_id,'MATCHED','MIGRATED','由原有供货关系迁移','SUCCESS',COALESCE(ss.last_sync_time,@now),IF(ss.status='offline','offline','normal'),@now,@now
FROM fa_shop_supplier_sku ss
JOIN fa_shop_goods g ON g.id=ss.goods_id
LEFT JOIN fa_shop_goods_sku s ON s.id=ss.goods_sku_id
LEFT JOIN fa_shop_sku_ext ext ON ext.goods_sku_id=ss.goods_sku_id
ON DUPLICATE KEY UPDATE title=VALUES(title),spec_text=VALUES(spec_text),barcode=VALUES(barcode),image=VALUES(image),supply_price=VALUES(supply_price),min_order_qty=VALUES(min_order_qty),delivery_days=VALUES(delivery_days),fulfillment_mode=VALUES(fulfillment_mode),goods_id=VALUES(goods_id),goods_sku_id=VALUES(goods_sku_id),match_status='MATCHED',match_method='MIGRATED',match_note='由原有供货关系迁移',sync_status='SUCCESS',last_sync_time=VALUES(last_sync_time),status=VALUES(status),updatetime=@now;

SET @fresh_supplier=(SELECT id FROM fa_shop_supplier WHERE code='MOCK_SUPPLIER_FRESH' LIMIT 1);
SET @pantry_supplier=(SELECT id FROM fa_shop_supplier WHERE code='MOCK_SUPPLIER_PANTRY' LIMIT 1);
INSERT INTO fa_shop_supplier_product_pool
(`supplier_id`,`supplier_goods_code`,`supplier_sku_code`,`title`,`spec_text`,`barcode`,`image`,`supply_price`,`min_order_qty`,`delivery_days`,`fulfillment_mode`,`source_payload_json`,`goods_id`,`goods_sku_id`,`match_status`,`match_method`,`match_note`,`sync_status`,`last_sync_time`,`status`,`createtime`,`updatetime`) VALUES
(@fresh_supplier,'MOCK-SOURCE-CEREAL','MOCK-SOURCE-CEREAL-300','演示-低糖玉米片 300g','300g','','',18.80,1,1,'SUPPLIER_DIRECT',JSON_OBJECT('mock',true),0,0,'PENDING','NONE','等待运营匹配', 'SUCCESS',@now,'normal',@now,@now),
(@pantry_supplier,'MOCK-SOURCE-SOY','MOCK-SOURCE-SOY-400','演示-无糖豆浆粉 400g','400g','','',25.60,1,2,'PLATFORM_WAREHOUSE',JSON_OBJECT('mock',true),0,0,'PENDING','NONE','等待运营匹配', 'SUCCESS',@now,'normal',@now,@now)
ON DUPLICATE KEY UPDATE title=VALUES(title),spec_text=VALUES(spec_text),supply_price=VALUES(supply_price),delivery_days=VALUES(delivery_days),match_status='PENDING',match_method='NONE',match_note='等待运营匹配',sync_status='SUCCESS',last_sync_time=@now,status='normal',updatetime=@now;

INSERT INTO fa_shop_schema_migration (`version`,`description`,`applied_at`) VALUES
('20260927_014','将现有供货关系迁移至供应商商品池并补齐待匹配示例',@now)
ON DUPLICATE KEY UPDATE description=VALUES(description),applied_at=VALUES(applied_at);

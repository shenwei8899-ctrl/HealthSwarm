-- Supplier-facing catalog import replaces the old internal master-data file.
ALTER TABLE "fa_shop_supplier_sku" ADD COLUMN IF NOT EXISTS "supplier_goods_code" varchar(100) NOT NULL DEFAULT '';
ALTER TABLE "fa_shop_supplier_sku" ADD COLUMN IF NOT EXISTS "delivery_days" integer NOT NULL DEFAULT 0;
ALTER TABLE "fa_shop_supplier_sku" ADD COLUMN IF NOT EXISTS "source_note" text NOT NULL DEFAULT '';
UPDATE "fa_auth_rule" SET "title" = '商品与食材库', "updatetime" = EXTRACT(EPOCH FROM NOW())::bigint
WHERE "name" = 'shop/v5/workspace/product';
UPDATE "fa_auth_rule" SET "ismenu" = 0, "updatetime" = EXTRACT(EPOCH FROM NOW())::bigint
WHERE "name" = 'shop/v5/workspace/ingredients';
UPDATE "fa_auth_rule" SET "title" = '下载供应商商品模板', "updatetime" = EXTRACT(EPOCH FROM NOW())::bigint
WHERE "name" = 'shop/v5/workspace/downloadimporttemplate';
UPDATE "fa_auth_rule" SET "title" = '预检供应商商品目录', "updatetime" = EXTRACT(EPOCH FROM NOW())::bigint
WHERE "name" = 'shop/v5/workspace/previewimport';
UPDATE "fa_auth_rule" SET "title" = '确认供应商商品导入', "updatetime" = EXTRACT(EPOCH FROM NOW())::bigint
WHERE "name" = 'shop/v5/workspace/confirmimport';

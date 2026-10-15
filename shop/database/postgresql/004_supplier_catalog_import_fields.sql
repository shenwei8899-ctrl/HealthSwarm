-- Additive, repeatable upgrade for supplier catalog import metadata.
BEGIN;
SET LOCAL lock_timeout = '10s';
ALTER TABLE "__PREFIX__shop_supplier_sku"
  ADD COLUMN IF NOT EXISTS "supplier_goods_code" varchar(100) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS "delivery_days" int NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS "source_note" text DEFAULT NULL;
INSERT INTO "__PREFIX__shop_schema_migration" ("version", "description", "checksum", "executed_at")
VALUES (
  '20261014_supplier_catalog_fields',
  'Supplier catalog import metadata fields',
  encode(sha256(convert_to('shop_supplier_sku|supplier_goods_code:varchar(100)|delivery_days:int|source_note:text', 'UTF8')), 'hex'),
  EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::bigint
)
ON CONFLICT ("version") DO NOTHING;
COMMIT;

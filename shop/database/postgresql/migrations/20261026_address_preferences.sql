-- Run once before activating the updated AddressService.php. Safe to repeat.
BEGIN;
ALTER TABLE fa_shop_address ADD COLUMN IF NOT EXISTS address_label varchar(10) NOT NULL DEFAULT '';
COMMENT ON COLUMN fa_shop_address.address_label IS 'Optional user-defined address label, at most 10 characters';
COMMIT;

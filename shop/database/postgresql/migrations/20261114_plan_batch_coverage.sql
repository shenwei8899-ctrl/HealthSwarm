ALTER TABLE fa_shop_plan_delivery_batch ADD COLUMN IF NOT EXISTS menu_day_start integer;
ALTER TABLE fa_shop_plan_delivery_batch ADD COLUMN IF NOT EXISTS menu_day_end integer;
ALTER TABLE fa_shop_plan_delivery_batch ADD COLUMN IF NOT EXISTS meal_end_date date;

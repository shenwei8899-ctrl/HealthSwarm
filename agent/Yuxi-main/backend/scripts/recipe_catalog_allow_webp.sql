-- 在独立菜谱目录上扩展图片格式。现有 JPEG 和已保存菜谱 ID 保持原样。
BEGIN;
ALTER TABLE recipe_catalog.recipes
    DROP CONSTRAINT recipe_image_type,
    ADD CONSTRAINT recipe_image_type CHECK (image_mime IN ('image/jpeg', 'image/webp'));
COMMIT;

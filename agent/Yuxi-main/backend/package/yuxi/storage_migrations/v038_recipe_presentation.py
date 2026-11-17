"""将菜谱展示信息绑定到已发布的食材映射版本。"""

from sqlalchemy import text


async def upgrade_recipe_presentation(manager):
    """补充可选菜谱封面和制作时间的存储。"""
    async with manager.async_engine.begin() as connection:
        await connection.execute(
            text("ALTER TABLE health_recipe_commerce_source ADD COLUMN IF NOT EXISTS presentation JSONB")
        )

"""读取独立的 PostgreSQL 参考菜谱目录。"""

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from yuxi.services.health_vision_types import HealthVisionError

_CATALOG_ROWS = """
    SELECT r.id, r.name, r.ingredients, r.steps, r.image_mime, r.image_label, r.image_sha256,
           (SELECT array_agg(i.raw_text ORDER BY i.position)
            FROM recipe_catalog.reference_recipe_ingredient i WHERE i.recipe_id = r.id) AS ingredient_lines
    FROM recipe_catalog.recipes r
"""


async def catalog_recipe_rows(session):
    """读取轻量菜谱事实，不读取图片二进制。"""
    return (await _catalog_query(session, _CATALOG_ROWS + " ORDER BY r.id")).mappings().all()


async def catalog_recipe_row(session, recipe_id, *, include_image=False):
    """锁定当前正文或读取待冻结到公共图片存储的原图。"""
    statement = (
        "SELECT image_bytes, image_mime, image_sha256 FROM recipe_catalog.recipes WHERE id = :recipe_id FOR SHARE"
        if include_image
        else _CATALOG_ROWS + " WHERE r.id = :recipe_id FOR SHARE OF r"
    )
    return (await _catalog_query(session, statement, {"recipe_id": recipe_id})).mappings().one_or_none()


async def _catalog_query(session, statement, params=None):
    """单独报告目录未配置；其他数据库错误按原错误处理。"""
    try:
        return await session.execute(text(statement), params)
    except ProgrammingError as error:
        if getattr(error.orig, "sqlstate", None) in {"42P01", "3F000"}:
            raise HealthVisionError("reference_catalog_unavailable", "菜谱数据库尚未导入或配置", 503) from error
        raise

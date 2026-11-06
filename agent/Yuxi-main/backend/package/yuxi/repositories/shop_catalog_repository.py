"""只读查询商城 PostgreSQL 中当前可见的商品候选。"""

import os
import re
import time

import asyncpg

from yuxi.services.health_vision_types import HealthVisionError


SEARCH_SQL = r"""
SELECT s.id AS sku_id
FROM fa_shop_goods_sku AS s
JOIN fa_shop_goods AS g ON g.id = s.goods_id
WHERE g.agent_visible = 1 AND g.catalog_status = 'published'
  AND g.status = 'normal' AND g.deletetime IS NULL
  AND g.business_category_code = ANY($5::text[])
  AND s.stocks - s.reserved_stock - s.safety_stock > 0
  AND ($1 = ''
    OR regexp_replace(g.title, '[[:space:]]+', '', 'g') ILIKE $2 ESCAPE E'\\'
    OR regexp_replace(s.sku_id, '[[:space:]]+', '', 'g') ILIKE $2 ESCAPE E'\\'
    OR regexp_replace(s.sku_code, '[[:space:]]+', '', 'g') ILIKE $2 ESCAPE E'\\'
    OR regexp_replace(g.business_category_code, '[[:space:]]+', '', 'g') ILIKE $2 ESCAPE E'\\'
    OR EXISTS (
      SELECT 1 FROM fa_shop_category AS c
      WHERE c.business_category_code = g.business_category_code
        AND c.status = 'normal' AND c.agent_visible = 1
        AND regexp_replace(c.name, '[[:space:]]+', '', 'g') ILIKE $2 ESCAPE E'\\')
    OR EXISTS (
      SELECT 1 FROM fa_shop_ingredient_sku_map AS m
      JOIN fa_shop_ingredient AS i ON i.id = m.ingredient_id
      LEFT JOIN fa_shop_ingredient_alias AS a
        ON a.ingredient_id = i.id AND a.status = 'normal'
      WHERE m.sku_id = s.id AND m.goods_id = g.id
        AND m.status = 'normal' AND m.review_status = 'approved'
        AND m.valid_from <= $4 AND (m.valid_to = 0 OR m.valid_to > $4)
        AND i.status = 'normal' AND i.deletetime IS NULL
        AND (regexp_replace(i.name, '[[:space:]]+', '', 'g') ILIKE $2 ESCAPE E'\\'
          OR regexp_replace(i.ingredient_code, '[[:space:]]+', '', 'g') ILIKE $2 ESCAPE E'\\'
          OR regexp_replace(a.alias, '[[:space:]]+', '', 'g') ILIKE $2 ESCAPE E'\\')
    ))
ORDER BY s.id
LIMIT 4 OFFSET $3
"""


async def search_shop_catalog(query: str, offset: int, category_codes: list[str]) -> dict:
    """以只读事务读取有限候选和目录版本，不向模型暴露数据库连接。"""
    dsn = os.environ.get("HEALTH_COMMERCE_SEARCH_DSN", "")
    if not dsn:
        raise HealthVisionError("commerce_not_configured", "商城商品搜索尚未配置", 503)
    normalized_query = re.sub(r"\s+", "", query).casefold()
    pattern = "%" + normalized_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    connection = None
    try:
        connection = await asyncpg.connect(dsn=dsn, timeout=3, command_timeout=5)
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            rows = await connection.fetch(
                SEARCH_SQL, normalized_query, pattern, offset, int(time.time()), category_codes
            )
            version = await connection.fetchval(
                "SELECT catalog_version FROM fa_shop_catalog_version ORDER BY id DESC LIMIT 1"
            )
    except (asyncpg.PostgresError, OSError, TimeoutError, ValueError):
        raise HealthVisionError("commerce_unavailable", "商城商品搜索暂时不可用", 503) from None
    finally:
        if connection is not None:
            await connection.close()
    items = [dict(row) for row in rows[:3]]
    return {
        "items": items,
        "version": version or "catalog_0",
        "next_offset": offset + 3 if len(rows) > 3 else None,
    }


async def lookup_restriction_codes(names: list[str]) -> dict[str, str | None]:
    """按商城当前食材名及有效别名解析限制，歧义项保持未知。"""
    if not names:
        return {}
    dsn = os.environ.get("HEALTH_COMMERCE_SEARCH_DSN", "")
    if not dsn:
        raise HealthVisionError("commerce_not_configured", "商城商品搜索尚未配置", 503)
    connection = None
    try:
        connection = await asyncpg.connect(dsn=dsn, timeout=3, command_timeout=5)
        async with connection.transaction(readonly=True):
            rows = await connection.fetch(
                """
                SELECT lower(regexp_replace(term, '[[:space:]]+', '', 'g')) AS name, ingredient_code
                FROM (
                    SELECT i.name AS term, i.ingredient_code
                    FROM fa_shop_ingredient AS i
                    WHERE i.status = 'normal' AND i.deletetime IS NULL
                    UNION ALL
                    SELECT a.alias AS term, i.ingredient_code
                    FROM fa_shop_ingredient_alias AS a
                    JOIN fa_shop_ingredient AS i ON i.id = a.ingredient_id
                    WHERE a.status = 'normal' AND i.status = 'normal' AND i.deletetime IS NULL
                ) AS terms
                WHERE lower(regexp_replace(term, '[[:space:]]+', '', 'g')) = ANY($1::text[])
                """,
                names,
            )
    except (asyncpg.PostgresError, OSError, TimeoutError, ValueError):
        raise HealthVisionError("commerce_unavailable", "商城食材限制暂时无法核对", 503) from None
    finally:
        if connection is not None:
            await connection.close()
    codes: dict[str, str | None] = {}
    for row in rows:
        name, code = row["name"], row["ingredient_code"]
        if name not in codes:
            codes[name] = code
        elif codes[name] != code:
            codes[name] = None
    return codes

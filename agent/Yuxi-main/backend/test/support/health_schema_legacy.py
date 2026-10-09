"""旧健康 Schema 的结构前置条件，防止当前 ORM 掩盖增量迁移。"""

from sqlalchemy import text


async def remove_schema21_safe_planner_structures(engine):
    """旧事实写入后移除 21 新结构，避免 ORM 插入引用尚不存在的列。"""
    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE health_safe_planner_preview"))
        await connection.execute(text("ALTER TABLE health_consultation DROP COLUMN safe_planner_selection"))
        await assert_schema21_safe_planner_absent(connection)


async def assert_schema21_safe_planner_absent(connection):
    """直接回读 PG 目录，证明安全预览表和绑定列均缺失。"""
    assert await connection.scalar(text("SELECT to_regclass('health_safe_planner_preview')")) is None
    assert (
        await connection.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name='health_consultation' "
                "AND column_name='safe_planner_selection'"
            )
        )
        == 0
    )

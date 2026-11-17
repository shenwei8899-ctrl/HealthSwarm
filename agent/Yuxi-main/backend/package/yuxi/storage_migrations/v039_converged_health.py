"""补齐两个已使用健康版本 38 的发布形态。"""

from yuxi.storage_migrations.v038_account_memory import upgrade_account_memory
from yuxi.storage_migrations.v038_recipe_presentation import upgrade_recipe_presentation


async def upgrade_converged_health(manager):
    """幂等补齐菜谱展示与账号记忆，成功后由迁移入口记录版本。"""
    await upgrade_recipe_presentation(manager)
    await upgrade_account_memory(manager)

"""辅助译文按完整来源版本幂等保存，读取前的授权由业务服务执行。"""

from sqlalchemy.dialects.postgresql import insert

from yuxi.storage.postgres.models_health import HealthRecipeTranslation


class RecipeTranslationRepository:
    """译文不拥有菜谱、采购或营养状态。"""

    def __init__(self, session):
        self.session = session

    async def get(self, key):
        """只读取调用方已验证来源的内容键。"""
        return await self.session.get(HealthRecipeTranslation, key)

    async def save(self, key, source, display, producer, version):
        """并发及重试复用第一份已验证译文，不覆盖历史内容。"""
        await self.session.execute(
            insert(HealthRecipeTranslation)
            .values(id=key, source=source, display=display, producer=producer, translation_version=version)
            .on_conflict_do_nothing(index_elements=[HealthRecipeTranslation.id])
        )

"""候选批次与正式数据冲突查询边界。"""

from sqlalchemy import select

from yuxi.storage.postgres.models_health import NutritionImportBatch, FoodRecord, RecipeVersion


class NutritionImportRepository:
    """导入权限由管理路由把关，批次仅对其创建者可读。"""

    def __init__(self, session):
        """复用用例事务。"""
        self.session = session

    async def receipt(self, uid, request_id):
        """账号级幂等收据。"""
        return await self.session.scalar(
            select(NutritionImportBatch).where(
                NutritionImportBatch.actor_uid == uid, NutritionImportBatch.request_id == request_id
            )
        )

    async def read(self, uid, batch_id):
        """不泄露其他导入者的未发布候选。"""
        return await self.session.scalar(
            select(NutritionImportBatch).where(
                NutritionImportBatch.actor_uid == uid, NutritionImportBatch.id == batch_id
            )
        )

    async def published(self, kind, codes):
        """读取候选代码的全部已发布版本以识别重号。"""
        model = FoodRecord if kind == "food" else RecipeVersion
        return list((await self.session.scalars(select(model).where(model.record_code.in_(codes)))).all())

    async def food_ids(self, ids):
        """配方原料必须已有可引用的正式食品版本。"""
        return set((await self.session.scalars(select(FoodRecord.id).where(FoodRecord.id.in_(ids)))).all())

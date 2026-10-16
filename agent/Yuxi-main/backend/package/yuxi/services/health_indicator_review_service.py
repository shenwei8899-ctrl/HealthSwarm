"""无模型的指标事实回顾，复用原实测授权和来源校验。"""

from yuxi.repositories.health_blood_glucose_repository import HealthBloodGlucoseRepository
from yuxi.repositories.health_blood_lipids_repository import HealthBloodLipidsRepository
from yuxi.repositories.health_blood_pressure_repository import HealthBloodPressureRepository
from yuxi.storage.postgres.manager import pg_manager


async def read_indicator_review(uid, member_id, kind, selection):
    """普通读取无需模型同意，不写入正式个体化建议。"""
    async with pg_manager.get_async_session_context() as session:
        return await read_indicator_in_session(session, uid, member_id, kind, selection.model_dump(mode="json"))


async def read_indicator_in_session(session, uid, member_id, kind, selection):
    """创建咨询和直接回顾使用同一来源投影。"""
    repo = {
        "blood_glucose": HealthBloodGlucoseRepository,
        "blood_lipids": HealthBloodLipidsRepository,
        "blood_pressure": HealthBloodPressureRepository,
    }[kind](session)
    return await repo.read(uid, member_id, selection=selection)

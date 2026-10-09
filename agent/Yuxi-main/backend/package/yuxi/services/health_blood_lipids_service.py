"""本人血脂四项的普通读取与受控Agent用例。"""

from yuxi.repositories.health_blood_lipids_repository import HealthBloodLipidsRepository
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager


async def read_blood_lipids_records(uid, member_id):
    """普通读取拥有事务，不创建模型同意或Run回执。"""
    async with pg_manager.get_async_session_context() as session:
        return await HealthBloodLipidsRepository(session).read(uid, member_id)


async def blood_lipids_records_for_run(context):
    """当前attempt、冻结同意及本人授权后读取并保存依赖。"""
    from yuxi.services.health_consultation_service import require_consultation

    async with pg_manager.get_async_session_context() as session:
        run = await HealthConsultationRepository(session).require_attempt(context, lock=True)
        snapshot = (run.input_payload or {}).get("health_processing")
        if not snapshot:
            raise HealthVisionError("policy_changed", "咨询缺少处理审批快照", 409)
        binding, _ = await require_consultation(
            session, context.uid, context.thread_id, context.model, expected=snapshot, lock=True
        )
        repo = HealthBloodLipidsRepository(session)
        result = await repo.read(context.uid, binding.member_id)
        await repo.record_use(run, result)
        return result

"""本人实测体重的普通读取与受控 Agent 用例。"""

from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.health_weight_repository import HealthWeightRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager


async def read_weight_records(uid, member_id):
    """普通读取拥有事务，不创建模型处理同意或运行回执。"""
    async with pg_manager.get_async_session_context() as session:
        return await HealthWeightRepository(session).read(uid, member_id)


async def weight_records_for_run(context):
    """当前 Worker attempt、冻结处理审批和本人授权后读取并登记依赖。"""
    from yuxi.services.health_consultation_service import require_consultation

    async with pg_manager.get_async_session_context() as session:
        run = await HealthConsultationRepository(session).require_attempt(context, lock=True)
        snapshot = (run.input_payload or {}).get("health_processing")
        if not snapshot:
            raise HealthVisionError("policy_changed", "咨询缺少处理审批快照", 409)
        binding, _ = await require_consultation(
            session, context.uid, context.thread_id, context.model, expected=snapshot, lock=True
        )
        repo = HealthWeightRepository(session)
        result = await repo.read(context.uid, binding.member_id)
        await repo.record_use(run, result)
        return result

"""本人正式家庭档案的普通接口及受控咨询读取。"""

from typing import Literal
from uuid import UUID

from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
from yuxi.services.health_vision_types import HealthDTO, HealthVisionError
from yuxi.storage.postgres.manager import pg_manager


class FamilyProfileLinkInput(HealthDTO):
    """显式确认两个 ID 是同一个本人；不接受模型或姓名匹配。"""

    family_id: UUID
    source_member_id: UUID
    confirmed_identity: Literal[True]


async def link_family_profile(uid, member_id, data):
    """关联用例拥有事务，成功返回即可安全重放。"""
    async with pg_manager.get_async_session_context() as session:
        return await HealthFamilyProfileRepository(session).link(
            uid, member_id, str(data.family_id), str(data.source_member_id)
        )


async def read_family_profile(uid, member_id, *, link_only=False):
    """普通接口独立于模型处理，不自动创建模型同意。"""
    async with pg_manager.get_async_session_context() as session:
        repo = HealthFamilyProfileRepository(session)
        return await repo.read_link(uid, member_id) if link_only else await repo.read(uid, member_id)


async def family_profile_for_run(context):
    """有效 Worker、模型处理审批及本人授权后读取并记录来源。"""
    from yuxi.services.health_consultation_service import require_consultation

    async with pg_manager.get_async_session_context() as session:
        run = await HealthConsultationRepository(session).require_attempt(context, lock=True)
        snapshot = (run.input_payload or {}).get("health_processing")
        if not snapshot:
            raise HealthVisionError("policy_changed", "咨询缺少处理审批快照", 409)
        binding, _ = await require_consultation(
            session, context.uid, context.thread_id, context.model, expected=snapshot, lock=True
        )
        repo = HealthFamilyProfileRepository(session)
        result = await repo.read(context.uid, binding.member_id)
        await repo.record_use(run, result)
        return result


async def validate_profile_publication(session, run):
    """发布事务重验来源、当前权限及冻结的模型处理同意。"""
    from yuxi.services.health_consultation_service import require_consultation

    snapshot = (run.input_payload or {}).get("health_processing")
    if not snapshot:
        raise HealthVisionError("policy_changed", "咨询缺少处理审批快照", 409)
    await require_consultation(session, run.uid, run.conversation_thread_id, expected=snapshot, lock=True)

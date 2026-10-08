"""健康咨询的会话身份及当前执行所有权查询。"""

from sqlalchemy import select, text

from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AgentRun, Conversation, Project
from yuxi.storage.postgres.models_health import HealthConsultation
from yuxi.utils.datetime_utils import utc_now_naive

CONSULTATION_SLUG = "health-consultation"
CONSULTATION_BACKEND = "HealthConsultationAgent"
PLANNER_SLUG = "health-meal-planner"
PLANNER_BACKEND = "HealthMealPlannerAgent"
ANALYST_SLUG = "health-diet-analyst"
ANALYST_BACKEND = "HealthDietAnalystAgent"
QUALITY_SLUG = "health-quality"
QUALITY_BACKEND = "HealthQualityAgent"
STRUCTURED_HEALTH_AGENTS = frozenset((PLANNER_SLUG, ANALYST_SLUG, QUALITY_SLUG))
HEALTH_AGENT_BACKENDS = {
    CONSULTATION_SLUG: CONSULTATION_BACKEND,
    PLANNER_SLUG: PLANNER_BACKEND,
    ANALYST_SLUG: ANALYST_BACKEND,
    QUALITY_SLUG: QUALITY_BACKEND,
}


class HealthConsultationRepository:
    """身份来自 PG 绑定，管理员与模型均不能旁路成员授权。"""

    def __init__(self, session):
        self.session = session

    async def lock_request(self, uid, request_id):
        """同账号同幂等键串行创建，跨成员重放也共享锁。"""
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"health-consultation:{uid}:{request_id}"},
        )

    async def find_request(self, uid, request_id):
        """按账号查询已有绑定，不泄露其他账号幂等键。"""
        return await self.session.scalar(
            select(HealthConsultation).where(
                HealthConsultation.actor_uid == uid, HealthConsultation.request_id == request_id
            )
        )

    async def authorize(self, uid, thread_id, *, lock=False):
        """逐次验证会话、项目、账号及成员 grant，成员锁与撤回排序。"""
        binding = await self.session.scalar(
            select(HealthConsultation)
            .join(Conversation, Conversation.id == HealthConsultation.conversation_id)
            .join(Project, Project.id == Conversation.project_id)
            .where(
                Conversation.thread_id == thread_id,
                Conversation.uid == uid,
                Conversation.agent_id.in_(HEALTH_AGENT_BACKENDS),
                Conversation.status == "active",
                Project.uid == uid,
                Project.status == "active",
                HealthConsultation.actor_uid == uid,
            )
        )
        if binding is None:
            raise HealthVisionError("not_found", "专属咨询不存在或无权访问", 404)
        conversation = await self.session.get(Conversation, binding.conversation_id)
        if getattr(binding, "initial_planner_selection", None) is not None:
            from yuxi.services.health_initial_planner_service import authorize_initial_planner_binding

            if conversation.agent_id != PLANNER_SLUG or binding.family_planner_selection is not None:
                raise HealthVisionError("source_invalidated", "初始选择不属于唯一配餐模式", 410)
            await authorize_initial_planner_binding(self.session, binding)
            return binding
        if getattr(binding, "family_planner_selection", None) is not None:
            from yuxi.services.health_family_planner_service import authorize_family_planner_binding

            if conversation.agent_id != PLANNER_SLUG:
                raise HealthVisionError("source_invalidated", "家庭选择不属于配餐线程", 410)
            await authorize_family_planner_binding(self.session, binding)
            return binding
        health_repo = HealthVisionRepository(self.session)
        await health_repo.authorize(binding.member_id, uid, "ai_use", lock=lock)
        scopes = (
            ("diet_edit", "profile_view")
            if conversation.agent_id == QUALITY_SLUG
            else ("diet_edit",)
            if conversation.agent_id == ANALYST_SLUG
            else ("report_view", "diet_edit")
        )
        for scope in scopes:
            await health_repo.authorize(binding.member_id, uid, scope)
        if conversation.agent_id == CONSULTATION_SLUG:
            from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
            from yuxi.repositories.health_weight_repository import HealthWeightRepository
            from yuxi.repositories.health_blood_pressure_repository import HealthBloodPressureRepository

            await HealthFamilyProfileRepository(self.session).validate_history(uid, binding, lock=lock)
            await HealthWeightRepository(self.session).validate_history(uid, binding, lock=lock)
            await HealthBloodPressureRepository(self.session).validate_history(uid, binding, lock=lock)
        if conversation.agent_id == ANALYST_SLUG:
            from yuxi.repositories.health_diet_analysis_repository import HealthDietAnalysisRepository
            from yuxi.repositories.health_dialog_feedback_repository import HealthDialogFeedbackRepository

            feedback_repo = HealthDialogFeedbackRepository(self.session)
            selection = await feedback_repo.selection(binding)
            if selection is not None:
                await feedback_repo.validate_history(uid, binding, selection)
            else:
                await HealthDietAnalysisRepository(self.session).validate_history(uid, binding)
        elif conversation.agent_id == QUALITY_SLUG:
            from yuxi.repositories.health_quality_repository import HealthQualityRepository

            await HealthQualityRepository(self.session).validate_history(uid, binding)
        return binding

    async def require_attempt(self, context, *, lock=False):
        """工具与模型调用须属于当前有效 worker attempt，不接受模型身份参数。"""
        stmt = (
            select(AgentRun)
            .where(
                AgentRun.id == context.run_id,
                AgentRun.request_id == context.request_id,
                AgentRun.uid == context.uid,
                AgentRun.agent_slug.in_(HEALTH_AGENT_BACKENDS),
                AgentRun.conversation_thread_id == context.thread_id,
                AgentRun.worker_id == context.worker_id,
                AgentRun.status == "running",
                AgentRun.lease_expires_at > utc_now_naive(),
            )
            .join(Conversation, Conversation.id == AgentRun.conversation_id)
            .where(
                Conversation.agent_id == AgentRun.agent_slug,
                Conversation.thread_id == context.thread_id,
                Conversation.uid == context.uid,
            )
        )
        if lock:
            # 只锁执行Owner，避免与提交请求的Member→Conversation锁序相反。
            stmt = stmt.with_for_update(of=AgentRun)
        run = await self.session.scalar(stmt)
        if run is None:
            raise HealthVisionError("execution_not_owned", "咨询执行已失去所有权", 409)
        return run

"""健康咨询的会话身份及当前执行所有权查询。"""

from sqlalchemy import and_, or_, select, text

from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AgentRun, Conversation, Project
from yuxi.storage.postgres.models_health import HealthConsultation, HealthDailyConversation, HealthSafePlannerPreview
from yuxi.utils.datetime_utils import utc_now_naive

CONSULTATION_SLUG = "health-consultation"
CONSULTATION_BACKEND = "HealthConsultationAgent"
PLANNER_SLUG = "health-meal-planner"
PLANNER_BACKEND = "HealthMealPlannerAgent"
ANALYST_SLUG = "health-diet-analyst"
ANALYST_BACKEND = "HealthDietAnalystAgent"
QUALITY_SLUG = "health-quality"
QUALITY_BACKEND = "HealthQualityAgent"
PURCHASE_SLUG = "health-purchase"
PURCHASE_BACKEND = "HealthPurchaseAgent"
STRUCTURED_HEALTH_AGENTS = frozenset((PLANNER_SLUG, ANALYST_SLUG, QUALITY_SLUG, PURCHASE_SLUG))
HEALTH_AGENT_BACKENDS = {
    CONSULTATION_SLUG: CONSULTATION_BACKEND,
    PLANNER_SLUG: PLANNER_BACKEND,
    ANALYST_SLUG: ANALYST_BACKEND,
    QUALITY_SLUG: QUALITY_BACKEND,
    PURCHASE_SLUG: PURCHASE_BACKEND,
}


class HealthConsultationRepository:
    """身份来自 PG 绑定，管理员与模型均不能旁路成员授权。"""

    def __init__(self, session):
        self.session = session

    async def list_member_consultations(self, uid, member_id, *, limit, offset):
        """只查询当前账号和成员的有效咨询元数据，额外一行判断分页。"""
        result = await self.session.execute(
            select(Conversation.thread_id, HealthDailyConversation.business_date, Conversation.created_at)
            .select_from(HealthConsultation)
            .join(Conversation, Conversation.id == HealthConsultation.conversation_id)
            .join(Project, Project.id == Conversation.project_id)
            .outerjoin(
                HealthDailyConversation,
                and_(
                    HealthDailyConversation.conversation_id == Conversation.id,
                    HealthDailyConversation.actor_uid == uid,
                    HealthDailyConversation.member_id == member_id,
                ),
            )
            .where(
                HealthConsultation.actor_uid == uid,
                HealthConsultation.member_id == member_id,
                Conversation.uid == uid,
                Conversation.agent_id == CONSULTATION_SLUG,
                Conversation.status == "active",
                Project.uid == uid,
                Project.status == "active",
            )
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .limit(limit + 1)
            .offset(offset)
        )
        return result.all()

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

    async def authorize(self, uid, thread_id, *, lock=False, preview_history=False):
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
        target_selection = getattr(binding, "personal_target_selection", None)
        if target_selection is not None and (
            conversation.agent_id != ANALYST_SLUG
            or any(
                getattr(binding, field, None) is not None
                for field in (
                    "family_planner_selection",
                    "initial_planner_selection",
                    "safe_planner_selection",
                    "purchase_selection",
                )
            )
        ):
            raise HealthVisionError("source_invalidated", "个人目标选择不属于唯一普通分析模式", 410)
        await self.validate_personal_target_runs(binding)
        if conversation.agent_id == PURCHASE_SLUG or getattr(binding, "purchase_selection", None) is not None:
            from yuxi.services.health_purchase_service import authorize_purchase_binding, validate_purchase_history

            if conversation.agent_id != PURCHASE_SLUG:
                raise HealthVisionError("source_invalidated", "采购选择不属于采购线程", 410)
            await authorize_purchase_binding(self.session, binding)
            if preview_history:
                await validate_purchase_history(self.session, binding)
            return binding
        if preview_history and getattr(binding, "safe_planner_selection", None) is None:
            had_safe_history = await self.session.scalar(
                select(
                    or_(
                        select(HealthSafePlannerPreview.id)
                        .where(HealthSafePlannerPreview.conversation_id == binding.conversation_id)
                        .exists(),
                        select(AgentRun.id)
                        .where(
                            AgentRun.conversation_id == binding.conversation_id,
                            AgentRun.input_payload["health_processing"]["safe_selection_hash"].as_string().is_not(None),
                        )
                        .exists(),
                    )
                )
            )
            if had_safe_history:
                raise HealthVisionError("source_invalidated", "单成员安全历史的固定选择已丢失或变更", 410)
        if getattr(binding, "safe_planner_selection", None) is not None:
            from yuxi.services.health_safe_planner_service import (
                authorize_safe_planner_binding,
                validate_safe_planner_history,
            )

            if conversation.agent_id != PLANNER_SLUG:
                raise HealthVisionError("source_invalidated", "单成员安全选择不属于配餐线程", 410)
            await authorize_safe_planner_binding(self.session, binding)
            if preview_history:
                await validate_safe_planner_history(self.session, binding)
            return binding
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
            from yuxi.repositories.health_blood_glucose_repository import HealthBloodGlucoseRepository
            from yuxi.repositories.health_blood_lipids_repository import HealthBloodLipidsRepository

            await HealthFamilyProfileRepository(self.session).validate_history(uid, binding, lock=lock)
            await HealthWeightRepository(self.session).validate_history(uid, binding, lock=lock)
            await HealthBloodPressureRepository(self.session).validate_history(uid, binding, lock=lock)
            await HealthBloodGlucoseRepository(self.session).validate_history(uid, binding, lock=lock)
            await HealthBloodLipidsRepository(self.session).validate_history(uid, binding, lock=lock)
        if conversation.agent_id == ANALYST_SLUG:
            from yuxi.repositories.health_diet_analysis_repository import HealthDietAnalysisRepository
            from yuxi.repositories.health_dialog_feedback_repository import HealthDialogFeedbackRepository

            feedback_repo = HealthDialogFeedbackRepository(self.session)
            selection = await feedback_repo.selection(binding)
            if target_selection is not None:
                from yuxi.services.health_agent_personal_target_service import authorize_personal_target_binding

                if selection is not None:
                    raise HealthVisionError("source_invalidated", "反馈模式不能沿用个人目标选择", 410)
                await authorize_personal_target_binding(self.session, binding)
            if selection is not None:
                await feedback_repo.validate_history(uid, binding, selection)
            else:
                await HealthDietAnalysisRepository(self.session).validate_history(uid, binding)
        elif conversation.agent_id == QUALITY_SLUG:
            from yuxi.repositories.health_quality_repository import HealthQualityRepository

            await HealthQualityRepository(self.session).validate_history(uid, binding)
        return binding

    async def validate_personal_target_runs(self, binding):
        """整线程的派生Run始终依赖固定选择，省略目标工具也不能移除依赖。"""
        from yuxi.services.health_nutrition_service import input_fingerprint

        selected = getattr(binding, "personal_target_selection", None)
        target_hash = AgentRun.input_payload["health_processing"]["personal_target_selection_hash"].as_string()
        condition = target_hash.is_not(None)
        if selected is not None:
            condition = or_(
                target_hash.is_(None),
                target_hash != input_fingerprint(selected),
                AgentRun.uid != binding.actor_uid,
                AgentRun.agent_slug != ANALYST_SLUG,
            )
        invalid = await self.session.scalar(
            select(AgentRun.id).where(AgentRun.conversation_id == binding.conversation_id, condition).limit(1)
        )
        if invalid is not None:
            raise HealthVisionError("source_invalidated", "分析运行的固定个人目标选择已丢失或变更", 410)

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

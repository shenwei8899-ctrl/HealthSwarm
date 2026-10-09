"""健康识图 HTTP 适配层，权限与事务由用例服务执行。"""

from typing import Literal
from datetime import date
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute

from server.utils.auth_middleware import get_admin_user, get_required_user
from yuxi.services.health_vision_service import health_vision_service as service
from yuxi.services.health_consultation_service import create_consultation, create_daily_consultation, list_consultations
from yuxi.services.health_family_planner_types import FamilyPlannerInput
from yuxi.services.health_initial_meal_plan_types import InitialPlannerInput
from yuxi.services.health_safe_planner_types import SafePlannerInput
from yuxi.services.health_daily_service import daily_history, daily_summary
from yuxi.services.health_memory_service import list_member_memory, memory_history, change_member_memory
from yuxi.services.health_memory_types import MemoryPatch, MemoryRevoke
from yuxi.services.health_agent_roles import health_agent_roles
from yuxi.services.health_meal_feedback_types import MealFeedbackChange, MealFeedbackRevoke, FeedbackConversationInput
from yuxi.services.health_meal_feedback_service import meal_feedback, change_meal_feedback
from yuxi.repositories.health_consultation_repository import PLANNER_SLUG, ANALYST_SLUG
from yuxi.services.health_diet_analysis_types import DietAnalysisPeriod, DietAnalysisSelection
from yuxi.services.health_diet_analysis_service import read_diet_analysis, read_period_analysis
from yuxi.services.health_meal_plan_types import (
    MealPlanSpec,
    MealPlanSave,
    MealPlanSwap,
    SafeSwapSelection,
    SafeSwapInput,
    SafeRegenerationSelection,
    SafeRegenerationInput,
)
from yuxi.services.health_safe_meal_swap_service import read_safe_swap_candidates, safe_swap_meal_plan_dish
from yuxi.services.health_safe_plan_regeneration_service import preview_safe_regeneration, regenerate_meal_plan
from yuxi.services.health_initial_meal_plan_types import InitialPlanSelection
from yuxi.services.health_initial_meal_plan_service import (
    create_initial_plan_preview,
    read_initial_plan_preview,
    save_initial_plan,
)
from yuxi.services.health_plan_adoption_types import NextDayProposalInput, PlanAdoptionInput, PlanAdoptionWithdraw
from yuxi.services.health_plan_adoption_service import (
    create_next_day_proposal,
    read_next_day_proposal,
    adopt_meal_plan,
    read_adoption,
    withdraw_adoption,
    current_adopted_plan,
)
from yuxi.services.health_meal_plan_service import (
    create_meal_plan_preview,
    save_meal_plan,
    swap_meal_plan_dish,
    read_meal_plan,
    list_meal_plans,
)
from yuxi.services.health_evidence_service import publish_evidence, revoke_evidence
from yuxi.services.health_evidence_types import NutritionEvidenceInput
from yuxi.services.health_quality_types import (
    ProfileImport,
    RulesImport,
    ReviewerImport,
    QualityCheckInput,
    ReviewActionInput,
    PersonalTargetSelection,
)
from yuxi.services.health_personal_target_service import read_personal_targets
from yuxi.services.health_profile_import_service import read_profile_import_context
from yuxi.services.health_family_profile_service import (
    FamilyProfileLinkInput,
    link_family_profile,
    read_family_profile,
)
from yuxi.services.health_family_meal_plan_types import (
    FamilyMealPlanSpec,
    FamilySafeSelection,
    FamilySafeSwapSelection,
    FamilySafeSwapInput,
    FamilySafeRegenerationInput,
    FamilyParticipationSelection,
    FamilyParticipationInput,
)
from yuxi.services.health_family_participation_service import (
    preview_family_participation,
    change_family_participation,
)
from yuxi.services.health_family_safe_plan_service import (
    read_family_safe_candidates,
    preview_family_regeneration,
    change_family_safe_plan,
)
from yuxi.services.health_dependency_service import (
    import_profile_projection,
    read_profile_projection,
    revoke_profile_projection,
    import_approved_rules,
    read_approved_rules,
    revoke_approved_rules,
    register_professional_reviewer,
    revoke_professional_reviewer,
)
from yuxi.services.health_quality_service import (
    check_saved_plan,
    read_quality_check,
    read_professional_review,
    change_professional_review,
    approved_plan_state,
    create_quality_conversation,
)
from yuxi.services.health_vision_statistics import vision_statistics
from yuxi.services.health_vision_types import (
    ConfirmInput,
    ConsentInput,
    ConsultationInput,
    DraftInput,
    DraftPatch,
    FoodInput,
    GrantInput,
    HealthDTO,
    HealthVisionError,
    MemberInput,
    PortionInput,
    RecipeInput,
    ReportReprocessInput,
    VersionInput,
    VisionConfigurationInput,
    VisionTaskInput,
)
from yuxi.storage.postgres.models_business import User


class HealthRoute(APIRoute):
    """返回受控业务错误，不透出患者正文或供应商响应。"""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def health_handler(request):
            """为健康业务错误加追踪标识。"""
            try:
                return await handler(request)
            except HealthVisionError as exc:
                return JSONResponse(
                    status_code=exc.status,
                    content={
                        "detail": exc.message,
                        "code": exc.code,
                        "message": exc.message,
                        "trace_id": str(uuid4()),
                        "retryable": exc.status in {429, 503},
                    },
                )

        return health_handler


health_vision = APIRouter(prefix="/health/v1", tags=["health-vision"], route_class=HealthRoute)


def require_request_key(request_id: UUID, header: str | None):
    """业务幂等键须与 HTTP 请求头一致。"""
    if header != str(request_id):
        raise HealthVisionError("request_key_mismatch", "Idempotency-Key 必须与 client_request_id 一致")


def require_match(version: int, header: str | None):
    """编辑显式带版本；拒绝省略和不同的 If-Match。"""
    if header != f'"{version}"':
        raise HealthVisionError("version_conflict", "If-Match 必须为当前草稿版本", 409)


@health_vision.post("/members/{member_id}/family-profile-link")
async def family_profile_link(member_id: UUID, data: FamilyProfileLinkInput, user: User = Depends(get_required_user)):
    """本人显式连接已认领的正式档案和健康对象。"""
    return await link_family_profile(user.uid, str(member_id), data)


@health_vision.get("/members/{member_id}/family-profile-link")
async def family_profile_link_read(member_id: UUID, response: Response, user: User = Depends(get_required_user)):
    """回读本人关联事实，重验当前健康及档案访问权。"""
    response.headers["Cache-Control"] = "no-store"
    return await read_family_profile(user.uid, str(member_id), link_only=True)


@health_vision.get("/members/{member_id}/weight-records")
async def member_weight_records(member_id: UUID, response: Response, user: User = Depends(get_required_user)):
    """读取本人的必要实测体重投影，不建立模型处理同意。"""
    from yuxi.services.health_weight_service import read_weight_records

    response.headers["Cache-Control"] = "no-store"
    return await read_weight_records(user.uid, str(member_id))


@health_vision.get("/members/{member_id}/blood-pressure-records")
async def member_blood_pressure_records(member_id: UUID, response: Response, user: User = Depends(get_required_user)):
    """读取本人的必要原始血压投影，不建立模型处理同意。"""
    from yuxi.services.health_blood_pressure_service import read_blood_pressure_records

    response.headers["Cache-Control"] = "no-store"
    return await read_blood_pressure_records(user.uid, str(member_id))


@health_vision.get("/members/{member_id}/blood-glucose-records")
async def member_blood_glucose_records(member_id: UUID, response: Response, user: User = Depends(get_required_user)):
    """读取本人的原始血糖与测量条件，不建立模型处理同意。"""
    from yuxi.services.health_blood_glucose_service import read_blood_glucose_records

    response.headers["Cache-Control"] = "no-store"
    return await read_blood_glucose_records(user.uid, str(member_id))


@health_vision.get("/members/{member_id}/family-profile")
async def family_profile_read(member_id: UUID, response: Response, user: User = Depends(get_required_user)):
    """读取本人确认原档案及专业字段缺口。"""
    response.headers["Cache-Control"] = "no-store"
    return await read_family_profile(user.uid, str(member_id))


@health_vision.get("/members/{member_id}/blood-lipids-records")
async def member_blood_lipids_records(member_id: UUID, response: Response, user: User = Depends(get_required_user)):
    """读取本人同条血脂四项，不建立模型处理同意。"""
    from yuxi.services.health_blood_lipids_service import read_blood_lipids_records

    response.headers["Cache-Control"] = "no-store"
    return await read_blood_lipids_records(user.uid, str(member_id))


@health_vision.get("/configuration")
async def configuration(user: User = Depends(get_required_user)):
    """读取无密钥的功能就绪状态。"""
    return await service.configuration()


@health_vision.post("/members/{member_id}/meal-planner", status_code=201)
async def create_planner(member_id: UUID, data: ConsultationInput, user: User = Depends(get_required_user)):
    """创建固定成员配餐线程，实际模型调用仍需独立用途同意。"""
    return await create_consultation(str(user.uid), str(member_id), data, agent_slug=PLANNER_SLUG)


@health_vision.post("/members/{member_id}/initial-meal-planner", status_code=201)
async def create_initial_planner(member_id: UUID, data: InitialPlannerInput, user: User = Depends(get_required_user)):
    """用户明确初始范围，所有实际参与者须独立授权与配餐同意。"""
    return await create_consultation(
        str(user.uid),
        str(member_id),
        data,
        agent_slug=PLANNER_SLUG,
        initial_selection=data.model_dump(mode="json", exclude={"client_request_id"}),
    )


@health_vision.post("/members/{member_id}/family-meal-planner", status_code=201)
async def create_family_planner(member_id: UUID, data: FamilyPlannerInput, user: User = Depends(get_required_user)):
    """创建不可变家庭选择线程，所有涉及成员须授权并同意独立配餐用途。"""
    return await create_consultation(
        str(user.uid),
        str(member_id),
        data,
        agent_slug=PLANNER_SLUG,
        family_selection=data.model_dump(mode="json", exclude={"client_request_id"}),
    )


@health_vision.post("/members/{member_id}/safe-meal-plan-conversations", status_code=201)
async def create_safe_planner(member_id: UUID, data: SafePlannerInput, user: User = Depends(get_required_user)):
    """绑定单成员当前已保存餐单，Agent仅提供安全改版预览。"""
    return await create_consultation(
        str(user.uid),
        str(member_id),
        data,
        agent_slug=PLANNER_SLUG,
        safe_selection=data.model_dump(mode="json", exclude={"client_request_id"}),
    )


@health_vision.post("/members/{member_id}/diet-analyst", status_code=201)
async def create_analyst(member_id: UUID, data: ConsultationInput, user: User = Depends(get_required_user)):
    """创建固定成员分析线程，调用模型须独立用途审批与同意。"""
    return await create_consultation(str(user.uid), str(member_id), data, agent_slug=ANALYST_SLUG)


@health_vision.post("/diet-logs/{record_id}/feedback-conversation", status_code=201)
async def create_feedback_conversation(
    record_id: UUID, data: FeedbackConversationInput, user: User = Depends(get_required_user)
):
    """用户显式选餐建立不可变反馈来源，模型不能调用此业务入口。"""
    from yuxi.services.health_dialog_feedback_service import create_feedback_conversation

    return await create_feedback_conversation(str(user.uid), str(record_id), data)


@health_vision.post("/members/{member_id}/diet-analysis")
async def diet_analysis(member_id: UUID, data: DietAnalysisSelection, user: User = Depends(get_required_user)):
    """从已确认单餐读取分析，无模型调用和业务记录写入。"""
    return await read_diet_analysis(str(user.uid), str(member_id), data)


@health_vision.post("/members/{member_id}/diet-period-analysis")
async def diet_period_analysis(member_id: UUID, data: DietAnalysisPeriod, user: User = Depends(get_required_user)):
    """按自然日读取有效确认饮食与反馈，缺失不补零。"""
    return await read_period_analysis(str(user.uid), str(member_id), data)


@health_vision.post("/members/{member_id}/external-profile-versions", status_code=201)
async def import_external_profile(member_id: UUID, data: ProfileImport, user: User = Depends(get_admin_user)):
    """登记外部确认版本，服务仍复核管理员与成员编辑权限。"""
    return await import_profile_projection(user.uid, str(member_id), data)


@health_vision.get("/members/{member_id}/profile-import-context")
async def profile_import_context(
    member_id: UUID,
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_admin_user),
):
    """读取专业导入上下文，原始来源仍受当前家庭字段授权。"""
    response.headers["Cache-Control"] = "no-store"
    return await read_profile_import_context(user.uid, str(member_id), limit=limit, offset=offset)


@health_vision.get("/members/{member_id}/external-profile-versions/current")
async def current_external_profile(member_id: UUID, user: User = Depends(get_required_user)):
    """读取当前已授权的营养安全档案投影。"""
    return await read_profile_projection(user.uid, str(member_id))


@health_vision.post("/members/{member_id}/external-profile-versions/{version}/revoke")
async def revoke_external_profile(member_id: UUID, version: int, user: User = Depends(get_admin_user)):
    """撤回外部版本并使对应未固定审核失效。"""
    return await revoke_profile_projection(user.uid, str(member_id), version)


@health_vision.post("/approved-quality-rules", status_code=201)
async def import_quality_rules(data: RulesImport, user: User = Depends(get_admin_user)):
    """登记专业内容方已批准规则版本。"""
    return await import_approved_rules(user.uid, data)


@health_vision.get("/approved-quality-rules/{rule_code}")
async def current_quality_rules(rule_code: str, user: User = Depends(get_required_user)):
    """规则目录不提供成员资料。"""
    return await read_approved_rules(user.uid, rule_code)


@health_vision.post("/approved-quality-rules/{rule_code}/versions/{version}/revoke")
async def revoke_quality_rules(rule_code: str, version: int, user: User = Depends(get_admin_user)):
    """撤回批准规则版本。"""
    return await revoke_approved_rules(user.uid, rule_code, version)


@health_vision.post("/professional-reviewers", status_code=201)
async def register_quality_reviewer(data: ReviewerImport, user: User = Depends(get_admin_user)):
    """另一位管理员登记专业资格来源。"""
    return await register_professional_reviewer(user.uid, data)


@health_vision.post("/professional-reviewers/{reviewer_uid}/versions/{version}/revoke")
async def revoke_quality_reviewer(reviewer_uid: str, version: int, user: User = Depends(get_admin_user)):
    """撤回专业资格及相应批准。"""
    return await revoke_professional_reviewer(user.uid, reviewer_uid, version)


@health_vision.post("/meal-plans/{plan_id}/quality-checks", status_code=201)
async def run_plan_quality_check(plan_id: UUID, data: QualityCheckInput, user: User = Depends(get_required_user)):
    """对用户选定保存方案执行确定性检查。"""
    return await check_saved_plan(user.uid, str(plan_id), data)


@health_vision.post("/meal-plans/{plan_id}/quality-conversation", status_code=201)
async def bind_plan_quality_agent(plan_id: UUID, data: QualityCheckInput, user: User = Depends(get_required_user)):
    """不可变业务选择绑定独立质量Agent。"""
    return await create_quality_conversation(user.uid, str(plan_id), data)


@health_vision.get("/quality-checks/{check_id}")
async def plan_quality_result(check_id: UUID, user: User = Depends(get_required_user)):
    """回读检查及专业流程的当前有效性。"""
    return await read_quality_check(user.uid, str(check_id))


@health_vision.get("/professional-reviews/{review_id}")
async def professional_review_result(review_id: UUID, user: User = Depends(get_required_user)):
    """申请人或有授权专业人员查看审核历史。"""
    return await read_professional_review(user.uid, str(review_id))


@health_vision.post("/professional-reviews/{review_id}/{action}")
async def perform_professional_review(
    review_id: UUID,
    action: Literal["submit", "return", "approve"],
    data: ReviewActionInput,
    user: User = Depends(get_required_user),
):
    """专业动作授权由服务执行，模型不能调用。"""
    return await change_professional_review(user.uid, str(review_id), action, data)


@health_vision.get("/meal-plans/{plan_id}/approval-state")
async def current_plan_approval(plan_id: UUID, version: int = Query(gt=0), user: User = Depends(get_required_user)):
    """仅当前对象及依赖版本的批准可供采用。"""
    return await approved_plan_state(user.uid, str(plan_id), version)


@health_vision.post("/members/{member_id}/meal-plan-previews", status_code=201)
async def plan_preview(member_id: UUID, data: MealPlanSpec, user: User = Depends(get_required_user)):
    """纯计算预览不向模型外发数据，不代替已审核个人方案。"""
    return await create_meal_plan_preview(str(user.uid), str(member_id), data)


@health_vision.post("/members/{member_id}/family-meal-plan-previews", status_code=201)
async def family_plan_preview(member_id: UUID, data: FamilyMealPlanSpec, user: User = Depends(get_required_user)):
    """逐成员明确餐次份量，服务端复算不外发模型。"""
    return await create_meal_plan_preview(str(user.uid), str(member_id), data)


@health_vision.post("/members/{member_id}/meal-plans", status_code=201)
async def save_plan(
    member_id: UUID,
    data: MealPlanSave,
    user: User = Depends(get_required_user),
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """幂等保存已有服务器预览。"""
    require_request_key(data.client_request_id, request_key)
    return await save_meal_plan(str(user.uid), str(member_id), data)


@health_vision.post("/members/{member_id}/initial-meal-plan-previews")
async def initial_plan_preview(member_id: UUID, data: InitialPlanSelection, user: User = Depends(get_required_user)):
    """当前批准菜单首次生成三餐，未就绪明确返回原因。"""
    return await create_initial_plan_preview(str(user.uid), str(member_id), data)


@health_vision.get("/initial-meal-plan-previews/{preview_id}")
async def read_initial_preview(preview_id: UUID, user: User = Depends(get_required_user)):
    """读取私有回执前重新核对全部来源。"""
    return await read_initial_plan_preview(str(user.uid), str(preview_id))


@health_vision.post("/members/{member_id}/initial-meal-plans", status_code=201)
async def save_initial_meal_plan(
    member_id: UUID,
    data: MealPlanSave,
    user: User = Depends(get_required_user),
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """用户确认生成回执，一次创建初版与专业待审检查。"""
    require_request_key(data.client_request_id, request_key)
    return await save_initial_plan(str(user.uid), str(member_id), data)


@health_vision.get("/members/{member_id}/meal-plans")
async def member_plans(member_id: UUID, user: User = Depends(get_required_user)):
    """读取当前账号维护的成员餐单草稿。"""
    return await list_meal_plans(str(user.uid), str(member_id))


@health_vision.post("/members/{member_id}/next-day-proposals", status_code=201)
async def next_day_proposal(member_id: UUID, data: NextDayProposalInput, user=Depends(get_required_user)):
    """登记明确的次日预览，不保存正式计划。"""
    return await create_next_day_proposal(str(user.uid), str(member_id), data)


@health_vision.get("/next-day-proposals/{proposal_id}")
async def get_next_day_proposal(proposal_id: UUID, user=Depends(get_required_user)):
    """次日提议来源失效时返回明确状态。"""
    return await read_next_day_proposal(str(user.uid), str(proposal_id))


@health_vision.post("/meal-plans/{plan_id}/adopt", status_code=201)
async def adopt_plan(plan_id: UUID, data: PlanAdoptionInput, user=Depends(get_required_user)):
    """业务采用携带当前餐单、专业批准与档案版本。"""
    return await adopt_meal_plan(str(user.uid), str(plan_id), data)


@health_vision.get("/meal-plan-adoptions/{adoption_id}")
async def get_plan_adoption(adoption_id: UUID, user=Depends(get_required_user)):
    """读取当前使用状态和原采用快照。"""
    return await read_adoption(str(user.uid), str(adoption_id))


@health_vision.post("/meal-plan-adoptions/{adoption_id}/withdraw")
async def withdraw_plan_adoption(adoption_id: UUID, data: PlanAdoptionWithdraw, user=Depends(get_required_user)):
    """版本化取消采用并保留原计划及历史。"""
    return await withdraw_adoption(str(user.uid), str(adoption_id), data)


@health_vision.get("/members/{member_id}/adopted-plan")
async def get_current_adopted_plan(member_id: UUID, plan_date: date, user=Depends(get_required_user)):
    """按明确日期读取唯一有效采用，不从草稿猜测今日来源。"""
    return await current_adopted_plan(str(user.uid), str(member_id), plan_date)


@health_vision.get("/meal-plans/{plan_id}")
async def get_plan(plan_id: UUID, user: User = Depends(get_required_user)):
    """读取当前版本及历史。"""
    return await read_meal_plan(str(user.uid), str(plan_id))


@health_vision.post("/meal-plans/{plan_id}/swap")
async def swap_plan(
    plan_id: UUID,
    data: MealPlanSwap,
    user: User = Depends(get_required_user),
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    match: str | None = Header(default=None, alias="If-Match"),
):
    """当前版本的显式换菜，不允许客户端覆盖营养值。"""
    require_request_key(data.client_request_id, request_key)
    require_match(data.version, match)
    return await swap_meal_plan_dish(str(user.uid), str(plan_id), data)


@health_vision.post("/meal-plans/{plan_id}/swap-candidates")
async def safe_swap_candidates(plan_id: UUID, data: SafeSwapSelection, user: User = Depends(get_required_user)):
    """按批准条款读取三道以内的安全候选，不修改原餐单。"""
    return await read_safe_swap_candidates(str(user.uid), str(plan_id), data)


@health_vision.post("/meal-plans/{plan_id}/safe-swap")
async def safe_swap_plan(
    plan_id: UUID,
    data: SafeSwapInput,
    user: User = Depends(get_required_user),
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    match: str | None = Header(default=None, alias="If-Match"),
):
    """明确选择当前候选，重算安全并使旧专业批准失效。"""
    require_request_key(data.client_request_id, request_key)
    require_match(data.version, match)
    return await safe_swap_meal_plan_dish(str(user.uid), str(plan_id), data)


@health_vision.post("/meal-plans/{plan_id}/regeneration-preview")
async def regeneration_preview(plan_id: UUID, data: SafeRegenerationSelection, user: User = Depends(get_required_user)):
    """整份安全重生成预览，不修改原餐单。"""
    return await preview_safe_regeneration(str(user.uid), str(plan_id), data)


@health_vision.post("/meal-plans/{plan_id}/safe-regenerate")
async def safe_regenerate_plan(
    plan_id: UUID,
    data: SafeRegenerationInput,
    user: User = Depends(get_required_user),
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    match: str | None = Header(default=None, alias="If-Match"),
):
    """确认当前服务器摘要，一次保存三餐并重新检查。"""
    require_request_key(data.client_request_id, request_key)
    require_match(data.version, match)
    return await regenerate_meal_plan(str(user.uid), str(plan_id), data)


@health_vision.post("/members/{member_id}/nutrition-targets")
async def member_nutrition_targets(
    member_id: UUID, data: PersonalTargetSelection, user: User = Depends(get_required_user)
):
    """读取当前批准公式计算的个人目标及来源，不写档案。"""
    return await read_personal_targets(str(user.uid), str(member_id), data)


@health_vision.post("/meal-plans/{plan_id}/family-swap-candidates")
async def family_swap_candidates(plan_id: UUID, data: FamilySafeSwapSelection, user: User = Depends(get_required_user)):
    """读取逐人当前版本约束下的合格共同菜品。"""
    return await read_family_safe_candidates(str(user.uid), str(plan_id), data)


@health_vision.post("/meal-plans/{plan_id}/family-safe-swap")
async def family_safe_swap(
    plan_id: UUID,
    data: FamilySafeSwapInput,
    user: User = Depends(get_required_user),
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    match: str | None = Header(default=None, alias="If-Match"),
):
    """明确选菜并复核所有成员，保存新的家庭修订。"""
    require_request_key(data.client_request_id, request_key)
    require_match(data.version, match)
    return await change_family_safe_plan(str(user.uid), str(plan_id), data, swap=True)


@health_vision.post("/meal-plans/{plan_id}/family-regeneration-preview")
async def family_regeneration_preview(
    plan_id: UUID, data: FamilySafeSelection, user: User = Depends(get_required_user)
):
    """只读共同修复预览，保留每位成员份量和参与餐次。"""
    return await preview_family_regeneration(str(user.uid), str(plan_id), data)


@health_vision.post("/meal-plans/{plan_id}/family-safe-regenerate")
async def family_safe_regenerate(
    plan_id: UUID,
    data: FamilySafeRegenerationInput,
    user: User = Depends(get_required_user),
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    match: str | None = Header(default=None, alias="If-Match"),
):
    """确认当前摘要，家庭改版、检查及旧批准失效共同提交。"""
    require_request_key(data.client_request_id, request_key)
    require_match(data.version, match)
    return await change_family_safe_plan(str(user.uid), str(plan_id), data, swap=False)


@health_vision.post("/meal-plans/{plan_id}/family-participation-preview")
async def family_participation_preview(
    plan_id: UUID, data: FamilyParticipationSelection, user: User = Depends(get_required_user)
):
    """只读试算参加成员和份量调整，保留原菜谱和日期。"""
    return await preview_family_participation(str(user.uid), str(plan_id), data)


@health_vision.post("/meal-plans/{plan_id}/family-participation")
async def family_participation_change(
    plan_id: UUID,
    data: FamilyParticipationInput,
    user: User = Depends(get_required_user),
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    match: str | None = Header(default=None, alias="If-Match"),
):
    """确认摘要后写入新版本，检查和旧批准/采用失效同事务。"""
    require_request_key(data.client_request_id, request_key)
    require_match(data.version, match)
    return await change_family_participation(str(user.uid), str(plan_id), data)


@health_vision.get("/agent-roles")
async def agent_roles(user: User = Depends(get_required_user)):
    """展示当前实现边界，待实现角色不开放执行入口。"""
    return health_agent_roles()


@health_vision.post("/members/{member_id}/daily-consultations", status_code=201)
async def daily_consultation(member_id: UUID, user: User = Depends(get_required_user)):
    """服务器创建或复用当前北京时间日期的成员专属会话。"""
    return await create_daily_consultation(user.uid, str(member_id))


@health_vision.get("/members/{member_id}/daily-conversations")
async def daily_conversations(member_id: UUID, before: date | None = None, user: User = Depends(get_required_user)):
    """按日期分页查询当前账号的成员会话。"""
    return await daily_history(user.uid, str(member_id), before)


@health_vision.get("/daily-conversations/{thread_id}/summary")
async def read_daily_summary(thread_id: UUID, user: User = Depends(get_required_user)):
    """来源失效或晚到结果变更时隐藏旧摘要。"""
    return await daily_summary(user.uid, str(thread_id))


@health_vision.post("/daily-conversations/{thread_id}/summary")
async def refresh_daily_summary(thread_id: UUID, user: User = Depends(get_required_user)):
    """手动补跑沿用与 worker 相同的原子发布用例。"""
    return await daily_summary(user.uid, str(thread_id), refresh=True)


@health_vision.get("/members/{member_id}/memory")
async def member_memories(member_id: UUID, user: User = Depends(get_required_user)):
    """查看自己维护的有效成员自述。"""
    return await list_member_memory(user.uid, str(member_id))


@health_vision.get("/memory/{memory_id}")
async def read_memory_history(memory_id: UUID, user: User = Depends(get_required_user)):
    """查看记忆修订及来源。"""
    return await memory_history(user.uid, str(memory_id))


@health_vision.patch("/memory/{memory_id}")
async def edit_member_memory(
    memory_id: UUID,
    data: MemoryPatch,
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: User = Depends(get_required_user),
):
    """用户显式编辑，保留版本与自述状态。"""
    require_request_key(data.client_request_id, request_key)
    require_match(data.version, if_match)
    return await change_member_memory(user.uid, str(memory_id), data)


@health_vision.delete("/memory/{memory_id}")
async def delete_member_memory(
    memory_id: UUID,
    data: MemoryRevoke,
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: User = Depends(get_required_user),
):
    """删除即撤回未来召回，保留不可变操作收据。"""
    require_request_key(data.client_request_id, request_key)
    require_match(data.version, if_match)
    return await change_member_memory(user.uid, str(memory_id), data, revoke=True)


@health_vision.post("/memory/{memory_id}/revoke")
async def revoke_member_memory(
    memory_id: UUID,
    data: MemoryRevoke,
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: User = Depends(get_required_user),
):
    """对话撤回入口与删除共用事实及幂等语义。"""
    require_request_key(data.client_request_id, request_key)
    require_match(data.version, if_match)
    return await change_member_memory(user.uid, str(memory_id), data, revoke=True)


@health_vision.post("/nutrition-evidence", status_code=201)
async def publish_nutrition_evidence(data: NutritionEvidenceInput, user: User = Depends(get_admin_user)):
    """管理员登记已专业审核的通用科普版本和凭据。"""
    return await publish_evidence(user.uid, data)


@health_vision.delete("/nutrition-evidence/{evidence_id}")
async def revoke_nutrition_evidence(evidence_id: UUID, user: User = Depends(get_admin_user)):
    """撤回版本并使依赖该来源的历史咨询引用失效。"""
    return await revoke_evidence(user.uid, str(evidence_id))


@health_vision.put("/configuration")
async def configure(data: VisionConfigurationInput, user: User = Depends(get_admin_user)):
    """管理员审批模型和处理政策。"""
    return await service.configure(user.uid, data)


@health_vision.get("/members")
async def members(user: User = Depends(get_required_user)):
    """列出当前账号的授权成员。"""
    return await service.members(user.uid)


@health_vision.post("/members", status_code=201)
async def create_member(data: MemberInput, user: User = Depends(get_required_user)):
    """创建明确获得代理依据的成员档案。"""
    return await service.create_member(user.uid, data)


@health_vision.put("/members/{member_id}/grants")
async def grant(member_id: UUID, data: GrantInput, user: User = Depends(get_required_user)):
    """授予或撤回成员访问范围。"""
    return await service.grant(user.uid, str(member_id), data)


@health_vision.post("/members/{member_id}/processing-consents")
async def consent(member_id: UUID, data: ConsentInput, user: User = Depends(get_required_user)):
    """按用途和政策记录处理同意或撤回。"""
    return await service.consent(user.uid, str(member_id), data)


@health_vision.get("/members/{member_id}/consultations")
async def consultation_list(
    member_id: UUID,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_required_user),
):
    """读取当前成员的咨询列表，不返回正文或工具数据。"""
    return await list_consultations(user.uid, str(member_id), limit=limit, offset=offset)


@health_vision.post("/members/{member_id}/consultations", status_code=201)
async def consultation(
    member_id: UUID,
    data: ConsultationInput,
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_required_user),
):
    """只创建固定成员会话；实际咨询另行校验用途与模型审批。"""
    require_request_key(data.client_request_id, request_key)
    return await create_consultation(user.uid, str(member_id), data)


@health_vision.post("/uploads", status_code=201)
async def upload(
    member_id: UUID = Form(...),
    purpose: Literal["report", "meal"] = Form(...),
    file: UploadFile = File(...),
    rotation: Literal["0", "90", "180", "270"] = Form(default="0"),
    deskew_angle: float = Form(default=0, ge=-10, le=10, allow_inf_nan=False),
    user: User = Depends(get_required_user),
):
    """有限额地读取上传字节，不接收任意外部 URL。"""
    try:
        data = await file.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise HealthVisionError("file_too_large", "文件不能超过 20MB", 413)
        return await service.upload(
            user.uid, str(member_id), purpose, data, rotation=int(rotation), deskew_angle=deskew_angle
        )
    finally:
        await file.close()


@health_vision.get("/uploads/{upload_id}/preview")
async def preview(
    upload_id: UUID, page_index: int | None = Query(default=None, ge=0, le=19), user: User = Depends(get_required_user)
):
    """禁止共享缓存的鉴权文件响应。"""
    data, mime = await service.preview(user.uid, str(upload_id), page_index)
    return Response(
        content=data,
        media_type=mime,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@health_vision.delete("/uploads/{upload_id}")
async def delete_upload(upload_id: UUID, user: User = Depends(get_required_user)):
    """失效源文件及其派生记录，再删除私有对象。"""
    return await service.delete_upload(user.uid, str(upload_id))


@health_vision.post("/report-tasks", status_code=202)
async def report_task(
    data: VisionTaskInput,
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_required_user),
):
    """提交报告异步提取任务。"""
    require_request_key(data.client_request_id, request_key)
    return await service.create_task(user.uid, "report", data)


@health_vision.post("/meal-photo-tasks", status_code=202)
async def meal_task(
    data: VisionTaskInput,
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_required_user),
):
    """提交同一餐的多视角识别任务。"""
    require_request_key(data.client_request_id, request_key)
    return await service.create_task(user.uid, "meal", data)


@health_vision.post("/report-page-tasks", status_code=202)
async def report_page_task(
    data: ReportReprocessInput,
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    match: str | None = Header(default=None, alias="If-Match"),
    user: User = Depends(get_required_user),
):
    """版本化重识别当前报告失败页，源文件由草稿确定。"""
    require_request_key(data.client_request_id, request_key)
    require_match(data.version, match)
    return await service.reprocess_report(user.uid, data)


@health_vision.get("/members/{member_id}/vision")
async def jobs(member_id: UUID, user: User = Depends(get_required_user)):
    """恢复任务与未确认草稿。"""
    return await service.jobs(user.uid, str(member_id))


@health_vision.get("/members/{member_id}/vision-statistics")
async def statistics(member_id: UUID, kind: Literal["report", "meal"], user: User = Depends(get_required_user)):
    """读取已授权成员及用途的运行摘要，不包含健康正文。"""
    return await vision_statistics(user.uid, str(member_id), kind)


@health_vision.get("/vision-tasks/{task_id}")
async def job(task_id: str, user: User = Depends(get_required_user)):
    """读取授权任务及处理页。"""
    return await service.get_job(user.uid, task_id)


@health_vision.post("/vision-tasks/{task_id}/cancel")
async def cancel(task_id: str, user: User = Depends(get_required_user)):
    """持久化尽力取消，最终状态仍以 PG 为准。"""
    return await service.cancel(user.uid, task_id)


class RetryInput(HealthDTO):
    """显式重试使用新的请求标识。"""

    client_request_id: UUID


@health_vision.post("/vision-tasks/{task_id}/retry", status_code=202)
async def retry(
    task_id: str,
    data: RetryInput,
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_required_user),
):
    """失败任务新建 attempt。"""
    require_request_key(data.client_request_id, request_key)
    return await service.retry(user.uid, task_id, data.client_request_id)


@health_vision.post("/manual-drafts", status_code=201)
async def manual_draft(data: DraftInput, user: User = Depends(get_required_user)):
    """手工录入真实候选而非伪造识别成功。"""
    return await service.manual_draft(user.uid, data)


@health_vision.get("/report-extractions/{draft_id}")
async def report_draft(draft_id: UUID, user: User = Depends(get_required_user)):
    """读取报告复核版本。"""
    return await service.get_draft(user.uid, str(draft_id), "report")


@health_vision.get("/meal-drafts/{draft_id}")
async def meal_draft(draft_id: UUID, user: User = Depends(get_required_user)):
    """读取一餐复核版本。"""
    return await service.get_draft(user.uid, str(draft_id), "meal")


@health_vision.patch("/report-extractions/{draft_id}")
async def patch_report(
    draft_id: UUID,
    data: DraftPatch,
    match: str | None = Header(default=None, alias="If-Match"),
    user: User = Depends(get_required_user),
):
    """版本化修改报告候选。"""
    require_match(data.version, match)
    return await service.patch_draft(user.uid, str(draft_id), "report", data)


@health_vision.patch("/meal-drafts/{draft_id}")
async def patch_meal(
    draft_id: UUID,
    data: DraftPatch,
    match: str | None = Header(default=None, alias="If-Match"),
    user: User = Depends(get_required_user),
):
    """纠错或改量，使旧预览失效。"""
    require_match(data.version, match)
    return await service.patch_draft(user.uid, str(draft_id), "meal", data)


@health_vision.post("/meal-drafts/{draft_id}/calculate")
async def calculate(draft_id: UUID, data: VersionInput, user: User = Depends(get_required_user)):
    """生成当前草稿的确定性营养快照。"""
    return await service.calculate(user.uid, str(draft_id), data.version)


@health_vision.post("/report-extractions/{draft_id}/confirm")
async def confirm_report(
    draft_id: UUID,
    data: ConfirmInput,
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_required_user),
):
    """人工确认后一次追加正式指标。"""
    require_request_key(data.client_request_id, request_key)
    return await service.confirm(user.uid, str(draft_id), "report", data)


@health_vision.post("/meal-drafts/{draft_id}/confirm")
async def confirm_meal(
    draft_id: UUID,
    data: ConfirmInput,
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_required_user),
):
    """确认当前计算，一次写入饮食日记。"""
    require_request_key(data.client_request_id, request_key)
    return await service.confirm(user.uid, str(draft_id), "meal", data)


@health_vision.get("/members/{member_id}/observations")
async def observations(member_id: UUID, user: User = Depends(get_required_user)):
    """读取已确认指标。"""
    return await service.records(user.uid, str(member_id), "report")


@health_vision.get("/members/{member_id}/diet-logs")
async def diet_logs(member_id: UUID, user: User = Depends(get_required_user)):
    """读取已确认饮食日记。"""
    return await service.records(user.uid, str(member_id), "meal")


@health_vision.get("/foods")
async def foods(q: str = Query(default="", max_length=120), user: User = Depends(get_required_user)):
    """搜索带来源和版本的已发布食品。"""
    return await service.foods(q)


@health_vision.post("/foods", status_code=201)
async def publish_food(data: FoodInput, user: User = Depends(get_admin_user)):
    """管理员审核发布食品数据，不自动导入商用数据。"""
    return await service.publish_food(user.uid, data)


@health_vision.get("/recipes")
async def recipes(q: str = Query(default="", max_length=120), user: User = Depends(get_required_user)):
    """搜索已发布食谱版本。"""
    return await service.recipes(q)


@health_vision.post("/recipes", status_code=201)
async def publish_recipe(data: RecipeInput, user: User = Depends(get_admin_user)):
    """审核发布配方、成品重及其推导营养。"""
    return await service.publish_recipe(user.uid, data)


@health_vision.get("/portion-references")
async def portions(
    food_id: UUID | None = None, recipe_version_id: UUID | None = None, user: User = Depends(get_required_user)
):
    """按明确版本查询适用的碗勺规格。"""
    return await service.portions(
        str(food_id) if food_id else None, str(recipe_version_id) if recipe_version_id else None
    )


@health_vision.post("/portion-references", status_code=201)
async def publish_portion(data: PortionInput, user: User = Depends(get_admin_user)):
    """审核发布实测参考及适用范围。"""
    return await service.publish_portion(user.uid, data)


@health_vision.get("/diet-logs/{record_id}/feedback")
async def get_diet_feedback(record_id: UUID, user: User = Depends(get_required_user)):
    """读取当前账号在指定餐次的反馈及修订。"""
    return await meal_feedback(user.uid, str(record_id))


@health_vision.put("/diet-logs/{record_id}/feedback")
async def put_diet_feedback(
    record_id: UUID,
    data: MealFeedbackChange,
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: User = Depends(get_required_user),
):
    """按当前版本创建或修改单餐反馈。"""
    require_request_key(data.client_request_id, request_key)
    require_match(data.version, if_match)
    return await change_meal_feedback(user.uid, str(record_id), data)


@health_vision.post("/diet-logs/{record_id}/feedback/revoke")
async def revoke_diet_feedback(
    record_id: UUID,
    data: MealFeedbackRevoke,
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: User = Depends(get_required_user),
):
    """撤回反馈并使旧版本模型依赖失效。"""
    require_request_key(data.client_request_id, request_key)
    require_match(data.version, if_match)
    return await change_meal_feedback(user.uid, str(record_id), data, revoke=True)

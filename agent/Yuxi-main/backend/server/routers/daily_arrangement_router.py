"""原小程序云端建档和每日安排的薄HTTP适配。"""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from server.routers.health_vision_router import HealthRoute
from server.utils.auth_middleware import get_admin_user, get_required_user
from yuxi.services.daily_arrangement_service import (
    read_daily_arrangement,
    start_daily_arrangement,
    change_daily_members,
    publish_daily_purchase,
    read_daily_purchase,
)
from yuxi.services.daily_arrangement_projection import save_recipe_commerce_source
from yuxi.services.daily_arrangement_purchase import (
    read_daily_summary,
    publish_daily_summary,
)
from yuxi.services.daily_arrangement_tasks import request_daily_resume
from yuxi.services.onboarding_preparation_service import (
    OnboardingPreparationInput,
    SavedPreparationInput,
    start_saved_preparation,
    start_onboarding_preparation,
    read_onboarding_preparation,
    resume_onboarding_preparation,
)
from yuxi.services.miniapp_profile_service import (
    read_miniapp_profile,
    save_miniapp_profile,
    start_miniapp_analysis,
)
from yuxi.services.miniapp_profile_types import (
    MiniappProfileInput,
    MiniappAnalysisInput,
    MiniappConsultationOpenInput,
)
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.commerce_sku_selection import RecipeSkuBinding
from yuxi.services.health_knowledge_import_service import (
    KnowledgeNutritionInput,
    prepare_knowledge_nutrition,
    read_knowledge_nutrition,
)
from yuxi.services.health_nutrition_import_types import NutritionImportInput
from yuxi.services.health_nutrition_import_service import (
    prepare_nutrition_import,
    read_nutrition_import,
)
from yuxi.services.daily_nutrition_setup import (
    daily_setup_readiness,
    read_recipe_commerce_source,
)


async def private_response(response: Response):
    """健康数据不允许公共缓存。"""
    response.headers["Cache-Control"] = "no-store"


daily_arrangement = APIRouter(
    tags=["daily-arrangement"],
    route_class=HealthRoute,
    dependencies=[Depends(private_response)],
)


class DailyStartInput(BaseModel):
    """日期和原请求键，不接受客户端模型结果。"""

    model_config = ConfigDict(extra="forbid")
    client_request_id: UUID
    date: date


class DailyMemberInput(BaseModel):
    """只允许明确调整某一餐的参与者。"""

    model_config = ConfigDict(extra="forbid")
    client_request_id: UUID
    version: int = Field(gt=0)
    daily_plan_version: int | None = Field(default=None, ge=0)
    meal: Literal["breakfast", "lunch", "dinner"]
    member_ids: list[UUID] = Field(min_length=1, max_length=20)


class DailyPurchaseInput(BaseModel):
    """发布采购只引用服务端已保存的餐次版本。"""

    model_config = ConfigDict(extra="forbid")
    arrangement_id: UUID
    version: int = Field(gt=0)
    daily_plan_version: int | None = Field(default=None, ge=0)


class DailyReferencePurchaseInput(BaseModel):
    """采购引用当前计划版本和已有参考结果。"""

    model_config = ConfigDict(extra="forbid")
    preview_id: UUID
    version: int = Field(ge=0)
    meal_types: list[Literal["breakfast", "lunch", "dinner"]] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def unique_meal_types(self):
        """采购餐次只能各出现一次。"""
        if len(self.meal_types) != len(set(self.meal_types)):
            raise ValueError("采购餐次不能重复")
        return self


class DailySummaryInput(DailyPurchaseInput):
    """汇总仅接受已保存餐次，不能上传采购数量或价格。"""

    meals: list[Literal["breakfast", "lunch", "dinner"]] = Field(min_length=1, max_length=3)


class RecipeCommerceInput(BaseModel):
    """真实做法和标准食材编码由管理端发布，不按菜名关联。"""

    model_config = ConfigDict(extra="forbid")
    recipe_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_ref: str = Field(min_length=1, max_length=500)
    steps: list[str] = Field(min_length=1, max_length=100)
    ingredient_codes: dict[UUID, str | RecipeSkuBinding]
    dish_type_code: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_.:-]{1,80}$")
    allowed_meal_types: list[Literal["breakfast", "lunch", "dinner"]] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def explicit_classification(self):
        """配方分类与适用餐次一并发布，不能提供半份依据。"""
        if bool(self.dish_type_code) != bool(self.allowed_meal_types) or len(set(self.allowed_meal_types)) != len(
            self.allowed_meal_types
        ):
            raise ValueError("菜品类型与适用餐次须明确且不重复")
        return self


def require_key(client_id, header):
    """HTTP重放不能换成另一个业务请求键。"""
    if header != str(client_id):
        raise HealthVisionError("request_key_required", "保存请求标识不一致", 422)


@daily_arrangement.get("/family/{fid}/miniapp-profile")
async def profile_get(fid: UUID, user=Depends(get_required_user)):
    """读取原页面需要的云端档案。"""
    return await read_miniapp_profile(str(user.uid), str(fid))


@daily_arrangement.post("/family/{fid}/miniapp-profile")
async def profile_save(
    fid: UUID,
    data: MiniappProfileInput | MiniappAnalysisInput | MiniappConsultationOpenInput,
    key: str | None = Header(default=None, alias="Idempotency-Key"),
    user=Depends(get_required_user),
):
    """同键保存完整建档。"""
    require_key(data.client_request_id, key)
    if isinstance(data, (MiniappAnalysisInput, MiniappConsultationOpenInput)):
        return await start_miniapp_analysis(str(user.uid), str(fid), data)
    return await save_miniapp_profile(str(user.uid), str(fid), data)


@daily_arrangement.post("/family/{fid}/onboarding-preparations")
async def preparation_start(
    fid: UUID,
    data: OnboardingPreparationInput,
    key: str | None = Header(default=None, alias="Idempotency-Key"),
    user=Depends(get_required_user),
):
    """一次提交保存档案并登记后台准备。"""
    require_key(data.client_request_id, key)
    return await start_onboarding_preparation(str(user.uid), str(fid), data)


@daily_arrangement.get("/family/{fid}/onboarding-preparations/current")
async def preparation_current(fid: UUID, user=Depends(get_required_user)):
    """重进找回准备，不触发模型。"""
    return await read_onboarding_preparation(str(user.uid), str(fid))


@daily_arrangement.post("/family/{fid}/onboarding-preparations/from-profile")
async def preparation_from_profile(
    fid: UUID,
    data: SavedPreparationInput,
    key: str | None = Header(default=None, alias="Idempotency-Key"),
    user=Depends(get_required_user),
):
    """从当前已保存档案准备，不能借恢复入口修改家庭资料。"""
    require_key(data.client_request_id, key)
    return await start_saved_preparation(str(user.uid), str(fid), data)


@daily_arrangement.get("/family/{fid}/onboarding-preparations/{pid}")
async def preparation_get(fid: UUID, pid: UUID, user=Depends(get_required_user)):
    """只读当前账号有权访问的准备结果。"""
    return await read_onboarding_preparation(str(user.uid), str(fid), str(pid))


@daily_arrangement.post("/family/{fid}/onboarding-preparations/{pid}/resume")
async def preparation_resume(fid: UUID, pid: UUID, user=Depends(get_required_user)):
    """继续原准备，保留已完成工作。"""
    return await resume_onboarding_preparation(str(user.uid), str(fid), str(pid))


@daily_arrangement.get("/family/{fid}/daily-arrangements/{day}")
async def daily_get(
    fid: UUID, day: date, daily_plan_version: int | None = Query(default=None, ge=0), user=Depends(get_required_user)
):
    """读取当天唯一安排。"""
    result = await read_daily_arrangement(str(user.uid), str(fid), day)
    if daily_plan_version is not None and result.get("status") == "ready":
        from yuxi.services.daily_meal_plan_service import require_formal_current

        await require_formal_current(
            str(user.uid),
            str(fid),
            day,
            result["id"],
            result["version"],
            daily_plan_version,
            ["breakfast", "lunch", "dinner"],
        )
    return result


@daily_arrangement.post("/family/{fid}/daily-arrangements")
async def daily_start(
    fid: UUID,
    data: DailyStartInput,
    key: str | None = Header(default=None, alias="Idempotency-Key"),
    user=Depends(get_required_user),
):
    """建档成功后创建或恢复当天生成。"""
    require_key(data.client_request_id, key)
    return await start_daily_arrangement(str(user.uid), str(fid), data)


@daily_arrangement.post("/family/{fid}/daily-arrangements/{day}/resume")
async def daily_resume(fid: UUID, day: date, retry_failed: bool = False, user=Depends(get_required_user)):
    """继续已有任务并核对最终保存。"""
    return await request_daily_resume(str(user.uid), str(fid), day, retry_failed=retry_failed)


@daily_arrangement.get("/family/{fid}/daily-arrangements/{day}/meals/{meal}")
async def meal_get(
    fid: UUID,
    day: date,
    meal: Literal["breakfast", "lunch", "dinner"],
    arrangement_id: UUID,
    version: int = Query(gt=0),
    daily_plan_version: int | None = Query(default=None, ge=0),
    user=Depends(get_required_user),
):
    """详情严格绑定首页显示的保存ID和版本。"""
    if daily_plan_version is not None:
        from yuxi.services.daily_meal_plan_service import require_formal_current

        await require_formal_current(
            str(user.uid), str(fid), day, str(arrangement_id), version, daily_plan_version, [meal]
        )
    result = await read_daily_arrangement(str(user.uid), str(fid), day)
    if result.get("status") != "ready" or result["id"] != str(arrangement_id) or result["version"] != version:
        raise HealthVisionError("daily_version_changed", "本餐安排已更新，请返回重新读取", 409)
    return {
        "arrangement_id": result["id"],
        "version": result["version"],
        "meal": next(item for item in result["meals"] if item["type"] == meal),
        "analysis": result["analysis"],
    }


@daily_arrangement.post("/family/{fid}/daily-arrangements/{day}/members")
async def member_change(
    fid: UUID,
    day: date,
    data: DailyMemberInput,
    key: str | None = Header(default=None, alias="Idempotency-Key"),
    user=Depends(get_required_user),
):
    """重新计算选定一餐，其他餐与支付履约不动。"""
    require_key(data.client_request_id, key)
    return await change_daily_members(str(user.uid), str(fid), day, data)


@daily_arrangement.get("/family/{fid}/daily-arrangements/{day}/meals/{meal}/purchase")
async def purchase_read(
    fid: UUID,
    day: date,
    meal: Literal["breakfast", "lunch", "dinner"],
    arrangement_id: UUID,
    version: int = Query(gt=0),
    daily_plan_version: int | None = Query(default=None, ge=0),
    user=Depends(get_required_user),
):
    """查看本餐商品，不要求商城登录也不产生交易写入。"""
    if daily_plan_version is not None:
        from yuxi.services.daily_meal_plan_service import require_formal_current

        await require_formal_current(
            str(user.uid), str(fid), day, str(arrangement_id), version, daily_plan_version, [meal]
        )
    return await read_daily_purchase(str(user.uid), str(fid), day, meal, str(arrangement_id), version)


@daily_arrangement.post("/family/{fid}/daily-arrangements/{day}/meals/{meal}/purchase")
async def purchase_publish(
    fid: UUID,
    day: date,
    meal: Literal["breakfast", "lunch", "dinner"],
    data: DailyPurchaseInput,
    user=Depends(get_required_user),
):
    """明确结算后幂等发布采购包，价格库存仍由商城核验。"""
    if data.daily_plan_version is not None:
        from yuxi.services.daily_meal_plan_service import require_formal_current

        await require_formal_current(
            str(user.uid), str(fid), day, str(data.arrangement_id), data.version, data.daily_plan_version, [meal]
        )
    return await publish_daily_purchase(str(user.uid), str(fid), day, meal, str(data.arrangement_id), data.version)


@daily_arrangement.get("/family/{fid}/daily-arrangements/{day}/purchase")
async def summary_read(
    fid: UUID,
    day: date,
    arrangement_id: UUID,
    version: int = Query(gt=0),
    daily_plan_version: int | None = Query(default=None, ge=0),
    meals: list[Literal["breakfast", "lunch", "dinner"]] = Query(min_length=1, max_length=3),
    user=Depends(get_required_user),
):
    """按所选餐次汇总真实食材，查看只读。"""
    if daily_plan_version is not None:
        from yuxi.services.daily_meal_plan_service import require_formal_current

        await require_formal_current(
            str(user.uid), str(fid), day, str(arrangement_id), version, daily_plan_version, meals
        )
    return await read_daily_summary(str(user.uid), str(fid), day, str(arrangement_id), version, meals)


@daily_arrangement.post("/family/{fid}/daily-arrangements/{day}/purchase")
async def summary_publish(fid: UUID, day: date, data: DailySummaryInput, user=Depends(get_required_user)):
    """明确购买后发布汇总采购包。"""
    if data.daily_plan_version is not None:
        from yuxi.services.daily_meal_plan_service import require_formal_current

        await require_formal_current(
            str(user.uid), str(fid), day, str(data.arrangement_id), data.version, data.daily_plan_version, data.meals
        )
    return await publish_daily_summary(str(user.uid), str(fid), day, str(data.arrangement_id), data.version, data.meals)


@daily_arrangement.put("/health/v1/recipe-commerce-sources/{rid}")
async def recipe_source_save(rid: UUID, data: RecipeCommerceInput, user=Depends(get_admin_user)):
    """发布明确的菜谱版本做法与采购映射。"""
    return await save_recipe_commerce_source(str(user.uid), str(rid), data)


@daily_arrangement.get("/health/v1/recipe-commerce-sources/{rid}")
async def recipe_source_read(rid: UUID, user=Depends(get_admin_user)):
    """返回准确配方hash、食材版本和既有做法映射，供发布前核对。"""
    return await read_recipe_commerce_source(str(rid))


@daily_arrangement.get("/health/v1/nutrition-setup/readiness")
async def nutrition_setup_readiness(user=Depends(get_admin_user)):
    """区分服务配置和专业资料缺项，不读取成员健康内容。"""
    return await daily_setup_readiness()


@daily_arrangement.get("/health/v1/reference-meal-plans/{preview_id}")
async def reference_meal_plan(preview_id: UUID, response: Response, user=Depends(get_required_user)):
    """读取本人已完成的日常参考结果，重验当前来源。"""
    from yuxi.services.reference_meal_plan_service import read_reference_plan

    response.headers["Cache-Control"] = "no-store"
    return await read_reference_plan(user.uid, str(preview_id))


@daily_arrangement.get("/family/{family_id}/reference-meal-plans/{plan_date}/current")
async def current_reference_meal_plan(
    family_id: UUID, plan_date: date, response: Response, user=Depends(get_required_user)
):
    """家庭主页只读已完成参考餐单。"""
    from yuxi.services.reference_meal_plan_service import current_reference_plan

    response.headers["Cache-Control"] = "no-store"
    return await current_reference_plan(user.uid, str(family_id), plan_date)


@daily_arrangement.get("/family/{family_id}/daily-meal-plans/{plan_date}")
async def current_daily_meal_plan(family_id: UUID, plan_date: date, user=Depends(get_required_user)):
    """聊天和快捷入口读取同一当前计划。"""
    from yuxi.services.daily_meal_plan_service import read_current_plan

    return await read_current_plan(str(user.uid), str(family_id), plan_date)


@daily_arrangement.post("/family/{family_id}/daily-meal-plans/{plan_date}/purchase")
async def current_daily_reference_purchase(
    family_id: UUID, plan_date: date, data: DailyReferencePurchaseInput, user=Depends(get_required_user)
):
    """把采购证明绑定每日计划版本，后续商品回读继续检查。"""
    from yuxi.services.reference_meal_plan_service import publish_reference_purchase

    daily = {
        "family_id": str(family_id),
        "date": plan_date.isoformat(),
        "version": data.version,
        "meal_types": sorted(data.meal_types),
    }
    return await publish_reference_purchase(str(user.uid), str(data.preview_id), daily_plan=daily)


@daily_arrangement.post("/health/v1/reference-meal-plans/{preview_id}/purchase")
async def reference_meal_purchase(preview_id: UUID, user=Depends(get_required_user)):
    """用户明确采购后发布既有参考结果的固定商品选择。"""
    from yuxi.services.reference_meal_plan_service import publish_reference_purchase

    return await publish_reference_purchase(user.uid, str(preview_id))


@daily_arrangement.post("/health/v1/nutrition-setup/imports", status_code=201)
async def prepare_nutrition_candidates(data: NutritionImportInput, user=Depends(get_admin_user)):
    """管理端登记未发布候选，保留异常和来源。"""
    return await prepare_nutrition_import(user.uid, data)


@daily_arrangement.get("/health/v1/nutrition-setup/imports/{batch_id}")
async def nutrition_candidate_status(batch_id: UUID, user=Depends(get_admin_user)):
    """只读取本人的候选批次。"""
    return await read_nutrition_import(user.uid, str(batch_id))


@daily_arrangement.post("/health/v1/nutrition-setup/knowledge", status_code=201)
async def prepare_knowledge_import(data: KnowledgeNutritionInput, user=Depends(get_admin_user)):
    """后台从既有资料整理待审候选，不发布营养或菜谱。"""
    return await prepare_knowledge_nutrition(user.uid, data)


@daily_arrangement.get("/health/v1/nutrition-setup/knowledge/tasks/{task_id}")
async def knowledge_import_status(task_id: str, user=Depends(get_admin_user)):
    """读取本人后台候选整理任务。"""
    return await read_knowledge_nutrition(user.uid, task_id)

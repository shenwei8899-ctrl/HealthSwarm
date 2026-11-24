"""家庭三档专属计划的薄 HTTP 入口。"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response, Query
from pydantic import BaseModel, ConfigDict, Field

from server.routers.health_vision_router import HealthRoute
from server.utils.auth_middleware import get_required_user
from yuxi.services.exclusive_plan_service import read_exclusive_plan, start_exclusive_plan
from yuxi.services.exclusive_plan_types import ExclusivePlanInput, EXCLUSIVE_PLAN_DAYS


async def private_response(response: Response):
    """计划与任务状态不能被共享缓存。"""
    response.headers["Cache-Control"] = "no-store"


exclusive_plan = APIRouter(tags=["exclusive-plans"], route_class=HealthRoute, dependencies=[Depends(private_response)])


class ExclusivePurchaseInput(BaseModel):
    """只接受已读取的范围摘要，不接受菜单、价格或商品身份。"""

    model_config = ConfigDict(extra="forbid")
    scope_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class PlanImageInput(BaseModel):
    """自动补图复用已有尝试，只有显式重试允许恢复失败任务。"""

    model_config = ConfigDict(extra="forbid")
    retry: bool = False


@exclusive_plan.post("/health/v1/families/{family_id}/exclusive-plans/{group_id}/images")
async def prepare_images(family_id: UUID, group_id: UUID, data: PlanImageInput, user=Depends(get_required_user)):
    """显式登记持久后台补图，菜单本身不等待图片。"""
    from yuxi.services.exclusive_plan_images import start_plan_images

    return await start_plan_images(user.uid, str(family_id), str(group_id), retry=data.retry)


@exclusive_plan.get("/health/v1/families/{family_id}/exclusive-plans/{group_id}/tiers/{tier}/images")
async def read_images(
    family_id: UUID,
    group_id: UUID,
    tier: Literal["economy", "standard", "premium"],
    day_no: int = Query(ge=1, le=EXCLUSIVE_PLAN_DAYS),
    user=Depends(get_required_user),
):
    """按当前日期返回图片，GET不会登记任务或调用生成供应商。"""
    from yuxi.services.exclusive_plan_images import read_plan_images

    return await read_plan_images(user.uid, str(family_id), str(group_id), tier, day_no)


@exclusive_plan.get("/health/v1/families/{family_id}/exclusive-plans/{group_id}/tiers/{tier}/purchase")
async def read_purchase(
    family_id: UUID, group_id: UUID, tier: Literal["economy", "standard", "premium"], user=Depends(get_required_user)
):
    from yuxi.services.exclusive_plan_purchase import read_purchase as read

    return await read(user.uid, str(family_id), str(group_id), tier)


@exclusive_plan.post("/health/v1/families/{family_id}/exclusive-plans/{group_id}/tiers/{tier}/purchase")
async def publish_purchase(
    family_id: UUID,
    group_id: UUID,
    tier: Literal["economy", "standard", "premium"],
    data: ExclusivePurchaseInput,
    user=Depends(get_required_user),
):
    from yuxi.services.exclusive_plan_purchase import publish_purchase as publish

    return await publish(user.uid, str(family_id), str(group_id), tier, data.scope_hash)


@exclusive_plan.get("/health/v1/families/{family_id}/exclusive-plans")
async def read_current(family_id: UUID, summary: bool = False, user=Depends(get_required_user)):
    """读取当前家庭的最近推荐组。"""
    if summary:
        from yuxi.services.exclusive_plan_browse import read_plan_summary

        return await read_plan_summary(user.uid, str(family_id))
    return await read_exclusive_plan(user.uid, str(family_id))


@exclusive_plan.get("/health/v1/families/{family_id}/exclusive-plans/{group_id}")
async def read_group(family_id: UUID, group_id: UUID, summary: bool = False, user=Depends(get_required_user)):
    """恢复准确的推荐组而非相邻任务。"""
    if summary:
        from yuxi.services.exclusive_plan_browse import read_plan_summary

        return await read_plan_summary(user.uid, str(family_id), str(group_id))
    return await read_exclusive_plan(user.uid, str(family_id), str(group_id))


@exclusive_plan.post("/health/v1/families/{family_id}/exclusive-plans")
async def prepare_group(family_id: UUID, data: ExclusivePlanInput, user=Depends(get_required_user)):
    """先保存后台任务，页面无需持续存活。"""
    return await start_exclusive_plan(user.uid, str(family_id), data)


@exclusive_plan.get("/health/v1/families/{family_id}/exclusive-plans/{group_id}/tiers/{tier}")
async def read_tier(
    family_id: UUID, group_id: UUID, tier: Literal["economy", "standard", "premium"], user=Depends(get_required_user)
):
    """按账号、家庭和组读取已复核原谱的菜单及采购缺口。"""
    return await read_exclusive_plan(user.uid, str(family_id), str(group_id), tier=tier)


@exclusive_plan.get("/health/v1/families/{family_id}/exclusive-plans/{group_id}/tiers/{tier}/directory")
async def read_directory(
    family_id: UUID, group_id: UUID, tier: Literal["economy", "standard", "premium"], user=Depends(get_required_user)
):
    """只读目录和轻量版本，进入页面不下载整期原文。"""
    from yuxi.services.exclusive_plan_browse import read_plan_directory

    return await read_plan_directory(user.uid, str(family_id), str(group_id), tier)


@exclusive_plan.get("/health/v1/families/{family_id}/exclusive-plans/{group_id}/tiers/{tier}/days/{day_no}")
async def read_day(
    family_id: UUID,
    group_id: UUID,
    tier: Literal["economy", "standard", "premium"],
    day_no: int,
    known_version: str | None = Query(default=None, pattern=r"^[a-f0-9]{64}$"),
    user=Depends(get_required_user),
):
    """服务端回执通过才允许返回未变化，客户端版本不是授权凭证。"""
    from yuxi.services.exclusive_plan_browse import read_plan_day

    if not 1 <= day_no <= EXCLUSIVE_PLAN_DAYS:
        from yuxi.services.health_vision_types import HealthVisionError

        raise HealthVisionError("not_found", "计划日期不存在", 404)
    return await read_plan_day(user.uid, str(family_id), str(group_id), tier, day_no, known_version)

"""家庭三档专属计划的薄 HTTP 入口。"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field

from server.routers.health_vision_router import HealthRoute
from server.utils.auth_middleware import get_required_user
from yuxi.services.exclusive_plan_service import read_exclusive_plan, start_exclusive_plan
from yuxi.services.exclusive_plan_types import ExclusivePlanInput


async def private_response(response: Response):
    """计划与任务状态不能被共享缓存。"""
    response.headers["Cache-Control"] = "no-store"


exclusive_plan = APIRouter(tags=["exclusive-plans"], route_class=HealthRoute, dependencies=[Depends(private_response)])


class ExclusivePurchaseInput(BaseModel):
    """只接受已读取的范围摘要，不接受菜单、价格或商品身份。"""
    model_config = ConfigDict(extra='forbid')
    scope_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


@exclusive_plan.get('/health/v1/families/{family_id}/exclusive-plans/{group_id}/tiers/{tier}/purchase')
async def read_purchase(family_id: UUID, group_id: UUID, tier: Literal['economy', 'standard', 'premium'],
                        user=Depends(get_required_user)):
    from yuxi.services.exclusive_plan_purchase import read_purchase as read
    return await read(user.uid, str(family_id), str(group_id), tier)


@exclusive_plan.post('/health/v1/families/{family_id}/exclusive-plans/{group_id}/tiers/{tier}/purchase')
async def publish_purchase(family_id: UUID, group_id: UUID, tier: Literal['economy', 'standard', 'premium'],
                           data: ExclusivePurchaseInput, user=Depends(get_required_user)):
    from yuxi.services.exclusive_plan_purchase import publish_purchase as publish
    return await publish(user.uid, str(family_id), str(group_id), tier, data.scope_hash)


@exclusive_plan.get("/health/v1/families/{family_id}/exclusive-plans")
async def read_current(family_id: UUID, user=Depends(get_required_user)):
    """读取当前家庭的最近推荐组。"""
    return await read_exclusive_plan(user.uid, str(family_id))


@exclusive_plan.get("/health/v1/families/{family_id}/exclusive-plans/{group_id}")
async def read_group(family_id: UUID, group_id: UUID, user=Depends(get_required_user)):
    """恢复准确的推荐组而非相邻任务。"""
    return await read_exclusive_plan(user.uid, str(family_id), str(group_id))


@exclusive_plan.post("/health/v1/families/{family_id}/exclusive-plans")
async def prepare_group(family_id: UUID, data: ExclusivePlanInput, user=Depends(get_required_user)):
    """先保存后台任务，页面无需持续存活。"""
    return await start_exclusive_plan(user.uid, str(family_id), data)


@exclusive_plan.get("/health/v1/families/{family_id}/exclusive-plans/{group_id}/tiers/{tier}")
async def read_tier(family_id: UUID, group_id: UUID, tier: Literal["economy", "standard", "premium"],
                    user=Depends(get_required_user)):
    """按账号、家庭和组读取已复核原谱的菜单及采购缺口。"""
    return await read_exclusive_plan(user.uid, str(family_id), str(group_id), tier=tier)

"""家庭三档专属计划的薄 HTTP 入口。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Response

from server.routers.health_vision_router import HealthRoute
from server.utils.auth_middleware import get_required_user
from yuxi.services.exclusive_plan_service import read_exclusive_plan, start_exclusive_plan
from yuxi.services.exclusive_plan_types import ExclusivePlanInput


async def private_response(response: Response):
    """计划与任务状态不能被共享缓存。"""
    response.headers["Cache-Control"] = "no-store"


exclusive_plan = APIRouter(tags=["exclusive-plans"], route_class=HealthRoute, dependencies=[Depends(private_response)])


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

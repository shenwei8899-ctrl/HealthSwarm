"""原小程序云端建档和每日安排的薄HTTP适配。"""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from server.routers.health_vision_router import HealthRoute
from server.utils.auth_middleware import get_admin_user, get_required_user
from yuxi.services.daily_arrangement_service import (
    read_daily_arrangement,
    start_daily_arrangement,
    resume_daily_arrangement,
    change_daily_members,
)
from yuxi.services.daily_arrangement_projection import save_recipe_commerce_source
from yuxi.services.miniapp_profile_service import read_miniapp_profile, save_miniapp_profile
from yuxi.services.miniapp_profile_types import MiniappProfileInput
from yuxi.services.health_vision_types import HealthVisionError


async def private_response(response: Response):
    """健康数据不允许公共缓存。"""
    response.headers["Cache-Control"] = "no-store"


daily_arrangement = APIRouter(
    tags=["daily-arrangement"], route_class=HealthRoute, dependencies=[Depends(private_response)]
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
    meal: Literal["breakfast", "lunch", "dinner"]
    member_ids: list[UUID] = Field(min_length=1, max_length=20)


class RecipeCommerceInput(BaseModel):
    """真实做法和标准食材编码由管理端发布，不按菜名关联。"""

    model_config = ConfigDict(extra="forbid")
    recipe_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_ref: str = Field(min_length=1, max_length=500)
    steps: list[str] = Field(min_length=1, max_length=100)
    ingredient_codes: dict[UUID, str]


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
    data: MiniappProfileInput,
    key: str | None = Header(default=None, alias="Idempotency-Key"),
    user=Depends(get_required_user),
):
    """同键保存完整建档。"""
    require_key(data.client_request_id, key)
    return await save_miniapp_profile(str(user.uid), str(fid), data)


@daily_arrangement.get("/family/{fid}/daily-arrangements/{day}")
async def daily_get(fid: UUID, day: date, user=Depends(get_required_user)):
    """读取当天唯一安排。"""
    return await read_daily_arrangement(str(user.uid), str(fid), day)


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
    return await resume_daily_arrangement(str(user.uid), str(fid), day, retry_failed=retry_failed)


@daily_arrangement.get("/family/{fid}/daily-arrangements/{day}/meals/{meal}")
async def meal_get(
    fid: UUID,
    day: date,
    meal: Literal["breakfast", "lunch", "dinner"],
    arrangement_id: UUID,
    version: int = Query(gt=0),
    user=Depends(get_required_user),
):
    """详情严格绑定首页显示的保存ID和版本。"""
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


@daily_arrangement.put("/health/v1/recipe-commerce-sources/{rid}")
async def recipe_source_save(rid: UUID, data: RecipeCommerceInput, user=Depends(get_admin_user)):
    """发布明确的菜谱版本做法与采购映射。"""
    return await save_recipe_commerce_source(str(user.uid), str(rid), data)

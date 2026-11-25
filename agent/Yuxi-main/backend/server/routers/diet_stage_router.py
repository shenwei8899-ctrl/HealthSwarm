"""我的家阶段管理HTTP入口。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Response

from server.routers.health_vision_router import HealthRoute
from server.utils.auth_middleware import get_required_user
from yuxi.services.diet_stage_service import generate_stage, read_stage, read_stage_job, save_stage, save_week
from yuxi.services.diet_stage_types import StageGenerate, StageWrite, WeekWrite


async def no_cache(response: Response):
    """成员阶段与生成结果不可被共享缓存。"""
    response.headers["Cache-Control"] = "no-store"


diet_stage = APIRouter(
    prefix="/health/v1/families/{family_id}/members/{member_id}/diet-stage",
    tags=["diet-stage"],
    route_class=HealthRoute,
    dependencies=[Depends(no_cache)],
)


@diet_stage.get("")
async def read(family_id: UUID, member_id: UUID, stage_id: UUID | None = None, user=Depends(get_required_user)):
    """读取当前或指定历史阶段。"""
    return await read_stage(user.uid, str(family_id), str(member_id), stage_id=str(stage_id) if stage_id else None)


@diet_stage.put("")
async def save(family_id: UUID, member_id: UUID, data: StageWrite, user=Depends(get_required_user)):
    """确认目标及下一阶段，不接受隐式自动生效。"""
    return await save_stage(user.uid, str(family_id), str(member_id), data)


@diet_stage.put("/{stage_id}/weeks/{week_id}")
async def action(
    family_id: UUID, member_id: UUID, stage_id: UUID, week_id: UUID, data: WeekWrite, user=Depends(get_required_user)
):
    """修改同一成员阶段的行动。"""
    return await save_week(user.uid, str(family_id), str(member_id), str(stage_id), str(week_id), data)


@diet_stage.post("/generations")
async def generate(family_id: UUID, member_id: UUID, data: StageGenerate, user=Depends(get_required_user)):
    """登记后台草案或复盘，不在HTTP内等待模型。"""
    return await generate_stage(user.uid, str(family_id), str(member_id), data)


@diet_stage.get("/generations/{job_id}")
async def result(family_id: UUID, member_id: UUID, job_id: UUID, user=Depends(get_required_user)):
    """回读本账号结果并重验来源可见性。"""
    return await read_stage_job(user.uid, str(family_id), str(member_id), str(job_id))

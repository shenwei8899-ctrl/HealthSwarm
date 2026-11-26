"""归档与成员更新状态不能进入换菜查询或写入。"""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from yuxi.services import daily_dish_swap_service as service
from yuxi.services.health_vision_types import HealthVisionError

@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["stale", "pending", "locked", "missing_origin", "not_purchasable"])
async def test_protected_meals_skip_lookup_and_reject_writes(monkeypatch, status):
    """真实候选和替换入口均在访问归档来源前拒绝。"""
    meal={"meal_type":"lunch","meal":{"dishes":[{"name":"合成饭","origin":{"source":{"kind":"reference"}}}]}}
    plan={"version":1,"meals":[meal],"needs_regeneration":[],"roster":{}}
    if status=="stale":plan["needs_regeneration"]=["lunch"]
    if status=="pending":plan["roster"]={"lunch":{"status":"pending"}}
    if status=="locked":plan["roster"]={"lunch":{"execution_locked":True}}
    if status=="missing_origin":meal["meal"]["dishes"][0].pop("origin")
    if status=="not_purchasable":meal["purchase_ready"]=False
    from yuxi.services import reference_recipe_index as recipes, daily_meal_plan_service as daily
    from yuxi.storage.postgres.manager import pg_manager
    lookup=AsyncMock(side_effect=AssertionError("protected meal reached recipe source"))
    monkeypatch.setattr(recipes,"reference_recipe_rows",lookup)
    assert await service.plan_candidates(None,"self","family",plan)==[{"meal_type":"lunch","dishes":[]}]
    lookup.assert_not_awaited()
    @asynccontextmanager
    async def session():
        yield SimpleNamespace()
    monkeypatch.setattr(pg_manager,"get_async_session_context",session)
    monkeypatch.setattr(daily,"current_row",AsyncMock(return_value=SimpleNamespace(meal_sources={})))
    monkeypatch.setattr(daily,"read_current_plan",AsyncMock(return_value=plan))
    monkeypatch.setattr(service,"require_today",lambda day:None)
    data=SimpleNamespace(version=1,meal_type="lunch",client_request_id="synthetic",model_dump=lambda **kwargs:{})
    with pytest.raises(HealthVisionError) as error:
        await service.replace_dish("self","family","synthetic",data)
    assert error.value.code==("swap_meal_needs_regeneration" if status=="stale" else "roster_not_ready")

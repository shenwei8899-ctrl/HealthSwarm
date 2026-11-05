"""待核对做法选择不扩大其他配餐模式，模型不能夹带批准或正文。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.services import health_meal_plan_service as service
from yuxi.services.health_meal_plan_types import PlannerAnswer
from yuxi.services.health_vision_types import HealthVisionError

CHOICE = [{"meal_type": "breakfast", "candidate_ids": ["source-hard-cooked-egg"]}]


@pytest.mark.parametrize(
    "extra",
    [
        {"preview_id": str(uuid4())},
        {"questions": ["补充资料"]},
        {"approved": True},
        {"meals": [{"name": "模型自造菜"}]},
    ],
)
def test_candidates_cannot_mix_outcomes_or_free_plan_fields(extra):
    """第三种输出仍受严格互斥协议约束。"""
    with pytest.raises(ValidationError):
        PlannerAnswer.model_validate({"candidate_meals": CHOICE, **extra})


@pytest.mark.parametrize("field", ["ingredients", "steps", "source", "nutrition", "approved", "sku_id"])
def test_candidate_choice_only_accepts_meal_and_ids(field):
    """来源、用料和适用性不能由模型写进选择对象。"""
    with pytest.raises(ValidationError):
        PlannerAnswer.model_validate({"candidate_meals": [{**CHOICE[0], field: "untrusted"}]})


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["generic", "initial", "safe", "family"])
async def test_candidates_rejected_outside_reference_binding(monkeypatch, mode):
    """固定模式核验先于任何预览读取或持久化。"""
    binding = SimpleNamespace(
        initial_planner_selection={"selection": {"mode": "initial"}} if mode == "initial" else None,
        safe_planner_selection={} if mode == "safe" else None,
        family_planner_selection={} if mode == "family" else None,
    )

    @asynccontextmanager
    async def session_context():
        yield "synthetic-session"

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service, "require_planner_run", AsyncMock(return_value=(SimpleNamespace(), binding)))
    with pytest.raises(HealthVisionError, match="planner_output_invalid"):
        await service.planner_final_result(SimpleNamespace(), PlannerAnswer(candidate_meals=CHOICE).model_dump_json())

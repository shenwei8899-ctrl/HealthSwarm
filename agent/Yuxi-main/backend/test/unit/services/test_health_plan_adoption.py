"""采用动作选择器拒绝半个替代和客户端批准声明。"""

from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from yuxi.services.health_plan_adoption_types import PlanAdoptionInput
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.repositories.health_plan_adoption_repository import HealthPlanAdoptionRepository
from yuxi.repositories.health_meal_plan_repository import HealthMealPlanRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from test.unit.services.test_health_family_meal_plan import family_spec


def request_body():
    """用户仅选择当前对象版本，不提交安全及专业结果。"""
    return {
        "client_request_id": str(uuid4()),
        "version": 1,
        "review_id": str(uuid4()),
        "profile_versions": {str(uuid4()): 1},
    }


@pytest.mark.parametrize(
    "selection",
    [
        {"replaces_adoption_id": str(uuid4())},
        {"replaces_version": 1},
    ],
)
def test_replacement_requires_both_selected_object_and_version(selection):
    """客户端缺少替代对象或版本，不能转换成无条件覆盖。"""
    with pytest.raises(ValidationError, match="替代采用须同时提供对象与版本"):
        PlanAdoptionInput.model_validate({**request_body(), **selection})


@pytest.mark.parametrize("field", ["status", "professional_review", "approved", "safety_status"])
def test_client_cannot_supply_adoption_or_professional_outcome(field):
    """采用输入不接受客户端或模型声明审核通过。"""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        PlanAdoptionInput.model_validate({**request_body(), field: "approved"})


def test_multiple_replacements_require_one_explicit_selection_format():
    """旧单对象仍可用，多对象选择不能与其混用。"""
    old = str(uuid4())
    body = {**request_body(), "replaces_adoptions": {old: 2}}
    assert PlanAdoptionInput.model_validate(body).replaces_adoptions
    with pytest.raises(ValidationError, match="不能同时选择"):
        PlanAdoptionInput.model_validate({**body, "replaces_adoption_id": old, "replaces_version": 2})


@pytest.mark.parametrize("version", [0, -1, True, "1"])
def test_replacement_versions_are_positive_integers(version):
    """多对象选择不能放宽版本边界。"""
    with pytest.raises(ValidationError):
        PlanAdoptionInput.model_validate({**request_body(), "replaces_adoptions": {str(uuid4()): version}})


@pytest.mark.asyncio
async def test_new_occupancy_members_after_lock_require_refresh(monkeypatch):
    """预读后出现未知家庭参与者，不能继续补逆序锁或覆盖该家庭。"""
    first, second = str(uuid4()), str(uuid4())
    plan = SimpleNamespace(member_id=first, spec={}, snapshot={"plan_date": "2026-10-07"})
    previous = SimpleNamespace(
        member_id=first, snapshot={"scope": "family_recipe_draft", "members": {first: {}, second: {}}}
    )
    session = SimpleNamespace(refresh=AsyncMock())
    repo = HealthPlanAdoptionRepository(session)
    monkeypatch.setattr(HealthMealPlanRepository, "plan", AsyncMock(return_value=plan))
    monkeypatch.setattr(repo, "overlapping", AsyncMock(side_effect=[[], [previous]]))
    authorize = AsyncMock()
    monkeypatch.setattr(HealthVisionRepository, "authorize", authorize)
    with pytest.raises(HealthVisionError) as error:
        await repo.lock_plan_occupancies("actor", "plan")
    assert error.value.code == "adoption_version_conflict"
    assert [call.args[0] for call in authorize.call_args_list] == [first]


@pytest.mark.asyncio
async def test_plan_participants_changed_after_lock_cannot_be_adopted(monkeypatch):
    """等待锁期间参与者变化，旧授权集合不得用于采用新版。"""
    first, second = str(uuid4()), str(uuid4())
    plan = SimpleNamespace(member_id=first, spec={}, snapshot={"plan_date": "2026-10-07"})

    async def refresh(row):
        """构造当前持久化边界返回的新参与者。"""
        row.spec = family_spec(str(uuid4()), first, second)

    repo = HealthPlanAdoptionRepository(SimpleNamespace(refresh=refresh))
    monkeypatch.setattr(HealthMealPlanRepository, "plan", AsyncMock(return_value=plan))
    monkeypatch.setattr(repo, "overlapping", AsyncMock(return_value=[]))
    monkeypatch.setattr(HealthVisionRepository, "authorize", AsyncMock())
    with pytest.raises(HealthVisionError) as error:
        await repo.lock_plan_occupancies("actor", "plan")
    assert error.value.code == "source_invalidated"

"""餐单分页结果、查询范围、逐页授权及协议边界的独立断言。"""

import inspect
import os
import textwrap
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, call
from uuid import UUID

import pytest
from pydantic import ValidationError, create_model
from sqlalchemy.dialects.postgresql import dialect

from server.routers import health_vision_router as router
from yuxi.repositories.health_meal_plan_repository import HealthMealPlanRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services import health_meal_plan_service as service
from yuxi.services.health_vision_types import HealthVisionError

MEMBER = "11111111-1111-1111-1111-111111111111"
PARTICIPANT = "22222222-2222-2222-2222-222222222222"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "limit,offset,count,truncated,next_offset",
    [
        (50, 0, 51, True, 50),
        (1, 4, 2, True, 5),
        (3, 7, 4, True, 10),
        (3, 7, 3, False, None),
        (3, 7, 2, False, None),
        (3, 7, 0, False, None),
    ],
)
async def test_service_returns_only_requested_page_and_next_offset(
    monkeypatch, limit, offset, count, truncated, next_offset
):
    """投影保持原版本与快照，满页且无额外行不宣称还有下一页。"""
    rows = [plan_row(index) for index in range(offset, offset + count)]
    query = AsyncMock(return_value=rows)
    monkeypatch.setattr(HealthMealPlanRepository, "list_plans", query)
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)

    result = await service.list_meal_plans("actor", MEMBER, limit=limit, offset=offset)

    assert result == {
        "plans": [
            {
                "plan_id": f"plan-{index}",
                "member_id": MEMBER,
                "version": index + 1,
                "updated_at": "2026-10-10T08:00:00Z",
                "status": "draft",
                "synthetic_label": f"row-{index}",
            }
            for index in range(offset, offset + min(limit, count))
        ],
        "truncated": truncated,
        "next_offset": next_offset,
    }
    query.assert_awaited_once_with("actor", MEMBER, limit=limit, offset=offset)


@pytest.mark.asyncio
async def test_service_default_retains_fifty_rows_and_lookahead(monkeypatch):
    """既有未传分页参数的调用继续获得50行及截断语义。"""
    query = AsyncMock(return_value=[plan_row(index) for index in range(51)])
    monkeypatch.setattr(HealthMealPlanRepository, "list_plans", query)
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)

    result = await service.list_meal_plans("actor", MEMBER)

    assert [row["plan_id"] for row in result["plans"]] == [f"plan-{index}" for index in range(50)]
    assert result["truncated"] is True and result["next_offset"] == 50
    query.assert_awaited_once_with("actor", MEMBER, limit=50, offset=0)


@pytest.mark.asyncio
async def test_repository_query_keeps_scope_order_page_and_lookahead(monkeypatch):
    """PG查询限定账号成员，按更新时间及ID排序，只取请求页加一行。"""
    rows = [plan_row(index) for index in range(7, 11)]
    session = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)))
    authorize = AsyncMock()
    participants = AsyncMock()
    monkeypatch.setattr(HealthVisionRepository, "authorize", authorize)
    monkeypatch.setattr(HealthVisionRepository, "authorize_plan_members", participants)

    result = await HealthMealPlanRepository(session).list_plans("actor", MEMBER, limit=3, offset=7)

    assert result == rows
    query = session.scalars.await_args.args[0].compile(dialect=dialect())
    sql = str(query)
    assert "health_meal_plan.actor_uid = %(actor_uid_1)s" in sql
    assert "health_meal_plan.member_id = %(member_id_1)s" in sql
    assert "ORDER BY health_meal_plan.updated_at DESC, health_meal_plan.id" in sql
    assert "LIMIT %(param_1)s OFFSET %(param_2)s" in sql
    assert query.params == {"actor_uid_1": "actor", "member_id_1": MEMBER, "param_1": 4, "param_2": 7}
    authorize.assert_awaited_once_with(MEMBER, "actor", "diet_edit")
    assert participants.await_args_list == [call(MEMBER, "actor", row.spec, ["diet_edit"]) for row in rows]


@pytest.mark.asyncio
async def test_repository_revoked_anchor_rejects_before_query(monkeypatch):
    """后续页仍须重验当前成员，不复用前页已通过的授权。"""
    session = SimpleNamespace(scalars=AsyncMock())
    authorize = AsyncMock(side_effect=HealthVisionError("not_found", "资源不存在或无权访问", 404))
    monkeypatch.setattr(HealthVisionRepository, "authorize", authorize)

    with pytest.raises(HealthVisionError, match="not_found"):
        await HealthMealPlanRepository(session).list_plans("actor", MEMBER, limit=3, offset=50)

    authorize.assert_awaited_once_with(MEMBER, "actor", "diet_edit")
    session.scalars.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("family_index", [0, 1])
async def test_repository_revoked_family_participant_rejects_page_and_lookahead(monkeypatch, family_index):
    """未展示的额外家庭行也走真实全员授权流程，撤回不能漏验。"""
    rows = [plan_row(index) for index in range(2)]
    rows[family_index].spec = family_spec()
    session = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)))

    async def authorize(self, member_id, uid, scope, *, lock=False):
        """合成有效入口成员和已撤回的家庭参与者。"""
        if member_id == PARTICIPANT:
            raise HealthVisionError("not_found", "资源不存在或无权访问", 404)
        return SimpleNamespace(id=member_id)

    monkeypatch.setattr(HealthVisionRepository, "authorize", authorize)

    with pytest.raises(HealthVisionError, match="not_found"):
        await HealthMealPlanRepository(session).list_plans("actor", MEMBER, limit=1, offset=50)


@pytest.mark.parametrize("values", [{}, {"limit": "1", "offset": "0"}, {"limit": "50", "offset": "2147483647"}])
def test_route_query_accepts_default_and_database_integer_edges(values):
    """直接使用路由拥有的Query字段校验合法协议与默认值。"""
    fields = inspect.signature(router.member_plans).parameters
    model = create_model("MealPlanPage", **{name: (int, fields[name].default) for name in ("limit", "offset")})

    result = model.model_validate(values)

    assert result.limit == int(values.get("limit", 50))
    assert result.offset == int(values.get("offset", 0))


@pytest.mark.parametrize(
    "values,field",
    [
        ({"limit": "0"}, "limit"),
        ({"limit": "51"}, "limit"),
        ({"limit": "1.5"}, "limit"),
        ({"offset": "-1"}, "offset"),
        ({"offset": "2147483648"}, "offset"),
        ({"offset": "999999999999999999999999"}, "offset"),
        ({"offset": "1.5"}, "offset"),
    ],
)
def test_route_query_rejects_invalid_page_at_owning_field(values, field):
    """非法页大小、负偏移、非整数和PG不可承载偏移在入口拒绝。"""
    fields = inspect.signature(router.member_plans).parameters
    model = create_model("MealPlanPage", **{name: (int, fields[name].default) for name in ("limit", "offset")})

    with pytest.raises(ValidationError) as failure:
        model.model_validate(values)

    assert [error["loc"] for error in failure.value.errors()] == [(field,)]


@pytest.mark.asyncio
async def test_route_forwards_current_actor_member_and_page(monkeypatch):
    """HTTP适配方法传递当前身份与已解析分页，不重新解释业务状态。"""
    expected = {"plans": [], "truncated": False, "next_offset": None}
    query = AsyncMock(return_value=expected)
    monkeypatch.setattr(router, "list_meal_plans", query)

    result = await router.member_plans(UUID(MEMBER), limit=3, offset=50, user=SimpleNamespace(uid="actor"))

    assert result is expected
    query.assert_awaited_once_with("actor", MEMBER, limit=3, offset=50)


def plan_row(index):
    """固定合成保存版本，结果oracle独立列出协议事实。"""
    return SimpleNamespace(
        id=f"plan-{index}",
        member_id=MEMBER,
        version=index + 1,
        updated_at=datetime(2026, 10, 10, 8),
        spec={},
        snapshot={"status": "draft", "synthetic_label": f"row-{index}"},
    )


@asynccontextmanager
async def session_context():
    """服务单测用只读事务替身，不触及真实健康数据。"""
    yield object()


def family_spec():
    """合成两名参与者三餐，用真实家庭解析与授权Owner验证。"""
    return {
        "kind": "family",
        "plan_date": "2026-10-10",
        "meals": [
            {
                "meal_type": meal,
                "participant_ids": [MEMBER, PARTICIPANT],
                "dishes": [
                    {
                        "recipe_version_id": "33333333-3333-3333-3333-333333333333",
                        "member_portions": [{"member_id": member, "grams": "50"} for member in (MEMBER, PARTICIPANT)],
                    }
                ],
            }
            for meal in ("breakfast", "lunch", "dinner")
        ],
    }


@pytest.fixture(autouse=True)
def controlled_pagination_mutation(monkeypatch):
    """显式负控仅替换内存函数副本，原结果与边界断言必须因目标缺陷变红。"""
    mode = os.getenv("HEALTH_MEAL_PAGINATION_MUTATION")
    if not mode:
        return
    mutations = {
        "fixed_limit": (HealthMealPlanRepository, "list_plans", ".limit(limit + 1)", ".limit(51)"),
        "missing_offset": (HealthMealPlanRepository, "list_plans", ".offset(offset)", ".offset(0)"),
        "missing_tiebreaker": (
            HealthMealPlanRepository,
            "list_plans",
            ".order_by(HealthMealPlan.updated_at.desc(), HealthMealPlan.id)",
            ".order_by(HealthMealPlan.updated_at.desc())",
        ),
        "lookahead_auth": (HealthMealPlanRepository, "list_plans", "for row in rows:", "for row in rows[:limit]:"),
        "fixed_slice": (service, "list_meal_plans", "rows[:limit]", "rows[:50]"),
        "missing_next": (service, "list_meal_plans", "offset + limit if truncated else None", "None"),
        "limit_min": (router, "member_plans", "default=50, ge=1, le=50", "default=50, ge=0, le=50"),
        "limit_max": (router, "member_plans", "default=50, ge=1, le=50", "default=50, ge=1, le=100"),
        "offset_min": (router, "member_plans", "default=0, ge=0, le=2147483647", "default=0, ge=-1, le=2147483647"),
        "offset_max": (router, "member_plans", "default=0, ge=0, le=2147483647", "default=0, ge=0"),
    }
    owner, attribute, old, new = mutations[mode]
    original = getattr(owner, attribute)
    source = textwrap.dedent(inspect.getsource(original))
    source = source[source.index("async def ") :]
    assert source.count(old) == 1, "负控须准确恢复当前Owner的一个目标缺陷"
    scope = dict(original.__globals__)
    exec(compile(source.replace(old, new), "<controlled_meal_pagination_mutation>", "exec"), scope)
    monkeypatch.setattr(owner, attribute, scope[attribute])

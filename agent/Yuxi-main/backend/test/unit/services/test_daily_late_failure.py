"""原样执行每日恢复用例，验证迟到失败不能改写已完成的同版本赢家。"""

import ast
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import date, datetime, time, timedelta
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("late_failure", ["agent_result", "ingredient_stock", "package_stock"])
async def test_late_daily_failure_preserves_ready_snapshot_and_attempt(monkeypatch, late_failure):
    """三个失败分支均在重取账号、家庭和日期的事务锁后重验赢家，不能递增尝试或抹去采购依据。"""
    backend = Path(__file__).resolve().parents[3]
    path = backend / "package/yuxi/services/daily_arrangement_service.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "resume_daily_arrangement"
    )
    receipt = {"status": "ready", "id": "daily", "version": 3, "saved": True}
    selection = {
        "initial": {"profile_versions": {"member": 1}, "rule_version": 1},
        "attempt": 2,
        "retry_limit": 4,
        "purchase_payloads": {"lunch": {"agent_task_id": "already-saved", "ingredient_requirements": [], "items": []}},
    }
    if late_failure != "agent_result":
        selection["agent_result"] = {
            "payload": {"preview_id": str(uuid4()), "explanation": "合成说明", "sources": {}},
            "task_key": "task",
            "run_id": "run",
        }
    row = SimpleNamespace(
        id="daily",
        version=3,
        status="generating",
        selection=deepcopy(selection),
        snapshot=receipt,
        sources={"members": {}, "account_ref": "account"},
    )

    @asynccontextmanager
    async def session():
        """只隔离事务设备；前后调用始终读到同一个可变业务对象。"""
        yield SimpleNamespace(scalar=AsyncMock(), scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))

    async def context(*_args, **_kwargs):
        """在用例的真实重读点提供当前行。"""
        return None, row

    def winner():
        """模拟另一个恢复者已提交相同版本的 ready 快照。"""
        row.status = "ready"

    async def failed_result(*_args):
        """模型结果的迟到失败发生前，赢家已经完成。"""
        winner()
        return SimpleNamespace(result=SimpleNamespace(model_dump=lambda **_: {"result_type": "failed"}))

    def match_meals(*_args):
        """库存失败发生前完成赢家；其它分支保留一个可购候选。"""
        if late_failure == "ingredient_stock":
            winner()
            return None
        return {"lunch": [{"sku_id": "sku", "quantity": 1}]}

    def packages_in_stock(*_args):
        """最终采购库存失败发生前，赢家已经完成。"""
        winner()
        return False

    request_module = ModuleType("yuxi.services.agent_request_service")
    request_module.AgentRequestInput = lambda **kwargs: kwargs
    request_module.RunOrigin = lambda **kwargs: kwargs
    request_module.submit_agent_request = AsyncMock()
    input_module = ModuleType("yuxi.services.input_message_service")
    input_module.build_chat_input_message = lambda *args: args
    monkeypatch.setitem(sys.modules, request_module.__name__, request_module)
    monkeypatch.setitem(sys.modules, input_module.__name__, input_module)
    authorized = AsyncMock()
    scope = {
        "date": date,
        "datetime": datetime,
        "time": time,
        "timedelta": timedelta,
        "ZoneInfo": ZoneInfo,
        "NAMESPACE_URL": NAMESPACE_URL,
        "uuid4": uuid4,
        "uuid5": uuid5,
        "pg_manager": SimpleNamespace(get_async_session_context=session),
        "DailyArrangementRepository": lambda *_: SimpleNamespace(context=context),
        "authorize_sources": authorized,
        "authorize_daily_agent_result": AsyncMock(),
        "HealthTaskEntryInput": SimpleNamespace(model_validate=lambda value: value),
        "create_health_task_entry": AsyncMock(
            return_value=SimpleNamespace(entry_status="ready", agent_slug="planner", thread_id="thread")
        ),
        "select": lambda *_: SimpleNamespace(where=lambda *_: None),
        "User": SimpleNamespace(uid="uid"),
        "read_health_task": failed_result,
        "save_initial_plan": AsyncMock(
            return_value={"plan_id": "plan", "version": 1, "quality_check": {"check_id": "check"}}
        ),
        "MealPlanSave": lambda **kwargs: kwargs,
        "HealthRecipeCommerceSource": object(),
        "RecipeVersion": SimpleNamespace(id=SimpleNamespace(in_=lambda *_: None)),
        "meal_views": lambda *_: [{"type": "lunch", "dishes": [], "memberNotes": [], "members": []}],
        "current_catalog": AsyncMock(return_value={"version": "catalog", "items": [{"sku_id": "sku"}]}),
        "ingredient_requirements": lambda *_: [],
        "match_meal_requirements": match_meals,
        "daily_commerce_source": lambda *_: {},
        "packages_in_stock": packages_in_stock,
        "retained_purchase_payloads": lambda *_: {},
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), scope)
    result = await scope[function.name]("owner", "family", date(2026, 10, 19))
    assert result == receipt and row.status == "ready"
    assert row.selection["attempt"] == 2
    assert row.selection["purchase_payloads"]["lunch"] == selection["purchase_payloads"]["lunch"]
    assert authorized.await_count >= 2

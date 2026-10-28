"""共享 ready 投影的编码边界；替身不代表真实 HTTP、数据库或 Worker 验收。"""

import ast
from contextlib import asynccontextmanager
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest


@pytest.fixture
def coding_guard(monkeypatch):
    """原样运行生产函数，只替换数据库、权限依赖与模型调用。"""
    backend = Path(__file__).resolve().parents[3]
    state = SimpleNamespace(
        source={"id": "source-peer", "version": 2},
        member=SimpleNamespace(id="source-peer", version=2, family_id="family"),
        link=SimpleNamespace(
            actor_uid="peer", source_kind="miniapp_reported", source_member_id="source-peer", family_id="family"
        ),
        projection={"status": "ready", "id": "source-peer", "version": 2},
    )
    scope = {}
    error_path = backend / "package/yuxi/services/health_vision_types.py"
    tree = ast.parse(error_path.read_text(encoding="utf-8"))
    error = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "HealthVisionError")
    exec(compile(ast.Module(body=[error], type_ignores=[]), str(error_path), "exec"), scope)
    state.error = scope["HealthVisionError"]
    state.health = SimpleNamespace(authorize=AsyncMock(), require_consent=AsyncMock())
    state.project = AsyncMock(side_effect=lambda _: state.projection)
    state.provider = AsyncMock(side_effect=AssertionError("模型调用不应发生"))
    configuration = AsyncMock(
        return_value={
            "meal_plan": {"available": True, "model": "synthetic", "processor": "synthetic"},
            "policy_version": "v1",
        }
    )
    member_type, link_type = object(), object()

    async def get(kind, _key):
        """按对象类型返回固定来源，允许精确变异身份边界。"""
        assert kind in (member_type, link_type)
        return state.member if kind is member_type else state.link

    @asynccontextmanager
    async def session():
        """模拟单次会话，不读取或写入数据库。"""
        yield SimpleNamespace(get=get)

    bindings = {
        "yuxi.repositories.health_quality_repository": {
            "HealthQualityRepository": lambda _: SimpleNamespace(profile_projection=state.project)
        },
        "yuxi.repositories.health_vision_repository": {"HealthVisionRepository": lambda _: state.health},
        "yuxi.services.health_vision_service": {"health_vision_service": SimpleNamespace(configuration=configuration)},
        "yuxi.services.miniapp_planning_source": {"code_submitted_profile": None},
    }
    for name, values in bindings.items():
        module = ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
    scope.update(
        FamilyMember=member_type,
        HealthFamilyProfileLink=link_type,
        pg_manager=SimpleNamespace(get_async_session_context=session),
        call_json_model=state.provider,
    )
    path = backend / "package/yuxi/services/miniapp_profile_coding.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "prepare_daily_profile_coding"
    )
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), scope)

    async def run():
        """使用真正的入口和固定 owner，不改写函数分支。"""
        await scope[node.name]("owner", {"members": {"health-peer": state.source}}, {}, {})

    state.run = run
    return state


@pytest.mark.parametrize("actor", ["peer", "owner"])
@pytest.mark.asyncio
async def test_ready_projection_skips_provider_only_after_current_authorization(coding_guard, actor):
    """共享或本人 ready 都无需再解释，三个 scope 和 owner 用途同意仍逐项核对。"""
    state = coding_guard
    state.link.actor_uid = actor
    await state.run()
    assert state.health.authorize.await_args_list == [
        call("health-peer", "owner", scope) for scope in ("ai_use", "diet_edit", "profile_view")
    ]
    state.health.require_consent.assert_awaited_once_with(
        "health-peer", "owner", "meal_plan", {"model": "synthetic", "processor": "synthetic", "policy_version": "v1"}
    )
    state.project.assert_awaited_once_with("health-peer")
    state.provider.assert_not_awaited()


@pytest.mark.parametrize("denial", ["ai_use", "diet_edit", "profile_view", "consent"])
@pytest.mark.asyncio
async def test_ready_projection_cannot_bypass_revoked_scope_or_owner_consent(coding_guard, denial):
    """即使投影已经 ready，撤权或缺少当前 owner 餐单同意仍先拒绝。"""
    state = coding_guard

    async def authorize(_hid, _uid, scope):
        """只撤回指定 scope。"""
        if scope == denial:
            raise state.error("not_found", "合成撤权", 404)

    state.health.authorize.side_effect = authorize
    expected = "consent_required" if denial == "consent" else "not_found"
    if denial == "consent":
        state.health.require_consent.side_effect = state.error(expected, "合成撤回同意", 403)
    with pytest.raises(state.error) as result:
        await state.run()
    assert result.value.code == expected
    state.project.assert_not_awaited()
    state.provider.assert_not_awaited()


@pytest.mark.parametrize(
    ("target", "key", "value"),
    [
        ("source", "id", "wrong-source"),
        ("source", "version", 3),
        ("member", "id", "wrong-member"),
        ("member", "family_id", "wrong-family"),
        ("link", "source_member_id", "wrong-source"),
        ("link", "family_id", "wrong-family"),
        ("projection", "id", "wrong-source"),
        ("projection", "version", 3),
    ],
)
@pytest.mark.asyncio
async def test_ready_projection_rejects_source_link_family_or_version_mismatch(coding_guard, target, key, value):
    """ready 不覆盖持久来源、家庭绑定或实际投影身份与版本的不一致。"""
    state = coding_guard
    obj = getattr(state, target)
    if isinstance(obj, dict):
        obj[key] = value
    else:
        setattr(obj, key, value)
    with pytest.raises(state.error) as result:
        await state.run()
    assert result.value.code == "source_invalidated" and result.value.status == 410
    state.provider.assert_not_awaited()


@pytest.mark.parametrize("source_kind", ["miniapp_reported", "self_confirmed"])
@pytest.mark.asyncio
async def test_cross_actor_unready_or_non_miniapp_source_cannot_reach_provider(coding_guard, source_kind):
    """跨 actor 只消费当前 ready 小程序投影，不能扩大为代本人解释或其它来源旁路。"""
    state = coding_guard
    state.link.source_kind = source_kind
    state.projection["status"] = "not_ready"
    with pytest.raises(state.error) as result:
        await state.run()
    assert result.value.code == "source_invalidated" and result.value.status == 410
    if source_kind == "miniapp_reported":
        state.project.assert_awaited_once_with("health-peer")
    else:
        state.project.assert_not_awaited()
    state.provider.assert_not_awaited()

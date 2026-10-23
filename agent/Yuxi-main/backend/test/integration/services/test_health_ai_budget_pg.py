"""独立真实 PostgreSQL 与合成供应商验证项目人民币预算。"""

import asyncio
from dataclasses import replace
import os
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from yuxi.models.providers.cache import ModelInfo, model_cache
from yuxi.services import health_ai_budget_service as budget
from yuxi.services.health_ai_budget_types import HealthAiPriceInput
from yuxi.services.health_ai_budget_types import HealthAiOpeningInput
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import PostgresManager
from yuxi.storage.postgres.models_health_budget import HEALTH_BUDGET_TABLES, HealthAiCall, HealthAiMonth, HealthAiPrice

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """本文件使用独立 Schema，不连接已有 API。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """本文件没有知识库测试资源。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本文件没有沙盒测试资源。"""
    yield


@pytest.fixture
async def budget_db(monkeypatch):
    """只创建预算表，独立连接回读提交事实。"""
    schema = "budget_" + uuid4().hex
    admin = create_async_engine(os.environ["POSTGRES_URL"])
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(os.environ["POSTGRES_URL"], connect_args={"server_settings": {"search_path": schema}})
    manager = object.__new__(PostgresManager)
    PostgresManager.__init__(manager)
    manager.async_engine = engine
    manager.AsyncSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    manager._initialized = True
    async with engine.begin() as connection:
        for table in HEALTH_BUDGET_TABLES:
            await connection.run_sync(lambda conn, table=table: table.create(conn))
    monkeypatch.setattr(budget, "pg_manager", manager)
    await budget.initialize_budget(
        "synthetic-admin",
        HealthAiOpeningInput(occupied_cny=0, evidence="隔离合成数据库此前没有任何供应商调用", verified=True),
    )
    try:
        yield manager
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def synthetic_price(**changes):
    """独立手算上界为 10 元，实际 11 入 7 出为 0.09 元。"""
    return HealthAiPriceInput.model_validate(
        {
            "kind": "model",
            "model_spec": "synthetic:fixed",
            "input_cny_per_million": "5000",
            "output_cny_per_million": "5000",
            "max_input_tokens": 1000,
            "max_output_tokens": 1000,
            "valid_until": datetime.now(UTC) + timedelta(days=1),
            "upper_bound_verified": True,
            "evidence": "仅用于隔离测试的合成价格，不代表任何真实供应商",
            **changes,
        }
    )


async def seed_price(manager, target="synthetic", price=None):
    """直接登记合成批准，生产价格只能走管理员接口。"""
    price = price or synthetic_price()
    async with manager.get_async_session_context() as session:
        row = HealthAiPrice(
            id=str(uuid4()),
            target=target,
            kind=price.kind,
            specification=price.model_dump(mode="json"),
            approved_by="synthetic-admin",
            valid_until=price.valid_until.astimezone(UTC).replace(tzinfo=None),
        )
        session.add(row)
    return row.id


async def test_concurrent_five_purposes_share_exactly_forty_and_commit_before_call(budget_db):
    """并发争抢允许四次十元外呼，拒绝者没有供应商副作用。"""
    await seed_price(budget_db)
    external = []

    async def attempt(index):
        try:
            reservation = await budget.reserve(
                ["consultation", "indicator_review", "diet_analysis", "meal", "report"][index % 5],
                f"owner-{index}",
                "synthetic",
            )
        except HealthVisionError as exc:
            assert exc.code == "budget_exceeded"
            return
        async with budget_db.get_async_session_context() as independent:
            row = await independent.get(HealthAiCall, reservation.call_id)
            assert row.status == "reserved" and row.reserved_cny == Decimal("10")
        external.append(reservation.call_id)

    await asyncio.gather(*(attempt(i) for i in range(40)))
    assert len(external) == 4
    async with budget_db.get_async_session_context() as session:
        account = (await session.scalars(select(HealthAiMonth))).one()
        calls = (await session.scalars(select(HealthAiCall))).all()
        assert account.occupied_cny == sum(c.reserved_cny for c in calls) == Decimal("40")


async def test_duplicate_call_and_concurrent_settlement_cannot_double_refund(budget_db):
    """同键重入不得再外呼，同一账本并发结算只退一次差额。"""
    await seed_price(budget_db)
    reservation = await budget.reserve("meal", "task-a", "synthetic")
    with pytest.raises(HealthVisionError, match="budget_call_replayed"):
        await budget.reserve("report", "task-b", "synthetic", call_id=reservation.call_id)
    usage = {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}
    await asyncio.gather(*(budget.settle(reservation, usage) for _ in range(10)))
    async with budget_db.get_async_session_context() as session:
        call = await session.get(HealthAiCall, reservation.call_id)
        month = await session.get(HealthAiMonth, call.month)
        assert call.charged_cny == month.occupied_cny == Decimal("0.09")
        assert call.status == "settled"


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"input_tokens": 1, "output_tokens": 1, "total_tokens": 3},
        {"input_tokens": -1, "output_tokens": 2, "total_tokens": 1},
    ],
)
async def test_unknown_receipt_keeps_full_reservation_on_retry(budget_db, usage):
    """异常或缺失回执不当零，每次新尝试仍须预留。"""
    await seed_price(budget_db)
    first = await budget.reserve("report", "task", "synthetic")
    await budget.settle(first, usage)
    for _ in range(3):
        await budget.reserve("report", "task", "synthetic")
    with pytest.raises(HealthVisionError, match="budget_exceeded"):
        await budget.reserve("report", "task", "synthetic")
    async with budget_db.get_async_session_context() as session:
        call = await session.get(HealthAiCall, first.call_id)
        assert call.status == "unknown" and call.charged_cny is None
        assert (await session.get(HealthAiMonth, call.month)).occupied_cny == Decimal("40")


async def test_missing_price_expiry_and_changed_credentials_fail_closed(budget_db, monkeypatch):
    """凭据或端点变化使旧批准失效，缺价格不得创建账本。"""
    info = ModelInfo(
        provider_id="synthetic",
        model_id="fixed",
        model_type="chat",
        display_name="合成",
        api_key="synthetic",
        base_url="https://synthetic.invalid/v1",
        provider_type="openai",
    )
    monkeypatch.setattr(model_cache, "get_model_info", lambda _: info)
    with pytest.raises(HealthVisionError, match="budget_price_unavailable"):
        await budget.reserve_model("consultation", "run", info.spec)
    await seed_price(
        budget_db,
        budget.model_target(info),
        synthetic_price(valid_until=datetime.now(UTC) - timedelta(seconds=1)),
    )
    with pytest.raises(HealthVisionError, match="budget_price_unavailable"):
        await budget.reserve_model("consultation", "run", info.spec)
    await seed_price(budget_db, budget.model_target(info))
    info = replace(info, api_key="changed-synthetic")
    with pytest.raises(HealthVisionError, match="budget_price_unavailable"):
        await budget.reserve_model("consultation", "run", info.spec)


async def test_out_of_contract_usage_freezes_month_and_price(budget_db):
    """供应商违反已批准上界时保留预留并阻止后续调用。"""
    price_id = await seed_price(budget_db)
    reservation = await budget.reserve("consultation", "run", "synthetic")
    await budget.settle(reservation, {"input_tokens": 1001, "output_tokens": 1, "total_tokens": 1002})
    async with budget_db.get_async_session_context() as session:
        call = await session.get(HealthAiCall, reservation.call_id)
        month = await session.get(HealthAiMonth, call.month)
        assert month.blocked and month.occupied_cny == Decimal("10")
        assert call.charged_cny is None and call.status == "unknown"
        assert not (await session.get(HealthAiPrice, price_id)).enabled


async def test_late_settlement_stays_in_original_month_and_migration_is_repeatable(budget_db, monkeypatch):
    """跨月结算不冲减新月份，重复增量建表不清空未知账本。"""
    await seed_price(budget_db)
    from datetime import date
    from yuxi.storage.postgres.models_health_budget import HealthAiOpening

    async with budget_db.get_async_session_context() as session:
        first_month = (await session.get(HealthAiOpening, 1)).month
    next_month = date(first_month.year + first_month.month // 12, first_month.month % 12 + 1, 1)
    monkeypatch.setattr(budget, "budget_month", lambda _: first_month)
    old = await budget.reserve("meal", "task", "synthetic")
    monkeypatch.setattr(budget, "budget_month", lambda _: next_month)
    await budget.reserve("meal", "task", "synthetic")
    await budget.settle(old, {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18})
    async with budget_db.async_engine.begin() as conn:
        for _ in range(2):
            for table in HEALTH_BUDGET_TABLES:
                await conn.run_sync(lambda connection, table=table: table.create(connection, checkfirst=True))
    async with budget_db.get_async_session_context() as session:
        rows = (await session.scalars(select(HealthAiMonth).order_by(HealthAiMonth.month))).all()
        assert [r.occupied_cny for r in rows] == [Decimal("0.09"), Decimal("10")]


async def test_real_sdk_wire_obeys_cap_and_no_retry_on_503(budget_db, monkeypatch):
    """保留实际 SDK 请求编码，合成传输返回失败，仅产生一次付费尝试。"""
    from unittest.mock import AsyncMock
    from yuxi.services.health_vision_provider import call_json_model

    info = ModelInfo(
        provider_id="synthetic",
        model_id="fixed",
        model_type="chat",
        display_name="合成",
        api_key="synthetic",
        base_url="https://synthetic.invalid/v1",
        provider_type="openai",
    )
    monkeypatch.setattr(model_cache, "get_model_info", lambda _: info)
    await seed_price(budget_db, budget.model_target(info))
    requests = []

    async def send(client, request, **kwargs):
        requests.append(request)
        return httpx.Response(503, json={"error": {"message": "synthetic failure"}}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    with pytest.raises(HealthVisionError, match="provider_unavailable"):
        await call_json_model(
            info.spec,
            "合成指令",
            [],
            SimpleNamespace(task_id="synthetic-task", raise_if_cancelled=AsyncMock()),
            authorize=AsyncMock(),
        )
    import json

    assert len(requests) == 1
    wire = json.loads(requests[0].content)
    assert wire.get("max_tokens", wire.get("max_completion_tokens")) == 1000
    async with budget_db.get_async_session_context() as session:
        call = (await session.scalars(select(HealthAiCall))).one()
        assert call.charged_cny is None and call.reserved_cny == Decimal("10")
        assert (await session.get(HealthAiMonth, call.month)).occupied_cny == Decimal("10")


@pytest.mark.parametrize("purpose", ["consultation", "indicator_review", "diet_analysis"])
async def test_compiled_agent_records_real_sdk_usage(budget_db, monkeypatch, purpose):
    """真实 LangGraph middleware 与 SDK 连接合成传输，最终账本回读结算金额。"""
    from unittest.mock import AsyncMock
    from dataclasses import dataclass
    from langchain.agents import create_agent
    from langchain_core.messages import HumanMessage
    from yuxi.agents.middlewares.health_budget import HealthAiBudgetMiddleware
    from yuxi.models.chat import load_chat_model
    from yuxi.services import health_consultation_service

    info = ModelInfo(
        provider_id="synthetic",
        model_id="fixed",
        model_type="chat",
        display_name="合成",
        api_key="synthetic",
        base_url="https://synthetic.invalid/v1",
        provider_type="openai",
    )
    monkeypatch.setattr(model_cache, "get_model_info", lambda _: info)
    monkeypatch.setattr(health_consultation_service, "require_consultation_attempt", AsyncMock())
    await seed_price(budget_db, budget.model_target(info))

    @dataclass
    class Context:
        """仅包含测试调用必需的服务端运行身份。"""

        model: str = "synthetic:fixed"
        thread_id: str = "synthetic-thread"
        run_id: str = "synthetic-run"

    async def send(client, request, **kwargs):
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "synthetic-response",
                "object": "chat.completion",
                "created": 1,
                "model": "fixed",
                "choices": [
                    {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "合成解释"}}
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    graph = create_agent(
        model=load_chat_model(info.spec),
        tools=[],
        middleware=[HealthAiBudgetMiddleware(purpose)],
        context_schema=Context,
    )
    result = await graph.ainvoke({"messages": [HumanMessage(content="合成问题")]}, context=Context())
    assert result["messages"][-1].content == "合成解释"
    async with budget_db.get_async_session_context() as session:
        call = (await session.scalars(select(HealthAiCall))).one()
        assert call.purpose == purpose and call.owner_id == "synthetic-run"
        assert call.charged_cny == Decimal("0.09") and call.status == "settled"


@pytest.mark.parametrize("change", ["credentials", "permission"])
async def test_budget_wait_cannot_send_under_changed_identity_or_authorization(budget_db, monkeypatch, change):
    """预留等待中换计费账号或撤权后，合成传输必须零请求。"""
    from unittest.mock import AsyncMock
    from yuxi.services.health_vision_provider import call_json_model

    info = ModelInfo(
        provider_id="synthetic",
        model_id="fixed",
        model_type="chat",
        display_name="合成",
        api_key="synthetic",
        base_url="https://synthetic.invalid/v1",
        provider_type="openai",
    )
    current = [info]
    monkeypatch.setattr(model_cache, "get_model_info", lambda _: current[0])
    await seed_price(budget_db, budget.model_target(info))
    original = budget.reserve
    authorize = AsyncMock()

    async def reserve_then_change(*args, **kwargs):
        result = await original(*args, **kwargs)
        if change == "credentials":
            current[0] = replace(info, api_key="changed", base_url="https://changed.invalid/v1")
        else:
            authorize.side_effect = HealthVisionError("not_found", "已撤权", 404)
        return result

    monkeypatch.setattr(budget, "reserve", reserve_then_change)
    transport = AsyncMock(side_effect=AssertionError("预算等待后不应外呼"))
    monkeypatch.setattr(httpx.AsyncClient, "send", transport)
    with pytest.raises(HealthVisionError, match="policy_changed|not_found"):
        await call_json_model(
            info.spec,
            "合成指令",
            [],
            SimpleNamespace(task_id="synthetic-task", raise_if_cancelled=AsyncMock()),
            authorize=authorize,
        )
    transport.assert_not_called()
    async with budget_db.get_async_session_context() as session:
        account = (await session.scalars(select(HealthAiMonth))).one()
        assert account.occupied_cny == Decimal("10")


async def test_ocr_submission_charges_once_and_resume_does_not_resubmit(budget_db, monkeypatch):
    """合成 OCR POST/GET 与真实账本共同证明恢复轮询不重复扣费。"""
    import json
    from unittest.mock import AsyncMock
    from yuxi.services.health_vision_provider import parse_report_page

    endpoint = "https://synthetic.invalid/ocr"
    price = HealthAiPriceInput(
        kind="ocr",
        ocr_endpoint=endpoint,
        fixed_cny_per_page=Decimal("0.1"),
        valid_until=datetime.now(UTC) + timedelta(days=1),
        evidence="合成 OCR 单页固定费用用于边界测试",
        upper_bound_verified=True,
    )
    await seed_price(budget_db, budget.ocr_target(endpoint, "synthetic"), price)
    requests = []

    async def send(client, request, **kwargs):
        requests.append((request.method, str(request.url)))
        if request.method == "POST":
            return httpx.Response(200, request=request, json={"data": {"jobId": "synthetic-job"}})
        if str(request.url).endswith("/synthetic-job"):
            return httpx.Response(
                200,
                request=request,
                json={"data": {"state": "done", "resultUrl": {"jsonUrl": "https://synthetic.invalid/result"}}},
            )
        return httpx.Response(
            200,
            request=request,
            content=json.dumps(
                {"result": {"layoutParsingResults": [{"markdown": {"text": "血糖 6.8 mmol/L"}}]}}
            ).encode(),
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    context = SimpleNamespace(task_id="synthetic-task", raise_if_cancelled=AsyncMock())
    for job_id in [None, "synthetic-job"]:
        result = await parse_report_page(
            b"synthetic-image",
            {"page_index": 0},
            {"api_token": "synthetic", "api_url": endpoint},
            context,
            AsyncMock(),
            authorize=AsyncMock(),
            provider_job_id=job_id,
        )
        assert result["provider_job_id"] == "synthetic-job"
    assert sum(method == "POST" for method, _ in requests) == 1
    async with budget_db.get_async_session_context() as session:
        call = (await session.scalars(select(HealthAiCall))).one()
        assert call.status == "settled" and call.charged_cny == Decimal("0.1")


async def test_ocr_revoked_while_reserving_does_not_upload(budget_db, monkeypatch):
    """OCR 初次检查通过但预算等待期间撤权，图片仍不能发送。"""
    from unittest.mock import AsyncMock
    from yuxi.services.health_vision_provider import parse_report_page

    endpoint = "https://synthetic.invalid/ocr"
    price = HealthAiPriceInput(
        kind="ocr",
        ocr_endpoint=endpoint,
        fixed_cny_per_page=Decimal("0.1"),
        valid_until=datetime.now(UTC) + timedelta(days=1),
        evidence="合成 OCR 单页固定费用用于边界测试",
        upper_bound_verified=True,
    )
    await seed_price(budget_db, budget.ocr_target(endpoint, "synthetic"), price)
    authorize = AsyncMock(side_effect=[None, HealthVisionError("not_found", "已撤权", 404)])
    transport = AsyncMock(side_effect=AssertionError("不应上传"))
    monkeypatch.setattr(httpx.AsyncClient, "send", transport)
    with pytest.raises(HealthVisionError, match="not_found"):
        await parse_report_page(
            b"synthetic-image",
            {"page_index": 0},
            {"api_token": "synthetic", "api_url": endpoint},
            SimpleNamespace(task_id="synthetic-task", raise_if_cancelled=AsyncMock()),
            AsyncMock(),
            authorize=authorize,
        )
    transport.assert_not_called()


async def test_opening_is_immutable_and_schema_upgrade_preserves_ledger(budget_db):
    """旧账确认不能覆盖，增量健康迁移重复执行保留已提交账本。"""
    with pytest.raises(HealthVisionError, match="budget_opening_conflict"):
        await budget.initialize_budget(
            "synthetic-admin", HealthAiOpeningInput(occupied_cny=20, evidence="更改期初不得覆盖已有确认", verified=True)
        )
    await seed_price(budget_db)
    call = await budget.reserve("meal", "synthetic-task", "synthetic")
    await budget_db.create_business_tables()
    await budget_db.create_health_tables()
    await budget_db.create_health_tables()
    async with budget_db.get_async_session_context() as session:
        row = await session.get(HealthAiCall, call.call_id)
        assert row.reserved_cny == Decimal("10") and row.charged_cny is None


async def test_missing_opening_denies_and_prior_spend_is_never_reset(budget_db):
    """启用前拒绝外呼，已有三十五元占用只允许五元以下的调用。"""
    from sqlalchemy import delete
    from yuxi.storage.postgres.models_health_budget import HealthAiOpening

    async with budget_db.get_async_session_context() as session:
        await session.execute(delete(HealthAiMonth))
        await session.execute(delete(HealthAiOpening))
    await seed_price(budget_db)
    with pytest.raises(HealthVisionError, match="budget_price_unavailable"):
        await budget.reserve("meal", "task", "synthetic")
    data = HealthAiOpeningInput(occupied_cny=35, evidence="合成当月已有费用与未决费用共三十五元", verified=True)
    await budget.initialize_budget("synthetic-admin", data)
    await budget.initialize_budget("synthetic-admin", data)
    with pytest.raises(HealthVisionError, match="budget_exceeded"):
        await budget.reserve("meal", "task", "synthetic")
    async with budget_db.get_async_session_context() as session:
        assert (await session.scalars(select(HealthAiMonth))).one().occupied_cny == Decimal("35")
        assert (await session.scalars(select(HealthAiCall))).all() == []


async def test_budget_http_admin_boundary_and_persistent_status(budget_db, monkeypatch):
    """真实路由与管理员依赖连接独立 PG；仅替代登录身份和配置来源。"""
    from unittest.mock import AsyncMock
    from fastapi import FastAPI, Header, HTTPException
    from server.routers.health_vision_router import health_vision
    from server.utils.auth_middleware import get_required_user
    from yuxi.services import health_vision_service

    app = FastAPI()
    app.include_router(health_vision, prefix="/api")

    async def identity(x_test_role: str | None = Header(None)):
        """合成身份不替代被测管理员权限判断。"""
        if x_test_role is None:
            raise HTTPException(401)
        return SimpleNamespace(uid="synthetic-admin", role=x_test_role)

    app.dependency_overrides[get_required_user] = identity
    info = ModelInfo(
        provider_id="synthetic",
        model_id="fixed",
        model_type="chat",
        display_name="合成",
        api_key="synthetic",
        base_url="https://synthetic.invalid/v1",
        provider_type="openai",
    )
    monkeypatch.setattr(health_vision_service, "current_health_model_info", AsyncMock(return_value=info))
    admin = {"x-test-role": "admin"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for headers, code in [({}, 401), ({"x-test-role": "user"}, 403)]:
            assert (await client.get("/api/health/v1/budget", headers=headers)).status_code == code
            assert (
                await client.post(
                    "/api/health/v1/budget/prices", headers=headers, json=synthetic_price().model_dump(mode="json")
                )
            ).status_code == code
            assert (
                await client.post(
                    "/api/health/v1/budget/opening",
                    headers=headers,
                    json={"occupied_cny": "0", "evidence": "不允许普通用户重置任何项目预算", "verified": True},
                )
            ).status_code == code
        price = await client.post(
            "/api/health/v1/budget/prices", headers=admin, json=synthetic_price().model_dump(mode="json")
        )
        assert price.status_code == 201, price.text
        reservation = await budget.reserve("consultation", "run", budget.model_target(info))
        response = await client.get("/api/health/v1/budget", headers=admin)
        assert response.status_code == 200
        result = response.json()
        assert Decimal(result["occupied_cny"]) == Decimal("10")
        assert Decimal(result["remaining_cny"]) == Decimal("30")
        assert result["calls"][0]["id"] == reservation.call_id
        reset = await client.post(
            "/api/health/v1/budget/opening",
            headers=admin,
            json={"occupied_cny": "0", "evidence": "不能通过新证据覆盖启用时的费用", "verified": True},
        )
        assert reset.status_code == 409
    async with budget_db.get_async_session_context() as session:
        assert (await session.scalars(select(HealthAiMonth))).one().occupied_cny == Decimal("10")

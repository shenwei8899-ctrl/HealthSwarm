"""固定会话的独立 OpenAPI、原始 wire 和非法服务返回验证。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.exceptions import ResponseValidationError

from server.routers import health_vision_router as routes
from server.utils.auth_middleware import get_required_user
from yuxi.services import health_dialog_feedback_service

MEMBER_ID = "20000000-0000-4000-8000-000000000001"
THREAD_ID = "20000000-0000-4000-8000-000000000002"
RECORD_ID = "20000000-0000-4000-8000-000000000003"
PLAN_ID = "20000000-0000-4000-8000-000000000004"
KEY = "20000000-0000-4000-8000-000000000005"
PLANNER = "/api/health/v1/members/{member_id}/meal-planner"
ANALYST = "/api/health/v1/members/{member_id}/diet-analyst"
FEEDBACK = "/api/health/v1/diet-logs/{record_id}/feedback-conversation"
SAFE = "/api/health/v1/members/{member_id}/safe-meal-plan-conversations"
BASE = {"thread_id": THREAD_ID, "member_id": MEMBER_ID, "business_date": None, "feedback_selection": None}
PLANNER_WIRE = {**BASE, "agent_slug": "health-meal-planner"}
ANALYST_WIRE = {**BASE, "agent_slug": "health-diet-analyst"}
TARGET = {"rule_code": "synthetic-target", "rule_version": 2, "profile_version": 3}
MEAL = {"record_id": RECORD_ID, "source_version": 4}
SAFE_SELECTION = {
    "plan_id": PLAN_ID,
    "version": 2,
    "rule_code": "synthetic-safe",
    "rule_version": 3,
    "profile_version": 4,
}
FEEDBACK_WIRE = {**ANALYST_WIRE, "feedback_selection": MEAL}
SAFE_WIRE = {**PLANNER_WIRE, "safe_selection": SAFE_SELECTION}


@pytest.fixture
def conversation_contract_app():
    """使用实际四个路由，认证和业务 I/O 由替身隔离。"""
    app = FastAPI()
    selected = APIRouter()
    selected.routes = [
        route for route in routes.health_vision.routes if "/api" + route.path in {PLANNER, ANALYST, FEEDBACK, SAFE}
    ]
    app.include_router(selected, prefix="/api")
    app.dependency_overrides[get_required_user] = lambda: SimpleNamespace(uid="synthetic-actor")
    return app


@pytest.mark.parametrize(
    "path,expected",
    [
        (PLANNER, {"$ref": "#/components/schemas/MealPlannerConversationResult"}),
        (
            ANALYST,
            {
                "anyOf": [
                    {"$ref": "#/components/schemas/DietAnalystConversationResult"},
                    {"$ref": "#/components/schemas/TargetedDietAnalystConversationResult"},
                ]
            },
        ),
        (FEEDBACK, {"$ref": "#/components/schemas/FeedbackConversationResult"}),
        (SAFE, {"$ref": "#/components/schemas/SafeMealPlannerConversationResult"}),
    ],
)
def test_openapi_declares_four_original_success_shapes(conversation_contract_app, path, expected):
    """201 的 schema oracle 不从实现类型生成。"""
    actual = conversation_contract_app.openapi()["paths"][path]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"]
    assert {key: value for key, value in actual.items() if key != "title"} == expected


def test_schemas_require_fixed_roles_and_present_source_versions(conversation_contract_app):
    """未选择目标不声明默认字段，已选来源必须完整且无额外数据。"""
    schemas = conversation_contract_app.openapi()["components"]["schemas"]
    common = {"thread_id", "member_id", "agent_slug", "business_date", "feedback_selection"}
    models = [
        ("MealPlannerConversationResult", "health-meal-planner", set()),
        ("DietAnalystConversationResult", "health-diet-analyst", set()),
        ("TargetedDietAnalystConversationResult", "health-diet-analyst", {"target_selection"}),
        ("FeedbackConversationResult", "health-diet-analyst", set()),
        ("SafeMealPlannerConversationResult", "health-meal-planner", {"safe_selection"}),
    ]
    for name, role, extra in models:
        model = schemas[name]
        assert set(model["required"]) == common | extra
        assert set(model["properties"]) == common | extra
        assert model["additionalProperties"] is False
        properties = model["properties"]
        assert properties["agent_slug"]["const"] == role
        assert properties["thread_id"]["format"] == "uuid" and properties["member_id"]["format"] == "uuid"
        assert properties["business_date"]["type"] == "null"
        if name == "FeedbackConversationResult":
            assert properties["feedback_selection"] == {"$ref": "#/components/schemas/DietAnalysisSelection"}
        else:
            assert properties["feedback_selection"]["type"] == "null"
    for name, fields in [
        ("PersonalTargetSelection", {"rule_code", "rule_version", "profile_version"}),
        ("DietAnalysisSelection", {"record_id", "source_version"}),
        ("SafePlannerSelection", {"plan_id", "version", "rule_code", "rule_version", "profile_version"}),
    ]:
        assert set(schemas[name]["required"]) == fields
        assert set(schemas[name]["properties"]) == fields
        assert schemas[name]["additionalProperties"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,payload",
    [
        ("planner", PLANNER_WIRE),
        ("analyst", ANALYST_WIRE),
        ("targeted", {**ANALYST_WIRE, "target_selection": TARGET}),
        ("feedback", FEEDBACK_WIRE),
        ("safe", SAFE_WIRE),
    ],
)
async def test_response_preserves_exact_role_and_selected_or_absent_sources(
    conversation_contract_app, monkeypatch, operation, payload
):
    """实际序列化保持目标缺省、反馈确认版本和安全餐单选择。"""
    request = _request_and_mock(monkeypatch, operation, payload)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=conversation_contract_app), base_url="http://test"
    ) as client:
        response = await client.post(**request)
    assert response.status_code == 201
    assert response.json() == payload, "fixed_conversation_wire_contract"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,payload",
    [
        ("planner", {key: value for key, value in PLANNER_WIRE.items() if key != "thread_id"}),
        ("planner", {**PLANNER_WIRE, "thread_id": "not-a-uuid"}),
        ("planner", {**PLANNER_WIRE, "member_id": "not-a-uuid"}),
        ("planner", {**PLANNER_WIRE, "agent_slug": "health-consultation"}),
        ("planner", {key: value for key, value in PLANNER_WIRE.items() if key != "business_date"}),
        ("planner", {**PLANNER_WIRE, "business_date": "2026-10-13"}),
        ("planner", {**PLANNER_WIRE, "feedback_selection": MEAL}),
        ("planner", {**PLANNER_WIRE, "owner_uid": "private-owner"}),
        ("planner", {**PLANNER_WIRE, "safe_selection": SAFE_SELECTION}),
        ("analyst", {**ANALYST_WIRE, "agent_slug": "health-meal-planner"}),
        ("analyst", {**ANALYST_WIRE, "target_selection": None}),
        ("targeted", {**ANALYST_WIRE, "target_selection": {"rule_code": "synthetic-target", "rule_version": 2}}),
        ("targeted", {**ANALYST_WIRE, "target_selection": {**TARGET, "profile_version": 0}}),
        ("targeted", {**ANALYST_WIRE, "target_selection": {**TARGET, "rule_version": True}}),
        ("targeted", {**ANALYST_WIRE, "target_selection": {**TARGET, "source_hash": "private-proof"}}),
        ("feedback", {**FEEDBACK_WIRE, "feedback_selection": None}),
        ("feedback", {key: value for key, value in FEEDBACK_WIRE.items() if key != "feedback_selection"}),
        ("feedback", {**FEEDBACK_WIRE, "feedback_selection": {**MEAL, "record_id": "not-a-uuid"}}),
        ("feedback", {**FEEDBACK_WIRE, "feedback_selection": {**MEAL, "source_version": 0}}),
        ("feedback", {**FEEDBACK_WIRE, "feedback_selection": {**MEAL, "source_version": True}}),
        ("feedback", {**FEEDBACK_WIRE, "feedback_selection": {**MEAL, "actor_uid": "private-actor"}}),
        ("feedback", {**FEEDBACK_WIRE, "target_selection": TARGET}),
        ("safe", {key: value for key, value in SAFE_WIRE.items() if key != "safe_selection"}),
        ("safe", {**SAFE_WIRE, "safe_selection": None}),
        ("safe", {**SAFE_WIRE, "safe_selection": {**SAFE_SELECTION, "plan_id": "not-a-uuid"}}),
        ("safe", {**SAFE_WIRE, "safe_selection": {**SAFE_SELECTION, "version": 0}}),
        ("safe", {**SAFE_WIRE, "safe_selection": {**SAFE_SELECTION, "profile_version": True}}),
        ("safe", {**SAFE_WIRE, "safe_selection": {**SAFE_SELECTION, "source_hash": "private-proof"}}),
    ],
)
async def test_response_boundary_rejects_wrong_roles_sources_and_private_fields(
    conversation_contract_app, monkeypatch, operation, payload
):
    """错误角色、非法来源版本和额外数据不能通过成功响应边界。"""
    request = _request_and_mock(monkeypatch, operation, payload)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=conversation_contract_app), base_url="http://test"
    ) as client:
        with pytest.raises(ResponseValidationError):
            await client.post(**request)


def _request_and_mock(monkeypatch, operation, payload):
    """替换业务输出，构造既有输入；四项不要求额外请求头。"""
    body = {"client_request_id": KEY}
    if operation == "feedback":
        monkeypatch.setattr(
            health_dialog_feedback_service, "create_feedback_conversation", AsyncMock(return_value=payload)
        )
        return {"url": FEEDBACK.format(record_id=RECORD_ID), "json": {**body, "source_version": MEAL["source_version"]}}
    monkeypatch.setattr(routes, "create_consultation", AsyncMock(return_value=payload))
    if operation == "safe":
        return {"url": SAFE.format(member_id=MEMBER_ID), "json": {**body, **SAFE_SELECTION}}
    if operation == "targeted":
        body["target_selection"] = TARGET
    return {"url": (PLANNER if operation == "planner" else ANALYST).format(member_id=MEMBER_ID), "json": body}

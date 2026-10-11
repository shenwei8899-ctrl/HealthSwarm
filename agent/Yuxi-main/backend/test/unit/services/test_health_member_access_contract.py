"""成员、授权和用途同意的 OpenAPI 与独立响应边界验证。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.exceptions import ResponseValidationError

from server.routers import health_vision_router as routes
from server.utils.auth_middleware import get_required_user

MEMBER_ID = "20000000-0000-4000-8000-000000000001"
OTHER_ID = "20000000-0000-4000-8000-000000000002"
MEMBERS = "/api/health/v1/members"
GRANTS = MEMBERS + "/{member_id}/grants"
CONSENTS = MEMBERS + "/{member_id}/processing-consents"
SUMMARY = {
    "id": MEMBER_ID,
    "display_name": "合成 成员",
    "relationship_label": "本人",
    "is_owner": True,
    "scopes": ["profile_view", "ai_use", "profile_edit"],
}


@pytest.fixture
def access_contract_app():
    """使用实际四个路由；替身仅隔离认证和业务 I/O。"""
    app = FastAPI()
    selected = APIRouter()
    selected.routes = [
        route for route in routes.health_vision.routes if "/api" + route.path in {MEMBERS, GRANTS, CONSENTS}
    ]
    app.include_router(selected, prefix="/api")
    app.dependency_overrides[get_required_user] = lambda: SimpleNamespace(uid="synthetic-actor")
    return app


@pytest.mark.parametrize(
    "path,method,status,expected",
    [
        (MEMBERS, "get", "200", {"type": "array", "items": {"$ref": "#/components/schemas/HealthMemberSummary"}}),
        (MEMBERS, "post", "201", {"$ref": "#/components/schemas/HealthMemberCreateResult"}),
        (GRANTS, "put", "200", {"$ref": "#/components/schemas/HealthGrantResult"}),
        (CONSENTS, "post", "200", {"$ref": "#/components/schemas/HealthProcessingConsentResult"}),
    ],
)
def test_openapi_publishes_existing_array_and_success_results(access_contract_app, path, method, status, expected):
    """四个 schema oracle 独立声明原数组与结果形状。"""
    schema = access_contract_app.openapi()["paths"][path][method]["responses"][status]["content"]["application/json"][
        "schema"
    ]
    assert {key: value for key, value in schema.items() if key != "title"} == expected


def test_output_schemas_require_original_fields_and_exclude_private_data(access_contract_app):
    """成功 DTO 不包含家庭身份、账号、政策正文或可省略字段。"""
    schemas = access_contract_app.openapi()["components"]["schemas"]
    expected_fields = {
        "HealthMemberSummary": {"id", "display_name", "relationship_label", "is_owner", "scopes"},
        "HealthMemberCreateResult": {"id"},
        "HealthGrantResult": {"saved"},
        "HealthProcessingConsentResult": {"accepted"},
    }
    for name, fields in expected_fields.items():
        assert set(schemas[name]["properties"]) == fields
        assert set(schemas[name]["required"]) == fields
        assert schemas[name]["additionalProperties"] is False
    summary = schemas["HealthMemberSummary"]["properties"]
    assert summary["id"]["format"] == "uuid"
    assert summary["is_owner"]["type"] == "boolean"
    assert summary["scopes"]["type"] == "array" and summary["scopes"]["items"] == {"type": "string"}
    assert schemas["HealthMemberCreateResult"]["properties"]["id"]["format"] == "uuid"
    assert schemas["HealthGrantResult"]["properties"]["saved"]["const"] is True
    consent = schemas["HealthProcessingConsentResult"]["properties"]["accepted"]
    assert consent["type"] == "boolean" and "const" not in consent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,payload",
    [
        ("members_get", []),
        ("members_get", [SUMMARY]),
        (
            "members_get",
            [SUMMARY, {**SUMMARY, "id": OTHER_ID, "is_owner": False, "scopes": ["ai_use", "profile_view"]}],
        ),
        ("members_post", {"id": MEMBER_ID}),
        ("grant_put", {"saved": True}),
        ("consent_accept", {"accepted": True}),
        ("consent_revoke", {"accepted": False}),
    ],
)
async def test_response_keeps_exact_wire_and_both_consent_choices(access_contract_app, monkeypatch, operation, payload):
    """成员裸数组、授权顺序及撤回 false 必须通过实际序列化保留。"""
    method_name, request, expected_status = _operation_request(operation)
    mocked = AsyncMock(return_value=payload)
    monkeypatch.setattr(routes.service, method_name, mocked)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=access_contract_app), base_url="http://test"
    ) as client:
        response = await client.request(**request)
    assert response.status_code == expected_status, "member_access_success_status"
    assert response.json() == payload, "member_access_wire_contract"
    assert mocked.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,payload",
    [
        ("members_get", {"members": []}),
        ("members_get", [{key: value for key, value in SUMMARY.items() if key != "scopes"}]),
        ("members_get", [{**SUMMARY, "owner_uid": "private-owner"}]),
        ("members_get", [{**SUMMARY, "id": "not-a-health-uuid"}]),
        ("members_get", [{**SUMMARY, "is_owner": None}]),
        ("members_get", [{**SUMMARY, "scopes": [None]}]),
        ("members_post", {}),
        ("members_post", {"id": MEMBER_ID, "source_member_id": OTHER_ID}),
        ("grant_put", {"saved": False}),
        ("grant_put", {}),
        ("grant_put", {"saved": True, "actor_uid": "private-actor"}),
        ("consent_accept", {}),
        ("consent_accept", {"accepted": None}),
        ("consent_revoke", {"accepted": False, "processor": "private-processor"}),
    ],
)
async def test_response_boundary_rejects_contract_drift(access_contract_app, monkeypatch, operation, payload):
    """服务缺字段、错误形状或私人额外数据不能通过成功响应边界。"""
    method_name, request, _ = _operation_request(operation)
    monkeypatch.setattr(routes.service, method_name, AsyncMock(return_value=payload))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=access_contract_app), base_url="http://test"
    ) as client:
        with pytest.raises(ResponseValidationError):
            await client.request(**request)


def _operation_request(operation):
    """构造现有请求 DTO，不给四个操作增添幂等或版本头。"""
    if operation == "members_get":
        return "members", {"method": "GET", "url": MEMBERS}, 200
    if operation == "members_post":
        return (
            "create_member",
            {
                "method": "POST",
                "url": MEMBERS,
                "json": {"display_name": "合成 成员", "relationship_label": "本人", "authorized": True},
            },
            201,
        )
    if operation == "grant_put":
        return (
            "grant",
            {
                "method": "PUT",
                "url": GRANTS.format(member_id=MEMBER_ID),
                "json": {"actor_uid": "synthetic-delegate", "scopes": ["ai_use", "profile_view"]},
            },
            200,
        )
    return (
        "consent",
        {
            "method": "POST",
            "url": CONSENTS.format(member_id=MEMBER_ID),
            "json": {
                "purpose": "consultation",
                "accepted": operation == "consent_accept",
                "processor": "synthetic-processor",
                "policy_version": "synthetic-policy",
            },
        },
        200,
    )

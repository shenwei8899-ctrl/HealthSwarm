"""本人关联和普通咨询的 OpenAPI、精确 wire 与响应校验。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.exceptions import ResponseValidationError

from server.routers import health_vision_router as routes
from server.utils.auth_middleware import get_required_user

MEMBER_ID = "10000000-0000-4000-8000-000000000001"
SOURCE_ID = "10000000-0000-4000-8000-000000000002"
FAMILY_ID = "10000000-0000-4000-8000-000000000003"
THREAD_ID = "10000000-0000-4000-8000-000000000004"
REQUEST_ID = "10000000-0000-4000-8000-000000000005"
LINK_PATH = "/api/health/v1/members/{member_id}/family-profile-link"
CONSULTATION_PATH = "/api/health/v1/members/{member_id}/consultations"
UNLINKED = {"member_id": MEMBER_ID, "source_member_id": None, "scope": "self_confirmed_profile"}
LINKED = {**UNLINKED, "source_member_id": SOURCE_ID, "family_id": FAMILY_ID}
CONSULTATION = {
    "thread_id": THREAD_ID,
    "member_id": MEMBER_ID,
    "agent_slug": "health-consultation",
    "business_date": None,
    "feedback_selection": None,
}
LIST_ITEM = {
    "thread_id": THREAD_ID,
    "member_id": MEMBER_ID,
    "agent_slug": "health-consultation",
    "business_date": None,
    "created_at": "2026-10-11T01:02:03Z",
}


@pytest.fixture
def contract_app():
    """装配实际四个路由，业务替身不替代 HTTP 响应校验。"""
    app = FastAPI()
    selected = APIRouter()
    selected.routes = [
        route for route in routes.health_vision.routes if "/api" + route.path in {LINK_PATH, CONSULTATION_PATH}
    ]
    app.include_router(selected, prefix="/api")
    app.dependency_overrides[get_required_user] = lambda: SimpleNamespace(uid="synthetic-actor")
    return app


@pytest.mark.parametrize(
    "path,method,status,expected",
    [
        (
            LINK_PATH,
            "get",
            "200",
            {
                "anyOf": [
                    {"$ref": "#/components/schemas/FamilyProfileUnlinkedResult"},
                    {"$ref": "#/components/schemas/FamilyProfileLinkResult"},
                ]
            },
        ),
        (LINK_PATH, "post", "200", {"$ref": "#/components/schemas/FamilyProfileLinkResult"}),
        (CONSULTATION_PATH, "get", "200", {"$ref": "#/components/schemas/ConsultationListResult"}),
        (CONSULTATION_PATH, "post", "201", {"$ref": "#/components/schemas/ConsultationResult"}),
    ],
)
def test_openapi_operations_publish_success_shapes(contract_app, path, method, status, expected):
    """未声明响应模型的原缺陷不能通过四个 operation 的 schema oracle。"""
    schema = contract_app.openapi()["paths"][path][method]["responses"][status]["content"]["application/json"]["schema"]
    assert {key: value for key, value in schema.items() if key != "title"} == expected


def test_openapi_preserves_required_fields_nulls_and_fixed_role(contract_app):
    """缺省家庭字段、必需的 null 和普通角色属于现有客户端 wire。"""
    schemas = contract_app.openapi()["components"]["schemas"]
    fields = {
        "FamilyProfileUnlinkedResult": {"member_id", "source_member_id", "scope"},
        "FamilyProfileLinkResult": {"member_id", "source_member_id", "family_id", "scope"},
        "ConsultationResult": {"thread_id", "member_id", "agent_slug", "business_date", "feedback_selection"},
        "ConsultationListItem": {"thread_id", "member_id", "agent_slug", "business_date", "created_at"},
        "ConsultationListResult": {"items", "has_more", "next_offset"},
    }
    for name, expected in fields.items():
        assert set(schemas[name]["properties"]) == expected
        assert set(schemas[name]["required"]) == expected
        assert schemas[name]["additionalProperties"] is False
    assert schemas["FamilyProfileUnlinkedResult"]["properties"]["source_member_id"]["type"] == "null"
    assert schemas["FamilyProfileLinkResult"]["properties"]["family_id"]["format"] == "uuid"
    for name in ("ConsultationResult", "ConsultationListItem"):
        properties = schemas[name]["properties"]
        assert properties["agent_slug"]["const"] == "health-consultation"
        assert properties["business_date"]["anyOf"] == [{"type": "string", "format": "date"}, {"type": "null"}]
    assert schemas["ConsultationResult"]["properties"]["feedback_selection"]["type"] == "null"
    assert schemas["ConsultationListResult"]["properties"]["next_offset"]["anyOf"] == [
        {"type": "integer"},
        {"type": "null"},
    ]
    assert schemas["ConsultationListResult"]["properties"]["items"]["items"] == {
        "$ref": "#/components/schemas/ConsultationListItem"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,payload",
    [
        ("link_get", UNLINKED),
        ("link_get", LINKED),
        ("link_post", LINKED),
        ("consultation_post", CONSULTATION),
        ("consultation_post", {**CONSULTATION, "business_date": "2026-10-11"}),
        ("consultation_get", {"items": [], "has_more": False, "next_offset": None}),
        ("consultation_get", {"items": [LIST_ITEM], "has_more": False, "next_offset": None}),
        (
            "consultation_get",
            {"items": [{**LIST_ITEM, "business_date": "2026-10-11"}], "has_more": True, "next_offset": 20},
        ),
    ],
)
async def test_response_validation_keeps_exact_existing_wire(contract_app, monkeypatch, operation, payload):
    """通过实际响应序列化核对绑定、日期和分页，字典替身仅隔离业务 I/O。"""
    service_name, request, status = _operation_request(operation)
    mocked = AsyncMock(return_value=payload)
    monkeypatch.setattr(routes, service_name, mocked)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=contract_app), base_url="http://test") as client:
        response = await client.request(**request)
    assert response.status_code == status
    assert response.json() == payload
    if operation == "link_get":
        assert response.headers["cache-control"] == "no-store"
    assert mocked.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,payload",
    [
        ("link_get", {**UNLINKED, "family_id": FAMILY_ID}),
        ("link_get", {key: value for key, value in LINKED.items() if key != "family_id"}),
        ("link_post", UNLINKED),
        ("consultation_post", {**CONSULTATION, "agent_slug": "health-meal-planner"}),
        ("consultation_post", {**CONSULTATION, "feedback_selection": {"record_id": SOURCE_ID, "source_version": 1}}),
        ("consultation_post", {key: value for key, value in CONSULTATION.items() if key != "feedback_selection"}),
        (
            "consultation_get",
            {"items": [{**LIST_ITEM, "agent_slug": "health-meal-planner"}], "has_more": False, "next_offset": None},
        ),
        (
            "consultation_get",
            {"items": [{**LIST_ITEM, "content": "private-body"}], "has_more": False, "next_offset": None},
        ),
        ("consultation_get", {"items": [], "has_more": False}),
    ],
)
async def test_response_boundary_rejects_contract_drift(contract_app, monkeypatch, operation, payload):
    """错误形状须在响应边界失败，不能以 2xx 公开其他角色或正文。"""
    service_name, request, _ = _operation_request(operation)
    monkeypatch.setattr(routes, service_name, AsyncMock(return_value=payload))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=contract_app), base_url="http://test") as client:
        with pytest.raises(ResponseValidationError):
            await client.request(**request)


def _operation_request(operation):
    """构造四个真实入口已有的合法请求包，响应 oracle 不从 DTO 派生。"""
    if operation.startswith("link"):
        path = LINK_PATH
        body = {"family_id": FAMILY_ID, "source_member_id": SOURCE_ID, "confirmed_identity": True}
        service_name = "read_family_profile" if operation.endswith("get") else "link_family_profile"
        status = 200
    else:
        path = CONSULTATION_PATH
        body = {"client_request_id": REQUEST_ID}
        service_name = "list_consultations" if operation.endswith("get") else "create_consultation"
        status = 200 if operation.endswith("get") else 201
    request = {"method": "GET" if operation.endswith("get") else "POST", "url": path.format(member_id=MEMBER_ID)}
    if request["method"] == "POST":
        request.update(json=body, headers={"Idempotency-Key": REQUEST_ID})
    return service_name, request, status

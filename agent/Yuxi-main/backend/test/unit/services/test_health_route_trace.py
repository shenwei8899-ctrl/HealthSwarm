"""使用真实HTTP适配器与日志sink核对错误追踪，禁止私有请求进入日志。"""

import io
import json
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI, Request

from server.routers.health_vision_router import HealthRoute
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.utils.logging_config import logger


@pytest.mark.asyncio
@pytest.mark.parametrize("status,retryable", [(404, False), (409, False), (429, True), (503, True)])
async def test_response_trace_matches_searchable_safe_log(status, retryable):
    app = FastAPI()

    async def fail(request: Request):
        """合成异常正文含私有内容，日志必须只包含受控元数据。"""
        raise HealthVisionError("synthetic_failure", "private-patient-detail", status)

    app.router.routes.append(HealthRoute("/health/v1/members/{member_id}/synthetic", fail, methods=["POST"]))
    sink = io.StringIO()
    sink_id = logger.add(sink, format="{message}", enqueue=False)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/health/v1/members/private-member-id/synthetic?secret=private-query",
                headers={"Authorization": "Bearer private-token"},
                json={"health": "private-body"},
            )
        assert response.status_code == status
        body = response.json()
        assert str(UUID(body["trace_id"])) == body["trace_id"]
        assert body["retryable"] is retryable
        assert response.headers["cache-control"] == "no-store"
        line = sink.getvalue().strip()
        assert line.startswith("health_business_error ")
        assert json.loads(line.removeprefix("health_business_error ")) == {
            "trace_id": body["trace_id"],
            "method": "POST",
            "route": "/health/v1/members/{member_id}/synthetic",
            "status": status,
            "code": "synthetic_failure",
        }
        assert "private" not in line and "Authorization" not in line
    finally:
        logger.remove(sink_id)

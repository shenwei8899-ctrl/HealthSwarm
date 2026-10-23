"""仅为内部重放模型准备真实预算账本，不替代生产核账。"""

import os
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import text

from yuxi.models.providers.cache import model_cache
from yuxi.services.health_vision_service import current_health_model_info
from yuxi.services.ocr_service import resolve_ocr_task_params
from yuxi.storage.postgres.manager import pg_manager


async def approve_synthetic_budget(client, headers, model_spec, *, ocr=False):
    """校验实际库和当前内部端点，再经管理员接口登记合成价格。"""
    assert os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") == "true"
    assert str(client.base_url).rstrip("/") == "http://localhost:5050"
    async with pg_manager.get_async_session_context() as session:
        assert await session.scalar(text("SELECT current_database()")) == "health_consultation_e2e"
        model_cache.refresh()
        info = await current_health_model_info(session, model_spec)
    assert info is not None, "合成模型必须与最新数据库配置一致"
    endpoint = urlsplit(info.base_url)
    assert endpoint.scheme in {"http", "https"} and endpoint.hostname == "api"
    assert endpoint.port in {8766, 8767, 8768, 8769, 8770, 8775, 8778, 8779, 8780}
    assert endpoint.path == "/v1" and not endpoint.query and not endpoint.fragment
    assert "replay-" in info.provider_id and info.api_key.startswith("synthetic-")
    ocr_endpoint = None
    if ocr:
        params = (await resolve_ocr_task_params({"ocr_engine": "paddleocr_vl_1_6"}))["_ocr_processor_kwargs"]
        ocr_endpoint = params["api_url"]
        assert ocr_endpoint == "https://api:8768/api/v2/ocr/jobs"
        assert params["api_token"] == "synthetic-health-ocr-key"
    opening = await client.post(
        "/api/health/v1/budget/opening",
        headers=headers,
        json={"occupied_cny": "0", "verified": True, "evidence": "专用合成E2E库，仅内部固定回放，无真实供应商费用"},
    )
    assert opening.status_code == 201, opening.text
    common = {
        "valid_until": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        "upper_bound_verified": True,
        "evidence": "仅内部固定输出回放的合成价格；非生产牌价或费用上界批准",
    }
    price = await client.post(
        "/api/health/v1/budget/prices",
        headers=headers,
        json={
            **common,
            "kind": "model",
            "model_spec": model_spec,
            "input_cny_per_million": "0.01",
            "output_cny_per_million": "0.01",
            "max_input_tokens": 1000000,
            "max_output_tokens": 32768,
        },
    )
    assert price.status_code == 201, price.text
    if ocr:
        price = await client.post(
            "/api/health/v1/budget/prices",
            headers=headers,
            json={**common, "kind": "ocr", "ocr_endpoint": ocr_endpoint, "fixed_cny_per_page": "0.001"},
        )
        assert price.status_code == 201, price.text

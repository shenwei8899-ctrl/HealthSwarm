"""隔离浏览器保存健康模型配置后，从真实API复核角色选择。"""

import asyncio
import json
import os
from pathlib import Path

import pytest

from test.e2e.test_health_consultation_e2e import isolated_health  # noqa: F401
from test.e2e.test_health_family_profile_ui import write_control
from test.integration.services.test_health_vision_http import health_http  # noqa: F401

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅使用隔离合成槽位"),
    pytest.mark.skipif(not os.getenv("HEALTH_CONFIGURATION_UI_CONTROL_DIR"), reason="需要真实浏览器控制目录"),
]


async def test_browser_preserves_configured_roles_and_explicit_clear(isolated_health):  # noqa: F811
    """浏览器填写并保存配置，API重读确认保留与明确停用的服务。"""
    client, users, _, model = isolated_health
    directory = Path(os.environ["HEALTH_CONFIGURATION_UI_CONTROL_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    assert not any((directory / name).exists() for name in ("context.json", "done.json", "failure.json"))
    headers = users[2]["headers"]
    configured = await client.put(
        "/api/health/v1/configuration",
        headers=headers,
        json={
            "consultation_model": model,
            "meal_plan_model": model,
            "diet_analysis_model": model,
            "quality_review_model": model,
            "policy_version": "synthetic-local-only-v1",
            "cloud_processing_reviewed": True,
        },
    )
    assert configured.status_code == 200
    write_control(directory / "context.json", {"access_token": headers["Authorization"][7:], "model": model})
    async with asyncio.timeout(180):
        while not (directory / "done.json").exists():
            assert not (directory / "failure.json").exists(), "浏览器验证失败，检查本地诊断文件"
            await asyncio.sleep(0.25)
    receipt = json.loads((directory / "done.json").read_text())
    assert receipt == {"preserved": True, "explicit_clear": True, "approval_reset": True}
    current = await client.get("/api/health/v1/configuration", headers=headers)
    assert current.status_code == 200
    actual = current.json()
    assert actual["report"]["model"] == actual["meal"]["model"] == actual["meal_plan"]["model"] == ""
    assert not actual["meal_plan"]["available"]
    for kind in ("consultation", "diet_analysis", "quality_review"):
        assert actual[kind]["model"] == model and actual[kind]["available"]
    write_control(
        directory / "verified.json",
        {
            "final_roles": {
                kind: actual[kind]["model"]
                for kind in ("report", "meal", "consultation", "meal_plan", "diet_analysis", "quality_review")
            },
            "browser_verified": True,
        },
    )

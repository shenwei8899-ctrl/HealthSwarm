"""编辑页读取当前绑定与资源权限，不能用通用选择替代业务配置。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.repositories.health_consultation_repository import HEALTH_AGENT_BACKENDS
from yuxi.services import health_agent_config_service as service
from yuxi.services.health_family_kb_service import INDICATOR_KB_ENVS, KB_ID_ENV


def agent(slug="health-consultation"):
    return SimpleNamespace(slug=slug, backend_id=HEALTH_AGENT_BACKENDS.get(slug, "ChatbotAgent"))


def kb(kb_id, name="当前库名", **kwargs):
    return SimpleNamespace(
        kb_id=kb_id,
        name=name,
        kb_type=kwargs.get("kb_type", "milvus"),
        created_by="owner",
        share_config={"version": 2, "read_scope": None, "manage_scope": None},
    )


@pytest.mark.parametrize("slug,env", [("health-consultation", KB_ID_ENV), *INDICATOR_KB_ENVS.items()])
async def test_uses_runtime_binding_and_fresh_names(monkeypatch, slug, env):
    monkeypatch.setenv(env, "fixed-library")
    rows = AsyncMock(return_value=[kb("fixed-library")])
    monkeypatch.setattr(service.KnowledgeBaseRepository, "get_by_ids", rows)
    user = SimpleNamespace(uid="admin", role="superadmin")
    result = await service.get_managed_knowledge(None, agent(slug), user)
    assert result["items"] == [{"id": "fixed-library", "name": "当前库名", "status": "configured"}]
    rows.assert_awaited_once_with(None, ("fixed-library",))
    rows.return_value[0].name = "已重命名"
    assert (await service.get_managed_knowledge(None, agent(slug), user))["items"][0]["name"] == "已重命名"


async def test_restricted_library_name_and_id_never_disclosed(monkeypatch):
    monkeypatch.setenv(KB_ID_ENV, "private-id")
    monkeypatch.setattr(
        service.KnowledgeBaseRepository, "get_by_ids", AsyncMock(return_value=[kb("private-id", "机密名称")])
    )
    result = await service.get_managed_knowledge(None, agent(), SimpleNamespace(uid="other", role="user"))
    assert result["items"] == [{"status": "restricted", "name": "已绑定知识库（当前账号无权查看详情）"}]
    assert "private-id" not in str(result) and "机密名称" not in str(result)


@pytest.mark.parametrize("rows,status", [([], "unavailable"), ([kb("fixed", kb_type="other")], "unsupported")])
async def test_missing_or_unsupported_library_is_not_reported_as_ready(monkeypatch, rows, status):
    monkeypatch.setenv(KB_ID_ENV, "fixed")
    monkeypatch.setattr(service.KnowledgeBaseRepository, "get_by_ids", AsyncMock(return_value=rows))
    result = await service.get_managed_knowledge(None, agent(), SimpleNamespace(uid="admin", role="superadmin"))
    assert result["status"] == "unavailable"
    assert result["items"][0]["status"] == status


@pytest.mark.parametrize("value", ["", "a,a", "a,", "a,b,c,d,e,f"])
async def test_invalid_config_reports_unconfigured_without_query(monkeypatch, value):
    monkeypatch.setenv(INDICATOR_KB_ENVS["health-blood-glucose"], value)
    rows = AsyncMock()
    monkeypatch.setattr(service.KnowledgeBaseRepository, "get_by_ids", rows)
    result = await service.get_managed_knowledge(None, agent("health-blood-glucose"), None)
    assert result["status"] == "unconfigured"
    rows.assert_not_called()


@pytest.mark.parametrize("slug", ["health-meal-planner", "health-diet-analyst", "health-quality", "health-purchase"])
async def test_structured_roles_report_business_sources(slug):
    result = await service.get_managed_knowledge(None, agent(slug), None)
    assert result["status"] == "business_data"
    assert result["items"] == []


async def test_normal_agent_and_wrong_backend_not_misidentified():
    assert await service.get_managed_knowledge(None, agent("normal"), None) is None
    wrong = agent()
    wrong.backend_id = "ChatbotAgent"
    assert await service.get_managed_knowledge(None, wrong, None) is None

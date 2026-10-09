"""营养师工具、固定 Skills 和引用质量的独立负向 oracle。"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import ValidationError

from yuxi.agents.toolkits.health import get_complete_health_profile, query_reviewed_nutrition_knowledge
from yuxi.services.health_agent_roles import consultation_skill_prompt, consultation_skill_snapshot, health_agent_roles
from yuxi.services.agent_run_manifest_service import build_skill_manifest_entries
from yuxi.services.health_evidence_service import validate_nutrition_answer
from yuxi.services.health_evidence_types import NutritionEvidenceInput
from yuxi.services.health_vision_types import HealthVisionError


def evidence_input():
    """人工定义合成审核凭据，不使用真实临床材料。"""
    return {
        "source_ref": "synthetic-source",
        "source_version": "v1",
        "title": "合成科普证据",
        "content": "只用于测试的合成营养说明",
        "review_ref": "synthetic-review",
        "reviewed_by": "synthetic-clinical-reviewer",
        "reviewed_at": datetime.now(UTC) - timedelta(days=1),
        "valid_until": datetime.now(UTC) + timedelta(days=1),
    }


def test_fixed_skills_and_roles_do_not_publish_unimplemented_agents():
    """角色目录对未完成能力作出可观察说明。"""
    text = consultation_skill_prompt()
    assert "红阳" not in text and "刘潇" not in text
    assert "营养安全档案仍未就绪" in text and "[证据:" in text and "通用科普" in text
    catalog = health_agent_roles()
    assert catalog["full_health_profile_available"] is False
    roles = {role["role"]: role for role in catalog["roles"]}
    assert len(roles) == 7
    assert roles["health-nutritionist"]["entry_agent"] == "health-consultation"
    assert roles["health-nutritionist"]["skills"] == ["family-nutritionist"]
    assert roles["health-profile"]["owner"] == "健康档案服务"
    assert roles["health-meal-planner"]["status"] == "partial"
    assert roles["health-meal-planner"]["entry_agent"] == "health-meal-planner"
    for name in ("health-purchase", "health-glucose"):
        assert roles[name]["status"] == "not_implemented" and "entry_agent" not in roles[name]


def test_fixed_skill_snapshot_records_published_identity_and_exact_content(monkeypatch):
    """来源只由内置发布源码提供，个人同名技能不参与解析；运行记录真实预加载摘要。"""
    import hashlib
    from yuxi.services.skills import shared as skill_service
    from yuxi.services.skills import catalog as skill_catalog

    personal_lookup = AsyncMock(side_effect=AssertionError("个人同名覆盖不能进入健康模型"))
    monkeypatch.setattr(skill_catalog, "list_accessible_skills", personal_lookup)
    snapshot = consultation_skill_snapshot()
    content = snapshot["preloaded_skill_contents"]["family-nutritionist"]
    spec = next(item for item in skill_service.list_builtin_skill_specs() if item["slug"] == "family-nutritionist")
    assert content == (spec["source_dir"] / "SKILL.md").read_text(encoding="utf-8")
    assert snapshot["effective_skills"] == snapshot["preloaded_skills"] == ["family-nutritionist"]
    assert consultation_skill_prompt(snapshot) == content
    assert build_skill_manifest_entries({"skills": ["family-nutritionist"]}, snapshot) == [
        {
            "slug": "family-nutritionist",
            "version": "2026.10.08.6",
            "content_hash": spec["content_hash"],
            "preload_content_hash": hashlib.sha256(content.encode()).hexdigest(),
        }
    ]
    personal_lookup.assert_not_called()


def test_new_tool_schema_rejects_member_scope_and_uncontrolled_knowledge_selection():
    """模型只能传短关键词，不能把个人库或其他成员带入检索。"""
    assert get_complete_health_profile.tool_call_schema.model_json_schema()["properties"] == {}
    assert set(query_reviewed_nutrition_knowledge.tool_call_schema.model_json_schema()["properties"]) == {"query"}
    for field in ("uid", "member_id", "kb_id", "runtime", "file_id"):
        with pytest.raises(ValidationError):
            query_reviewed_nutrition_knowledge.args_schema.model_validate({"query": "营养", field: "forged"})
    for query in ("", " " * 5, "x" * 121):
        with pytest.raises(ValidationError):
            query_reviewed_nutrition_knowledge.args_schema.model_validate({"query": query})


@pytest.mark.asyncio
async def test_profile_adapter_reports_missing_integration_after_authorization(monkeypatch):
    """接口尚未接入不补造无过敏史；授权拒绝不能返回可用数据。"""
    from yuxi.services import health_family_profile_service as service

    expected = {"status": "not_ready", "code": "profile_not_linked", "profile": None}
    guard = AsyncMock(return_value=expected)
    monkeypatch.setattr(service, "family_profile_for_run", guard)
    context = SimpleNamespace(uid="synthetic", thread_id="thread")
    runtime = ToolRuntime(
        state={}, context=context, config={}, stream_writer=lambda _: None, tool_call_id="call", store=None
    )
    output = await get_complete_health_profile.ainvoke({"runtime": runtime})
    assert output == expected
    guard.assert_awaited_once_with(context)
    guard.side_effect = HealthVisionError("forbidden", "合成撤回", 403)
    with pytest.raises(HealthVisionError, match="forbidden"):
        await get_complete_health_profile.ainvoke({"runtime": runtime})


@pytest.mark.parametrize("case", ["future_review", "expired", "naive", "missing_review", "extra_scope"])
def test_evidence_requires_review_provenance_and_valid_utc_dates(case):
    """发布日期不能代替专业审核，也不能额外授权个人方案。"""
    data = evidence_input()
    if case == "future_review":
        data["reviewed_at"] = datetime.now(UTC) + timedelta(days=1)
    elif case == "expired":
        data["valid_until"] = datetime.now(UTC) - timedelta(days=1)
    elif case == "naive":
        data["reviewed_at"] = datetime.now()
    elif case == "missing_review":
        del data["review_ref"]
    else:
        data["scope"] = "personal_meal_plan"
    with pytest.raises(ValidationError):
        NutritionEvidenceInput.model_validate(data)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text", ["没有引用", "[证据:forged]", "[证据:00000000-0000-0000-0000-000000000000] [证据:bad]"]
)
async def test_final_answer_rejects_missing_or_malformed_citation(text):
    """质量校验在访问数据库前拒绝缺引用和格式错误。"""
    messages = [
        HumanMessage(content="合成问题"),
        ToolMessage(
            content='{"citations":[{"citation_id":"test"}]}',
            name="query_reviewed_nutrition_knowledge",
            tool_call_id="call",
        ),
        AIMessage(content=text),
    ]
    with pytest.raises(HealthVisionError, match="citation_invalid"):
        await validate_nutrition_answer(None, text, messages)


@pytest.mark.asyncio
async def test_no_match_and_previous_turn_evidence_do_not_require_invented_citations():
    """新轮无证据时允许说明不足，上一轮结果不能迫使虚构引用。"""
    messages = [
        HumanMessage(content="旧问题"),
        ToolMessage(
            content='{"citations":[{"citation_id":"old"}]}',
            name="query_reviewed_nutrition_knowledge",
            tool_call_id="old",
        ),
        HumanMessage(content="新问题"),
        ToolMessage(content='{"citations":[]}', name="query_reviewed_nutrition_knowledge", tool_call_id="new"),
    ]
    await validate_nutrition_answer(None, "目前证据不足", messages)

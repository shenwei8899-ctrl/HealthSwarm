"""单餐事实、模型选择及分析用途的独立负向验证。"""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.agents.context import BaseContext
from yuxi.agents.toolkits.diet_analyst import list_analysis_meals, analyze_confirmed_meal as analysis_tool
from yuxi.services import health_consultation_service as consultation
from yuxi.services.health_diet_analysis_service import analyze_confirmed_meal, analyst_final_result
from yuxi.services.health_diet_analysis_types import DietAnalysisAnswer, DietAnalysisSelection
from yuxi.services.health_vision_types import NUTRIENTS, HealthVisionError, VisionConfigurationInput
from yuxi.utils.datetime_utils import utc_now_naive


def synthetic_record():
    """已算60克的独立手算快照：120kcal、6g蛋白，钠未知。"""
    item_id = str(uuid4())
    values = {
        "energy_kcal": "120.00",
        "protein_g": "6.00",
        "fat_g": "3.00",
        "carbohydrate_g": "15.00",
        "sodium_mg": None,
    }
    return SimpleNamespace(
        id=str(uuid4()),
        member_id=str(uuid4()),
        created_at=utc_now_naive(),
        snapshot={
            "meal": {
                "meal_type": "lunch",
                "eaten_at": "2026-10-07T12:00:00+08:00",
                "items": [
                    {
                        "item_id": item_id,
                        "name": "合成食物",
                        "grams": "150",
                        "share_ratio": "0.4",
                        "portion_source": "weighed",
                    }
                ],
            },
            "nutrition": {
                "items": [{"item_id": item_id, "eaten_grams": "60", "nutrients": values}],
                "totals": values,
                "units": NUTRIENTS,
                "missing": [{"item_id": item_id, "nutrient": "sodium_mg", "reason": "nutrient_missing"}],
                "complete": False,
                "estimated": False,
                "sources": [{"dataset_version": "synthetic-v1"}],
                "calculation_version": "recipe-portions-v2",
            },
            "object_key": "private-do-not-export",
            "ocr": "private-do-not-export",
        },
    )


def test_snapshot_and_missing_facts_preserved_without_personal_judgement():
    """确认快照只读，不重算或补造未知营养与个人目标。"""
    record = synthetic_record()
    original = deepcopy(record.snapshot)
    result = analyze_confirmed_meal(record, SimpleNamespace(id=str(uuid4()), draft_id=str(uuid4()), draft_version=2))
    assert result["nutrition"]["totals"] == {
        "energy_kcal": "120.00",
        "protein_g": "6.00",
        "fat_g": "3.00",
        "carbohydrate_g": "15.00",
        "sodium_mg": None,
    }
    assert result["items"][0]["eaten_grams"] == "60" and result["items"][0]["share_ratio"] == "0.4"
    assert result["coverage"] == {
        "recorded_items": 1,
        "calculated_items": 1,
        "known_nutrients": 4,
        "supported_nutrients": 5,
        "meaning": "仅描述本次已确认记录的覆盖，不能代表实际吃过的全部食物。",
    }
    assert result["records"] == [{"record_id": record.id, "source_version": 2}]
    assert result["personalized"] is False and result["personal_target"] is None
    assert result["professional_review"] == "not_reviewed"
    assert "private-do-not-export" not in str(result)
    assert record.snapshot == original


def test_unknown_portion_zero_and_excluded_item_are_distinct():
    """未知份量无已算覆盖，真实零值可计数，已排除食物不计入餐次。"""
    record = synthetic_record()
    record.snapshot["meal"]["items"].extend(
        [
            {"item_id": str(uuid4()), "name": "未知", "grams": None, "share_ratio": None, "portion_source": "unknown"},
            {"item_id": str(uuid4()), "name": "已排除", "excluded": True},
        ]
    )
    record.snapshot["nutrition"]["totals"] = {code: None for code in NUTRIENTS}
    result = analyze_confirmed_meal(record, SimpleNamespace(id="c", draft_id="d", draft_version=1))
    assert result["coverage"]["recorded_items"] == 2 and result["coverage"]["calculated_items"] == 1
    assert result["coverage"]["known_nutrients"] == 0
    assert result["items"][1]["eaten_grams"] is None
    record.snapshot["nutrition"]["totals"] = {code: "0.00" for code in NUTRIENTS}
    assert (
        analyze_confirmed_meal(record, SimpleNamespace(id="c", draft_id="d", draft_version=1))["coverage"][
            "known_nutrients"
        ]
        == 5
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"record_id": str(uuid4())},
        {"source_version": 1},
        {"questions": [" "]},
        {"questions": ["哪餐？"], "totals": {}},
        {"record_id": str(uuid4()), "source_version": True},
        {"record_id": str(uuid4()), "source_version": 1, "questions": ["哪餐？"]},
    ],
)
def test_model_answer_rejects_empty_forged_or_ambiguous_choices(body):
    """模型字段和选择结构在JSON边界被拒绝。"""
    with pytest.raises(ValidationError):
        DietAnalysisAnswer.model_validate(body)


def test_tools_hide_identity_and_configuration_requires_approval():
    """只读工具不能接受账号/运行注入，分析模型不得默认启用。"""
    assert set(list_analysis_meals.tool_call_schema.model_json_schema()["properties"]) == set()
    assert set(analysis_tool.tool_call_schema.model_json_schema()["properties"]) == {"record_id", "source_version"}
    with pytest.raises(ValidationError):
        VisionConfigurationInput(diet_analysis_model="test:fixed")
    with pytest.raises(ValidationError):
        DietAnalysisSelection(record_id=uuid4(), source_version=1, member_id="forged")


@pytest.mark.asyncio
async def test_model_free_text_or_nutrition_fails_before_storage():
    """自由文本和额外营养值不会成为最终分析。"""
    for text in ["营养达标", '{"energy_kcal":100}', '{"questions":["哪餐？"],"reviewed":true}']:
        with pytest.raises(HealthVisionError, match="analyst_output_invalid"):
            await analyst_final_result(None, text)


@pytest.mark.asyncio
async def test_analyst_requires_own_purpose_and_fixes_resources(monkeypatch):
    """已有咨询同意不能代替分析同意，输入配置不能增加工具。"""
    monkeypatch.setattr(
        consultation.HealthConsultationRepository,
        "authorize",
        AsyncMock(return_value=SimpleNamespace(member_id="m", conversation_id="c")),
    )
    config = {
        "policy_version": "policy",
        "diet_analysis": {"available": True, "model": "test:fixed", "processor": "fingerprint"},
    }
    monkeypatch.setattr(consultation.health_vision_service, "configuration", AsyncMock(return_value=config))
    consent = AsyncMock(side_effect=HealthVisionError("consent_required", "未同意分析", 403))
    monkeypatch.setattr(consultation.HealthVisionRepository, "require_consent", consent)
    with pytest.raises(HealthVisionError, match="consent_required"):
        await consultation.require_consultation(
            SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(agent_id="health-diet-analyst"))),
            "actor",
            "thread",
        )
    assert consent.await_args.args[2] == "diet_analysis"
    approved = {"model": "test:fixed", "processor": "fingerprint", "policy_version": "policy"}
    monkeypatch.setattr(consultation, "require_consultation", AsyncMock(return_value=(
        SimpleNamespace(conversation_id=1), approved
    )))
    context = BaseContext(
        uid="actor", thread_id="thread", tools=["remember_member_fact"], skills=["untrusted"], mcps=["other"]
    )
    prepared = await consultation.prepare_consultation_context(
        context, SimpleNamespace(get=AsyncMock(return_value=None)),
        SimpleNamespace(agent_slug="health-diet-analyst", input_payload={"health_processing": approved})
    )
    assert prepared.tools == ["list_analysis_meals", "analyze_confirmed_meal", "analyze_confirmed_period"]
    assert prepared.skills == prepared.preload_skills == ["family-diet-analyst"]
    assert prepared.mcps == prepared.knowledges == []
    assert prepared.system_prompt == consultation.ANALYST_PROMPT

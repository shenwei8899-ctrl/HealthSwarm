"""采购不完整不影响菜单，费用只公开可靠小计。"""

from copy import deepcopy
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from yuxi.services import exclusive_reference_plan as reference
from yuxi.services.exclusive_plan_generation import TIERS
from yuxi.services.exclusive_plan_service import PREVIEW_POLICY, project_group, project_preview
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_meal_plan_types import ReferenceSelection
from yuxi.services.reference_recipe_index import prepare_reference_documents
from yuxi.utils.datetime_utils import utc_now_naive


def sku(**changes):
    """合成明确净重和映射的单食材包装。"""
    return {
        "sku_id": "rice",
        "product_id": "rice",
        "product_name": "大米",
        "sku_name": "500g",
        "price_cent": 500,
        "sale_status": "available",
        "available_quantity": 100,
        "data_completeness": "complete",
        "allergen_codes": [],
        "ingredients": [
            {
                "ingredient_id": "rice",
                "ingredient_code": "大米",
                "ingredient_name": "大米",
                "net_unit": "g",
                "net_value": 500,
                "review_status": "approved",
            }
        ],
        **changes,
    }


def meals(*ingredients):
    """保留原谱逐项食材。"""
    return [{"meal_type": "lunch", "dishes": [{"file_id": "recipe", "name": "蔬菜饭", "ingredients": ingredients}]}]


@pytest.mark.parametrize(
    "changes",
    [
        {"price_cent": None},
        {"ingredients": []},
        {"available_quantity": None},
        {"available_quantity": 0},
        {"sale_status": "unavailable"},
        {
            "ingredients": [
                {"ingredient_id": "rice", "ingredient_code": "大米", "net_unit": "g", "review_status": "approved"}
            ]
        },
    ],
)
def test_missing_procurement_facts_are_gaps_not_menu_errors(changes):
    result = reference.reference_procurement(meals("大米100克"), {"items": [sku(**changes)]})
    assert result["ingredients"][0]["ingredient"] == "大米100克"
    assert result["pricing"]["matched_subtotal_cent"] is None
    assert len(result["purchase_gaps"]) == 1
    assert result["purchase_gaps"][0]["price_cent"] is None


def test_partial_subtotal_does_not_price_unknown_as_zero_or_complete_budget():
    result = reference.reference_procurement(meals("大米100克", "菠菜适量"), {"items": [sku()]})
    assert result["pricing"]["matched_subtotal_cent"] == 500
    assert [item["ingredient"] for item in result["purchase_gaps"]] == ["菠菜适量"]
    assert result["pricing"]["complete_estimate"] is False
    assert (
        reference.reference_procurement(meals("大米100克"), {"items": [sku(price_cent=0)]})["pricing"][
            "matched_subtotal_cent"
        ]
        == 0
    )
    assert (
        reference.reference_procurement(meals("大米1杯"), {"items": [sku()]})["pricing"]["matched_subtotal_cent"]
        is None
    )


def test_repeated_ingredient_requirements_are_aggregated_before_packaging():
    result = reference.reference_procurement(meals("大米300克", "大米300克"), {"items": [sku()]})
    assert result["matched_items"][0]["quantity"] == 2
    assert result["pricing"]["matched_subtotal_cent"] == 1000


@pytest.mark.parametrize(
    "line", ["大米100-200克", "大米1/2克", "大米½克", "大米适量", "大米100克或200克", "大米1,500克", "大米1，500克"]
)
def test_uncertain_units_do_not_invent_weights(line):
    assert reference.explicit_grams(line) is None


@pytest.mark.asyncio
async def test_unavailable_catalog_is_visible_and_unrelated_errors_propagate(monkeypatch):
    monkeypatch.setattr(
        reference, "current_catalog", AsyncMock(side_effect=HealthVisionError("commerce_not_configured", "未接入", 503))
    )
    catalog = await reference.optional_exclusive_catalog()
    result = reference.reference_procurement(meals("大米100克"), catalog)
    assert result["catalog_status"] == "unavailable"
    assert result["purchase_gaps"][0]["reason"] == "catalog_unavailable"
    monkeypatch.setattr(
        reference, "current_catalog", AsyncMock(side_effect=HealthVisionError("not_authorized", "拒绝", 403))
    )
    with pytest.raises(HealthVisionError, match="not_authorized"):
        await reference.optional_exclusive_catalog()


def reference_context():
    """与知识库分片结构一致的独立合成来源，不建立审核配方或采购映射。"""
    rows = []
    for number in range(40):
        content = f"# 合成蔬菜饭{number}\n## 食材\n- 大米100克\n- 菠菜适量\n## 做法\n1. 加热至熟。"
        rows.append((f"recipe-{number}", "kb", f"烹饪菜谱{number}.md", f"hash-{number}", f"chunk-{number}", content))
    return {
        "mode": "reference",
        "selection": ReferenceSelection(family_id=uuid4(), plan_date=date(2099, 1, 1), participant_ids=[uuid4()]),
        "current": {"members": [{"dietary": {}, "allergens": [], "avoidances": [], "intolerances": []}]},
        "documents": prepare_reference_documents(rows),
        "verified_documents": {},
    }


def test_three_tiers_21_days_without_products_and_without_price_order():
    context, tiers = reference_context(), {}
    for tier in TIERS:
        entries = []
        for number in range(21):
            context["selection"].plan_date = date(2099, 1, 1) + timedelta(days=number)
            entries.append(
                reference.generate_reference_day(
                    context, tier, entries, "stable", {"items": [], "status": "unavailable"}
                )
            )
        tiers[tier] = entries
    row = SimpleNamespace(
        id="group", status="ready", policy=PREVIEW_POLICY, progress={"tiers": tiers}, updated_at=utc_now_naive()
    )
    sources = {"members": {"member": {"name": "合成成员"}}}
    summary = project_group(row, sources)
    assert summary["total_days"] == summary["completed_days"] == 63
    assert all(item["pricing"]["matched_subtotal_cent"] is None for item in summary["plans"])
    detail = project_preview(row, "economy", sources)
    assert len(detail["days"]) == 21
    assert detail["days"][20]["plan_date"] == "2099-01-21"
    assert detail["days"][20]["meals"][0]["ingredients"] == ["大米100克", "菠菜适量"]
    assert detail["professional_status"] == "not_reviewed"
    for entries in tiers.values():
        assert reference.summarize_reference_prices(entries)["complete_estimate"] is False


@pytest.mark.asyncio
async def test_saved_menu_checks_actual_source_and_restrictions_without_procurement(monkeypatch):
    context = reference_context()
    entry = reference.generate_reference_day(context, "standard", [], "stable", {"items": []})
    docs = {document["source"]["file_id"]: document for document in context["documents"]}

    async def document(session, file_id, chunk_id):
        doc = docs[file_id]
        return {**doc["source"], "chunks_hash": doc["chunks_hash"], "content": doc["content"]}

    monkeypatch.setattr(reference, "recipe_document", document)
    await reference.validate_reference_days(None, context, [entry])
    assert entry["meals"][0]["dishes"][0]["nutrition_status"] == "not_calculated"
    changed = deepcopy(entry)
    changed["meals"][0]["dishes"][0]["source"]["file_hash"] = "changed"
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await reference.validate_reference_days(None, context, [changed])
    changed = deepcopy(entry)
    changed["meals"][0]["dishes"][0]["ingredients"] = ["编造食材100克"]
    with pytest.raises(HealthVisionError, match="reference_quote_invalid"):
        await reference.validate_reference_days(None, context, [changed])
    context["current"]["members"][0]["allergens"] = ["菠菜"]
    with pytest.raises(HealthVisionError, match="reference_restriction_conflict"):
        await reference.validate_reference_days(None, context, [entry])


@pytest.mark.asyncio
async def test_account_memory_limits_generation_and_saved_menu_even_with_empty_profile(monkeypatch):
    """档案没有限制也必须核对账号明确忌口，不能只交给模型提示。"""
    context = reference_context()
    beef = prepare_reference_documents(
        [
            (
                "beef",
                "kb",
                "牛肉饭.md",
                "beef-hash",
                "beef-chunk",
                "# 牛肉饭\n## 食材\n- 大米100克\n- 牛肉100克\n## 做法\n1. 加热至熟。",
            )
        ]
    )
    context["documents"].extend(beef)
    context["current"]["memory_restrictions"] = ["牛肉"]
    entry = reference.generate_reference_day(context, "standard", [], "stable", {"items": []})
    assert all(dish["file_id"] != "beef" for meal in entry["meals"] for dish in meal["dishes"])
    docs = {document["source"]["file_id"]: document for document in context["documents"]}

    async def document(session, file_id, chunk_id):
        """同一原谱证明失败来自记忆限制。"""
        doc = docs[file_id]
        return {**doc["source"], "chunks_hash": doc["chunks_hash"], "content": doc["content"]}

    monkeypatch.setattr(reference, "recipe_document", document)
    for doc in context["documents"]:
        doc["content"] += "\n牛肉100克\n"
    with pytest.raises(HealthVisionError, match="reference_restriction_conflict"):
        await reference.validate_reference_days(None, context, [entry])


def test_equal_and_reversed_partial_totals_are_not_group_failures():
    tiers = {}
    for tier, cents in zip(TIERS, (500, 500, 100)):
        entries = []
        for number in range(21):
            procurement = reference.reference_procurement(meals("大米100克", "菠菜适量"), {"items": [sku()]})
            procurement["pricing"]["matched_subtotal_cent"] = cents
            entries.append(
                {
                    "day": {"day_no": number + 1, "plan_date": (date(2099, 1, 1) + timedelta(days=number)).isoformat()},
                    "meals": [],
                    "procurement": procurement,
                }
            )
        tiers[tier] = entries
    row = SimpleNamespace(
        id="group", status="ready", policy=PREVIEW_POLICY, progress={"tiers": tiers}, updated_at=utc_now_naive()
    )
    sources = {"members": {"member": {"name": "合成成员"}}}
    summary = project_group(row, sources)
    assert summary["status"] == "ready"
    assert [plan["pricing"]["matched_subtotal_cent"] for plan in summary["plans"]] == [10500, 10500, 2100]
    for tier in TIERS:
        detail = project_preview(row, tier, sources)
        assert len(detail["days"]) == 21
        assert detail["pricing"]["unpriced_ingredients"]
        assert detail["pricing"]["complete_estimate"] is False

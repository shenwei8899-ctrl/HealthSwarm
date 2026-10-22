"""每日安排的库存负控、真实份量汇总和单餐不变性。"""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from test.unit.services.test_health_initial_meal_generation import initial_fixture, generated
from yuxi.services.daily_commerce_service import match_requirements, packages_in_stock
from yuxi.services.daily_arrangement_projection import ingredient_requirements, meal_views
from yuxi.services.miniapp_profile_types import MiniappMemberInput
from yuxi.services.health_meal_plan_types import PlannerAnswer
from yuxi.services.miniapp_planning_source import code_submitted_profile, bind_submitted_profile
from yuxi.services.health_quality_types import QualityRules
from test.unit.services.test_health_quality import rules_payload


def sku(*, stock=2, grams=200, code="food-A", sid="SKU-1"):
    """仅供测试的可售库存，不作为生产菜谱来源。"""
    return {
        "sku_id": sid,
        "data_completeness": "complete",
        "sale_status": "available",
        "available_quantity": stock,
        "price_cent": 100,
        "ingredients": [
            {
                "ingredient_id": code,
                "ingredient_code": code,
                "net_unit": "g",
                "net_value": str(grams),
                "convert_ratio": "1",
                "loss_rate": "0",
                "review_status": "approved",
            }
        ],
    }


def test_no_stock_never_matches_a_purchase_menu():
    """数量不足或未映射不能因商品可见就发布。"""
    needs = [{"ingredient_id": "food-A", "required_value": "401"}]
    assert match_requirements(needs, {"items": [sku()]}) is None
    needs[0]["required_value"] = "400"
    result = match_requirements(needs, {"items": [sku()]})
    assert result[0]["quantity"] == 2
    assert match_requirements(needs, {"items": [sku(stock=0)]}) is None


def test_shared_sku_cannot_spend_stock_twice():
    """两种食材共享一包时也不能各自假定完整库存。"""
    product = sku(stock=1)
    product["ingredients"].append({**product["ingredients"][0], "ingredient_code": "food-B"})
    needs = [{"ingredient_id": code, "required_value": "200"} for code in ("food-A", "food-B")]
    assert match_requirements(needs, {"items": [product]}) is None


def test_actual_separate_packages_must_fit_combined_stock():
    """总克数够两包，但逐餐各需一包时不能推荐只有两包的库存。"""
    catalog = {"items": [sku(stock=2, grams=500)]}
    assert match_requirements([{"ingredient_id": "food-A", "required_value": "900"}], catalog)
    packages = [
        {"items": [{"sku_id": "SKU-1", "quantity": 1}], "ingredient_requirements": [{"ingredient_id": "food-A"}]}
        for _ in range(3)
    ]
    assert not packages_in_stock(packages, catalog)
    catalog["items"][0]["available_quantity"] = 3
    assert packages_in_stock(packages, catalog)
    catalog["items"][0]["sale_status"] = "unavailable"
    assert not packages_in_stock(packages, catalog)
    assert not packages_in_stock([{"items": []}], catalog)


def test_empty_ingredient_mapping_is_not_purchasable():
    """缺失食材映射不能被当作无需购买。"""
    assert match_requirements([], {"items": [sku()]}) is None


def test_stock_matching_tries_available_alternatives_instead_of_greedy_failure():
    """共享便宜SKU留给没有替代品的食材。"""
    shared = sku(stock=1)
    shared["ingredients"].append({**shared["ingredients"][0], "ingredient_code": "food-B"})
    alternate = sku(stock=1, sid="SKU-2")
    alternate["price_cent"] = 200
    needs = [{"ingredient_id": code, "required_value": "200"} for code in ("food-A", "food-B")]
    assert {item["sku_id"] for item in match_requirements(needs, {"items": [shared, alternate]})} == {"SKU-1", "SKU-2"}


@pytest.mark.parametrize("ranges", [{"invalid": "adult"}, {"0:80": "adult", "70:130": "adult"}])
def test_approved_profile_mapping_rejects_ambiguous_age_ranges(ranges):
    """错误编码规则在发布边界失败，不能变成运行期500。"""
    with pytest.raises(ValidationError):
        QualityRules.model_validate({**rules_payload(), "miniapp_profile_codes": {"population_age_ranges": ranges}})


def test_inventory_rejection_participates_in_the_entire_menu_search():
    """已通过营养检查但没有库存的组合仍不能成为结果。"""
    values = initial_fixture()
    assert generated(values)["status"] == "ready"
    assert generated(values, purchase_validator=lambda snapshot: False)["status"] == "not_ready"


def test_only_target_meal_is_replanned():
    """固定另外两餐的配方和份量，最终仍复算全天规则。"""
    values = initial_fixture(family=True)
    before = generated(values)
    assert before["status"] == "ready"
    fixed = {
        meal["meal_type"]: deepcopy(meal) for meal in before["plan_spec"]["meals"] if meal["meal_type"] != "dinner"
    }
    after = generated(values, fixed_meals=fixed)
    assert after["status"] == "ready"
    for meal in after["plan_spec"]["meals"]:
        if meal["meal_type"] != "dinner":
            assert meal == fixed[meal["meal_type"]]


def test_family_ingredients_follow_each_person_and_remain_unknown_without_a_map():
    """共餐按真实逐人需求汇总，不能套用平均人数。"""
    values = initial_fixture(family=True)
    generated_plan = generated(values)
    mappings = {
        rid: SimpleNamespace(
            ingredient_codes={recipe.ingredients[0]["food"]["id"]: "standard-food"}, steps=["测试步骤"]
        )
        for rid, recipe in values[2].items()
    }
    requirements = ingredient_requirements(generated_plan["plan_snapshot"], mappings)
    assert Decimal(requirements[0]["required_value"]) == Decimal("360")
    assert ingredient_requirements(generated_plan["plan_snapshot"], {}) == []
    members = {mid: {"id": mid, "name": "合成成员"} for mid in generated_plan["plan_snapshot"]["members"]}
    views = meal_views(generated_plan["plan_snapshot"], mappings, members, next(iter(members)), values[2])
    breakfast = next(meal for meal in views if meal["type"] == "breakfast")
    assert sum(
        Decimal(item["planned_grams"]) for dish in breakfast["dishes"] for item in dish["ingredients"]
    ) == Decimal("160")


def test_model_explanation_cannot_supply_nutrition_or_approval_fields():
    """说明文字只附属真实回执，不能成为营养真值。"""
    answer = PlannerAnswer(preview_id="00000000-0000-4000-8000-000000000001", explanation="合成菜单说明")
    assert answer.explanation == "合成菜单说明"
    with pytest.raises(ValidationError):
        PlannerAnswer(preview_id=answer.preview_id, explanation="说明", nutrition={"protein": 100})


def test_onboarding_does_not_accept_identity_or_authorization_fields():
    """建档不得通过提交昵称/客户端ID认领其他账号。"""
    with pytest.raises(ValidationError):
        MiniappMemberInput(client_ref="1", name="合成成员", relation="家人", dietary={}, subject_uid="someone-else")


def test_submitted_profile_uses_only_published_coding_and_preserves_unknowns():
    """自述投影不创造临床确认或默认无过敏。"""
    rule = QualityRules.model_validate(rules_payload())
    code = {"population_age_ranges": {"0:130": rule.allowed_population_codes[0]}, "sex": {"female": "female"}}
    profile = {
        "birth_date": "1990-01-01",
        "sex": "female",
        "height_cm": 165,
        "dietary_details": {
            "statedWeightKg": 55,
            "healthStatus": "none",
            "allergyStatus": "unknown",
            "intoleranceStatus": "none",
            "avoidanceStatus": "none",
            "doctorStatus": "none",
        },
    }
    result = code_submitted_profile(profile, rule, code)
    assert result["allergies"] == {"state": "unknown", "codes": []}
    assert result["weight_kg"] == "55"
    profile["dietary_details"]["doctorStatus"] = "set"
    profile["dietary_details"]["clinicianGuidance"] = "无批准编码的合成医嘱"
    with pytest.raises(KeyError):
        code_submitted_profile(profile, rule, code)


@pytest.mark.asyncio
async def test_onboarding_never_downgrades_existing_professional_source(monkeypatch):
    """再次建档不能把原专业投影切成自述，从而丢失已知临床资料。"""
    from yuxi.services.health_vision_service import health_vision_service

    async def configured(session):
        return {"meal_plan": {"available": True, "processor": "test-processor"}, "policy_version": "test-policy"}

    monkeypatch.setattr(health_vision_service, "configuration", configured)
    link = SimpleNamespace(actor_uid="actor", member_id="health-member", source_kind="self_confirmed")
    record = SimpleNamespace()

    class Session:
        """已有来源与用途记录，不建立任何新身份。"""

        async def scalar(self, query):
            return link

        async def get(self, model, key):
            return record

    await bind_submitted_profile(
        Session(),
        "actor",
        SimpleNamespace(id="family"),
        [SimpleNamespace(id="member", subject_uid="actor")],
        {"processor": "test-processor", "policy_version": "test-policy"},
    )
    assert link.source_kind == "self_confirmed"


@pytest.mark.parametrize("change", ["partial", "pending", "extra", "allergen", "nan"])
def test_daily_matching_and_saved_purchase_both_reject_unsafe_composition(change):
    """负控同时覆盖首轮匹配和已保存采购的目录复验。"""
    product = sku()
    needs = [{"ingredient_id": "food-A", "required_value": "100"}]
    if change == "partial":
        product["data_completeness"] = "partial"
    elif change == "pending":
        product["ingredients"].append({**product["ingredients"][0], "review_status": "pending"})
    elif change == "extra":
        product["ingredients"].append({**product["ingredients"][0], "ingredient_code": "peanut"})
    elif change == "allergen":
        product["allergen_codes"] = ["peanut"]
    else:
        product["ingredients"][0]["net_value"] = "NaN"
    catalog = {"items": [product]}
    assert match_requirements(needs, catalog) is None
    assert not packages_in_stock(
        [{"items": [{"sku_id": "SKU-1", "quantity": 1}], "ingredient_requirements": needs}], catalog
    )


def test_single_meal_retry_preserves_other_meal_payloads():
    """库存重试丢弃目标餐及依赖汇总，另两餐保留原始发布键和来源。"""
    from yuxi.services.daily_arrangement_service import retained_purchase_payloads

    payloads = {meal: {"agent_task_id": meal} for meal in ["breakfast", "lunch", "dinner", "daily:breakfast,lunch"]}
    assert retained_purchase_payloads({"purchase_payloads": payloads}, "lunch") == {
        meal: payloads[meal] for meal in ["breakfast", "dinner"]
    }
    assert retained_purchase_payloads({"purchase_payloads": payloads}, None) == {}


@pytest.mark.asyncio
async def test_pending_purchase_keeps_saved_product_when_available_catalog_omits_it(monkeypatch):
    """售罄原商品仍能展示并确认原请求，不能被替换为另一个可售商品。"""
    from unittest.mock import AsyncMock
    from yuxi.services import daily_commerce_service as commerce

    product = {**sku(), "product_name": "合成原商品"}
    fetch = AsyncMock(side_effect=AssertionError("已有快照不必读取单品"))
    monkeypatch.setattr(commerce, "commerce_request", fetch)
    items = await commerce.refresh_purchase_items(
        [{"sku_id": "SKU-1", "quantity": 2}],
        {"items": [sku(sid="alternative")]},
        [{"sku_id": "SKU-1", "sku": product}],
    )
    assert items[0]["sku_id"] == items[0]["sku"]["sku_id"] == "SKU-1"
    assert items[0]["sku"]["product_name"] == "合成原商品"
    assert items[0]["sku"]["price_cent"] == 100
    assert items[0]["sku"]["available_quantity"] == 0
    assert items[0]["sku"]["sale_status"] == "unavailable"
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_substitute_without_snapshot_reads_actual_product(monkeypatch):
    """首次改配后超时的商品从单品接口恢复名称价格，不借用原商品快照。"""
    from unittest.mock import AsyncMock
    from yuxi.services import daily_commerce_service as commerce

    product = {**sku(sid="new sku"), "product_name": "合成替代商品", "price_cent": 234}
    fetch = AsyncMock(return_value=product)
    monkeypatch.setattr(commerce, "commerce_request", fetch)
    items = await commerce.refresh_purchase_items(
        [{"sku_id": "new sku", "quantity": 1}], {"items": []}, [{"sku_id": "SKU-1", "sku": sku()}]
    )
    fetch.assert_awaited_once_with("GET", "/api/v1/integration/ai/catalog/skus/new%20sku")
    assert items[0]["sku"]["sku_id"] == "new sku"
    assert items[0]["sku"]["product_name"] == "合成替代商品"
    assert items[0]["sku"]["price_cent"] == 234
    assert items[0]["sku"]["available_quantity"] == 0

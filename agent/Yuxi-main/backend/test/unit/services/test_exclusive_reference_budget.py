"""参考档位是软偏好；总金额先合并整期包装，再除以天数和人数。"""

from dataclasses import replace

import pytest

from yuxi.services import exclusive_reference_plan as reference
from yuxi.services import exclusive_plan_purchase as purchase
from test.unit.services.test_exclusive_plan_prices import sku, meals, reference_context


def entries(count=21, line="大米100克"):
    """每天的包装小计故意与整期采购不同。"""
    catalog = {"items": [sku()], "version": "synthetic"}
    return [
        {
            "day": {"day_no": n},
            "meals": meals(line),
            "procurement": reference.reference_procurement(meals(line), catalog),
        }
        for n in range(1, count + 1)
    ]


def test_summary_rounds_packages_once_then_divides_total_by_days_and_diners():
    result = reference.summarize_reference_prices(entries(), catalog={"items": [sku()]}, member_count=3)
    assert result["matched_subtotal_cent"] == result["total_cent"] == 2500
    assert result["day_count"] == 21
    assert result["member_count"] == 3
    assert result["per_person_day_cent"] == 40
    assert result["complete_estimate"] is False


def test_plan_summary_and_purchase_use_the_same_merged_total():
    days = entries()
    catalog = {"items": [sku()]}
    plan = {
        "group_id": "synthetic",
        "tier_code": "economy",
        "members": [{}, {}, {}],
        "days": [
            {
                "day_no": entry["day"]["day_no"],
                "meals": [
                    {
                        "meal_type": meal["meal_type"],
                        "recipe_name": dish["name"],
                        "source": {"file_id": dish["file_id"]},
                        "ingredients": dish["ingredients"],
                    }
                    for meal in entry["meals"]
                    for dish in meal["dishes"]
                ],
            }
            for entry in days
        ],
    }
    summary = reference.summarize_reference_prices(days, catalog=catalog, member_count=3)
    receipt = purchase.assemble_purchase(plan, catalog, [])
    assert receipt["pricing"]["total_cent"] == summary["total_cent"] == 2500
    assert receipt["pricing"]["per_person_day_cent"] == 40
    assert sum(item["quantity"] * item["sku"]["price_cent"] for item in receipt["items"]) == 2500


@pytest.mark.parametrize("line", ["大米适量", "大米100克、菠菜适量"])
def test_partial_amount_cannot_be_published_as_the_whole_plan_total(line):
    result = reference.summarize_reference_prices(entries(line=line), catalog={"items": [sku()]}, member_count=3)
    assert result["total_cent"] is None
    assert result["per_person_day_cent"] is None
    assert result["unpriced_ingredients"]


def test_real_zero_price_is_preserved_and_zero_diners_do_not_divide():
    result = reference.summarize_reference_prices(entries(), catalog={"items": [sku(price_cent=0)]}, member_count=3)
    assert result["total_cent"] == result["per_person_day_cent"] == 0
    result = reference.summarize_reference_prices(entries(), catalog={"items": [sku()]}, member_count=0)
    assert result["total_cent"] == 2500
    assert result["per_person_day_cent"] is None


@pytest.mark.parametrize("include_in_range", [True, False])
def test_budget_prefers_reference_range_but_accepts_slightly_higher_total(monkeypatch, include_in_range):
    context = reference_context()
    menus = []
    for index, grams in enumerate([1000, 350, *([200] if include_in_range else [])]):
        documents = context["documents"][index * 6 : (index + 1) * 6]
        for document in documents:
            document["parsed"] = replace(document["parsed"], ingredients=(f"大米{grams}克",))
        menus.append(
            [
                {
                    "meal_type": meal,
                    "dishes": [{"file_id": document["source"]["file_id"]} for document in documents[n * 2 : n * 2 + 2]],
                }
                for n, meal in enumerate(["breakfast", "lunch", "dinner"])
            ]
        )
    monkeypatch.setattr(reference, "reference_menu_options", lambda *args: {"menus": menus})
    product = sku(price_cent=100)
    product["ingredients"][0]["net_value"] = 100
    result = reference.generate_reference_day(context, "economy", [], "synthetic", {"items": [product]})
    # 12元在区间内；只有21/60元可选时仍采用21元，不失败或升级档位。
    assert result["procurement"]["pricing"]["matched_subtotal_cent"] == (1200 if include_in_range else 2100)


def test_summary_projects_reference_price_and_actual_plan_diners():
    from types import SimpleNamespace
    from yuxi.services.exclusive_plan_service import project_group, PREVIEW_POLICY
    from yuxi.utils.datetime_utils import utc_now_naive

    row = SimpleNamespace(
        id="synthetic",
        status="ready",
        policy=PREVIEW_POLICY,
        progress={
            "tiers": {tier: entries() for tier in ("economy", "standard", "premium")},
            "catalog_snapshot": {"items": [sku()]},
        },
        updated_at=utc_now_naive(),
    )
    result = project_group(row, {"members": {str(n): {"name": "合成成员"} for n in range(3)}})
    for plan, bounds in zip(result["plans"], [(1000, 2000), (3000, 5000), (5000, 10000)], strict=True):
        assert plan["reference_price"] == {"min_cent": bounds[0], "max_cent": bounds[1], "unit": "person_day"}
        assert plan["pricing"]["per_person_day_cent"] == 40

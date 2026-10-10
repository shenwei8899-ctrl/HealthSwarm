"""采购独立手算、未知库存及固定输出协议边界。"""

import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.agents.toolkits.purchase import get_purchase_requirements, preview_purchase_requirements
from yuxi.services.health_purchase_types import PurchaseAnswer, PurchaseSelection
from yuxi.services.health_purchase_service import (
    calculate_purchase_requirements,
    purchase_answer_in_session,
    validate_purchase_publication,
)
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import HealthPurchasePreview

FOOD = "00000000-0000-4000-8000-000000000001"
ADOPTION = "00000000-0000-4000-8000-000000000002"


def selection(**values):
    """版本与库存由独立用户输入给定。"""
    return PurchaseSelection(adoption_id=ADOPTION, adoption_version=1, plan_version=1, **values)


def meal(grams):
    """字面配方已由业务Owner算好，不从被测输出构造期望。"""
    return {
        "meal_type": "lunch",
        "dishes": [
            {
                "recipe_version_id": "synthetic-recipe",
                "ingredients": [{"food_id": FOOD, "name": "合成米", "role": "food", "planned_grams": grams}],
            }
        ],
        "nutrition": {
            "sources": [
                {
                    "recipe_version_id": "synthetic-recipe",
                    "ingredients": [
                        {"food": {"id": FOOD, "name": "合成米", "cooking_state": "raw"}, "grams": "100", "role": "food"}
                    ],
                }
            ]
        },
    }


def test_family_member_allocations_merge_without_counting_public_dishes():
    snapshot = {
        "scope": "family_recipe_draft",
        "meals": [meal("999")],
        "members": {"first": {"meals": [meal("120.25"), meal("30")]}, "second": {"meals": [meal("49.75")]}},
    }
    chosen = selection(
        inventory_confirmed=True, inventory=[{"food_id": FOOD, "cooking_state": "raw", "edible_grams": "35"}]
    )
    result = calculate_purchase_requirements(snapshot, chosen)
    assert result["status"] == "requirements_ready"
    assert result["items"] == [
        {
            "food_id": FOOD,
            "name": "合成米",
            "cooking_state": "raw",
            "unit": "edible_g",
            "required_grams": "200.000000",
            "inventory_grams": "35.000000",
            "net_required_grams": "165.000000",
        }
    ]
    assert result["purchase_available"] is False and result["order_available"] is False
    assert result["sku_candidates"] == [] and "purchase_weight_conversion" in result["missing_dependencies"]


def test_unconfirmed_empty_inventory_is_unknown_not_zero():
    result = calculate_purchase_requirements({"meals": [meal("100")]}, selection())
    assert result["status"] == "needs_input" and result["missing_fields"] == ["inventory_confirmation"]
    assert result["items"][0]["inventory_grams"] is None and result["items"][0]["net_required_grams"] is None


def test_confirmed_empty_inventory_and_oversupply_have_exact_zero_semantics():
    result = calculate_purchase_requirements({"meals": [meal("50")]}, selection(inventory_confirmed=True))
    assert (
        result["items"][0]["inventory_grams"] == "0.000000" and result["items"][0]["net_required_grams"] == "50.000000"
    )
    result = calculate_purchase_requirements(
        {"meals": [meal("50")]},
        selection(
            inventory_confirmed=True, inventory=[{"food_id": FOOD, "cooking_state": "raw", "edible_grams": "60"}]
        ),
    )
    assert result["items"][0]["net_required_grams"] == "0.000000"


def test_missing_quantity_keeps_entire_food_total_unknown():
    result = calculate_purchase_requirements({"meals": [meal("20"), meal(None)]}, selection(inventory_confirmed=True))
    assert result["items"][0]["required_grams"] is None and result["items"][0]["net_required_grams"] is None
    assert result["missing_fields"] == [f"ingredient_quantity:{FOOD}"]


@pytest.mark.parametrize("food,state", [(FOOD, "cooked"), (str(uuid4()), "raw")])
def test_wrong_food_or_cooking_state_cannot_reduce_requirements(food, state):
    with pytest.raises(HealthVisionError, match="inventory_mapping_mismatch"):
        calculate_purchase_requirements(
            {"meals": [meal("50")]},
            selection(
                inventory_confirmed=True, inventory=[{"food_id": food, "cooking_state": state, "edible_grams": "20"}]
            ),
        )


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "1000001", "0.0000001"])
def test_inventory_rejects_nonfinite_negative_or_unbounded_values(value):
    with pytest.raises(ValidationError):
        selection(
            inventory_confirmed=True, inventory=[{"food_id": FOOD, "cooking_state": "raw", "edible_grams": value}]
        )


def test_inventory_requires_human_confirmation_and_unique_mapping():
    row = {"food_id": FOOD, "cooking_state": "raw", "edible_grams": "1"}
    with pytest.raises(ValidationError):
        selection(inventory=[row])
    with pytest.raises(ValidationError):
        selection(inventory_confirmed=True, inventory=[row, row])
    for values in ({"adoption_version": True}, {"inventory_confirmed": "true"}):
        with pytest.raises(ValidationError):
            PurchaseSelection.model_validate({**selection().model_dump(mode="json"), **values})


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"preview_id": str(uuid4()), "questions": ["库存？"]},
        {"questions": [" "]},
        {"questions": ["a" * 201]},
        {"questions": ["q"], "sku": "fake"},
        {"preview_id": str(uuid4()), "nutrition": {"energy": 1}},
    ],
)
def test_model_final_answer_rejects_ambiguous_or_fabricated_fields(payload):
    with pytest.raises(ValidationError):
        PurchaseAnswer.model_validate(payload)


def test_tool_schema_does_not_allow_identity_or_inventory_overrides():
    for tool in (get_purchase_requirements, preview_purchase_requirements):
        schema = tool.tool_call_schema.model_json_schema()
        assert schema["properties"] == {}
        with pytest.raises(ValidationError) as exc:
            tool.args_schema.model_validate({"member_id": FOOD})
        assert any(
            error["loc"] == ("member_id",) and error["type"] == "extra_forbidden" for error in exc.value.errors()
        )


@pytest.mark.asyncio
async def test_receipt_owner_run_and_complete_snapshot_are_required():
    preview_id = str(uuid4())
    binding = SimpleNamespace(
        actor_uid="owner",
        member_id="member",
        conversation_id=4,
        purchase_selection={"x": 1},
        _purchase_current={"status": "requirements_ready", "items": [], "source_hash": "internal"},
    )
    run = SimpleNamespace(uid="owner", id="run")
    receipt = HealthPurchasePreview(
        id=preview_id,
        actor_uid="owner",
        run_id="run",
        conversation_id=4,
        snapshot={"status": "requirements_ready", "items": []},
    )

    class Session:
        async def get(self, model, key):
            return receipt

    session = Session()
    answer = PurchaseAnswer(preview_id=preview_id)
    assert (await purchase_answer_in_session(session, run, binding, answer))["run_id"] == "run"
    for field, value in (
        ("actor_uid", "stranger"),
        ("run_id", "another"),
        ("conversation_id", 5),
        ("snapshot", {"items": ["fabricated"]}),
    ):
        before = getattr(receipt, field)
        setattr(receipt, field, value)
        with pytest.raises(HealthVisionError):
            await purchase_answer_in_session(session, run, binding, answer)
        setattr(receipt, field, before)


@pytest.mark.asyncio
async def test_publication_rejects_fabricated_result_after_valid_receipt(monkeypatch):
    from yuxi.services import health_consultation_service
    from yuxi.services import health_purchase_service as service

    binding = SimpleNamespace(conversation_id=3)

    async def require(*args, **kwargs):
        return binding, {}

    async def answer(*args, **kwargs):
        return {"preview_id": ADOPTION, "result": {"items": [{"net_required_grams": "20"}]}}

    monkeypatch.setattr(health_consultation_service, "require_consultation", require)
    monkeypatch.setattr(service, "purchase_answer_in_session", answer)
    run = SimpleNamespace(
        uid="owner",
        conversation_id=3,
        agent_slug="health-purchase",
        conversation_thread_id="thread",
        input_payload={"health_processing": {"purchase_selection_hash": "bound"}},
    )
    result = await answer()
    await validate_purchase_publication(None, run, json.dumps(result))
    changed = deepcopy(result)
    changed["result"]["items"][0]["net_required_grams"] = "999"
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await validate_purchase_publication(None, run, json.dumps(changed))

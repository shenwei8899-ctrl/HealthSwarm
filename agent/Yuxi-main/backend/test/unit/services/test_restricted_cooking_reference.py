"""受控做法只提供未核验资料，不绕过真实限制、来源或当前选择。"""

from copy import deepcopy
import json

from pydantic import ValidationError
import pytest

from yuxi.services import restricted_cooking_reference_service as service
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError


@pytest.fixture
def current():
    """合成当前明确填写的限制，不依赖真实成员或数据库。"""
    return {
        "selection": {
            "mode": "reference",
            "family_id": "synthetic-family",
            "participant_ids": ["synthetic-member"],
            "plan_date": "2099-01-01",
            "meal_types": ["breakfast"],
        },
        "members": [
            {
                "id": "synthetic-member",
                "name": "合成成员",
                "allergens": ["麸质谷物"],
                "intolerances": ["大豆不耐受"],
                "avoidances": ["牛羊肉"],
                "doctor_instructions": "少吃重油重盐",
            }
        ],
        "sources": {"members": {"synthetic-member": {"version": 1}}},
    }


def receipt(current):
    """合成已完成上下文工具的业务投影；同 Run 身份由调用 Owner 核验。"""
    return {**deepcopy(current), "cooking_reference_candidates": service.restricted_cooking_catalog(current)}


def choices(*candidate_ids):
    """模型仅选择资料编号，不携带菜谱正文。"""
    return [{"meal_type": "breakfast", "candidate_ids": list(candidate_ids or ["source-hard-cooked-egg"])}]


def write_data(tmp_path, monkeypatch, transform):
    """仅改临时受控目录，生产资料文件不变。"""
    data = json.loads(service.DATA_PATH.read_text(encoding="utf-8"))
    transform(data)
    path = tmp_path / "references.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(service, "DATA_PATH", path)


def test_candidates_copy_canonical_sources_without_plan_or_purchase_claims(current):
    """候选正文、来源和限制均来自当前业务事实，而非模型重写。"""
    context = receipt(current)
    original = deepcopy(context)
    result = service.build_restricted_cooking_candidates(
        current, context, choices("source-plain-rice", "source-hard-cooked-egg")
    )
    expected = {item["id"]: item for item in context["cooking_reference_candidates"]["items"]}
    assert result["status"] == "reference_candidates"
    assert result["scope"] == "cooking_reference"
    assert result["purchase_allowed"] is False
    assert result["purchase_items"] == []
    assert "preview_id" not in result
    assert result["plan_date"] == current["selection"]["plan_date"]
    assert result["selection"] == current["selection"]
    assert result["members"] == current["members"]
    assert result["candidate_selection"] == choices("source-hard-cooked-egg", "source-plain-rice")
    for dish in result["meals"][0]["dishes"]:
        assert dish == expected[dish["id"]]
        assert dish["source"]["kind"] == "source_based_notes"
        assert dish["no_added_oil"] is dish["no_added_salt"] is True
        assert "classification" not in dish
        assert "sku_id" not in dish
    assert result["restriction_verification"]["status"] == "unresolved"
    assert [item["text"] for item in result["restriction_verification"]["restrictions"]] == [
        "麸质谷物",
        "牛羊肉",
        "大豆不耐受",
        "少吃重油重盐",
    ]
    assert any("交叉接触" in text for text in result["unresolved_materials"])
    assert "不是已安排餐单或个人适用推荐" in result["notice"]
    result["members"][0]["allergens"].clear()
    result["meals"][0]["dishes"][0]["steps"].clear()
    assert context == original


@pytest.mark.parametrize(
    "field,term",
    [
        ("allergens", "鸡蛋"),
        ("allergens", "花生"),
        ("doctor_instructions", "限制蛋白质摄入"),
        ("doctor_instructions", "少吃重油重盐，并限制蛋白质"),
        ("allergens", "麸质谷物和鸡蛋"),
    ],
)
def test_other_allergies_and_unexplained_doctor_instructions_never_open_candidates(current, field, term):
    """不能用水煮蛋或其他候选名称绕过未解释的真实限制。"""
    current["members"][0][field] = term if field == "doctor_instructions" else [term]
    context = receipt(current)
    assert context["cooking_reference_candidates"]["items"] == []
    with pytest.raises(HealthVisionError, match="reference_candidate_invalid"):
        service.build_restricted_cooking_candidates(current, context, choices())


def test_missing_restriction_field_is_unknown_instead_of_no_restriction(current):
    """缺失限制字段不推断为明确无。"""
    current["members"][0]["allergens"] = None
    assert service.restricted_cooking_catalog(current)["items"] == []


def test_only_meat_or_no_restrictions_does_not_open_alternative_path(current):
    """已有普通路径或无新增有限条目时不扩大候选入口。"""
    member = current["members"][0]
    member.update(allergens=[], intolerances=[], doctor_instructions="")
    assert service.restricted_cooking_catalog(current)["items"] == []
    member["avoidances"] = []
    assert service.restricted_cooking_catalog(current)["items"] == []


@pytest.mark.parametrize(
    "selection",
    [
        choices("source-hard-cooked-egg", "source-hard-cooked-egg"),
        choices() + choices(),
        [{"meal_type": "dinner", "candidate_ids": ["source-hard-cooked-egg"]}],
        choices("invented-candidate"),
        [],
    ],
)
def test_invalid_or_duplicate_selection_is_refused(current, selection):
    """重复、不属于当前餐次或不存在的资料编号均拒绝。"""
    with pytest.raises(HealthVisionError, match="reference_candidate_invalid"):
        service.build_restricted_cooking_candidates(current, receipt(current), selection)


def test_same_candidate_cannot_be_reused_across_meals(current):
    """同一资料不能被重复包装为不同餐次的候选。"""
    current["selection"]["meal_types"] = ["breakfast", "dinner"]
    selection = choices() + [{"meal_type": "dinner", "candidate_ids": ["source-hard-cooked-egg"]}]
    with pytest.raises(HealthVisionError, match="reference_candidate_invalid"):
        service.build_restricted_cooking_candidates(current, receipt(current), selection)


@pytest.mark.parametrize(
    "field,value",
    [
        ("ingredients", ["编造配料"]),
        ("steps", ["编造步骤"]),
        ("source", {"kind": "professional_approval"}),
        ("professional_status", "approved"),
    ],
)
def test_model_cannot_supply_or_rewrite_recipe_and_approval_fields(current, field, value):
    """模型载荷不能夹带正文或审批字段。"""
    selection = choices()
    selection[0][field] = value
    with pytest.raises(ValidationError):
        service.build_restricted_cooking_candidates(current, receipt(current), selection)


@pytest.mark.parametrize("field", ["selection", "members"])
def test_other_context_receipt_cannot_be_used(current, field):
    """别的成员或选择回执不能成为本轮资料来源。"""
    context = receipt(current)
    context[field] = {} if field == "selection" else []
    with pytest.raises(HealthVisionError, match="reference_receipt_invalid"):
        service.build_restricted_cooking_candidates(current, context, choices())


def test_profile_source_change_invalidates_receipt(current):
    """档案版本改变后不能沿用旧上下文回执。"""
    context = receipt(current)
    current["sources"]["members"]["synthetic-member"]["version"] = 2
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        service.build_restricted_cooking_candidates(current, context, choices())


def test_missing_or_edited_catalog_receipt_is_rejected(current):
    """目录缺失或被改写时不猜测已读来源。"""
    context = receipt(current)
    context.pop("cooking_reference_candidates")
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        service.build_restricted_cooking_candidates(current, context, choices())
    context = receipt(current)
    context["cooking_reference_candidates"]["items"][0]["steps"] = ["伪造已读做法"]
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        service.build_restricted_cooking_candidates(current, context, choices())


def test_source_version_change_requires_fresh_context(current, tmp_path, monkeypatch):
    """当前有效新稿也必须先形成新的读取回执。"""
    context = receipt(current)

    def change(data):
        """模拟已审阅的新整理稿；新摘要不能冒用旧读取回执。"""
        item = data["references"][0]
        item["steps"][0] += "（整理稿版本更新）"
        material = deepcopy(item)
        material["source"].pop("content_hash")
        item["source"]["content_hash"] = input_fingerprint(material)

    write_data(tmp_path, monkeypatch, change)
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        service.build_restricted_cooking_candidates(current, context, choices())


@pytest.mark.parametrize(
    "change",
    [
        lambda data: data["references"][0]["steps"].append("添加酱油"),
        lambda data: data["references"][0]["ingredients"].append("未知复合调味料"),
        lambda data: data["references"][0].update(no_added_salt=False),
        lambda data: data["references"][0]["source"].update(kind="professional_approval"),
        lambda data: data["references"].append(deepcopy(data["references"][0])),
    ],
)
def test_invalid_controlled_source_is_not_a_usable_candidate(current, tmp_path, monkeypatch, change):
    """损坏摘要、复合原料、含盐和伪造审核来源均拒绝。"""
    write_data(tmp_path, monkeypatch, change)
    with pytest.raises(HealthVisionError, match="reference_source_unavailable"):
        service.restricted_cooking_catalog(current)

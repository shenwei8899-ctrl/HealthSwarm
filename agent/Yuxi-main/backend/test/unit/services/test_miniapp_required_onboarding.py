"""完整建档输入必须具备明确日期、状态和偏好，局部编辑仍允许未知。"""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from yuxi.services.miniapp_profile_types import (
    DietaryDetails,
    MiniappProfileInput,
    miniapp_onboarding_ready,
    saved_miniapp_member,
)


def complete_profile():
    """纯合成建档，基础计算资料均明确提供。"""
    return {
        "client_request_id": str(uuid4()),
        "family_version": 1,
        "usage_mode": "家庭使用",
        "default_diners": ["self"],
        "members": [
            {
                "client_ref": "self",
                "name": "合成本人",
                "relation": "本人",
                "birth_date": "1995-01-01",
                "sex": "female",
                "height_cm": 165,
                "weight_kg": 60,
                "dietary": {
                    "healthStatus": "none",
                    "allergyStatus": "none",
                    "intoleranceStatus": "none",
                    "avoidanceStatus": "none",
                    "doctorStatus": "none",
                    "goals": ["饮食均衡"],
                    "cuisines": ["不限菜系"],
                    "tastePreferences": ["不限口味"],
                },
            }
        ],
    }


@pytest.mark.parametrize(
    "field",
    [
        "birth_date",
        "sex",
        "height_cm",
        "weight_kg",
        "healthStatus",
        "allergyStatus",
        "intoleranceStatus",
        "avoidanceStatus",
        "doctorStatus",
        "goals",
        "tastePreferences",
    ],
)
def test_missing_required_field_rejected(field):
    """删除任何必填信息都不能提交完整建档。"""
    data = complete_profile()
    member = data["members"][0]
    del (member if field in {"birth_date", "sex", "height_cm", "weight_kg"} else member["dietary"])[field]
    with pytest.raises(ValidationError):
        MiniappProfileInput.model_validate(data)


@pytest.mark.parametrize(
    "field", ["healthStatus", "allergyStatus", "intoleranceStatus", "avoidanceStatus", "doctorStatus"]
)
def test_unknown_status_rejected(field):
    """未知不能被当成用户确认没有。"""
    data = complete_profile()
    data["members"][0]["dietary"][field] = "unknown"
    with pytest.raises(ValidationError):
        MiniappProfileInput.model_validate(data)


@pytest.mark.parametrize(
    ("state", "field", "value"),
    [
        ("healthStatus", "conditions", []),
        ("healthStatus", "conditions", ["其他"]),
        ("allergyStatus", "allergies", []),
        ("intoleranceStatus", "intolerances", []),
        ("avoidanceStatus", "avoidances", []),
        ("doctorStatus", "clinicianGuidance", "  "),
        (None, "goals", ["  "]),
        (None, "goals", ["其他"]),
    ],
)
def test_empty_or_placeholder_details_rejected(state, field, value):
    """有状态须提供具体内容，选择占位项不构成回答。"""
    data = complete_profile()
    dietary = data["members"][0]["dietary"]
    dietary[field] = value
    if state:
        dietary[state] = "set"
    with pytest.raises(ValidationError):
        MiniappProfileInput.model_validate(data)


def test_every_member_required_even_when_not_a_default_diner():
    """未选为默认就餐者也不能提交空白家人建档。"""
    data = complete_profile()
    relative = deepcopy(data["members"][0])
    relative.update(client_ref="relative", relation="家人", birth_date=None)
    data["members"].append(relative)
    with pytest.raises(ValidationError):
        MiniappProfileInput.model_validate(data)


def test_explicit_none_and_neutral_preferences_are_valid():
    """明确无限制及均衡饮食是有效答案，身体资料也完整保留。"""
    value = MiniappProfileInput.model_validate(complete_profile())
    assert value.members[0].dietary.doctorStatus == "none"
    assert value.members[0].height_cm == 165 and value.members[0].weight_kg == 60


@pytest.mark.parametrize(
    "field,value",
    [
        ("sex", "unspecified"),
        ("sex", None),
        ("height_cm", None),
        ("weight_kg", None),
        ("height_cm", 0),
        ("weight_kg", 0),
        ("height_cm", 301),
        ("weight_kg", 1001),
        ("height_cm", " "),
        ("weight_kg", float("nan")),
    ],
)
def test_body_fields_cannot_be_blank_or_invalid(field, value):
    """空值、占位、非有限值和越界值不能构成完整建档。"""
    data = complete_profile()
    data["members"][0][field] = value
    with pytest.raises(ValidationError):
        MiniappProfileInput.model_validate(data)


def test_partial_dietary_edit_still_preserves_unknown():
    """共享档案字段模型继续表达草稿和局部更新。"""
    assert DietaryDetails().healthStatus == "unknown"


def test_saved_body_data_is_reused_and_legacy_missing_weight_is_incomplete():
    """读取已存的规范体重。旧档案保留其它资料，且不能通过完整性检查。"""
    body = complete_profile()["members"][0]
    member = SimpleNamespace(
        id=str(uuid4()),
        name=body["name"],
        relationship=body["relation"],
        is_active=True,
        version=1,
        confirmed_version=1,
        profile={
            "sex": body["sex"],
            "birth_date": body["birth_date"],
            "height_cm": body["height_cm"],
            "dietary_details": {**body["dietary"], "statedWeightKg": body["weight_kg"]},
        },
    )
    assert saved_miniapp_member(member).weight_kg == 60
    assert miniapp_onboarding_ready(member, None)
    del member.profile["dietary_details"]["statedWeightKg"]
    before = deepcopy(member.profile)
    assert not miniapp_onboarding_ready(member, None)
    assert member.profile == before


@pytest.mark.parametrize("omitted", [True, False])
def test_cuisine_preference_remains_optional_as_in_live_release(omitted):
    """线上已允许不选择菜系，本次发布保持该行为。"""
    data = complete_profile()
    dietary = data["members"][0]["dietary"]
    if omitted:
        del dietary["cuisines"]
    else:
        dietary["cuisines"] = []
    value = MiniappProfileInput.model_validate(data)
    assert value.members[0].dietary.cuisines == []


@pytest.mark.parametrize("placeholder", ["其他", "自定义"])
def test_unexplained_cuisine_placeholder_remains_invalid(placeholder):
    """可后补不等于接受未具体填写的自定义选项。"""
    data = complete_profile()
    data["members"][0]["dietary"]["cuisines"] = [placeholder]
    with pytest.raises(ValidationError):
        MiniappProfileInput.model_validate(data)

"""完整建档输入必须具备明确日期、状态和偏好，局部编辑仍允许未知。"""

from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError

from yuxi.services.miniapp_profile_types import DietaryDetails, MiniappProfileInput


def complete_profile():
    """纯合成建档，未额外提供身高、体重或性别。"""
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
    del (member if field == "birth_date" else member["dietary"])[field]
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
        (None, "cuisines", ["自定义"]),
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
    """明确无限制及均衡饮食是有效答案，其他基础资料仍可后补。"""
    value = MiniappProfileInput.model_validate(complete_profile())
    assert value.members[0].dietary.doctorStatus == "none"
    assert value.members[0].height_cm is None and value.members[0].weight_kg is None


def test_partial_dietary_edit_still_preserves_unknown():
    """共享档案字段模型继续表达草稿和局部更新。"""
    assert DietaryDetails().healthStatus == "unknown"

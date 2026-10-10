"""结构化用户事实、明确无和监护期限的边界验证。"""

from datetime import datetime, timedelta, UTC

import pytest
from pydantic import ValidationError

from yuxi.services.family_schemas import GuardianRequest, ProfileInput, MeasurementInput


def test_structured_facts_keep_unknowns_and_do_not_make_professional_codes():
    """部分药物资料和明确无保留原语义。"""
    result = ProfileInput(
        medication_records=[{"description": "待核对药名", "status": "current"}], allergy_records=[], allergens=[]
    ).model_dump(mode="json", exclude_unset=True)
    assert result["medication_records"][0].get("dose") is None
    assert result["allergy_records"] == [] and result["allergens"] == []
    assert "population_code" not in result and "nutrition_targets" not in result


@pytest.mark.parametrize(
    "profile",
    [
        {"health_goals": [{"description": "行为目标", "start_date": "2026-10-10", "review_date": "2026-10-09"}]},
        {"medication_records": [{"description": ""}]},
        {"condition_records": [{"description": "自述", "status": "invented"}]},
    ],
)
def test_invalid_structured_records_are_rejected(profile):
    """空记录、非法状态及倒序复盘不能保存。"""
    with pytest.raises(ValidationError):
        ProfileInput(**profile)


@pytest.mark.parametrize("age,expiry", [(30, 30), (6, -1), (6, 400)])
def test_guardian_application_requires_minor_and_bounded_future_expiry(age, expiry):
    """成年、过去期限和超长期限拒绝。"""
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        GuardianRequest(
            expected_version=1,
            relationship="父亲",
            birth_date=f"{now.year - age}-01-01",
            attested=True,
            expires_at=now + timedelta(days=expiry),
        )


def test_height_is_an_independent_dated_measurement():
    """身高历史采用独立测量身份和版本。"""
    result = MeasurementInput(
        id="62e3f366-c50e-46ef-bb5a-fc75a9a69c34", kind="height", values={"height": 141}, measured_at=datetime.now(UTC)
    )
    assert result.values == {"height": 141}

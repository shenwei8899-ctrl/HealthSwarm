"""配餐前一次列出多人问题，未知字段与授权失败不泄漏档案原值。"""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from yuxi.services import reference_meal_plan_service as service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.miniapp_profile_types import miniapp_profile_issues, saved_miniapp_member


def person(name):
    """合成历史不完整档案，不使用生产数据。"""
    return SimpleNamespace(
        id=str(uuid4()),
        name=name,
        relationship="家人",
        is_active=True,
        subject_uid=None,
        version=2,
        profile={
            "sex": "unspecified",
            "birth_date": "1990-01-01",
            "height_cm": None,
            "dietary_details": {
                "statedWeightKg": None,
                "healthStatus": "none",
                "allergyStatus": "none",
                "intoleranceStatus": "none",
                "avoidanceStatus": "none",
                "doctorStatus": "none",
                "goals": ["均衡饮食"],
                "tastePreferences": ["清淡"],
            },
        },
    )


def test_all_basic_and_dietary_fields_reported_without_values():
    member = person("合成成员")
    member.profile["dietary_details"]["allergyStatus"] = "unknown"
    member.profile["dietary_details"]["goals"] = []
    original = deepcopy(member.profile)
    issues = miniapp_profile_issues(member)
    assert {i["field"] for i in issues} == {"sex", "height_cm", "weight_kg", "allergyStatus", "goals"}
    assert next(i for i in issues if i["field"] == "sex")["reason"] == "invalid"
    assert next(i for i in issues if i["field"] == "height_cm")["reason"] == "missing"
    assert all(set(i) == {"field", "label", "reason", "section", "message"} for i in issues)
    assert member.profile == original


def test_valid_profile_matches_save_contract():
    member = person("合成成员")
    member.profile.update(sex="female", height_cm=160.0)
    member.profile["dietary_details"]["statedWeightKg"] = 55.0
    assert saved_miniapp_member(member)
    assert miniapp_profile_issues(member) == []
    member.profile["dietary_details"]["goals"] = []
    assert miniapp_profile_issues(member)[0]["field"] == "goals"


def test_malformed_dietary_field_does_not_hide_other_missing_questions():
    member = person("合成甲")
    member.profile["dietary_details"].update(allergyStatus="unknown", goals=[], cuisines=123)
    issues = {issue["field"]: issue for issue in miniapp_profile_issues(member)}
    assert {"sex", "height_cm", "weight_kg", "allergyStatus", "goals", "cuisines"} <= issues.keys()
    assert issues["cuisines"]["reason"] == "invalid"
    assert issues["cuisines"]["section"] == "preferences"


def test_invalid_weight_does_not_hide_all_missing_dietary_answers():
    member = person("合成甲")
    member.profile["dietary_details"] = {"statedWeightKg": -5}
    issues = miniapp_profile_issues(member)
    assert {
        "weight_kg",
        "healthStatus",
        "allergyStatus",
        "intoleranceStatus",
        "avoidanceStatus",
        "doctorStatus",
        "goals",
        "tastePreferences",
    } <= {i["field"] for i in issues}
    assert len([i for i in issues if i["label"] == "体重"]) == 1
    member.profile["activity_level"] = "invalid"
    assert next(i for i in miniapp_profile_issues(member) if i["field"] == "activity_level")["section"] == "health"


@pytest.mark.parametrize("future_birth", ["2099-01-01T00:00:00", 4070908800])
def test_future_birth_representations_rejected_by_save_are_also_rejected_by_readiness(future_birth):
    from pydantic import ValidationError
    from yuxi.services.miniapp_profile_types import require_complete_planning_profiles

    member = person("合成甲")
    member.profile.update(sex="female", height_cm=160.0, birth_date=future_birth)
    member.profile["dietary_details"]["statedWeightKg"] = 55.0
    with pytest.raises(ValidationError):
        saved_miniapp_member(member)
    assert any(i["field"] == "birth_date" and i["reason"] == "invalid" for i in miniapp_profile_issues(member))
    with pytest.raises(HealthVisionError, match="profile_incomplete"):
        require_complete_planning_profiles([member], family=SimpleNamespace(owner_uid="owner"), uid="owner")


@pytest.mark.asyncio
@pytest.mark.parametrize("deny_second", [False, True])
async def test_collect_members_after_all_authorization(monkeypatch, deny_second):
    people = [person("合成甲"), person("合成乙")]
    family = SimpleNamespace(id=str(uuid4()), owner_uid="actor", version=1)
    by_id = {p.id: p for p in people}
    family_service = SimpleNamespace(context=AsyncMock(return_value=(family, None)))
    repository = SimpleNamespace(
        member=AsyncMock(side_effect=lambda fid, mid: by_id[mid]),
        linked_health_member=AsyncMock(side_effect=lambda fid, mid: mid),
    )

    async def authorize(mid, uid, scope):
        if deny_second and mid == people[1].id:
            raise HealthVisionError("not_authorized", "无权使用", 403)

    health = SimpleNamespace(authorize=AsyncMock(side_effect=authorize), require_consent=AsyncMock())
    monkeypatch.setattr(service, "FamilyService", lambda *args: family_service)
    monkeypatch.setattr(service, "FamilyRepository", lambda *args: repository)
    monkeypatch.setattr(service, "HealthVisionRepository", lambda *args: health)
    monkeypatch.setattr(
        service.health_vision_service,
        "configuration",
        AsyncMock(
            return_value={
                "meal_plan": {"available": True, "model": "synthetic", "processor": "synthetic"},
                "policy_version": "test",
            }
        ),
    )
    selection = {
        "mode": "reference",
        "family_id": family.id,
        "participant_ids": [p.id for p in people],
        "plan_date": "2026-11-28",
        "meal_types": ["breakfast"],
    }
    with pytest.raises(HealthVisionError) as error:
        await service.reference_context_in_session(None, "actor", people[0].id, selection)
    if deny_second:
        assert error.value.code == "not_authorized"
        assert error.value.profile_issues is None
    else:
        assert error.value.code == "profile_incomplete"
        assert {p["name"] for p in error.value.profile_issues} == {p.name for p in people}
        assert all(
            {f["field"] for f in p["fields"]} == {"sex", "height_cm", "weight_kg"} for p in error.value.profile_issues
        )
        assert all(p["can_edit"] for p in error.value.profile_issues)
    health.require_consent.assert_not_awaited()

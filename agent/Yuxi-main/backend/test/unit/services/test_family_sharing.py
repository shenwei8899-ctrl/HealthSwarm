"""普通家庭共享和 AI 来源权限分别计算。"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from yuxi.services.family_schemas import METRIC_FIELDS, PROFILE_FIELDS
from yuxi.services.family_service import authorized_fields


@pytest.mark.parametrize("uid", ["owner", "peer"])
def test_family_sharing_is_explicit_and_never_the_ai_default(uid):
    """恢复全局放开缺陷时，默认 AI 来源拒绝断言必须失败。"""
    family = SimpleNamespace(owner_uid="owner")
    member = SimpleNamespace(
        is_active=True,
        subject_uid="subject",
        guardian_uid=None,
        profile={"birth_date": "1990-01-01"},
        grant_purpose=None,
        grant_expires_at=None,
        grant_fields=[],
        grant_edit_fields=[],
    )
    assert authorized_fields(family, member, uid) == set()
    assert authorized_fields(family, member, uid, family_sharing=True) == PROFILE_FIELDS | METRIC_FIELDS.keys()
    assert (
        authorized_fields(family, member, uid, write=True, family_sharing=True) == PROFILE_FIELDS | METRIC_FIELDS.keys()
    )
    member.grant_purpose = "family_nutrition"
    member.grant_expires_at = datetime.now() + timedelta(days=1)
    member.grant_fields = ["height_cm"]
    assert authorized_fields(family, member, uid) == ({"height_cm"} if uid == "owner" else set())
    assert authorized_fields(family, member, uid, write=True) == set()
    member.is_active = False
    assert authorized_fields(family, member, uid, family_sharing=True) == set()

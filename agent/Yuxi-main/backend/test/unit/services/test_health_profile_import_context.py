"""专业导入上下文的独立权限、必要字段与候选完整性。"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.repositories.family_repository import FamilyRepository
from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services import health_profile_import_service
from yuxi.services.family_schemas import REQUIRED_PROFILE_FIELDS
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = pytest.mark.asyncio


@pytest.fixture
def source_context(monkeypatch):
    """存储设备隔离，实际家庭字段授权和候选校验保持执行。"""
    now = utc_now_naive()
    link = SimpleNamespace(family_id="family", source_member_id="source", actor_uid="subject")
    family = SimpleNamespace(id="family", owner_uid="admin")
    source = SimpleNamespace(
        id="source",
        is_active=True,
        subject_uid="subject",
        profile={
            "sex": "female",
            "birth_date": "1990-01-01",
            "height_cm": 165,
            "activity_level": "light",
            "goal": "合成目标",
            "medical_history": "不得进入基础字段上下文",
        },
        version=2,
        confirmed_version=2,
        grant_fields=[*REQUIRED_PROFILE_FIELDS, "weight", "medical_history"],
        grant_edit_fields=[],
        grant_purpose="family_nutrition",
        grant_expires_at=now + timedelta(days=1),
    )
    record = SimpleNamespace(
        id="old-record",
        values={"weight": 60.0},
        version=3,
        source="synthetic-scale",
        measured_at=now - timedelta(days=65),
    )
    session = SimpleNamespace(get=AsyncMock(return_value=link), refresh=AsyncMock())
    family_query = AsyncMock(return_value=family)
    page = AsyncMock(return_value=([record], 4))
    audit = AsyncMock()
    monkeypatch.setattr(FamilyRepository, "get_family", family_query)
    monkeypatch.setattr(FamilyRepository, "member", AsyncMock(return_value=source))
    monkeypatch.setattr(FamilyRepository, "measurement_page", page)
    monkeypatch.setattr(FamilyRepository, "audit", audit)
    return SimpleNamespace(
        repo=HealthFamilyProfileRepository(session),
        session=session,
        link=link,
        family=family,
        source=source,
        record=record,
        family_query=family_query,
        page=page,
        audit=audit,
    )


async def test_owner_requires_explicit_fields_and_returns_only_needed_data(source_context):
    """有目的期限的显式授权提供旧体重，病史和代维护权不进入响应。"""
    case = source_context
    result = await case.repo.read_import_source("admin", "health", limit=1, offset=2)
    formal, weights = result["formal_source"], result["weight_candidates"]
    assert formal["status"] == "ready" and formal["reason"] is None
    assert formal["family_profile_source"] == {
        "family_id": "family",
        "source_member_id": "source",
        "confirmed_version": 2,
    }
    assert set(formal["profile"]) == set(REQUIRED_PROFILE_FIELDS)
    assert formal["allowed_fields"] == sorted(REQUIRED_PROFILE_FIELDS)
    assert weights["items"][0]["weight_kg"] == "60.0" and weights["items"][0]["version"] == 3
    assert set(weights["items"][0]) == {"record_id", "version", "weight_kg", "unit", "measured_at", "source"}
    assert weights["total"] == 4 and weights["limit"] == 1 and weights["offset"] == 2
    args, kwargs = case.page.call_args
    assert args == (["source"], ["weight"]) and "since" not in kwargs
    assert isinstance(kwargs["until"], datetime) and kwargs["limit"] == 1 and kwargs["offset"] == 2
    assert all(call.args[2] == "admin" for call in case.audit.call_args_list)


async def test_self_retains_original_field_access_without_owner_grants(source_context):
    """本人访问不依赖其向家庭管理员签发的授权。"""
    case = source_context
    case.source.grant_fields = []
    case.source.grant_expires_at = None
    result = await case.repo.read_import_source("subject", "health")
    assert result["formal_source"]["status"] == result["weight_candidates"]["status"] == "ready"
    case.family_query.assert_awaited_once_with("family", "subject")


@pytest.mark.parametrize("fault", ["expired", "revoked", "purpose", "unclaimed", "minor", "nonowner"])
async def test_family_authorization_boundaries_hide_coordinates_and_values(source_context, fault):
    """健康授权不补齐家庭权限，期限、用途、主体及成年边界分别约束读取。"""
    case = source_context
    if fault == "expired":
        case.source.grant_expires_at = utc_now_naive() - timedelta(seconds=1)
    elif fault == "revoked":
        case.source.grant_fields = []
    elif fault == "purpose":
        case.source.grant_purpose = "other"
    elif fault == "unclaimed":
        case.source.subject_uid = None
    elif fault == "minor":
        case.source.profile = {**case.source.profile, "birth_date": "2020-01-01"}
    else:
        case.family.owner_uid = "other"
    result = await case.repo.read_import_source("admin", "health")
    assert result["formal_source"]["status"] == "not_ready"
    assert result["formal_source"]["family_profile_source"] is None
    assert result["formal_source"]["profile"] == {}
    assert result["weight_candidates"]["items"] == [] and result["weight_candidates"]["total"] == 0
    case.page.assert_not_awaited()


async def test_family_visibility_uses_current_actor(source_context):
    """只有关联本人可见的家庭不能借其身份向管理员提供原始来源。"""
    case = source_context

    async def visible(fid, uid):
        return case.family if uid == "subject" else None

    case.family_query.side_effect = visible
    result = await case.repo.read_import_source("admin", "health")
    assert result["formal_source"]["reason"] == "family_profile_access_required"
    assert result["formal_source"]["profile"] == {} and result["formal_source"]["family_profile_source"] is None
    assert result["weight_candidates"]["items"] == []
    case.page.assert_not_awaited()


@pytest.mark.parametrize("fault", ["inactive", "identity", "missing"])
async def test_invalid_source_identity_has_no_readable_payload(source_context, monkeypatch, fault):
    """失效、不同主体或缺失源成员不会继续按旧关联读取。"""
    case = source_context
    if fault == "inactive":
        case.source.is_active = False
    elif fault == "identity":
        case.source.subject_uid = "admin"
    else:
        monkeypatch.setattr(FamilyRepository, "member", AsyncMock(return_value=None))
    result = await case.repo.read_import_source("admin", "health")
    assert result["formal_source"]["reason"] == "family_profile_source_unavailable"
    assert result["formal_source"]["family_profile_source"] is None and result["formal_source"]["profile"] == {}
    assert result["weight_candidates"]["items"] == []
    case.page.assert_not_awaited()


async def test_partial_basic_access_does_not_reveal_confirmation_or_coordinates(source_context):
    """单字段授权只显示该字段，确认状态与三项坐标需要完整基础读取权。"""
    case = source_context
    case.source.grant_fields = ["height_cm", "weight"]
    result = await case.repo.read_import_source("admin", "health")
    formal = result["formal_source"]
    assert formal["status"] == "not_ready" and formal["reason"] == "family_profile_fields_required"
    assert formal["family_profile_source"] is None and formal["profile"] == {"height_cm": 165}
    assert formal["allowed_fields"] == ["height_cm"]
    assert result["weight_candidates"]["status"] == "ready"


async def test_basic_read_permission_does_not_imply_weight_access(source_context):
    """完整基础档案可读时也须独立取得weight字段读取权。"""
    case = source_context
    case.source.grant_fields = list(REQUIRED_PROFILE_FIELDS)
    result = await case.repo.read_import_source("admin", "health")
    assert result["formal_source"]["status"] == "ready"
    assert result["weight_candidates"]["reason"] == "weight_access_required"
    assert result["weight_candidates"]["items"] == []
    case.page.assert_not_awaited()


@pytest.mark.parametrize("fault", ["unconfirmed", "incomplete", "unlinked", "empty"])
async def test_missing_source_and_measurement_states_remain_explicit(source_context, fault):
    """不确认、不完整、未关联及无候选均保留独立缺失状态。"""
    case = source_context
    if fault == "unconfirmed":
        case.source.confirmed_version = 1
    elif fault == "incomplete":
        case.source.profile = {**case.source.profile, "height_cm": None}
    elif fault == "unlinked":
        case.session.get.return_value = None
    else:
        case.page.return_value = ([], 0)
    result = await case.repo.read_import_source("admin", "health")
    if fault == "empty":
        assert result["formal_source"]["status"] == "ready"
        assert result["weight_candidates"]["reason"] == "weight_missing"
    else:
        assert result["formal_source"]["status"] == "not_ready"
        assert result["formal_source"]["family_profile_source"] is None


@pytest.mark.parametrize("value", [True, "60", 0, -1, float("inf"), float("nan"), None])
async def test_corrupt_persisted_weight_refuses_candidate_page(source_context, value):
    """候选数值不转换字符串或布尔值，非有限及缺失值明确拒绝整页。"""
    source_context.record.values = {"weight": value}
    with pytest.raises(HealthVisionError) as caught:
        await source_context.repo.read_import_source("admin", "health")
    assert (caught.value.status, caught.value.code) == (410, "weight_measurement_source_changed")


@pytest.mark.parametrize("version", [0, -1, True, "1"])
async def test_corrupt_persisted_version_refuses_candidate_page(source_context, version):
    """候选独立版本必须为正整数，不能向导入传播含糊或无效版本。"""
    source_context.record.version = version
    with pytest.raises(HealthVisionError) as caught:
        await source_context.repo.read_import_source("admin", "health")
    assert caught.value.status == 410


@pytest.fixture
def service_context(monkeypatch):
    """仅隔离数据库，公开用例仍逐项执行授权与版本装配。"""
    session = SimpleNamespace()

    @asynccontextmanager
    async def database():
        yield session

    admin = AsyncMock()
    authorize = AsyncMock()
    source = AsyncMock(return_value={"formal_source": {}, "weight_candidates": {}})
    profile = AsyncMock(return_value={"version": 5, "status": "not_ready", "reason": "expired"})
    monkeypatch.setattr(health_profile_import_service.pg_manager, "get_async_session_context", database)
    monkeypatch.setattr(health_profile_import_service, "require_evidence_admin", admin)
    monkeypatch.setattr(HealthVisionRepository, "authorize", authorize)
    monkeypatch.setattr(HealthFamilyProfileRepository, "read_import_source", source)
    monkeypatch.setattr(HealthQualityRepository, "profile_projection", profile)
    return SimpleNamespace(admin=admin, authorize=authorize, source=source, profile=profile)


async def test_latest_unusable_profile_still_advances_next_version(service_context):
    """最高撤回或过期版本仍占用其版本，不通过旧版回退计算下一版本。"""
    result = await health_profile_import_service.read_profile_import_context("admin", "health", limit=1, offset=2)
    assert result["current_profile"]["next_version"] == 6
    assert result["current_profile"]["reason"] == "expired"
    assert [call.args[2] for call in service_context.authorize.call_args_list] == ["profile_edit", "profile_view"]


@pytest.mark.parametrize("guard", ["admin", "profile_edit", "profile_view"])
async def test_service_permission_guards_cannot_be_replaced_by_ui(service_context, guard):
    """替代service调用也拒绝缺失管理员或任何健康scope的读取。"""
    case = service_context
    if guard == "admin":
        case.admin.side_effect = HealthVisionError("forbidden", "禁止", 403)
    else:

        async def authorize(member_id, uid, scope, **kwargs):
            if scope == guard:
                raise HealthVisionError("not_found", "无权", 404)

        case.authorize.side_effect = authorize
    with pytest.raises(HealthVisionError) as caught:
        await health_profile_import_service.read_profile_import_context("admin", "health")
    assert caught.value.status == (403 if guard == "admin" else 404)
    case.source.assert_not_awaited()

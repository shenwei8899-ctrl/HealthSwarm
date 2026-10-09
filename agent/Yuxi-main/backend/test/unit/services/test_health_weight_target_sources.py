"""本人明确实测来源、批准目标和实际质量消费者的拒绝边界。"""

import hashlib
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from yuxi.repositories.family_repository import FamilyRepository
from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services import health_dependency_service, health_personal_target_service, health_quality_service
from yuxi.services.health_personal_targets import calculate_personal_targets
from yuxi.services.health_quality_checks import external_projection, projection_digest
from yuxi.services.health_quality_types import PersonalTargetSelection, ProfileImport, ProfileProjection, QualityRules
from yuxi.services.health_vision_types import HealthVisionError

pytestmark = pytest.mark.unit

MEMBER = "00000000-0000-4000-8000-000000000001"
FAMILY = "00000000-0000-4000-8000-000000000002"
SOURCE_MEMBER = "00000000-0000-4000-8000-000000000003"
RECORD = "00000000-0000-4000-8000-000000000004"
FOOD = "00000000-0000-4000-8000-000000000005"
OWNER = "synthetic-owner"
RULE = "synthetic-weight-target"


def test_profile_import_accepts_only_explicit_weight_coordinates():
    """输入只携带明确记录和版本，缺省与明确空值仍兼容。"""
    data = ProfileImport.model_validate(import_body())
    assert data.weight_measurement_source.model_dump(mode="json") == {"record_id": RECORD, "version": 1}
    assert data.payload.weight_kg == Decimal("60.000000")
    for with_null in (False, True):
        body = import_body()
        body.pop("weight_measurement_source")
        body.pop("family_profile_source")
        if with_null:
            body["weight_measurement_source"] = None
        assert ProfileImport.model_validate(body).weight_measurement_source is None


@pytest.mark.parametrize("version", [True, "1", 0, -1, 1.0, None])
def test_weight_source_version_is_strict_positive_integer(version):
    """布尔、字符串及非正数不能进入来源版本契约。"""
    body = import_body()
    body["weight_measurement_source"]["version"] = version
    with pytest.raises(ValidationError):
        ProfileImport.model_validate(body)


@pytest.mark.parametrize("fault", ["no_family", "uuid", "root_hash", "weight_hash", "weight_value", "weight_unit"])
def test_profile_import_rejects_unbound_or_client_attested_weight(fault):
    """归属必需；数值、单位及摘要均不能藏在来源对象或根输入。"""
    body = import_body()
    if fault == "no_family":
        body.pop("family_profile_source")
    elif fault == "uuid":
        body["weight_measurement_source"]["record_id"] = "invalid-record"
    elif fault == "root_hash":
        body["source_hash"] = "a" * 64
    else:
        field = {"weight_hash": "source_hash", "weight_value": "weight_kg", "weight_unit": "unit"}[fault]
        body["weight_measurement_source"][field] = "forged"
    with pytest.raises(ValidationError):
        ProfileImport.model_validate(body)


@pytest.mark.parametrize("weight,expected", [("60", "330"), ("61", "335")])
def test_approved_target_uses_independent_330_to_335_oracle(weight, expected):
    """独立手算30+5×60=330，30+5×61=335；常数营养范围不漂移。"""
    payload = profile_payload(weight)
    result = calculate_personal_targets(
        ProfileProjection.model_validate(payload), QualityRules.model_validate(rule_payload())
    )
    assert result["status"] == "ready"
    assert Decimal(result["energy_kcal"]) == Decimal(expected)
    assert {key: Decimal(value) for key, value in result["bounds"]["energy_kcal"].items()} == {
        "minimum": Decimal(expected),
        "maximum": Decimal(expected),
    }
    assert result["bounds"]["protein_g"] == {"minimum": "20", "maximum": "40"}
    assert result["inputs"]["weight_kg"] == weight
    assert "height_cm" not in result["inputs"]


def test_nonzero_weight_formula_rejects_unmapped_linked_parameter():
    """正文中的60kg不能替代明确选定实测的依赖。"""
    result = calculate_personal_targets(
        ProfileProjection.model_validate(profile_payload()),
        QualityRules.model_validate(rule_payload()),
        weight_source_missing=True,
    )
    assert result["status"] == "not_ready" and result["reason"] == "selected_weight_measurement_required"
    assert result["missing_field"] == "weight_kg" and "bounds" not in result


def test_zero_weight_and_height_coefficients_do_not_collect_unused_fields():
    """零系数只使用批准常数330，无实测和身高仍可计算。"""
    payload, rules = profile_payload(), rule_payload()
    payload.pop("weight_kg")
    rules["personal_targets"][0].update(intercept_kcal="330", weight_kg_coefficient="0")
    result = calculate_personal_targets(
        ProfileProjection.model_validate(payload),
        QualityRules.model_validate(rules),
        weight_source_missing=True,
    )
    assert result["status"] == "ready" and Decimal(result["energy_kcal"]) == 330
    assert "weight_kg" not in result["inputs"] and "height_cm" not in result["inputs"]


@pytest.mark.asyncio
async def test_weight_source_hash_binds_actual_provenance_without_query_window(source_context):
    """明确记录即使早于30天也可核对；单位、来源、时间和实际值共同进摘要。"""
    ctx = source_context
    ctx.record.measured_at = datetime(2020, 1, 1)
    weight, reference = await ctx.repo.weight_source(MEMBER, RECORD)
    facts = {
        "family_id": FAMILY,
        "source_member_id": SOURCE_MEMBER,
        "record_id": RECORD,
        "version": 1,
        "kind": "weight",
        "weight_kg": "60.0",
        "unit": "kg",
        "measured_at": "2020-01-01T00:00:00Z",
        "source": "synthetic-scale",
    }
    assert weight == Decimal("60")
    assert reference == {key: value for key, value in facts.items() if key not in {"kind", "weight_kg"}} | {
        "source_hash": independent_digest(facts)
    }
    ctx.record.values = {"weight": 61.0}
    new_weight, new_reference = await ctx.repo.weight_source(MEMBER, RECORD)
    assert new_weight == Decimal("61") and new_reference["source_hash"] != reference["source_hash"]


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["unlinked", "missing", "foreign", "kind", "voided", "future"])
async def test_weight_source_rejects_unavailable_record_without_disclosure(source_context, fault):
    """缺关联、他人、错误类型、作废及未来记录统一不可用。"""
    ctx = source_context
    if fault == "unlinked":
        ctx.session.get.return_value = None
    elif fault == "missing":
        ctx.measurement.return_value = None
    elif fault == "foreign":
        ctx.record.member_id = MEMBER
    elif fault == "kind":
        ctx.record.kind = "blood_pressure"
    elif fault == "voided":
        ctx.record.voided_at = ctx.record.measured_at
    else:
        ctx.record.measured_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
    with pytest.raises(HealthVisionError) as error:
        await ctx.repo.weight_source(MEMBER, RECORD)
    assert (error.value.status, error.value.code) == (404, "not_found")


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["inactive", "foreign_subject", "foreign_actor", "missing_member", "missing_family"])
async def test_weight_source_requires_active_self_link(source_context, fault):
    """家庭管理员或旧关联不能继承本人已停用的处理授权。"""
    ctx = source_context
    if fault == "inactive":
        ctx.member.is_active = False
    elif fault == "foreign_subject":
        ctx.member.subject_uid = "other-user"
    elif fault == "foreign_actor":
        ctx.link.actor_uid = "other-user"
    elif fault == "missing_member":
        ctx.member_query.return_value = None
    else:
        ctx.family_query.return_value = None
    with pytest.raises(HealthVisionError) as error:
        await ctx.repo.weight_source(MEMBER, RECORD)
    assert (error.value.status, error.value.code) == (404, "not_found")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values",
    [
        None,
        [],
        {},
        {"weight": True},
        {"weight": "60"},
        {"weight": 0},
        {"weight": -1},
        {"weight": float("nan")},
        {"weight": float("inf")},
        {"weight": 60, "extra": 1},
    ],
)
async def test_malformed_persisted_weight_is_explicitly_changed(source_context, values):
    """持久化坏值不能变零、字符串数值或继续作为确认体重。"""
    source_context.record.values = values
    with pytest.raises(HealthVisionError) as error:
        await source_context.repo.weight_source(MEMBER, RECORD)
    assert (error.value.status, error.value.code) == (410, "weight_measurement_source_changed")


@pytest.mark.asyncio
async def test_import_persists_server_weight_attestation_and_digest(import_context):
    """Decimal等值接受；导入最终对象保存真实实测依据并参与投影摘要。"""
    ctx = import_context
    result = await health_dependency_service.import_profile_projection(
        OWNER, MEMBER, ProfileImport.model_validate(import_body())
    )
    row = ctx.rows[0]
    assert result["status"] == "ready" and result["payload"]["weight_kg"] == "60.000000"
    assert row.attestation["weight_measurement_source"] == ctx.weight_reference
    assert row.attestation["family_profile_source"] == ctx.family_reference
    assert row.content_hash == independent_digest(
        {
            "kind": "profile",
            "key": MEMBER,
            "version": 1,
            "payload": row.payload,
            "attestation": row.attestation,
        }
    )
    original = row.content_hash
    row.attestation["weight_measurement_source"]["source"] = "forged-source"
    assert external_projection(row, "profile", MEMBER)["reason"] == "integrity_mismatch"
    assert row.content_hash == original


@pytest.mark.asyncio
async def test_explicit_reimport_updates_actual_target_service_330_to_335(import_context, monkeypatch):
    """旧测量变源拒绝；明确新专业版本导入后实际目标服务才产生335。"""
    ctx = import_context
    rule_row = snapshot("rules", RULE, rule_payload(), {})
    monkeypatch.setattr(HealthQualityRepository, "rules", AsyncMock(return_value=rule_row))
    await health_dependency_service.import_profile_projection(
        OWNER, MEMBER, ProfileImport.model_validate(import_body())
    )
    initial = await health_personal_target_service.read_personal_targets(OWNER, MEMBER, target_selection())
    assert initial["status"] == "ready" and Decimal(initial["energy_kcal"]) == Decimal("330")

    ctx.record.values = {"weight": 61.0}
    ctx.record.version = 2
    changed = await health_personal_target_service.read_personal_targets(OWNER, MEMBER, target_selection())
    assert changed["status"] == "not_ready" and "bounds" not in changed
    assert changed["sources"]["profile"]["reason"] == "weight_measurement_source_changed"

    body = import_body()
    body["version"] = 2
    body["payload"]["weight_kg"] = "61.000000"
    body["weight_measurement_source"]["version"] = 2
    await health_dependency_service.import_profile_projection(OWNER, MEMBER, ProfileImport.model_validate(body))
    updated = await health_personal_target_service.read_personal_targets(
        OWNER,
        MEMBER,
        PersonalTargetSelection(rule_code=RULE, rule_version=1, profile_version=2),
    )
    assert updated["status"] == "ready" and Decimal(updated["energy_kcal"]) == Decimal("335")
    assert updated["sources"]["profile"]["version"] == 2
    assert updated["attestations"]["profile"]["weight_measurement_source"]["record_id"] == RECORD
    assert updated["attestations"]["profile"]["weight_measurement_source"]["version"] == 2
    assert len(ctx.rows) == 2 and ctx.rows[0].payload["weight_kg"] == "60.000000"


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["version", "value", "missing_value"])
async def test_import_rejects_weight_version_or_decimal_value_mismatch(import_context, fault):
    """失败发生在持久化之前，不能保存版本不符或专业数值不符的正文。"""
    body = import_body()
    if fault == "version":
        body["weight_measurement_source"]["version"] = 2
    elif fault == "value":
        body["payload"]["weight_kg"] = "60.000001"
    else:
        body["payload"].pop("weight_kg")
    with pytest.raises(HealthVisionError) as error:
        await health_dependency_service.import_profile_projection(OWNER, MEMBER, ProfileImport.model_validate(body))
    assert (error.value.status, error.value.code) == (409, "weight_measurement_source_conflict")
    assert import_context.rows == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["foreign", "voided"])
async def test_import_preserves_unavailable_weight_failure(import_context, fault):
    """导入不会吞掉真实来源仓储的他人和作废错误。"""
    if fault == "foreign":
        import_context.record.member_id = MEMBER
    else:
        import_context.record.voided_at = import_context.record.measured_at
    with pytest.raises(HealthVisionError) as error:
        await health_dependency_service.import_profile_projection(
            OWNER, MEMBER, ProfileImport.model_validate(import_body())
        )
    assert (error.value.status, error.value.code) == (404, "not_found")
    assert import_context.rows == []


@pytest.mark.asyncio
async def test_projection_rechecks_selected_weight_and_hides_changed_payload(projection_context):
    """更正所选值后旧专业正文及依据均隐藏，不从新测量自动重绑。"""
    ctx = projection_context
    ctx.record.values = {"weight": 61.0}
    ctx.record.version = 2
    result = await HealthQualityRepository(ctx.session).profile_projection(MEMBER)
    assert result["status"] == "not_ready" and result["reason"] == "weight_measurement_source_changed"
    assert result["payload"] is None and result["attestation"] is None
    assert result["version"] == 1 and result["content_hash"] == ctx.profile_row.content_hash


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["record_id", "missing_id", "not_object", "value", "unavailable", "malformed"])
async def test_projection_invalid_reference_or_value_cannot_remain_ready(projection_context, fault):
    """即使总摘要重新计算，畸形坐标和变更实测仍不能成为可用正文。"""
    ctx = projection_context
    proof = ctx.profile_row.attestation
    if fault == "record_id":
        proof["weight_measurement_source"]["record_id"] = "bad-uuid"
    elif fault == "missing_id":
        proof["weight_measurement_source"].pop("record_id")
    elif fault == "not_object":
        proof["weight_measurement_source"] = []
    elif fault == "value":
        ctx.profile_row.payload["weight_kg"] = "61"
    elif fault == "unavailable":
        ctx.measurement.return_value = None
    else:
        ctx.record.values = {"weight": True}
    ctx.profile_row.content_hash = projection_digest("profile", MEMBER, 1, ctx.profile_row.payload, proof)
    result = await HealthQualityRepository(ctx.session).profile_projection(MEMBER)
    assert result["status"] == "not_ready" and result["reason"] == "weight_measurement_source_changed"
    assert result["payload"] is None and result["attestation"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [HealthVisionError("database_problem", "合成错误", 503), RuntimeError("synthetic failure")]
)
async def test_projection_does_not_swallow_unexpected_weight_resolver_error(projection_context, monkeypatch, error):
    """仅已知来源失效转成未就绪，设备故障须明确上抛。"""
    monkeypatch.setattr(HealthFamilyProfileRepository, "weight_source", AsyncMock(side_effect=error))
    with pytest.raises(type(error)) as raised:
        await HealthQualityRepository(projection_context.session).profile_projection(MEMBER)
    assert raised.value is error


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_target_service_enforces_selected_weight_dependency_and_legacy_compatibility(projection_context, legacy):
    """实际服务对正式关联缺源拒绝；无关联独立专业投影保留旧计算。"""
    ctx = projection_context
    ctx.profile_row.attestation.pop("weight_measurement_source")
    if legacy:
        ctx.session.get.return_value = None
        ctx.profile_row.attestation.pop("family_profile_source")
    ctx.profile_row.content_hash = projection_digest(
        "profile", MEMBER, 1, ctx.profile_row.payload, ctx.profile_row.attestation
    )
    result = await health_personal_target_service.read_personal_targets(OWNER, MEMBER, target_selection())
    if legacy:
        assert result["status"] == "ready" and Decimal(result["energy_kcal"]) == 330
    else:
        assert result["status"] == "not_ready" and result["reason"] == "selected_weight_measurement_required"
        assert "bounds" not in result


@pytest.mark.asyncio
async def test_target_service_rejects_changed_selected_weight(projection_context):
    """目标接口真实调用统一投影重验，不能直接解析旧正文计算330。"""
    ctx = projection_context
    ctx.record.values = {"weight": 61.0}
    ctx.record.version = 2
    result = await health_personal_target_service.read_personal_targets(OWNER, MEMBER, target_selection())
    assert result["status"] == "not_ready" and "bounds" not in result
    assert result["sources"]["profile"]["reason"] == "weight_measurement_source_changed"


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["selected", "missing", "changed", "zero", "legacy"])
async def test_saved_plan_quality_consumes_same_weight_dependency(projection_context, monkeypatch, state):
    """实际已存餐单质量上下文与最终检查共享本人实测依赖，完整营养不掩盖缺源。"""
    ctx = projection_context
    if state in {"missing", "zero", "legacy"}:
        ctx.profile_row.attestation.pop("weight_measurement_source")
    if state == "changed":
        ctx.record.version = 2
    elif state == "zero":
        ctx.profile_row.payload.pop("weight_kg")
        ctx.rule_row.payload["personal_targets"][0].update(intercept_kcal="330", weight_kg_coefficient="0")
        ctx.rule_row.content_hash = projection_digest("rules", RULE, 1, ctx.rule_row.payload, ctx.rule_row.attestation)
    elif state == "legacy":
        ctx.profile_row.attestation.pop("family_profile_source")
        ctx.session.get.return_value = None
    ctx.profile_row.content_hash = projection_digest(
        "profile", MEMBER, 1, ctx.profile_row.payload, ctx.profile_row.attestation
    )
    calculated = {
        "nutrition": {
            "totals": {
                "energy_kcal": "330",
                "protein_g": "30",
                "fat_g": "6",
                "carbohydrate_g": "60",
                "sodium_mg": "150",
            }
        }
    }
    plan = SimpleNamespace(
        id=RECORD,
        member_id=MEMBER,
        version=1,
        snapshot=deepcopy(calculated),
        spec={
            "plan_date": "2026-10-06",
            "meals": [
                {"meal_type": meal, "dishes": [{"recipe_version_id": FOOD, "grams": "100"}]}
                for meal in ("breakfast", "lunch", "dinner")
            ],
        },
    )
    monkeypatch.setattr(HealthQualityRepository, "plan", AsyncMock(return_value=plan))
    monkeypatch.setattr(HealthQualityRepository, "lock_profile_sources", AsyncMock())
    monkeypatch.setattr(
        HealthQualityRepository,
        "ingredients",
        AsyncMock(
            return_value=(
                {FOOD: {"content_hash": "a" * 64, "source_current": True}},
                {},
            )
        ),
    )
    monkeypatch.setattr(health_quality_service, "calculate_in_session", AsyncMock(return_value=calculated))
    current = await health_quality_service.quality_context_in_session(
        ctx.session,
        OWNER,
        SimpleNamespace(plan_id=RECORD, plan_version=1, rule_code=RULE),
    )
    safety = health_quality_service.quality_snapshot(current)["safety_check"]
    if state in {"selected", "zero", "legacy"}:
        assert safety["status"] == "passed" and safety["missing"] == []
        assert Decimal(safety["personal_targets"]["energy_kcal"]) == 330
    else:
        assert safety["status"] == "unknown"
        assert safety["missing"] == [
            {
                "path": "personal_targets" if state == "missing" else "profile",
                "reason": "selected_weight_measurement_required"
                if state == "missing"
                else "weight_measurement_source_changed",
            }
        ]
        if state == "changed":
            assert current["profile"]["payload"] is None and current["profile"]["attestation"] is None


@pytest.fixture
def source_context(monkeypatch):
    """隔离数据库设备；本人来源与实测校验保留真实实现。"""
    link = SimpleNamespace(member_id=MEMBER, family_id=FAMILY, source_member_id=SOURCE_MEMBER, actor_uid=OWNER)
    member = SimpleNamespace(
        id=SOURCE_MEMBER, is_active=True, subject_uid=OWNER, version=1, confirmed_version=1, profile={}
    )
    record = SimpleNamespace(
        id=RECORD,
        member_id=SOURCE_MEMBER,
        kind="weight",
        values={"weight": 60.0},
        version=1,
        source="synthetic-scale",
        measured_at=datetime(2020, 1, 1),
        voided_at=None,
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=link), refresh=AsyncMock(), scalar=AsyncMock(return_value=None)
    )
    family_query = AsyncMock(return_value=SimpleNamespace(id=FAMILY))
    member_query = AsyncMock(return_value=member)
    measurement = AsyncMock(return_value=record)
    monkeypatch.setattr(FamilyRepository, "get_family", family_query)
    monkeypatch.setattr(FamilyRepository, "member", member_query)
    monkeypatch.setattr(FamilyRepository, "measurement", measurement)
    return SimpleNamespace(
        repo=HealthFamilyProfileRepository(session),
        session=session,
        link=link,
        member=member,
        record=record,
        family_query=family_query,
        member_query=member_query,
        measurement=measurement,
    )


@pytest.fixture
def import_context(source_context, monkeypatch):
    """导入使用真实来源校验；仅隔离存储及管理员设备。"""
    ctx = source_context
    ctx.rows = []
    ctx.session.add = Mock(side_effect=ctx.rows.append)
    ctx.session.flush = AsyncMock()

    @asynccontextmanager
    async def session_context():
        """当前单测不建立真实事务。"""
        yield ctx.session

    async def profile(repository, member_id):
        """返回本用例实际新增的对象。"""
        return ctx.rows[-1] if ctx.rows else None

    monkeypatch.setattr(health_dependency_service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(health_dependency_service, "require_evidence_admin", AsyncMock())
    monkeypatch.setattr(HealthVisionRepository, "authorize", AsyncMock())
    monkeypatch.setattr(HealthQualityRepository, "profile", profile)
    monkeypatch.setattr(HealthQualityRepository, "invalidate", AsyncMock())
    ctx.family_reference = family_reference()
    ctx.weight_reference = weight_reference()
    return ctx


@pytest.fixture
def projection_context(import_context, monkeypatch):
    """外部资料为有效合成事实，投影解析和消费者均使用真实代码。"""
    ctx = import_context
    ctx.profile_row = snapshot(
        "profile",
        MEMBER,
        profile_payload(),
        {
            "family_profile_source": ctx.family_reference,
            "weight_measurement_source": ctx.weight_reference,
        },
    )
    ctx.rule_row = snapshot("rules", RULE, rule_payload(), {})
    ctx.rows.append(ctx.profile_row)
    monkeypatch.setattr(HealthQualityRepository, "rules", AsyncMock(return_value=ctx.rule_row))
    return ctx


def import_body():
    """仅合成批准投影和明确本人来源，不包含真实健康资料。"""
    now = datetime.now(UTC)
    return {
        "version": 1,
        "source_ref": "synthetic-professional-source",
        "source_version": "synthetic-1",
        "authority_ref": "synthetic-authority",
        "attested_by": "synthetic-professional",
        "attested_at": (now - timedelta(minutes=1)).isoformat(),
        "valid_until": (now + timedelta(days=1)).isoformat(),
        "status": "confirmed",
        "payload": profile_payload("60.000000"),
        "family_profile_source": {"family_id": FAMILY, "source_member_id": SOURCE_MEMBER, "confirmed_version": 1},
        "weight_measurement_source": {"record_id": RECORD, "version": 1},
    }


def profile_payload(weight="60"):
    """安全编码明确无；年龄、性别和活动仅代表合成计算域。"""
    return {
        "population_code": "synthetic_adult",
        "age_years": 30,
        "sex_code": "synthetic_sex",
        "activity_code": "synthetic_activity",
        "weight_kg": weight,
        **{
            key: {"state": "none", "codes": []}
            for key in (
                "conditions",
                "allergies",
                "intolerances",
                "avoidances",
                "doctor_requirements",
                "preferences",
            )
        },
    }


def rule_payload():
    """批准合成公式30+5×体重，其他营养范围独立固定。"""
    bounds = {
        code: {"minimum": str(low), "maximum": str(high)}
        for code, low, high in [
            ("energy_kcal", 250, 350),
            ("protein_g", 20, 40),
            ("fat_g", 4, 8),
            ("carbohydrate_g", 50, 70),
            ("sodium_mg", 100, 200),
        ]
    }
    return {
        "allowed_population_codes": ["synthetic_adult"],
        "minimum_age_years": 18,
        "maximum_age_years": 130,
        "supported_condition_sets": [[]],
        "ingredient_classifications": [
            {
                "food_id": FOOD,
                "food_hash": "a" * 64,
                "complete": True,
            }
        ],
        "daily_bounds": bounds,
        "personal_targets": [
            {
                "population_code": "synthetic_adult",
                "sex_code": "synthetic_sex",
                "condition_codes": [],
                "intercept_kcal": "30",
                "weight_kg_coefficient": "5",
                "height_cm_coefficient": "0",
                "age_years_coefficient": "0",
                "activity_factors": {"synthetic_activity": "1"},
                "nutrient_ranges": {
                    code: {
                        "minimum_per_energy": "1" if code == "energy_kcal" else "0",
                        "maximum_per_energy": "1" if code == "energy_kcal" else "0",
                        "minimum_constant": "0" if code == "energy_kcal" else value["minimum"],
                        "maximum_constant": "0" if code == "energy_kcal" else value["maximum"],
                    }
                    for code, value in bounds.items()
                },
            }
        ],
    }


def independent_digest(value):
    """按公开规范独立序列化，不复用受测摘要函数。"""
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def family_reference():
    """本人确认原始字段的来源摘要独立构造。"""
    coordinates = {"family_id": FAMILY, "source_member_id": SOURCE_MEMBER, "confirmed_version": 1}
    return coordinates | {"source_hash": independent_digest({**coordinates, "profile": {}})}


def weight_reference():
    """明确实测60kg的完整服务器来源依据。"""
    reference = {
        "family_id": FAMILY,
        "source_member_id": SOURCE_MEMBER,
        "record_id": RECORD,
        "version": 1,
        "unit": "kg",
        "measured_at": "2020-01-01T00:00:00Z",
        "source": "synthetic-scale",
    }
    return reference | {"source_hash": independent_digest({**reference, "kind": "weight", "weight_kg": "60.0"})}


def snapshot(kind, key, payload, extra_proof):
    """构造合法外部资料，动态来源事实在调用时由仓储重验。"""
    now = datetime.now(UTC)
    proof = {
        "version": 1,
        "attested_at": (now - timedelta(minutes=1)).isoformat(),
        "valid_until": (now + timedelta(days=1)).isoformat(),
        **deepcopy(extra_proof),
    }
    return SimpleNamespace(
        id=f"synthetic-{kind}",
        version=1,
        payload=payload,
        attestation=proof,
        content_hash=projection_digest(kind, key, 1, payload, proof),
        revoked_at=None,
        attested_at=datetime.fromisoformat(proof["attested_at"]).replace(tzinfo=None),
        valid_until=datetime.fromisoformat(proof["valid_until"]).replace(tzinfo=None),
    )


def target_selection():
    """当前明确专业版本，客户端不提供身体参数。"""
    return PersonalTargetSelection(rule_code=RULE, rule_version=1, profile_version=1)

"""真实浏览器导入专业档案、选定旧体重与失效回跳的隔离合成验收。"""

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text

from test.integration.services.test_health_family_profile_http import linked_self
from test.integration.services.test_health_quality_http import action, proof
from test.integration.services.test_health_vision_http import (
    ROOT,
    cleanup_test_knowledge_resources,  # noqa: F401
    cleanup_test_sandboxes,  # noqa: F401
    ensure_live_api_schema,  # noqa: F401
    health_http,  # noqa: F401
)
from test.integration.services.test_health_weight_http import add_weight
from test.integration.services.test_health_weight_targets_http import (
    publish_weight_rules,
    save_weight_plan,
    selected_profile_body,
    target_read,
)
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    FamilyArchive,
    FamilyAudit,
    FamilyMeasurement,
    FamilyMember,
    FamilyProfileRevision,
    OperationLog,
    User,
)
from yuxi.storage.postgres.models_health import (
    HealthFamilyProfileLink,
    HealthMealPlanAdoption,
    HealthProcessingConsent,
    HealthProfessionalReview,
    HealthProfileSnapshot,
)
from yuxi.utils.auth_utils import AuthUtils

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true", reason="仅在隔离合成槽位运行"),
    pytest.mark.skipif(not os.getenv("HEALTH_PROFILE_IMPORT_UI_CONTROL_DIR"), reason="需要真实浏览器控制目录"),
]


async def test_browser_explicit_weight_import_target_and_invalidated_plan(health_http):  # noqa: F811
    """不配置模型；浏览器写入、持久化与目标均由独立 HTTP/PG oracle 核对。"""
    client, users = health_http
    owner, reviewer = users[2], users[1]
    control = Path(os.environ["HEALTH_PROFILE_IMPORT_UI_CONTROL_DIR"])
    control.mkdir(parents=True, exist_ok=True)
    assert not any(control.iterdir()), "使用本轮新建的空控制目录"
    async with pg_manager.get_async_session_context() as session:
        assert await session.scalar(text("SELECT current_database()")) == "health_consultation_e2e"
        account = await session.scalar(select(User).where(User.uid == owner["uid"]))
        password = "SyntheticProfileUI-20261009!"
        account.password_hash = AuthUtils.hash_password(password)
        # 本槽位没有超管时登录页会显示初始化；只预置本次新建的合成账号。
        account.role = "superadmin"
    configuration = await read_configuration(client, owner["headers"])
    assert str(client.base_url).rstrip("/") == "http://localhost:5050"
    member, source = await linked_self(client, owner["headers"])
    case = SimpleNamespace(
        client=client,
        sessions=pg_manager.get_async_session_context,
        identities={"admin": owner["headers"], "self": owner["headers"], "other": reviewer["headers"]},
        headers=owner["headers"],
        member=member,
        source=source,
        measurement_path=f"/api/family/{source['family_id']}/members/{source['source_member_id']}/measurements",
    )
    try:
        old = await add_weight(case, measured_at=datetime.now(UTC) - timedelta(days=65))
        latest = await add_weight(case, value=90)
        rules = await publish_weight_rules(case)
        body = selected_profile_body(source, old)
        write_control(
            control / "context.json",
            {
                "username": owner["uid"],
                "password": password,
                "member_id": member,
                "family_id": source["family_id"],
                "source_member_id": source["source_member_id"],
                "selected_record": old,
                "unselected_record": latest,
                "professional_body": body,
                "rule_code": rules["rule_code"],
            },
        )
        await signal(control, "imported.json")
        await assert_profile(case, old, 1, "60", "330", rules)
        saved = await save_weight_plan(case, rules)
        adopted = await approve_real_reviewer(case, saved, reviewer["uid"])
        original = await client.get(f"{ROOT}/meal-plans/{saved['plan']}", headers=case.headers)
        assert original.status_code == 200
        write_control(control / "plan-ready.json", {"plan_id": saved["plan"], "review_id": saved["review"]})

        await signal(control, "corrected.json")
        # 必须在任何会惰性核对来源的GET之前读取更正事务写出的失效事实。
        async with case.sessions() as session:
            changed = await session.get(FamilyMeasurement, old["id"])
            assert changed.version == 2 and changed.values == {"weight": 61.0}
            assert changed.source == old["source"] and changed.measured_at.isoformat() == old[
                "measured_at"
            ].removesuffix("Z")
            review = await session.get(HealthProfessionalReview, saved["review"])
            adoption = await session.get(HealthMealPlanAdoption, adopted["adoption_id"])
            assert review.status == adoption.status == "invalidated"
            assert review.invalidation_reason == adoption.reason == "weight_measurement_changed"
        read = await client.get(f"{ROOT}/members/{member}/external-profile-versions/current", headers=case.headers)
        assert read.status_code == 200 and read.json()["status"] == "not_ready"
        assert read.json()["reason"] == "weight_measurement_source_changed" and read.json()["payload"] is None
        after = await client.get(f"{ROOT}/meal-plans/{saved['plan']}", headers=case.headers)
        assert after.status_code == 200 and after.json() == original.json()
        new_record = {**old, "version": 2, "values": {"weight": 61.0}}
        write_control(
            control / "correction-verified.json",
            {
                "professional_body": selected_profile_body(source, new_record, version=2, weight="61"),
            },
        )
        await signal(control, "done.json")
        await assert_profile(case, new_record, 2, "61", "335", rules)
        async with case.sessions() as session:
            review = await session.get(HealthProfessionalReview, saved["review"])
            adoption = await session.get(HealthMealPlanAdoption, adopted["adoption_id"])
            assert review.status == adoption.status == "invalidated"
            assert (
                await session.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.uid == owner["uid"]))
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(HealthProcessingConsent)
                    .where(HealthProcessingConsent.member_id == member)
                )
                == 0
            )
        assert await read_configuration(client, owner["headers"]) == configuration
        write_control(
            control / "verified.json",
            {
                "status": "passed",
                "professional_versions": [1, 2],
                "weight_versions": [1, 2],
                "targets_kcal": ["330", "335"],
                "old_nonlatest_record_selected": True,
                "historical_plan_unchanged": True,
                "review_and_adoption": "invalidated",
                "no_model_approval_or_consent_or_run": True,
            },
        )
    finally:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                delete(OperationLog).where(
                    OperationLog.user_id.in_(select(User.id).where(User.uid.in_([item["uid"] for item in users])))
                )
            )
            await session.execute(delete(HealthFamilyProfileLink).where(HealthFamilyProfileLink.member_id == member))
            await session.execute(delete(FamilyAudit).where(FamilyAudit.family_id == source["family_id"]))
            for model in (FamilyMeasurement, FamilyProfileRevision):
                await session.execute(delete(model).where(model.member_id == source["source_member_id"]))
            await session.execute(delete(FamilyMember).where(FamilyMember.family_id == source["family_id"]))
            await session.execute(
                delete(FamilyArchive).where(
                    FamilyArchive.id == source["family_id"], FamilyArchive.owner_uid == owner["uid"]
                )
            )


async def assert_profile(case, record, version, weight, energy, rules):
    """PG中只存在明确专业版本，选择不是最新测量，目标使用手算330/335。"""
    async with case.sessions() as session:
        rows = list(
            (
                await session.scalars(
                    select(HealthProfileSnapshot)
                    .where(HealthProfileSnapshot.member_id == case.member)
                    .order_by(HealthProfileSnapshot.version)
                )
            ).all()
        )
        assert [row.version for row in rows] == list(range(1, version + 1))
        current = rows[-1]
        assert current.payload["weight_kg"] == weight
        selection = current.attestation["weight_measurement_source"]
        assert selection["record_id"] == record["id"] and selection["version"] == record["version"]
        measurement = await session.get(FamilyMeasurement, record["id"])
        assert measurement.version == record["version"] and Decimal(str(measurement.values["weight"])) == Decimal(
            weight
        )
        facts = {
            "family_id": case.source["family_id"],
            "source_member_id": case.source["source_member_id"],
            "record_id": record["id"],
            "version": record["version"],
            "kind": "weight",
            "weight_kg": str(Decimal(str(measurement.values["weight"]))),
            "unit": "kg",
            "measured_at": record["measured_at"],
            "source": measurement.source,
        }
        assert (
            selection["source_hash"]
            == hashlib.sha256(
                json.dumps(facts, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
            ).hexdigest()
        )
        formal = await session.get(FamilyMember, case.source["source_member_id"])
        expected = {
            "family_id": case.source["family_id"],
            "source_member_id": formal.id,
            "confirmed_version": formal.confirmed_version,
        }
        assert {key: current.attestation["family_profile_source"][key] for key in expected} == expected
    result = await target_read(case, rules, profile_version=version)
    assert result["status"] == "ready" and Decimal(result["energy_kcal"]) == Decimal(energy)
    assert result["inputs"]["weight_kg"] == weight


async def approve_real_reviewer(case, saved, reviewer_uid):
    """仅初始化合成餐单状态，专业人员和成员授权经真实现有接口。"""
    response = await case.client.put(
        f"{ROOT}/members/{case.member}/grants",
        headers=case.headers,
        json={"actor_uid": reviewer_uid, "scopes": ["profile_view", "professional_review"]},
    )
    assert response.status_code == 200, response.text
    response = await case.client.post(
        f"{ROOT}/professional-reviewers",
        headers=case.headers,
        json={**proof(), "status": "qualified", "reviewer_uid": reviewer_uid},
    )
    assert response.status_code == 201, response.text
    await action(case.client, case.headers, saved["review"], "submit", 1)
    await action(case.client, case.identities["other"], saved["review"], "approve", 2)
    response = await case.client.post(
        f"{ROOT}/meal-plans/{saved['plan']}/adopt",
        headers=case.headers,
        json={
            "client_request_id": str(uuid4()),
            "version": 1,
            "review_id": saved["review"],
            "profile_versions": {case.member: 1},
        },
    )
    assert response.status_code == 201 and response.json()["status"] == "active", response.text
    return response.json()


async def read_configuration(client, headers):
    """只读配置，所有模型审批维持关闭。"""
    response = await client.get(f"{ROOT}/configuration", headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert not result["policy_version"]
    assert not any(value.get("available", False) for value in result.values() if isinstance(value, dict))
    # 食品数量由本夹具发布菜谱而增加；它不是模型审批配置。
    return {key: value for key, value in result.items() if key != "food_count"}


async def signal(control, name):
    """等待独立浏览器信号；信号不替代业务oracle。"""
    try:
        async with asyncio.timeout(1200):
            while not (control / name).exists():
                if (control / "failure.json").exists():
                    pytest.fail("真实浏览器验收失败，保留本地报告")
                await asyncio.sleep(1)
    except TimeoutError:
        pytest.fail(f"浏览器未完成阶段{name}")


def write_control(path, payload):
    """原子发布合成控制数据；不在测试日志输出凭据。"""
    temp = path.with_suffix(".new")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)

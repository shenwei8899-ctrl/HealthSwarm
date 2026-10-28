"""HTTP 建立真实资料，PG 与本进程回源验证来源失效；商城组成由独立用例覆盖。"""

from copy import deepcopy
from datetime import date, timedelta
import hashlib
import hmac
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, update

from test.integration.services.test_health_nutrition_foundation_http import source_document
from test.integration.services.test_health_quality_http import setup_quality
from test.integration.services.test_health_vision_http import ROOT, health_http  # noqa: F401
from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.services import daily_arrangement_service
from yuxi.services.health_commerce_service import SourceProof, validate_source_proof
from yuxi.services.health_quality_checks import external_projection
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.miniapp_planning_source import submitted_profile_projection
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import FamilyArchive, FamilyAudit, FamilyMember, User
from yuxi.storage.postgres.models_health import HealthDailyArrangement, HealthQualityCheck
from yuxi.storage.postgres.models_knowledge import KnowledgeFile
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(autouse=True)
def isolate_commerce_composition(monkeypatch):
    """本组验证真实营养来源；商品组成与远端商城由独立采购用例验证。"""
    monkeypatch.setattr(daily_arrangement_service, "validate_daily_purchase_composition", AsyncMock())


async def validate_commerce(proof):
    """调用当前回源用例，保留真实账号、授权、质量与 PostgreSQL 校验。"""
    return await validate_source_proof(SourceProof.model_validate(proof))


@pytest_asyncio.fixture
async def created_families(health_http):  # noqa: F811
    """在公共账号清理前按本例准确ID清理新增家庭与安排。"""
    ids = []
    try:
        yield ids
    finally:
        if ids:
            async with pg_manager.get_async_session_context() as session:
                await session.execute(delete(HealthDailyArrangement).where(HealthDailyArrangement.family_id.in_(ids)))
                await session.execute(delete(FamilyAudit).where(FamilyAudit.family_id.in_(ids)))
                await session.execute(delete(FamilyMember).where(FamilyMember.family_id.in_(ids)))
                await session.execute(delete(FamilyArchive).where(FamilyArchive.id.in_(ids)))


async def daily_record(client, users, current, created_families):
    """使用真实质量接口生成保存收据，覆盖旧版未储存check_id的安排。"""
    uid, rid, fid, source_id = users[0]["uid"], str(uuid4()), str(uuid4()), str(uuid4())
    created_families.append(fid)
    day, version, attempt = date(2026, 10, 19), 3, 2
    save_key = uuid5(NAMESPACE_URL, f"daily-save:{rid}:{version}:{attempt}")
    check_key = str(uuid5(NAMESPACE_URL, f"health-initial-generation:{uid}:{save_key}"))
    checked = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/quality-checks",
        headers=users[0]["headers"],
        json={"client_request_id": check_key, "version": 1, "rule_code": current["rules"]["rule_code"]},
    )
    assert checked.status_code == 201, checked.text
    snapshot = {
        "status": "ready",
        "id": rid,
        "version": version,
        "date": day.isoformat(),
        "saved": True,
        "plan_id": current["plan"],
        "plan_version": 1,
        "quality_check_id": checked.json()["check_id"],
        "validation": {"status": "passed", "sources": current["check"]["sources"]},
        "analysis": {"source": "agent", "text": "合成工程说明"},
        "meals": [
            {"type": meal, "members": [source_id], "dishes": [], "memberNotes": []}
            for meal in ("breakfast", "lunch", "dinner")
        ],
    }
    async with pg_manager.get_async_session_context() as session:
        session.add(FamilyArchive(id=fid, owner_uid=uid, name="合成来源验证家庭"))
        await session.flush()
        session.add(
            FamilyMember(
                id=source_id,
                family_id=fid,
                subject_uid=uid,
                name="合成成员",
                relationship="self",
                profile={},
            )
        )
        session.add(
            HealthDailyArrangement(
                id=rid,
                actor_uid=uid,
                family_id=fid,
                plan_date=day,
                version=version,
                status="ready",
                request_id=str(uuid4()),
                selection={
                    "initial": {
                        "kind": "family",
                        "plan_date": day.isoformat(),
                        "rule_code": current["rules"]["rule_code"],
                        "rule_version": 1,
                        "profile_versions": {current["member"]: 1},
                        "meals": [
                            {"meal_type": meal, "participant_ids": [current["member"]]}
                            for meal in ("breakfast", "lunch", "dinner")
                        ],
                    },
                    "attempt": attempt,
                    "retry_limit": attempt + 2,
                },
                sources={
                    "members": {current["member"]: {"id": source_id, "version": 1}},
                    "account_ref": "synthetic-account",
                },
                snapshot=snapshot,
            )
        )
    return {"id": rid, "fid": fid, "day": day, "snapshot": snapshot, "check_id": checked.json()["check_id"]}


async def request_daily(client, headers, saved, entry):
    """同一真实安排分别经过读取、幂等首开、恢复及单餐详情。"""
    path = f"/api/family/{saved['fid']}/daily-arrangements"
    if entry == "start":
        key = str(uuid4())
        return await client.post(
            path,
            headers={**headers, "Idempotency-Key": key},
            json={"client_request_id": key, "date": saved["day"].isoformat()},
        )
    if entry == "resume":
        return await client.post(path + f"/{saved['day']}/resume", headers=headers)
    if entry == "meal":
        return await client.get(
            path + f"/{saved['day']}/meals/lunch",
            headers=headers,
            params={"arrangement_id": saved["id"], "version": saved["snapshot"]["version"]},
        )
    return await client.get(path + f"/{saved['day']}", headers=headers)


async def commerce_proof(uid, saved):
    """独立组装商城传回的签名协议，不借用被测签名函数产生期望值。"""
    secret = os.getenv("HEALTH_COMMERCE_SOURCE_SECRET", "")
    assert len(secret) >= 32, "真实 API 与测试进程须配置同一隔离测试来源密钥"

    def canonical(value):
        """协议固定为 UTF-8 排序的紧凑 JSON。"""
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthDailyArrangement, saved["id"])
        meal = next(item for item in row.snapshot["meals"] if item["type"] == "lunch")
        source = {
            "kind": "daily_arrangement",
            "uid": uid,
            "family_id": saved["fid"],
            "date": saved["day"].isoformat(),
            "arrangement_id": row.id,
            "meal": meal["type"],
            "meal_hash": hashlib.sha256(
                canonical({key: meal[key] for key in ("type", "members", "dishes", "memberNotes")}).encode()
            ).hexdigest(),
        }
    raw = canonical(source)
    return {"payload": raw, "signature": hmac.new(secret.encode(), raw.encode(), "sha256").hexdigest()}


@pytest.mark.parametrize("target", ["food", "recipe", "rules"])
@pytest.mark.parametrize("change", ["hash", "deleted"])
async def test_daily_commerce_rechecks_original_sources_without_user_auth(
    health_http,  # noqa: F811
    created_families,
    target,
    change,
):
    """商城凭签名回源，原件改变或删除即拒绝旧采购包且历史不变。"""
    client, users = health_http
    async with source_document(users[2]["uid"]) as (_, file_id, reference):
        current = await setup_quality(client, users, source_refs={target: reference})
        saved = await daily_record(client, users, current, created_families)
        proof = await commerce_proof(users[0]["uid"], saved)
        assert await validate_commerce(proof) == {"available": True}
        async with pg_manager.get_async_session_context() as session:
            query = delete(KnowledgeFile).where(KnowledgeFile.file_id == file_id)
            if change == "hash":
                query = update(KnowledgeFile).where(KnowledgeFile.file_id == file_id).values(content_hash="c" * 64)
            await session.execute(query)
        with pytest.raises(HealthVisionError) as invalidated:
            await validate_commerce(proof)
        assert invalidated.value.status == 410 and invalidated.value.code == "source_invalidated"
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(HealthDailyArrangement, saved["id"])
            assert row.status == "ready" and row.version == saved["snapshot"]["version"]
            assert row.snapshot == saved["snapshot"]


@pytest.mark.parametrize(
    "change",
    [
        "not_ready",
        "plan",
        "plan_version",
        "check",
        "member",
        "meal",
        "deleted",
        "locked",
        "department",
    ],
)
async def test_daily_commerce_rejects_changed_binding_and_account(health_http, created_families, change):  # noqa: F811
    """签名正确仍须匹配当前 ready 的单餐内容、原收据、成员和有效账号。"""
    client, users = health_http
    current = await setup_quality(client, users)
    saved = await daily_record(client, users, current, created_families)
    proof = await commerce_proof(users[0]["uid"], saved)
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthDailyArrangement, saved["id"])
        if change == "not_ready":
            row.status = "generating"
        elif change in {"plan", "plan_version", "meal"}:
            snapshot = deepcopy(row.snapshot)
            if change == "plan":
                snapshot["plan_id"] = str(uuid4())
            elif change == "plan_version":
                snapshot["plan_version"] += 1
            else:
                snapshot["meals"][1]["dishes"] = [{"name": "变更后的合成菜"}]
            row.snapshot = snapshot
        elif change == "check":
            row.snapshot = {**row.snapshot, "quality_check_id": str(uuid4())}
        elif change == "member":
            source_id = next(iter(row.sources["members"].values()))["id"]
            member = await session.get(FamilyMember, source_id)
            member.version += 1
        else:
            user = await session.scalar(select(User).where(User.uid == users[0]["uid"]))
            if change == "deleted":
                user.is_deleted = 1
            elif change == "locked":
                user.login_locked_until = utc_now_naive() + timedelta(hours=1)
            else:
                user.department_id = None
        expected = deepcopy(row.snapshot)
        expected_status, expected_version = row.status, row.version
    with pytest.raises(HealthVisionError) as invalidated:
        await validate_commerce(proof)
    assert invalidated.value.status == 410 and invalidated.value.code == "source_invalidated"
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthDailyArrangement, saved["id"])
        assert row.snapshot == expected and row.status == expected_status and row.version == expected_version


async def test_daily_commerce_rejects_bad_signature_unknown_kind_and_wrong_arrangement(health_http, created_families):  # noqa: F811
    """签名与安排身份是独立边界，正确签名不能绑定另一安排。"""
    client, users = health_http
    current = await setup_quality(client, users)
    saved = await daily_record(client, users, current, created_families)
    proof = await commerce_proof(users[0]["uid"], saved)
    bad = {**proof, "signature": "0" * 64}
    with pytest.raises(HealthVisionError) as invalid:
        await validate_commerce(bad)
    assert invalid.value.status == 403 and invalid.value.code == "source_proof_invalid"
    for field, value, expected in [("kind", "unknown", 403), ("arrangement_id", str(uuid4()), 410)]:
        source = {**json.loads(proof["payload"]), field: value}
        raw = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        modified = {
            "payload": raw,
            "signature": hmac.new(
                os.environ["HEALTH_COMMERCE_SOURCE_SECRET"].encode(), raw.encode(), "sha256"
            ).hexdigest(),
        }
        with pytest.raises(HealthVisionError) as invalid:
            await validate_commerce(modified)
        assert invalid.value.status == expected


@pytest.mark.parametrize("change", ["version", "attempt"])
async def test_same_meal_purchase_survives_unrelated_arrangement_progress(health_http, created_families, change):  # noqa: F811
    """新版协议绑定单餐内容；其它餐的版本或尝试推进不撤销未改动的原采购依据。"""
    client, users = health_http
    current = await setup_quality(client, users)
    saved = await daily_record(client, users, current, created_families)
    proof = await commerce_proof(users[0]["uid"], saved)
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthDailyArrangement, saved["id"])
        if change == "version":
            row.version += 1
            row.snapshot = {**row.snapshot, "version": row.version}
        else:
            row.selection = {**row.selection, "attempt": row.selection["attempt"] + 1}
    assert await validate_commerce(proof) == {"available": True}


async def test_legacy_adoption_commerce_proof_keeps_current_source_validation(health_http, monkeypatch):  # noqa: F811
    """真实业务生成采用后，原无kind凭据与显式adoption凭据均能回源且撤回后拒绝。"""
    from datetime import UTC, datetime

    from test.integration.services.test_health_plan_adoption_http import adopt_body, approve
    from yuxi.services import health_commerce_service
    from yuxi.services.health_purchase_types import PurchaseSelection
    from yuxi.storage.postgres.models_health import HealthMealPlan, RecipeVersion

    client, users = health_http
    current = await setup_quality(client, users)
    await approve(client, users, current)
    adopted = await client.post(
        f"{ROOT}/meal-plans/{current['plan']}/adopt", headers=users[0]["headers"], json=adopt_body(current)
    )
    assert adopted.status_code == 201, adopted.text
    adoption = adopted.json()
    selected = PurchaseSelection(
        adoption_id=adoption["adoption_id"], adoption_version=1, plan_version=1, inventory_confirmed=True
    )
    async with pg_manager.get_async_session_context() as session:
        plan = await session.get(HealthMealPlan, current["plan"])
        recipe = await session.get(RecipeVersion, plan.spec["meals"][0]["dishes"][0]["recipe_version_id"])
        food = recipe.ingredients[0]["food"]
    monkeypatch.setenv("HEALTH_COMMERCE_URL", "http://localhost:1")
    monkeypatch.setenv("HEALTH_COMMERCE_CLIENT_ID", "synthetic-legacy-test")
    monkeypatch.setenv("HEALTH_COMMERCE_CLIENT_SECRET", "synthetic-legacy-client-signature-only")
    monkeypatch.setenv("HEALTH_COMMERCE_SOURCE_SECRET", "synthetic-legacy-source-signature-only")
    mappings = [
        {
            "food_id": food["id"],
            "cooking_state": food["cooking_state"],
            "ingredient_code": "synthetic-ingredient",
            "purchase_grams_per_edible_gram": "1",
            "source_ref": "synthetic:commerce-compatibility",
            "approved_by": "synthetic-engineering-fixture",
            "valid_until": (datetime.now(UTC) + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        }
    ]
    monkeypatch.setenv("HEALTH_COMMERCE_INGREDIENT_MAP", json.dumps(mappings))
    captured = []

    async def mall(_base, _path, *, payload=None, key=None):
        """商城仅作外部端口，专业采用和回源数据均来自真实PG。"""
        if payload is None:
            return {"catalog_version": "synthetic"}
        captured.append((deepcopy(payload), key))
        return {"package_sn": "synthetic-legacy-package"}

    monkeypatch.setattr(health_commerce_service, "mall_request", mall)
    requirements = await health_commerce_service.purchase_requirements(users[0]["uid"], current["member"], selected)

    def legacy_hash(value):
        """独立复现发布前的协议散列，不调用被测签名或指纹 helper。"""
        return hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    legacy_source = {
        "uid": users[0]["uid"],
        "member_id": current["member"],
        "selection": selected.model_dump(mode="json"),
        "source_hash": requirements["source_hash"],
        "mapping_hash": legacy_hash(mappings),
    }
    legacy_task = "adoption-" + legacy_hash({"source": legacy_source, "catalog": "synthetic"})
    for _ in range(2):
        await health_commerce_service.export_adopted_purchase(users[0]["uid"], current["member"], selected)
    assert captured[0] == captured[1]
    for package, key in captured:
        assert package["agent_task_id"] == legacy_task and key == legacy_task[-64:]
        assert json.loads(package["agent_source_proof"]["payload"]) == legacy_source
    legacy_proof = captured[0][0]["agent_source_proof"]
    raw = json.dumps({**legacy_source, "kind": "adoption"}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    typed_proof = {
        "payload": raw,
        "signature": hmac.new(os.environ["HEALTH_COMMERCE_SOURCE_SECRET"].encode(), raw.encode(), "sha256").hexdigest(),
    }
    for proof in (legacy_proof, typed_proof):
        assert await validate_source_proof(SourceProof.model_validate(proof)) == {"available": True}
    response = await client.post(
        f"{ROOT}/meal-plan-adoptions/{adoption['adoption_id']}/withdraw",
        headers=users[0]["headers"],
        json={"client_request_id": str(uuid4()), "version": 1, "reason": "合成兼容性验收撤回"},
    )
    assert response.status_code == 200, response.text
    for proof in (legacy_proof, typed_proof):
        with pytest.raises(HealthVisionError) as invalidated:
            await validate_source_proof(SourceProof.model_validate(proof))
        assert invalidated.value.status == 410


@pytest.mark.parametrize("target", ["food", "recipe", "rules"])
async def test_ready_daily_rejects_changed_sources_on_all_entry_points(health_http, created_families, target):  # noqa: F811
    """原件变更后读取标记 stale，详情和恢复拒绝；历史快照保持原值。"""
    client, users = health_http
    async with source_document(users[2]["uid"]) as (_, fid, reference):
        current = await setup_quality(client, users, source_refs={target: reference})
        saved = await daily_record(client, users, current, created_families)
        for entry in ("read", "start", "resume", "meal"):
            response = await request_daily(client, users[0]["headers"], saved, entry)
            assert response.status_code == 200, response.text
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                update(KnowledgeFile).where(KnowledgeFile.file_id == fid).values(content_hash="b" * 64)
            )
        response = await request_daily(client, users[0]["headers"], saved, "read")
        assert response.status_code == 200 and response.json()["status"] == "stale", response.text
        response = await request_daily(client, users[0]["headers"], saved, "meal")
        assert response.status_code == 409 and response.json()["code"] == "daily_version_changed", response.text
        response = await request_daily(client, users[0]["headers"], saved, "resume")
        assert response.status_code == 410 and response.json()["code"] == "source_invalidated", response.text
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(HealthDailyArrangement, saved["id"])
            assert row.status == "ready" and row.version == saved["snapshot"]["version"]
            assert row.snapshot == saved["snapshot"]


@pytest.mark.parametrize("mismatch", ["missing", "actor", "plan", "version", "rule", "not_passed"])
async def test_ready_daily_requires_original_matching_check(health_http, created_families, mismatch):  # noqa: F811
    """没有原收据或绑定对象不符时，不能借其他检查继续声明passed。"""
    client, users = health_http
    current = await setup_quality(client, users)
    saved = await daily_record(client, users, current, created_families)
    async with pg_manager.get_async_session_context() as session:
        check = await session.get(HealthQualityCheck, saved["check_id"])
        if mismatch == "missing":
            row = await session.get(HealthDailyArrangement, saved["id"])
            row.snapshot = {**row.snapshot, "quality_check_id": str(uuid4())}
        elif mismatch == "actor":
            check.actor_uid = users[1]["uid"]
        elif mismatch == "plan":
            row = await session.get(HealthDailyArrangement, saved["id"])
            row.snapshot = {**row.snapshot, "plan_id": str(uuid4())}
        elif mismatch == "version":
            check.plan_version += 1
        elif mismatch == "rule":
            check.rule_code = "synthetic-other-rule"
        else:
            snapshot = deepcopy(check.snapshot)
            snapshot["safety_check"]["status"] = "unknown"
            check.snapshot = snapshot
    response = await request_daily(client, users[0]["headers"], saved, "read")
    assert response.status_code == 200 and response.json()["status"] == "stale", response.text
    response = await request_daily(client, users[0]["headers"], saved, "resume")
    assert response.status_code == 410 and response.json()["code"] == "source_invalidated", response.text


@pytest.mark.parametrize("change", ["hash", "deleted"])
async def test_miniapp_coding_rule_rechecks_its_own_original(health_http, created_families, monkeypatch, change):  # noqa: F811
    """编码规则与消费规则不同，原件失效不能被另一有效目录掩盖。"""
    client, users = health_http
    current = await setup_quality(client, users)
    uid, fid, mid = users[0]["uid"], str(uuid4()), str(uuid4())
    created_families.append(fid)
    async with source_document(users[2]["uid"]) as (_, file_id, reference):
        coding = deepcopy(current["rules"])
        coding["rule_code"] = "synthetic-coding-" + uuid4().hex
        coding["source_ref"] = reference
        coding["payload"]["miniapp_profile_codes"] = {"population_age_ranges": {"18:130": "synthetic_adult"}}
        published = await client.post(f"{ROOT}/approved-quality-rules", headers=users[2]["headers"], json=coding)
        assert published.status_code == 201, published.text
        monkeypatch.setenv("HEALTH_DAILY_RULE_CODE", coding["rule_code"])
        async with pg_manager.get_async_session_context() as session:
            session.add(FamilyArchive(id=fid, owner_uid=uid, name="合成编码来源家庭"))
            await session.flush()
            session.add(
                FamilyMember(
                    id=mid,
                    family_id=fid,
                    subject_uid=uid,
                    name="合成自述成员",
                    relationship="self",
                    profile={
                        "birth_date": "1990-01-01",
                        "dietary_details": dict.fromkeys(
                            ["healthStatus", "allergyStatus", "intoleranceStatus", "avoidanceStatus", "doctorStatus"],
                            "none",
                        ),
                    },
                )
            )
        link = SimpleNamespace(family_id=fid, source_member_id=mid, actor_uid=uid, source_kind="miniapp_reported")
        async with pg_manager.get_async_session_context() as session:
            assert (await submitted_profile_projection(session, link))["status"] == "ready"
        async with pg_manager.get_async_session_context() as session:
            query = delete(KnowledgeFile).where(KnowledgeFile.file_id == file_id)
            if change == "hash":
                query = update(KnowledgeFile).where(KnowledgeFile.file_id == file_id).values(content_hash="b" * 64)
            await session.execute(query)
        async with pg_manager.get_async_session_context() as session:
            consumer = await HealthQualityRepository(session).rules(current["rules"]["rule_code"])
            assert external_projection(consumer, "rules", current["rules"]["rule_code"])["status"] == "ready"
            projection = await submitted_profile_projection(session, link)
            assert projection["status"] == "not_ready"
            assert projection["reason"] == "profile_coding_rules_unavailable"
            assert projection["payload"] is None and projection["attestation"] is None

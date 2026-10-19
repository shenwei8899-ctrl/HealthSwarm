"""真实HTTP/PG核对每日安排和小程序编码来源失效；仅使用合成工程资料。"""

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
from yuxi.services.health_commerce_service import SourceProof, daily_source_proof, validate_source_proof
from yuxi.services.health_quality_checks import external_projection
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.miniapp_planning_source import submitted_profile_projection
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import FamilyArchive, FamilyAudit, FamilyMember, User
from yuxi.storage.postgres.models_health import HealthDailyArrangement, HealthQualityCheck
from yuxi.storage.postgres.models_knowledge import KnowledgeFile
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


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
        "validation": {"status": "passed", "sources": current["check"]["sources"]},
        "analysis": {"source": "agent", "text": "合成工程说明"},
        "meals": [{"type": meal, "dishes": []} for meal in ("breakfast", "lunch", "dinner")],
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
            "kind": "daily",
            "uid": uid,
            "family_id": saved["fid"],
            "plan_date": saved["day"].isoformat(),
            "arrangement_id": row.id,
            "arrangement_version": row.version,
            "attempt": row.selection["attempt"],
            "plan_id": row.snapshot["plan_id"],
            "plan_version": row.snapshot["plan_version"],
            "check_id": saved["check_id"],
            "sources_hash": hashlib.sha256(canonical(row.sources).encode()).hexdigest(),
            "meal_type": meal["type"],
            "meal_hash": hashlib.sha256(
                canonical({key: value for key, value in meal.items() if key != "purchase"}).encode()
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
        response = await client.post(f"{ROOT}/commerce/source-validation", json=proof)
        assert response.status_code == 200 and response.json() == {"available": True}, response.text
        async with pg_manager.get_async_session_context() as session:
            query = delete(KnowledgeFile).where(KnowledgeFile.file_id == file_id)
            if change == "hash":
                query = update(KnowledgeFile).where(KnowledgeFile.file_id == file_id).values(content_hash="c" * 64)
            await session.execute(query)
        response = await client.post(f"{ROOT}/commerce/source-validation", json=proof)
        assert response.status_code == 410 and response.json()["code"] == "source_invalidated", response.text
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(HealthDailyArrangement, saved["id"])
            assert row.status == "ready" and row.version == saved["snapshot"]["version"]
            assert row.snapshot == saved["snapshot"]


@pytest.mark.parametrize(
    "change",
    [
        "version",
        "attempt",
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
    """签名正确仍须匹配当前ready版本、原收据、成员和有效账号。"""
    client, users = health_http
    current = await setup_quality(client, users)
    saved = await daily_record(client, users, current, created_families)
    proof = await commerce_proof(users[0]["uid"], saved)
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthDailyArrangement, saved["id"])
        if change == "version":
            row.version += 1
        elif change == "attempt":
            row.selection = {**row.selection, "attempt": row.selection["attempt"] + 1}
        elif change == "not_ready":
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
            check = await session.get(HealthQualityCheck, saved["check_id"])
            check.request_id = str(uuid4())
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
    response = await client.post(f"{ROOT}/commerce/source-validation", json=proof)
    assert response.status_code == 410 and response.json()["code"] == "source_invalidated", response.text
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthDailyArrangement, saved["id"])
        assert row.snapshot == expected and row.status == expected_status and row.version == expected_version


async def test_daily_commerce_rejects_bad_signature_unknown_kind_and_wrong_check(health_http, created_families):  # noqa: F811
    """服务签名是独立认证边界；正确签名也不能把另一检查嫁接到原安排。"""
    client, users = health_http
    current = await setup_quality(client, users)
    saved = await daily_record(client, users, current, created_families)
    proof = await commerce_proof(users[0]["uid"], saved)
    bad = {**proof, "signature": "0" * 64}
    response = await client.post(f"{ROOT}/commerce/source-validation", json=bad)
    assert response.status_code == 403 and response.json()["code"] == "source_proof_invalid", response.text
    for field, value, expected in [("kind", "unknown", 403), ("check_id", str(uuid4()), 410)]:
        source = {**json.loads(proof["payload"]), field: value}
        raw = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        modified = {
            "payload": raw,
            "signature": hmac.new(
                os.environ["HEALTH_COMMERCE_SOURCE_SECRET"].encode(), raw.encode(), "sha256"
            ).hexdigest(),
        }
        response = await client.post(f"{ROOT}/commerce/source-validation", json=modified)
        assert response.status_code == expected, response.text


async def test_changed_meal_republishes_all_packages_with_stable_current_proofs(
    health_http,  # noqa: F811
    created_families,
    monkeypatch,
):
    """真实PG完成恢复；调整一餐后其他两餐保留菜品但重发当前版本采购包。"""
    client, users = health_http
    current = await setup_quality(client, users)
    saved = await daily_record(client, users, current, created_families)
    uid = users[0]["uid"]
    monkeypatch.setenv("HEALTH_COMMERCE_SOURCE_SECRET", "synthetic-daily-source-signature-test-only")
    monkeypatch.delenv("HEALTH_COMMERCE_INGREDIENT_MAP", raising=False)
    previous = deepcopy(saved["snapshot"])
    for meal in previous["meals"]:
        meal.update(memberNotes=[], purchase={"package_sn": "old-" + meal["type"], "package_version": 1, "items": []})
    meals = [{key: value for key, value in meal.items() if key != "purchase"} for meal in previous["meals"]]
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthDailyArrangement, saved["id"])
        row.status, row.snapshot = "generating", previous
        row.selection = {
            **row.selection,
            "initial": {**row.selection["initial"], "change_meal": "lunch"},
            "agent_result": {
                "payload": {
                    "preview_id": str(uuid4()),
                    "explanation": "合成调整完成说明",
                    "sources": current["check"]["sources"],
                },
                "task_key": str(uuid4()),
                "run_id": str(uuid4()),
            },
        }
    plan = {"plan_id": current["plan"], "version": 1, "quality_check": {"check_id": saved["check_id"]}}
    monkeypatch.setattr(daily_arrangement_service, "save_initial_plan", AsyncMock(return_value=plan))
    monkeypatch.setattr(daily_arrangement_service, "meal_views", lambda *_: deepcopy(meals))
    monkeypatch.setattr(daily_arrangement_service, "ingredient_requirements", lambda *_: [])
    monkeypatch.setattr(daily_arrangement_service, "current_catalog", AsyncMock(return_value={"version": "synthetic"}))
    monkeypatch.setattr(daily_arrangement_service, "match_requirements", lambda *_: True)
    monkeypatch.setattr(daily_arrangement_service, "packages_in_stock", lambda *_: True)
    published = []

    async def publish(_method, _path, payload, *, request_id):
        """只隔离商城端口，保存调用正文供最终PG状态交叉验证。"""
        published.append(deepcopy(payload))
        with pytest.raises(HealthVisionError) as unavailable:
            await validate_source_proof(SourceProof.model_validate(payload["agent_source_proof"]))
        assert unavailable.value.status == 410
        return {
            "status": "available",
            "trade_validation_status": "passed",
            "package_sn": "new-" + request_id,
            "package_version": 1,
            "items": [],
        }

    monkeypatch.setattr(daily_arrangement_service, "commerce_request", publish)
    result = await daily_arrangement_service.resume_daily_arrangement(uid, saved["fid"], saved["day"])
    assert result["status"] == "ready" and len(published) == 3
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthDailyArrangement, saved["id"])
        assert row.snapshot == result and row.status == "ready"
        sources = deepcopy(row.sources)
    for meal, payload, old in zip(result["meals"], published, previous["meals"], strict=True):
        proof = payload["agent_source_proof"]
        source = json.loads(proof["payload"])
        expected_key = str(uuid5(NAMESPACE_URL, f"daily-purchase-source-v1:{saved['id']}:3:2:{meal['type']}"))
        assert payload["agent_task_id"] == expected_key and meal["purchase"]["package_sn"] == "new-" + expected_key
        assert source["kind"] == "daily" and source["arrangement_version"] == 3 and source["attempt"] == 2
        assert source["meal_type"] == meal["type"] and source["check_id"] == saved["check_id"]
        assert meal["purchase"]["package_sn"] != "old-" + meal["type"]
        assert meal["dishes"] == old["dishes"] and meal["memberNotes"] == old["memberNotes"]
        assert proof == daily_source_proof(uid, saved["fid"], saved["day"], saved["id"], 3, 2, sources, plan, meal)
        assert await validate_source_proof(SourceProof.model_validate(proof)) == {"available": True}
    monkeypatch.delenv("HEALTH_COMMERCE_SOURCE_SECRET")
    with pytest.raises(HealthVisionError) as missing_key:
        await validate_source_proof(SourceProof.model_validate(published[0]["agent_source_proof"]))
    assert missing_key.value.status == 503
    with pytest.raises(HealthVisionError) as missing_export_key:
        daily_source_proof(uid, saved["fid"], saved["day"], saved["id"], 3, 2, sources, plan, result["meals"][0])
    assert missing_export_key.value.status == 503


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
    """原件变更后所有旧ready入口均拒绝，历史快照和状态保持原值。"""
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
        for entry in ("read", "start", "resume", "meal"):
            response = await request_daily(client, users[0]["headers"], saved, entry)
            assert response.status_code == 410, (entry, response.text)
            assert response.json()["code"] == "source_invalidated"
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
            check.request_id = str(uuid4())
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
    assert response.status_code == 410, response.text
    assert response.json()["code"] == "source_invalidated"


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
        link = SimpleNamespace(family_id=fid, source_member_id=mid, actor_uid=uid)
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


@pytest.mark.parametrize("late_failure", ["agent_result", "ingredient_stock", "package_stock"])
async def test_late_failure_preserves_ready_receipt(health_http, created_families, monkeypatch, late_failure):  # noqa: F811
    """直接调用本进程service控制延迟点，真实PG赢家ready不能被旧失败递增attempt。"""
    from yuxi.services import agent_request_service

    client, users = health_http
    monkeypatch.setenv("HEALTH_COMMERCE_SOURCE_SECRET", "synthetic-daily-source-signature-test-only")
    current = await setup_quality(client, users)
    saved = await daily_record(client, users, current, created_families)
    uid = users[0]["uid"]
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthDailyArrangement, saved["id"])
        row.status = "generating"
        if late_failure != "agent_result":
            row.selection = {
                **row.selection,
                "agent_result": {
                    "payload": {"preview_id": str(uuid4())},
                    "task_key": str(uuid4()),
                    "run_id": str(uuid4()),
                },
            }

    async def winner_ready():
        """在落后调用继续前提交另一个resume的已完成状态。"""
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(HealthDailyArrangement, saved["id"])
            row.status = "ready"

    if late_failure == "agent_result":
        monkeypatch.setattr(
            daily_arrangement_service,
            "create_health_task_entry",
            AsyncMock(
                return_value=SimpleNamespace(
                    entry_status="ready", agent_slug="health-meal-planner", thread_id=str(uuid4())
                )
            ),
        )
        monkeypatch.setattr(agent_request_service, "submit_agent_request", AsyncMock())

        async def failed_result(*_):
            """本进程任务端口返回失败前，让另一个调用完成。"""
            await winner_ready()
            return SimpleNamespace(result=SimpleNamespace(model_dump=lambda **_: {"result_type": "failed"}))

        monkeypatch.setattr(daily_arrangement_service, "read_health_task", failed_result)
    else:
        monkeypatch.setattr(
            daily_arrangement_service,
            "save_initial_plan",
            AsyncMock(
                return_value={
                    "plan_id": current["plan"],
                    "version": 1,
                    "quality_check": {"check_id": saved["check_id"]},
                }
            ),
        )
        monkeypatch.setattr(daily_arrangement_service, "meal_views", lambda *_: deepcopy(saved["snapshot"]["meals"]))
        monkeypatch.setattr(daily_arrangement_service, "ingredient_requirements", lambda *_: [])
        monkeypatch.setattr(
            daily_arrangement_service, "match_requirements", lambda *_: late_failure != "ingredient_stock"
        )
        monkeypatch.setattr(daily_arrangement_service, "packages_in_stock", lambda *_: False)
        monkeypatch.setattr(
            daily_arrangement_service,
            "commerce_request",
            AsyncMock(
                return_value={
                    "status": "available",
                    "trade_validation_status": "passed",
                    "package_sn": "synthetic-package",
                    "package_version": 1,
                    "items": [],
                }
            ),
        )
        calls = 0

        async def changed_catalog():
            """分别在原料或最终采购包库存检查前提交并发赢家。"""
            nonlocal calls
            calls += 1
            if late_failure == "ingredient_stock" or calls == 2:
                await winner_ready()
            return {"version": "synthetic-catalog"}

        monkeypatch.setattr(daily_arrangement_service, "current_catalog", changed_catalog)

    result = await daily_arrangement_service.resume_daily_arrangement(uid, saved["fid"], saved["day"])
    assert result == saved["snapshot"]
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(HealthDailyArrangement, saved["id"])
        assert row.status == "ready" and row.selection["attempt"] == 2
        assert row.snapshot == saved["snapshot"]
    response = await request_daily(client, users[0]["headers"], saved, "read")
    assert response.status_code == 200 and response.json() == saved["snapshot"], response.text

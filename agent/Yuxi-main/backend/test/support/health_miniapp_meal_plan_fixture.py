"""小程序普通餐单的隔离合成资料、独立PG事实与精确清理。"""

import argparse
import asyncio
import hashlib
import json
import os
import secrets
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import delete, func, or_, select, text

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    AgentRunRequest,
    Department,
    FamilyArchive,
    FamilyAudit,
    FamilyMeasurement,
    FamilyMember as SourceMember,
    FamilyProfileRevision,
    OperationLog,
    User,
)
from yuxi.storage.postgres.models_health import (
    DietLog,
    FamilyMember as HealthMember,
    FoodRecord,
    HealthFamilyProfileLink,
    HealthGrant,
    HealthMealPlan,
    HealthMealPlanAdoption,
    HealthMealPlanPreview,
    HealthMealPlanRevision,
    HealthProcessingConsent,
    PortionReference,
    RecipeVersion,
)
from yuxi.utils.auth_utils import AuthUtils

CONTROL = Path("/app/test/.tmp/miniapp-meal-plan-20261010")
ROOT = "/api/health/v1"
HTTP_BASE = "http://localhost:5050"


async def main():
    """阶段命令只输出无凭据摘要，验收正文写入忽略目录。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create", "read", "verify-browser", "cleanup"))
    args = parser.parse_args()
    await require_isolated_slot()
    try:
        if args.command == "create":
            state = await create_fixture()
            summary = {"created": True, "fixture_id": state["fixture_id"], "control_directory": str(CONTROL)}
        else:
            state = load_state()
            if args.command == "cleanup":
                summary = await cleanup_fixture(state)
            else:
                filename = "browser-pg-verification.json" if args.command == "verify-browser" else "pg-current.json"
                save_json(filename, {"passed": False, "status": "running"})
                facts = await read_facts(state)
                if args.command == "verify-browser":
                    try:
                        verify_browser(state, facts)
                    except Exception:
                        save_json(filename, {"passed": False, "status": "failed", "facts": facts})
                        raise
                save_json(filename, {"passed": args.command == "verify-browser", "facts": facts})
                summary = {
                    "passed": args.command == "verify-browser",
                    "plan_count": len(facts["plans"]),
                    "versions": [row["version"] for row in facts["plans"]],
                    "report": str(CONTROL / filename),
                }
        print(json.dumps(summary))
    finally:
        await pg_manager.close()


async def require_isolated_slot():
    """标记、实际数据库、Schema与真实ready共同限定隔离边界。"""
    if os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true":
        raise RuntimeError("仅允许明确的隔离健康验收槽位")
    pg_manager.initialize()
    async with pg_manager.get_async_session_context() as session:
        if await session.scalar(text("SELECT current_database()")) != "health_consultation_e2e":
            raise RuntimeError("禁止操作主数据库")
    await pg_manager.require_current_schema()
    async with httpx.AsyncClient(base_url=HTTP_BASE, timeout=10) as client:
        require_status(await client.get("/api/system/ready"), 200)


async def create_fixture():
    """本人关系和发布数据经过正式HTTP；不配置模型或创建用途同意。"""
    CONTROL.mkdir(parents=True, exist_ok=True)
    if (CONTROL / "metadata.json").exists() and not load_state().get("cleaned"):
        raise RuntimeError("已有未清理夹具，请先读取或完成清理")
    fixture_id = uuid4().hex[:12]
    state = {"fixture_id": fixture_id, "accounts": {}, "members": {}, "recipes": {}, "cleaned": False}
    credentials = {}
    async with pg_manager.get_async_session_context() as session:
        configuration = await session.scalar(text("SELECT value FROM config_options WHERE key='health_vision_opts'"))
        assert isinstance(configuration, dict) and not any(configuration.values()), "不能使用已配置的健康模型槽位"
        assert not await session.scalar(
            select(AgentRun.id).where(
                or_(
                    AgentRun.status.not_in(("completed", "failed", "cancelled", "interrupted")),
                    AgentRun.worker_id.is_not(None),
                    AgentRun.lease_expires_at.is_not(None),
                    AgentRun.runtime_cleanup_pending.is_(True),
                )
            )
        ), "共享隔离槽尚有执行owner"
        state["configuration_provider_baseline"] = await configuration_provider_hash(session)
        department = Department(name="mini_meal_" + fixture_id)
        session.add(department)
        await session.flush()
        state["department_id"] = department.id
        for name, role in (("owner", "user"), ("browser", "user"), ("admin", "admin")):
            uid = "pytest_health_mini_meal_" + fixture_id + "_" + name
            password = secrets.token_urlsafe(24)
            user = User(
                uid=uid,
                username=uid,
                role=role,
                password_hash=AuthUtils.hash_password(password),
                department_id=department.id,
            )
            session.add(user)
            await session.flush()
            state["accounts"][name] = {"uid": uid, "user_id": user.id}
            credentials[name] = {"identifier": uid, "password": password}
    save_json("metadata.json", state)
    save_json("credentials.secret.json", credentials)
    try:
        async with httpx.AsyncClient(base_url=HTTP_BASE, timeout=20) as client:
            for name in ("owner", "browser"):
                headers = await login_headers(client, name)
                family = await client.post("/api/family", headers=headers, json={"name": "合成餐单本人家庭 " + name})
                require_status(family, 200)
                source_id = next(row["id"] for row in family.json()["members"] if row["is_self"])
                state["members"][name] = {"family_id": family.json()["id"], "source_member_id": source_id}
                save_json("metadata.json", state)
                member = await client.post(
                    ROOT + "/members",
                    headers=headers,
                    json={"display_name": "合成餐单本人 " + name, "relationship_label": "本人", "authorized": True},
                )
                require_status(member, 201)
                member_id = member.json()["id"]
                state["members"][name]["health_member_id"] = member_id
                save_json("metadata.json", state)
                require_status(
                    await client.post(
                        f"{ROOT}/members/{member_id}/family-profile-link",
                        headers=headers,
                        json={
                            "family_id": family.json()["id"],
                            "source_member_id": source_id,
                            "confirmed_identity": True,
                        },
                    ),
                    200,
                )
                require_status(
                    await client.put(
                        f"{ROOT}/members/{member_id}/grants",
                        headers=headers,
                        json={
                            "actor_uid": state["accounts"][name]["uid"],
                            "scopes": ["profile_view", "profile_edit", "diet_edit"],
                        },
                    ),
                    200,
                )
            admin = await login_headers(client, "admin")
            for key, label, energy in (
                ("breakfast", "合成燕麦早餐", "100"),
                ("lunch", "合成豆腐午餐", "200"),
                ("dinner", "合成南瓜晚餐", "300"),
                ("replacement", "合成菠菜换菜", "400"),
            ):
                state["recipes"][key] = await publish_recipe(client, admin, fixture_id, label, energy)
                save_json("metadata.json", state)
        state["browser_spec"] = plan_spec(state)
        state["browser_swap"] = {
            "meal_type": "lunch",
            "dish_index": 0,
            "replacement": {"recipe_version_id": state["recipes"]["replacement"]["recipe_id"], "grams": "100"},
        }
        state["before"] = await read_facts(state)
        verify_business_boundary(state, state["before"])
        assert state["before"]["plans"] == state["before"]["previews"] == []
        save_json("metadata.json", state)
        return state
    except Exception:
        await cleanup_fixture(state)
        raise


async def read_facts(state):
    """独立连接读取不可变修订、正式记录与执行行，避免只相信HTTP成功。"""
    uids = [row["uid"] for row in state["accounts"].values()]
    member_ids = [row["health_member_id"] for row in state["members"].values() if "health_member_id" in row]
    async with pg_manager.get_async_session_context() as session:
        plans = list(
            (
                await session.scalars(
                    select(HealthMealPlan).where(HealthMealPlan.actor_uid.in_(uids)).order_by(HealthMealPlan.id)
                )
            ).all()
        )
        revisions = list(
            (
                await session.scalars(
                    select(HealthMealPlanRevision)
                    .where(HealthMealPlanRevision.actor_uid.in_(uids))
                    .order_by(HealthMealPlanRevision.plan_id, HealthMealPlanRevision.version)
                )
            ).all()
        )
        counts = {}
        for key, model, condition in (
            ("agent_runs", AgentRun, AgentRun.uid.in_(uids)),
            ("agent_requests", AgentRunRequest, AgentRunRequest.uid.in_(uids)),
            ("diet_logs", DietLog, DietLog.member_id.in_(member_ids)),
            ("adoptions", HealthMealPlanAdoption, HealthMealPlanAdoption.actor_uid.in_(uids)),
            ("consents", HealthProcessingConsent, HealthProcessingConsent.member_id.in_(member_ids)),
        ):
            counts[key] = int(await session.scalar(select(func.count()).select_from(model).where(condition)) or 0)
        return {
            "database": await session.scalar(text("SELECT current_database()")),
            "configuration_provider_hash": await configuration_provider_hash(session),
            **counts,
            "accounts": [
                {"uid": row.uid, "role": row.role}
                for row in (await session.scalars(select(User).where(User.uid.in_(uids)).order_by(User.uid))).all()
            ],
            "links": [
                {
                    "member_id": row.member_id,
                    "family_id": row.family_id,
                    "source_member_id": row.source_member_id,
                    "actor_uid": row.actor_uid,
                }
                for row in (
                    await session.scalars(
                        select(HealthFamilyProfileLink)
                        .where(HealthFamilyProfileLink.member_id.in_(member_ids))
                        .order_by(HealthFamilyProfileLink.member_id)
                    )
                ).all()
            ],
            "grants": [
                {
                    "member_id": row.member_id,
                    "actor_uid": row.actor_uid,
                    "scopes": sorted(row.scopes),
                    "revoked": row.revoked_at is not None,
                }
                for row in (
                    await session.scalars(
                        select(HealthGrant)
                        .where(HealthGrant.member_id.in_(member_ids))
                        .order_by(HealthGrant.member_id, HealthGrant.actor_uid)
                    )
                ).all()
            ],
            "previews": [
                {
                    "preview_id": row.id,
                    "actor_uid": row.actor_uid,
                    "member_id": row.member_id,
                    "run_id": row.run_id,
                    "spec": row.spec,
                    "snapshot": row.snapshot,
                }
                for row in (
                    await session.scalars(
                        select(HealthMealPlanPreview)
                        .where(HealthMealPlanPreview.actor_uid.in_(uids))
                        .order_by(HealthMealPlanPreview.id)
                    )
                ).all()
            ],
            "plans": [
                {
                    "plan_id": row.id,
                    "actor_uid": row.actor_uid,
                    "member_id": row.member_id,
                    "version": row.version,
                    "spec": row.spec,
                    "snapshot": row.snapshot,
                    "revisions": [
                        {
                            "version": revision.version,
                            "request_id": revision.request_id,
                            "reason": revision.reason,
                            "spec": revision.spec,
                            "snapshot": revision.snapshot,
                        }
                        for revision in revisions
                        if revision.plan_id == row.id
                    ],
                }
                for row in plans
            ],
        }


def verify_browser(state, facts):
    """固定手算输入反证浏览器保存和换菜，历史不能覆盖当前版。"""
    verify_business_boundary(state, facts)
    for key in ("accounts", "links", "grants"):
        assert facts[key] == state["before"][key], f"浏览器餐单不得改变{key}"
    uid = state["accounts"]["browser"]["uid"]
    plans = [row for row in facts["plans"] if row["actor_uid"] == uid]
    assert len(plans) == 1, "浏览器仅明确保存一份草稿"
    plan = plans[0]
    assert plan["member_id"] == state["members"]["browser"]["health_member_id"]
    assert plan["version"] == 2 and [row["version"] for row in plan["revisions"]] == [1, 2]
    assert len({row["request_id"] for row in plan["revisions"]}) == 2
    assert_plan_snapshot(state, plan["revisions"][0]["snapshot"], swapped=False)
    assert_plan_snapshot(state, plan["revisions"][1]["snapshot"], swapped=True)
    assert plan["snapshot"] == plan["revisions"][1]["snapshot"]
    assert plan["revisions"][0]["spec"] == state["browser_spec"]
    expected_spec = deepcopy(state["browser_spec"])
    selected_meal = next(
        row for row in expected_spec["meals"] if row["meal_type"] == state["browser_swap"]["meal_type"]
    )
    selected_meal["dishes"][state["browser_swap"]["dish_index"]] = {
        **state["browser_swap"]["replacement"],
        "portion_reference_id": None,
        "portion_count": None,
    }
    assert plan["spec"] == plan["revisions"][1]["spec"] == expected_spec


def verify_business_boundary(state, facts):
    """普通草稿不得产生实际摄入、采用、模型请求或用途同意。"""
    assert facts["database"] == "health_consultation_e2e"
    assert facts["configuration_provider_hash"] == state["configuration_provider_baseline"]
    for key in ("agent_runs", "agent_requests", "diet_logs", "adoptions", "consents"):
        assert facts[key] == 0, f"普通餐单不得创建{key}"
    assert all(row["run_id"] is None for row in facts["previews"])


def assert_plan_snapshot(state, snapshot, *, swapped):
    """菜名、原料与手算数值来自显式合成输入，保留未知值和零值。"""
    assert snapshot["status"] == "draft" and snapshot["personalized"] is False
    assert snapshot["adoption_available"] is False and snapshot["purchase_available"] is False
    assert snapshot["personal_target"] is None and snapshot["professional_review"] == "not_reviewed"
    assert snapshot["plan_date"] == "2026-10-10"
    assert [row["meal_type"] for row in snapshot["meals"]] == ["breakfast", "lunch", "dinner"]
    for meal, key, grams in zip(
        snapshot["meals"], ("breakfast", "replacement" if swapped else "lunch", "dinner"), (50, 100, 150)
    ):
        recipe = state["recipes"][key]
        assert len(meal["dishes"]) == 1
        dish = meal["dishes"][0]
        assert dish["name"] == recipe["name"] and dish["recipe_version_id"] == recipe["recipe_id"]
        assert float(dish["planned_grams"]) == grams
        assert dish["ingredients"][0]["food_id"] == recipe["food_id"]
        assert float(dish["ingredients"][0]["planned_grams"]) == grams
        assert dish["nutrition"]["sodium_mg"] is None and dish["nutrition"]["fat_g"] == "0.00"
    assert snapshot["nutrition"]["totals"] == {
        "energy_kcal": "900.00" if swapped else "700.00",
        "protein_g": "30.00",
        "fat_g": "0.00",
        "carbohydrate_g": "60.00",
        "sodium_mg": None,
    }
    assert snapshot["nutrition"]["complete"] is False


async def cleanup_fixture(state):
    """仅删除本轮UUID和账号所属行，未预期依赖使事务回滚并保留证据。"""
    facts = await read_facts(state)
    verify_business_boundary(state, facts)
    save_json("before-cleanup.json", facts)
    uids = [row["uid"] for row in state["accounts"].values()]
    async with pg_manager.get_async_session_context() as session:
        assert await session.scalar(text("SELECT current_database()")) == "health_consultation_e2e"
        members = list((await session.scalars(select(HealthMember.id).where(HealthMember.owner_uid.in_(uids)))).all())
        families = list(
            (await session.scalars(select(FamilyArchive.id).where(FamilyArchive.owner_uid.in_(uids)))).all()
        )
        sources = list(
            (await session.scalars(select(SourceMember.id).where(SourceMember.family_id.in_(families)))).all()
        )
        targets = {
            ("users", "uid"): uids,
            ("users", "id"): [str(row["user_id"]) for row in state["accounts"].values()],
            ("departments", "id"): [str(state["department_id"])],
            ("family_member", "id"): members,
            ("family_archives", "id"): families,
            ("family_members", "id"): sources,
        }
        for model in (HealthMealPlanRevision, HealthMealPlan, HealthMealPlanPreview):
            await session.execute(delete(model).where(model.actor_uid.in_(uids)))
        for model in (HealthFamilyProfileLink, HealthGrant):
            await session.execute(delete(model).where(model.member_id.in_(members)))
        await session.execute(delete(HealthMember).where(HealthMember.id.in_(members)))
        await session.execute(delete(FamilyAudit).where(FamilyAudit.family_id.in_(families)))
        await session.execute(delete(FamilyMeasurement).where(FamilyMeasurement.member_id.in_(sources)))
        await session.execute(delete(FamilyProfileRevision).where(FamilyProfileRevision.member_id.in_(sources)))
        await session.execute(delete(SourceMember).where(SourceMember.id.in_(sources)))
        await session.execute(delete(FamilyArchive).where(FamilyArchive.id.in_(families)))
        for model in (PortionReference, RecipeVersion, FoodRecord):
            ids = list((await session.scalars(select(model.id).where(model.published_by.in_(uids)))).all())
            targets[(model.__tablename__, "id")] = ids
            await session.execute(delete(model).where(model.id.in_(ids)))
        await session.execute(
            delete(OperationLog).where(OperationLog.user_id.in_([row["user_id"] for row in state["accounts"].values()]))
        )
        await session.execute(delete(User).where(User.uid.in_(uids)))
        await session.execute(delete(Department).where(Department.id == state["department_id"]))
        remaining = await remaining_owned_references(session, targets)
        assert not remaining, f"发现未覆盖的本轮反向外键：{remaining}"
        assert await configuration_provider_hash(session) == state["configuration_provider_baseline"]
    final = await read_facts(state)
    assert all(final[key] == [] for key in ("accounts", "links", "grants", "previews", "plans"))
    verify_business_boundary(state, final)
    state["cleaned"] = True
    save_json("metadata.json", state)
    save_json("cleanup-verification.json", {"passed": True, "remaining_owned_references": [], "facts": final})
    (CONTROL / "credentials.secret.json").unlink(missing_ok=True)
    return {"cleaned": True, "fixture_id": state["fixture_id"], "remaining_owned_rows": 0}


async def publish_recipe(client, admin, fixture_id, name, energy):
    """发布一份配方和适用份量，数值只用于合成手算oracle。"""
    source = {
        "source": "synthetic-miniapp-meal",
        "license": "synthetic-test-only",
        "edition": "synthetic",
        "dataset_version": fixture_id,
    }
    food = await client.post(
        ROOT + "/foods",
        headers=admin,
        json={
            **source,
            "record_code": str(uuid4()),
            "name": name + "原料",
            "cooking_state": "合成",
            "nutrients": {
                "energy_kcal": energy,
                "protein_g": "10",
                "fat_g": "0",
                "carbohydrate_g": "20",
                "sodium_mg": None,
            },
        },
    )
    require_status(food, 201)
    recipe = await client.post(
        ROOT + "/recipes",
        headers=admin,
        json={
            **source,
            "record_code": str(uuid4()),
            "name": name,
            "cooking_state": "合成",
            "yield_grams": "200",
            "ingredients": [{"food_id": food.json()["id"], "grams": "200", "role": "food"}],
        },
    )
    require_status(recipe, 201)
    portion = await client.post(
        ROOT + "/portion-references",
        headers=admin,
        json={
            **source,
            "recipe_version_id": recipe.json()["id"],
            "unit_label": "合成份",
            "grams_per_unit": "100",
            "applicable_scope": "仅此合成菜谱",
        },
    )
    require_status(portion, 201)
    return {
        "recipe_id": recipe.json()["id"],
        "food_id": food.json()["id"],
        "portion_id": portion.json()["id"],
        "name": name,
    }


def plan_spec(state):
    """固定三餐50、100、150克只用于验收，不是个人营养目标。"""
    return {
        "plan_date": "2026-10-10",
        "meals": [
            {
                "meal_type": key,
                "dishes": [
                    {
                        "recipe_version_id": state["recipes"][key]["recipe_id"],
                        "grams": str(grams),
                        "portion_reference_id": None,
                        "portion_count": None,
                    }
                ],
            }
            for key, grams in zip(("breakfast", "lunch", "dinner"), (50, 100, 150))
        ],
    }


async def login_headers(client, name):
    """凭据只从本轮私有文件读取，Token不进入状态文件或标准输出。"""
    credentials = json.loads((CONTROL / "credentials.secret.json").read_text())[name]
    response = await client.post(
        "/api/auth/token", data={"username": credentials["identifier"], "password": credentials["password"]}
    )
    require_status(response, 200)
    return {"Authorization": "Bearer " + response.json()["access_token"]}


async def configuration_provider_hash(session):
    """全表摘要证明配置和供应商不变，不导出任何供应商原始值。"""
    rows = []
    for table, order in (("config_options", "id"), ("model_providers", "provider_id")):
        rows.append(
            (await session.execute(text(f"SELECT row_to_json(t)::text FROM {table} t ORDER BY {order}")))
            .scalars()
            .all()
        )
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


async def remaining_owned_references(session, targets):
    """枚举实际PG全表反向外键，不能因ORM清单遗漏而宣称清理成功。"""
    constraints = (
        await session.execute(
            text("""
        SELECT ns.nspname, src.relname, sa.attname, dst.relname, da.attname
        FROM pg_constraint c
        JOIN pg_class src ON src.oid=c.conrelid
        JOIN pg_namespace ns ON ns.oid=src.relnamespace
        JOIN pg_class dst ON dst.oid=c.confrelid
        JOIN LATERAL unnest(c.conkey, c.confkey) AS cols(source_number, target_number) ON true
        JOIN pg_attribute sa ON sa.attrelid=src.oid AND sa.attnum=cols.source_number
        JOIN pg_attribute da ON da.attrelid=dst.oid AND da.attnum=cols.target_number
        WHERE c.contype='f' AND ns.nspname='public'
    """)
        )
    ).all()
    remaining = []
    quote = session.bind.dialect.identifier_preparer.quote
    for schema, table, column, target, target_column in constraints:
        values = targets.get((target, target_column))
        if not values:
            continue
        count = await session.scalar(
            text(
                f"SELECT count(*) FROM {quote(schema)}.{quote(table)} "
                f"WHERE {quote(column)}::text = ANY(CAST(:owned AS text[]))"
            ),
            {"owned": [str(value) for value in values]},
        )
        if count:
            remaining.append({"table": table, "column": column, "rows": int(count)})
    return remaining


def load_state():
    """只读取固定忽略目录的本轮夹具元数据。"""
    return json.loads((CONTROL / "metadata.json").read_text())


def save_json(name, value):
    """私有输出写入项目忽略目录，凭据不进入日志。"""
    path = CONTROL / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    path.chmod(0o600)


def require_status(response, expected):
    """错误只包含路径和状态，避免认证正文出现在诊断。"""
    if response.status_code != expected:
        raise AssertionError(
            f"{response.request.method} {response.request.url.path}: expected {expected}, got {response.status_code}"
        )


if __name__ == "__main__":
    asyncio.run(main())

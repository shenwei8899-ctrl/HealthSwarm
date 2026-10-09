"""隔离槽位的小程序普通账号、HTTP业务资料和独立PG验收。"""

import argparse
import asyncio
import hashlib
import json
import os
import secrets
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import delete, func, select, text

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
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
    FamilyMember as HealthMember,
    HealthFamilyProfileLink,
    HealthGrant,
    HealthProcessingConsent,
)
from yuxi.utils.auth_utils import AuthUtils

HTTP_BASE = "http://localhost:5050"
STATE_ROOT = Path("/app/test/.tmp/miniapp-account-20261009")
SYNTHETIC_PROFILE = {
    "sex": "female",
    "birth_date": "1990-01-01",
    "height_cm": 165,
    "activity_level": "light",
    "goal": "合成验收：保持规律饮食",
    "allergens": [],
    "avoidances": [],
}


async def main():
    """先验证隔离数据库，再执行明确的夹具阶段；从不输出凭据。"""
    global STATE_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create", "read", "verify", "cleanup"))
    parser.add_argument("--fixture", choices=("main", "writer-check"), default="main")
    parser.add_argument("--browser-linked", action="store_true", help="明确验收另一合成账号经浏览器创建的本人关联")
    args = parser.parse_args()
    if args.fixture == "writer-check":
        STATE_ROOT = STATE_ROOT / "writer-check"
    if os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true":
        raise RuntimeError("仅允许明确的隔离健康验收槽位")
    pg_manager.initialize()
    try:
        async with pg_manager.get_async_session_context() as session:
            if await session.scalar(text("SELECT current_database()")) != "health_consultation_e2e":
                raise RuntimeError("禁止在非隔离数据库创建或清理验收数据")
        await pg_manager.require_current_schema()
        STATE_ROOT.mkdir(parents=True, exist_ok=True)
        if args.command == "create":
            state = await create_fixture()
            print(json.dumps({"created": True, "state_directory": str(STATE_ROOT), "fixture_id": state["fixture_id"]}))
        else:
            state = json.loads((STATE_ROOT / "metadata.json").read_text())
            if args.command == "cleanup":
                print(json.dumps(await cleanup_fixture(state)))
            else:
                facts = await read_facts(state)
                if args.command == "verify":
                    verify_facts(state, facts, browser_linked=args.browser_linked)
                    filename = "pg-browser-verification.json" if args.browser_linked else "pg-verification.json"
                    save_json(filename, {"passed": True, "facts": facts})
                else:
                    save_json("pg-current.json", facts)
                print(json.dumps({"passed": args.command == "verify", "facts": facts}, ensure_ascii=False))
    finally:
        await pg_manager.close()


async def create_fixture():
    """仅插入合成账号和部门；家庭、档案确认与健康对象经过真实HTTP。"""
    if (STATE_ROOT / "metadata.json").exists():
        previous = json.loads((STATE_ROOT / "metadata.json").read_text())
        if not previous.get("cleaned"):
            raise RuntimeError("已有尚未清理的夹具，请读取或完成清理后再创建")
    fixture_id = uuid4().hex[:12]
    state = {"fixture_id": fixture_id, "accounts": {}, "families": {}, "health_members": {}, "cleaned": False}
    configuration_before = (await read_facts(state))["model_configuration_hash"]
    credentials = {}
    async with pg_manager.get_async_session_context() as session:
        department = Department(name="miniapp_test_" + fixture_id)
        session.add(department)
        await session.flush()
        state["department_id"] = department.id
        for name in ("owner", "other", "no_department"):
            uid = "miniapp_test_" + fixture_id + "_" + name
            password = secrets.token_urlsafe(24)
            user = User(
                uid=uid,
                username=uid,
                role="user",
                password_hash=AuthUtils.hash_password(password),
                department_id=department.id if name != "no_department" else None,
            )
            session.add(user)
            await session.flush()
            state["accounts"][name] = {"uid": uid, "user_id": user.id}
            credentials[name] = {"identifier": uid, "password": password}
    save_json("metadata.json", state)
    save_json("credentials.secret.json", credentials)
    try:
        async with httpx.AsyncClient(base_url=HTTP_BASE, timeout=20) as client:
            for name in ("owner", "other"):
                login = await client.post(
                    "/api/auth/token",
                    data={"username": credentials[name]["identifier"], "password": credentials[name]["password"]},
                )
                require_status(login, 200)
                assert login.json()["role"] == "user"
                headers = {"Authorization": "Bearer " + login.json()["access_token"]}
                family = await client.post("/api/family", headers=headers, json={"name": "小程序合成家庭 " + name})
                require_status(family, 200)
                source_id = next(member["id"] for member in family.json()["members"] if member["is_self"])
                state["families"][name] = {"family_id": family.json()["id"], "source_member_id": source_id}
                save_json("metadata.json", state)
                profile_path = f"/api/family/{family.json()['id']}/members/{source_id}"
                update = await client.put(
                    profile_path, headers=headers, json={"expected_version": 1, "profile": SYNTHETIC_PROFILE}
                )
                require_status(update, 200)
                assert update.json()["version"] == 2
                confirm = await client.post(profile_path + "/confirm", headers=headers, json={"expected_version": 2})
                require_status(confirm, 200)
                for key in ("primary", "conflict") if name == "owner" else ("foreign",):
                    member = await client.post(
                        "/api/health/v1/members",
                        headers=headers,
                        json={
                            "display_name": "小程序合成本人成员 " + key,
                            "relationship_label": "本人",
                            "authorized": True,
                        },
                    )
                    require_status(member, 201)
                    state["health_members"][key] = member.json()["id"]
                    save_json("metadata.json", state)
        state["baseline"] = await read_facts(state)
        assert state["baseline"]["model_configuration_hash"] == configuration_before
        assert state["baseline"]["links"] == []
        assert state["baseline"]["consents"] == []
        save_json("metadata.json", state)
        return state
    except Exception:
        await cleanup_fixture(state)
        raise


async def read_facts(state):
    """每次独立连接回读明确归属的关联、权限、同意与原模型配置摘要。"""
    uids = [account["uid"] for account in state["accounts"].values()]
    async with pg_manager.get_async_session_context() as session:
        members = list(
            (
                await session.scalars(
                    select(HealthMember).where(HealthMember.owner_uid.in_(uids)).order_by(HealthMember.id)
                )
            ).all()
        )
        member_ids = [member.id for member in members]
        links = list(
            (
                await session.scalars(
                    select(HealthFamilyProfileLink)
                    .where(HealthFamilyProfileLink.member_id.in_(member_ids))
                    .order_by(HealthFamilyProfileLink.member_id)
                )
            ).all()
        )
        grants = list(
            (
                await session.scalars(
                    select(HealthGrant)
                    .where(HealthGrant.member_id.in_(member_ids))
                    .order_by(HealthGrant.member_id, HealthGrant.actor_uid)
                )
            ).all()
        )
        consents = list(
            (
                await session.scalars(
                    select(HealthProcessingConsent)
                    .where(HealthProcessingConsent.member_id.in_(member_ids))
                    .order_by(
                        HealthProcessingConsent.member_id,
                        HealthProcessingConsent.actor_uid,
                        HealthProcessingConsent.purpose,
                    )
                )
            ).all()
        )
        sources = list(
            (
                await session.scalars(
                    select(SourceMember).where(SourceMember.subject_uid.in_(uids)).order_by(SourceMember.id)
                )
            ).all()
        )
        configuration = (
            (
                await session.execute(
                    text("SELECT row_to_json(c)::text FROM config_options c WHERE key='health_vision_opts' ORDER BY id")
                )
            )
            .scalars()
            .all()
        )
        providers = (
            (await session.execute(text("SELECT row_to_json(p)::text FROM model_providers p ORDER BY provider_id")))
            .scalars()
            .all()
        )
        return {
            "database": await session.scalar(text("SELECT current_database()")),
            "accounts": [
                {"uid": user.uid, "role": user.role, "department_id": user.department_id}
                for user in (await session.scalars(select(User).where(User.uid.in_(uids)).order_by(User.uid))).all()
            ],
            "health_members": [
                {"id": member.id, "owner_uid": member.owner_uid, "relationship_label": member.relationship_label}
                for member in members
            ],
            "links": [
                {
                    "member_id": row.member_id,
                    "family_id": row.family_id,
                    "source_member_id": row.source_member_id,
                    "actor_uid": row.actor_uid,
                }
                for row in links
            ],
            "grants": [
                {
                    "member_id": row.member_id,
                    "actor_uid": row.actor_uid,
                    "scopes": row.scopes,
                    "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
                }
                for row in grants
            ],
            "consents": [
                {
                    "member_id": row.member_id,
                    "actor_uid": row.actor_uid,
                    "purpose": row.purpose,
                    "processor": row.processor,
                    "policy_version": row.policy_version,
                    "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
                }
                for row in consents
            ],
            "sources": [
                {
                    "id": row.id,
                    "family_id": row.family_id,
                    "subject_uid": row.subject_uid,
                    "version": row.version,
                    "confirmed_version": row.confirmed_version,
                    "grant_fields": row.grant_fields,
                    "grant_edit_fields": row.grant_edit_fields,
                    "grant_purpose": row.grant_purpose,
                    "grant_expires_at": row.grant_expires_at.isoformat() if row.grant_expires_at else None,
                }
                for row in sources
            ],
            "agent_runs": int(
                await session.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.uid.in_(uids))) or 0
            ),
            "model_configuration_hash": hashlib.sha256(
                json.dumps([configuration, providers], sort_keys=True).encode()
            ).hexdigest(),
        }


def verify_facts(state, facts, *, browser_linked=False):
    """预期绑定来自夹具身份，而非HTTP响应或客户端缓存。"""
    expected = [
        {
            "member_id": state["health_members"]["primary"],
            **state["families"]["owner"],
            "actor_uid": state["accounts"]["owner"]["uid"],
        }
    ]
    if browser_linked:
        expected.append(
            {
                "member_id": state["health_members"]["foreign"],
                **state["families"]["other"],
                "actor_uid": state["accounts"]["other"]["uid"],
            }
        )
    expected.sort(key=lambda row: row["member_id"])
    assert facts["database"] == "health_consultation_e2e"
    assert facts["links"] == expected, "应且仅应存在各账号明确验收的本人关联"
    for key in ("accounts", "health_members", "grants", "consents", "sources", "model_configuration_hash"):
        assert facts[key] == state["baseline"][key], f"客户端接入不应改变 {key}"
    assert facts["agent_runs"] == 0, "普通账号与成员读写不应启动Agent"


async def cleanup_fixture(state):
    """精确删除此次账号下创建的资源，未覆盖业务副作用则保留而拒绝清理。"""
    uids = [account["uid"] for account in state["accounts"].values()]
    async with pg_manager.get_async_session_context() as session:
        assert await session.scalar(text("SELECT current_database()")) == "health_consultation_e2e"
        assert not await session.scalar(select(AgentRun.id).where(AgentRun.uid.in_(uids))), (
            "发现非预期Agent资源，拒绝清理"
        )
        member_ids = select(HealthMember.id).where(HealthMember.owner_uid.in_(uids))
        source_ids = select(SourceMember.id).where(SourceMember.subject_uid.in_(uids))
        family_ids = select(FamilyArchive.id).where(FamilyArchive.owner_uid.in_(uids))
        for model in (HealthFamilyProfileLink, HealthProcessingConsent, HealthGrant):
            await session.execute(delete(model).where(model.member_id.in_(member_ids)))
        await session.execute(delete(HealthMember).where(HealthMember.owner_uid.in_(uids)))
        await session.execute(delete(FamilyAudit).where(FamilyAudit.family_id.in_(family_ids)))
        await session.execute(delete(FamilyMeasurement).where(FamilyMeasurement.member_id.in_(source_ids)))
        await session.execute(delete(FamilyProfileRevision).where(FamilyProfileRevision.member_id.in_(source_ids)))
        await session.execute(delete(SourceMember).where(SourceMember.family_id.in_(family_ids)))
        await session.execute(delete(FamilyArchive).where(FamilyArchive.owner_uid.in_(uids)))
        await session.execute(
            delete(OperationLog).where(OperationLog.user_id.in_(select(User.id).where(User.uid.in_(uids))))
        )
        await session.execute(delete(User).where(User.uid.in_(uids)))
        await session.execute(delete(Department).where(Department.id == state["department_id"]))
    facts = await read_facts(state)
    for key in ("accounts", "health_members", "links", "grants", "consents", "sources"):
        assert facts[key] == [], f"清理后仍有 {key}"
    async with pg_manager.get_async_session_context() as session:
        remaining_families = int(
            await session.scalar(
                select(func.count()).select_from(FamilyArchive).where(FamilyArchive.owner_uid.in_(uids))
            )
            or 0
        )
        remaining_audits = int(
            await session.scalar(select(func.count()).select_from(FamilyAudit).where(FamilyAudit.actor_uid.in_(uids)))
            or 0
        )
        remaining_operations = int(
            await session.scalar(
                select(func.count())
                .select_from(OperationLog)
                .where(OperationLog.user_id.in_([account["user_id"] for account in state["accounts"].values()]))
            )
            or 0
        )
        assert not (remaining_families or remaining_audits or remaining_operations)
        assert await session.get(Department, state["department_id"]) is None
    if "baseline" in state:
        assert facts["model_configuration_hash"] == state["baseline"]["model_configuration_hash"]
    state["cleaned"] = True
    save_json("metadata.json", state)
    save_json("cleanup-verification.json", {"passed": True, "facts": facts})
    (STATE_ROOT / "credentials.secret.json").unlink(missing_ok=True)
    return {"cleaned": True, "fixture_id": state["fixture_id"], "remaining_owned_rows": 0}


def save_json(name, value):
    """只在固定的项目忽略目录写文件；secret从不写到标准输出。"""
    path = STATE_ROOT / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    path.chmod(0o600)


def require_status(response, expected):
    """失败信息只保留路径与状态，避免认证响应泄漏到日志。"""
    if response.status_code != expected:
        raise AssertionError(
            f"{response.request.method} {response.request.url.path}: expected {expected}, got {response.status_code}"
        )


if __name__ == "__main__":
    asyncio.run(main())

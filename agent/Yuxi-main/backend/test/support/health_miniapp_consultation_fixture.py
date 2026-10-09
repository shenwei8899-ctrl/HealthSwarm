"""小程序本人咨询的独立合成资料、隔离配置和精确收敛清理。"""

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import signal
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import delete, select, text

from test.e2e.test_health_consultation_e2e import drain_requests, wait_until
from test.integration.services.test_health_vision_http import cleanup_health_test_resources
from test.support.health_consultation_replay_server import MODEL
from yuxi.config import get_user_data_dir
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    AgentRun,
    AgentRunAttempt,
    AgentRunRequest,
    ConfigOption,
    Department,
    FamilyArchive,
    FamilyAudit,
    FamilyMember as SourceMember,
    FamilyProfileRevision,
    Message,
    ModelProvider,
    OperationLog,
    User,
)
from yuxi.storage.postgres.models_health import (
    FamilyMember as HealthMember,
    HealthConsultation,
    HealthFamilyProfileLink,
    HealthFamilyProfileUse,
    HealthGrant,
    HealthProcessingConsent,
)
from yuxi.storage.redis import sync_redis_client
from yuxi.utils.auth_utils import AuthUtils
from yuxi.workspace.paths import global_user_data_dir

CONTROL = Path("/app/test/.tmp/miniapp-consultation-20261010")
ROOT = "/api/health/v1"
PROFILE = {
    "sex": "female",
    "birth_date": "1992-01-02",
    "height_cm": 171,
    "activity_level": "light",
    "goal": "合成均衡饮食",
    "allergens": [],
}


async def main():
    """只在明确隔离槽执行夹具阶段，标准输出不包含凭据。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start-replay", "create", "read", "verify-browser", "cleanup"))
    args = parser.parse_args()
    await require_isolated_slot()
    try:
        if args.command == "start-replay":
            print(json.dumps(await start_replay()))
        elif args.command == "create":
            state = await create_fixture()
            print(json.dumps({"created": True, "fixture_id": state["fixture_id"], "control_directory": str(CONTROL)}))
        else:
            state = load_state()
            if args.command == "cleanup":
                print(json.dumps(await cleanup_fixture(state)))
            else:
                if args.command == "verify-browser":
                    save_json("browser-pg-verification.json", {"passed": False, "status": "running"})
                facts = await read_facts(state)
                if args.command == "verify-browser":
                    try:
                        verify_browser(state, facts)
                    except Exception:
                        save_json("browser-pg-verification.json", {"passed": False, "status": "failed", "facts": facts})
                        raise
                save_json(
                    "browser-pg-verification.json" if args.command == "verify-browser" else "pg-current.json",
                    {
                        "passed": args.command == "verify-browser",
                        "facts": facts,
                    },
                )
                print(json.dumps({"passed": args.command == "verify-browser", "facts": facts}, ensure_ascii=False))
    finally:
        await pg_manager.close()


async def require_isolated_slot():
    """实际数据库和启动标记同时限定边界；不迁移或重启服务。"""
    if os.getenv("HEALTH_CONSULTATION_E2E_ISOLATED") != "true":
        raise RuntimeError("仅允许明确的隔离健康验收槽位")
    pg_manager.initialize()
    async with pg_manager.get_async_session_context() as session:
        if await session.scalar(text("SELECT current_database()")) != "health_consultation_e2e":
            raise RuntimeError("禁止操作主数据库")
    await pg_manager.require_current_schema()


async def start_replay():
    """启动专用的已有确定性重放，记录精确PID，不重启或修改共享服务。"""
    CONTROL.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=1) as client:
        try:
            await client.get("/health")
        except httpx.ConnectError:
            pass
        else:
            raise RuntimeError("8766已有监听者，不能接管其他重放进程")
    with (CONTROL / "replay.log").open("a") as output:
        process = subprocess.Popen(
            [sys.executable, "-m", "test.support.health_miniapp_consultation_replay"],
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    (CONTROL / "replay.pid").write_text(str(process.pid))
    async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=1) as client:
        async with asyncio.timeout(5):
            while True:
                if process.poll() is not None:
                    raise RuntimeError("专用重放进程启动失败，保留本轮日志")
                try:
                    response = await client.get("/health")
                except httpx.ConnectError:
                    await asyncio.sleep(0.1)
                    continue
                require_status(response, 200)
                assert response.json() == {"isolated": True}
                return {"replay_started": True, "port": 8766}


async def create_fixture():
    """账号经合成数据插入，家庭、确认、关联及临时审批通过真实HTTP。"""
    CONTROL.mkdir(parents=True, exist_ok=True)
    if (CONTROL / "metadata.json").exists() and not load_state().get("cleaned"):
        raise RuntimeError("已有未清理夹具，请先读取或完成清理")
    fixture_id = uuid4().hex[:12]
    state = {"fixture_id": fixture_id, "accounts": {}, "members": {}, "provider_id": None, "cleaned": False}
    credentials = {}
    async with httpx.AsyncClient(base_url="http://localhost:5050", timeout=20) as client:
        ready = await wait_until(lambda: client.get("/api/system/ready"), lambda response: response.status_code == 200)
        require_status(ready, 200)
        async with httpx.AsyncClient(base_url="http://localhost:8766", timeout=5) as replay:
            require_status(await replay.get("/health"), 200)
        async with pg_manager.get_async_session_context() as session:
            baseline = await session.scalar(select(ConfigOption.value).where(ConfigOption.key == "health_vision_opts"))
            assert isinstance(baseline, dict) and not any(baseline.values()), "不能覆盖已有健康配置"
            assert not await session.scalar(
                select(AgentRun.id).where(
                    AgentRun.worker_id.is_not(None)
                    | AgentRun.lease_expires_at.is_not(None)
                    | AgentRun.runtime_cleanup_pending.is_(True)
                )
            ), "共享隔离槽尚有执行owner"
            state["configuration_baseline"] = baseline
            state["provider_baseline_hash"] = await provider_hash(session)
            department = Department(name="mini_consult_" + fixture_id)
            session.add(department)
            await session.flush()
            state["department_id"] = department.id
            for name, role in (("owner", "user"), ("browser", "user"), ("admin", "admin")):
                uid = "pytest_health_mini_consult_" + fixture_id + "_" + name
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
            for name in ("owner", "browser"):
                headers = await login_headers(client, name)
                family = await client.post("/api/family", headers=headers, json={"name": "小程序合成本人咨询 " + name})
                require_status(family, 200)
                source_id = next(row["id"] for row in family.json()["members"] if row["is_self"])
                state["members"][name] = {"family_id": family.json()["id"], "source_member_id": source_id}
                save_json("metadata.json", state)
                path = f"/api/family/{family.json()['id']}/members/{source_id}"
                updated = await client.put(path, headers=headers, json={"expected_version": 1, "profile": PROFILE})
                require_status(updated, 200)
                assert updated.json()["version"] == 2
                require_status(await client.post(path + "/confirm", headers=headers, json={"expected_version": 2}), 200)
                member = await client.post(
                    ROOT + "/members",
                    headers=headers,
                    json={
                        "display_name": "小程序合成咨询本人 " + name,
                        "relationship_label": "本人",
                        "authorized": True,
                    },
                )
                require_status(member, 201)
                member_id = member.json()["id"]
                state["members"][name]["health_member_id"] = member_id
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
                state["members"][name]["replay_token"] = uuid4().hex
                state["members"][name]["profile_query"] = (
                    f"HEALTH_CONSULTATION_E2E:{state['members'][name]['replay_token']}:profile"
                )
                save_json("metadata.json", state)
            state["before"] = await read_facts(state)
            assert state["before"]["consents"] == []
            admin = await login_headers(client, "admin")
            provider_id = "miniapp-consultation-replay-" + fixture_id
            configured = await client.post(
                "/api/system/model-providers",
                headers=admin,
                json={
                    "provider_id": provider_id,
                    "display_name": "Synthetic miniapp consultation only",
                    "provider_type": "openai",
                    "base_url": "http://api:8766/v1",
                    "api_key": "synthetic-health-replay-key",
                    "capabilities": ["chat"],
                    "enabled_models": [{"id": MODEL, "display_name": MODEL, "type": "chat", "source": "manual"}],
                    "is_enabled": True,
                },
            )
            require_status(configured, 200)
            state["provider_id"] = provider_id
            save_json("metadata.json", state)
            policy = await client.put(
                ROOT + "/configuration",
                headers=admin,
                json={
                    "consultation_model": provider_id + ":" + MODEL,
                    "policy_version": "synthetic-miniapp-consultation-v1",
                    "cloud_processing_reviewed": True,
                },
            )
            require_status(policy, 200)
            assert policy.json()["consultation"]["available"]
            state["configuration"] = policy.json()
            state["browser_question"] = "请根据本人已确认的基础档案，说明目前可以用于营养咨询的信息。"
            state["browser_expected_answer"] = (
                "已读取本人确认基础档案：身高171cm，版本2；这是合成联调答复，营养安全字段尚未就绪。"
            )
            save_json("metadata.json", state)
            return state
        except Exception:
            await cleanup_fixture(state)
            raise


async def read_facts(state):
    """独立PG连接回读身份、用途、线程、Request、Run及正式来源回执。"""
    uids = [row["uid"] for row in state["accounts"].values()]
    member_ids = [row["health_member_id"] for row in state["members"].values() if "health_member_id" in row]
    async with pg_manager.get_async_session_context() as session:
        result = {
            "database": await session.scalar(text("SELECT current_database()")),
            "configuration": await session.scalar(
                select(ConfigOption.value).where(ConfigOption.key == "health_vision_opts")
            ),
            "provider_hash": await provider_hash(session),
            "accounts": [
                {"uid": row.uid, "role": row.role}
                for row in (await session.scalars(select(User).where(User.uid.in_(uids)).order_by(User.uid))).all()
            ],
            "grants": [
                {
                    "member_id": row.member_id,
                    "actor_uid": row.actor_uid,
                    "scopes": row.scopes,
                    "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
                }
                for row in (
                    await session.scalars(
                        select(HealthGrant)
                        .where(HealthGrant.member_id.in_(member_ids))
                        .order_by(HealthGrant.member_id, HealthGrant.actor_uid)
                    )
                ).all()
            ],
            "consents": [
                {
                    "member_id": row.member_id,
                    "actor_uid": row.actor_uid,
                    "purpose": row.purpose,
                    "processor": row.processor,
                    "policy_version": row.policy_version,
                    "revoked": row.revoked_at is not None,
                }
                for row in (
                    await session.scalars(
                        select(HealthProcessingConsent).where(HealthProcessingConsent.member_id.in_(member_ids))
                    )
                ).all()
            ],
            "links": [
                {
                    "member_id": row.member_id,
                    "source_member_id": row.source_member_id,
                    "family_id": row.family_id,
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
            "sources": [
                {
                    "id": row.id,
                    "subject_uid": row.subject_uid,
                    "version": row.version,
                    "confirmed_version": row.confirmed_version,
                    "height_cm": row.profile.get("height_cm"),
                }
                for row in (
                    await session.scalars(
                        select(SourceMember).where(SourceMember.subject_uid.in_(uids)).order_by(SourceMember.id)
                    )
                ).all()
            ],
            "requests": [
                {
                    "request_id": row.request_id,
                    "uid": row.uid,
                    "thread_id": row.conversation_thread_id,
                    "status": row.status,
                    "run_id": row.dispatched_run_id,
                }
                for row in (
                    await session.scalars(
                        select(AgentRunRequest)
                        .where(AgentRunRequest.uid.in_(uids))
                        .order_by(AgentRunRequest.created_at)
                    )
                ).all()
            ],
            "runs": [],
        }
        for run in (
            await session.scalars(select(AgentRun).where(AgentRun.uid.in_(uids)).order_by(AgentRun.created_at))
        ).all():
            message = await session.get(Message, run.output_message_id) if run.output_message_id else None
            binding = await session.get(HealthConsultation, run.conversation_id)
            attempts = list(
                (await session.scalars(select(AgentRunAttempt).where(AgentRunAttempt.run_id == run.id))).all()
            )
            uses = list(
                (
                    await session.scalars(select(HealthFamilyProfileUse).where(HealthFamilyProfileUse.run_id == run.id))
                ).all()
            )
            result["runs"].append(
                {
                    "run_id": run.id,
                    "request_id": run.request_id,
                    "uid": run.uid,
                    "thread_id": run.conversation_thread_id,
                    "status": run.status,
                    "error_type": run.error_type,
                    "output_message_id": run.output_message_id,
                    "owner_released": run.worker_id is None,
                    "lease_released": run.lease_expires_at is None,
                    "runtime_cleanup_pending": run.runtime_cleanup_pending,
                    "binding": {"member_id": binding.member_id, "actor_uid": binding.actor_uid} if binding else None,
                    "message": {
                        "run_id": message.run_id,
                        "request_id": message.request_id,
                        "content": message.content,
                        "role": message.role,
                        "message_type": message.message_type,
                    }
                    if message
                    else None,
                    "attempts": [{"outcome": row.outcome, "finished": row.finished_at is not None} for row in attempts],
                    "profile_uses": [
                        {
                            "member_id": row.member_id,
                            "source_member_id": row.source_member_id,
                            "version": row.version,
                            "payload_hash": row.payload_hash,
                        }
                        for row in uses
                    ],
                }
            )
        return result


def verify_browser(state, facts):
    """真实浏览器完成本人明确同意及提问后，用PG权威输出反证串读。"""
    uid, selected = state["accounts"]["browser"]["uid"], state["members"]["browser"]
    assert facts["grants"] == state["before"]["grants"]
    assert facts["links"] == state["before"]["links"]
    assert [row for row in facts["sources"] if row["subject_uid"] == uid] == [
        {
            "id": selected["source_member_id"],
            "subject_uid": uid,
            "version": 2,
            "confirmed_version": 2,
            "height_cm": 171,
        }
    ]
    browser_consents = [row for row in facts["consents"] if row["actor_uid"] == uid]
    assert browser_consents == [
        {
            "member_id": selected["health_member_id"],
            "actor_uid": uid,
            "purpose": "consultation",
            "processor": state["configuration"]["consultation"]["processor"],
            "policy_version": state["configuration"]["policy_version"],
            "revoked": False,
        }
    ]
    runs = [row for row in facts["runs"] if row["uid"] == uid]
    assert runs and all(row["status"] == "completed" for row in runs)
    assert any(row["profile_uses"] for row in runs)
    for run in runs:
        request = next(row for row in facts["requests"] if row["request_id"] == run["request_id"])
        assert request == {
            "request_id": run["request_id"],
            "uid": uid,
            "thread_id": run["thread_id"],
            "status": "dispatched",
            "run_id": run["run_id"],
        }
        assert run["binding"] == {"member_id": selected["health_member_id"], "actor_uid": uid}
        assert run["message"] == {
            "run_id": run["run_id"],
            "request_id": run["request_id"],
            "content": state["browser_expected_answer"],
            "role": "assistant",
            "message_type": "text",
        }
        assert run["owner_released"] and run["lease_released"] and not run["runtime_cleanup_pending"]
        assert run["attempts"] and all(row["finished"] and row["outcome"] == "completed" for row in run["attempts"])
        for use in run["profile_uses"]:
            assert (use["member_id"], use["source_member_id"], use["version"]) == (
                selected["health_member_id"],
                selected["source_member_id"],
                2,
            )


async def cleanup_fixture(state):
    """取消仅本轮请求并核对lease释放，恢复真实基线后清理精确所属行。"""
    uids = [row["uid"] for row in state["accounts"].values()]
    async with httpx.AsyncClient(base_url="http://localhost:5050", timeout=20) as client:
        identities = []
        for name in state["accounts"]:
            headers = await login_headers(client, name)
            identities.append({"uid": state["accounts"][name]["uid"], "headers": headers})
            async with pg_manager.get_async_session_context() as session:
                request_ids = list(
                    (
                        await session.scalars(
                            select(AgentRunRequest.request_id).where(
                                AgentRunRequest.uid == state["accounts"][name]["uid"]
                            )
                        )
                    ).all()
                )
            await drain_requests(client, headers, request_ids)
        await wait_until(
            lambda: read_facts(state),
            lambda facts: all(
                run["owner_released"] and run["lease_released"] and not run["runtime_cleanup_pending"]
                for run in facts["runs"]
            ),
        )
        facts = await read_facts(state)
        save_json("before-cleanup.json", facts)
        if state["provider_id"]:
            admin = await login_headers(client, "admin")
            reset = await client.put(ROOT + "/configuration", headers=admin, json={})
            require_status(reset, 200)
            require_status(
                await client.delete("/api/system/model-providers/" + state["provider_id"], headers=admin), 200
            )
        async with pg_manager.get_async_session_context() as session:
            members = select(HealthMember.id).where(HealthMember.owner_uid.in_(uids))
            families = select(FamilyArchive.id).where(FamilyArchive.owner_uid.in_(uids))
            sources = select(SourceMember.id).where(SourceMember.family_id.in_(families))
            await session.execute(delete(HealthFamilyProfileUse).where(HealthFamilyProfileUse.member_id.in_(members)))
            await session.execute(delete(HealthFamilyProfileLink).where(HealthFamilyProfileLink.member_id.in_(members)))
            await session.execute(delete(FamilyAudit).where(FamilyAudit.family_id.in_(families)))
            await session.execute(delete(FamilyProfileRevision).where(FamilyProfileRevision.member_id.in_(sources)))
            await session.execute(delete(SourceMember).where(SourceMember.family_id.in_(families)))
            await session.execute(delete(FamilyArchive).where(FamilyArchive.owner_uid.in_(uids)))
            await session.execute(
                delete(OperationLog).where(
                    OperationLog.user_id.in_([row["user_id"] for row in state["accounts"].values()])
                )
            )
        await cleanup_health_test_resources(identities, state["department_id"])
    root = get_user_data_dir().resolve()
    for uid in uids:
        target = global_user_data_dir(uid)
        target.resolve().relative_to(root)
        assert target.name == uid and uid.startswith("pytest_health_mini_consult_")
        if target.exists():
            shutil.rmtree(target)
    keys = ["run:events:" + row["run_id"] for row in facts["runs"]]
    with sync_redis_client() as redis:
        assert all(redis.type(key) in {"none", "stream"} for key in keys)
        if keys:
            redis.delete(*keys)
        assert not any(redis.exists(key) for key in keys)
    final = await read_facts(state)
    for key in ("accounts", "grants", "consents", "links", "sources", "requests", "runs"):
        assert final[key] == [], f"清理后仍有 {key}"
    assert final["configuration"] == state["configuration_baseline"]
    assert final["provider_hash"] == state["provider_baseline_hash"]
    state["cleaned"] = True
    save_json("metadata.json", state)
    save_json("cleanup-verification.json", {"passed": True, "facts": final})
    (CONTROL / "credentials.secret.json").unlink(missing_ok=True)
    pid_path = CONTROL / "replay.pid"
    if pid_path.exists():
        pid = int(pid_path.read_text())
        command = Path(f"/proc/{pid}/cmdline")
        if command.exists() and command.read_bytes():
            assert b"test.support.health_miniapp_consultation_replay" in command.read_bytes()
            os.kill(pid, signal.SIGTERM)
        pid_path.unlink()
    return {"cleaned": True, "fixture_id": state["fixture_id"], "remaining_owned_rows": 0}


async def login_headers(client, name):
    """经正式Token接口取得普通或合成管理员身份，凭据不打印或持久化。"""
    credentials = json.loads((CONTROL / "credentials.secret.json").read_text())[name]
    response = await client.post(
        "/api/auth/token", data={"username": credentials["identifier"], "password": credentials["password"]}
    )
    require_status(response, 200)
    return {"Authorization": "Bearer " + response.json()["access_token"]}


async def provider_hash(session):
    """保存供应商全表摘要，不导出任何原始供应商凭据。"""
    rows = (await session.execute(select(ModelProvider).order_by(ModelProvider.provider_id))).scalars().all()
    content = [{column.name: getattr(row, column.name) for column in ModelProvider.__table__.columns} for row in rows]
    return hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()


def load_state():
    """只读取固定项目忽略目录内本轮状态。"""
    return json.loads((CONTROL / "metadata.json").read_text())


def save_json(name, value):
    """健康合成输出只写忽略目录，secret不进入标准输出。"""
    path = CONTROL / name
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o600)


def require_status(response, expected):
    """错误只包含协议路径与状态，认证正文不得进入诊断。"""
    if response.status_code != expected:
        raise AssertionError(
            f"{response.request.method} {response.request.url.path}: expected {expected}, got {response.status_code}"
        )


if __name__ == "__main__":
    asyncio.run(main())

"""账号家庭记忆的真实 HTTP、PG 与语义处理持久化验收。"""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import select, text

from test.integration.services.test_health_family_profile_http import (  # noqa: F401
    family_profile_http,
    linked_self,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    ensure_live_api_schema,
)
from yuxi.services import health_memory_context_service as service
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import (
    AgentRun,
    AgentRunRequest,
    Message,
    Conversation,
    Project,
    FamilyMember as SourceMember,
)
from yuxi.storage.postgres.models_health import (
    HealthConsultation,
    HealthFamilyProfileLink,
    HealthMemoryFact,
    HealthMemoryProcessing,
)
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_plan_restrictions_use_only_current_actor_family_and_participants(family_profile_http):
    """实际数据库筛选不能把其他账号、旧家庭和未参与者的自述带入菜单。"""
    client, sessions, users = family_profile_http
    hid, source = await linked_self(client, users["self"])
    async with sessions() as db:
        link = await db.get(HealthFamilyProfileLink, hid)
        source_id = link.source_member_id
    current = {"sources": {"family_id": source["family_id"], "members": {source_id: {"health_member_id": hid}}}}
    async with sessions.begin() as db:
        for name, actor, family, member, kind in [
            ("restriction", "self", source["family_id"], source_id, "restriction"),
            ("other", "other", source["family_id"], source_id, "restriction"),
            ("old", "self", "old-family", source_id, "restriction"),
            ("wrong-subject", "self", source["family_id"], "wrong-member", "restriction"),
            ("preference", "self", source["family_id"], source_id, "preference"),
        ]:
            db.add(
                HealthMemoryFact(
                    id=name,
                    actor_uid=actor,
                    member_id=hid,
                    fact_key=name,
                    content="我不吃牛肉",
                    kind=kind,
                    version=1,
                    provenance={"family_id": family, "source_member_id": member, "entity": "牛肉"},
                )
            )
    async with sessions() as db:
        expected = [{"id": "restriction", "version": 1, "restriction": "牛肉"}]
        assert await service.account_plan_restrictions(db, "self", current) == expected
        assert (
            await service.account_plan_restrictions(
                db, "self", {"sources": {"family_id": source["family_id"], "members": {}}}
            )
            == []
        )
    async with sessions.begin() as db:
        fact = await db.get(HealthMemoryFact, "restriction")
        fact.version, fact.status = 2, "revoked"
    async with sessions() as db:
        assert await service.account_plan_restrictions(db, "self", current) == []


async def memory_run_fixture(client, sessions, headers, *, planner=False, quote="我妈妈不爱吃香菜，安排晚餐"):
    """真实建档与请求原文；只在测试层替换模型及运行审批配置。"""
    anchor, source = await linked_self(client, headers)
    async with sessions.begin() as session:
        from yuxi.storage.postgres.models_health import FamilyMember

        family_id = source["family_id"]
        mom, mom_hid = str(uuid4()), str(uuid4())
        session.add(SourceMember(id=mom, family_id=family_id, name="妈妈", relationship="母亲", profile={}))
        session.add(FamilyMember(id=mom_hid, owner_uid="self", display_name="妈妈", relationship_label="母亲"))
        await session.flush()
        session.add(
            HealthFamilyProfileLink(
                member_id=mom_hid,
                source_member_id=mom,
                family_id=family_id,
                actor_uid="self",
                source_kind="miniapp_reported",
            )
        )
        project_id, thread, request_id, run_id = (str(uuid4()) for _ in range(4))
        slug = "health-meal-planner" if planner else "health-consultation"
        session.add(
            Project(
                id=project_id,
                uid="self",
                selection_status="implicit",
                directory_mode="managed",
                workdir_path="projects/" + project_id,
            )
        )
        await session.flush()
        conversation = Conversation(uid="self", thread_id=thread, project_id=project_id, agent_id=slug)
        session.add(conversation)
        await session.flush()
        binding = HealthConsultation(
            conversation_id=conversation.id, actor_uid="self", member_id=anchor, request_id=str(uuid4())
        )
        session.add(binding)
        message = Message(conversation_id=conversation.id, role="user", content=quote, request_id=request_id)
        session.add(message)
        await session.flush()
        run = AgentRun(
            id=run_id,
            uid="self",
            agent_slug=slug,
            conversation_thread_id=thread,
            runtime_scope_id=thread,
            conversation_id=conversation.id,
            request_id=request_id,
            status="running",
            worker_id="synthetic-worker",
            lease_expires_at=utc_now_naive() + timedelta(minutes=5),
            input_payload={"health_processing": {"model": "synthetic/model"}},
        )
        session.add(run)
        await session.flush()
        session.add(
            AgentRunRequest(
                request_id=request_id,
                uid="self",
                agent_slug=slug,
                conversation_thread_id=thread,
                input_message_id=message.id,
                dispatched_run_id=run_id,
                status="dispatched",
            )
        )
    context = SimpleNamespace(
        uid="self",
        thread_id=thread,
        request_id=request_id,
        run_id=run_id,
        worker_id="synthetic-worker",
        model="synthetic/model",
    )
    return context, binding, mom_hid, family_id


def extraction_model(monkeypatch, binding, candidates):
    """预算和模型边界使用确定性输出，事实、收据和授权仍用真实 PG。"""
    from yuxi.services import health_ai_budget_service as budget, health_consultation_service as consultation

    monkeypatch.setattr(consultation, "require_consultation", AsyncMock(return_value=(binding, {})))
    monkeypatch.setattr(consultation, "require_consultation_attempt", AsyncMock())
    monkeypatch.setattr(budget, "reserve_model", AsyncMock(return_value=object()))
    monkeypatch.setattr(budget, "settle", AsyncMock())
    import json

    model = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value=AIMessage(content=json.dumps({"candidates": candidates, "questions": []}, ensure_ascii=False))
        )
    )
    monkeypatch.setattr(budget, "reserved_chat_model", lambda *args, **kwargs: model)
    # 审核的独立语义结果可控制，PG用例不把regex当自然语言oracle。
    accepted = set(range(len(candidates)))
    if (
        len(candidates) == 1
        and candidates[0].get("subject_quote") == "我"
        and any(term in candidates[0].get("quote", "") for term in ("妈妈", "爸爸", "叔叔", "同事", "孩子", "曾祖母"))
    ):
        accepted = set()
    if candidates and ("的同事" in candidates[0].get("quote", "") or "同事的妈妈" in candidates[0].get("quote", "")):
        accepted = set()
    if candidates and candidates[0].get("subject_quote") == "我" and candidates[0]["member_id"] != binding.member_id:
        accepted = set()
    if (
        candidates
        and candidates[0].get("subject_quote") == "妈妈"
        and candidates[0].get("quote", "").startswith("我不")
    ):
        accepted = set()
    monkeypatch.setattr(service, "verify_candidate_subjects", AsyncMock(return_value=accepted))
    return model


async def test_natural_family_memory_same_run_private_management_and_departure(family_profile_http, monkeypatch):  # noqa: F811
    """妈妈记忆在本人账号保存；当轮提供，离家后仍能看删且不再召回。"""
    client, sessions, identities = family_profile_http
    headers = identities["self"]
    context, binding, mom, family_id = await memory_run_fixture(client, sessions, headers)
    model = extraction_model(
        monkeypatch,
        binding,
        [
            {
                "member_id": mom,
                "quote": "我妈妈不爱吃香菜",
                "subject_quote": "我妈妈",
                "kind": "preference",
                "fact_key": "coriander",
                "meaning": "不爱吃香菜",
                "ongoing": True,
            }
        ],
    )
    result = await service.process_memory_for_run(context, purpose="consultation")
    assert result["saved"]
    assert await service.process_memory_for_run(context, purpose="consultation") == result
    assert model.ainvoke.await_count == 1
    payload = await service.memory_context_for_run(context)
    assert len(payload["memories"]) == 1
    assert payload["memories"][0]["member_id"] == mom
    assert payload["memories"][0]["kind"] == "preference"
    fact_id = result["saved"][0]["memory_id"]
    from yuxi.repositories.health_memory_repository import HealthMemoryRepository

    async with sessions() as session:
        assert (
            list(
                (
                    await session.scalars(HealthMemoryRepository(session).invalid_requests("self", binding.member_id))
                ).all()
            )
            == []
        )
    listed = await client.get("/api/health/v1/memory", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["memories"][0]["subject_label"] == "妈妈"
    assert listed.json()["memories"][0]["recallable"] is True
    assert (await client.get(f"/api/health/v1/memory/{fact_id}", headers=identities["other"])).status_code == 404
    async with sessions.begin() as session:
        member = await session.scalar(select(SourceMember).where(SourceMember.subject_uid == "self"))
        member.is_active = False
    listed = (await client.get("/api/health/v1/memory", headers=headers)).json()
    assert listed["memories"][0]["recallable"] is False
    assert listed["memories"][0]["editable"] is False
    async with sessions() as session:
        assert (
            context.request_id
            in (
                await session.scalars(HealthMemoryRepository(session).invalid_requests("self", binding.member_id))
            ).all()
        )
    async with sessions() as session:
        run = await session.get(AgentRun, context.run_id)
        with pytest.raises(HealthVisionError, match="memory_changed|not_found"):
            await service.validate_memory_publication(session, run)
    request_id = str(uuid4())
    removed = await client.post(
        f"/api/health/v1/memory/{fact_id}/revoke",
        headers={**headers, "Idempotency-Key": request_id, "If-Match": '"1"'},
        json={"version": 1, "client_request_id": request_id},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["status"] == "revoked"
    async with sessions() as session:
        fact = await session.get(HealthMemoryFact, fact_id)
        assert fact.member_id == mom and fact.status == "revoked" and fact.version == 2
        assert fact.provenance["family_id"] == family_id
        assert await session.get(HealthMemoryProcessing, (context.request_id, "self"))


@pytest.mark.parametrize("planner", [False, True])
async def test_semantic_source_and_unknown_subject_rejected(family_profile_http, monkeypatch, planner):  # noqa: F811
    """模型即使编出不存在成员也不能写；失败无事实或处理收据。"""
    client, sessions, identities = family_profile_http
    context, binding, _, _ = await memory_run_fixture(client, sessions, identities["self"], planner=planner)
    extraction_model(
        monkeypatch,
        binding,
        [
            {
                "member_id": str(uuid4()),
                "quote": "我妈妈不爱吃香菜",
                "subject_quote": "我妈妈",
                "kind": "preference",
                "fact_key": "coriander",
                "meaning": "不爱吃",
                "ongoing": True,
            }
        ],
    )
    with pytest.raises(HealthVisionError, match="memory_source_invalid"):
        await service.process_memory_for_run(context, purpose="meal" if planner else "consultation")
    async with sessions() as session:
        assert (await session.scalars(select(HealthMemoryFact))).all() == []
        assert (await session.scalars(select(HealthMemoryProcessing))).all() == []


async def test_incremental_schema_preserves_legacy_rows_and_never_later_relinks_unknown(family_profile_http):  # noqa: F811
    """真实旧列升级重复执行保留版本；无法确定的来源不因重跑而被推断。"""
    from yuxi.storage_migrations.v038_account_memory import upgrade_account_memory

    client, sessions, identities = family_profile_http
    _, binding, _, _ = await memory_run_fixture(client, sessions, identities["self"])
    engine = sessions.kw["bind"]
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE health_memory_fact DROP COLUMN provenance"))
        await conn.execute(text("ALTER TABLE health_memory_revision DROP COLUMN provenance"))
        await conn.execute(
            text(
                "INSERT INTO health_memory_fact "
                "(id,actor_uid,member_id,fact_key,kind,content,version,status,updated_at)"
                " VALUES ('legacy','self',:member,'coriander','preference','我不喜欢香菜',7,'active',now())"
            ),
            {"member": binding.member_id},
        )
    manager = SimpleNamespace(async_engine=engine)
    await upgrade_account_memory(manager)
    await upgrade_account_memory(manager)
    async with sessions.begin() as session:
        fact = await session.get(HealthMemoryFact, "legacy")
        assert fact.version == 7 and fact.content == "我不喜欢香菜" and fact.provenance["family_id"]
        fact.provenance = {}
    await upgrade_account_memory(manager)
    async with sessions() as session:
        assert (await session.get(HealthMemoryFact, "legacy")).provenance == {}


async def test_planner_same_message_filters_participants_and_rejects_changed_memory(family_profile_http, monkeypatch):  # noqa: F811
    """配餐当轮接收新偏好；未参加者不提供，外部修改后拒绝继续生成。"""
    from yuxi.services import reference_meal_plan_service
    from yuxi.storage.postgres.models_health import HealthMemoryUse

    client, sessions, identities = family_profile_http
    context, binding, mom, _ = await memory_run_fixture(client, sessions, identities["self"], planner=True)
    extraction_model(
        monkeypatch,
        binding,
        [
            {
                "member_id": mom,
                "quote": "我妈妈不爱吃香菜",
                "subject_quote": "我妈妈",
                "kind": "preference",
                "fact_key": "coriander",
                "meaning": "不爱吃香菜",
                "ongoing": True,
            }
        ],
    )
    result = await service.process_memory_for_run(context, purpose="meal")
    selected = {"sources": {"members": {"mom": {"health_member_id": mom}}}, "members": []}
    monkeypatch.setattr(reference_meal_plan_service, "bound_reference_context", AsyncMock(return_value=selected))
    payload = await service.memory_context_for_run(context, planner=True)
    assert payload["memories"][0]["content"] == "我妈妈不爱吃香菜"
    selected["sources"]["members"] = {"self": {"health_member_id": binding.member_id}}
    assert (await service.memory_context_for_run(context, planner=True))["memories"] == []
    async with sessions.begin() as session:
        fact = await session.get(HealthMemoryFact, result["saved"][0]["memory_id"])
        fact.version += 1
        fact.content = "妈妈改为喜欢香菜"
    with pytest.raises(HealthVisionError, match="memory_changed"):
        await service.memory_context_for_run(context, planner=True)
    async with sessions() as session:
        uses = (await session.scalars(select(HealthMemoryUse).where(HealthMemoryUse.run_id == context.run_id))).all()
        assert len(uses) == 1 and uses[0].version == 1


async def test_same_quote_multiple_members_and_processing_receipt_prevents_revival(family_profile_http, monkeypatch):  # noqa: F811
    """同一原句能保存两个实际主体；删除后重放处理收据不复活。"""
    from yuxi.services.health_memory_service import change_member_memory
    from yuxi.services.health_memory_types import MemoryRevoke

    client, sessions, identities = family_profile_http
    quote = "我和妈妈都不喜欢香菜"
    context, binding, mom, _ = await memory_run_fixture(client, sessions, identities["self"], quote=quote)
    model = extraction_model(
        monkeypatch,
        binding,
        [
            {
                "member_id": mid,
                "quote": quote,
                "subject_quote": "我" if mid == binding.member_id else "妈妈",
                "kind": "preference",
                "fact_key": "coriander",
                "meaning": "不喜欢香菜",
                "ongoing": True,
            }
            for mid in [binding.member_id, mom]
        ],
    )
    result = await service.process_memory_for_run(context, purpose="consultation")
    assert len(result["saved"]) == 2
    fact_id = result["saved"][0]["memory_id"]
    await change_member_memory("self", fact_id, MemoryRevoke(client_request_id=uuid4(), version=1), revoke=True)
    await service.process_memory_for_run(context, purpose="consultation")
    assert model.ainvoke.await_count == 1
    async with sessions() as session:
        assert (await session.get(HealthMemoryFact, fact_id)).status == "revoked"


async def test_temporary_candidate_and_empty_receipt_never_become_long_term(family_profile_http, monkeypatch):  # noqa: F811
    """临时要求只留处理结果，空结果重试也不再次调用模型。"""
    client, sessions, identities = family_profile_http
    context, binding, mom, _ = await memory_run_fixture(
        client, sessions, identities["self"], quote="妈妈今天不想吃香菜"
    )
    model = extraction_model(
        monkeypatch,
        binding,
        [
            {
                "member_id": mom,
                "quote": "妈妈今天不想吃香菜",
                "subject_quote": "妈妈",
                "kind": "preference",
                "fact_key": "coriander",
                "meaning": "本次不吃",
                "ongoing": False,
            }
        ],
    )
    assert (await service.process_memory_for_run(context, purpose="consultation"))["saved"] == []
    await service.process_memory_for_run(context, purpose="consultation")
    assert model.ainvoke.await_count == 1
    async with sessions() as session:
        assert (await session.scalars(select(HealthMemoryFact))).all() == []


@pytest.mark.parametrize(
    "wrong_subject,subject,offset,quote",
    [
        ("self", "我", 0, "我妈妈不爱吃香菜"),
        ("self", "我", 0, "我爸爸不爱吃香菜"),
        ("self", "我", 0, "我叔叔不爱吃香菜"),
        ("self", "我", 0, "我的同事不爱吃香菜"),
        ("self", "我", 0, "我家孩子不吃花生"),
        ("mom", "妈妈", 0, "妈妈的同事不爱吃香菜"),
        ("self", "我", 0, "我曾祖母不吃花生"),
        ("mom", "妈妈", 0, "我同事的妈妈不爱吃香菜"),
        ("mom", "我", 0, "我不爱吃香菜"),
        ("mom", "妈妈", 0, "我不爱吃香菜"),
    ],
)
async def test_original_subject_must_match_unique_directory(
    family_profile_http, monkeypatch, wrong_subject, subject, offset, quote
):
    """合法成员ID不能替代原文主体证明，失败追问且不写事实。"""
    client, sessions, identities = family_profile_http
    context, binding, mom, _ = await memory_run_fixture(client, sessions, identities["self"], quote=quote)
    extraction_model(
        monkeypatch,
        binding,
        [
            {
                "member_id": binding.member_id if wrong_subject == "self" else mom,
                "quote": quote,
                "subject_quote": subject,
                "kind": "preference",
                "fact_key": "coriander",
                "meaning": "不爱吃香菜",
                "ongoing": True,
            }
        ],
    )
    result = await service.process_memory_for_run(context, purpose="consultation")
    assert result["saved"] == [] and result["questions"]
    async with sessions() as session:
        assert (await session.scalars(select(HealthMemoryFact))).all() == []


async def test_private_memory_write_and_edit_do_not_grant_health_access(family_profile_http, monkeypatch):
    """家人无健康权限时仍能管理自己的自述，但模型不能收到其档案。"""
    from yuxi.repositories.health_vision_repository import HealthVisionRepository
    from yuxi.services.health_memory_service import change_member_memory
    from yuxi.services.health_memory_types import MemoryPatch

    client, sessions, identities = family_profile_http
    context, binding, mom, _ = await memory_run_fixture(client, sessions, identities["self"])
    extraction_model(
        monkeypatch,
        binding,
        [
            {
                "member_id": mom,
                "quote": "我妈妈不爱吃香菜",
                "subject_quote": "我妈妈",
                "kind": "preference",
                "fact_key": "coriander",
                "meaning": "不爱吃香菜",
                "ongoing": True,
            }
        ],
    )
    async with sessions() as session:
        for scope in ("profile_view", "ai_use"):
            with pytest.raises(HealthVisionError):
                await HealthVisionRepository(session).authorize(mom, "self", scope)
    result = await service.process_memory_for_run(context, purpose="consultation")
    payload = await service.memory_context_for_run(context)
    assert mom not in [row["member_id"] for row in payload["profile"]]
    assert payload["memories"][0]["member_id"] == mom
    listed = (await client.get("/api/health/v1/memory", headers=identities["self"])).json()
    assert listed["memories"][0]["editable"] is True
    updated = await change_member_memory(
        "self",
        result["saved"][0]["memory_id"],
        MemoryPatch(client_request_id=uuid4(), version=1, content="妈妈不喜欢香菜", kind="preference"),
    )
    assert updated["version"] == 2
    async with sessions() as session:
        with pytest.raises(HealthVisionError):
            await HealthVisionRepository(session).authorize(mom, "self", "ai_use")


async def test_account_list_keeps_current_family_memory_without_self_health_link(family_profile_http, monkeypatch):
    """统一管理不依赖本人健康档案已建立关联。"""
    from sqlalchemy import delete

    client, sessions, identities = family_profile_http
    context, binding, mom, _ = await memory_run_fixture(client, sessions, identities["self"])
    extraction_model(
        monkeypatch,
        binding,
        [
            {
                "member_id": mom,
                "quote": "我妈妈不爱吃香菜",
                "subject_quote": "我妈妈",
                "kind": "preference",
                "fact_key": "coriander",
                "meaning": "不爱吃香菜",
                "ongoing": True,
            }
        ],
    )
    result = await service.process_memory_for_run(context, purpose="consultation")
    async with sessions.begin() as session:
        await session.execute(
            delete(HealthFamilyProfileLink).where(HealthFamilyProfileLink.member_id == binding.member_id)
        )
    response = await client.get("/api/health/v1/memory", headers=identities["self"])
    row = response.json()["memories"][0]
    assert row["memory_id"] == result["saved"][0]["memory_id"] and row["editable"] and row["recallable"]


async def test_unlinked_history_is_preserved_when_new_statement_uses_same_key(family_profile_http, monkeypatch):
    """空来源历史不原地重映射，新陈述形成独立来源事实。"""
    client, sessions, identities = family_profile_http
    context, binding, mom, _ = await memory_run_fixture(client, sessions, identities["self"])
    async with sessions.begin() as session:
        session.add(
            HealthMemoryFact(
                id="legacy-unknown",
                actor_uid="self",
                member_id=mom,
                fact_key="coriander",
                content="旧来源原文",
                kind="preference",
                version=7,
                provenance={},
            )
        )
    extraction_model(
        monkeypatch,
        binding,
        [
            {
                "member_id": mom,
                "quote": "我妈妈不爱吃香菜",
                "subject_quote": "我妈妈",
                "kind": "preference",
                "fact_key": "coriander",
                "meaning": "不爱吃香菜",
                "ongoing": True,
            }
        ],
    )
    result = await service.process_memory_for_run(context, purpose="consultation")
    async with sessions() as session:
        legacy = await session.get(HealthMemoryFact, "legacy-unknown")
        assert legacy.provenance == {} and legacy.version == 7 and legacy.content == "旧来源原文"
        assert result["saved"][0]["memory_id"] != legacy.id
        fresh = await session.get(HealthMemoryFact, result["saved"][0]["memory_id"])
        assert fresh.provenance["source_member_id"] and fresh.version == 1


@pytest.mark.parametrize(
    "quote", ["我一向不吃香菜", "我一吃花生就过敏", "按照家里的习惯我一向不吃香菜", "我的确不吃花生"]
)
async def test_natural_self_statement_has_no_verb_whitelist(family_profile_http, monkeypatch, quote):
    """主体校验不限定后续长期事实的谓语句式。"""
    client, sessions, identities = family_profile_http
    context, binding, mom, _ = await memory_run_fixture(client, sessions, identities["self"], quote=quote)
    extraction_model(
        monkeypatch,
        binding,
        [
            {
                "member_id": binding.member_id,
                "quote": quote,
                "subject_quote": "我",
                "kind": "restriction",
                "fact_key": "restriction",
                "meaning": quote,
                "ongoing": True,
            }
        ],
    )
    assert (await service.process_memory_for_run(context, purpose="consultation"))["saved"]


async def test_consultation_without_profile_permission_keeps_optional_context_empty(family_profile_http, monkeypatch):
    """没有档案读取权限不阻断已有AI咨询。"""
    from sqlalchemy import delete
    from yuxi.storage.postgres.models_health import HealthGrant

    client, sessions, identities = family_profile_http
    context, binding, mom, _ = await memory_run_fixture(client, sessions, identities["self"])
    extraction_model(monkeypatch, binding, [])
    async with sessions.begin() as session:
        await session.execute(
            delete(HealthFamilyProfileLink).where(HealthFamilyProfileLink.member_id == binding.member_id)
        )
        grant = await session.get(HealthGrant, (binding.member_id, "self"))
        grant.scopes = ["ai_use"]
    payload = await service.memory_context_for_run(context)
    assert payload["profile"] == [] and payload["complete"] is True


async def test_profile_use_rechecks_ai_permission_at_publication(family_profile_http, monkeypatch):
    """真实来源仅撤销AI用途即拒绝；去掉目标校验后同一依赖必须可发布。"""
    from yuxi.storage.postgres.models_health import HealthGrant
    from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
    from yuxi.repositories.health_vision_repository import HealthVisionRepository

    client, sessions, identities = family_profile_http
    context, binding, mom, _ = await memory_run_fixture(client, sessions, identities["self"])
    extraction_model(monkeypatch, binding, [])
    async with sessions.begin() as session:
        run = await session.get(AgentRun, context.run_id)
        profiles = HealthFamilyProfileRepository(session)
        payload = await profiles.read("self", binding.member_id, family_assistant=True)
        await profiles.record_use(run, payload)
    async with sessions() as session:
        await service.validate_memory_publication(session, await session.get(AgentRun, context.run_id))
    async with sessions.begin() as session:
        grant = await session.get(HealthGrant, (binding.member_id, "self"))
        grant.scopes = [scope for scope in grant.scopes if scope != "ai_use"]
        assert "profile_view" in grant.scopes
    async with sessions() as session:
        with pytest.raises(HealthVisionError) as caught:
            await service.validate_memory_publication(session, await session.get(AgentRun, context.run_id))
        assert caught.value.code == "not_found" and caught.value.status == 404
    original = HealthVisionRepository.authorize

    async def without_ai_guard(self, member_id, uid, scope, **kwargs):
        return await original(self, member_id, uid, "profile_view" if scope == "ai_use" else scope, **kwargs)

    monkeypatch.setattr(HealthVisionRepository, "authorize", without_ai_guard)
    async with sessions() as session:
        await service.validate_memory_publication(session, await session.get(AgentRun, context.run_id))


async def test_unlinked_anchor_recalls_existing_current_family_memory(family_profile_http, monkeypatch):
    """当前账号家庭记忆不依赖入口健康对象已关联，旧家庭明确关联仍拒绝。"""
    from sqlalchemy import delete

    client, sessions, identities = family_profile_http
    context, binding, mom, _ = await memory_run_fixture(client, sessions, identities["self"])
    extraction_model(
        monkeypatch,
        binding,
        [
            {
                "member_id": mom,
                "quote": "我妈妈不爱吃香菜",
                "subject_quote": "我妈妈",
                "kind": "preference",
                "fact_key": "coriander",
                "meaning": "不爱吃香菜",
                "ongoing": True,
            }
        ],
    )
    result = await service.process_memory_for_run(context, purpose="consultation")
    async with sessions.begin() as session:
        await session.execute(
            delete(HealthFamilyProfileLink).where(HealthFamilyProfileLink.member_id == binding.member_id)
        )
    payload = await service.memory_context_for_run(context)
    assert payload["memories"][0]["memory_id"] == result["saved"][0]["memory_id"]


@pytest.mark.parametrize("valid_count", [1, 301])
async def test_recall_capacity_excludes_unlinked_history(family_profile_http, monkeypatch, valid_count):
    """历史管理记录不耗召回容量，真实有效记录仍执行上限。"""
    from yuxi.services.health_memory_service import member_memory_for_run

    client, sessions, identities = family_profile_http
    context, binding, mom, family_id = await memory_run_fixture(client, sessions, identities["self"])
    extraction_model(monkeypatch, binding, [])
    async with sessions.begin() as session:
        link = await session.get(HealthFamilyProfileLink, mom)
        for index in range(301):
            session.add(
                HealthMemoryFact(
                    id=f"a-history-{index:03}",
                    actor_uid="self",
                    member_id=mom,
                    fact_key=f"history_{index}",
                    content="历史自述",
                    kind="preference",
                    version=1,
                    provenance={},
                )
            )
        for index in range(valid_count):
            session.add(
                HealthMemoryFact(
                    id=f"z-current-{index:03}",
                    actor_uid="self",
                    member_id=mom,
                    fact_key=f"current_{index}",
                    content="我妈妈不爱吃香菜",
                    kind="preference",
                    version=1,
                    provenance={
                        "family_id": family_id,
                        "source_member_id": link.source_member_id,
                        "subject_label": "妈妈",
                    },
                )
            )

    async def restrictions():
        async with sessions() as session:
            run = await session.get(AgentRun, context.run_id)
            return await service.memory_restrictions_for_plan(
                session, run, binding, {"sources": {"members": {"mom": {"health_member_id": mom}}}}
            )

    operations = [
        lambda: service.process_memory_for_run(context, purpose="consultation"),
        lambda: service.memory_context_for_run(context),
        lambda: member_memory_for_run(context),
        restrictions,
    ]
    if valid_count > 300:
        for operation in operations:
            with pytest.raises(HealthVisionError, match="memory_capacity"):
                await operation()
    else:
        assert (await operations[0]())["saved"] == []
        assert len((await operations[1]())["memories"]) == 1
        assert len((await operations[2]())["memories"]) == 1
        assert await operations[3]() == []


@pytest.mark.parametrize("updates_existing", [False, True])
async def test_memory_write_capacity_is_atomic(family_profile_http, monkeypatch, updates_existing):
    """容量边界允许更新，新增超额时事实、版本与处理收据一起回滚。"""
    client, sessions, identities = family_profile_http
    context, binding, mom, family_id = await memory_run_fixture(client, sessions, identities["self"])
    extraction_model(
        monkeypatch,
        binding,
        [
            {
                "member_id": mom,
                "quote": "我妈妈不爱吃香菜",
                "subject_quote": "我妈妈",
                "kind": "preference",
                "fact_key": "current_0" if updates_existing else "new_coriander",
                "meaning": "不爱吃香菜",
                "ongoing": True,
            }
        ],
    )
    async with sessions.begin() as session:
        link = await session.get(HealthFamilyProfileLink, mom)
        for index in range(300):
            session.add(
                HealthMemoryFact(
                    id=f"capacity-{index:03}",
                    actor_uid="self",
                    member_id=mom,
                    fact_key=f"current_{index}",
                    content="原偏好",
                    kind="preference",
                    version=1,
                    provenance={
                        "family_id": family_id,
                        "source_member_id": link.source_member_id,
                        "subject_label": "妈妈",
                    },
                )
            )
    if updates_existing:
        result = await service.process_memory_for_run(context, purpose="consultation")
        assert result["saved"] == [{"memory_id": "capacity-000", "version": 2}]
        assert len((await service.memory_context_for_run(context))["memories"]) == 300
    else:
        with pytest.raises(HealthVisionError, match="memory_capacity"):
            await service.process_memory_for_run(context, purpose="consultation")
    async with sessions() as session:
        facts = list((await session.scalars(select(HealthMemoryFact))).all())
        assert len(facts) == 300
        assert (await session.get(HealthMemoryFact, "capacity-000")).version == (2 if updates_existing else 1)
        assert bool(await session.get(HealthMemoryProcessing, (context.request_id, "self"))) is updates_existing

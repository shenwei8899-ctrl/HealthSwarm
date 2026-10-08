"""真实 HTTP、PostgreSQL、MinIO 和运行 worker 的健康识图验收。"""

import asyncio
import hashlib
import io
import json
import math
import os
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import delete, select

from yuxi.services.health_vision_service import PRIVATE_BUCKET
from yuxi.services.task_service import tasker
from yuxi.storage.minio import get_minio_client
from yuxi.storage.minio.client import StorageError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import (
    User,
    TaskRecord,
    Department,
    Conversation,
    ConversationStats,
    Project,
    Message,
    AgentRun,
    AgentRunRequest,
    MessageFeedback,
    ToolCall,
)
from yuxi.storage.postgres.models_health import (
    DietLog,
    MealFeedback,
    FamilyMember,
    FoodRecord,
    HealthGrant,
    HealthObservation,
    HealthProcessingConsent,
    HealthConsultation,
    HealthFeedbackConversation,
    HealthRuleSnapshot,
    HealthProfessionalReviewer,
    HealthMealPlan,
    HealthMealPlanPreview,
    HealthInitialPlanPreview,
    HealthMealPlanRevision,
    HealthMemoryFact,
    HealthMemoryRevision,
    NutritionCalculation,
    NutritionEvidence,
    NutritionEvidenceCitation,
    PrivateUpload,
    PortionReference,
    RecipeVersion,
    VisionConfirmation,
    VisionDraft,
    VisionJob,
    VisionRevision,
)
from yuxi.utils.auth_utils import AuthUtils
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ROOT = "/api/health/v1"


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本文件没有创建沙盒；不清理别人的运行数据。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """健康数据从不进入知识库。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """由 fixture 在所属异步循环检查当前 Schema。"""


@pytest_asyncio.fixture
async def health_http():
    """只创建三个唯一测试账号，并按精确外键清理本次测试资源。"""
    pg_manager.initialize()
    await pg_manager.require_current_schema()
    identities = []
    async with pg_manager.get_async_session_context() as session:
        department = Department(name=f"pytest_health_dept_{uuid4().hex[:16]}")
        session.add(department)
        await session.flush()
        department_id = department.id
        for role in ("user", "user", "admin"):
            uid = f"pytest_health_{uuid4().hex}"
            user = User(
                username=uid, uid=uid, role=role, password_hash="not-a-login-password", department_id=department_id
            )
            session.add(user)
            await session.flush()
            identities.append(
                {
                    "uid": uid,
                    "headers": {"Authorization": f"Bearer {AuthUtils.create_access_token({'sub': str(user.id)})}"},
                }
            )
    try:
        async with httpx.AsyncClient(
            base_url=os.getenv("TEST_BASE_URL", "http://127.0.0.1:5050"), timeout=60
        ) as client:
            yield client, identities
    finally:
        try:
            await cleanup_health_test_resources(identities, department_id)
        finally:
            await pg_manager.close()


async def cleanup_health_test_resources(identities, department_id):
    """只在本轮 Task 全部终态且无 lease 后清理精确测试资源。"""
    uids = [item["uid"] for item in identities]
    async with pg_manager.get_async_session_context() as session:
        owned_tasks = list(
            (
                await session.scalars(
                    select(TaskRecord)
                    .join(VisionJob, VisionJob.task_id == TaskRecord.id)
                    .where(VisionJob.actor_uid.in_(uids))
                )
            ).all()
        )
        active_ids = [
            task.id
            for task in owned_tasks
            if task.status not in {"success", "failed", "cancelled"}
            or task.worker_id is not None
            or task.lease_expires_at is not None
        ]
        if active_ids:
            raise RuntimeError(f"健康测试任务尚未收敛，保留账号、PG 及对象诊断数据：{active_ids}")
        checkpoint_threads = list(
            (await session.scalars(select(Conversation.thread_id).where(Conversation.uid.in_(uids)))).all()
        )
        member_ids = list(
            (await session.scalars(select(FamilyMember.id).where(FamilyMember.owner_uid.in_(uids)))).all()
        )
        jobs = list((await session.scalars(select(VisionJob).where(VisionJob.member_id.in_(member_ids)))).all())
        task_ids = [job.task_id for job in jobs]
        draft_ids = list(
            (await session.scalars(select(VisionDraft.id).where(VisionDraft.member_id.in_(member_ids)))).all()
        )
        objects = []
        for upload in (
            await session.scalars(select(PrivateUpload).where(PrivateUpload.member_id.in_(member_ids)))
        ).all():
            objects += [upload.original_key, *[page["object_key"] for page in upload.pages]]
        for draft in (await session.scalars(select(VisionDraft).where(VisionDraft.id.in_(draft_ids)))).all():
            if draft.raw_result_key:
                objects.append(draft.raw_result_key)
        for job in jobs:
            snapshot = job.input_snapshot
            result_keys = [*snapshot.get("raw_result_keys", []), snapshot.get("published_result_key")]
            for key in result_keys:
                if key and key.startswith(f"results/{job.task_id}/"):
                    objects.append(key)
        for model in (HealthMealPlanRevision, HealthMealPlan, HealthMealPlanPreview, HealthInitialPlanPreview):
            await session.execute(delete(model).where(model.actor_uid.in_(uids)))
        await session.execute(delete(HealthRuleSnapshot).where(HealthRuleSnapshot.imported_by.in_(uids)))
        await session.execute(
            delete(HealthProfessionalReviewer).where(
                (HealthProfessionalReviewer.reviewer_uid.in_(uids))
                | (HealthProfessionalReviewer.registered_by.in_(uids))
            )
        )
        await session.execute(delete(MealFeedback).where(MealFeedback.actor_uid.in_(uids)))
        await session.execute(
            delete(HealthFeedbackConversation).where(
                HealthFeedbackConversation.conversation_id.in_(
                    select(HealthConsultation.conversation_id).where(HealthConsultation.member_id.in_(member_ids))
                )
            )
        )
        for model in (HealthObservation, DietLog):
            await session.execute(delete(model).where(model.member_id.in_(member_ids)))
        await session.execute(delete(NutritionEvidenceCitation).where(NutritionEvidenceCitation.actor_uid.in_(uids)))
        await session.execute(delete(NutritionEvidence).where(NutritionEvidence.published_by.in_(uids)))
        await session.execute(delete(HealthConsultation).where(HealthConsultation.member_id.in_(member_ids)))
        from yuxi.storage.postgres.models_health import HealthWeightUse, HealthBloodPressureUse

        await session.execute(delete(HealthWeightUse).where(HealthWeightUse.member_id.in_(member_ids)))
        await session.execute(delete(HealthBloodPressureUse).where(HealthBloodPressureUse.member_id.in_(member_ids)))
        message_ids = select(Message.id).where(
            Message.conversation_id.in_(select(Conversation.id).where(Conversation.uid.in_(uids)))
        )
        await session.execute(delete(HealthMemoryRevision).where(HealthMemoryRevision.actor_uid.in_(uids)))
        await session.execute(delete(HealthMemoryFact).where(HealthMemoryFact.actor_uid.in_(uids)))
        await session.execute(delete(MessageFeedback).where(MessageFeedback.message_id.in_(message_ids)))
        await session.execute(delete(ToolCall).where(ToolCall.message_id.in_(message_ids)))
        await session.execute(delete(AgentRunRequest).where(AgentRunRequest.uid.in_(uids)))
        await session.execute(
            delete(Message).where(
                Message.conversation_id.in_(select(Conversation.id).where(Conversation.uid.in_(uids)))
            )
        )
        await session.execute(delete(AgentRun).where(AgentRun.uid.in_(uids)))
        conversation_ids = select(Conversation.id).where(Conversation.uid.in_(uids))
        await session.execute(delete(ConversationStats).where(ConversationStats.conversation_id.in_(conversation_ids)))
        await session.execute(delete(Conversation).where(Conversation.uid.in_(uids)))
        await session.execute(delete(Project).where(Project.uid.in_(uids)))
        for model in (VisionConfirmation, VisionRevision, NutritionCalculation):
            await session.execute(delete(model).where(model.draft_id.in_(draft_ids)))
        await session.execute(delete(VisionDraft).where(VisionDraft.id.in_(draft_ids)))
        await session.execute(delete(VisionJob).where(VisionJob.member_id.in_(member_ids)))
        await session.execute(delete(TaskRecord).where(TaskRecord.id.in_(task_ids)))
        for model in (PrivateUpload, HealthProcessingConsent, HealthGrant):
            await session.execute(delete(model).where(model.member_id.in_(member_ids)))
        await session.execute(delete(FamilyMember).where(FamilyMember.id.in_(member_ids)))
        await session.execute(delete(PortionReference).where(PortionReference.published_by.in_(uids)))
        await session.execute(delete(RecipeVersion).where(RecipeVersion.published_by.in_(uids)))
        await session.execute(delete(FoodRecord).where(FoodRecord.published_by.in_(uids)))
        await session.execute(delete(User).where(User.uid.in_(uids)))
        await session.execute(delete(Department).where(Department.id == department_id))
    saver = pg_manager.get_langgraph_checkpointer()
    for thread_id in checkpoint_threads:
        await saver.adelete_thread(thread_id)
        assert await saver.aget_tuple({"configurable": {"thread_id": thread_id}}) is None
    for key in set(objects):
        await get_minio_client().adelete_file(PRIVATE_BUCKET, key)


@pytest.mark.parametrize(
    "status,worker,leased",
    [("running", "synthetic", True), ("failed", "synthetic", False), ("failed", None, True)],
)
async def test_cleanup_retains_owned_unsettled_task_and_private_objects(health_http, status, worker, leased):
    """非终态或残留 owner/lease 阻止整轮清理，保留 PG 和私有图片事实。"""
    client, users = health_http
    member = await create_member(client, users[0]["headers"])
    image = io.BytesIO()
    Image.new("RGB", (512, 512), (44, 180, 91)).save(image, "PNG")
    uploaded = await client.post(
        f"{ROOT}/uploads",
        headers=users[0]["headers"],
        data={"member_id": member, "purpose": "meal"},
        files={"file": ("synthetic-cleanup.png", image.getvalue(), "image/png")},
    )
    assert uploaded.status_code == 201
    upload_id = uploaded.json()["upload_id"]
    async with pg_manager.get_async_session_context() as session:
        department_id = await session.scalar(select(User.department_id).where(User.uid == users[0]["uid"]))
        task = await tasker.create_in_session(
            session, name="synthetic cleanup guard", task_type="meal_recognize_v1", payload={}
        )
        task_id = task.id
        task = await session.get(TaskRecord, task_id)
        task.status, task.worker_id = status, worker
        task.lease_expires_at = utc_now_naive() + timedelta(minutes=10) if leased else None
        session.add(
            VisionJob(
                id=str(uuid4()),
                task_id=task_id,
                actor_uid=users[0]["uid"],
                member_id=member,
                kind="meal",
                request_id=str(uuid4()),
                fingerprint="0" * 64,
                upload_ids=[upload_id],
                input_snapshot={},
            )
        )
    try:
        async with pg_manager.get_async_session_context() as session:
            persisted = await session.get(TaskRecord, task_id)
            assert (persisted.status, persisted.worker_id) == (status, worker)
            assert (persisted.lease_expires_at is not None) is leased
        with pytest.raises(RuntimeError, match="保留账号、PG 及对象诊断数据"):
            await cleanup_health_test_resources(users, department_id)
        async with pg_manager.get_async_session_context() as session:
            assert await session.get(TaskRecord, task_id) is not None
            assert await session.get(FamilyMember, member) is not None
            assert await session.get(PrivateUpload, upload_id) is not None
            assert await session.scalar(select(User).where(User.uid == users[0]["uid"])) is not None
        preview = await client.get(f"{ROOT}/uploads/{upload_id}/preview?page_index=0", headers=users[0]["headers"])
        assert preview.status_code == 200 and Image.open(io.BytesIO(preview.content)).size == (512, 512)
    finally:
        async with pg_manager.get_async_session_context() as session:
            task = await session.get(TaskRecord, task_id)
            task.status, task.worker_id, task.lease_expires_at = "failed", None, None


async def test_cleanup_removes_all_owned_raw_receipts_but_preserves_foreign_namespace(health_http):
    """旧解析 receipt 与尝试文件精确删除，越出所属 Task 的键不得删除。"""
    client, users = health_http
    member = await create_member(client, users[0]["headers"])
    async with pg_manager.get_async_session_context() as session:
        department_id = await session.scalar(select(User.department_id).where(User.uid == users[0]["uid"]))
        task = await tasker.create_in_session(
            session, name="synthetic receipt cleanup", task_type="report_extract_v1", payload={}
        )
        task_id = task.id
        (await session.get(TaskRecord, task_id)).status = "failed"
        own_keys = [f"results/{task_id}/{uuid4()}.json" for _ in range(2)]
        foreign_key = f"results/{uuid4()}/{uuid4()}.json"
        session.add(
            VisionJob(
                id=str(uuid4()),
                task_id=task_id,
                actor_uid=users[0]["uid"],
                member_id=member,
                kind="report",
                request_id=str(uuid4()),
                fingerprint="0" * 64,
                upload_ids=[],
                input_snapshot={"raw_result_keys": [own_keys[0], foreign_key], "published_result_key": own_keys[1]},
            )
        )
    storage = get_minio_client()
    try:
        for key in [*own_keys, foreign_key]:
            await storage.aupload_file(PRIVATE_BUCKET, key, b'{"synthetic":true}', "application/json")
        await cleanup_health_test_resources(users, department_id)
        async with pg_manager.get_async_session_context() as session:
            assert await session.get(TaskRecord, task_id) is None
            assert await session.scalar(select(VisionJob).where(VisionJob.task_id == task_id)) is None
        for key in own_keys:
            with pytest.raises(StorageError, match="不存在"):
                await storage.adownload_file(PRIVATE_BUCKET, key)
        assert await storage.adownload_file(PRIVATE_BUCKET, foreign_key) == b'{"synthetic":true}'
    finally:
        # 外部命名空间样本也由本用例创建；在验证保留后按精确键清理。
        for key in [*own_keys, foreign_key]:
            await storage.adelete_file(PRIVATE_BUCKET, key)


async def test_consultation_binding_concurrent_replay_is_private_and_immutable(health_http):
    """真实 HTTP 创建、并发重放及 PG 唯一绑定，不产生模型执行。"""
    client, users = health_http
    owner, stranger, admin = users
    member = await create_member(client, owner["headers"])
    other_member = await create_member(client, owner["headers"])
    request_id = str(uuid4())
    headers = {**owner["headers"], "Idempotency-Key": request_id}
    path = f"{ROOT}/members/{member}/consultations"
    responses = await asyncio.gather(
        *[client.post(path, headers=headers, json={"client_request_id": request_id}) for _ in range(4)]
    )
    assert all(response.status_code == 201 for response in responses), [r.text for r in responses]
    bound = responses[0].json()
    assert all(r.json() == bound for r in responses)
    assert bound["member_id"] == member and bound["agent_slug"] == "health-consultation"
    conflict = await client.post(
        f"{ROOT}/members/{other_member}/consultations", headers=headers, json={"client_request_id": request_id}
    )
    assert conflict.status_code == 409 and conflict.json()["code"] == "request_conflict"
    for actor in (stranger, admin):
        denied = await client.post(
            path, headers={**actor["headers"], "Idempotency-Key": request_id}, json={"client_request_id": request_id}
        )
        assert denied.status_code == 404
    async with pg_manager.get_async_session_context() as session:
        bindings = (
            await session.scalars(select(HealthConsultation).where(HealthConsultation.actor_uid == owner["uid"]))
        ).all()
        assert len(bindings) == 1 and bindings[0].member_id == member
        conversation = await session.get(Conversation, bindings[0].conversation_id)
        assert conversation.thread_id == bound["thread_id"] and conversation.uid == owner["uid"]
        assert conversation.extra_metadata.get("member_id") is None
        assert len((await session.scalars(select(Project).where(Project.uid == owner["uid"]))).all()) == 1
    revoked = await client.put(
        f"{ROOT}/members/{member}/grants", headers=owner["headers"], json={"actor_uid": owner["uid"], "scopes": []}
    )
    assert revoked.status_code == 200
    denied = await client.post(path, headers=headers, json={"client_request_id": request_id})
    assert denied.status_code == 404


async def test_closed_consultation_rejects_requests_before_message_queue_or_run(health_http):
    """云未配置、未绑定及多模态替代入口均不能产生 Message/Request/Run。"""
    client, users = health_http
    owner = users[0]
    config = (await client.get(f"{ROOT}/configuration", headers=owner["headers"])).json()
    assert not config["consultation"]["available"], "此验收只在云咨询关闭环境执行"
    member = await create_member(client, owner["headers"])
    request_id = str(uuid4())
    bound = await client.post(
        f"{ROOT}/members/{member}/consultations",
        headers={**owner["headers"], "Idempotency-Key": request_id},
        json={"client_request_id": request_id},
    )
    assert bound.status_code == 201
    thread_id = bound.json()["thread_id"]
    for overrides, expected_status in (
        ({}, 503),
        ({"model_spec": "unapproved/default"}, 503),
        ({"thread_id": str(uuid4())}, 404),
        ({"image_content": "c3ludGhldGlj"}, 422),
        ({"resume": {"answer": "synthetic"}}, 422),
    ):
        response = await client.post(
            "/api/agent/runs",
            headers=owner["headers"],
            json={
                "agent_slug": "health-consultation",
                "thread_id": thread_id,
                "query": "解释已确认指标",
                "meta": {"request_id": str(uuid4()), "member_id": str(uuid4())},
                **overrides,
            },
        )
        assert response.status_code == expected_status, response.text
    async with pg_manager.get_async_session_context() as session:
        conversation = await session.scalar(select(Conversation).where(Conversation.thread_id == thread_id))
        assert not (await session.scalars(select(Message).where(Message.conversation_id == conversation.id))).all()
        for model in (AgentRunRequest, AgentRun):
            assert not (await session.scalars(select(model).where(model.uid == owner["uid"]))).all()
        assert await session.get(HealthProcessingConsent, (member, owner["uid"], "consultation")) is None


async def test_consultation_tools_read_confirmed_records_under_current_pg_lease_and_scopes(health_http, monkeypatch):
    """真实 PG 绑定及正式数据回读；审批状态只在测试进程替换，不启用云配置。"""
    from yuxi.services import health_consultation_service as consultation_service
    from yuxi.services.health_vision_types import HealthVisionError
    from unittest.mock import AsyncMock

    client, users = health_http
    owner = users[0]
    headers = owner["headers"]
    member = await create_member(client, headers)
    request_key = str(uuid4())
    bound = await client.post(
        f"{ROOT}/members/{member}/consultations",
        headers={**headers, "Idempotency-Key": request_key},
        json={"client_request_id": request_key},
    )
    assert bound.status_code == 201
    thread_id = bound.json()["thread_id"]
    draft_response = await client.post(
        f"{ROOT}/manual-drafts",
        headers=headers,
        json={"member_id": member, "kind": "report", "report": {"fields": [field()]}},
    )
    assert draft_response.status_code == 201
    draft = draft_response.json()
    data, key = confirmation()
    confirmed = await client.post(
        f"{ROOT}/report-extractions/{draft['id']}/confirm", headers={**headers, **key}, json=data
    )
    assert confirmed.status_code == 200
    pending = await client.post(
        f"{ROOT}/manual-drafts",
        headers=headers,
        json={"member_id": member, "kind": "report", "report": {"fields": [{**field(), "name": "未确认不得外发"}]}},
    )
    assert pending.status_code == 201
    snapshot = {"model": "synthetic/fixed", "processor": "synthetic-fingerprint", "policy_version": "synthetic-policy"}
    configuration = {"policy_version": snapshot["policy_version"], "consultation": {"available": True, **snapshot}}
    monkeypatch.setattr(
        consultation_service.health_vision_service, "configuration", AsyncMock(return_value=configuration)
    )
    run_id, run_request_id = str(uuid4()), str(uuid4())
    context = SimpleNamespace(
        uid=owner["uid"],
        thread_id=thread_id,
        run_id=run_id,
        request_id=run_request_id,
        worker_id="synthetic-attempt",
        model=snapshot["model"],
    )
    async with pg_manager.get_async_session_context() as session:
        conversation = await session.scalar(select(Conversation).where(Conversation.thread_id == thread_id))
        session.add(
            HealthProcessingConsent(
                member_id=member,
                actor_uid=owner["uid"],
                purpose="consultation",
                processor=snapshot["processor"],
                policy_version=snapshot["policy_version"],
            )
        )
        session.add(
            AgentRun(
                id=run_id,
                request_id=run_request_id,
                uid=owner["uid"],
                agent_slug="health-consultation",
                conversation_thread_id=thread_id,
                conversation_id=conversation.id,
                runtime_scope_id=thread_id,
                status="running",
                worker_id=context.worker_id,
                lease_expires_at=utc_now_naive() + timedelta(minutes=5),
                input_payload={"model_spec": snapshot["model"], "health_processing": snapshot},
            )
        )
    result = await consultation_service.confirmed_consultation_records(context, "report")
    assert len(result["records"]) == 1
    record = result["records"][0]
    assert record["record_id"] == confirmed.json()["target_ids"][0]
    assert record["name"] == "测试指标" and record["value_numeric"] == "6.8" and record["unit_raw"] == "mmol/L"
    assert "evidence" not in record and "value_raw" not in record
    assert result["full_health_profile_available"] is False
    from langchain_core.messages import ToolMessage

    history = [ToolMessage(name="get_confirmed_profile", tool_call_id="synthetic-call", content=json.dumps(result))]
    await consultation_service.require_consultation_attempt(context, history)
    error_history = [
        ToolMessage(
            name="get_confirmed_profile",
            tool_call_id="synthetic-invalid-call",
            status="error",
            content="Error invoking tool: Extra inputs are not permitted",
        )
    ]
    await consultation_service.require_consultation_attempt(context, error_history)
    with pytest.raises(HealthVisionError, match="consultation_history_invalid"):
        await consultation_service.require_consultation_attempt(
            context,
            [ToolMessage(name="get_confirmed_profile", tool_call_id="synthetic-broken-call", content="not-json")],
        )

    from yuxi.agents.buildin.health_consultation import graph as graph_module
    from yuxi.agents.context import BaseContext
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage, HumanMessage

    model_calls = []

    class SyntheticModel(GenericFakeChatModel):
        """实际图联调只产生固定合成响应，没有网络传输。"""

        def bind_tools(self, tools, **kwargs):
            """保留固定工具协议，不连接任何供应商。"""
            return self

        def _generate(self, messages, *args, **kwargs):
            """独立记录模型入口，失效来源必须阻止下一次调用。"""
            model_calls.append(messages)
            return super()._generate(messages, *args, **kwargs)

    model = SyntheticModel(
        messages=iter(
            [
                AIMessage(
                    content="", tool_calls=[{"id": "synthetic-call", "name": "get_confirmed_profile", "args": {}}]
                ),
                AIMessage(content="解释合成已确认指标"),
                AIMessage(content="这次调用不得发生"),
            ]
        )
    )
    monkeypatch.setattr(graph_module, "load_chat_model", lambda **kwargs: model)
    monkeypatch.setattr(graph_module.SteerMiddleware, "_jump_if_steer_requested", AsyncMock(return_value=None))
    backend = graph_module.HealthConsultationAgent()
    graph_context = BaseContext(**vars(context))
    graph_context._runtime_prepared = True
    graph = await backend.get_graph(context=graph_context)
    graph_config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 20}
    await graph.ainvoke(
        {"messages": [HumanMessage(content="解释合成已确认指标")]}, config=graph_config, context=graph_context
    )
    assert len(model_calls) == 2
    saved_checkpoint = await pg_manager.get_langgraph_checkpointer().aget_tuple(graph_config)
    saved_messages = saved_checkpoint.checkpoint["channel_values"]["messages"]
    assert saved_messages[-1].content == "解释合成已确认指标"
    saved_tools = [message for message in saved_messages if isinstance(message, ToolMessage)]
    assert len(saved_tools) == 1
    assert json.loads(saved_tools[0].content)["records"][0]["record_id"] == record["record_id"]
    context.worker_id = "stale-attempt"
    with pytest.raises(HealthVisionError, match="execution_not_owned"):
        await consultation_service.confirmed_consultation_records(context, "report")
    context.worker_id = "synthetic-attempt"
    configuration["consultation"]["processor"] = "changed-fingerprint"
    with pytest.raises(HealthVisionError, match="policy_changed"):
        await consultation_service.confirmed_consultation_records(context, "report")
    configuration["consultation"]["processor"] = snapshot["processor"]
    async with pg_manager.get_async_session_context() as session:
        saved = await session.get(VisionDraft, draft["id"])
        saved.review_status = "invalidated"
    assert (await consultation_service.confirmed_consultation_records(context, "report"))["records"] == []
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await consultation_service.require_consultation_attempt(context, history)
    with pytest.raises(HealthVisionError, match="source_invalidated"):
        await graph.ainvoke(
            {"messages": [HumanMessage(content="继续解释上一记录")]}, config=graph_config, context=graph_context
        )
    assert len(model_calls) == 2  # checkpoint 保留旧引用，但不再发给模型。
    async with pg_manager.get_async_session_context() as session:
        grant = await session.get(HealthGrant, (member, owner["uid"]))
        grant.scopes = ["ai_use", "diet_edit"]
    with pytest.raises(HealthVisionError, match="not_found"):
        await consultation_service.require_consultation_attempt(context)


async def test_consultation_private_history_memory_dashboard_and_sse_recheck_revocation(health_http, monkeypatch):
    """健康内容不能进入通用记忆/管理正文，存量 SSE 的下一载荷也重查 grant。"""
    from yuxi.repositories.conversation_repository import ConversationRepository
    from yuxi.services import agent_run_service

    client, users = health_http
    owner, _, admin = users
    member = await create_member(client, owner["headers"])
    request_id = str(uuid4())
    response = await client.post(
        f"{ROOT}/members/{member}/consultations",
        headers={**owner["headers"], "Idempotency-Key": request_id},
        json={"client_request_id": request_id},
    )
    assert response.status_code == 201
    thread_id, run_id = response.json()["thread_id"], str(uuid4())
    marker = "synthetic-health-private-content"
    async with pg_manager.get_async_session_context() as session:
        administrator = await session.scalar(select(User).where(User.uid == admin["uid"]))
        administrator.role = "superadmin"
        conversation = await session.scalar(select(Conversation).where(Conversation.thread_id == thread_id))
        message = Message(conversation_id=conversation.id, role="assistant", content=marker, message_type="text")
        session.add(message)
        await session.flush()
        session.add(MessageFeedback(message_id=message.id, uid=owner["uid"], rating="dislike", reason=marker))
        session.add(
            AgentRun(
                id=run_id,
                request_id=str(uuid4()),
                uid=owner["uid"],
                agent_slug="health-consultation",
                conversation_thread_id=thread_id,
                conversation_id=conversation.id,
                runtime_scope_id=thread_id,
                status="completed",
                output_message_id=message.id,
                input_payload={},
                error_message=marker,
            )
        )
    for suffix in ("history", "state?include_messages=true"):
        before = await client.get(f"/api/chat/thread/{thread_id}/{suffix}", headers=owner["headers"])
        assert before.status_code == 200, before.text
    feedback_path = f"/api/chat/message/{message.id}/feedback"
    before_feedback = await client.get(feedback_path, headers=owner["headers"])
    assert before_feedback.status_code == 200 and before_feedback.json()["feedback"]["reason"] == marker
    before_cancel = await client.post(f"/api/agent/runs/{run_id}/cancel", headers=owner["headers"])
    assert before_cancel.status_code == 200 and before_cancel.json()["run"]["error_message"] == marker
    stranger_feedback = await client.get(feedback_path, headers=users[1]["headers"])
    assert stranger_feedback.status_code == 404 and marker not in stranger_feedback.text
    async with pg_manager.get_async_session_context() as session:
        repository = ConversationRepository(session)
        assert (await repository.search_memory_messages(uid=owner["uid"], query=marker))["items"] == []
        with pytest.raises(ValueError, match="不存在或不可见"):
            await repository.read_memory_messages(uid=owner["uid"], thread_id=thread_id)
    details = await client.get(f"/api/dashboard/conversations/{thread_id}", headers=admin["headers"])
    assert details.status_code == 404
    feedback = await client.get(
        "/api/dashboard/feedbacks", headers=admin["headers"], params={"agent_id": "health-consultation"}
    )
    assert feedback.status_code == 200 and feedback.json() == []
    from unittest.mock import AsyncMock

    events = [
        {"seq": "1-0", "event_type": "message", "payload": {"synthetic": marker}},
        {"seq": "2-0", "event_type": "message", "payload": {"synthetic": marker + "-second"}},
    ]
    monkeypatch.setattr(agent_run_service, "list_run_stream_events", AsyncMock(return_value=events))
    stream = agent_run_service.stream_agent_run_events(run_id=run_id, after_seq="0-0", current_uid=owner["uid"])
    assert marker in await anext(stream)
    revoked = await client.put(
        f"{ROOT}/members/{member}/grants", headers=owner["headers"], json={"actor_uid": owner["uid"], "scopes": []}
    )
    assert revoked.status_code == 200
    denied_feedback = await client.get(feedback_path, headers=owner["headers"])
    assert denied_feedback.status_code == 404 and marker not in denied_feedback.text
    denied_submission = await client.post(
        feedback_path, headers=owner["headers"], json={"rating": "like", "reason": "synthetic-revoked"}
    )
    assert denied_submission.status_code == 404 and marker not in denied_submission.text
    next_payload = await anext(stream)
    assert marker not in next_payload and "无权访问" in next_payload
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    for suffix in ("history", "state?include_messages=true"):
        denied = await client.get(f"/api/chat/thread/{thread_id}/{suffix}", headers=owner["headers"])
        assert denied.status_code == 404 and marker not in denied.text
    denied = await client.get(f"/api/agent/runs/{run_id}", headers=owner["headers"])
    assert denied.status_code == 404 and marker not in denied.text
    denied_cancel = await client.post(f"/api/agent/runs/{run_id}/cancel", headers=owner["headers"])
    assert denied_cancel.status_code == 404 and marker not in denied_cancel.text
    denied_result = await client.get(f"/api/agent/runs/{run_id}/result", headers=owner["headers"])
    assert denied_result.status_code == 200 and denied_result.json()["output"] == ""
    assert denied_result.json()["error"]["type"] == "run_not_found" and marker not in denied_result.text
    async with pg_manager.get_async_session_context() as session:
        saved = await session.scalar(select(Message).where(Message.conversation_id == conversation.id))
        assert saved.content == marker  # 撤权拦截读取，不静默抹掉持久历史。
        assert (await session.get(AgentRun, run_id)).status == "completed"


async def test_plain_thread_creation_rejects_health_roles_before_any_persistence(health_http):
    """普通入口拒绝全部健康角色，绑定入口和普通聊天保持可用。"""
    client, users = health_http
    owner = users[0]
    for slug in ("health-consultation", "health-meal-planner", "health-diet-analyst", "health-quality"):
        response = await client.post(
            "/api/chat/thread", headers=owner["headers"], json={"agent_id": slug, "request_id": str(uuid4())}
        )
        assert response.status_code == 422 and "健康识图" in response.json()["detail"], response.text
    async with pg_manager.get_async_session_context() as session:
        assert await session.scalar(select(Conversation.id).where(Conversation.uid == owner["uid"])) is None
        assert await session.scalar(select(Project.id).where(Project.uid == owner["uid"])) is None
        assert await session.scalar(select(AgentRun.id).where(AgentRun.uid == owner["uid"])) is None
    ordinary = await client.post(
        "/api/chat/thread", headers=owner["headers"], json={"agent_id": "default-chatbot", "request_id": str(uuid4())}
    )
    assert ordinary.status_code == 200, ordinary.text
    async with pg_manager.get_async_session_context() as session:
        ordinary_row = await session.scalar(select(Conversation).where(Conversation.thread_id == ordinary.json()["id"]))
        assert ordinary_row.agent_id == "default-chatbot"
    member = await create_member(client, owner["headers"])
    key = str(uuid4())
    bound = await client.post(
        f"{ROOT}/members/{member}/consultations",
        headers={**owner["headers"], "Idempotency-Key": key},
        json={"client_request_id": key},
    )
    assert bound.status_code == 201, bound.text
    async with pg_manager.get_async_session_context() as session:
        row = await session.scalar(select(Conversation).where(Conversation.thread_id == bound.json()["thread_id"]))
        binding = await session.get(HealthConsultation, row.id)
        assert binding.member_id == member and binding.actor_uid == owner["uid"]


async def create_member(client, headers):
    """通过 shipping 路由创建明确授权的合成成员。"""
    response = await client.post(
        f"{ROOT}/members", headers=headers, json={"display_name": "合成测试成员", "authorized": True}
    )
    assert response.status_code == 201
    return response.json()["id"]


async def statistics_upload(client, headers, member, kind="report"):
    """实际上传无身份信息的纯色图片，不启用模型。"""
    buffer = io.BytesIO()
    Image.new("RGB", (512, 512), "white").save(buffer, format="PNG")
    response = await client.post(
        f"{ROOT}/uploads",
        headers=headers,
        data={"member_id": member, "purpose": kind},
        files={"file": ("statistics-synthetic.png", buffer.getvalue(), "image/png")},
    )
    assert response.status_code == 201
    return response.json()["upload_id"]


async def statistics_job(session, uid, member, upload_id, *, number=1, days=0, kind="report"):
    """准备终态 PG 时间点；该只读统计测试不声称经过识图 worker。"""
    created = utc_now_naive() - timedelta(days=days, hours=1)
    task_id, job_id = uuid4().hex, str(uuid4())
    session.add(
        TaskRecord(
            id=task_id,
            name="合成统计任务",
            type="report_extract_v1" if kind == "report" else "meal_recognize_v1",
            status="failed" if number == 1 else "success",
            payload={},
            error="synthetic-private-body",
            created_at=created,
            started_at=created + timedelta(seconds=number),
            completed_at=created + timedelta(seconds=number * 3),
        )
    )
    await session.flush()
    session.add(
        VisionJob(
            id=job_id,
            task_id=task_id,
            actor_uid=uid,
            member_id=member,
            kind=kind,
            request_id=str(uuid4()),
            fingerprint="0" * 64,
            upload_ids=[upload_id],
            input_snapshot={},
            error_code="provider_timeout" if number == 1 else None,
            phase="partial_ready" if kind == "report" and number == 2 else "ready",
            created_at=created,
        )
    )
    await session.flush()
    return job_id, task_id


async def test_statistics_full_window_pg_times_member_kind_grants_and_deleted_sources(health_http):
    """真实 HTTP 回读超过列表上限的 PG 样本，管理员没有成员旁路。"""
    client, users = health_http
    owner, stranger, admin = users
    headers = owner["headers"]
    member = await create_member(client, headers)
    upload_id = await statistics_upload(client, headers, member)
    other_member = await create_member(client, headers)
    other_upload = await statistics_upload(client, headers, other_member)
    meal_upload = await statistics_upload(client, headers, member, "meal")
    async with pg_manager.get_async_session_context() as session:
        for number in range(1, 61):
            await statistics_job(session, owner["uid"], member, upload_id, number=number)
        await statistics_job(session, owner["uid"], member, upload_id, days=35)
        await statistics_job(session, owner["uid"], member, upload_id, days=-2)
        await statistics_job(session, owner["uid"], other_member, other_upload)
        await statistics_job(session, owner["uid"], member, meal_upload, kind="meal")
    path = f"{ROOT}/members/{member}/vision-statistics?kind=report"
    response = await client.get(path, headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert result["tasks"]["sample_count"] == 60
    assert result["tasks"]["queue"] == {"sample_count": 60, "p50_seconds": 30, "p95_seconds": 57}
    assert result["tasks"]["execution"] == {"sample_count": 60, "p50_seconds": 60, "p95_seconds": 114}
    assert result["tasks"]["failure_codes"] == {"provider_timeout": 1}
    assert result["tasks"]["partial_report_count"] == 1
    assert result["cost"]["amount"] is None and result["reviews"]["modification_rate_percent"] is None
    assert "synthetic-private-body" not in response.text and upload_id not in response.text
    async with pg_manager.get_async_session_context() as session:
        job = await session.scalar(
            select(VisionJob).where(VisionJob.member_id == member, VisionJob.error_code == "provider_timeout")
        )
        saved_task = await session.get(TaskRecord, job.task_id)
        assert saved_task.error == "synthetic-private-body"
        assert (saved_task.started_at - saved_task.created_at).total_seconds() == 1
        assert (saved_task.completed_at - saved_task.started_at).total_seconds() == 2
    assert (await client.get(path)).status_code == 401
    for identity in (stranger, admin):
        assert (await client.get(path, headers=identity["headers"])).status_code == 404
    assert (
        await client.get(f"{ROOT}/members/{uuid4()}/vision-statistics?kind=report", headers=headers)
    ).status_code == 404
    assert (
        await client.get(f"{ROOT}/members/{member}/vision-statistics?kind=other", headers=headers)
    ).status_code == 422
    assert (
        await client.put(
            f"{ROOT}/members/{member}/grants",
            headers=headers,
            json={"actor_uid": stranger["uid"], "scopes": ["report_view"]},
        )
    ).status_code == 200
    assert (await client.get(path, headers=stranger["headers"])).json()["tasks"]["sample_count"] == 60
    assert (
        await client.get(f"{ROOT}/members/{member}/vision-statistics?kind=meal", headers=stranger["headers"])
    ).status_code == 404
    assert (
        await client.put(
            f"{ROOT}/members/{member}/grants", headers=headers, json={"actor_uid": stranger["uid"], "scopes": []}
        )
    ).status_code == 200
    assert (await client.get(path, headers=stranger["headers"])).status_code == 404
    assert (await client.delete(f"{ROOT}/uploads/{upload_id}", headers=headers)).status_code == 200
    assert (await client.get(path, headers=headers)).json()["tasks"]["sample_count"] == 0
    assert (await client.get(f"{ROOT}/members/{member}/vision-statistics?kind=meal", headers=headers)).json()["tasks"][
        "sample_count"
    ] == 1


async def test_statistics_actual_confirmations_manual_and_pending_are_not_model_corrections(health_http):
    """修订、确认及营养通过真实接口；合成识别初始候选显式写入 PG。"""
    client, users = health_http
    headers, uid = users[0]["headers"], users[0]["uid"]
    member = await create_member(client, headers)
    upload_id = await statistics_upload(client, headers, member)
    created = await client.post(
        f"{ROOT}/manual-drafts",
        headers=headers,
        json={"member_id": member, "kind": "report", "report": {"fields": [field(), field(), field()]}},
    )
    assert created.status_code == 201
    draft = created.json()
    original = deepcopy(draft["payload"])
    for index, item in enumerate(original["fields"]):
        item.update(
            source="ocr", evidence={"page_index": 0, "block_id": f"p0_b{index}", "raw_text": "合成原文", "bbox": None}
        )
    async with pg_manager.get_async_session_context() as session:
        job_id, _ = await statistics_job(session, uid, member, upload_id, number=3)
        record = await session.get(VisionDraft, draft["id"])
        record.job_id, record.model_version = job_id, "synthetic-model"
        record.original_payload, record.payload = original, deepcopy(original)
        (await session.get(VisionJob, job_id)).result_id = record.id
    revised = deepcopy(original)
    revised["fields"][0].update(observed_at="2026-10-04", fasting="yes")
    revised["fields"][1].update(value_raw="7.1", value_numeric="7.1")
    revised["fields"][2]["excluded"] = True
    revised["fields"].append(field())
    path = f"{ROOT}/report-extractions/{draft['id']}"
    patched = await client.patch(
        path, headers={**headers, "If-Match": '"1"'}, json={"version": 1, "reason": "合成纠错", "report": revised}
    )
    assert patched.status_code == 200, patched.json()
    stats_path = f"{ROOT}/members/{member}/vision-statistics?kind=report"
    assert (await client.get(stats_path, headers=headers)).json()["reviews"]["confirmed_drafts"] == 0
    data, key = confirmation(2)
    assert (await client.post(f"{path}/confirm", headers={**headers, **key}, json=data)).status_code == 200
    for confirmed in (True, False):
        manual = await client.post(
            f"{ROOT}/manual-drafts",
            headers=headers,
            json={"member_id": member, "kind": "report", "report": {"fields": [field()]}},
        )
        assert manual.status_code == 201
        if confirmed:
            data, key = confirmation()
            assert (
                await client.post(
                    f"{ROOT}/report-extractions/{manual.json()['id']}/confirm", headers={**headers, **key}, json=data
                )
            ).status_code == 200
    result = (await client.get(stats_path, headers=headers)).json()["reviews"]
    assert result == {
        "confirmed_drafts": 2,
        "model_drafts": 1,
        "original_items": 3,
        "modified_items": 1,
        "excluded_items": 1,
        "added_items": 1,
        "modification_rate_percent": 33.33,
    }
    async with pg_manager.get_async_session_context() as session:
        saved = await session.get(VisionDraft, draft["id"])
        assert saved.original_payload["fields"][1]["value_raw"] == "6.8"
        assert saved.payload["fields"][1]["value_raw"] == "7.1" and saved.review_status == "confirmed"
        observations = list(
            (await session.scalars(select(HealthObservation).where(HealthObservation.member_id == member))).all()
        )
        assert len(observations) == 4 and sum(item.snapshot["value_raw"] == "7.1" for item in observations) == 1
    meal = await client.post(
        f"{ROOT}/manual-drafts",
        headers=headers,
        json={
            "member_id": member,
            "kind": "meal",
            "meal": {
                "meal_type": "lunch",
                "eaten_at": "2026-10-04T12:00:00+08:00",
                "items": [{"item_id": str(uuid4()), "name": "合成未知食物"}],
            },
        },
    )
    assert meal.status_code == 201
    meal_path = f"{ROOT}/meal-drafts/{meal.json()['id']}"
    calculation = await client.post(f"{meal_path}/calculate", headers=headers, json={"version": 1})
    assert calculation.status_code == 200 and calculation.json()["complete"] is False
    data, key = confirmation(calculation_id=calculation.json()["calculation_id"], accept_incomplete=True)
    assert (await client.post(f"{meal_path}/confirm", headers={**headers, **key}, json=data)).status_code == 200
    nutrition = (await client.get(f"{ROOT}/members/{member}/vision-statistics?kind=meal", headers=headers)).json()
    assert nutrition["nutrition"] == {
        "sample_count": 1,
        "incomplete_count": 1,
        "incomplete_rate_percent": 100,
        "portion_sources": {"unknown": 1},
    }
    assert nutrition["reviews"]["modification_rate_percent"] is None
    assert (await client.delete(f"{ROOT}/uploads/{upload_id}", headers=headers)).status_code == 200
    assert (await client.get(stats_path, headers=headers)).json()["reviews"]["confirmed_drafts"] == 1


def synthetic_pdf(page_count=3, *, encrypted=False, width=120, height=160):
    """中心颜色区分页序，左下黑标区分方向；不包含患者数据。"""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject

    writer = PdfWriter()
    writer.add_metadata({"/Author": "synthetic-private-metadata"})
    for index in range(page_count):
        page = writer.add_blank_page(width=width, height=height)
        stream = DecodedStreamObject()
        color = ("1 0 0", "0 1 0", "0 0 1")[index % 3]
        stream.set_data(f"q {color} rg 20 20 {width - 40} {height - 40} re f 0 0 0 rg 25 25 10 10 re f Q".encode())
        page.replace_contents(stream)
        page.rotate((0, 90, 270)[index % 3])
    if encrypted:
        writer.encrypt("synthetic-fixture-only")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


async def test_multipage_pdf_upload_keeps_order_private_original_transforms_and_deletes_every_page(health_http):
    """发布路由逐页回读 PDF、PNG、PG 归属与删除，独立于真实 OCR。"""
    client, users = health_http
    owner, stranger, admin = users
    headers = owner["headers"]
    member = await create_member(client, headers)
    original = synthetic_pdf()
    response = await client.post(
        f"{ROOT}/uploads",
        headers=headers,
        data={"member_id": member, "purpose": "report", "rotation": "90", "deskew_angle": "-2.5"},
        # 文件名和声明 MIME 均故意不符，实际字节类型才是 Owner。
        files={"file": ("synthetic.jpg", original, "image/jpeg")},
    )
    assert response.status_code == 201
    upload_id = response.json()["upload_id"]
    assert response.json()["page_count"] == 3 and response.json()["mime"] == "application/pdf"
    async with pg_manager.get_async_session_context() as session:
        upload = await session.get(PrivateUpload, upload_id)
        assert upload.member_id == member and upload.actor_uid == owner["uid"]
        assert upload.sha256 == hashlib.sha256(original).hexdigest() and upload.byte_size == len(original)
        assert upload.mime == "application/pdf" and upload.status == "active"
        pages = upload.pages
        keys = [upload.original_key, *[page["object_key"] for page in pages]]
        assert [page["page_index"] for page in pages] == [0, 1, 2]
        assert len(set(keys)) == 4
        for model in (VisionJob, VisionDraft, HealthProcessingConsent):
            assert (await session.scalars(select(model).where(model.member_id == member))).all() == []
    root_path = f"{ROOT}/uploads/{upload_id}/preview"
    preview = await client.get(root_path, headers=headers)
    assert preview.status_code == 200 and preview.content == original
    assert preview.headers["content-type"] == "application/pdf"
    assert preview.headers["cache-control"] == "private, no-store"
    # 二倍渲染之后才施加人工角度；期望尺寸来自固定页几何，而非被测处理器。
    for index, (source_size, output_size, color, marker) in enumerate(
        [
            ((240, 320), (331, 254), (255, 0, 0), (62, 71)),
            ((320, 240), (254, 331), (0, 255, 0), (182, 62)),
            ((320, 240), (254, 331), (0, 0, 255), (71, 267)),
        ]
    ):
        page = pages[index]
        assert page["source_space"] == "pdf_rendered_page" and page["transform"] == "affine-v1"
        assert (page["source_width"], page["source_height"]) == source_size
        assert (page["width"], page["height"]) == output_size
        assert page["rotation"] == 90 and page["deskew_angle"] == -2.5
        assert page["exif_orientation"] == 1
        processed = await client.get(root_path, headers=headers, params={"page_index": index})
        assert processed.status_code == 200 and processed.headers["content-type"] == "image/png"
        assert processed.headers["cache-control"] == "private, no-store"
        with Image.open(io.BytesIO(processed.content)) as decoded:
            assert decoded.size == output_size and not decoded.getexif() and not decoded.info
            a, b, c, d, e, f = page["source_to_processed"]
            # 固定 87.5 度顺时针变换；不调用被测实现生成期望矩阵或标记位置。
            assert [a, b, c, d, e, f] == pytest.approx(
                [0.043619387365, -0.999048221582, 0.999048221582 * source_size[1], 0.999048221582, 0.043619387365, 0]
            )
            x, y = source_size[0] / 2, source_size[1] / 2
            assert decoded.getpixel((math.floor(a * x + b * y + c), math.floor(d * x + e * y + f))) == color
            assert decoded.getpixel(marker) == (0, 0, 0)
        for identity in (stranger, admin):
            denied = await client.get(root_path, headers=identity["headers"], params={"page_index": index})
            assert denied.status_code == 404
    for identity in (stranger, admin):
        assert (await client.get(root_path, headers=identity["headers"])).status_code == 404
    assert (await client.get(root_path)).status_code == 401
    assert (await client.get(root_path, headers=headers, params={"page_index": 3})).status_code == 404
    assert (await client.get(root_path, headers=headers, params={"page_index": -1})).status_code == 422
    assert (await client.delete(f"{ROOT}/uploads/{upload_id}", headers=stranger["headers"])).status_code == 404
    assert (await client.delete(f"{ROOT}/uploads/{upload_id}", headers=headers)).status_code == 200
    for params in ({}, *[{"page_index": index} for index in range(3)]):
        assert (await client.get(root_path, headers=headers, params=params)).status_code == 404
    for key in keys:
        assert await get_minio_client().astat_file(PRIVATE_BUCKET, key) is None
    async with pg_manager.get_async_session_context() as session:
        assert (await session.get(PrivateUpload, upload_id)).status == "deleted"


async def test_pdf_http_rejects_invalid_encrypted_oversize_and_meal_without_persisting_uploads(health_http):
    """每次非法 PDF 均在产生持久上传及云任务前拒绝。"""
    client, users = health_http
    owner = users[0]
    member = await create_member(client, owner["headers"])
    for contents, purpose, status, code in (
        (synthetic_pdf(0), "report", 422, "invalid_pdf"),
        (synthetic_pdf(21), "report", 422, "invalid_pdf"),
        (synthetic_pdf(1, encrypted=True), "report", 422, "invalid_pdf"),
        (b"%PDF-1.7\nsynthetic-broken-file", "report", 422, "invalid_pdf"),
        (synthetic_pdf(1), "meal", 415, "unsupported_type"),
        (synthetic_pdf(1, width=3000, height=3000), "report", 422, "page_too_large"),
        (b"%PDF-1.7\n" + b"0" * (20 * 1024 * 1024), "report", 413, "file_too_large"),
    ):
        rejected = await client.post(
            f"{ROOT}/uploads",
            headers=owner["headers"],
            data={"member_id": member, "purpose": purpose},
            files={"file": ("synthetic.pdf", contents, "application/pdf")},
        )
        assert rejected.status_code == status and rejected.json()["code"] == code
        async with pg_manager.get_async_session_context() as session:
            for model in (PrivateUpload, VisionJob, VisionDraft, HealthProcessingConsent):
                assert (await session.scalars(select(model).where(model.member_id == member))).all() == []


async def test_report_transform_upload_private_original_processed_metadata_and_parameters(health_http):
    """真实上传与对象回读证明变换不改原件、不创建云任务且受成员权限限制。"""
    client, users = health_http
    owner, stranger, admin = users
    headers = owner["headers"]
    member = await create_member(client, headers)
    image = Image.new("RGB", (120, 160), "white")
    image.paste("red", (20, 30, 40, 50))
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "synthetic-private-comment"
    buffer = io.BytesIO()
    image.save(buffer, "PNG", exif=exif)
    original = buffer.getvalue()
    data = {"member_id": member, "purpose": "report", "rotation": "90", "deskew_angle": "-2.5"}
    file = {"file": ("synthetic.png", original, "image/png")}
    for identity in (stranger, admin):
        assert (
            await client.post(f"{ROOT}/uploads", headers=identity["headers"], data=data, files=file)
        ).status_code == 404
    assert (await client.post(f"{ROOT}/uploads", data=data, files=file)).status_code == 401
    for change in (
        {"rotation": "1"},
        {"rotation": "90.0"},
        {"deskew_angle": "11"},
        {"deskew_angle": "-11"},
        {"deskew_angle": "nan"},
        {"deskew_angle": "inf"},
        {"purpose": "meal"},
    ):
        assert (
            await client.post(f"{ROOT}/uploads", headers=headers, data={**data, **change}, files=file)
        ).status_code == 422
    response = await client.post(f"{ROOT}/uploads", headers=headers, data=data, files=file)
    assert response.status_code == 201
    upload_id = response.json()["upload_id"]
    original_response = await client.get(f"{ROOT}/uploads/{upload_id}/preview", headers=headers)
    assert original_response.status_code == 200 and original_response.content == original
    processed = await client.get(f"{ROOT}/uploads/{upload_id}/preview?page_index=0", headers=headers)
    assert processed.status_code == 200 and processed.headers["cache-control"] == "private, no-store"
    with Image.open(io.BytesIO(processed.content)) as decoded:
        angle = math.radians(2.5)
        assert decoded.size == (
            math.ceil(120 * math.cos(angle) + 160 * math.sin(angle)),
            math.ceil(160 * math.cos(angle) + 120 * math.sin(angle)),
        )
        assert not decoded.getexif() and not decoded.info
        async with pg_manager.get_async_session_context() as session:
            upload = await session.get(PrivateUpload, upload_id)
            page = upload.pages[0]
            assert page["transform"] == "affine-v1"
            assert page["source_space"] == "encoded_image"
            assert (page["source_width"], page["source_height"]) == (120, 160)
            assert page["exif_orientation"] == 6
            assert page["rotation"] == 90 and page["deskew_angle"] == -2.5
            assert (page["width"], page["height"]) == decoded.size
            a, b, c, d, e, f = page["source_to_processed"]
            # 已知原始红色块中心，经持久化矩阵落在同一处理 PNG 内。
            assert decoded.getpixel((int(a * 30.5 + b * 40.5 + c), int(d * 30.5 + e * 40.5 + f))) == (255, 0, 0)
            assert (await session.scalars(select(VisionJob).where(VisionJob.member_id == member))).all() == []
            assert (
                await session.scalars(
                    select(HealthProcessingConsent).where(HealthProcessingConsent.member_id == member)
                )
            ).all() == []
    for identity in (stranger, admin):
        assert (
            await client.get(f"{ROOT}/uploads/{upload_id}/preview?page_index=0", headers=identity["headers"])
        ).status_code == 404


async def test_report_page_task_http_headers_types_and_private_boundary(health_http):
    """实际 shipping 入口验证失败页任务边界，不开启收费供应商。"""
    client, users = health_http
    owner, stranger, admin = users
    member = await create_member(client, owner["headers"])
    response = await client.post(
        f"{ROOT}/manual-drafts",
        headers=owner["headers"],
        json={"member_id": member, "kind": "report", "report": {"fields": [field()]}},
    )
    assert response.status_code == 201
    data = {"draft_id": response.json()["id"], "version": 1, "page_indices": [1], "client_request_id": str(uuid4())}
    path = f"{ROOT}/report-page-tasks"
    headers = {**owner["headers"], "Idempotency-Key": data["client_request_id"], "If-Match": '"1"'}
    for identity in (stranger, admin):
        denied = await client.post(path, headers={**headers, **identity["headers"]}, json=data)
        assert denied.status_code == 404
    assert (await client.post(path, json=data)).status_code == 401
    for bad_headers in (
        {k: v for k, v in headers.items() if k != "If-Match"},
        {**headers, "If-Match": '"2"'},
    ):
        assert (await client.post(path, headers=bad_headers, json=data)).status_code == 409
    assert (await client.post(path, headers={**headers, "Idempotency-Key": str(uuid4())}, json=data)).status_code == 422
    for invalid in (
        {"page_indices": [1, 1]},
        {"page_indices": [True]},
        {"page_indices": [20]},
        {"page_indices": ["1"]},
        {"version": True},
        {"version": 1.1},
        {"version": "1"},
        {"model": "untrusted"},
    ):
        assert (await client.post(path, headers=headers, json={**data, **invalid})).status_code == 422
    rejected = await client.post(path, headers=headers, json=data)
    assert rejected.status_code == 422 and rejected.json()["code"] == "report_reprocess_invalid"
    async with pg_manager.get_async_session_context() as session:
        assert (await session.scalars(select(VisionJob).where(VisionJob.member_id == member))).all() == []


async def test_partial_report_pages_require_explicit_exclusion_and_reject_forgery(health_http):
    """真实 HTTP 验证部分结果人工排除；页状态是合成 fixture，不声称真实 OCR。"""
    client, users = health_http
    owner, stranger, admin = users
    headers = owner["headers"]
    member = await create_member(client, headers)
    image = io.BytesIO()
    Image.new("RGB", (120, 120), "white").save(image, "PNG")
    uploads = []
    for _ in range(2):
        response = await client.post(
            f"{ROOT}/uploads",
            headers=headers,
            data={"member_id": member, "purpose": "report"},
            files={"file": ("synthetic.png", image.getvalue(), "image/png")},
        )
        assert response.status_code == 201
        uploads.append(response.json()["upload_id"])
    response = await client.post(
        f"{ROOT}/manual-drafts",
        headers=headers,
        json={"member_id": member, "kind": "report", "report": {"fields": [field()]}},
    )
    assert response.status_code == 201
    draft_id = response.json()["id"]
    async with pg_manager.get_async_session_context() as session:
        draft = await session.get(VisionDraft, draft_id)
        pages = []
        for index, upload_id in enumerate(uploads):
            upload = await session.get(PrivateUpload, upload_id)
            page = {k: v for k, v in upload.pages[0].items() if k != "object_key"}
            pages.append({**page, "page_index": index, "upload_id": upload_id, "upload_page_index": 0})
        pages[1].update(status="failed", error_code="provider_failed", quality_flags=["low_resolution"])
        # 第一页去掉新字段，证明旧快照不会阻断正常修订。
        pages[0] = {
            k: v
            for k, v in pages[0].items()
            if k
            not in {
                "source_space",
                "source_width",
                "source_height",
                "exif_orientation",
                "deskew_angle",
                "source_to_processed",
            }
        }
        pages[0]["transform"] = "identity"
        draft.payload = {**draft.payload, "pages": pages}
        draft.original_payload = draft.payload
    path = f"{ROOT}/report-extractions/{draft_id}"
    for identity in (stranger, admin):
        assert (await client.get(path, headers=identity["headers"])).status_code == 404
    request, key = confirmation(accept_incomplete=True)
    response = await client.post(f"{path}/confirm", headers={**headers, **key}, json=request)
    assert response.status_code == 422 and response.json()["code"] == "report_pages_incomplete"
    assert (await client.get(f"{ROOT}/members/{member}/observations", headers=headers)).json() == []
    payload = (await client.get(path, headers=headers)).json()["payload"]
    forged = {**payload, "pages": [{**p, "status": "ready", "error_code": None} for p in payload["pages"]]}
    response = await client.patch(
        path, headers={**headers, "If-Match": '"1"'}, json={"version": 1, "reason": "合成篡改页状态", "report": forged}
    )
    assert response.status_code == 422 and response.json()["code"] == "evidence_invalid"
    forged_pages = [{**p} for p in payload["pages"]]
    forged_pages[1]["source_to_processed"] = [1, 0, 99, 0, 1, 99]
    response = await client.patch(
        path,
        headers={**headers, "If-Match": '"1"'},
        json={"version": 1, "reason": "合成篡改坐标映射", "report": {**payload, "pages": forged_pages}},
    )
    assert response.status_code == 422 and response.json()["code"] == "evidence_invalid"
    payload["excluded_pages"] = [1]
    response = await client.patch(
        path,
        headers={**headers, "If-Match": '"1"'},
        json={"version": 1, "reason": "明确排除合成失败页", "report": payload},
    )
    assert response.status_code == 200 and response.json()["version"] == 2
    request, key = confirmation(version=2)
    confirmed = await client.post(f"{path}/confirm", headers={**headers, **key}, json=request)
    assert confirmed.status_code == 200
    async with pg_manager.get_async_session_context() as session:
        draft = await session.get(VisionDraft, draft_id)
        assert draft.review_status == "confirmed" and draft.payload["excluded_pages"] == [1]
        assert draft.payload["pages"][1]["status"] == "failed"
        records = list(
            (await session.scalars(select(HealthObservation).where(HealthObservation.member_id == member))).all()
        )
        assert len(records) == 1 and records[0].id == confirmed.json()["target_ids"][0]


def field():
    """合成指标不是患者数据。"""
    return {
        "field_id": str(uuid4()),
        "name": "测试指标",
        "value_raw": "6.8",
        "value_numeric": "6.8",
        "unit_raw": "mmol/L",
    }


def confirmation(version=1, **kwargs):
    """生成一次请求键及其匹配 HTTP 头。"""
    data = {"version": version, "client_request_id": str(uuid4()), **kwargs}
    return data, {"Idempotency-Key": data["client_request_id"]}


async def test_manual_report_private_once_confirm_revoke_and_version(health_http):
    client, users = health_http
    owner, stranger, admin = users
    headers = owner["headers"]
    member = await create_member(client, headers)
    response = await client.post(
        f"{ROOT}/manual-drafts",
        headers=headers,
        json={"member_id": member, "kind": "report", "report": {"fields": [field()]}},
    )
    assert response.status_code == 201
    draft = response.json()
    path = f"{ROOT}/report-extractions/{draft['id']}"
    for identity in (stranger, admin):
        assert (await client.get(path, headers=identity["headers"])).status_code == 404
    assert (await client.get(f"{ROOT}/members/{member}/observations", headers=headers)).json() == []
    payload = draft["payload"]
    payload["fields"][0]["value_raw"] = "7.1"
    payload["fields"][0]["value_numeric"] = "7.1"
    patch = {"version": 1, "reason": "合成复核", "report": payload}
    assert (await client.patch(path, headers=headers, json=patch)).status_code == 409
    response = await client.patch(path, headers={**headers, "If-Match": '"1"'}, json=patch)
    assert response.status_code == 200 and response.json()["version"] == 2
    assert (await client.patch(path, headers={**headers, "If-Match": '"1"'}, json=patch)).status_code == 409
    data, key = confirmation(2)
    responses = await asyncio.gather(
        *[client.post(f"{path}/confirm", headers={**headers, **key}, json=data) for _ in range(2)]
    )
    assert [item.status_code for item in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    assert (
        await client.post(f"{path}/confirm", headers={**headers, **key}, json={**data, "accept_incomplete": True})
    ).status_code == 409
    records = (await client.get(f"{ROOT}/members/{member}/observations", headers=headers)).json()
    assert len(records) == 1 and records[0]["snapshot"]["value_raw"] == "7.1"
    async with pg_manager.get_async_session_context() as session:
        saved = await session.get(VisionDraft, draft["id"])
        assert saved.review_status == "confirmed" and saved.original_payload["fields"][0]["value_raw"] == "6.8"
    response = await client.put(
        f"{ROOT}/members/{member}/grants",
        headers=headers,
        json={"actor_uid": stranger["uid"], "scopes": ["report_view"]},
    )
    assert response.status_code == 200
    assert (await client.get(path, headers=stranger["headers"])).status_code == 200
    list_response = await client.get(f"{ROOT}/members/{member}/vision", headers=stranger["headers"])
    assert list_response.status_code == 200 and len(list_response.json()["drafts"]) == 1
    assert (
        await client.post(
            f"{ROOT}/manual-drafts",
            headers=stranger["headers"],
            json={"member_id": member, "kind": "report", "report": {"fields": [field()]}},
        )
    ).status_code == 404
    await client.put(
        f"{ROOT}/members/{member}/grants", headers=headers, json={"actor_uid": stranger["uid"], "scopes": []}
    )
    assert (await client.get(path, headers=stranger["headers"])).status_code == 404
    assert (await client.get(path)).status_code == 401


async def test_meal_food_versions_old_calculation_and_incomplete_confirmation(health_http):
    client, users = health_http
    headers, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    food = {
        "record_code": str(uuid4()),
        "name": "合成测试食品",
        "cooking_state": "熟",
        "source": "独立测试手算",
        "license": "仅自动化测试",
        "edition": "test",
        "dataset_version": "test-1",
        "nutrients": {"energy_kcal": "200", "protein_g": "10", "fat_g": "5", "carbohydrate_g": "25", "sodium_mg": None},
    }
    assert (await client.post(f"{ROOT}/foods", headers=headers, json=food)).status_code == 403
    response = await client.post(f"{ROOT}/foods", headers=admin, json=food)
    assert response.status_code == 201
    food_id = response.json()["id"]
    assert (await client.post(f"{ROOT}/foods", headers=admin, json=food)).status_code == 409
    payload = {
        "meal_type": "lunch",
        "eaten_at": "2026-10-04T12:00:00+08:00",
        "items": [
            {
                "item_id": str(uuid4()),
                "name": "合成食物",
                "food_id": food_id,
                "grams": "150",
                "share_ratio": "0.4",
                "portion_source": "weighed",
            }
        ],
    }
    response = await client.post(
        f"{ROOT}/manual-drafts", headers=headers, json={"member_id": member, "kind": "meal", "meal": payload}
    )
    assert response.status_code == 201
    draft = response.json()
    path = f"{ROOT}/meal-drafts/{draft['id']}"
    result = (await client.post(f"{path}/calculate", headers=headers, json={"version": 1})).json()
    assert result["totals"]["energy_kcal"] == "120.00" and result["totals"]["sodium_mg"] is None
    payload["items"][0]["grams"] = "200"
    assert (
        await client.patch(
            path, headers={**headers, "If-Match": '"1"'}, json={"version": 1, "reason": "合成改量", "meal": payload}
        )
    ).status_code == 200
    data, key = confirmation(2, calculation_id=result["calculation_id"], accept_incomplete=True)
    assert (await client.post(f"{path}/confirm", headers={**headers, **key}, json=data)).status_code == 409
    result = (await client.post(f"{path}/calculate", headers=headers, json={"version": 2})).json()
    assert result["totals"]["energy_kcal"] == "160.00"
    data, key = confirmation(2, calculation_id=result["calculation_id"])
    assert (await client.post(f"{path}/confirm", headers={**headers, **key}, json=data)).status_code == 422
    assert (await client.get(f"{ROOT}/members/{member}/diet-logs", headers=headers)).json() == []
    data, key = confirmation(2, calculation_id=result["calculation_id"], accept_incomplete=True)
    assert (await client.post(f"{path}/confirm", headers={**headers, **key}, json=data)).status_code == 200
    records = (await client.get(f"{ROOT}/members/{member}/diet-logs", headers=headers)).json()
    assert len(records) == 1 and records[0]["snapshot"]["nutrition"]["sources"][0]["dataset_version"] == "test-1"


async def test_recipe_portion_oil_http_publish_version_and_confirm(health_http):
    """真实接口计算、纠错与 PG 入账；合成数值只作为独立 oracle。"""
    client, users = health_http
    headers, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    source = {"source": "独立合成手算", "license": "仅自动化测试", "edition": "synthetic", "dataset_version": "test-1"}
    food_ids = []
    for name, energy in (("合成原料", 300), ("合成油", 900), ("合成糖", 400)):
        response = await client.post(
            f"{ROOT}/foods",
            headers=admin,
            json={
                **source,
                "record_code": str(uuid4()),
                "name": name,
                "cooking_state": "原料",
                "nutrients": {
                    "energy_kcal": str(energy),
                    "protein_g": "0",
                    "fat_g": "0",
                    "carbohydrate_g": "0",
                    "sodium_mg": "0",
                },
            },
        )
        assert response.status_code == 201
        food_ids.append(response.json()["id"])
    recipe = {
        **source,
        "record_code": str(uuid4()),
        "name": "合成食谱",
        "cooking_state": "熟",
        "yield_grams": "600",
        "ingredients": [
            {"food_id": food_id, "grams": grams, "role": role}
            for food_id, grams, role in zip(food_ids, ("200", "20", "10"), ("food", "oil", "sugar"))
        ],
    }
    assert (await client.post(f"{ROOT}/recipes", headers=headers, json=recipe)).status_code == 403
    assert (
        await client.post(
            f"{ROOT}/recipes", headers=admin, json={**recipe, "ingredients": [{"food_id": str(uuid4()), "grams": "1"}]}
        )
    ).status_code == 422
    response = await client.post(f"{ROOT}/recipes", headers=admin, json=recipe)
    assert response.status_code == 201
    recipe_id = response.json()["id"]
    assert (await client.post(f"{ROOT}/recipes", headers=admin, json=recipe)).status_code == 409
    assert any(
        item["id"] == recipe_id for item in (await client.get(f"{ROOT}/recipes?q=合成食谱", headers=headers)).json()
    )
    for literal_query in ("%", "_"):
        matches = (await client.get(f"{ROOT}/recipes", headers=headers, params={"q": literal_query})).json()
        assert all(item["id"] != recipe_id for item in matches)
    portion = {
        **source,
        "recipe_version_id": recipe_id,
        "unit_label": "合成平装碗",
        "grams_per_unit": "300",
        "applicable_scope": "仅此合成食谱与容器",
    }
    assert (await client.post(f"{ROOT}/portion-references", headers=headers, json=portion)).status_code == 403
    response = await client.post(f"{ROOT}/portion-references", headers=admin, json=portion)
    assert response.status_code == 201
    portion_id = response.json()["id"]
    assert (await client.post(f"{ROOT}/portion-references", headers=admin, json=portion)).status_code == 409
    assert (await client.get(f"{ROOT}/portion-references", headers=headers)).status_code == 422
    assert (await client.get(f"{ROOT}/portion-references?recipe_version_id={recipe_id}", headers=headers)).json()[0][
        "id"
    ] == portion_id
    payload = {
        "meal_type": "lunch",
        "eaten_at": "2026-10-04T12:00:00+08:00",
        "items": [
            {
                "item_id": str(uuid4()),
                "name": "合成成品",
                "recipe_version_id": recipe_id,
                "grams": None,
                "portion_reference_id": portion_id,
                "portion_count": "0.5",
                "share_ratio": "0.5",
                "portion_source": "estimated",
            }
        ],
    }
    response = await client.post(
        f"{ROOT}/manual-drafts", headers=headers, json={"member_id": member, "kind": "meal", "meal": payload}
    )
    assert response.status_code == 201
    draft = response.json()
    path = f"{ROOT}/meal-drafts/{draft['id']}"
    result = (await client.post(f"{path}/calculate", headers=headers, json={"version": 1})).json()
    assert result["totals"]["energy_kcal"] == "102.50" and result["estimated"]
    payload["items"][0].update(
        {
            "portion_reference_id": None,
            "portion_count": None,
            "grams": "295",
            "portion_source": "weighed",
            "adjustments": [{"role": "oil", "mode": "replace", "food_id": food_ids[1], "grams": "5"}],
        }
    )
    assert (
        await client.patch(
            path, headers={**headers, "If-Match": '"1"'}, json={"version": 1, "reason": "合成更换用油", "meal": payload}
        )
    ).status_code == 200
    data, key = confirmation(2, calculation_id=result["calculation_id"])
    assert (await client.post(f"{path}/confirm", headers={**headers, **key}, json=data)).status_code == 409
    result = (await client.post(f"{path}/calculate", headers=headers, json={"version": 2})).json()
    assert result["totals"]["energy_kcal"] == "182.50" and result["estimated"] and result["complete"]
    data, key = confirmation(2, calculation_id=result["calculation_id"])
    confirmed = await client.post(f"{path}/confirm", headers={**headers, **key}, json=data)
    assert confirmed.status_code == 200
    assert (await client.post(f"{path}/confirm", headers={**headers, **key}, json=data)).json() == confirmed.json()
    logs = (await client.get(f"{ROOT}/members/{member}/diet-logs", headers=headers)).json()
    assert len(logs) == 1 and logs[0]["snapshot"]["nutrition"]["totals"]["energy_kcal"] == "182.50"
    assert logs[0]["snapshot"]["nutrition"]["sources"][0]["ingredients"][1]["food"]["id"] == food_ids[1]
    async with pg_manager.get_async_session_context() as session:
        stored = (await session.scalars(select(DietLog).where(DietLog.member_id == member))).one()
        assert stored.snapshot["nutrition"]["totals"]["energy_kcal"] == "182.50"
        stored_recipe = await session.get(RecipeVersion, recipe_id)
        assert str(stored_recipe.yield_grams) == "600.000000" and len(stored_recipe.ingredients) == 3
    assert (
        await client.patch(
            path,
            headers={**headers, "If-Match": '"2"'},
            json={"version": 2, "reason": "不能改正式记录", "meal": payload},
        )
    ).status_code == 409


async def test_private_upload_real_worker_fails_closed_and_generic_tasks_denied(health_http):
    client, users = health_http
    headers, admin = users[0]["headers"], users[2]["headers"]
    member = await create_member(client, headers)
    invalid = await client.post(
        f"{ROOT}/uploads",
        headers=headers,
        data={"member_id": member, "purpose": "meal"},
        files={"file": ("photo.jpg", b"this is not an image", "image/jpeg")},
    )
    assert invalid.status_code == 415
    buffer = io.BytesIO()
    Image.new("RGB", (120, 120), "white").save(buffer, "PNG")
    response = await client.post(
        f"{ROOT}/uploads",
        headers=headers,
        data={"member_id": member, "purpose": "meal"},
        files={"file": ("synthetic.png", buffer.getvalue(), "image/png")},
    )
    assert response.status_code == 201
    upload_id = response.json()["upload_id"]
    preview = await client.get(f"{ROOT}/uploads/{upload_id}/preview?page_index=0", headers=headers)
    assert preview.status_code == 200 and preview.headers["cache-control"] == "private, no-store"
    assert preview.content.startswith(b"\x89PNG")
    async with pg_manager.get_async_session_context() as session:
        stored_upload = await session.get(PrivateUpload, upload_id)
        original_key = stored_upload.original_key
    async with httpx.AsyncClient() as unsigned:
        assert (await unsigned.get(f"http://minio:9000/{PRIVATE_BUCKET}/{original_key}")).status_code == 403
    assert (await client.get(f"{ROOT}/uploads/{upload_id}/preview", headers=admin)).status_code == 404
    configuration = (await client.get(f"{ROOT}/configuration", headers=headers)).json()
    if not configuration["meal"]["available"]:
        request = {
            "member_id": member,
            "upload_ids": [upload_id],
            "client_request_id": str(uuid4()),
            "meal_type": "lunch",
            "eaten_at": "2026-10-04T12:00:00+08:00",
        }
        assert (
            await client.post(
                f"{ROOT}/meal-photo-tasks",
                headers={**headers, "Idempotency-Key": request["client_request_id"]},
                json=request,
            )
        ).status_code == 503
    # 精确创建没有有效同意的合成 Task，让实际 ARQ worker 验证拒绝；不调用收费供应商。
    job_id = str(uuid4())
    async with pg_manager.get_async_session_context() as session:
        task = await tasker.create_in_session(
            session, name="pytest health permission failure", task_type="meal_recognize_v1", payload={"job_id": job_id}
        )
        session.add(
            VisionJob(
                id=job_id,
                task_id=task.id,
                actor_uid=users[0]["uid"],
                member_id=member,
                kind="meal",
                request_id=str(uuid4()),
                fingerprint="0" * 64,
                upload_ids=[upload_id],
                input_snapshot={"model": "not-configured", "processor": "synthetic", "policy_version": "test-only"},
            )
        )
    await tasker.publish(task)
    for _ in range(60):
        response = await client.get(f"{ROOT}/vision-tasks/{task.id}", headers=headers)
        assert response.status_code == 200
        if response.json()["execution_status"] in {"failed", "cancelled"}:
            break
        await asyncio.sleep(0.5)
    assert response.json()["execution_status"] == "failed" and response.json()["error_code"] == "consent_required"
    async with pg_manager.get_async_session_context() as session:
        persisted = await session.get(VisionJob, job_id)
        assert persisted.result_id is None
        assert (await session.scalars(select(VisionDraft).where(VisionDraft.member_id == member))).all() == []
    for method, suffix in (("GET", ""), ("POST", "/cancel"), ("DELETE", "")):
        assert (await client.request(method, f"/api/tasks/{task.id}{suffix}", headers=admin)).status_code == 404
    tasks = (await client.get("/api/tasks", headers=admin)).json()
    assert task.id not in str(tasks)
    assert (await client.delete(f"{ROOT}/uploads/{upload_id}", headers=headers)).status_code == 200
    assert (await client.get(f"{ROOT}/uploads/{upload_id}/preview", headers=headers)).status_code == 404
    assert (await client.get(f"{ROOT}/vision-tasks/{task.id}", headers=headers)).status_code == 410

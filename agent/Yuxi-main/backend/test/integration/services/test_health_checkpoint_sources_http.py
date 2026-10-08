"""独立真实PG来源与shipping模型入口核对正文，避免共享模型配置变更。"""

from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

from langchain_core.messages import HumanMessage, ToolMessage
import pytest

from test.integration.services.test_health_family_profile_http import create_health_member, family_profile_http  # noqa: F401
from yuxi.agents.buildin.health_consultation.graph import HealthAuthorizationMiddleware
from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.services import health_consultation_service as service
from yuxi.services.health_evidence_service import search_nutrition_evidence
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AgentRun, Conversation, Project
from yuxi.storage.postgres.models_health import (
    DietLog,
    HealthConsultation,
    HealthObservation,
    NutritionCalculation,
    NutritionEvidence,
    VisionConfirmation,
    VisionDraft,
)
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_persisted_report_meal_and_reviewed_evidence_are_exact_at_model_entry(family_profile_http, monkeypatch):  # noqa: F811
    """来源owner真实读取，伪造相同ID正文与附加正文均不能进入模型。"""
    client, sessions, identities = family_profile_http
    member_id = await create_health_member(client, identities["self"])
    project_id, thread_id, run_id, request_id = [str(uuid4()) for _ in range(4)]
    timestamp = utc_now_naive()
    report = {"name": "合成指标", "value_numeric": 5, "unit_raw": "synthetic", "source": "user_confirmed"}
    meal = {
        "meal": {"meal_type": "lunch", "eaten_at": "2026-10-08T12:00:00+08:00", "items": []},
        "nutrition": {
            "totals": {"energy_kcal": "300.00"},
            "complete": True,
            "estimated": True,
            "units": {"energy_kcal": "kcal"},
            "calculation_version": "synthetic",
        },
    }
    context = SimpleNamespace(
        uid="self",
        thread_id=thread_id,
        run_id=run_id,
        request_id=request_id,
        worker_id="synthetic-owner",
        model="synthetic:fixed",
    )
    async with sessions() as session:
        session.add(
            Project(
                id=project_id,
                uid="self",
                selection_status="implicit",
                directory_mode="managed",
                workdir_path=f"projects/{project_id}",
            )
        )
        await session.flush()
        conversation = Conversation(
            uid="self", thread_id=thread_id, project_id=project_id, agent_id="health-consultation"
        )
        session.add(conversation)
        await session.flush()
        session.add(
            HealthConsultation(
                conversation_id=conversation.id, member_id=member_id, actor_uid="self", request_id=request_id
            )
        )
        session.add(
            AgentRun(
                id=run_id,
                uid="self",
                conversation_id=conversation.id,
                conversation_thread_id=thread_id,
                runtime_scope_id=thread_id,
                agent_slug="health-consultation",
                request_id=request_id,
                status="running",
                worker_id=context.worker_id,
                lease_expires_at=timestamp + timedelta(minutes=10),
                input_payload={"health_processing": {"model": context.model}},
            )
        )
        for kind, snapshot in (("report", report), ("meal", meal)):
            draft_id, confirmation_id, record_id = [str(uuid4()) for _ in range(3)]
            session.add(
                VisionDraft(
                    id=draft_id,
                    member_id=member_id,
                    kind=kind,
                    version=1,
                    review_status="confirmed",
                    original_payload=snapshot,
                    payload=snapshot,
                )
            )
            await session.flush()
            session.add(
                VisionConfirmation(
                    id=confirmation_id,
                    draft_id=draft_id,
                    draft_version=1,
                    actor_uid="self",
                    member_id=member_id,
                    kind=kind,
                    request_id=str(uuid4()),
                    fingerprint="a" * 64,
                    target_ids=[record_id],
                )
            )
            await session.flush()
            if kind == "report":
                session.add(
                    HealthObservation(
                        id=record_id,
                        member_id=member_id,
                        confirmation_id=confirmation_id,
                        field_id=str(uuid4()),
                        snapshot=snapshot,
                    )
                )
            else:
                calculation_id = str(uuid4())
                session.add(
                    NutritionCalculation(
                        id=calculation_id,
                        draft_id=draft_id,
                        draft_version=1,
                        input_hash="a" * 64,
                        input_snapshot=snapshot,
                        result=meal["nutrition"],
                        calculation_version="synthetic",
                    )
                )
                await session.flush()
                session.add(
                    DietLog(
                        id=record_id,
                        member_id=member_id,
                        confirmation_id=confirmation_id,
                        calculation_id=calculation_id,
                        snapshot=snapshot,
                    )
                )
        content = "合成审核营养科普，仅作通用教育"
        session.add(
            NutritionEvidence(
                id=str(uuid4()),
                title="合成营养",
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                source_ref="https://example.com/synthetic",
                source_version="synthetic-v1",
                review_ref="synthetic-review",
                reviewed_by="synthetic-professional",
                reviewed_at=timestamp,
                valid_until=timestamp + timedelta(days=1),
                published_by="admin",
            )
        )
        await session.commit()

    async def bound_processing(session, uid, thread_id, model, **kwargs):
        """只隔离部署审批配置，成员/用途/来源权限由真实PG repository核对。"""
        return await HealthConsultationRepository(session).authorize(uid, thread_id, lock=kwargs.get("lock", False)), {
            "model": model
        }

    monkeypatch.setattr(service, "require_consultation", bound_processing)
    monkeypatch.setattr("yuxi.agents.buildin.health_consultation.graph.model_cache.get_model_info", lambda _: None)
    payloads = [
        ("report", "get_confirmed_profile", await service.confirmed_consultation_records(context, "report")),
        ("meal", "get_confirmed_diet", await service.confirmed_consultation_records(context, "meal")),
        ("evidence", "query_reviewed_nutrition_knowledge", await search_nutrition_evidence(context, "营养")),
    ]
    middleware = HealthAuthorizationMiddleware(None)

    async def model_guard(tool_name, payload, status="success"):
        """shipping middleware和所有来源owner均使用真实事务。"""
        messages = [
            HumanMessage(content="合成问题"),
            ToolMessage(name=tool_name, tool_call_id="synthetic-call", status=status, content=json.dumps(payload)),
        ]
        await middleware.abefore_model({"messages": messages}, SimpleNamespace(context=context))

    for kind, tool_name, original in payloads:
        assert original["citations"] if kind == "evidence" else original["records"]
        await model_guard(tool_name, original)
        for mutation in ("body", "record_extra", "envelope_extra", "flag_type", "error_status"):
            forged = deepcopy(original)
            target = forged["citations"][0] if kind == "evidence" else forged["records"][0]
            if mutation in {"body", "error_status"}:
                if kind == "report":
                    target["value_numeric"] = 999
                elif kind == "meal":
                    target["nutrition"]["totals"]["energy_kcal"] = "1.00"
                else:
                    target["content"] = "未经审核的合成治疗规则"
            elif mutation == "record_extra":
                target["diagnosis"] = "未经审核的合成诊断"
            elif mutation == "envelope_extra":
                forged["extra_body"] = "未经审核的合成诊断"
            else:
                forged["personal_meal_plan_available"] = 0
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await model_guard(tool_name, forged, "error" if mutation == "error_status" else "success")
        await model_guard(tool_name, original)
    async with sessions() as session:
        report_row = await session.get(HealthObservation, payloads[0][2]["records"][0]["record_id"])
        meal_row = await session.get(DietLog, payloads[1][2]["records"][0]["record_id"])
        evidence_row = await session.get(NutritionEvidence, payloads[2][2]["citations"][0]["evidence_id"])
        assert report_row.snapshot["value_numeric"] == 5
        assert meal_row.snapshot["nutrition"]["totals"]["energy_kcal"] == "300.00"
        assert evidence_row.content == "合成审核营养科普，仅作通用教育"

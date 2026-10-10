"""真实HTTP/PG目标绑定、初次依赖未就绪、幂等及派生来源失效。"""

import hashlib
import json
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test.integration.services.test_health_personal_targets_http import (
    import_targets,
    read_targets,
)
from test.integration.services.test_health_quality_http import setup_quality
from test.integration.services.test_health_vision_http import (  # noqa: F401
    ROOT,
    health_http,
)
from yuxi.repositories.health_consultation_repository import (
    HealthConsultationRepository,
)
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.health_quality_checks import projection_digest
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import AgentRun, Conversation
from yuxi.storage.postgres.models_health import (
    HealthConsultation,
    HealthProfileSnapshot,
    HealthRuleSnapshot,
)
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def digest(value):
    """独立于生产hash的规范化手算摘要。"""
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def bound_targets(client, users):
    current = await setup_quality(client, users)
    await import_targets(client, users, current)
    result = await read_targets(client, users[0]["headers"], current)
    assert result.status_code == 200 and result.json()["energy_kcal"] == "330"
    selected = {
        "rule_code": current["rules"]["rule_code"],
        "rule_version": 2,
        "profile_version": 2,
    }
    key = str(uuid4())
    body = {"client_request_id": key, "target_selection": selected}
    path = f"{ROOT}/members/{current['member']}/diet-analyst"
    created = await client.post(path, headers=users[0]["headers"], json=body)
    assert created.status_code == 201, created.text
    return current, result.json(), body, path, created.json()


async def test_bound_target_http_persists_only_source_binding_and_same_key_cannot_change_selection(
    health_http,  # noqa: F811
):
    client, users = health_http
    current, target, body, path, created = await bound_targets(client, users)
    assert created["agent_slug"] == "health-diet-analyst" and created["target_selection"] == body["target_selection"]
    async with pg_manager.get_async_session_context() as session:
        conversation = await session.scalar(select(Conversation).where(Conversation.thread_id == created["thread_id"]))
        binding = await session.get(HealthConsultation, conversation.id)
        assert binding.personal_target_selection == {
            "selection": body["target_selection"],
            "source_hash": digest(target),
        }
        assert "inputs" not in json.dumps(binding.personal_target_selection)
        assert (
            await session.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.uid == users[0]["uid"])) == 0
        )
    repeated = await client.post(path, headers=users[0]["headers"], json=body)
    assert repeated.status_code == 201 and repeated.json() == created
    for changed in (
        {"client_request_id": body["client_request_id"]},
        {**body, "target_selection": {**body["target_selection"], "rule_version": 1}},
        {
            **body,
            "target_selection": {**body["target_selection"], "profile_version": 1},
        },
    ):
        conflict = await client.post(path, headers=users[0]["headers"], json=changed)
        assert conflict.status_code == 409 and conflict.json()["code"] == "request_conflict", conflict.text
    for actor in (users[1], users[2]):
        denied = await client.post(
            path,
            headers=actor["headers"],
            json={**body, "client_request_id": str(uuid4())},
        )
        # 用户1在quality fixture有专业授权，但不继承ai_use；admin同样不能旁路。
        assert denied.status_code == 404, denied.text
    consultation = await client.post(
        f"{ROOT}/members/{current['member']}/consultations",
        headers=users[0]["headers"],
        json=body,
    )
    assert consultation.status_code == 422


async def test_optional_unbound_analyst_stays_valid_without_profile_view_or_ready_target(
    health_http,  # noqa: F811
):
    client, users = health_http
    current = await setup_quality(client, users)
    owner = users[0]["headers"]
    path = f"{ROOT}/members/{current['member']}/diet-analyst"
    unavailable = await client.post(
        path,
        headers=owner,
        json={
            "client_request_id": str(uuid4()),
            "target_selection": {
                "rule_code": current["rules"]["rule_code"],
                "rule_version": 1,
                "profile_version": 1,
            },
        },
    )
    assert unavailable.status_code == 503 and unavailable.json()["code"] == "target_dependencies_not_ready"
    assert (
        await client.put(
            f"{ROOT}/members/{current['member']}/grants",
            headers=owner,
            json={
                "actor_uid": users[0]["uid"],
                "scopes": ["diet_edit", "ai_use", "profile_edit"],
            },
        )
    ).status_code == 200
    assert (await client.post(path, headers=owner, json={"client_request_id": str(uuid4())})).status_code == 201
    denied = await client.post(
        path,
        headers=owner,
        json={
            "client_request_id": str(uuid4()),
            "target_selection": {
                "rule_code": current["rules"]["rule_code"],
                "rule_version": 1,
                "profile_version": 1,
            },
        },
    )
    assert denied.status_code == 404


async def test_binding_checks_original_target_sources_and_derived_runs_even_without_target_tool(
    health_http,  # noqa: F811
):
    client, users = health_http
    _current, target, _, _, created = await bound_targets(client, users)
    async with pg_manager.get_async_session_context() as session:
        conversation = await session.scalar(select(Conversation).where(Conversation.thread_id == created["thread_id"]))
        binding = await session.get(HealthConsultation, conversation.id)
        original_binding = deepcopy(binding.personal_target_selection)
        original_profile = await session.get(
            HealthProfileSnapshot,
            target["sources"]["profile"]["id"],
        )
        profile_id, original_payload = (
            original_profile.id,
            deepcopy(original_profile.payload),
        )
        original_profile.payload = {**original_payload, "weight_kg": "999"}
    try:
        async with pg_manager.get_async_session_context() as session:
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await HealthConsultationRepository(session).authorize(
                    users[0]["uid"], created["thread_id"], preview_history=True
                )
    finally:
        async with pg_manager.get_async_session_context() as session:
            (await session.get(HealthProfileSnapshot, profile_id)).payload = original_payload
    async with pg_manager.get_async_session_context() as session:
        session.add(
            AgentRun(
                id=str(uuid4()),
                uid=users[0]["uid"],
                request_id=str(uuid4()),
                status="completed",
                agent_slug="health-diet-analyst",
                conversation_thread_id=created["thread_id"],
                runtime_scope_id=created["thread_id"],
                conversation_id=conversation.id,
                input_payload={"health_processing": {"personal_target_selection_hash": digest(original_binding)}},
            )
        )
        (await session.get(HealthConsultation, conversation.id)).personal_target_selection = None
    async with pg_manager.get_async_session_context() as session:
        with pytest.raises(HealthVisionError, match="source_invalidated"):
            await HealthConsultationRepository(session).authorize(
                users[0]["uid"], created["thread_id"], preview_history=True
            )


@pytest.mark.parametrize(
    "source,change",
    [
        ("profile", "revoked"),
        ("rules", "revoked"),
        ("profile", "expired"),
        ("rules", "expired"),
        ("profile", "attestation"),
        ("rules", "attestation"),
    ],
)
async def test_current_bound_source_withdrawal_has_no_target_or_private_body(health_http, source, change):  # noqa: F811
    """真实来源失效由原Owner判断，绑定重放统一410且不返回公式/身体输入。"""
    client, users = health_http
    current, target, body, path, created = await bound_targets(client, users)
    model = HealthProfileSnapshot if source == "profile" else HealthRuleSnapshot
    row_id = target["sources"][source]["id"]
    async with pg_manager.get_async_session_context() as session:
        row = await session.get(model, row_id)
        original = {
            key: deepcopy(getattr(row, key)) for key in ("revoked_at", "valid_until", "attestation", "content_hash")
        }
        if change == "revoked":
            row.revoked_at = utc_now_naive()
        elif change == "expired":
            row.valid_until = utc_now_naive() - timedelta(seconds=1)
            row.attestation = {**row.attestation, "valid_until": row.valid_until.isoformat() + "Z"}
            key = current["member"] if source == "profile" else current["rules"]["rule_code"]
            row.content_hash = projection_digest(source, key, row.version, row.payload, row.attestation)
        else:
            row.attestation = {**row.attestation, "source_ref": "synthetic://tampered-target-attestation"}
    try:
        rejected = await client.post(path, headers=users[0]["headers"], json=body)
        assert rejected.status_code == 410 and rejected.json()["code"] == "source_invalidated", rejected.text
        assert not {"inputs", "bounds", "formula", "attestations", "current_personal_targets"} & rejected.json().keys()
        async with pg_manager.get_async_session_context() as session:
            with pytest.raises(HealthVisionError, match="source_invalidated"):
                await HealthConsultationRepository(session).authorize(
                    users[0]["uid"], created["thread_id"], preview_history=True
                )
    finally:
        async with pg_manager.get_async_session_context() as session:
            row = await session.get(model, row_id)
            for key, value in original.items():
                setattr(row, key, value)

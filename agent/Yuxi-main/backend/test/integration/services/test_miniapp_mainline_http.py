"""两类邀请经真实 HTTP 与独立 PostgreSQL 验证，无生产业务写入。"""
# ruff: noqa: F811 -- pytest 按同名 fixture 参数注入。

import asyncio
import time
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from test.integration.services.test_health_family_profile_http import (  # noqa: F401
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
)
from test.integration.services.test_daily_arrangement_http import source
from yuxi.storage.postgres.models_business import FamilyMember

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_ordinary_invite_preview_decline_multi_user_and_concurrent_repeat(family_profile_http):
    """同一卡片允许多人；预览拒绝不加入，同账号并发接受不重复建档。"""
    client, sessions, users = family_profile_http
    family, _, _, _ = await source(client, users["self"])
    fid = family["id"]
    invite = await client.post(f"/api/family/{fid}/invite", headers=users["self"])
    assert invite.status_code == 200, invite.text
    code = invite.json()["code"]
    preview = await client.get(f"/api/family/invitations/{code}", headers=users["other"])
    assert preview.status_code == 200, preview.text
    assert preview.json()["kind"] == "family" and preview.json()["can_accept"]
    assert "profile" not in preview.json() and "members" not in preview.json()
    assert (await client.post(f"/api/family/invitations/{code}/decline", headers=users["other"])).status_code == 200
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(FamilyMember).where(FamilyMember.family_id == fid)) == 1
    replies = await asyncio.gather(
        *(
            client.post("/api/family/join", headers=users[uid], json={"code": code})
            for uid in ["other", "other", "admin"]
        )
    )
    assert all(reply.status_code == 200 for reply in replies), [reply.text for reply in replies]
    async with sessions() as db:
        members = list((await db.scalars(select(FamilyMember).where(FamilyMember.family_id == fid))).all())
        assert sorted(member.subject_uid for member in members) == ["admin", "other", "self"]
    tampered = code[:-1] + ("a" if code[-1] != "a" else "b")
    assert (await client.post("/api/family/join", headers=users["other"], json={"code": tampered})).status_code == 410
    assert (await client.post(f"/api/family/{fid}/invite", headers=users["other"])).status_code == 403


async def test_bound_invite_claims_existing_profile_and_requires_personal_confirmation(
    family_profile_http, monkeypatch
):
    """认领不重复创建，家庭已完成也不能绕过本人确认或改全家默认设置。"""
    client, sessions, users = family_profile_http
    from yuxi.services.health_vision_service import health_vision_service
    from yuxi.storage.postgres.models_health import HealthFamilyProfileLink, HealthGrant

    async def configured(session=None):
        """只替换模型可用配置，不调用真实供应商。"""
        return {
            "meal_plan": {"available": True, "processor": "synthetic-processor"},
            "policy_version": "synthetic-policy",
        }

    monkeypatch.setattr(health_vision_service, "configuration", configured)
    family, path, data, headers = await source(client, users["self"])
    data["analysis_consent"] = {"processor": "synthetic-processor", "policy_version": "synthetic-policy"}
    saved = await client.post(path, headers=headers, json=data)
    assert saved.status_code == 200, saved.text
    before = saved.json()
    mid = next(member["id"] for member in before["members"] if member["relation"] != "本人")
    async with sessions() as db:
        linked_id = await db.scalar(
            select(HealthFamilyProfileLink.member_id).where(HealthFamilyProfileLink.source_member_id == mid)
        )
    invited = await client.post(f"/api/family/{family['id']}/members/{mid}/invite", headers=users["self"])
    assert invited.status_code == 200, invited.text
    code = invited.json()["code"]
    joined = await client.post("/api/family/join", headers=users["other"], json={"code": code})
    assert joined.status_code == 200, joined.text
    repeated = await client.post("/api/family/join", headers=users["other"], json={"code": code})
    assert repeated.status_code == 200 and len(repeated.json()["members"]) == 2
    assert (await client.post("/api/family/join", headers=users["admin"], json={"code": code})).status_code == 410
    own = await client.get(path, headers=users["other"])
    assert own.status_code == 200 and own.json()["onboarded"] is False
    assert own.json()["selfMemberId"] == mid and own.json()["isOwner"] is False
    draft = deepcopy(data)
    draft.update(
        client_request_id=str(uuid4()), scope="self", members=[deepcopy(data["members"][1])], default_diners=["child"]
    )
    member = next(member for member in own.json()["members"] if member["id"] == mid)
    draft["members"][0].update(member_id=mid, version=member["version"], relation="本人")
    wrong = deepcopy(draft)
    wrong["members"][0]["member_id"] = next(
        member["id"] for member in before["members"] if member["relation"] == "本人"
    )
    own_headers = {**users["other"], "Idempotency-Key": draft["client_request_id"]}
    assert (await client.post(path, headers=own_headers, json=wrong)).status_code == 403
    complete = await client.post(path, headers=own_headers, json=draft)
    assert complete.status_code == 200, complete.text
    assert complete.json()["onboarded"] is True
    after = (await client.get(path, headers=users["self"])).json()
    assert after["familyVersion"] == before["familyVersion"]
    assert after["defaultDiners"] == before["defaultDiners"]
    assert after["usageMode"] == before["usageMode"]
    async with sessions() as db:
        member = await db.get(FamilyMember, mid)
        assert member.subject_uid == "other" and member.confirmed_version == member.version
        assert member.relationship == "家人"
        link = await db.scalar(select(HealthFamilyProfileLink).where(HealthFamilyProfileLink.source_member_id == mid))
        assert link.member_id == linked_id and link.actor_uid == "other"
        assert (await db.get(HealthGrant, (linked_id, "self"))).revoked_at is not None
        assert (await db.get(HealthGrant, (linked_id, "other"))).revoked_at is None


async def test_family_completion_never_substitutes_for_current_person_confirmation(family_profile_http):
    """创建人同样按本人当前版本确认；旧家庭完成标记不会放行新资料。"""
    client, sessions, users = family_profile_http
    family, path, data, headers = await source(client, users["self"])
    result = await client.post(path, headers=headers, json=data)
    assert result.status_code == 200 and result.json()["onboarded"] is True
    mid = result.json()["selfMemberId"]
    async with sessions() as db:
        member = await db.get(FamilyMember, mid)
        member.confirmed_version = None
        await db.commit()
    assert (await client.get(path, headers=users["self"])).json()["onboarded"] is False


async def test_conversation_package_http_reads_own_final_message_and_publishes_only_explicitly(
    family_profile_http, monkeypatch
):
    """真实请求、Run和消息归属；目录与交易供应商用受控协议替身，不调用真实购买。"""
    from yuxi.services import conversation_purchase_service as purchase
    from yuxi.services.health_consultation_service import CONSULTATION_SKILLS
    from yuxi.services.health_vision_service import health_vision_service
    from yuxi.services.health_nutrition_service import input_fingerprint
    from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Conversation, Message, Project, Skill
    from yuxi.storage.postgres.models_health import HealthConsultation, HealthFamilyProfileLink, HealthProcessingConsent

    monkeypatch.setenv("HEALTH_COMMERCE_SOURCE_SECRET", "synthetic-conversation-http-proof-secret-012345")
    approved = {"model": "synthetic/model", "processor": "synthetic-processor", "policy_version": "synthetic-policy"}

    async def configured(session=None):
        """处理审批固定，不执行外部模型。"""
        return {
            "meal_plan": {"available": True, "processor": approved["processor"]},
            "consultation": {"available": True, **approved},
            "policy_version": approved["policy_version"],
        }

    item = {
        "sku_id": "31",
        "product_name": "青椒肉丝食材包",
        "sale_status": "available",
        "available_quantity": 3,
        "price_cent": 2500,
        "data_completeness": "complete",
        "net_content": {"value": "500", "unit": "g"},
        "ingredients": [
            {
                "ingredient_id": "11",
                "ingredient_code": "pepper",
                "name": "青椒",
                "review_status": "approved",
                "net_value": "500",
                "net_unit": "g",
                "convert_ratio": "0.8",
                "loss_rate": "0.1",
            }
        ],
        "allergen_codes": [],
    }

    async def catalog():
        """使用商城实际目录字段，不接受客户端商品字段。"""
        return {"version": "catalog-1", "items": [item]}

    writes = []

    async def publish(method, path, payload, *, request_id):
        """回读发布正文和幂等键，不产生任何真实商城数据。"""
        writes.append((payload, request_id))
        return {"package_sn": "synthetic-package", "package_version": 1, "status": "available"}

    monkeypatch.setattr(health_vision_service, "configuration", configured)
    monkeypatch.setattr(purchase, "current_catalog", catalog)
    monkeypatch.setattr(purchase, "commerce_request", publish)
    client, sessions, users = family_profile_http
    _, path, data, headers = await source(client, users["self"])
    data["analysis_consent"] = {key: approved[key] for key in ["processor", "policy_version"]}
    assert (await client.post(path, headers=headers, json=data)).status_code == 200
    request_id, run_id, thread, project = [str(uuid4()) for _ in range(4)]
    async with sessions() as db:
        member = await db.scalar(select(FamilyMember).where(FamilyMember.subject_uid == "self"))
        link = await db.scalar(
            select(HealthFamilyProfileLink).where(HealthFamilyProfileLink.source_member_id == member.id)
        )
        for slug in CONSULTATION_SKILLS:
            db.add(
                Skill(
                    slug=slug, name=slug, description="合成测试", source_type="builtin", dir_path=slug, share_config={}
                )
            )
        db.add(
            Project(
                id=project,
                uid="self",
                selection_status="implicit",
                directory_mode="managed",
                workdir_path="projects/" + project,
            )
        )
        await db.flush()
        conversation = Conversation(uid="self", thread_id=thread, agent_id="health-consultation", project_id=project)
        db.add(conversation)
        await db.flush()
        db.add(
            HealthConsultation(
                conversation_id=conversation.id, member_id=link.member_id, actor_uid="self", request_id=str(uuid4())
            )
        )
        db.add(
            HealthProcessingConsent(
                member_id=link.member_id,
                actor_uid="self",
                purpose="consultation",
                processor=approved["processor"],
                policy_version=approved["policy_version"],
            )
        )
        run = AgentRun(
            id=run_id,
            request_id=request_id,
            uid="self",
            agent_slug="health-consultation",
            conversation_thread_id=thread,
            conversation_id=conversation.id,
            runtime_scope_id=thread,
            status="completed",
            input_payload={"health_processing": approved},
            manifest={"resources": {"tools": ["query_family_nutrition_knowledge", "find_food_packages"]}},
        )
        db.add(run)
        await db.flush()
        source_data = {
            "kind": "conversation_package",
            "uid": "self",
            "member_id": link.member_id,
            "run_id": run_id,
            "request_id": request_id,
            "query": "青椒肉丝",
            "catalog_version": "catalog-1",
            "sku_id": "31",
            "composition_hash": purchase.composition_hash(item),
            "profile_hash": input_fingerprint(member.profile),
            "expires_at": int(time.time()) + 1800,
        }
        token = purchase.encode_offer(source_data)
        question = Message(
            conversation_id=conversation.id, role="user", content="有没有青椒肉丝的食材包", request_id=request_id
        )
        answer = Message(
            conversation_id=conversation.id,
            role="assistant",
            request_id=request_id,
            run_id=run_id,
            content="这是对应食材包。[食材包:" + token + "]",
            message_type="text",
            delivery_status="complete",
        )
        db.add_all([question, answer])
        await db.flush()
        run.output_message_id = answer.id
        db.add(
            AgentRunRequest(
                request_id=request_id,
                uid="self",
                agent_slug="health-consultation",
                conversation_thread_id=thread,
                input_message_id=question.id,
                dispatched_run_id=run_id,
                status="dispatched",
            )
        )
        await db.commit()
    url = "/api/health/v1/conversation-purchases/" + request_id
    result = await client.get(url, headers=users["self"])
    assert result.status_code == 200, result.text
    assert result.json()["offers"][0]["available"] is True and not writes
    assert (await client.get(url, headers=users["other"])).status_code == 404
    assert (
        await client.post(url, headers=users["self"], json={"offer_token": token, "sku_id": "unrelated"})
    ).status_code == 422
    for _ in range(2):
        response = await client.post(url, headers=users["self"], json={"offer_token": token})
        assert response.status_code == 200, response.text
    assert writes[0] == writes[1]
    requirement = writes[0][0]["ingredient_requirements"][0]
    assert requirement == {
        "ingredient_id": "11",
        "ingredient_code": "pepper",
        "required_value": "360.00",
        "required_unit": "g",
    }
    item["net_content"]["value"] = "250"
    assert (await client.get(url, headers=users["self"])).json()["offers"][0]["available"] is False
    assert (await client.post(url, headers=users["self"], json={"offer_token": token})).status_code == 409
    assert len(writes) == 2
    async with sessions() as db:
        source_member = await db.scalar(select(FamilyMember).where(FamilyMember.subject_uid == "self"))
        source_member.profile = {key: value for key, value in source_member.profile.items() if key != "dietary_details"}
        await db.commit()
    incomplete = await client.get(url, headers=users["self"])
    assert incomplete.status_code == 409 and incomplete.json()["code"] == "purchase_profile_required"

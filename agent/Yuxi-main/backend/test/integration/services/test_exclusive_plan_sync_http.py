"""同步恢复的计划入口在真实 HTTP/PG 上保持账号隔离与只读状态。"""
# ruff: noqa: F811 -- pytest 注入共享隔离 fixture。

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from test.integration.services.test_health_family_profile_http import (  # noqa: F401
    family_profile_http,
    ensure_live_api_schema,
    cleanup_test_sandboxes,
    cleanup_test_knowledge_resources,
    create_health_member,
)
from yuxi.services import exclusive_plan_service as service
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services import health_task_service
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import HealthExclusivePlanGroup

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def seeded_group(client, sessions, users):
    """只建立合成推荐组，不调用模型或真实商城。"""
    family = await client.post('/api/family', headers=users['self'], json={'name': '合成计划同步验证'})
    assert family.status_code == 200, family.text
    fid, gid = family.json()['id'], str(uuid4())
    async with sessions() as db:
        db.add(HealthExclusivePlanGroup(
            id=gid, actor_uid='self', family_id=fid, request_id=str(uuid4()), basis_hash='a'*64,
            status='generating', selection={}, sources={}, policy={},
            progress={'tiers': {'economy': [{'day': {'day_no': 1}}]},
                      'receipts': {'economy': {'plan_sn': 'synthetic-only'}}},
        ))
        await db.commit()
    return fid, gid


async def test_read_keeps_exact_owner_and_hides_partial_exports(family_profile_http, monkeypatch):
    """准备中的组不展示局部商城引用，越权和错误组均不泄露结果。"""
    client, sessions, users = family_profile_http
    fid, gid = await seeded_group(client, sessions, users)

    async def policy():
        return {'version': 'synthetic'}

    async def context(*args, **kwargs):
        return {'basis_hash': 'a'*64, 'sources': {'members': {'synthetic': {'name': '合成成员'}}}}

    monkeypatch.setattr(service, 'read_plan_policy', policy)
    monkeypatch.setattr(service, 'exclusive_context', context)
    path = f'/api/health/v1/families/{fid}/exclusive-plans/{gid}'
    response = await client.get(path, headers=users['self'])
    assert response.status_code == 200, response.text
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json()['group_id'] == gid
    assert response.json()['status'] == 'generating' and response.json()['completed_days'] == 1
    assert response.json()['plans'] == []
    assert (await client.get(path, headers=users['other'])).status_code == 404
    assert (await client.get(path.replace(gid, str(uuid4())), headers=users['self'])).status_code == 404
    assert (await client.get(path)).status_code in (401, 403)
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(HealthExclusivePlanGroup)) == 1


async def test_multi_day_capability_and_task_entry_contract(family_profile_http, monkeypatch):
    """真实授权与缺输入保持只读；生成服务替身只核对入口委派，不代替计划生成验收。"""
    client, sessions, users = family_profile_http
    member = await create_health_member(client, users['self'])

    async def configuration(session=None):
        return {'policy_version': 'synthetic', **{purpose: {'available': False, 'reason_code': 'policy_not_approved'}
                for purpose in ('consultation', 'meal_plan', 'diet_analysis', 'quality_review', 'purchase')}}

    monkeypatch.setattr(service.health_vision_service, 'configuration', configuration)
    capabilities = await client.get(f'/api/health/v1/members/{member}/capabilities', headers=users['self'])
    assert capabilities.status_code == 200, capabilities.text
    multi = next(row for row in capabilities.json()['tasks'] if row['task_type'] == 'multi_day_plan')
    assert multi['purpose'] == 'meal_plan' and multi['required_inputs'] == ['selection.family_id']
    assert multi['reason_code'] != 'external_contract_required'
    path = f'/api/health/v1/members/{member}/task-entries'
    request_id = str(uuid4())
    headers = {**users['self'], 'Idempotency-Key': request_id}
    missing = await client.post(path, headers=headers, json={'task_type': 'multi_day_plan', 'client_request_id': request_id})
    assert missing.status_code == 200, missing.text
    assert missing.json()['entry_status'] == 'needs_input'
    assert missing.json()['reason_code'] == 'selection_required'
    assert missing.json()['thread_id'] is None
    calls = []

    async def runtime(uid, member_id):
        async with pg_manager.get_async_session_context() as db:
            await HealthVisionRepository(db).authorize(member_id, uid, 'ai_use')
        return []

    async def start(uid, fid, data, *, required_member):
        calls.append((uid, fid, str(data.client_request_id), required_member))
        return {'group_id': str(uuid4()), 'status': 'generating', 'plans': []}

    monkeypatch.setattr(health_task_service, 'health_task_runtime_blockers', runtime)
    monkeypatch.setattr(service, 'start_exclusive_plan', start)
    fid = str(uuid4())
    body = {'task_type': 'multi_day_plan', 'client_request_id': request_id, 'selection': {'family_id': fid}}
    ready = await client.post(path, headers=headers, json=body)
    assert ready.status_code == 200, ready.text
    assert ready.json()['entry_status'] == 'ready' and ready.json()['exclusive_plan']['status'] == 'generating'
    assert calls == [('self', fid, request_id, member)]
    denied = await client.post(path, headers={**users['other'], 'Idempotency-Key': request_id}, json=body)
    assert denied.status_code == 404 and len(calls) == 1
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(HealthExclusivePlanGroup)) == 0


async def test_changed_basis_is_stale_and_read_does_not_rewrite_group(family_profile_http, monkeypatch):
    """档案依据变化后只投影失效，不重做、覆盖或发布旧方案。"""
    client, sessions, users = family_profile_http
    fid, gid = await seeded_group(client, sessions, users)

    async def policy():
        return {'version': 'synthetic'}

    async def context(*args, **kwargs):
        return {'basis_hash': 'b'*64}

    monkeypatch.setattr(service, 'read_plan_policy', policy)
    monkeypatch.setattr(service, 'exclusive_context', context)
    response = await client.get(f'/api/health/v1/families/{fid}/exclusive-plans/{gid}', headers=users['self'])
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'stale' and response.json()['plans'] == []
    rejected = await client.post(f'/api/health/v1/families/{fid}/exclusive-plans', headers=users['self'],
                                json={'client_request_id': str(uuid4()), 'price_cent': 1})
    assert rejected.status_code == 422
    async with sessions() as db:
        row = await db.get(HealthExclusivePlanGroup, gid)
        assert row.status == 'generating' and row.basis_hash == 'a'*64
        assert row.progress['receipts']['economy']['plan_sn'] == 'synthetic-only'
        assert await db.scalar(select(func.count()).select_from(HealthExclusivePlanGroup)) == 1

"""第2、4、6项客户端验收：仅使用专用临时数据库与合成资料。"""
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, UTC
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from server.routers import router
from server.utils.auth_middleware import get_db
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import Base, Department, User
from yuxi.storage.postgres.models_health import DietLog, DietLogRevision, FamilyMember, HealthMealPlanAdoption, VisionConfirmation
from yuxi.utils.auth_utils import AuthUtils
from test.integration.services.test_health_quality_http import setup_quality, action
from test.integration.services.test_health_diet_analysis_http import confirm_analysis_meal
from test.integration.services.test_health_weight_http import create_weight_subject

DSN = os.environ['HEALTH246_POSTGRES_URL']
if not any(host in DSN for host in ('127.0.0.1:15488/client246', 'host.docker.internal:15488/client246')):
    raise RuntimeError('本脚本仅允许专用临时数据库')
EVIDENCE = Path(os.environ['HEALTH246_EVIDENCE'])
engine = create_async_engine(DSN)
sessions = async_sessionmaker(engine, expire_on_commit=False)
facts = {}

@asynccontextmanager
async def health_database():
    async with sessions() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

async def database():
    async with sessions() as session:
        yield session

@asynccontextmanager
async def lifespan(app):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    pg_manager.get_async_session_context = health_database
    users = []
    async with health_database() as session:
        department = Department(name='客户端246合成验收')
        session.add(department)
        await session.flush()
        for name, role in [('client246-owner', 'user'), ('client246-reviewer', 'user'), ('client246-admin', 'superadmin')]:
            row = User(uid=name, username=name, role=role, password_hash='not-a-login-password', department_id=department.id)
            session.add(row)
            await session.flush()
            token = AuthUtils.create_access_token({'sub': str(row.id)})
            users.append({'uid': name, 'account_id': str(row.id), 'headers': {'Authorization': 'Bearer ' + token}, 'token': token})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        current = await setup_quality(client, users)
        await action(client, users[0]['headers'], current['case']['review_id'], 'submit', 1)
        await action(client, users[1]['headers'], current['case']['review_id'], 'approve', 2)
        source, _ = await confirm_analysis_meal(client, users[0]['headers'], users[2]['headers'], current['member'], eaten_at='2026-10-16T12:00:00+08:00')
        subject = await create_weight_subject(client, users, member_id=current['member'])
        for value, condition, hour in [(5, 'fasting', 0), (7, 'fasting', 1), (9, 'after_meal_2h', 2)]:
            response = await client.post(subject.measurement_path, headers=users[0]['headers'], json={
                'id': str(uuid4()), 'kind': 'blood_glucose', 'values': {'glucose': value},
                'measured_at': datetime(2026, 10, 16, hour, tzinfo=UTC).isoformat(), 'source': 'synthetic', 'condition': condition})
            assert response.status_code == 200, response.text
        # 本人关联会正确失效原批准；另建独立成员验证当前有效批准的采用。
        async with health_database() as session:
            reviewer = User(uid='client246-reviewer-plan', username='client246-reviewer-plan', role='user', password_hash='not-a-login-password', department_id=department.id)
            session.add(reviewer)
            await session.flush()
            plan_users = [users[0], {'uid': reviewer.uid, 'headers': {'Authorization': 'Bearer ' + AuthUtils.create_access_token({'sub': str(reviewer.id)})}}, users[2]]
        adopted = await setup_quality(client, plan_users)
        await action(client, users[0]['headers'], adopted['case']['review_id'], 'submit', 1)
        await action(client, plan_users[1]['headers'], adopted['case']['review_id'], 'approve', 2)
        async with health_database() as session:
            (await session.get(FamilyMember, adopted['member'])).display_name = '合成采用成员'
        facts.update(member_id=current['member'], plan_id=adopted['plan'], plan_member_id=adopted['member'],
                     invalidated_plan_id=current['plan'], record_id=source['id'], token=users[0]['token'], account_id=users[0]['account_id'])
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / 'fixture.json').write_text(json.dumps(facts, ensure_ascii=False), encoding='utf-8')
    try:
        yield
    finally:
        await engine.dispose()

app = FastAPI(lifespan=lifespan)
app.include_router(router, prefix='/api')
app.dependency_overrides[get_db] = database

@app.get('/fixture-ready')
async def ready():
    return {'ready': bool(facts)}

@app.get('/fixture-facts')
async def inspect_facts():
    """独立回读持久事实，不把HTTP成功当作业务提交证据。"""
    async with sessions() as session:
        record = await session.get(DietLog, facts['record_id'])
        adoptions = list((await session.scalars(select(HealthMealPlanAdoption))).all())
        return {'record_id': record.id, 'version': record.version,
                'energy_kcal': record.snapshot['nutrition']['totals']['energy_kcal'],
                'revisions': await session.scalar(select(func.count()).select_from(DietLogRevision)),
                'records': await session.scalar(select(func.count()).select_from(DietLog)),
                'confirmations': await session.scalar(select(func.count()).select_from(VisionConfirmation)),
                'adoptions': [{'id': row.id, 'status': row.status, 'version': row.version} for row in adoptions]}

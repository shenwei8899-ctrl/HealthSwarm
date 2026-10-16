"""正式 App 浏览器验收专用独立 PG schema；全部用户和档案均为合成数据。"""
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from datetime import timedelta
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from server.routers import router
from server.utils.auth_middleware import get_db
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import Base, Department, User
from yuxi.services.family_service import FamilyService
from yuxi.services.family_schemas import ProfileUpdate
from yuxi.utils.auth_utils import AuthUtils
from yuxi.utils.datetime_utils import utc_now_naive

ROOT = Path('/app/formal-client-evidence')
SCHEMA = 'formal_client_' + uuid4().hex
PASSWORD = 'Synthetic-Only-20261016!'
bootstrap = create_async_engine(os.environ['POSTGRES_URL'])
engine = create_async_engine(os.environ['POSTGRES_URL'], connect_args={'server_settings': {'search_path': SCHEMA}})
sessions = async_sessionmaker(engine, expire_on_commit=False)

@asynccontextmanager
async def session_context():
    async with sessions() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise

async def database():
    async with session_context() as db:
        yield db

@asynccontextmanager
async def lifespan(app):
    async with bootstrap.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        pg_manager.get_async_session_context = session_context
        async with sessions() as db:
            department = Department(name='正式客户端合成验收')
            db.add(department); await db.flush()
            for uid in ('formal_owner', 'formal_peer', 'formal_stranger'):
                db.add(User(uid=uid, username=uid, password_hash=AuthUtils.hash_password(PASSWORD), role='user', department_id=department.id))
            await db.commit()
            owner = FamilyService(db, 'formal_owner')
            family = await owner.create_family('合成共享家庭', '合成户主')
            peer = await owner.add_member(family['id'], '合成成员', '家人')
            invite = await owner.invite(family['id'], peer['id'])
            await FamilyService(db, 'formal_peer').join(invite['code'])
            target = await owner.add_member(family['id'], '待共享验收', '家人')
            await owner.update_profile(family['id'], target['id'], ProfileUpdate(expected_version=1, profile={'sex':'female','birth_date':'1990-01-01','height_cm':165,'activity_level':'light','goal':'合成规律饮食','medical_history':'仅合成验收','allergens':[], 'condition_records':[{'description':'合成情况','status':'unknown'}]}))
            member = await owner.repo.member(family['id'], target['id'])
            member.grant_expires_at = utc_now_naive() - timedelta(days=1)
            await db.commit()
            other = await FamilyService(db, 'formal_stranger').create_family('合成独立家庭', '其他账号')
        (ROOT/'fixture.json').write_text(json.dumps({'schema':SCHEMA,'family_id':family['id'],'owner_member_id':family['members'][0]['id'],'peer_member_id':peer['id'],'target_id':target['id'],'stranger_family_id':other['id'],'password':PASSWORD}),encoding='utf-8')
        yield
    finally:
        await engine.dispose()
        async with bootstrap.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{SCHEMA}" CASCADE'))
            assert not await conn.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:name)'),{'name':SCHEMA})
        (ROOT/'fixture-cleanup.json').write_text(json.dumps({'schema':SCHEMA,'removed':True}))
        await bootstrap.dispose()

app = FastAPI(lifespan=lifespan)
app.include_router(router, prefix='/api')
app.dependency_overrides[get_db] = database
@app.get('/fixture-ready')
async def ready():
    return {'ready':True}

"""隔离跨服务验收：只替换微信供应商，认证、JWT 与数据库均使用实际实现。"""
import asyncio
import importlib.util
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import select

from server.utils.auth_middleware import get_db
from yuxi.services import wechat_login_service
from yuxi.storage.postgres.models_business import Base, Department
from yuxi.storage.postgres import models_health  # noqa: F401


async def main():
    """仅在明确的独立测试库和测试标识下启动。"""
    dsn = os.environ['WECHAT_TEST_POSTGRES_URL']
    if not dsn.endswith('/wechat_login_test') or os.getenv('IDENTITY_E2E_TEST_ONLY') != 'true':
        raise RuntimeError('仅允许独立测试数据库')
    os.environ.update(JWT_SECRET_KEY='synthetic-identity-e2e-secret-00000000000000',
                      WECHAT_LOGIN_ENABLED='true', WECHAT_APP_ID='wx1234567890abcdef',
                      WECHAT_APP_SECRET='synthetic-only', WECHAT_AUTO_REGISTER='true',
                      YUXI_INSTANCE_ID='synthetic-identity-e2e', REDIS_URL=os.environ['WECHAT_TEST_REDIS_URL'])
    engine = create_async_engine(dsn)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as db:
        department = await db.scalar(select(Department).where(Department.name == 'identity-e2e-synthetic'))
        if department is None:
            department = Department(name='identity-e2e-synthetic')
            db.add(department)
            await db.commit()
        os.environ['WECHAT_USER_DEPARTMENT_ID'] = str(department.id)

    async def provider(settings, code):
        """合成微信响应仅存在于隔离测试入口。"""
        if code not in {'member-a', 'member-b', 'new-member', 'racing-member'}:
            raise HTTPException(401, 'invalid synthetic code')
        return 'synthetic-' + code

    async def database():
        """每个请求使用独立实际事务。"""
        async with sessions() as db:
            yield db

    wechat_login_service.exchange_wechat_code = provider
    path = Path('/app/server/routers/wechat_auth_router.py')
    spec = importlib.util.spec_from_file_location('identity_e2e_route', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = FastAPI()
    app.include_router(module.wechat_auth, prefix='/api')
    app.dependency_overrides[get_db] = database
    await uvicorn.Server(uvicorn.Config(app, host='0.0.0.0', port=6060, log_level='warning')).serve()
    await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())

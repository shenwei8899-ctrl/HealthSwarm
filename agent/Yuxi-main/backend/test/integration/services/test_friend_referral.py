"""独立 PostgreSQL 验证邀请唯一约束、并发编号和事务回滚。"""

import asyncio
import os
from uuid import uuid4

from test.integration.services.test_onboarding_preparation_http import (
    cleanup_test_sandboxes, cleanup_test_knowledge_resources, ensure_live_api_schema,
)  # noqa: F401

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.repositories.referral_repository import ReferralRepository
from yuxi.services.referral_service import referral_records
from yuxi.storage.postgres.models_business import Department, FriendReferral, User
from yuxi.storage_migrations.v018_friend_referral import upgrade_friend_referral
from types import SimpleNamespace


@pytest.mark.asyncio
async def test_referral_atomic_success_and_concurrency(monkeypatch):
    """测试库必须显式命名，合成数据保存在每次运行独立 schema。"""
    dsn = os.getenv("REFERRAL_TEST_POSTGRES_URL", "")
    if not dsn:
        pytest.skip("REFERRAL_TEST_POSTGRES_URL 未配置")
    if dsn.rsplit("/", 1)[-1] != "referral_test":
        raise RuntimeError("仅允许独立 referral_test 数据库")
    schema = "referral_" + uuid4().hex
    bootstrap = create_async_engine(dsn)
    async with bootstrap.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            for table in (Department.__table__, User.__table__):
                await connection.run_sync(lambda conn, table=table: table.create(conn))
        await upgrade_friend_referral(SimpleNamespace(async_engine=engine))
        await upgrade_friend_referral(SimpleNamespace(async_engine=engine))
        async with sessions.begin() as db:
            for uid in ("inviter", "one", "two", "three"):
                db.add(User(uid=uid, username=uid, password_hash="synthetic"))
            await db.flush()
            row = await ReferralRepository(db).prepare("inviter", "a" * 24)
            assert (await ReferralRepository(db).valid_code(row.code)).inviter_uid == "inviter"
            for uid in ("one", "two", "three"):
                await ReferralRepository(db).bind(uid, row, "share")

        async def complete(uid):
            """不同会话同时完成建档，仅有数据库拥有最终编号。"""
            async with sessions.begin() as db:
                await ReferralRepository(db).complete(uid)

        await asyncio.gather(complete("one"), complete("one"), complete("two"))
        async with sessions() as db:
            assert await db.get(FriendReferral, "three") is not None
            result = await referral_records(db, "inviter", None, 1)
            assert result["total"] == 2 and result["next_cursor"] == 2
            assert result["items"][0]["label"] == "好友002"
            assert set(result["items"][0]) == {"label", "completed_at"}
            assert (await referral_records(db, "one", None, 20))["total"] == 0
        async with sessions() as db:
            await ReferralRepository(db).complete("three")
            await db.rollback()
        async with sessions() as db:
            assert (await db.get(FriendReferral, "three")).completed_at is None
    finally:
        await engine.dispose()
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await bootstrap.dispose()

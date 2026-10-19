"""微信身份摘要与业务账号的 PostgreSQL 关联。"""

import hashlib

from sqlalchemy import select, text

from yuxi.storage.postgres.models_business import Department, User, WechatIdentity


class WechatIdentityRepository:
    """由登录服务拥有事务，身份与账号约束共同阻止并发重复注册。"""

    def __init__(self, db):
        """使用当前请求的数据库会话。"""
        self.db = db

    async def lock_identity(self, appid, digest):
        """串行化同一微信身份，包括还没有关联记录的首次注册。"""
        lock = int.from_bytes(hashlib.sha256(f"{appid}:{digest}".encode()).digest()[:8], "big", signed=True)
        await self.db.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": lock})

    async def identity(self, appid, digest):
        """读取关联；停用账号的记录继续占用身份。"""
        return await self.db.scalar(
            select(WechatIdentity).where(WechatIdentity.appid == appid, WechatIdentity.openid_hash == digest)
        )

    async def user(self, user_id):
        """锁定关联账号并交给服务判断停用和锁定状态。"""
        return await self.db.scalar(select(User).where(User.id == user_id).with_for_update())

    async def login_user(self, identifier):
        """与现有登录一致，优先 UID，再匹配手机号。"""
        user = await self.db.scalar(select(User).where(User.uid == identifier).with_for_update())
        if user is None:
            user = await self.db.scalar(select(User).where(User.phone_number == identifier).with_for_update())
        return user

    async def department(self, department_id):
        """注册只使用运营明确配置的既有部门。"""
        return await self.db.scalar(select(Department).where(Department.id == department_id))

    async def bind(self, appid, digest, user):
        """在当前事务创建唯一关联，完整性异常由服务转换。"""
        self.db.add(WechatIdentity(appid=appid, openid_hash=digest, user_id=user.id))
        await self.db.flush()

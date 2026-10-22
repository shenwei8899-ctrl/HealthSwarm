"""微信身份摘要的非破坏性、幂等业务迁移。"""

from sqlalchemy import text


async def upgrade_wechat_identity(manager):
    """仅创建身份关联表；不改变既有账号、部门或健康授权。"""
    async with manager.async_engine.begin() as connection:
        await connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS wechat_identities (
                id SERIAL PRIMARY KEY,
                appid VARCHAR(18) NOT NULL,
                openid_hash VARCHAR(64) NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_wechat_app_identity UNIQUE (appid, openid_hash),
                CONSTRAINT uq_wechat_app_user UNIQUE (appid, user_id)
            )
        """)
        )

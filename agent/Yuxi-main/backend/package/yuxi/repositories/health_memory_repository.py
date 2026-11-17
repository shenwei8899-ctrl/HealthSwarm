"""成员记忆的账号隔离查询及不可变请求收据。"""

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Message, FamilyMember, FamilyArchive
from yuxi.storage.postgres.models_health import (
    HealthMemoryFact,
    HealthMemoryRevision,
    HealthMemoryUse,
    HealthFamilyProfileLink,
)


class HealthMemoryRepository:
    """成员授权由用例执行，查询始终限定当前账号。"""

    def __init__(self, session):
        self.session = session

    async def list_active(self, uid, member_id):
        """读取有界有效记忆，不将撤回版本提供给模型。"""
        return list(
            (
                await self.session.scalars(
                    select(HealthMemoryFact)
                    .where(
                        HealthMemoryFact.actor_uid == uid,
                        HealthMemoryFact.member_id == member_id,
                        HealthMemoryFact.status == "active",
                    )
                    .order_by(HealthMemoryFact.updated_at.desc(), HealthMemoryFact.id)
                    .limit(101)
                )
            ).all()
        )

    async def list_account(self, uid, *, after=None, limit=50, member_ids=None, recallable_only=False):
        """稳定 ID 游标管理全部主体；召回范围由服务端成员目录限制。"""
        query = select(HealthMemoryFact).where(HealthMemoryFact.actor_uid == uid, HealthMemoryFact.status == "active")
        if recallable_only:
            query = query.where(HealthMemoryFact.id.in_(self.current_recall_ids(uid)))
        if after:
            query = query.where(HealthMemoryFact.id > after)
        if member_ids is not None:
            query = query.where(HealthMemoryFact.member_id.in_(member_ids))
        return list((await self.session.scalars(query.order_by(HealthMemoryFact.id).limit(limit + 1))).all())

    async def get(self, uid, fact_id, *, lock=False):
        """不允许知道标识的其他账号访问记忆。"""
        query = (
            select(HealthMemoryFact)
            .where(HealthMemoryFact.id == fact_id, HealthMemoryFact.actor_uid == uid)
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query)

    async def slot(self, uid, member_id, key):
        """调用方已持有成员锁，串行处理同一语义槽位。"""
        return await self.session.scalar(
            select(HealthMemoryFact).where(
                HealthMemoryFact.actor_uid == uid,
                HealthMemoryFact.member_id == member_id,
                HealthMemoryFact.fact_key == key,
            )
        )

    async def receipt(self, uid, request_id, source_hash):
        """撤回后也保留幂等收据，禁止旧请求复活事实。"""
        return await self.session.scalar(
            select(HealthMemoryRevision).where(
                HealthMemoryRevision.actor_uid == uid,
                HealthMemoryRevision.request_id == request_id,
                HealthMemoryRevision.source_hash == source_hash,
            )
        )

    async def source_message(self, run):
        """工具只引用当前 Run 对应的服务器持久化用户消息。"""
        return await self.session.scalar(
            select(Message)
            .join(
                AgentRunRequest,
                AgentRunRequest.input_message_id == Message.id,
            )
            .where(
                AgentRunRequest.request_id == run.request_id,
                AgentRunRequest.uid == run.uid,
                Message.role == "user",
                Message.request_id == run.request_id,
            )
        )

    async def revisions(self, fact_id):
        """管理入口回读版本与来源，不重建会话全文。"""
        return list(
            (
                await self.session.scalars(
                    select(HealthMemoryRevision)
                    .where(
                        HealthMemoryRevision.fact_id == fact_id,
                    )
                    .order_by(HealthMemoryRevision.version)
                )
            ).all()
        )

    async def record_uses(self, run, references):
        """读取及历史传播的依赖在外呼前提交，重放不重复插入。"""
        for fact_id, version in set(references):
            await self.session.execute(
                insert(HealthMemoryUse).values(run_id=run.id, fact_id=fact_id, version=version).on_conflict_do_nothing()
            )

    async def supersede_run_use(self, run, fact):
        """同轮明确改写事实后，模型依赖转向本轮产生的新版本。"""
        await self.session.execute(
            delete(HealthMemoryUse).where(
                HealthMemoryUse.run_id == run.id,
                HealthMemoryUse.fact_id == fact.id,
                HealthMemoryUse.version != fact.version,
            )
        )
        await self.record_uses(run, [(fact.id, fact.version)])

    async def own_revision(self, uid, fact_id, version, request_id):
        """仅本请求实际写出的当前版本允许替代同轮旧工具投影。"""
        return await self.session.scalar(
            select(HealthMemoryRevision).where(
                HealthMemoryRevision.actor_uid == uid,
                HealthMemoryRevision.fact_id == fact_id,
                HealthMemoryRevision.version == version,
                HealthMemoryRevision.request_id == request_id,
                HealthMemoryRevision.source_run_id.is_not(None),
            )
        )

    def invalid_requests(self, uid, member_id):
        """从 PG 版本依赖识别写入、读取及派生回答的失效请求。"""
        return (
            select(AgentRun.request_id)
            .join(HealthMemoryUse, HealthMemoryUse.run_id == AgentRun.id)
            .join(HealthMemoryFact, HealthMemoryFact.id == HealthMemoryUse.fact_id)
            .where(
                AgentRun.uid == uid,
                HealthMemoryFact.actor_uid == uid,
                or_(
                    HealthMemoryFact.status != "active",
                    HealthMemoryUse.version != HealthMemoryFact.version,
                    HealthMemoryFact.id.not_in(self.current_recall_ids(uid)),
                ),
            )
        )

    def current_recall_ids(self, uid):
        """日终摘要同样排除退出家庭后失效的真实来源，避免复活旧自述。"""
        actor = aliased(FamilyMember)
        return (
            select(HealthMemoryFact.id)
            .join(HealthFamilyProfileLink, HealthFamilyProfileLink.member_id == HealthMemoryFact.member_id)
            .join(FamilyMember, FamilyMember.id == HealthFamilyProfileLink.source_member_id)
            .join(FamilyArchive, FamilyArchive.id == HealthFamilyProfileLink.family_id)
            .join(actor, actor.family_id == FamilyArchive.id)
            .where(
                actor.subject_uid == uid,
                actor.is_active.is_(True),
                FamilyMember.is_active.is_(True),
                FamilyArchive.archived_at.is_(None),
                FamilyMember.family_id == FamilyArchive.id,
                HealthMemoryFact.actor_uid == uid,
                HealthMemoryFact.provenance["family_id"].as_string() == FamilyArchive.id,
                HealthMemoryFact.provenance["source_member_id"].as_string() == FamilyMember.id,
            )
        )

    async def history_uses(self, uid, thread_id):
        """返回本线程可信版本依赖；不依赖模型可见的工具收据。"""
        return list(
            (
                await self.session.execute(
                    select(
                        AgentRun.request_id,
                        HealthMemoryUse.fact_id,
                        HealthMemoryUse.version,
                        HealthMemoryFact.status,
                        HealthMemoryFact.version,
                    )
                    .join(HealthMemoryUse, HealthMemoryUse.run_id == AgentRun.id)
                    .join(HealthMemoryFact, HealthMemoryFact.id == HealthMemoryUse.fact_id)
                    .where(
                        AgentRun.uid == uid,
                        AgentRun.conversation_thread_id == thread_id,
                        HealthMemoryFact.actor_uid == uid,
                    )
                )
            ).all()
        )

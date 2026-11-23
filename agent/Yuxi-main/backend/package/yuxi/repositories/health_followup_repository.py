"""最终答案的追问认领与元数据保存，事务由用例服务持有。"""

import time

from sqlalchemy import select

from yuxi.services.health_followup_types import FOLLOWUPS_KEY, answer_digest
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AgentRun, Message


class HealthFollowupRepository:
    """只从账号、线程及权威输出指针确定来源。"""

    def __init__(self, session):
        """复用 owning transaction，不自行提交。"""
        self.session = session

    async def answer(self, uid, thread_id, message_id, *, lock=False):
        """拒绝其他账号、线程、运行及非最终消息。"""
        query = (
            select(Message, AgentRun)
            .join(AgentRun, Message.run_id == AgentRun.id)
            .where(
                Message.id == message_id,
                Message.role == "assistant",
                Message.conversation_id == AgentRun.conversation_id,
                Message.id == AgentRun.output_message_id,
                AgentRun.uid == uid,
                AgentRun.conversation_thread_id == str(thread_id),
                AgentRun.status == "completed",
            )
        )
        if lock:
            query = query.with_for_update(of=Message)
        row = (await self.session.execute(query)).first()
        if row is None:
            raise HealthVisionError("not_found", "未找到可用的咨询答案", 404)
        return row

    async def question(self, run):
        """只取同一请求的原始用户输入，不从相邻轮次猜测。"""
        text = await self.session.scalar(
            select(Message.content).where(
                Message.id == run.input_message_id,
                Message.conversation_id == run.conversation_id,
                Message.request_id == run.request_id,
                Message.role == "user",
            )
        )
        if not isinstance(text, str) or not text.strip():
            raise HealthVisionError("answer_unavailable", "答案缺少原始问题", 409)
        return text

    def claim(self, message):
        """锁读后的首次认领；已经认领的答案不因刷新再调用模型。"""
        if FOLLOWUPS_KEY in (message.extra_metadata or {}):
            return False
        message.extra_metadata = {
            **(message.extra_metadata or {}),
            FOLLOWUPS_KEY: {
                "status": "pending",
                "answer_hash": answer_digest(message.content),
                "claimed_at": time.time(),
            },
        }
        return True

    def finish(self, message, result):
        """只替换本功能字段，保留引用及其他并发维护的元数据。"""
        old = (message.extra_metadata or {}).get(FOLLOWUPS_KEY, {})
        if old.get("answer_hash") != answer_digest(message.content):
            raise HealthVisionError("source_invalidated", "原答案已变化", 410)
        message.extra_metadata = {
            **(message.extra_metadata or {}),
            FOLLOWUPS_KEY: {**old, "status": "ready" if result.followups else "unavailable", **result.model_dump()},
        }

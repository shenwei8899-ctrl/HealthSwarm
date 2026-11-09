"""对话内意图分析的幂等回执。"""

from sqlalchemy import select
from yuxi.storage.postgres.models_business import Conversation, Message
from yuxi.services.health_vision_types import HealthVisionError


class HealthIntentRepository:
    """复用对话元数据，不创建平行的 AgentRun 状态。"""

    def __init__(self, session):
        """事务由分类服务持有。"""
        self.session = session

    async def claim(self, conversation_id, request_id, fingerprint):
        """提交外呼占位，重放同键不会重复向模型发送。"""
        conversation = await self.session.scalar(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        metadata = dict(conversation.extra_metadata or {})
        receipts = dict(metadata.get("health_intent_receipts") or {})
        receipt = receipts.get(request_id)
        if receipt is not None:
            if receipt["fingerprint"] != fingerprint:
                raise HealthVisionError("request_conflict", "同一分类请求不能改变问题或上下文", 409)
            return receipt
        receipts[request_id] = {"fingerprint": fingerprint, "result": None}
        metadata["health_intent_receipts"] = receipts
        conversation.extra_metadata = metadata
        return None

    async def finish(self, conversation_id, request_id, result):
        """仅更新已占位请求，保存有限分类结果。"""
        conversation = await self.session.scalar(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        metadata = dict(conversation.extra_metadata or {})
        receipts = dict(metadata["health_intent_receipts"])
        receipts[request_id] = {**receipts[request_id], "result": result.model_dump(mode="json")}
        metadata["health_intent_receipts"] = receipts
        conversation.extra_metadata = metadata

    async def recent_dialogue(self, conversation_id):
        """只给分类器最近两条普通对话，不包含工具资料或图片。"""
        rows = list(
            await self.session.scalars(
                select(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.message_type == "text",
                    Message.role.in_(("user", "assistant")),
                    Message.delivery_status == "complete",
                )
                .order_by(Message.id.desc())
                .limit(2)
            )
        )
        return [{"role": row.role, "text": row.content[:800]} for row in reversed(rows)]

    async def is_published_message(self, message):
        """仅公开与已提交分类回执完全一致的入口或追问。"""
        import json

        conversation = await self.session.get(Conversation, message.conversation_id)
        receipt = ((conversation.extra_metadata or {}).get("health_intent_receipts") or {}).get(message.request_id)
        result = (receipt or {}).get("result")
        if not result or result.get("route") not in {"exclusive_plan", "needs_clarification"}:
            return False
        try:
            return json.loads(message.content) == {"result_type": "health_intent", **result}
        except (ValueError, TypeError):
            return False

"""每次健康模型循环独立预留，禁止 SDK 在账本外自动重试。"""

from langchain.agents.middleware import AgentMiddleware

from yuxi.services import health_ai_budget_service as budget


class HealthAiBudgetMiddleware(AgentMiddleware):
    """只装配到首批开放的咨询、指标与饮食解释角色。"""

    def __init__(self, purpose: str):
        """用途由服务端固定角色指定。"""
        self.purpose = purpose

    async def awrap_model_call(self, request, handler):
        """外呼返回的真实用量用于结算，失败保留已提交预留。"""
        from yuxi.services.health_consultation_service import require_consultation_attempt

        context = request.runtime.context
        reservation = await budget.reserve_model(self.purpose, context.run_id, context.model)
        try:
            await require_consultation_attempt(context)
            model = budget.reserved_chat_model(reservation, session_id=context.thread_id)
            response = await handler(request.override(model=model))
        except Exception:
            await budget.settle(reservation)
            raise
        messages = getattr(response, "model_response", response).result
        usage = getattr(messages[0], "usage_metadata", None) if len(messages) == 1 else None
        await budget.settle(reservation, usage)
        return response

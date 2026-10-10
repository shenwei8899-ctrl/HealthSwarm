"""用户选定普通配餐完成结果的次日提议输入。"""

from pydantic import Field

from yuxi.services.health_plan_adoption_types import NextDayProposalInput


class AgentNextDayProposalInput(NextDayProposalInput):
    """明确选择当前请求、最终消息和明日预览，不接受模型业务字段。"""

    request_id: str = Field(min_length=1, max_length=64)
    final_message_id: int = Field(gt=0, strict=True)

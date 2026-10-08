"""单餐反馈的公开输入边界。"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator
from yuxi.services.health_vision_types import HealthDTO

FeedbackTag = Literal["too_salty", "too_oily", "too_sweet", "too_spicy", "portion_large", "portion_small", "discomfort"]


class MealFeedbackChange(HealthDTO):
    """显式选择餐次并提交当前版本，初次填写版本为零。"""

    client_request_id: UUID
    version: int = Field(ge=0)
    consumption: Literal["unknown", "all", "most", "half", "little", "none"] = "unknown"
    tags: list[FeedbackTag] = Field(default_factory=list, max_length=7)
    comment: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def useful_feedback(self):
        """拒绝空反馈和重复标签，不把比例用来重算营养。"""
        self.comment = self.comment.strip()
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("反馈标签不能重复")
        if not self.comment and not self.tags and self.consumption == "unknown":
            raise ValueError("请填写至少一项餐后体验")
        return self


class MealFeedbackRevoke(HealthDTO):
    """撤回已存在的反馈版本。"""

    client_request_id: UUID
    version: int = Field(ge=1)


class FeedbackConversationInput(HealthDTO):
    """业务入口由用户明确选择确认来源，模型没有此能力。"""

    client_request_id: UUID
    source_version: Annotated[int, Field(strict=True, gt=0)]


class DialogFeedbackInput(HealthDTO):
    """工具只提供本轮原文和反馈版本，身份与餐次由服务器绑定。"""

    quote: str = Field(min_length=1, max_length=500)
    version: Annotated[int, Field(strict=True, ge=0)]


class DialogFeedbackAnswer(HealthDTO):
    """最终仅选择本轮写入收据或补充问题。"""

    feedback_saved: Literal[True] | None = None
    questions: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def one_answer(self):
        """成功声明和问题互斥，不允许空结果。"""
        if (self.feedback_saved is not None) == bool(self.questions) or any(not x.strip() for x in self.questions):
            raise ValueError("请选择反馈收据或提出补充问题")
        return self

"""成员自述记忆的公开输入与持续性边界。"""

from typing import Literal
from uuid import UUID

from pydantic import Field

from yuxi.services.health_vision_types import HealthDTO, HealthVisionError

MemoryKind = Literal["preference", "restriction", "health_self_report"]


class MemoryPatch(HealthDTO):
    """用户显式编辑仍保留自述来源及版本。"""

    client_request_id: UUID
    version: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=500)
    kind: MemoryKind


class MemoryRevoke(HealthDTO):
    """撤回按请求和当前版本幂等执行。"""

    client_request_id: UUID
    version: int = Field(ge=1)


def validate_memory_statement(member, uid, subject, quote, user_content):
    """旧调用的来源边界；持续性由统一语义处理判定。"""
    if quote not in user_content:
        raise HealthVisionError("memory_source_invalid", "记忆必须引用本轮用户原文")
    self_subject = subject == "我" and member.owner_uid == uid and member.relationship_label in {"本人", "自己", "我"}
    if subject != member.display_name and not self_subject:
        raise HealthVisionError("memory_subject_unclear", "成员归属不明确，请先说明是哪位成员")

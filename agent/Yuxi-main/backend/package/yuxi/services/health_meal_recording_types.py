"""明确实际摄入的人工记餐与逐成员批量协议。"""

from uuid import UUID

from pydantic import Field, model_validator

from yuxi.services.health_vision_types import HealthDTO, MealPayload


class MealRecordingInput(HealthDTO):
    """一次用户确认固定成员、菜品版本和实际摄入。"""

    member_id: UUID
    client_request_id: UUID
    meal: MealPayload
    accept_incomplete: bool = False

    @model_validator(mode="after")
    def actual_intake(self):
        """人工记餐不伪造照片，不用整桌比例猜测个人摄入。"""
        if (
            self.meal.photos
            or not self.meal.items
            or any(
                item.locations
                or item.excluded
                or item.share_ratio != 1
                or (item.grams is None and item.portion_reference_id is None)
                or item.portion_source == "unknown"
                for item in self.meal.items
            )
        ):
            raise ValueError("请填写实际吃过的项目及个人克数或已发布份量；不能填写照片位置或整桌分摊")
        return self


class FamilyMealRecordingInput(HealthDTO):
    """批次稳定，重试可只包含失败成员；不参加者不提交。"""

    group_id: UUID
    members: list[MealRecordingInput] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def distinct_members(self):
        """同一批次每位成员只提交一次。"""
        if len({item.member_id for item in self.members}) != len(self.members):
            raise ValueError("同批次成员不能重复")
        return self

"""固定配餐与分析会话的成功响应，来源字段由业务绑定决定。"""

from typing import Literal

from yuxi.services.health_diet_analysis_types import DietAnalysisSelection
from yuxi.services.health_quality_types import PersonalTargetSelection
from yuxi.services.health_safe_planner_types import SafePlannerSelection
from yuxi.services.health_vision_types import ConsultationResult


class MealPlannerConversationResult(ConsultationResult):
    """普通配餐只返回固定角色及线程，业务日期和反馈为空。"""

    agent_slug: Literal["health-meal-planner"]
    business_date: None


class DietAnalystConversationResult(ConsultationResult):
    """未绑定目标的普通分析保留原五字段响应。"""

    agent_slug: Literal["health-diet-analyst"]
    business_date: None


class TargetedDietAnalystConversationResult(DietAnalystConversationResult):
    """明确选定目标时返回原批准版本选择。"""

    target_selection: PersonalTargetSelection


class FeedbackConversationResult(DietAnalystConversationResult):
    """反馈会话必须公开用户选定的确认餐次版本。"""

    feedback_selection: DietAnalysisSelection


class SafeMealPlannerConversationResult(MealPlannerConversationResult):
    """安全改版会话必须返回已保存餐单及专业来源选择。"""

    safe_selection: SafePlannerSelection

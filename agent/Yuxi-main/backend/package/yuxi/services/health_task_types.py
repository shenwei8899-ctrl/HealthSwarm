"""健康任务的明确入口选择与受权只读结果协议。"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, JsonValue, RootModel

from yuxi.services.health_agent_personal_target_types import TargetAwareAnalystInput
from yuxi.services.health_evidence_types import NutritionCitation
from yuxi.services.health_family_planner_types import FamilyPlannerSelection
from yuxi.services.health_initial_meal_plan_types import InitialPlanSelection
from yuxi.services.health_quality_types import Code
from yuxi.services.health_purchase_types import PurchaseSelection
from yuxi.services.health_safe_planner_types import SafePlannerSelection
from yuxi.services.health_vision_types import HealthDTO

HealthTaskType = Literal[
    "consultation",
    "meal_preview",
    "initial_meal_preview",
    "family_meal_revision",
    "safe_meal_revision",
    "diet_analysis",
    "quality_check",
    "purchase_requirements",
]


class BasicTaskEntry(HealthDTO):
    """选择已有交互角色，具体数据仍由其受控工具读取。"""

    task_type: Literal["consultation", "meal_preview"]
    client_request_id: UUID
    selection: None = None


class AnalystTaskEntry(TargetAwareAnalystInput):
    """普通分析仅允许用户显式选择当前批准目标来源。"""

    task_type: Literal["diet_analysis"]
    selection: None = None


class PurchaseTaskEntry(HealthDTO):
    """采购需要明确采用版本和库存选择，缺选择不创建线程。"""

    task_type: Literal["purchase_requirements"]
    client_request_id: UUID
    selection: PurchaseSelection | None = None


class InitialTaskEntry(HealthDTO):
    """明确初始日期、参加者和批准来源。"""

    task_type: Literal["initial_meal_preview"]
    client_request_id: UUID
    selection: InitialPlanSelection | None = None


class FamilyTaskEntry(HealthDTO):
    """明确待修改家庭餐单及全员来源。"""

    task_type: Literal["family_meal_revision"]
    client_request_id: UUID
    selection: FamilyPlannerSelection | None = None


class SafeTaskEntry(HealthDTO):
    """明确单成员安全改版对象及批准来源。"""

    task_type: Literal["safe_meal_revision"]
    client_request_id: UUID
    selection: SafePlannerSelection | None = None


class QualityTaskSelection(HealthDTO):
    """质量检查对象采用现有检查版本和规则约束。"""

    plan_id: UUID
    version: int = Field(gt=0, strict=True)
    rule_code: Code


class QualityTaskEntry(HealthDTO):
    """用户选择方案后才创建质量检查线程。"""

    task_type: Literal["quality_check"]
    client_request_id: UUID
    selection: QualityTaskSelection | None = None


class UnsupportedTaskEntry(HealthDTO):
    """外部契约未就绪的任务不接受健康数据或生成运行。"""

    task_type: Literal["glucose_plan", "multi_day_plan", "automatic_family_coordination"]
    client_request_id: UUID
    selection: None = None


class HealthTaskEntryInput(RootModel):
    """按明确任务类型解析独立选择，拒绝额外成员或营养字段。"""

    root: Annotated[
        BasicTaskEntry
        | AnalystTaskEntry
        | PurchaseTaskEntry
        | InitialTaskEntry
        | FamilyTaskEntry
        | SafeTaskEntry
        | QualityTaskEntry
        | UnsupportedTaskEntry,
        Field(discriminator="task_type"),
    ]


class HealthTaskEntryResult(HealthDTO):
    """入口就绪不表示已创建 Request 或完成业务结果。"""

    entry_status: Literal["ready", "needs_input", "dependency_not_ready"]
    task_type: HealthTaskType | Literal["glucose_plan", "multi_day_plan", "automatic_family_coordination"]
    member_id: UUID
    client_request_id: UUID
    thread_id: UUID | None = None
    agent_slug: str | None = None
    request_submit_url: Literal["/api/agent/runs"] | None = None
    questions: list[str] = Field(default_factory=list)
    reason_code: Literal["selection_required", "external_contract_required"] | None = None


class HealthTaskNeedsInput(HealthDTO):
    """已完成运行的追问独立于执行中断。"""

    result_type: Literal["needs_input"] = "needs_input"
    questions: list[str] = Field(min_length=1, max_length=3)


class HealthTaskGeneralAnswer(HealthDTO):
    """咨询正文和有效科普引用不声明个人营养安全。"""

    result_type: Literal["general_education_answer"] = "general_education_answer"
    scope: Literal["general_education"] = "general_education"
    answer: str
    citations: list[NutritionCitation]


class HealthTaskValidatedResult(HealthDTO):
    """当前业务服务复核的快照，专业批准由业务快照另行表达。"""

    result_type: Literal[
        "meal_plan_preview", "diet_analysis", "meal_feedback", "quality_check", "ingredient_requirements"
    ]
    validation: Literal["current_business_sources"] = "current_business_sources"
    data: dict[str, JsonValue]


class HealthTaskError(HealthDTO):
    """只返回固定执行结局，不投影患者或上游错误正文。"""

    result_type: Literal["error"] = "error"
    code: Literal["execution_failed", "request_rejected", "execution_cancelled", "execution_interrupted"]
    retryable: Literal[False] = False


class HealthTaskResult(HealthDTO):
    """Request、Run 和业务结果分开投影，SSE继续使用现有游标。"""

    request_id: str
    task_type: HealthTaskType
    agent_slug: str
    thread_id: UUID
    member_id: UUID
    request_status: Literal["queued", "dispatched", "cancelled", "rejected", "failed"]
    execution_status: Literal[
        "not_dispatched", "pending", "running", "cancel_requested", "completed", "failed", "cancelled", "interrupted"
    ]
    run_id: str | None = None
    final_message_id: int | None = None
    request_events_url: str | None = None
    run_events_url: str | None = None
    query_url: str
    result: (
        Annotated[
            HealthTaskNeedsInput | HealthTaskGeneralAnswer | HealthTaskValidatedResult | HealthTaskError,
            Field(discriminator="result_type"),
        ]
        | None
    ) = None

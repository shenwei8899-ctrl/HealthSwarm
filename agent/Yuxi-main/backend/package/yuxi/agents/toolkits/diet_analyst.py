"""饮食分析师只读固定成员确认餐次，模型不提供营养或身份。"""

from langgraph.prebuilt.tool_node import ToolRuntime

from yuxi.agents.toolkits.health import HealthReadInput
from yuxi.agents.toolkits.registry import tool
from yuxi.services.health_diet_analysis_types import DietAnalysisPeriod, DietAnalysisSelection
from yuxi.services.health_meal_feedback_types import DialogFeedbackInput


class AnalysisToolInput(DietAnalysisSelection, HealthReadInput):
    """模型选择来源，运行对象由ToolNode注入。"""


class PeriodAnalysisToolInput(DietAnalysisPeriod, HealthReadInput):
    """模型仅指定窗口，账号成员及处理用途由运行绑定。"""


class FeedbackToolInput(DialogFeedbackInput, HealthReadInput):
    """选餐及消息身份均不进入模型输入schema。"""


@tool(category="health", display_name="可分析的已确认餐次", args_schema=HealthReadInput)
async def list_analysis_meals(runtime: ToolRuntime) -> dict:
    """读取当前成员的有效餐次与确认版本，不能读取草稿。"""
    from yuxi.services.health_diet_analysis_service import analyst_meal_records

    return await analyst_meal_records(runtime.context)


@tool(category="health", display_name="已确认单餐分析", args_schema=AnalysisToolInput)
async def analyze_confirmed_meal(record_id, source_version: int, runtime: ToolRuntime) -> dict:
    """单餐营养和缺失由当前有效确认快照投影。"""
    from yuxi.services.health_diet_analysis_service import read_diet_analysis

    selection = DietAnalysisSelection(record_id=record_id, source_version=source_version)
    return await read_diet_analysis(None, None, selection, context=runtime.context)


@tool(category="health", display_name="已确认周期饮食与反馈分析", args_schema=PeriodAnalysisToolInput)
async def analyze_confirmed_period(period_days: int, end_date, runtime: ToolRuntime) -> dict:
    """按北京时间汇总1、7、30天有效确认记录与当前账号反馈。"""
    from yuxi.services.health_diet_analysis_service import read_period_analysis

    period = DietAnalysisPeriod(period_days=period_days, end_date=end_date)
    return await read_period_analysis(None, None, period, context=runtime.context)


@tool(category="health", display_name="当前明确绑定的批准个人目标", args_schema=HealthReadInput)
async def get_bound_personal_targets(runtime: ToolRuntime) -> dict:
    """只读用户明确绑定的当前目标；不计算记录窗口差额、达标或趋势。"""
    from yuxi.services.health_agent_personal_target_service import bound_personal_targets

    return await bound_personal_targets(runtime.context)


@tool(category="health", display_name="用户所选餐次反馈上下文", args_schema=HealthReadInput)
async def get_selected_meal_feedback(runtime: ToolRuntime) -> dict:
    """读取用户明确选择的餐次及当前反馈版本。"""
    from yuxi.services.health_dialog_feedback_service import selected_meal_feedback

    return await selected_meal_feedback(runtime.context)


@tool(category="health", display_name="保存用户所选餐次原文反馈", args_schema=FeedbackToolInput)
async def record_selected_meal_feedback(quote: str, version: int, runtime: ToolRuntime) -> dict:
    """仅将当前完整原文写入服务器绑定的餐次，不猜来源或标签。"""
    from yuxi.services.health_dialog_feedback_service import record_selected_feedback

    return await record_selected_feedback(runtime.context, DialogFeedbackInput(quote=quote, version=version))

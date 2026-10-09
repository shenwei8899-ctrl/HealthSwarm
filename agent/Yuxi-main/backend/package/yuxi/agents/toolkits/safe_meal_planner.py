"""单成员已保存餐单的固定只读安全工具。"""

from langgraph.prebuilt.tool_node import ToolRuntime

from yuxi.agents.toolkits.health import HealthReadInput
from yuxi.agents.toolkits.registry import tool
from yuxi.services.health_safe_planner_types import SafeSwapParameters


class SafeSwapToolInput(SafeSwapParameters, HealthReadInput):
    """菜位参数可见，运行身份仅由ToolNode注入。"""


@tool(category="health", display_name="单成员餐单当前上下文", args_schema=HealthReadInput)
async def get_safe_plan_context(runtime: ToolRuntime) -> dict:
    """读取服务器绑定餐单及已同意的当前专业档案和批准规则。"""
    from yuxi.services.health_safe_planner_service import read_safe_context_for_run

    return await read_safe_context_for_run(runtime.context)


@tool(category="health", display_name="单成员安全换菜候选", args_schema=SafeSwapToolInput)
async def preview_safe_plan_swap(meal_type, dish_index, runtime: ToolRuntime) -> dict:
    """预览原菜位的受限合格候选，只保存本Run预览回执。"""
    from yuxi.services.health_safe_planner_service import preview_safe_for_run

    return await preview_safe_for_run(runtime.context, "swap", {"meal_type": meal_type, "dish_index": dish_index})


@tool(category="health", display_name="单成员整份安全重生成预览", args_schema=HealthReadInput)
async def preview_safe_plan_regeneration(runtime: ToolRuntime) -> dict:
    """按批准目录只读重算三餐，返回当前依赖和真实搜索结果。"""
    from yuxi.services.health_safe_planner_service import preview_safe_for_run

    return await preview_safe_for_run(runtime.context, "regeneration", {})

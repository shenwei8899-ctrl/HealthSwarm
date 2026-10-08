"""质量检查固定工具，无身份、批准或规则写入参数。"""

from langgraph.prebuilt.tool_node import ToolRuntime

from yuxi.agents.toolkits.health import HealthReadInput
from yuxi.agents.toolkits.registry import tool


@tool(category="health", display_name="选定方案质量上下文", args_schema=HealthReadInput)
async def get_quality_review_context(runtime: ToolRuntime) -> dict:
    """读取业务入口选定对象的当前档案、规则和营养来源。"""
    from yuxi.services.health_quality_service import selected_quality_context

    return await selected_quality_context(runtime.context)


@tool(category="health", display_name="选定方案工程检查", args_schema=HealthReadInput)
async def check_selected_plan_quality(runtime: ToolRuntime) -> dict:
    """服务器按批准条款检查选定方案，返回本Run工程回执。"""
    from yuxi.services.health_quality_service import check_selected_quality

    return await check_selected_quality(runtime.context)

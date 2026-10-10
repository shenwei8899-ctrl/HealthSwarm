"""采购工具不接收成员、采用版本和库存等身份覆盖。"""

from langgraph.prebuilt.tool_node import ToolRuntime

from yuxi.agents.toolkits.health import HealthReadInput
from yuxi.agents.toolkits.registry import tool


@tool(category="health", display_name="采用餐单净食材需求", args_schema=HealthReadInput)
async def get_purchase_requirements(runtime: ToolRuntime) -> dict:
    """读取服务器固定采用及用户库存的最小需求投影。"""
    from yuxi.services.health_purchase_service import read_purchase_for_run

    return await read_purchase_for_run(runtime.context)


@tool(category="health", display_name="采购净需求回执", args_schema=HealthReadInput)
async def preview_purchase_requirements(runtime: ToolRuntime) -> dict:
    """生成当前Run权威回执，不修改餐单、库存或交易。"""
    from yuxi.services.health_purchase_service import preview_purchase_for_run

    return await preview_purchase_for_run(runtime.context)

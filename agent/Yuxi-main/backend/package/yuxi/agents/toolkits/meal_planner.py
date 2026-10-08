"""配餐师固定工具，只检索发布菜谱并计算未审核预览。"""

from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import Field

from yuxi.agents.toolkits.registry import tool
from yuxi.agents.toolkits.health import HealthReadInput
from yuxi.services.health_meal_plan_types import MealPlanSpec
from yuxi.services.health_family_planner_types import FamilySwapToolInput, FamilyParticipationToolInput


class RecipeSearch(HealthReadInput):
    """关键词不接受账号、成员或模型参数。"""

    query: str = Field(default="", max_length=80)


class MealPlanToolInput(MealPlanSpec, HealthReadInput):
    """ToolNode注入身份；HTTP和模型JSON均不能提供运行对象。"""


@tool(category="health", display_name="初始配餐当前上下文", args_schema=HealthReadInput)
async def get_initial_plan_context(runtime: ToolRuntime) -> dict:
    """读取服务器固定的全员选择及已同意营养投影和批准目录。"""
    from yuxi.services.health_initial_planner_service import read_initial_context_for_run

    return await read_initial_context_for_run(runtime.context)


@tool(category="health", display_name="批准目录初始三餐预览", args_schema=HealthReadInput)
async def preview_initial_meal_plan(runtime: ToolRuntime) -> dict:
    """固定选择生成三餐，仅保存本Run只读回执，不保存或采用。"""
    from yuxi.services.health_initial_planner_service import preview_initial_for_run

    return await preview_initial_for_run(runtime.context)


@tool(category="health", display_name="配餐菜谱检索", args_schema=RecipeSearch)
async def search_meal_plan_recipes(query: str = "", runtime: ToolRuntime = None) -> dict:
    """检索已发布菜谱版本，返回实际原料及来源。"""
    from yuxi.services.health_meal_plan_service import meal_plan_recipes_for_run

    return await meal_plan_recipes_for_run(runtime.context, query)


@tool(category="health", display_name="三餐计划营养预览", args_schema=MealPlanToolInput)
async def preview_meal_plan(plan_date, meals, runtime: ToolRuntime) -> dict:
    """按已发布菜谱和计划量重算三餐，返回本运行的预览回执。"""
    from yuxi.services.health_meal_plan_service import create_meal_plan_preview

    spec = MealPlanSpec.model_validate({"plan_date": plan_date, "meals": meals})
    return await create_meal_plan_preview(None, None, spec, context=runtime.context)


@tool(category="health", display_name="家庭餐单当前上下文", args_schema=HealthReadInput)
async def get_family_plan_context(runtime: ToolRuntime) -> dict:
    """读取服务器选定家庭的当前档案、规则和逐人覆盖检查。"""
    from yuxi.services.health_family_planner_service import read_family_context_for_run

    return await read_family_context_for_run(runtime.context)


@tool(category="health", display_name="家庭共同换菜候选", args_schema=FamilySwapToolInput)
async def preview_family_plan_swap(meal_type, dish_index, runtime: ToolRuntime) -> dict:
    """只预览当前共同菜位的逐人合格候选，不保存新版本。"""
    from yuxi.services.health_family_planner_service import preview_family_for_run

    return await preview_family_for_run(runtime.context, "swap", {"meal_type": meal_type, "dish_index": dish_index})


@tool(category="health", display_name="家庭整份安全重算预览", args_schema=HealthReadInput)
async def preview_family_plan_regeneration(runtime: ToolRuntime) -> dict:
    """只读重算共同三餐，未就绪或预算耗尽如实返回。"""
    from yuxi.services.health_family_planner_service import preview_family_for_run

    return await preview_family_for_run(runtime.context, "regeneration", {})


@tool(category="health", display_name="家庭参与者与份量调整预览", args_schema=FamilyParticipationToolInput)
async def preview_family_plan_participation(allocations, runtime: ToolRuntime) -> dict:
    """只预览用户明确选定范围内的三餐分配，不保存或采用。"""
    from yuxi.services.health_family_planner_service import preview_family_for_run

    return await preview_family_for_run(runtime.context, "participation", {"allocations": allocations})

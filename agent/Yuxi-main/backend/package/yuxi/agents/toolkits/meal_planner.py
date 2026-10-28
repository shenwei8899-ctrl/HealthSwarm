"""配餐师固定工具，只检索发布菜谱并计算未审核预览。"""

from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import Field

from yuxi.agents.toolkits.registry import tool
from yuxi.agents.toolkits.health import HealthKnowledgeInput, HealthReadInput
from yuxi.services.health_meal_plan_types import MealPlanSpec
from yuxi.services.health_family_planner_types import FamilySwapToolInput, FamilyParticipationToolInput
from yuxi.services.reference_meal_plan_types import ReferencePlanDraft


class RecipeSearch(HealthReadInput):
    """关键词不接受账号、成员或模型参数。"""

    query: str = Field(default="", max_length=80)


class ReferenceRecipeSearch(HealthReadInput):
    """参考食谱要求 trim 后非空关键词，与受控检索服务保持相同边界。"""

    query: str = Field(min_length=1, max_length=80, description="简短菜名或食材关键词，不传身份或病历正文")


class MealPlanToolInput(MealPlanSpec, HealthReadInput):
    """ToolNode注入身份；HTTP和模型JSON均不能提供运行对象。"""


class ReferenceRecipeInput(HealthReadInput):
    """文件必须来自当前固定资料库。"""

    file_id: str = Field(min_length=1, max_length=64)
    chunk_id: str = Field(min_length=1, max_length=128)


class ReferencePlanToolInput(ReferencePlanDraft, HealthReadInput):
    """模型仅提供参考稿，运行身份由 ToolNode 注入并验证。"""


@tool(category="health", display_name="日常参考餐单上下文", args_schema=HealthReadInput)
async def get_reference_plan_context(runtime: ToolRuntime) -> dict:
    """读取当前已选成员与可售商品，不读取专业规则。"""
    from yuxi.services.reference_meal_plan_service import get_reference_context

    return await get_reference_context(runtime.context)


@tool(category="health", display_name="检索参考菜谱", args_schema=ReferenceRecipeSearch)
async def search_reference_recipes(query: str, runtime: ToolRuntime) -> dict:
    """按主题检索真实食谱文件。"""
    from yuxi.services.reference_meal_plan_service import search_reference_recipes as search

    return await search(runtime.context, query)


@tool(category="health", display_name="读取参考菜谱原文", args_schema=ReferenceRecipeInput)
async def read_reference_recipe(file_id: str, chunk_id: str, runtime: ToolRuntime) -> dict:
    """打开本 Run 检索命中的当前文件。"""
    from yuxi.services.reference_meal_plan_service import read_reference_recipe as read

    return await read(runtime.context, file_id, chunk_id)


@tool(category="health", display_name="保存日常参考餐单", args_schema=ReferencePlanToolInput)
async def save_reference_meal_plan(
    meals: list, purchase_items: list, purchase_gaps: list, runtime: ToolRuntime
) -> dict:
    """保存原文可核对的三餐，未知营养保持缺失。"""
    from yuxi.services.reference_meal_plan_service import save_reference_plan

    return await save_reference_plan(
        runtime.context, {"meals": meals, "purchase_items": purchase_items, "purchase_gaps": purchase_gaps}
    )


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


@tool(category="health", display_name="配餐营养依据检索", args_schema=HealthKnowledgeInput)
async def query_initial_nutrition_knowledge(query: str, runtime: ToolRuntime) -> dict:
    """从固定知识库检索搭配依据，数值与配方仍使用正式发布版本。"""
    from yuxi.services.health_initial_planner_service import search_initial_nutrition_knowledge

    return await search_initial_nutrition_knowledge(runtime.context, query)


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

"""配餐师固定工具，只检索发布菜谱并计算未审核预览。"""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import Field, ValidationError

from yuxi.agents.toolkits.registry import tool
from yuxi.agents.toolkits.health import HealthKnowledgeInput, HealthReadInput
from yuxi.services.health_meal_plan_types import MealPlanSpec
from yuxi.services.health_family_planner_types import FamilySwapToolInput, FamilyParticipationToolInput
from yuxi.services.reference_meal_plan_types import REFERENCE_TOOLS, ReferencePlanDraft
from yuxi.services.health_vision_types import HealthVisionError


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
) -> dict | ToolMessage:
    """保存原文可核对的三餐，未知营养保持缺失。"""
    from yuxi.services.reference_meal_plan_service import save_reference_plan

    try:
        return await save_reference_plan(
            runtime.context, {"meals": meals, "purchase_items": purchase_items, "purchase_gaps": purchase_gaps}
        )
    except HealthVisionError as error:
        tools = tuple(
            name for name in getattr(runtime.context, "tools", ()) if name != "query_family_nutrition_knowledge"
        )
        if error.code != "reference_quote_invalid" or tools != REFERENCE_TOOLS:
            raise
        messages = runtime.state.get("messages", [])
        human_index = next((i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)), None)
        if (
            human_index is None
            or messages[human_index].additional_kwargs.get("health_request_id") != runtime.context.request_id
        ):
            raise
        latest = messages[-1]
        if (
            not isinstance(latest, AIMessage)
            or sum(
                call["id"] == runtime.tool_call_id and call["name"] == "save_reference_meal_plan"
                for call in latest.tool_calls
            )
            != 1
        ):
            raise
        if reference_save_failure_index(messages, runtime.context.request_id) is not None:
            raise
        return ToolMessage(
            name="save_reference_meal_plan",
            tool_call_id=runtime.tool_call_id,
            status="error",
            content=json.dumps(
                {"error_code": error.code, "request_id": runtime.context.request_id, "message": error.message},
                ensure_ascii=False,
            ),
        )


def reference_quote_failure_index(messages, request_id):
    """定位本请求真实保存调用的首次引文失败，不采纳旧轮次或模型正文。"""
    return _reference_save_failure_index(messages, request_id, include_validation=False)


def reference_save_failure_index(messages, request_id):
    """定位本请求可纠正的真实保存失败，引文与参数校验共享一次预算。"""
    return _reference_save_failure_index(messages, request_id, include_validation=True)


def _reference_save_failure_index(messages, request_id, *, include_validation):
    """仅接受当前请求唯一声明的工具调用及静态可修复错误回执。"""
    human_index = next((i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)), None)
    if human_index is None or messages[human_index].additional_kwargs.get("health_request_id") != request_id:
        return None
    declared = {}
    for index in range(human_index + 1, len(messages)):
        message = messages[index]
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                if not call["id"]:
                    if call["name"] == "save_reference_meal_plan":
                        raise HealthVisionError(
                            "reference_save_correction_invalid", "保存调用标识缺失，无法核对回执，本轮已停止", 422
                        )
                    continue
                if call["id"] in declared:
                    previous = declared[call["id"]]
                    if call["name"] == "save_reference_meal_plan" or (
                        previous is not None and previous[0] == "save_reference_meal_plan"
                    ):
                        raise HealthVisionError(
                            "reference_save_correction_invalid", "保存调用标识重复，无法核对回执，本轮已停止", 422
                        )
                    declared[call["id"]] = None
                else:
                    declared[call["id"]] = (call["name"], index)
    for index in range(human_index + 1, len(messages)):
        message = messages[index]
        if (
            isinstance(message, ToolMessage)
            and message.status == "error"
            and message.name == "save_reference_meal_plan"
        ):
            declaration = declared.get(message.tool_call_id)
            if declaration is None or declaration[0] != message.name or declaration[1] >= index:
                continue
            try:
                payload = json.loads(message.content)
            except (ValueError, TypeError):
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("error_code") == "reference_quote_invalid" and payload.get("request_id") == request_id:
                return index
            if (
                include_validation
                and payload.get("error_code")
                in {"reference_duplicate_meals", "reference_duplicate_sku", "reference_purchase_coverage_invalid"}
                and payload.get("retryable") is True
                and payload.get("request_id", request_id) == request_id
            ):
                return index
    return None


def _reference_save_validation_error(error: ValidationError) -> str:
    """只公开固定校验说明，不把稿件、运行对象或异常正文送回模型。"""
    details = (
        error.errors(include_input=False, include_url=False, include_context=False)
        if isinstance(error, ValidationError)
        else []
    )
    payload = {
        "error_code": "reference_plan_validation_failed",
        "message": "保存参数未通过校验，本次未保存；请停止本轮保存并如实说明失败。",
        "retryable": False,
    }
    if any(item["loc"] and item["loc"][0] == "runtime" for item in details):
        payload = {
            "error_code": "reference_runtime_invalid",
            "message": "保存工具的服务端运行上下文校验失败，本次未保存；请停止本轮保存，不能补造运行对象。",
            "retryable": False,
        }
    elif len(details) == 1 and details[0]["loc"] == () and details[0]["type"] == "value_error":
        known_errors = {
            "Value error, 参考餐次不能重复": (
                "reference_duplicate_meals",
                "餐次不能重复；仅提交所选餐次，每个餐次一次。",
            ),
            "Value error, 相同规格须合并数量": (
                "reference_duplicate_sku",
                "相同SKU须合并为一项并合计包装数量；每条食材原文仍只对应一个采购决定。",
            ),
            "Value error, 每种食材原文必须且只能对应一个采购商品或一条未选原因": (
                "reference_purchase_coverage_invalid",
                "每条食材原文必须且只能对应一个采购商品或一条未选原因；检查重复、遗漏和多余对应，"
                "逐字使用已读取原文，不移除食材或放宽限制。",
            ),
        }
        if match := known_errors.get(details[0]["msg"]):
            payload = {"error_code": match[0], "message": match[1], "retryable": True}
    return json.dumps(payload, ensure_ascii=False)


save_reference_meal_plan.handle_validation_error = _reference_save_validation_error


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

"""健康数据工具只接受服务端运行上下文，不接受对象选择参数。"""

from typing import Annotated, Any
from typing import Literal

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import Field, field_validator

from yuxi.agents.toolkits.registry import tool
from yuxi.services.health_vision_types import HealthDTO
from yuxi.services.health_memory_types import MemoryKind


class HealthReadInput(HealthDTO):
    """读取当前已绑定成员，拒绝额外身份或查询参数。"""

    runtime: Annotated[Any, InjectedToolArg]

    @field_validator("runtime")
    @classmethod
    def injected_runtime(cls, value):
        """只接受 ToolNode 注入的运行对象，JSON 不能伪造它。"""
        if not isinstance(value, ToolRuntime):
            raise ValueError("健康工具需要服务端运行上下文")
        return value


@tool(category="health", display_name="已确认健康指标", args_schema=HealthReadInput)
async def get_confirmed_profile(runtime: ToolRuntime) -> dict:
    """读取本会话绑定成员的已确认健康指标；完整病史和过敏档案尚不可用。"""
    from yuxi.services.health_consultation_service import confirmed_consultation_records

    return await confirmed_consultation_records(runtime.context, "report")


@tool(category="health", display_name="已确认饮食日记", args_schema=HealthReadInput)
async def get_confirmed_diet(runtime: ToolRuntime) -> dict:
    """读取本会话绑定成员的已确认饮食与营养快照；缺失数据保持未知。"""
    from yuxi.services.health_consultation_service import confirmed_consultation_records

    return await confirmed_consultation_records(runtime.context, "meal")


@tool(category="health", display_name="本人确认家庭档案", args_schema=HealthReadInput)
async def get_complete_health_profile(runtime: ToolRuntime) -> dict:
    """读取固定成员已关联的本人确认档案；自由文本不替代批准安全规则。"""
    from yuxi.services.health_family_profile_service import family_profile_for_run

    return await family_profile_for_run(runtime.context)


@tool(category="health", display_name="本人体重实测记录", args_schema=HealthReadInput)
async def get_member_weight_records(runtime: ToolRuntime) -> dict:
    """读取固定本人近30日实测体重，保留独立来源与版本；缺失保持未知。"""
    from yuxi.services.health_weight_service import weight_records_for_run

    return await weight_records_for_run(runtime.context)


@tool(category="health", display_name="本人血压实测记录", args_schema=HealthReadInput)
async def get_member_blood_pressure_records(runtime: ToolRuntime) -> dict:
    """读取固定本人近30日原始血压及独立版本；缺失保持未知，不作医学判断。"""
    from yuxi.services.health_blood_pressure_service import blood_pressure_records_for_run

    return await blood_pressure_records_for_run(runtime.context)


class HealthKnowledgeInput(HealthReadInput):
    """模型只选择短关键词，知识范围与成员由后端决定。"""

    query: str = Field(min_length=1, max_length=120, description="营养科普短关键词，不传入成员身份或病历正文")


@tool(category="health", display_name="审核营养科普检索", args_schema=HealthKnowledgeInput)
async def query_reviewed_nutrition_knowledge(query: str, runtime: ToolRuntime) -> dict:
    """检索已发布且有效的通用科普片段，返回本次运行引用；不适用于个人方案。"""
    from yuxi.services.health_evidence_service import search_nutrition_evidence

    return await search_nutrition_evidence(runtime.context, query)


@tool(category="health", display_name="成员有效记忆", args_schema=HealthReadInput)
async def get_member_memories(runtime: ToolRuntime) -> dict:
    """读取当前绑定成员的账号私有自述，不能当作确诊或正式档案。"""
    from yuxi.services.health_memory_service import member_memory_for_run

    return await member_memory_for_run(runtime.context)


class HealthMemoryInput(HealthReadInput):
    """只选择当前原文及语义槽位，成员和来源消息由服务器固定。"""

    fact_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$", description="稳定语义键；修改已有事实时复用读取到的键")
    kind: MemoryKind
    subject: str = Field(min_length=1, max_length=80, description="原文中明确的当前成员称呼；本人会话可填我")
    quote: str = Field(
        min_length=1, max_length=500, description="当前用户消息中的完整连续原文，包含主体；不能改写或推断"
    )
    persistence: Literal["ongoing"]


@tool(category="health", display_name="保存成员长期自述", args_schema=HealthMemoryInput)
async def remember_member_fact(
    fact_key: str, kind: MemoryKind, subject: str, quote: str, persistence: Literal["ongoing"], runtime: ToolRuntime
) -> dict:
    """明确主体和长期自述可自动保存；临时体验、歧义和推断先澄清。"""
    from yuxi.services.health_memory_service import member_memory_for_run

    return await member_memory_for_run(
        runtime.context, {"fact_key": fact_key, "kind": kind, "subject": subject, "quote": quote}
    )


@tool(category="health", display_name="有效餐后反馈", args_schema=HealthReadInput)
async def get_meal_feedback(runtime: ToolRuntime) -> dict:
    """读取当前绑定成员、账号私有的单餐自述，保持原营养快照。"""
    from yuxi.services.health_meal_feedback_service import meal_feedback_for_run

    return await meal_feedback_for_run(runtime.context)

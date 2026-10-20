"""固定本人血糖范围的受控咨询后端。"""

from yuxi.agents.buildin.health_consultation.graph import HealthConsultationAgent
from yuxi.agents.toolkits.health import (
    get_member_blood_glucose_records,
    query_reviewed_nutrition_knowledge,
    query_family_nutrition_knowledge,
)


class HealthBloodGlucoseAgent(HealthConsultationAgent):
    """只回顾血糖原始记录、追问缺口及解释专题通用科普。"""

    name = "血糖记录助手"
    description = "读取本人血糖记录和专题通用科普，区分测量条件与资料缺口，不诊断、调药或生成控糖计划。"
    prompt_name = "BLOOD_GLUCOSE_PROMPT"
    consultation_tools = (
        get_member_blood_glucose_records,
        query_reviewed_nutrition_knowledge,
        query_family_nutrition_knowledge,
    )

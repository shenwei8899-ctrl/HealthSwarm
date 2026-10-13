"""固定本人血压范围的受控咨询后端。"""

from yuxi.agents.buildin.health_consultation.graph import HealthConsultationAgent
from yuxi.agents.toolkits.health import get_member_blood_pressure_records, query_reviewed_nutrition_knowledge


class HealthBloodPressureAgent(HealthConsultationAgent):
    """只回顾成对血压记录、追问缺口及解释审核科普。"""

    name = "血压记录助手"
    description = "读取本人血压成对记录和审核科普，明确测量信息缺口，不诊断、调药或生成降压计划。"
    prompt_name = "BLOOD_PRESSURE_PROMPT"
    consultation_tools = (get_member_blood_pressure_records, query_reviewed_nutrition_knowledge)

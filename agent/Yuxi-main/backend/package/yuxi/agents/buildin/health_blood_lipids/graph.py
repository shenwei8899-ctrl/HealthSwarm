"""固定本人血脂范围的受控咨询后端。"""

from yuxi.agents.buildin.health_consultation.graph import HealthConsultationAgent
from yuxi.agents.toolkits.health import get_member_blood_lipids_records, query_reviewed_nutrition_knowledge


class HealthBloodLipidsAgent(HealthConsultationAgent):
    """只回顾同条血脂四项、追问缺口及解释审核科普。"""

    name = "血脂记录助手"
    description = "读取本人血脂四项和审核科普，保持同条来源与缺失状态，不分级风险、诊断或调药。"
    prompt_name = "BLOOD_LIPIDS_PROMPT"
    consultation_tools = (get_member_blood_lipids_records, query_reviewed_nutrition_knowledge)

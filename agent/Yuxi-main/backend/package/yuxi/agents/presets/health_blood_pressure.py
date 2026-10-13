"""服务器固定成员的血压咨询预设。"""

from yuxi.agents.presets import AgentPreset

PRESET = AgentPreset(
    slug="health-blood-pressure",
    name="血压记录助手",
    description="从健康业务入口选择本人后进入；回顾成对血压记录、追问资料缺口并解释审核科普。",
    backend_id="HealthBloodPressureAgent",
    context={
        "tools": [],
        "knowledges": [],
        "mcps": [],
        "skills": ["family-blood-pressure"],
        "preload_skills": ["family-blood-pressure"],
    },
)

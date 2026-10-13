"""服务器固定成员的血糖咨询预设。"""

from yuxi.agents.presets import AgentPreset

PRESET = AgentPreset(
    slug="health-blood-glucose",
    name="血糖记录助手",
    description="从健康业务入口选择本人后进入；回顾血糖记录、追问资料缺口并解释审核科普。",
    backend_id="HealthBloodGlucoseAgent",
    context={
        "tools": [],
        "knowledges": [],
        "mcps": [],
        "skills": ["family-blood-glucose"],
        "preload_skills": ["family-blood-glucose"],
    },
)

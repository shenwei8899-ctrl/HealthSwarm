"""服务器固定成员的血脂咨询预设。"""

from yuxi.agents.presets import AgentPreset

PRESET = AgentPreset(
    slug="health-blood-lipids",
    name="血脂记录助手",
    description="从健康业务入口选择本人后进入；回顾血脂四项、追问资料缺口并解释审核科普。",
    backend_id="HealthBloodLipidsAgent",
    context={
        "tools": [],
        "knowledges": [],
        "mcps": [],
        "skills": ["family-blood-lipids"],
        "preload_skills": ["family-blood-lipids"],
    },
)

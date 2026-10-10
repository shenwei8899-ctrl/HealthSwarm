"""饮食分析师通过健康业务入口绑定成员。"""

from yuxi.agents.presets import AgentPreset

PRESET = AgentPreset(
    slug="health-diet-analyst",
    name="饮食分析师",
    description="解释确认单餐或1/7/30日记录事实与缺失，可只读用户明确绑定的当前批准目标；不判历史达标或趋势。",
    backend_id="HealthDietAnalystAgent",
    context={
        "tools": [],
        "knowledges": [],
        "mcps": [],
        "skills": ["family-diet-analyst"],
        "preload_skills": ["family-diet-analyst"],
    },
)

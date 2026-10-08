"""饮食分析师通过健康业务入口绑定成员。"""

from yuxi.agents.presets import AgentPreset

PRESET = AgentPreset(
    slug="health-diet-analyst",
    name="饮食分析师",
    description="解释有效已确认单餐营养与缺失，个人目标与周期分析尚未接入。",
    backend_id="HealthDietAnalystAgent",
    context={
        "tools": [],
        "knowledges": [],
        "mcps": [],
        "skills": ["family-diet-analyst"],
        "preload_skills": ["family-diet-analyst"],
    },
)

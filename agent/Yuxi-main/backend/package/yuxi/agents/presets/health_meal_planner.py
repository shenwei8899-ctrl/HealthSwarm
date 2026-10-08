"""配餐师只从健康业务绑定入口进入。"""

from yuxi.agents.presets import AgentPreset

PRESET = AgentPreset(
    slug="health-meal-planner",
    name="基础配餐师",
    description="单成员三餐草稿；选定家庭餐单及全体来源后，提供换菜、重算和参与调整只读预览。",
    backend_id="HealthMealPlannerAgent",
    context={
        "tools": [],
        "knowledges": [],
        "mcps": [],
        "skills": ["family-meal-planner"],
        "preload_skills": ["family-meal-planner"],
    },
)

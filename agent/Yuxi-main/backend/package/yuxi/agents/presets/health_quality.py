"""质量检查须通过显式业务选定入口绑定对象。"""

from yuxi.agents.presets import AgentPreset

PRESET = AgentPreset(
    slug="health-quality",
    name="质量检查师",
    description="按当前档案及批准规则执行工程检查，专业批准由授权人员办理。",
    backend_id="HealthQualityAgent",
    context={
        "tools": [],
        "knowledges": [],
        "mcps": [],
        "skills": ["family-quality-review"],
        "preload_skills": ["family-quality-review"],
    },
)

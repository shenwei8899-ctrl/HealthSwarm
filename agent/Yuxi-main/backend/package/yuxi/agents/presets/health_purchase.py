"""采购助手只从有效采用与明确库存选择入口进入。"""

from yuxi.agents.presets import AgentPreset

PRESET = AgentPreset(
    slug="health-purchase",
    name="采购助手",
    description="有效采用食材可食净需求；独立用途同意后解释缺口和当前Run回执。",
    backend_id="HealthPurchaseAgent",
    context={
        "tools": [],
        "knowledges": [],
        "mcps": [],
        "skills": ["family-purchase"],
        "preload_skills": ["family-purchase"],
    },
)

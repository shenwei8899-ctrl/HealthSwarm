"""专属咨询角色，成员必须由健康业务接口绑定。"""

from yuxi.agents.presets import AgentPreset

PRESET = AgentPreset(
    slug="health-consultation",
    name="成员专属营养咨询",
    description="从健康识图选择成员后进入；读取确认记录和审核通用科普并校验引用，不提供治疗或个人配餐方案。",
    backend_id="HealthConsultationAgent",
    context={
        "tools": [],
        "knowledges": [],
        "mcps": [],
        "skills": ["family-nutritionist"],
        "preload_skills": ["family-nutritionist"],
    },
)

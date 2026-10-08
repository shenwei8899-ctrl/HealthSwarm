"""健康业务角色的实现范围，由接口展示并由咨询运行消费。"""

from yuxi.services.skills.shared import list_builtin_skill_specs

CONSULTATION_SKILLS = ("family-nutritionist",)
PLANNER_SKILLS = ("family-meal-planner",)
ANALYST_SKILLS = ("family-diet-analyst",)
QUALITY_SKILLS = ("family-quality-review",)


def consultation_skill_snapshot(skills=CONSULTATION_SKILLS):
    """只读取固定内置技能的发布源码及版本，不解析个人覆盖或扩展依赖。"""
    specs = {spec["slug"]: spec for spec in list_builtin_skill_specs()}
    return {
        "effective_skills": list(skills),
        "preloaded_skills": list(skills),
        "skill_metadata": {
            slug: {
                "source_scope": "builtin",
                "version": specs[slug]["version"],
                "content_hash": specs[slug]["content_hash"],
            }
            for slug in skills
        },
        "preloaded_skill_contents": {
            slug: (specs[slug]["source_dir"] / "SKILL.md").read_text(encoding="utf-8") for slug in skills
        },
    }


def consultation_skill_prompt(snapshot=None):
    """模型输入与审计使用同一预加载内容。"""
    snapshot = consultation_skill_snapshot() if snapshot is None else snapshot
    return "\n\n".join(snapshot["preloaded_skill_contents"][slug] for slug in CONSULTATION_SKILLS)


def health_agent_roles():
    """公开角色边界；未实现的角色不发布为可运行预设。"""
    return {
        "roles": [
            {
                "role": "health-profile",
                "name": "健康档案",
                "status": "partial",
                "owner": "健康档案服务",
                "implemented_scope": (
                    "独立家庭档案模块、本人显式成员关联、确认档案读取及Run/历史来源校验；"
                    "本人关联页面、确认版本/缺口展示及来源变更后显式新建咨询；本人独立实测体重/血压读取与版本失效"
                ),
                "missing": ["管理员代成员模型处理同意及字段授权联调", "营养安全编码与血糖/血脂等其他独立测量映射"],
            },
            {
                "role": "health-nutritionist",
                "name": "家庭营养师",
                "status": "partial",
                "entry_agent": "health-consultation",
                "skills": list(CONSULTATION_SKILLS),
                "implemented_scope": (
                    "成员咨询、本人确认家庭档案及独立体重/血压与确认记录读取、审核科普引用、成员自述记忆与每日消息摘要"
                ),
                "missing": ["完整营养安全档案联调", "审核知识数据", "次日餐次提议"],
            },
            {
                "role": "health-meal-planner",
                "name": "配餐师",
                "status": "partial",
                "entry_agent": "health-meal-planner",
                "skills": list(PLANNER_SKILLS),
                "implemented_scope": (
                    "单成员三餐草稿、发布菜谱营养计算、显式保存、换菜重算及版本历史；"
                    "次日预览提议登记、当前专业批准的正式采用、明确替代/取消及来源失效；"
                    "批准类型与营养差异的三候选、单菜安全换菜及新版本检查收据；"
                    "批准目录的整份三餐共同修复预览与用户确认重生成后端；"
                    "当前批准个人目标、家庭逐餐参与和逐人份量/质量检查；"
                    "家庭逐人安全候选、共同换菜及整份重生成后端；"
                    "家庭共同正式采用、多旧餐单明确替代、整体取消/失效及逐成员今日读取；"
                    "家庭逐餐参与者/份量调整预览、确认新版本及移出成员历史授权后端；"
                    "固定家庭线程、全体模型用途同意及四工具只读预览，当前Run收据和发布复核；"
                    "批准目录的初始个人/家庭三餐后端，逐人有限份量搜索、当前来源回执及确认初版/检查原子保存；"
                    "固定初始个人/家庭线程、全员模型用途同意及两工具预览，当前Run回执与发布复核"
                ),
                "missing": [
                    "完整档案联调",
                    "21天安全重算",
                    "单成员安全换菜Agent工具、家庭页面及未付采购和做法联动",
                    "日终及Agent次日提议联动",
                    "次日提议/采用页面及小程序",
                ],
            },
            {
                "role": "health-diet-analyst",
                "name": "饮食分析师",
                "status": "partial",
                "entry_agent": "health-diet-analyst",
                "skills": list(ANALYST_SKILLS),
                "implemented_scope": (
                    "有效确认单餐与1/7/30天饮食及反馈事实分析、逐日覆盖与来源版本、营养缺失和已知和分离；"
                    "用户选餐后的本轮原文反馈写入、幂等修订及消息/Run来源"
                ),
                "missing": [
                    "批准的趋势评判规则",
                    "持久派生刷新",
                    "个人目标与专业规则",
                    "分析及选餐反馈页面",
                    "真实模型质量验收",
                ],
            },
            {
                "role": "health-glucose",
                "name": "控糖管理",
                "status": "not_implemented",
                "missing": ["21天计划", "打卡反馈", "审核控糖规则"],
            },
            {
                "role": "health-purchase",
                "name": "采购助手",
                "status": "not_implemented",
                "missing": ["餐单汇总", "库存扣减", "采购清单", "商城映射"],
            },
            {
                "role": "health-quality",
                "name": "质量审核",
                "status": "partial",
                "entry_agent": "health-quality",
                "skills": list(QUALITY_SKILLS),
                "implemented_scope": (
                    "单成员保存三餐的版本化档案与批准规则投影、营养复算及确定性限制检查；"
                    "固定两工具质量Agent实际Run及提交、退回、批准和失效的专业状态流与独立资格/成员授权；"
                    "当前批准的单成员正式采用门禁与失效传播；单菜及整份安全改版的新检查及旧批准/采用失效；"
                    "家庭逐人目标/配料/覆盖范围的质量与专业状态、安全共同改版及末次检查原子提交；"
                    "家庭正式采用的全部来源门禁、共同失效与逐成员读取；"
                    "参与调整的新成员质量检查及当前/历史成员统一授权"
                ),
                "missing": [
                    "21天/采购消费者接入",
                    "审核页面",
                    "专业生产规则及真实模型验收",
                ],
            },
        ],
        "full_health_profile_available": False,
        "personal_meal_plan_available": False,
    }

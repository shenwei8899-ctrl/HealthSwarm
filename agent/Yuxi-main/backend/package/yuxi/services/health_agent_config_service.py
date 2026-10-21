"""健康 Agent 编辑页的只读业务知识来源投影。"""

from yuxi.permissions.resource_permission import ResourcePermission, resolve_knowledge_base_permission
from yuxi.repositories.health_consultation_repository import HEALTH_AGENT_BACKENDS
from yuxi.repositories.knowledge_base_repository import KnowledgeBaseRepository
from yuxi.services.health_family_kb_service import KNOWLEDGE_HEALTH_AGENTS, configured_health_kb_ids
from yuxi.services.health_vision_types import HealthVisionError


async def get_managed_knowledge(session, agent, user) -> dict | None:
    """复用运行时绑定；仅返回有权查看的库名，不改动 Agent 配置。"""
    if agent.slug not in HEALTH_AGENT_BACKENDS or agent.backend_id != HEALTH_AGENT_BACKENDS[agent.slug]:
        return None

    if agent.slug not in KNOWLEDGE_HEALTH_AGENTS:
        descriptions = {
            "health-diet-analyst": "使用已确认饮食记录、营养计算结果及明确绑定的业务数据；未绑定文档知识库。",
            "health-quality": "使用档案、已批准规则及业务校验结果；未绑定文档知识库。",
            "health-purchase": "使用有效餐单和采购需求等业务数据；未绑定文档知识库。",
        }
        return {"status": "business_data", "description": descriptions[agent.slug], "items": []}

    try:
        ids = configured_health_kb_ids(agent.slug)
    except HealthVisionError as exc:
        if exc.code != "knowledge_unavailable":
            raise
        return {
            "status": "unconfigured",
            "description": "后台尚未正确配置知识库绑定，请联系管理员。",
            "items": [],
        }

    rows = await KnowledgeBaseRepository().get_by_ids(session, ids)
    by_id = {row.kb_id: row for row in rows}
    items = []
    for kb_id in ids:
        kb = by_id.get(kb_id)
        if kb is None:
            items.append({"status": "unavailable", "name": "绑定的知识库不存在或已移除"})
        elif resolve_knowledge_base_permission(user, kb) == ResourcePermission.NONE:
            items.append({"status": "restricted", "name": "已绑定知识库（当前账号无权查看详情）"})
        else:
            items.append(
                {"id": kb_id, "name": kb.name, "status": "configured" if kb.kb_type == "milvus" else "unsupported"}
            )

    return {
        "status": "configured"
        if all(item["status"] in {"configured", "restricted"} for item in items)
        else "unavailable",
        "description": (
            "菜谱文档仅作烹饪与食材搭配参考；餐单仍使用已发布结构化菜谱及程序计算校验。实际运行需成员授权及配餐处理政策。"
            if agent.slug == "health-meal-planner"
            else "用于一般科普检索；实际咨询仍需成员授权及已批准的处理政策。绑定不代表资料已完成专业审核。"
        ),
        "items": items,
    }

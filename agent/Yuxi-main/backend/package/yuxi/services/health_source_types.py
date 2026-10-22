"""专业业务版本引用知识库原件，不把资料上传视为专业批准。"""

import re

from yuxi.services.health_vision_types import HealthVisionError


def parse_knowledge_source(value: str) -> tuple[str, str, str] | None:
    """外部来源保持兼容；知识库引用必须明确文件归属和原始内容摘要。"""
    if not value.lower().startswith("knowledge:"):
        return None
    match = re.fullmatch(r"knowledge://([A-Za-z0-9_-]{1,80})/([A-Za-z0-9_-]{1,64})#([0-9a-f]{64})", value)
    if match is None:
        raise HealthVisionError("knowledge_source_invalid", "知识库来源引用格式无效，请重新选择来源", 422)
    return match.groups()


def knowledge_source_reference(kb_id: str, file_id: str, content_hash: str) -> str:
    """从已读取的原件生成规范引用，不接受缺失摘要。"""
    value = f"knowledge://{kb_id}/{file_id}#{content_hash}"
    parse_knowledge_source(value)
    return value


def nutrition_source_references(sources):
    """枚举计算快照中的食物、份量与菜谱原料出处。"""
    return [item["source"] for item in sources] + [
        ingredient["food"]["source"] for item in sources for ingredient in item.get("ingredients", [])
    ]

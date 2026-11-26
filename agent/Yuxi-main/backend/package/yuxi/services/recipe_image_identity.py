"""生成图与餐单归档共用菜谱事实身份，不依赖图片服务。"""

import hashlib
import json


def recipe_image_key(dish):
    """以菜谱来源及实际食材做法绑定图片，避免不同菜品共用错误封面。"""
    facts = {k: dish.get(k) for k in ("name", "ingredients", "steps", "source")}
    digest = hashlib.sha256(json.dumps(facts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return "recipe-illustrations/gpt-v1/" + digest + ".webp"

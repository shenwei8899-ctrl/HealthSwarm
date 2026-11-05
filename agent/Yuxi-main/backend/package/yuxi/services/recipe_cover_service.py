"""独立封面只匹配已核对的菜谱身份和内容版本，不改写菜谱正文。"""

import copy
import json
from functools import lru_cache
from pathlib import Path


def recipe_cover(source):
    """给当前已授权的确切原文版本返回封面，未知来源保持无图。"""
    if not source:
        return {}
    key = (source.get("kb_id"), source.get("file_id"), source.get("file_hash"))
    cover = cover_index().get(key)
    if not cover:
        return {}
    return {"image_url": cover["image_url"], "image_source": copy.deepcopy(cover["image_source"])}


@lru_cache(maxsize=1)
def cover_index():
    """发布目录随代码审阅，图片本体在对象存储，运行期不抓取外站。"""
    catalog = json.loads((Path(__file__).parent / "data/recipe_covers.json").read_text(encoding="utf-8"))
    return {(item["kb_id"], item["file_id"], item["file_hash"]): item for item in catalog["covers"]}

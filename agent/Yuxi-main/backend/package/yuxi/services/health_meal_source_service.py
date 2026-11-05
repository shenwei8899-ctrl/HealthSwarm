"""从现有资料或原始照片估计重建本餐数值，不信任客户端改写。"""

import hashlib

from yuxi.repositories.health_meal_source_repository import HealthMealSourceRepository
from yuxi.services.health_meal_source_parser import PARSER_VERSION, parse_meal_source
from yuxi.services.health_source_types import knowledge_source_reference, parse_knowledge_source
from yuxi.services.health_vision_types import HealthVisionError


async def search_meal_sources(session, uid, query):
    """返回可计算的现有资料及明确计量基准，不改变发布目录。"""
    repo = HealthMealSourceRepository(session)
    result = []
    for candidate in await repo.search(uid, query):
        try:
            file, content, parent_source = await repo.document(uid, candidate.kb_id, candidate.file_id)
        except HealthVisionError as error:
            if error.code != "meal_source_unavailable":
                raise
            continue
        facts = parse_meal_source(content)
        if facts:
            result.append(_source(file, content, facts, parent_source))
    return result


async def meal_source_inputs(session, uid, meal, *, lock=False):
    """逐项从当前原件重建数值，旧引用或解析版本不进入计算。"""
    repo, result = HealthMealSourceRepository(session), {}
    for item in sorted(meal.items, key=lambda row: str(row.photo_estimate.draft_id) if row.photo_estimate else ""):
        if item.photo_estimate:
            estimate, model, prompt = await repo.photo_estimate(uid, item, lock=lock)
            reference = f"photo://{estimate.draft_id}/{item.item_id}"
            result[reference] = {
                "source": reference,
                "type": "photo_estimate",
                "name": item.name,
                "item_id": str(item.item_id),
                "photo_estimate": estimate.model_dump(mode="json"),
                "basis": "per100g",
                "basis_label": "每100克可食部分",
                "nutrients": estimate.model_dump(mode="json")["nutrients"],
                "model_version": model,
                "prompt_version": prompt,
                "professional_approval": False,
            }
    references = [item.nutrition_source for item in meal.items if not item.excluded and item.nutrition_source]
    for selected in sorted(references, key=lambda value: value.reference):
        reference = selected.reference
        if reference in result:
            if result[reference]["nutrition_source"] != selected.model_dump():
                raise HealthVisionError("meal_source_changed", "同一资料的版本不一致，请重新匹配", 409)
            continue
        parsed = parse_knowledge_source(reference)
        if parsed is None:
            raise HealthVisionError("meal_source_invalid", "请选择当前可用的营养资料", 422)
        file, content, parent_source = await repo.document(uid, parsed[0], parsed[1], lock=lock)
        facts = parse_meal_source(content)
        if not facts:
            raise HealthVisionError("meal_source_unavailable", "原件缺少明确的营养基准，请重新匹配", 409)
        current = _source(file, content, facts, parent_source)
        if current["nutrition_source"] != selected.model_dump():
            raise HealthVisionError("meal_source_changed", "营养资料版本已变化，请重新匹配后计算", 409)
        result[reference] = current
    return result


async def validate_photo_estimates(session, uid, meal, *, lock=False):
    """草稿写入和读取也检查估计，包含未计入营养的排除项。"""
    repo = HealthMealSourceRepository(session)
    for item in sorted(meal.items, key=lambda row: str(row.photo_estimate.draft_id) if row.photo_estimate else ""):
        if item.photo_estimate:
            await repo.photo_estimate(uid, item, lock=lock)


def _source(file, content, facts, parent_source):
    """文件摘要与解析正文共同标识实际消费版本。"""
    reference = knowledge_source_reference(file.kb_id, file.file_id, file.content_hash)
    return {
        **facts,
        "parent_source": parent_source,
        "id": reference,
        "type": "knowledge",
        "source": reference,
        "nutrition_source": {
            "reference": reference,
            "version": hashlib.sha256((PARSER_VERSION + "\n" + content).encode()).hexdigest(),
        },
        "dataset_version": file.content_hash[:12],
        "cooking_state": "按原文食物状态核对",
        "filename": file.filename,
    }

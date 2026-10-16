"""只持久化营养候选和校验报告，绝不自动发布。"""

from collections import Counter
from uuid import uuid4

from pydantic import ValidationError

from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.health_nutrition_import_repository import NutritionImportRepository
from yuxi.services.health_vision_types import FoodInput, RecipeInput, HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import NutritionImportBatch


async def prepare_nutrition_import(uid, data):
    """同键同内容重放候选报告，异常行不进入正式数据集。"""
    async with pg_manager.get_async_session_context() as session:
        await HealthConsultationRepository(session).lock_request(uid, str(data.client_request_id))
        repo = NutritionImportRepository(session)
        old = await repo.receipt(uid, str(data.client_request_id))
        if old:
            if old.fingerprint != data.fingerprint():
                raise HealthVisionError("idempotency_conflict", "导入请求内容已改变，请使用新批次", 409)
            return {"id": old.id, **old.report}
        codes = {row.get("record_code") for row in data.rows if isinstance(row.get("record_code"), str)}
        published = await repo.published(data.kind, codes)
        existing = {(row.record_code, row.dataset_version) for row in published}
        keys = [(str(row.get("record_code", "")), str(row.get("dataset_version", ""))) for row in data.rows]
        counts = Counter(keys)
        items = []
        metadata = {"source", "license", "edition", "dataset_version"}
        model = FoodInput if data.kind == "food" else RecipeInput
        for index, row in enumerate(data.rows):
            issues, normalized = [], None
            try:
                parsed = model.model_validate(row)
                normalized = parsed.model_dump(mode="json")
                if data.kind == "recipe":
                    ids = {str(item.food_id) for item in parsed.ingredients}
                    if ids - await repo.food_ids(ids):
                        issues.append({"field": "ingredients", "code": "unpublished_food"})
            except ValidationError as error:
                issues.extend(
                    {
                        "field": ".".join(map(str, item["loc"])),
                        "code": "metadata_required"
                        if item["loc"][0] in metadata and item["type"] in {"missing", "string_too_short"}
                        else item["type"],
                    }
                    for item in error.errors(include_url=False, include_input=False)
                )
            if counts[keys[index]] > 1:
                issues.append({"field": "record_code", "code": "duplicate_in_batch"})
            if keys[index] in existing:
                issues.append({"field": "dataset_version", "code": "published_version_conflict"})
            status = "invalid" if any(item["code"] != "metadata_required" for item in issues) else "pending_review"
            items.append(
                {
                    "row": index + 1,
                    "status": status,
                    "issues": issues,
                    "candidate": normalized if normalized is not None else row,
                    "required_before_publish": [
                        "source_version_and_license",
                        "applicable_scope",
                        "professional_review",
                    ],
                }
            )
        report = {
            "kind": data.kind,
            "status": "prepared_only",
            "published_count": 0,
            "items": items,
            "summary": {
                "total": len(items),
                "invalid": sum(item["status"] == "invalid" for item in items),
                "pending_review": sum(item["status"] == "pending_review" for item in items),
            },
        }
        batch = NutritionImportBatch(
            id=str(uuid4()),
            actor_uid=uid,
            request_id=str(data.client_request_id),
            fingerprint=data.fingerprint(),
            report=report,
        )
        session.add(batch)
        await session.flush()
        return {"id": batch.id, **report}


async def read_nutrition_import(uid, batch_id):
    """管理端重新读取已保存的候选报告。"""
    async with pg_manager.get_async_session_context() as session:
        batch = await NutritionImportRepository(session).read(uid, batch_id)
        if batch is None:
            raise HealthVisionError("not_found", "导入批次不存在或不可读取", 404)
        return {"id": batch.id, **batch.report}

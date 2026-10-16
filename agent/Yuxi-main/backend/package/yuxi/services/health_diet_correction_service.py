"""已确认饮食同 ID 更正、计算及派生失效的原子事务。"""

from copy import deepcopy
from uuid import uuid4

from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.health_diet_correction_repository import HealthDietCorrectionRepository
from yuxi.repositories.health_diet_analysis_repository import HealthDietAnalysisRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_diet_analysis_service import analyze_confirmed_meal
from yuxi.services.health_nutrition_service import CALCULATION_VERSION, calculate_nutrition, input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError, MealPayload
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import DietLogRevision, MealFeedbackRevision, NutritionCalculation
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive


async def correct_diet_log(uid, record_id, data):
    """重放返回当前版本；失败不发布新版本或失效旧分析。"""
    request_id = str(data.client_request_id)
    fingerprint = input_fingerprint({"record_id": record_id, **data.model_dump(mode="json")})
    async with pg_manager.get_async_session_context() as session:
        await HealthConsultationRepository(session).lock_request(uid, request_id)
        repo = HealthDietCorrectionRepository(session)
        record = await repo.record(uid, record_id, lock=True)
        record, confirmation = await HealthDietAnalysisRepository(session).source(uid, record.member_id, record_id)
        version = record.version or confirmation.draft_version
        receipt = await repo.receipt(uid, request_id)
        if receipt:
            if receipt.fingerprint != fingerprint:
                raise HealthVisionError("idempotency_conflict", "同一更正请求不能改变内容", 409)
            return _result(record, confirmation, receipt.version)
        if version != data.expected_version:
            raise HealthVisionError("version_conflict", "饮食记录已变化，请刷新后更正", 409)
        draft = await HealthVisionRepository(session).draft(confirmation.draft_id, uid, "meal")
        payload = data.meal.model_dump(mode="json")
        _validate_evidence(payload, draft.original_payload)
        nutrition = calculate_nutrition(data.meal, *await repo.nutrition_inputs(data.meal))
        if not nutrition["complete"] and not data.accept_incomplete:
            raise HealthVisionError("nutrition_incomplete", "营养数据不完整；请补充或明确接受不完整日记")
        if not await repo.revisions(record_id):
            session.add(
                DietLogRevision(
                    id=str(uuid4()),
                    diet_log_id=record.id,
                    version=version,
                    calculation_id=record.calculation_id,
                    actor_uid=confirmation.actor_uid,
                    reason="原确认快照",
                    snapshot=deepcopy(record.snapshot),
                    created_at=record.created_at,
                )
            )
        calculation = NutritionCalculation(
            id=str(uuid4()),
            draft_id=draft.id,
            draft_version=confirmation.draft_version,
            input_hash=input_fingerprint(payload),
            input_snapshot=payload,
            result=nutrition,
            calculation_version=CALCULATION_VERSION,
        )
        session.add(calculation)
        await session.flush()
        record.version = version + 1
        record.calculation_id = calculation.id
        record.snapshot = {**record.snapshot, "meal": payload, "nutrition": nutrition}
        session.add(
            DietLogRevision(
                id=str(uuid4()),
                diet_log_id=record.id,
                version=record.version,
                calculation_id=calculation.id,
                actor_uid=uid,
                request_id=request_id,
                fingerprint=fingerprint,
                reason=data.reason,
                snapshot=deepcopy(record.snapshot),
            )
        )
        for feedback in await repo.active_feedback(record_id):
            feedback.version += 1
            feedback.status = "invalidated"
            feedback.updated_at = utc_now_naive()
            session.add(
                MealFeedbackRevision(
                    id=str(uuid4()),
                    feedback_id=feedback.id,
                    actor_uid=feedback.actor_uid,
                    request_id=str(uuid4()),
                    fingerprint=fingerprint,
                    version=feedback.version,
                    details=deepcopy(feedback.details),
                    status="invalidated",
                )
            )
        await session.flush()
        return _result(record, confirmation, record.version)


async def diet_log_revisions(uid, record_id):
    """历史只作为审计读取，仍逐次检查当前权限和原图有效性。"""
    async with pg_manager.get_async_session_context() as session:
        repo = HealthDietCorrectionRepository(session)
        record = await repo.record(uid, record_id, lock=True)
        record, confirmation = await HealthDietAnalysisRepository(session).source(uid, record.member_id, record_id)
        revisions = await repo.revisions(record_id)
        return {
            "id": record.id,
            "source_version": record.version or confirmation.draft_version,
            "revisions": [
                {
                    "version": row.version,
                    "snapshot": row.snapshot,
                    "reason": row.reason,
                    "calculation_id": row.calculation_id,
                    "created_at": format_utc_datetime(row.created_at),
                }
                for row in revisions
            ],
        }


def _validate_evidence(payload, original):
    """照片和模型原位置不可伪造；新增人工项目无模型位置。"""
    original = MealPayload.model_validate(original).model_dump(mode="json")
    if payload["photos"] != original["photos"]:
        raise HealthVisionError("evidence_invalid", "照片来源不可修改或伪造")
    sources = {item["item_id"]: item for item in original["items"]}
    ids = [item["item_id"] for item in payload["items"]]
    if len(ids) != len(set(ids)):
        raise HealthVisionError("duplicate_item", "结果项不能重复")
    for item in payload["items"]:
        if item["locations"] != sources.get(item["item_id"], {}).get("locations", []):
            raise HealthVisionError("evidence_invalid", "模型原位置不可修改或伪造")


def _result(record, confirmation, applied_version):
    """立即返回重算事实；重放收据不把历史版本复活成当前结果。"""
    return {
        "id": record.id,
        "source_version": record.version or confirmation.draft_version,
        "applied_version": applied_version,
        "status": "recalculated",
        "snapshot": record.snapshot,
        "analysis": analyze_confirmed_meal(record, confirmation),
    }

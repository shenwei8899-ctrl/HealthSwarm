"""人工实际摄入的原子确认及家庭逐人成败。"""

from uuid import uuid4, uuid5

from yuxi.repositories.health_consultation_repository import HealthConsultationRepository
from yuxi.repositories.health_diet_correction_repository import HealthDietCorrectionRepository
from yuxi.repositories.health_diet_analysis_repository import HealthDietAnalysisRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_nutrition_service import CALCULATION_VERSION, calculate_nutrition, input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_health import DietLog, NutritionCalculation, VisionConfirmation, VisionDraft


async def record_family_meal(uid, data):
    """独立事务允许部分成功，业务失败不撤销已确认成员。"""
    results = []
    for item in data.members:
        try:
            result = await record_meal(uid, item, group_id=data.group_id)
            results.append({"member_id": str(item.member_id), "status": "saved", **result})
        except HealthVisionError as error:
            results.append(
                {
                    "member_id": str(item.member_id),
                    "status": "failed",
                    "code": error.code,
                    "message": error.message,
                    "http_status": error.status,
                }
            )
    return {"group_id": str(data.group_id), "results": results}


async def record_meal(uid, data, *, group_id=None):
    """草稿、确定性计算、确认和日记同事务，未知响应可安全重放。"""
    member_id = str(data.member_id)
    request_id = str(uuid5(group_id, member_id)) if group_id else str(data.client_request_id)
    fingerprint = input_fingerprint(
        {
            "operation": "record_actual_meal",
            "group_id": str(group_id) if group_id else None,
            **data.model_dump(mode="json"),
        }
    )
    async with pg_manager.get_async_session_context() as session:
        await HealthConsultationRepository(session).lock_request(uid, request_id)
        repo = HealthVisionRepository(session)
        await repo.authorize(member_id, uid, "diet_edit", lock=True)
        previous = await repo.find_confirmation(uid, member_id, "meal", request_id)
        if previous:
            if previous.fingerprint != fingerprint:
                raise HealthVisionError("idempotency_conflict", "同一记餐请求不能修改内容，请先读取已保存记录", 409)
            record, confirmation = await HealthDietAnalysisRepository(session).source(
                uid, member_id, previous.target_ids[0]
            )
            return {
                "id": record.id,
                "source_version": record.version or confirmation.draft_version,
                "snapshot": record.snapshot,
                "replayed": True,
            }
        payload = data.meal.model_dump(mode="json")
        nutrition = calculate_nutrition(
            data.meal, *await HealthDietCorrectionRepository(session).nutrition_inputs(data.meal)
        )
        if not nutrition["complete"] and not data.accept_incomplete:
            raise HealthVisionError("nutrition_incomplete", "营养资料不完整，请明确接受缺失后再保存")
        draft = VisionDraft(
            id=str(uuid4()),
            member_id=member_id,
            kind="meal",
            payload=payload,
            original_payload=payload,
            review_status="confirmed",
            version=1,
        )
        session.add(draft)
        await session.flush()
        calculation = NutritionCalculation(
            id=str(uuid4()),
            draft_id=draft.id,
            draft_version=1,
            input_hash=input_fingerprint(payload),
            input_snapshot=payload,
            result=nutrition,
            calculation_version=CALCULATION_VERSION,
        )
        record_id = str(uuid4())
        confirmation = VisionConfirmation(
            id=str(uuid4()),
            draft_id=draft.id,
            draft_version=1,
            actor_uid=uid,
            member_id=member_id,
            kind="meal",
            request_id=request_id,
            fingerprint=fingerprint,
            target_ids=[record_id],
        )
        session.add_all([calculation, confirmation])
        await session.flush()
        snapshot = {
            "meal": payload,
            "nutrition": nutrition,
            "recording": {"group_id": str(group_id) if group_id else None, "source": "manual_actual_intake"},
        }
        session.add(
            DietLog(
                id=record_id,
                member_id=member_id,
                confirmation_id=confirmation.id,
                calculation_id=calculation.id,
                version=1,
                snapshot=snapshot,
            )
        )
        await session.flush()
        return {"id": record_id, "source_version": 1, "snapshot": snapshot, "replayed": False}


async def read_meal(uid, member_id, record_id):
    """详情始终重验当前成员授权、版本与来源。"""
    async with pg_manager.get_async_session_context() as session:
        record, confirmation = await HealthDietAnalysisRepository(session).source(uid, member_id, record_id)
        return {
            "id": record.id,
            "source_version": record.version or confirmation.draft_version,
            "snapshot": record.snapshot,
        }

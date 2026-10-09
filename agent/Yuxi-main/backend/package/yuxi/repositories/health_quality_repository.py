"""外部投影、检查收据及专业审核的PG来源查询。"""

import json
from datetime import datetime, UTC
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text, update, or_, and_
from yuxi.services.health_family_meal_plan_types import plan_member_ids

from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_quality_checks import external_projection, projection_digest
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AgentRun, FamilyArchive, Message, User, TOOL_AUDIT_MESSAGE_TYPE
from yuxi.storage.postgres.models_health import (
    HealthProfileSnapshot,
    HealthRuleSnapshot,
    HealthProfessionalReviewer,
    HealthQualityCheck,
    HealthProfessionalReview,
    HealthReviewAction,
    HealthQualityConversation,
    HealthMealPlan,
    HealthMealPlanAdoption,
    RecipeVersion,
    FoodRecord,
)
from yuxi.utils.datetime_utils import utc_now_naive


class HealthQualityRepository:
    """私有资源由成员授权和对象归属决定，管理员无读取旁路。"""

    def __init__(self, session):
        """复用业务用例的唯一事务。"""
        self.session = session

    async def lock_request(self, uid, request_id):
        """检查和审核动作的同账号同键冲突共享一个锁。"""
        await self.lock_key(f"health-quality:{uid}:{request_id}")

    async def lock_key(self, key):
        """版本来源的锁在当前事务持有，禁止检查后并发改源。"""
        await self.session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key})

    async def profile(self, member_id):
        """只读最高版本，最新撤回不得退回旧版本。"""
        return await self.session.scalar(
            select(HealthProfileSnapshot)
            .where(HealthProfileSnapshot.member_id == member_id)
            .order_by(HealthProfileSnapshot.version.desc())
            .limit(1)
        )

    async def profile_projection(self, member_id):
        """最高安全投影须仍对应本人当前确认来源，失败不回退旧版本。"""
        result = external_projection(await self.profile(member_id), "profile", member_id)
        if result["status"] != "ready":
            return result
        try:
            source = await HealthFamilyProfileRepository(self.session).confirmed_source(member_id)
        except HealthVisionError as error:
            if error.code == "family_profile_unconfirmed":
                reason = error.code
            elif error.status == 404:
                reason = "family_profile_source_unavailable"
            else:
                raise
        else:
            recorded = result["attestation"].get("family_profile_source")
            if source is None and recorded is None and result["attestation"].get("weight_measurement_source") is None:
                return result
            if source is not None and recorded is None:
                reason = "family_profile_source_unmapped"
            elif input_fingerprint(recorded) != input_fingerprint(source):
                reason = "family_profile_source_changed"
            else:
                recorded_weight = result["attestation"].get("weight_measurement_source")
                if recorded_weight is None:
                    return result
                try:
                    weight, weight_source = await HealthFamilyProfileRepository(self.session).weight_source(
                        member_id, str(UUID(recorded_weight["record_id"]))
                    )
                    value = result["payload"].get("weight_kg")
                    if (
                        input_fingerprint(recorded_weight) == input_fingerprint(weight_source)
                        and value is not None
                        and Decimal(str(value)) == weight
                    ):
                        return result
                except (KeyError, TypeError, ValueError):
                    pass
                except HealthVisionError as error:
                    if error.status != 404 and error.code != "weight_measurement_source_changed":
                        raise
                reason = "weight_measurement_source_changed"
        return {**result, "status": "not_ready", "reason": reason, "payload": None, "attestation": None}

    async def lock_profile_sources(self, member_ids):
        """健康成员锁后按家庭ID排序锁来源，跨计划共享家庭也不会反序等待。"""
        from yuxi.storage.postgres.models_health import HealthFamilyProfileLink

        families = select(HealthFamilyProfileLink.family_id).where(HealthFamilyProfileLink.member_id.in_(member_ids))
        await self.session.execute(
            select(FamilyArchive).where(FamilyArchive.id.in_(families)).order_by(FamilyArchive.id).with_for_update()
        )

    async def rules(self, rule_code, *, lock=False):
        """规则发布与使用共享来源锁，未知规则不会换到其他目录。"""
        if lock:
            await self.lock_key(f"health-rules:{rule_code}")
        return await self.session.scalar(
            select(HealthRuleSnapshot)
            .where(HealthRuleSnapshot.rule_code == rule_code)
            .order_by(HealthRuleSnapshot.version.desc())
            .limit(1)
        )

    async def latest_plan_review(self, uid, plan_id, version):
        """仅查询当前操作者、餐单与修订版本的最近检查复核状态。"""
        return await self.session.scalar(
            select(HealthProfessionalReview)
            .join(HealthQualityCheck, HealthQualityCheck.id == HealthProfessionalReview.check_id)
            .where(
                HealthQualityCheck.actor_uid == uid,
                HealthQualityCheck.plan_id == plan_id,
                HealthQualityCheck.plan_version == version,
                HealthProfessionalReview.actor_uid == uid,
            )
            .order_by(HealthQualityCheck.created_at.desc(), HealthQualityCheck.id.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )

    async def reviewer(self, uid, *, lock=False):
        """资格注册和审核共享当前人员来源锁。"""
        if lock:
            await self.lock_key(f"health-reviewer:{uid}")
        user = await self.session.scalar(select(User).where(User.uid == uid, User.is_deleted == 0))
        row = await self.session.scalar(
            select(HealthProfessionalReviewer)
            .where(HealthProfessionalReviewer.reviewer_uid == uid)
            .order_by(HealthProfessionalReviewer.version.desc())
            .limit(1)
        )
        if (
            user is None
            or row is None
            or row.revoked_at is not None
            or row.attested_at > utc_now_naive()
            or row.valid_until <= utc_now_naive()
        ):
            raise HealthVisionError("reviewer_not_qualified", "当前专业审核资格未登记或已失效", 403)
        try:
            proof = row.attestation
            attested = datetime.fromisoformat(proof["attested_at"]).astimezone(UTC).replace(tzinfo=None)
            expiry = datetime.fromisoformat(proof["valid_until"]).astimezone(UTC).replace(tzinfo=None)
            if (
                row.content_hash != projection_digest("reviewer", uid, row.version, {}, proof)
                or proof["reviewer_uid"] != uid
                or proof["version"] != row.version
                or attested != row.attested_at
                or expiry != row.valid_until
            ):
                raise ValueError("资格依据不符")
        except (KeyError, TypeError, ValueError):
            raise HealthVisionError("reviewer_not_qualified", "专业审核资格来源无法核对", 403) from None
        return row

    async def plan(self, uid, plan_id, *, review=False, lock=False, historical_member_ids=()):
        """当前与历史检查成员并集排序授权，审核者须显式专业成员授权。"""
        row = await self.session.get(HealthMealPlan, plan_id, populate_existing=True)
        if row is None or (not review and row.actor_uid != uid):
            raise HealthVisionError("not_found", "餐单不存在或无权访问", 404)
        ids = plan_member_ids(row.member_id, row.spec)
        vision = HealthVisionRepository(self.session)
        for member_id in sorted(set(ids) | set(historical_member_ids)):
            await vision.authorize(member_id, uid, "professional_review" if review else "diet_edit", lock=lock)
            await vision.authorize(member_id, uid, "profile_view")
        if lock:
            await self.session.refresh(row)
            if plan_member_ids(row.member_id, row.spec) != ids:
                raise HealthVisionError("source_invalidated", "计划参与者已变化，请刷新", 410)
        return row

    async def ingredients(self, spec):
        """批准分类绑定当前食品数据，配方内复制的来源也须一致。"""
        recipe_ids = {str(d.recipe_version_id) for meal in spec.meals for d in meal.dishes}
        return await self.recipe_sources(recipe_ids)

    async def recipe_sources(self, recipe_ids):
        """有界菜谱目录与计划检查共用配料完整性Owner。"""
        by_recipe, refs = await self.recipe_sources_by_recipe(recipe_ids)
        ingredients = {}
        for foods in by_recipe.values():
            for food_id, food in foods.items():
                entry = ingredients.setdefault(food_id, dict(food))
                entry["source_current"] = entry["source_current"] and food["source_current"]
        return ingredients, refs

    async def recipe_sources_by_recipe(self, recipe_ids):
        """目录逐配方校验，未选中坏配方不污染有效候选的食品来源。"""
        from yuxi.services.health_vision_service import health_vision_service

        recipes = list(
            (await self.session.scalars(select(RecipeVersion).where(RecipeVersion.id.in_(recipe_ids)))).all()
        )
        parsed, food_ids = [], set()
        for recipe in recipes:
            try:
                if not isinstance(recipe.ingredients, list) or not recipe.ingredients:
                    raise ValueError("配方须有明确配料")
                ids = {str(UUID(i["food"]["id"])) for i in recipe.ingredients}
            except (KeyError, TypeError, ValueError, AttributeError):
                # 持久化边界逐配方拒绝：未选坏配方不能使整个候选目录读取失败。
                continue
            parsed.append(recipe)
            food_ids.update(ids)
        foods = {
            food.id: food
            for food in (await self.session.scalars(select(FoodRecord).where(FoodRecord.id.in_(food_ids)))).all()
        }
        result, recipe_refs = {}, {}
        for recipe in parsed:
            recipe_foods = result.setdefault(recipe.id, {})
            recipe_refs[recipe.id] = input_fingerprint(
                {
                    "ingredients": recipe.ingredients,
                    "yield_grams": str(recipe.yield_grams),
                    "nutrients": recipe.nutrients,
                    "dataset_version": recipe.dataset_version,
                }
            )
            for ingredient in recipe.ingredients:
                food_id = ingredient["food"]["id"]
                current = health_vision_service.serialize_food(foods[food_id]) if food_id in foods else None
                entry = recipe_foods.setdefault(
                    food_id, {"content_hash": input_fingerprint(current), "source_current": True}
                )
                entry["source_current"] = entry["source_current"] and current == ingredient["food"]
        return result, recipe_refs

    async def selected(self, binding):
        """检查对象来自不可变业务选定，不读取会话metadata。"""
        row = await self.session.get(HealthQualityConversation, binding.conversation_id)
        if row is None:
            raise HealthVisionError("quality_selection_required", "需要业务入口明确选定方案和规则", 409)
        return row

    async def check_receipt(self, uid, request_id):
        """检查和动作不能混用一个幂等键。"""
        return await self.session.scalar(
            select(HealthQualityCheck).where(
                HealthQualityCheck.actor_uid == uid, HealthQualityCheck.request_id == request_id
            )
        )

    async def action_receipt(self, uid, request_id):
        """从不可变动作查询幂等结果。"""
        return await self.session.scalar(
            select(HealthReviewAction).where(
                HealthReviewAction.actor_uid == uid, HealthReviewAction.request_id == request_id
            )
        )

    async def case_for_check(self, check_id):
        """每个检查收据仅对应一个专业流程。"""
        return await self.session.scalar(
            select(HealthProfessionalReview).where(HealthProfessionalReview.check_id == check_id)
        )

    async def invalidate(
        self,
        *,
        member_id=None,
        rule_code=None,
        plan_id=None,
        reviewer_uid=None,
        actor_uid=None,
        reviewer_version=None,
        review_id=None,
        reason,
    ):
        """来源写入事务使受影响流程显式失效，历史动作不覆盖。"""
        stmt = update(HealthProfessionalReview).where(HealthProfessionalReview.status != "invalidated")
        if review_id is not None:
            stmt = stmt.where(HealthProfessionalReview.id == review_id)
        if member_id is not None or rule_code is not None or plan_id is not None:
            checks = select(HealthQualityCheck.id)
            if member_id is not None:
                checks = checks.where(
                    or_(
                        HealthQualityCheck.member_id == member_id,
                        HealthQualityCheck.snapshot["sources"]["profiles"].op("?")(member_id),
                    )
                )
            if rule_code is not None:
                checks = checks.where(HealthQualityCheck.rule_code == rule_code)
            if plan_id is not None:
                checks = checks.where(HealthQualityCheck.plan_id == plan_id)
            stmt = stmt.where(HealthProfessionalReview.check_id.in_(checks))
        if reviewer_uid is not None:
            stmt = stmt.where(
                HealthProfessionalReview.reviewer_uid == reviewer_uid, HealthProfessionalReview.status == "approved"
            )
        if actor_uid is not None:
            stmt = stmt.where(HealthProfessionalReview.actor_uid == actor_uid)
        if reviewer_version is not None:
            stmt = stmt.where(HealthProfessionalReview.reviewer_version == reviewer_version)
        await self.session.execute(
            stmt.values(
                status="invalidated",
                version=HealthProfessionalReview.version + 1,
                invalidation_reason=reason,
                updated_at=utc_now_naive(),
            )
        )
        # 专业失效与采用使用状态在同一写事务收敛，恢复来源不得复活。
        invalid_reviews = select(HealthProfessionalReview.id).where(HealthProfessionalReview.status == "invalidated")
        await self.session.execute(
            update(HealthMealPlanAdoption)
            .where(HealthMealPlanAdoption.status == "active", HealthMealPlanAdoption.review_id.in_(invalid_reviews))
            .values(
                status="invalidated",
                version=HealthMealPlanAdoption.version + 1,
                reason=reason,
                updated_at=utc_now_naive(),
            )
        )

    async def validate_history(self, uid, binding):
        """历史正文和成功工具审计均须对应当前服务器来源。"""
        from yuxi.services.health_quality_service import quality_context_in_session, validate_quality_tool_payload

        selection = await self.selected(binding)
        await quality_context_in_session(self.session, uid, selection)
        rows = (
            await self.session.execute(
                select(Message, AgentRun)
                .join(AgentRun, AgentRun.id == Message.run_id)
                .where(
                    AgentRun.conversation_id == binding.conversation_id,
                    or_(
                        and_(AgentRun.status == "completed", AgentRun.output_message_id == Message.id),
                        and_(
                            Message.message_type == TOOL_AUDIT_MESSAGE_TYPE,
                            Message.execution_status == "completed",
                            Message.extra_metadata["tool_name"]
                            .as_string()
                            .in_(["get_quality_review_context", "check_selected_plan_quality"]),
                        ),
                    ),
                )
            )
        ).all()
        for message, run in rows:
            try:
                payload = json.loads(message.content)
            except (ValueError, TypeError):
                raise HealthVisionError("source_invalidated", "质量检查历史无法解析", 410) from None
            name = (
                (message.extra_metadata or {}).get("tool_name")
                if message.message_type == TOOL_AUDIT_MESSAGE_TYPE
                else "final"
            )
            await validate_quality_tool_payload(self.session, uid, binding, run, name, payload)

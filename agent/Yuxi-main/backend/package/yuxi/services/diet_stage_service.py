"""阶段目标及行动用例，普通读写不等待模型。"""

from copy import deepcopy
from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import select

from yuxi.repositories.diet_stage_repository import DietStageRepository, stage_view, week_view
from yuxi.services.family_service import guardian_active
from yuxi.services.diet_stage_sources import generation_sources, report_comparisons, source_hash, frozen_review_valid
from yuxi.services.diet_stage_types import StageGenerate, review_date, stage_today, week_window
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.task_service import tasker
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import FamilyProfileRevision
from yuxi.storage.postgres.models_diet_stage import DietActionWeek, DietStage, DietStageReview
from yuxi.utils.datetime_utils import utc_now_naive


async def read_stage(uid, fid, mid, *, stage_id=None):
    """阶段页面只读，不登记任务或修改档案。"""
    async with pg_manager.get_async_session_context() as session:
        repo = DietStageRepository(session, uid, fid, mid)
        family, member = await repo.context()
        stage = await repo.stage(stage_id) if stage_id else await repo.active()
        history = list(
            (
                await session.scalars(
                    select(DietStage)
                    .where(DietStage.family_id == fid, DietStage.member_id == mid)
                    .order_by(DietStage.created_at.desc())
                )
            ).all()
        )
        weeks = await repo.weeks(stage.id) if stage else []
        jobs = list(
            (
                await session.scalars(
                    select(DietStageReview)
                    .where(
                        DietStageReview.member_id == mid,
                        DietStageReview.actor_uid == str(uid),
                        DietStageReview.stage_id == (stage.id if stage else None),
                    )
                    .order_by(DietStageReview.created_at.desc())
                    .limit(12)
                )
            ).all()
        )
        return {
            "can_edit": family.owner_uid == str(uid)
            or member.subject_uid == str(uid)
            or guardian_active(member, str(uid)),
            "member_id": member.id,
            "name": member.name,
            "is_self": member.subject_uid == str(uid),
            "profile_version": member.version,
            "existing_goals": (member.profile or {}).get("dietary_details", {}).get("goals", []),
            "stage": stage_view(stage) if stage else None,
            "weeks": [week_view(week) for week in weeks],
            "history": [stage_view(row) for row in history],
            "jobs": [{"id": row.id, "kind": row.kind, "status": row.status} for row in jobs],
            "today": stage_today().isoformat(),
        }


async def save_stage(uid, fid, mid, data):
    """目标与兼容摘要原子提交，原键重放先于版本检查。"""
    async with pg_manager.get_async_session_context() as session:
        repo = DietStageRepository(session, uid, fid, mid)
        _, member = await repo.context(write=True)
        digest = input_fingerprint(data.model_dump(mode="json"))
        replay = await repo.replay(data.client_request_id, digest)
        if replay is not None:
            return replay
        draft = await repo.job(data.draft_id)
        if draft.status != "ready" or draft.kind != "draft":
            raise HealthVisionError("stage_draft_unavailable", "请先生成并核对目标草案", 409)
        if draft.sources["profile_version"] != member.version or data.profile_version != member.version:
            raise HealthVisionError("version_conflict", "档案已变化，请重新生成目标建议", 409)
        current = await generation_sources(
            repo,
            StageGenerate.model_validate(draft.sources["request"]),
            as_of=date.fromisoformat(draft.sources["as_of"]),
        )
        if source_hash(current) != draft.input_hash:
            raise HealthVisionError("source_invalidated", "草案资料已变化，请重新生成建议", 409)
        stage = await repo.active()
        if data.previous_stage_id:
            if stage is None or stage.id != str(data.previous_stage_id) or stage.version != data.expected_version:
                raise HealthVisionError("version_conflict", "阶段已变化，请重新读取", 409)
            reviews = await session.scalar(
                select(DietStageReview)
                .where(
                    DietStageReview.stage_id == stage.id,
                    DietStageReview.actor_uid == str(uid),
                    DietStageReview.kind == "review",
                    DietStageReview.status == "ready",
                )
                .order_by(DietStageReview.created_at.desc())
                .limit(1)
            )
            if stage_today() < stage.review_on or reviews is None:
                raise HealthVisionError("stage_review_required", "阶段到期并完成复盘后再开启下一阶段", 409)
            review_request = StageGenerate.model_validate(reviews.sources["request"])
            review_sources = await generation_sources(
                repo, review_request, as_of=date.fromisoformat(reviews.sources["as_of"])
            )
            if reviews.sources["as_of"] != (stage.review_on - timedelta(days=1)).isoformat() or (
                source_hash(review_sources) != reviews.input_hash
            ):
                raise HealthVisionError("stage_review_stale", "请先更新截至阶段结束的复盘", 409)
            stage.status = "completed"
            await session.flush()
            stage = None
        if stage is None:
            if not data.previous_stage_id and data.expected_version != 0:
                raise HealthVisionError("version_conflict", "阶段状态已变化", 409)
            day = stage_today()
            stage = DietStage(
                id=str(uuid4()),
                family_id=fid,
                member_id=mid,
                actor_uid=str(uid),
                starts_on=day,
                review_on=review_date(day),
                goals=list(data.goals),
                version=1,
            )
            session.add(stage)
            await session.flush()
        else:
            if stage.version != data.expected_version or stage_today() >= stage.review_on:
                raise HealthVisionError("version_conflict", "请核对当前阶段或先完成复盘", 409)
            stage.goals = list(data.goals)
            stage.version += 1
        await sync_goal_summary(session, member, uid, data.goals)
        first, stop = week_window(stage.starts_on, stage.review_on, stage_today())
        week = await repo.week(stage.id, first)
        if week is None:
            week = DietActionWeek(
                id=str(uuid4()),
                stage_id=stage.id,
                starts_on=first,
                ends_on=stop,
                actions=fresh_actions(data.actions),
                goal_version=stage.version,
                version=1,
            )
            session.add(week)
        # 修改目标不清除已勾选的当周行动；可在行动编辑中单独调整。
        result = {"stage": stage_view(stage), "week": week_view(week)}
        draft.status = "adopted"
        repo.receipt(stage, data.client_request_id, digest, result)
        await session.flush()
        return result


async def save_week(uid, fid, mid, stage_id, week_id, data):
    """绝对计次和幂等收据共同避免重复完成，保留阶段版本。"""
    async with pg_manager.get_async_session_context() as session:
        repo = DietStageRepository(session, uid, fid, mid)
        await repo.context(write=True)
        stage = await repo.stage(stage_id)
        digest = input_fingerprint({"week_id": str(week_id), **data.model_dump(mode="json")})
        replay = await repo.replay(data.client_request_id, digest)
        if replay is not None:
            return replay
        week = await session.get(DietActionWeek, str(week_id))
        if week is None or week.stage_id != stage.id:
            raise HealthVisionError("not_found", "行动清单不存在", 404)
        if stage.status != "active" or stage_today() >= stage.review_on:
            raise HealthVisionError("stage_closed", "已结束阶段的行动不能修改", 409)
        if week.version != data.expected_version:
            raise HealthVisionError("version_conflict", "行动已更新，请重新读取", 409)
        known = {item["id"] for item in week.actions}
        ids = [str(item.id) for item in data.actions if item.id]
        if len(set(ids)) != len(ids) or any(item not in known for item in ids):
            raise HealthVisionError("action_invalid", "行动身份无法核对", 422)
        week.actions = [{**item.model_dump(mode="json"), "id": str(item.id or uuid4())} for item in data.actions]
        week.version += 1
        result = week_view(week)
        repo.receipt(stage, data.client_request_id, digest, result)
        return result


async def generate_stage(uid, fid, mid, data):
    """先提交持久任务，再投递；相同请求不重复外呼。"""
    async with pg_manager.get_async_session_context() as session:
        repo = DietStageRepository(session, uid, fid, mid)
        await repo.context(write=True)
        old = await session.scalar(
            select(DietStageReview).where(
                DietStageReview.actor_uid == str(uid), DietStageReview.request_id == str(data.client_request_id)
            )
        )
        if old:
            await repo.job(old.id)
            if old.sources["request"] != data.model_dump(mode="json"):
                raise HealthVisionError("idempotency_conflict", "请求内容已变化", 409)
            return {"id": old.id, "status": old.status, "kind": old.kind}
        sources = await generation_sources(repo, data)
        stage = await repo.stage(data.stage_id) if data.stage_id else await repo.active()
        if data.kind != "draft" and stage is None:
            raise HealthVisionError("stage_required", "请先开启阶段", 409)
        row = DietStageReview(
            id=str(uuid4()),
            family_id=fid,
            member_id=mid,
            actor_uid=str(uid),
            request_id=str(data.client_request_id),
            stage_id=stage.id if stage else None,
            kind=data.kind,
            status="pending",
            input_hash=source_hash(sources),
            sources={**sources, "request": data.model_dump(mode="json")},
        )
        session.add(row)
        task = await tasker.create_in_session(
            session,
            name="整理饮食目标与阶段复盘",
            task_type="diet_stage_v1",
            payload={"job_id": row.id, "uid": str(uid), "family_id": fid, "member_id": mid},
            timeout_seconds=300,
        )
        row.task_id = task.id
    await tasker.publish(task)
    return {"id": row.id, "kind": row.kind, "status": row.status}


async def read_stage_job(uid, fid, mid, job_id):
    """来源变化不返回旧正文；后台失败保留可重试状态。"""
    async with pg_manager.get_async_session_context() as session:
        repo = DietStageRepository(session, uid, fid, mid)
        await repo.context()
        row = await repo.job(job_id)
        if row.status != "ready":
            return {"id": row.id, "kind": row.kind, "status": row.status, "result": None, "error": row.error}
        current = await generation_sources(
            repo,
            StageGenerate.model_validate(row.sources["request"]),
            as_of=date.fromisoformat(row.sources["as_of"]),
            for_read=True,
        )
        current["processing"] = row.sources["processing"]
        closed = row.stage_id and (await repo.stage(row.stage_id)).status == "completed" and row.kind == "review"
        valid = frozen_review_valid(row.sources, current) if closed else source_hash(current) == row.input_hash
        if not valid:
            return {
                "id": row.id,
                "kind": row.kind,
                "status": "stale",
                "result": None,
                "error": "资料或行动有更新，可以重新整理",
            }
        return {
            "id": row.id,
            "kind": row.kind,
            "status": row.status,
            "result": row.result,
            "as_of": row.sources["as_of"],
            "error": row.error,
            "reports": [
                {**item, "supplemental": item["current"]["observed_at"] > current["window"]["end_date"]}
                for item in report_comparisons(
                    current["reports"],
                    {**current["window"], "end_date": stage_today().isoformat()} if closed else current["window"],
                )
            ]
            if row.kind == "review"
            else [],
        }


async def sync_goal_summary(session, member, uid, goals):
    """同一事务同步既有字段和档案修订，不调用会自行提交的HTTP用例。"""
    from yuxi.repositories.health_quality_repository import HealthQualityRepository
    from yuxi.repositories.family_repository import FamilyRepository

    profile = deepcopy(member.profile or {})
    profile["goal"] = "、".join(goals)
    profile["diet_stage_managed"] = True
    profile["dietary_details"] = {**profile.get("dietary_details", {}), "goals": list(goals)}
    # 原结构化历史保持，不新增另一套可编辑的当前目标。
    member.profile = profile
    member.version += 1
    member.confirmed_at = None
    member.updated_at = utc_now_naive()
    session.add(FamilyProfileRevision(member_id=member.id, version=member.version, profile=profile, actor_uid=str(uid)))
    await FamilyRepository(session).audit(member.family_id, member.id, str(uid), "diet_stage.goal", member.version)
    hid = await FamilyRepository(session).linked_health_member(member.family_id, member.id)
    if hid:
        await HealthQualityRepository(session).invalidate(member_id=hid, reason="family_profile_changed")


def fresh_actions(actions):
    """模型建议与新周均从零开始，不接受自动完成。"""
    return [{"id": str(uuid4()), "title": item.title, "target": item.target, "count": 0} for item in actions]

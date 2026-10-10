"""正式家庭档案与 Agent 的显式来源及当前版本依赖。"""

import hashlib
import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from yuxi.repositories.family_repository import FamilyRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.family_schemas import (
    PROFILE_FIELDS,
    REQUIRED_PROFILE_FIELDS,
    STRUCTURED_PROFILE_FIELDS,
    validate_metric_values,
)
from yuxi.services.family_service import authorized_fields
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AgentRun
from yuxi.storage.postgres.models_health import HealthFamilyProfileLink, HealthFamilyProfileUse
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive


class HealthFamilyProfileRepository:
    """由用例拥有事务；健康锁后家庭锁，正式档案写入不反向锁健康对象。"""

    def __init__(self, session):
        self.session = session

    async def link(self, uid, member_id, family_id, source_member_id):
        """本人确认身份后建立唯一关联；重复调用返回同一事实。"""
        member = await HealthVisionRepository(self.session).authorize(member_id, uid, "profile_edit", lock=True)
        if member.owner_uid != uid or member.relationship_label != "本人":
            raise HealthVisionError("not_found", "仅能关联自己的本人健康对象", 404)
        family_repo = FamilyRepository(self.session)
        family = await family_repo.get_family(family_id, uid)
        source = await family_repo.member(family_id, source_member_id) if family else None
        if source is None or not source.is_active or source.subject_uid != uid:
            raise HealthVisionError("not_found", "仅能关联自己已认领的家庭成员", 404)
        existing = await self.session.get(HealthFamilyProfileLink, member_id, populate_existing=True)
        if existing is not None:
            if existing.source_member_id != source_member_id or existing.family_id != family_id:
                raise HealthVisionError("profile_link_conflict", "已关联的成员不能改绑", 409)
            return self.link_result(existing)
        other = await self.session.scalar(
            select(HealthFamilyProfileLink).where(HealthFamilyProfileLink.source_member_id == source_member_id)
        )
        if other is not None:
            raise HealthVisionError("profile_link_conflict", "正式成员已关联其他健康对象", 409)
        link = HealthFamilyProfileLink(
            member_id=member_id, source_member_id=source_member_id, family_id=family_id, actor_uid=uid
        )
        self.session.add(link)
        await family_repo.audit(family_id, source_member_id, uid, "agent_profile_link", source.version)
        from yuxi.repositories.health_quality_repository import HealthQualityRepository

        await HealthQualityRepository(self.session).invalidate(member_id=member_id, reason="family_profile_linked")
        return self.link_result(link)

    async def read_link(self, uid, member_id):
        """映射元信息也受本人及当前健康字段授权保护。"""
        await HealthVisionRepository(self.session).authorize(member_id, uid, "profile_view", lock=True)
        link = await self.session.get(HealthFamilyProfileLink, member_id, populate_existing=True)
        if link is None:
            return {"member_id": member_id, "source_member_id": None, "scope": "self_confirmed_profile"}
        await self.source(uid, link)
        return self.link_result(link)

    async def read_import_source(self, uid, member_id, *, limit=20, offset=0):
        """健康授权后读取操作者当前可见来源；原始字段不借用关联本人的授权。"""
        formal = {
            "status": "not_ready",
            "reason": "profile_not_linked",
            "family_profile_source": None,
            "profile": {},
            "allowed_fields": [],
        }
        weights = {
            "status": "not_ready",
            "reason": "profile_not_linked",
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
        }
        result = {"formal_source": formal, "weight_candidates": weights}
        link = await self.session.get(HealthFamilyProfileLink, member_id, populate_existing=True)
        if link is None:
            return result
        family_repo = FamilyRepository(self.session)
        family = await family_repo.get_family(link.family_id, uid)
        if family is None:
            formal["reason"] = weights["reason"] = "family_profile_access_required"
            return result
        source = await family_repo.member(link.family_id, link.source_member_id)
        if source is not None:
            await self.session.refresh(source)
        if source is None or not source.is_active or source.subject_uid != link.actor_uid:
            formal["reason"] = weights["reason"] = "family_profile_source_unavailable"
            return result
        allowed = authorized_fields(family, source, uid)
        basic_fields = set(REQUIRED_PROFILE_FIELDS) & allowed
        formal.update(
            reason="family_profile_fields_required",
            profile={key: (source.profile or {}).get(key) for key in sorted(basic_fields)},
            allowed_fields=sorted(basic_fields),
        )
        if set(REQUIRED_PROFILE_FIELDS) <= allowed:
            if source.confirmed_version != source.version:
                formal["reason"] = "family_profile_unconfirmed"
            elif any((source.profile or {}).get(key) in (None, "", []) for key in REQUIRED_PROFILE_FIELDS):
                formal["reason"] = "family_profile_incomplete"
            else:
                formal.update(
                    status="ready",
                    reason=None,
                    family_profile_source={
                        "family_id": link.family_id,
                        "source_member_id": source.id,
                        "confirmed_version": source.version,
                    },
                )
        if basic_fields:
            await family_repo.audit(link.family_id, source.id, uid, "profile_import_source_read")
        if "weight" not in allowed:
            weights["reason"] = "weight_access_required"
            return result
        rows, total = await family_repo.measurement_page(
            [source.id], ["weight"], until=utc_now_naive(), limit=limit, offset=offset
        )
        items = []
        for row in rows:
            try:
                if (
                    not isinstance(row.values, dict)
                    or type(row.values.get("weight")) not in (int, float)
                    or type(row.version) is not int
                    or row.version < 1
                ):
                    raise ValueError
                validate_metric_values("weight", row.values)
                weight = Decimal(str(row.values["weight"]))
            except (ValueError, TypeError, OverflowError) as error:
                raise HealthVisionError(
                    "weight_measurement_source_changed", "体重记录无法核对，请更正原记录", 410
                ) from error
            items.append(
                {
                    "record_id": row.id,
                    "version": row.version,
                    "weight_kg": str(weight),
                    "unit": "kg",
                    "measured_at": format_utc_datetime(row.measured_at),
                    "source": row.source,
                }
            )
        weights.update(
            status="ready" if items else "not_ready",
            reason=None if items else "weight_missing",
            items=items,
            total=total,
        )
        await family_repo.audit(link.family_id, source.id, uid, "profile_import_weights_read")
        return result

    async def confirmed_source(self, member_id):
        """调用方已核对健康授权；专业投影绑定本人当前确认事实。"""
        link = await self.session.get(HealthFamilyProfileLink, member_id, populate_existing=True)
        if link is None:
            return None
        _, source = await self.source(link.actor_uid, link, lock=True)
        if source.confirmed_version != source.version:
            raise HealthVisionError("family_profile_unconfirmed", "正式档案当前版本尚未由本人确认", 409)
        facts = {
            "family_id": link.family_id,
            "source_member_id": source.id,
            "confirmed_version": source.version,
            "profile": source.profile,
        }
        digest = hashlib.sha256(
            json.dumps(facts, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        return {key: value for key, value in facts.items() if key != "profile"} | {"source_hash": digest}

    async def weight_source(self, member_id, record_id):
        """在本人家庭锁下核对明确实测，不从查询窗口自动选取。"""
        link = await self.session.get(HealthFamilyProfileLink, member_id, populate_existing=True)
        if link is None:
            raise HealthVisionError("not_found", "没有对应的本人正式档案关联", 404)
        _, source = await self.source(link.actor_uid, link, lock=True)
        record = await FamilyRepository(self.session).measurement(record_id)
        if record is not None:
            await self.session.refresh(record)
        if (
            record is None
            or record.member_id != source.id
            or record.kind != "weight"
            or record.voided_at is not None
            or record.measured_at > utc_now_naive()
        ):
            raise HealthVisionError("not_found", "所选本人实测体重不可用", 404)
        try:
            if not isinstance(record.values, dict) or type(record.values.get("weight")) not in (int, float):
                raise ValueError
            validate_metric_values("weight", record.values)
            weight = Decimal(str(record.values["weight"]))
        except (ValueError, TypeError, OverflowError) as error:
            raise HealthVisionError(
                "weight_measurement_source_changed", "体重记录无法核对，请更正原记录", 410
            ) from error
        facts = {
            "family_id": link.family_id,
            "source_member_id": source.id,
            "record_id": record.id,
            "version": record.version,
            "kind": "weight",
            "weight_kg": str(weight),
            "unit": "kg",
            "measured_at": format_utc_datetime(record.measured_at),
            "source": record.source,
        }
        reference = {key: value for key, value in facts.items() if key not in {"kind", "weight_kg"}}
        return weight, {**reference, "source_hash": input_fingerprint(facts)}

    async def read(self, uid, member_id, *, lock=True, audit=True):
        """只返回本人已确认的原始档案；临床编码与独立测量不继承确认。"""
        await HealthVisionRepository(self.session).authorize(member_id, uid, "profile_view", lock=lock)
        link = await self.session.get(HealthFamilyProfileLink, member_id, populate_existing=True)
        result = {
            "status": "not_ready",
            "code": "profile_not_linked",
            "owner": "健康档案服务",
            "profile_available": False,
            "full_health_profile_available": False,
            "nutrition_safety_ready": False,
            "profile": None,
            "confirmed_version": None,
        }
        if link is None:
            return result
        family, source = await self.source(uid, link, lock=lock)
        allowed = authorized_fields(family, source, uid) & PROFILE_FIELDS
        allowed -= STRUCTURED_PROFILE_FIELDS - (source.profile or {}).keys()
        missing = sorted(key for key in REQUIRED_PROFILE_FIELDS if (source.profile or {}).get(key) in (None, "", []))
        if source.confirmed_version != source.version:
            return {**result, "code": "profile_unconfirmed"}
        if missing:
            return {**result, "code": "profile_incomplete", "missing_fields": missing}
        profile = {key: (source.profile or {}).get(key) for key in sorted(allowed)}
        result.update(
            status="ready",
            code="self_confirmed_profile",
            profile_available=True,
            profile=profile,
            confirmed_version=source.version,
            allowed_fields=sorted(allowed),
            unknown_fields=sorted(key for key, value in profile.items() if value in (None, "")),
            source={"family_id": link.family_id, "source_member_id": source.id, "version": source.version},
            unsupported=["nutrition_safety_codes", "approved_personal_targets", "independent_measurements"],
        )
        result["source_hash"] = self.payload_hash(result)
        if audit:
            await FamilyRepository(self.session).audit(
                link.family_id, source.id, uid, "agent_profile_read", source.version
            )
        return result

    async def record_use(self, run, payload):
        """外呼前持久化依赖；不复制健康正文。"""
        if payload.get("status") != "ready":
            return
        source = payload["source"]
        await self.session.execute(
            insert(HealthFamilyProfileUse)
            .values(
                run_id=run.id,
                payload_hash=payload["source_hash"],
                member_id=await self.run_member(run),
                source_member_id=source["source_member_id"],
                version=source["version"],
            )
            .on_conflict_do_nothing()
        )

    async def validate_history(self, uid, binding, *, lock=False):
        """真实 Run 依赖重验所有派生轮次；改版后建立新咨询。"""
        uses = list(
            (
                await self.session.scalars(
                    select(HealthFamilyProfileUse)
                    .join(AgentRun, AgentRun.id == HealthFamilyProfileUse.run_id)
                    .where(
                        AgentRun.conversation_id == binding.conversation_id,
                        AgentRun.uid == uid,
                    )
                )
            ).all()
        )
        if not uses:
            return
        current = await self.read(uid, binding.member_id, lock=lock, audit=False)
        if any(
            current.get("source_hash") != use.payload_hash
            or use.member_id != binding.member_id
            or current.get("source", {}).get("source_member_id") != use.source_member_id
            for use in uses
        ):
            raise HealthVisionError("profile_source_changed", "档案来源已变化，请建立新咨询读取当前版本", 410)

    async def validate_tool_payload(self, uid, binding, payload):
        """checkpoint 只接受真实线程读取过且仍有效的档案正文。"""
        if not isinstance(payload, dict):
            raise HealthVisionError("profile_source_changed", "档案checkpoint无法核对", 410)
        if payload.get("status") != "ready":
            legacy = {
                "status": "not_ready",
                "code": "profile_integration_pending",
                "owner": "健康档案服务",
                "full_health_profile_available": False,
                "profile": None,
                "confirmed_version": None,
            }
            if payload != legacy and payload != await self.read(uid, binding.member_id):
                raise HealthVisionError("profile_source_changed", "未确认档案checkpoint无法核对", 410)
            return
        current = await self.read(uid, binding.member_id)
        if payload != current or self.payload_hash(payload) != current.get("source_hash"):
            raise HealthVisionError("profile_source_changed", "档案checkpoint来源已失效", 410)
        use = await self.session.scalar(
            select(HealthFamilyProfileUse)
            .join(AgentRun, AgentRun.id == HealthFamilyProfileUse.run_id)
            .where(
                AgentRun.conversation_id == binding.conversation_id,
                AgentRun.uid == uid,
                HealthFamilyProfileUse.member_id == binding.member_id,
                HealthFamilyProfileUse.payload_hash == payload.get("source_hash"),
            )
        )
        if use is None:
            raise HealthVisionError("profile_source_changed", "档案checkpoint来源已失效", 410)

    async def source(self, uid, link, *, lock=True):
        """持家庭锁后刷新身份；管理员自己的处理同意不能代替本人。"""
        family_repo = FamilyRepository(self.session)
        if lock:
            family = await family_repo.get_family(link.family_id, uid)
        else:
            from yuxi.storage.postgres.models_business import FamilyArchive

            family = await self.session.scalar(
                family_repo.visible_families(uid).where(FamilyArchive.id == link.family_id)
            )
        source = await family_repo.member(link.family_id, link.source_member_id) if family else None
        if source is not None:
            await self.session.refresh(source)
        if source is None or not source.is_active or source.subject_uid != uid or link.actor_uid != uid:
            raise HealthVisionError("not_found", "正式档案不存在或无本人处理授权", 404)
        return family, source

    async def run_member(self, run):
        """依赖成员只能来自服务器固定的咨询绑定。"""
        from yuxi.storage.postgres.models_health import HealthConsultation

        binding = await self.session.get(HealthConsultation, run.conversation_id)
        return binding.member_id

    @staticmethod
    def link_result(link):
        """仅公开稳定来源，不公开操作者账号。"""
        return {
            "member_id": link.member_id,
            "source_member_id": link.source_member_id,
            "family_id": link.family_id,
            "scope": "self_confirmed_profile",
        }

    @staticmethod
    def payload_hash(payload):
        """正式字段、确认版本和来源共同决定摘要。"""
        return hashlib.sha256(
            json.dumps(
                {key: value for key, value in payload.items() if key != "source_hash"},
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

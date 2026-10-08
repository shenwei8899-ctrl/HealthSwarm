"""本人独立体重与血压的共同授权、冻结范围及依赖校验。"""

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from yuxi.repositories.family_repository import FamilyRepository
from yuxi.repositories.health_family_profile_repository import HealthFamilyProfileRepository
from yuxi.repositories.health_vision_repository import HealthVisionRepository
from yuxi.services.family_schemas import METRIC_UNITS, validate_metric_values
from yuxi.services.family_service import authorized_fields
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_business import AgentRun
from yuxi.storage.postgres.models_health import HealthConsultation, HealthFamilyProfileLink
from yuxi.utils.datetime_utils import format_utc_datetime

DISPLAY_ZONE = ZoneInfo("Asia/Shanghai")
MEASUREMENT_LIMIT = 20


class HealthMeasurementRepository:
    """用例拥有事务；受控读取先持健康锁，再持家庭锁。"""

    kind: str
    label: str
    use_model: type
    value_fields: dict[str, str]

    def __init__(self, session):
        self.session = session

    async def read(self, uid, member_id, period=None, *, lock=True, audit=True):
        """只投影本人必要实测字段，不继承基础档案确认或营养安全状态。"""
        member = await HealthVisionRepository(self.session).authorize(member_id, uid, "profile_view", lock=lock)
        if member.owner_uid != uid or member.relationship_label != "本人":
            raise HealthVisionError("not_found", f"仅能读取自己的本人实测{self.label}", 404)
        period, since, until = self.period_window(period)
        result = {
            "status": "not_ready",
            "code": f"{self.kind}_not_linked",
            "owner": "健康档案服务",
            "member_id": member_id,
            "source_member_id": None,
            "period": period,
            "limit": MEASUREMENT_LIMIT,
            "records": [],
            "truncated": False,
            "full_health_profile_available": False,
            "nutrition_safety_ready": False,
        }
        link = await self.session.get(HealthFamilyProfileLink, member_id, populate_existing=True)
        if link is not None:
            family, source = await HealthFamilyProfileRepository(self.session).source(uid, link, lock=lock)
            if self.kind not in authorized_fields(family, source, uid):
                raise HealthVisionError("not_found", f"无本人实测{self.label}字段访问授权", 403)
            family_repo = FamilyRepository(self.session)
            rows, total = await family_repo.measurement_page(
                [source.id], [self.kind], since=since, until=until, limit=MEASUREMENT_LIMIT
            )
            for row in rows[:MEASUREMENT_LIMIT]:
                try:
                    if not isinstance(row.values, dict) or any(
                        type(row.values.get(field)) not in (int, float) for field in self.value_fields.values()
                    ):
                        raise ValueError
                    validate_metric_values(self.kind, row.values)
                except (ValueError, TypeError, OverflowError) as error:
                    raise HealthVisionError(
                        f"{self.kind}_source_changed", f"{self.label}记录无法核对，请更正原记录", 410
                    ) from error
            result.update(
                status="ready" if rows else "not_ready",
                code=f"self_{self.kind}_records" if rows else f"{self.kind}_missing",
                source_member_id=source.id,
                records=[
                    {
                        "record_id": row.id,
                        **{output: row.values[field] for output, field in self.value_fields.items()},
                        "unit": METRIC_UNITS[self.kind],
                        "measured_at": format_utc_datetime(row.measured_at),
                        "source": row.source,
                        "version": row.version,
                    }
                    for row in rows[:MEASUREMENT_LIMIT]
                ],
                truncated=total > MEASUREMENT_LIMIT,
            )
            if audit:
                await family_repo.audit(link.family_id, source.id, uid, f"agent_{self.kind}_read")
        result["source_hash"] = self.payload_hash(result)
        return result

    async def record_use(self, run, payload):
        """外呼前保存引用回执，未关联与空结果也参与后续失效校验。"""
        binding = await self.session.get(HealthConsultation, run.conversation_id)
        if binding is None or binding.actor_uid != run.uid or payload["member_id"] != binding.member_id:
            raise HealthVisionError(f"{self.kind}_source_changed", f"{self.label}读取缺少当前咨询绑定", 410)
        period, _, _ = self.period_window(payload["period"])
        await self.session.execute(
            insert(self.use_model)
            .values(
                run_id=run.id,
                payload_hash=payload["source_hash"],
                member_id=binding.member_id,
                source_member_id=payload["source_member_id"],
                start_date=date.fromisoformat(period["start_date"]),
                end_date=date.fromisoformat(period["end_date"]),
                record_refs=self.record_refs(payload),
            )
            .on_conflict_do_nothing()
        )

    async def validate_history(self, uid, binding, *, lock=False):
        """所有派生轮次重读当时冻结的范围；不依赖当前轮再次调用工具。"""
        uses = list(
            (
                await self.session.scalars(
                    select(self.use_model)
                    .join(AgentRun, AgentRun.id == self.use_model.run_id)
                    .where(AgentRun.conversation_id == binding.conversation_id, AgentRun.uid == uid)
                )
            ).all()
        )
        for use in uses:
            period = {
                "start_date": use.start_date.isoformat(),
                "end_date": use.end_date.isoformat(),
                "timezone": "Asia/Shanghai",
            }
            try:
                current = await self.read(uid, binding.member_id, period, lock=lock, audit=False)
            except HealthVisionError as error:
                if error.status not in (403, 404):
                    raise
                raise HealthVisionError(
                    f"{self.kind}_source_changed", f"{self.label}来源已失效，请建立新咨询", 410
                ) from error
            if (
                use.member_id != binding.member_id
                or use.payload_hash != current["source_hash"]
                or use.source_member_id != current["source_member_id"]
                or json.dumps(use.record_refs, sort_keys=True) != json.dumps(self.record_refs(current), sort_keys=True)
            ):
                raise HealthVisionError(
                    f"{self.kind}_source_changed", f"{self.label}记录已变化，请建立新咨询读取当前版本", 410
                )

    async def validate_tool_payload(self, uid, binding, payload):
        """checkpoint 只接受真实线程已读取且当前仍精确一致的投影。"""
        if not isinstance(payload, dict) or "period" not in payload:
            raise HealthVisionError(f"{self.kind}_source_changed", f"{self.label}checkpoint无法核对", 410)
        try:
            current = await self.read(uid, binding.member_id, payload["period"], audit=False)
        except HealthVisionError as error:
            if error.status not in (403, 404):
                raise
            raise HealthVisionError(f"{self.kind}_source_changed", f"{self.label}checkpoint来源已失效", 410) from error
        if payload != current or self.payload_hash(payload) != current["source_hash"]:
            raise HealthVisionError(f"{self.kind}_source_changed", f"{self.label}checkpoint来源已失效", 410)
        use = await self.session.scalar(
            select(self.use_model)
            .join(AgentRun, AgentRun.id == self.use_model.run_id)
            .where(
                AgentRun.conversation_id == binding.conversation_id,
                AgentRun.uid == uid,
                self.use_model.member_id == binding.member_id,
                self.use_model.payload_hash == payload.get("source_hash"),
            )
        )
        if (
            use is None
            or use.source_member_id != current["source_member_id"]
            or use.start_date.isoformat() != current["period"]["start_date"]
            or use.end_date.isoformat() != current["period"]["end_date"]
            or json.dumps(use.record_refs, sort_keys=True) != json.dumps(self.record_refs(current), sort_keys=True)
        ):
            raise HealthVisionError(f"{self.kind}_source_changed", f"{self.label}checkpoint来源已失效", 410)

    @staticmethod
    def payload_hash(payload):
        """摘要包括空结果、固定范围和截断标志，但不包括摘要自身。"""
        return hashlib.sha256(
            json.dumps(
                {key: value for key, value in payload.items() if key != "source_hash"},
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    @classmethod
    def period_window(cls, period=None):
        """北京时间自然日闭区间转换为数据库 UTC 半开区间。"""
        if period is None:
            end = datetime.now(DISPLAY_ZONE).date()
            start = end - timedelta(days=29)
        else:
            try:
                if not isinstance(period, dict) or set(period) != {"start_date", "end_date", "timezone"}:
                    raise ValueError
                if period["timezone"] != "Asia/Shanghai":
                    raise ValueError
                start = date.fromisoformat(period["start_date"])
                end = date.fromisoformat(period["end_date"])
                if end - start != timedelta(days=29) or start.isoformat() != period["start_date"]:
                    raise ValueError
                if end.isoformat() != period["end_date"]:
                    raise ValueError
            except (ValueError, TypeError) as error:
                raise HealthVisionError(f"{cls.kind}_source_changed", f"{cls.label}查询范围无法核对", 410) from error
        normalized = {"start_date": start.isoformat(), "end_date": end.isoformat(), "timezone": "Asia/Shanghai"}
        try:
            since = datetime.combine(start, time.min, DISPLAY_ZONE).astimezone(UTC).replace(tzinfo=None)
            until = (
                datetime.combine(end + timedelta(days=1), time.min, DISPLAY_ZONE).astimezone(UTC).replace(tzinfo=None)
            )
        except OverflowError as error:
            raise HealthVisionError(f"{cls.kind}_source_changed", f"{cls.label}查询范围无法核对", 410) from error
        return normalized, since, until

    @staticmethod
    def record_refs(payload):
        """回执只保存记录标识和独立版本，不复制测量正文。"""
        return [{"record_id": row["record_id"], "version": row["version"]} for row in payload["records"]]

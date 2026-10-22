"""来源分流和拒绝边界的内存测试，不创建业务或专业确认数据。"""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from yuxi.repositories.health_quality_repository import HealthQualityRepository
from yuxi.services.miniapp_planning_source import submitted_profile_projection
from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError


class ConfirmedMiniappSourceTest(unittest.IsolatedAsyncioTestCase):
    """自述读取只补没有专业快照的本人建档来源。"""

    async def test_confirmed_link_without_snapshot_uses_reported_path(self):
        """修复原实现永远等待外部专业快照的问题。"""
        link = SimpleNamespace(source_kind="self_confirmed")
        session = SimpleNamespace(get=AsyncMock(return_value=link))
        repo = HealthQualityRepository(session)
        repo.profile = AsyncMock(return_value=None)
        result = {"status": "not_ready", "reason": "profile_coding_rules_unavailable"}
        with patch(
            "yuxi.services.miniapp_planning_source.submitted_profile_projection", AsyncMock(return_value=result)
        ) as read:
            self.assertIs(await repo.profile_projection("member"), result)
            read.assert_awaited_once_with(session, link)

    async def test_existing_unready_professional_snapshot_never_falls_back(self):
        """专业来源撤回或失效仍拒绝，不降级为自述。"""
        session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(source_kind="self_confirmed")))
        repo = HealthQualityRepository(session)
        repo.profile = AsyncMock(return_value=object())
        result = {"status": "not_ready", "reason": "revoked"}
        with (
            patch("yuxi.repositories.health_quality_repository.external_projection", return_value=result),
            patch("yuxi.services.miniapp_planning_source.submitted_profile_projection", AsyncMock()) as read,
        ):
            self.assertIs(await repo.profile_projection("member"), result)
            read.assert_not_awaited()

    async def test_unknown_source_kind_is_not_converted(self):
        """未知来源不按本人确认处理。"""
        session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(source_kind="unknown")))
        repo = HealthQualityRepository(session)
        repo.profile = AsyncMock(return_value=None)
        with patch("yuxi.services.miniapp_planning_source.submitted_profile_projection", AsyncMock()) as read:
            result = await repo.profile_projection("member")
            self.assertEqual(result["reason"], "not_delivered")
            read.assert_not_awaited()

    async def test_existing_miniapp_source_keeps_original_path(self):
        """原自述来源不被本次兼容分支重定向。"""
        link = SimpleNamespace(source_kind="miniapp_reported")
        session = SimpleNamespace(get=AsyncMock(return_value=link))
        repo = HealthQualityRepository(session)
        repo.profile = AsyncMock()
        with patch(
            "yuxi.services.miniapp_planning_source.submitted_profile_projection", AsyncMock(return_value={})
        ) as read:
            await repo.profile_projection("member")
            read.assert_awaited_once_with(session, link)
            repo.profile.assert_not_awaited()

    async def test_unconfirmed_source_is_rejected_before_reading_rules(self):
        """本人确认不能由来源关联或规则配置代替。"""
        session = SimpleNamespace(scalar=AsyncMock())
        link = SimpleNamespace(source_kind="self_confirmed", member_id="member")
        with patch(
            "yuxi.repositories.health_family_profile_repository.HealthFamilyProfileRepository.confirmed_source",
            AsyncMock(side_effect=HealthVisionError("family_profile_unconfirmed", "尚未确认", 409)),
        ):
            result = await submitted_profile_projection(session, link)
            self.assertEqual(result["reason"], "family_profile_unconfirmed")
            self.assertEqual(result["status"], "not_ready")
            self.assertIsNone(result["payload"])
            session.scalar.assert_not_awaited()

    async def test_incomplete_reported_profile_is_rejected(self):
        """未完成小程序建档的历史档案不因身份关联绕过完整性。"""
        await self.check_reported_source(complete=False)

    async def test_missing_rules_preserve_real_source_identity_but_not_safety_readiness(self):
        """没有规则时只返回真实版本摘要，不构造专业payload或证明。"""
        await self.check_reported_source(complete=True)

    async def check_reported_source(self, *, complete):
        """装配自述读取的权限和确认依赖，不伪造任何已批准规则。"""
        link = SimpleNamespace(
            source_kind="self_confirmed",
            member_id="health",
            family_id="family",
            source_member_id="member",
            actor_uid="owner",
        )
        member = SimpleNamespace(
            id="member", is_active=True, subject_uid="owner", version=3, profile={"dietary_details": {"cuisines": []}}
        )
        session = SimpleNamespace(scalar=AsyncMock(return_value=None))
        with (
            patch(
                "yuxi.repositories.health_family_profile_repository.HealthFamilyProfileRepository.confirmed_source",
                AsyncMock(),
            ),
            patch("yuxi.services.miniapp_planning_source.FamilyRepository") as repository,
            patch(
                "yuxi.services.miniapp_planning_source.authorized_fields",
                return_value={"birth_date", "dietary_details"},
            ),
            patch("yuxi.services.miniapp_profile_types.miniapp_onboarding_ready", return_value=complete),
        ):
            repository.return_value.get_family = AsyncMock(return_value=object())
            repository.return_value.member = AsyncMock(return_value=member)
            result = await submitted_profile_projection(session, link)
            self.assertEqual((result["id"], result["version"]), (member.id, member.version))
            self.assertEqual(result["content_hash"], input_fingerprint(member.profile))
            self.assertEqual(result["source_kind"], "user_reported")
            self.assertEqual(
                result["reason"], "profile_coding_rules_unavailable" if complete else "family_profile_incomplete"
            )
            if not complete:
                session.scalar.assert_not_awaited()
            self.assertEqual(result["status"], "not_ready")
            self.assertIsNone(result["payload"])
            self.assertIsNone(result["attestation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

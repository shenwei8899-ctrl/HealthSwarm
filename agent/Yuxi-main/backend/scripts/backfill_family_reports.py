"""为有效家庭档案补齐报告关联；默认只统计，不调用模型或修改 AI 同意。"""

import argparse
import asyncio
import json

from sqlalchemy import select

from yuxi.services.family_service import FamilyService
from yuxi.services.miniapp_report_service import ensure_member_reports
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import FamilyArchive
from yuxi.storage.postgres.models_health import HealthFamilyProfileLink


async def main(apply):
    """逐家庭持有原有家庭锁；重复执行复用原成员及报告。"""
    pg_manager.initialize()
    try:
        await pg_manager.require_current_schema()
        async with pg_manager.get_async_session_context() as db:
            families = list((await db.execute(select(FamilyArchive.id, FamilyArchive.owner_uid))).all())
        counts = {"families": 0, "members": 0, "missing_links": 0, "apply": apply}
        for fid, uid in families:
            async with pg_manager.get_async_session_context() as db:
                service = FamilyService(db, uid)
                family = await service.repo.get_family(fid, uid)
                if family is None:
                    continue
                counts["families"] += 1
                for member in await service.repo.members(fid):
                    if not member.is_active:
                        continue
                    counts["members"] += 1
                    link = await db.scalar(
                        select(HealthFamilyProfileLink).where(HealthFamilyProfileLink.source_member_id == member.id)
                    )
                    counts["missing_links"] += link is None
                    if apply:
                        await ensure_member_reports(service, family, member)
        print(json.dumps(counts))
    finally:
        await pg_manager.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="实际补齐关联和普通报告权限")
    asyncio.run(main(parser.parse_args().apply))

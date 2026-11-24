"""计划浏览投影与按日校验回执，不载入整份生成检查点。"""

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from yuxi.repositories.exclusive_plan_repository import ExclusivePlanRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.models_health import HealthExclusiveDayValidation, HealthRecipeTranslation
from yuxi.storage.postgres.models_knowledge import KnowledgeChunk, KnowledgeFile


class ExclusivePlanBrowseRepository:
    """当前账号和家庭绑定所有读取，回执不拥有计划内容。"""

    def __init__(self, session, uid, fid):
        """使用调用方的事务边界。"""
        self.session, self.uid, self.fid = session, uid, fid

    async def header(self, gid, tier):
        """仅投影目录、来源身份与内容摘要，不返回原谱和商品目录。"""
        await ExclusivePlanRepository(self.session, self.uid, self.fid).context()
        result = await self.session.execute(
            text("""
            SELECT id, status, policy, selection, basis_hash,
              (SELECT jsonb_agg(jsonb_build_object(
                'day_no', e->'day'->'day_no', 'plan_date', e->'day'->'plan_date',
                'content_version', encode(sha256(convert_to(e::text, 'UTF8')), 'hex'),
                'sources', (SELECT jsonb_agg(d->'source')
                  FROM jsonb_array_elements(e->'meals') m,
                       jsonb_array_elements(m->'dishes') d)
              ) ORDER BY (e->'day'->>'day_no')::int)
              FROM jsonb_array_elements(progress->'tiers'->:tier) e) AS days
            FROM health_exclusive_plan_group
            WHERE actor_uid=:uid AND family_id=:fid AND id=:gid
        """),
            dict(uid=self.uid, fid=self.fid, gid=gid, tier=tier),
        )
        row = result.mappings().first()
        if row is None:
            raise HealthVisionError("not_found", "计划不存在或无权读取", 404)
        return dict(row)

    async def day(self, gid, tier, number):
        """只投影所选日，不能依赖客户端传入菜单。"""
        row = await self.session.execute(
            text("""
            SELECT progress->'tiers'->CAST(:tier AS text)->CAST(:position AS integer) AS entry
            FROM health_exclusive_plan_group
            WHERE actor_uid=:uid AND family_id=:fid AND id=:gid
        """),
            dict(uid=self.uid, fid=self.fid, gid=gid, tier=tier, position=number - 1),
        )
        entry = row.scalar_one_or_none()
        if not entry or entry.get("day", {}).get("day_no") != number:
            raise HealthVisionError("not_found", "计划日期不存在", 404)
        return entry

    async def translations(self, keys):
        """展示译文按来源键一次取齐，缺失仍由服务保留原谱或不可展示状态。"""
        return {
            r.id: r
            for r in (
                await self.session.scalars(select(HealthRecipeTranslation).where(HealthRecipeTranslation.id.in_(keys)))
            ).all()
        }

    async def summary(self, gid=None):
        """列表只投影三档已存小计，不加载菜单原文或商品目录。"""
        await ExclusivePlanRepository(self.session, self.uid, self.fid).context()
        result = await self.session.execute(
            text("""
            SELECT id, status, policy, selection, basis_hash, updated_at,
              (SELECT jsonb_object_agg(t.key, (SELECT jsonb_agg(jsonb_build_object(
                'day', e->'day', 'procurement', jsonb_build_object(
                  'pricing', e->'procurement'->'pricing',
                  'purchase_gaps', COALESCE(e->'procurement'->'purchase_gaps', '[]'::jsonb)
                ))) FROM jsonb_array_elements(t.value) e))
              FROM jsonb_each(COALESCE(progress->'tiers', '{}'::jsonb)) t) AS tiers,
              progress->'error' AS error
            FROM health_exclusive_plan_group
            WHERE actor_uid=:uid AND family_id=:fid
              AND (CAST(:gid AS varchar) IS NULL OR id=CAST(:gid AS varchar))
            ORDER BY created_at DESC LIMIT 1
        """),
            dict(uid=self.uid, fid=self.fid, gid=gid),
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def sources(self, file_ids, kb_ids):
        """两个批量查询取齐文件和有序分片，禁止同一会话并发查询。"""
        files = list(
            (
                await self.session.scalars(
                    select(KnowledgeFile).where(KnowledgeFile.file_id.in_(file_ids), KnowledgeFile.kb_id.in_(kb_ids))
                )
            ).all()
        )
        chunks = list(
            (
                await self.session.scalars(
                    select(KnowledgeChunk)
                    .where(KnowledgeChunk.file_id.in_(file_ids), KnowledgeChunk.kb_id.in_(kb_ids))
                    .order_by(KnowledgeChunk.file_id, KnowledgeChunk.chunk_index, KnowledgeChunk.id)
                )
            ).all()
        )
        return files, chunks

    async def receipt(self, gid, tier, number):
        """只读当前计划日期的最后一次通过记录。"""
        return await self.session.get(HealthExclusiveDayValidation, (gid, tier, number))

    async def verified(self, gid, tier, number, version):
        """只在完整校验通过后记录版本，不向 progress 回写浏览缓存。"""
        await self.session.execute(
            insert(HealthExclusiveDayValidation)
            .values(
                group_id=gid,
                tier=tier,
                day_no=number,
                version=version,
            )
            .on_conflict_do_update(
                index_elements=["group_id", "tier", "day_no"],
                set_={"version": version},
            )
        )

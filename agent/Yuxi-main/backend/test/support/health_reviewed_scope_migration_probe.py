"""本轮独立PG槽位23升级24的合成旧事实保存与重复迁移核对。"""

import argparse
import asyncio
import hashlib
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import delete, text

from yuxi.repositories.health_evidence_repository import HealthEvidenceRepository
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.storage.postgres.manager import HEALTH_SCHEMA_VERSION, pg_manager
from yuxi.storage.postgres.models_business import AgentRun, Conversation, Message, Project, User
from yuxi.storage.postgres.models_health import (
    FamilyMember,
    HealthConsultation,
    HealthGrant,
    NutritionEvidence,
    NutritionEvidenceCitation,
)
from yuxi.utils.datetime_utils import utc_now_naive

OUTPUT = Path("test/.tmp/health-reviewed-scope")
SNAPSHOT = OUTPUT / "migration23.json"


async def main(mode):
    """seed仅接受真实23；verify仅接受真实24并回读旧数据与范围边界。"""
    pg_manager.initialize()
    try:
        async with pg_manager.get_async_session_context() as session:
            assert await session.scalar(text("SELECT current_database()")) == "health_consultation_e2e"
        OUTPUT.mkdir(parents=True, exist_ok=True)
        if mode == "seed":
            await seed_legacy()
        else:
            await verify_legacy(mode)
    finally:
        await pg_manager.close()


async def seed_legacy():
    """先持久化旧正文及引用，版本与缺列从实际PG断言。"""
    assert (await pg_manager.get_schema_versions())["health"] == 23
    uid = f"pytest_health_scope_legacy_{uuid4().hex}"
    member, project, thread, run, request, source, citation = (str(uuid4()) for _ in range(7))
    body = f"legacy_scope_{uuid4().hex} 合成旧科普，仅协议保存验收。"
    now = utc_now_naive()
    async with pg_manager.get_async_session_context() as session:
        columns = list(
            await session.scalars(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='nutrition_evidence'")
            )
        )
        assert "reviewed_scope" not in columns and "scope_hash" not in columns
        session.add(User(username=uid, uid=uid, role="user", password_hash="synthetic-not-a-login"))
        await session.flush()
        session.add(
            Project(
                id=project,
                uid=uid,
                selection_status="implicit",
                directory_mode="managed",
                workdir_path=f"projects/{project}",
                status="active",
            )
        )
        session.add(FamilyMember(id=member, owner_uid=uid, display_name="合成迁移本人", relationship_label="本人"))
        await session.flush()
        conv = Conversation(thread_id=thread, uid=uid, agent_id="health-consultation", project_id=project)
        session.add(conv)
        await session.flush()
        session.add(HealthGrant(member_id=member, actor_uid=uid, scopes=["profile_view", "ai_use"]))
        session.add(HealthConsultation(conversation_id=conv.id, member_id=member, actor_uid=uid, request_id=request))
        record = AgentRun(
            id=run,
            conversation_thread_id=thread,
            runtime_scope_id=thread,
            agent_slug="health-consultation",
            uid=uid,
            status="completed",
            request_id=request,
            conversation_id=conv.id,
            started_at=now,
            finished_at=now,
            runtime_cleanup_pending=False,
        )
        session.add(record)
        session.add(
            NutritionEvidence(
                id=source,
                source_ref=f"synthetic://scope-migration/{source}",
                source_version="legacy-v1",
                title="合成旧通用资料",
                content=body,
                content_hash=hashlib.sha256(body.encode()).hexdigest(),
                review_ref=f"synthetic://scope-migration-review/{source}",
                reviewed_by="synthetic-reviewer",
                reviewed_at=now - timedelta(days=1),
                valid_until=now + timedelta(days=1),
                published_by=uid,
            )
        )
        await session.flush()
        session.add(
            NutritionEvidenceCitation(
                id=citation,
                evidence_id=source,
                run_id=run,
                conversation_id=conv.id,
                member_id=member,
                actor_uid=uid,
                content_hash=hashlib.sha256(body.encode()).hexdigest(),
            )
        )
        message = Message(
            conversation_id=conv.id,
            role="assistant",
            content=f"合成旧正文 [证据:{citation}]",
            run_id=run,
            request_id=request,
        )
        session.add(message)
        await session.flush()
        record.output_message_id = message.id
        identities = {
            "uid": uid,
            "member": member,
            "project": project,
            "thread": thread,
            "run": run,
            "source": source,
            "citation": citation,
            "conversation": conv.id,
            "message": message.id,
        }
    rows = await read_legacy_rows(identities)
    SNAPSHOT.write_text(
        json.dumps({"identities": identities, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "health_version": 23,
                "preserved_tables": list(rows),
                "counts": {key: len(value) for key, value in rows.items()},
            }
        )
    )


async def verify_legacy(mode):
    """新列为NULL且旧列逐字节相等；仅普通咨询继承旧通用审核。"""
    assert (await pg_manager.get_schema_versions())["health"] == HEALTH_SCHEMA_VERSION
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    identities = snapshot["identities"]
    rows = await read_legacy_rows(identities)
    for table, old in snapshot["rows"].items():
        current = [{key: row[key] for key in old[index]} for index, row in enumerate(rows[table])]
        assert current == old, f"旧列改变：{table}"
    async with pg_manager.get_async_session_context() as session:
        source = await session.get(NutritionEvidence, identities["source"])
        citation = await session.get(NutritionEvidenceCitation, identities["citation"])
        assert source.reviewed_scope is None and source.scope_hash is None and citation.scope_hash is None
        repo = HealthEvidenceRepository(session)
        binding = SimpleNamespace(conversation_id=identities["conversation"], member_id=identities["member"])
        adopted = await repo.validate_citations(
            [citation.id], binding, identities["uid"], agent_slug="health-consultation", run_id=identities["run"]
        )
        assert len(adopted) == 1 and adopted[citation.id]["content"] == source.content
        for slug in ("health-blood-glucose", "health-blood-lipids", "health-blood-pressure"):
            try:
                await repo.validate_citations(
                    [citation.id], binding, identities["uid"], agent_slug=slug, run_id=identities["run"]
                )
            except HealthVisionError as exc:
                assert exc.code == "citation_invalid"
            else:
                raise AssertionError("旧普通引用被错误扩大到指标角色")
    receipt = {
        "health_version": HEALTH_SCHEMA_VERSION,
        "phase": mode,
        "old_columns_equal": True,
        "legacy_scope_null": True,
        "ordinary_citation_retained": True,
        "indicator_citations_rejected": 3,
        "counts": {key: len(value) for key, value in rows.items()},
    }
    (OUTPUT / f"migration-{mode}.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt))
    if mode == "cleanup":
        async with pg_manager.get_async_session_context() as session:
            for model, condition in (
                (NutritionEvidenceCitation, NutritionEvidenceCitation.actor_uid == identities["uid"]),
                (NutritionEvidence, NutritionEvidence.published_by == identities["uid"]),
                (Message, Message.run_id == identities["run"]),
                (AgentRun, AgentRun.id == identities["run"]),
                (HealthConsultation, HealthConsultation.actor_uid == identities["uid"]),
                (HealthGrant, HealthGrant.actor_uid == identities["uid"]),
                (FamilyMember, FamilyMember.owner_uid == identities["uid"]),
                (Conversation, Conversation.uid == identities["uid"]),
                (Project, Project.uid == identities["uid"]),
                (User, User.uid == identities["uid"]),
            ):
                await session.execute(delete(model).where(condition))
        clean = await read_legacy_rows(identities)
        assert all(not value for value in clean.values())
        (OUTPUT / "migration-cleanup-counts.json").write_text(
            json.dumps({key: len(value) for key, value in clean.items()}), encoding="utf-8"
        )


async def read_legacy_rows(identities):
    """SELECT to_jsonb只观察具体fixture，不从当前模型生成迁移oracle。"""
    rows = {}
    async with pg_manager.get_async_session_context() as session:
        for table, column, key in (
            ("users", "uid", "uid"),
            ("projects", "id", "project"),
            ("conversations", "id", "conversation"),
            ("family_member", "id", "member"),
            ("health_grant", "actor_uid", "uid"),
            ("health_consultation", "actor_uid", "uid"),
            ("agent_runs", "id", "run"),
            ("messages", "id", "message"),
            ("nutrition_evidence", "id", "source"),
            ("nutrition_evidence_citation", "id", "citation"),
        ):
            rows[table] = list(
                await session.scalars(
                    text(f"SELECT to_jsonb(t) FROM {table} t WHERE {column}=:identity"), {"identity": identities[key]}
                )
            )
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("seed", "first", "repeat", "cleanup"))
    asyncio.run(main(parser.parse_args().mode))

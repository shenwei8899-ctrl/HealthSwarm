"""将已经发布的每日餐单归并到家庭维度，保留其他历史记录。"""

from sqlalchemy import text


async def upgrade_shared_daily_meal_plan(manager):
    """每个家庭日期保留最近发布的餐单，并使切换前的待处理版本失效。"""
    async with manager.async_engine.begin() as connection:
        for statement in (
            "ALTER TABLE health_daily_meal_plan ADD COLUMN IF NOT EXISTS is_shared BOOLEAN NOT NULL DEFAULT false",
            "ALTER TABLE health_daily_meal_plan DROP CONSTRAINT IF EXISTS uq_health_daily_meal_plan",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_shared_daily_meal_plan "
            "ON health_daily_meal_plan (family_id, plan_date) WHERE is_shared",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_legacy_daily_meal_plan "
            "ON health_daily_meal_plan (actor_uid, family_id, plan_date) WHERE NOT is_shared",
            """WITH ranked AS (
                SELECT old.id,
                       row_number() OVER (
                           PARTITION BY old.family_id, old.plan_date
                           ORDER BY (old.version > 0 AND old.meal_sources <> '{}'::jsonb) DESC,
                                    old.updated_at DESC, old.id DESC
                       ) AS position,
                       max(old.version) OVER (PARTITION BY old.family_id, old.plan_date) AS last_version
                FROM health_daily_meal_plan old
                WHERE NOT EXISTS (
                    SELECT 1 FROM health_daily_meal_plan shared
                    WHERE shared.family_id = old.family_id AND shared.plan_date = old.plan_date AND shared.is_shared
                )
            )
            UPDATE health_daily_meal_plan plan
            SET is_shared = true, version = ranked.last_version + 1, pending = '{}'::jsonb
            FROM ranked WHERE plan.id = ranked.id AND ranked.position = 1""",
            """WITH latest_formal AS (
                SELECT DISTINCT ON (family_id, plan_date)
                       id, actor_uid, family_id, plan_date, snapshot, updated_at
                FROM health_daily_arrangement
                WHERE snapshot->>'status' = 'ready'
                  AND jsonb_typeof(snapshot->'meals') = 'array'
                  AND snapshot->>'version' ~ '^[1-9][0-9]*$'
                ORDER BY family_id, plan_date, updated_at DESC, id DESC
            )
            INSERT INTO health_daily_meal_plan AS plan
                (id, actor_uid, family_id, plan_date, is_shared, version, meal_sources, pending, updated_at)
            SELECT gen_random_uuid()::text, formal.actor_uid, formal.family_id, formal.plan_date, true, 1,
                   refs.meals, '{}'::jsonb, formal.updated_at
            FROM latest_formal formal
            CROSS JOIN LATERAL (
                SELECT jsonb_object_agg(meal->>'type', jsonb_build_object(
                    'kind', 'formal', 'id', formal.id, 'version', (formal.snapshot->>'version')::integer
                )) AS meals
                FROM jsonb_array_elements(formal.snapshot->'meals') meal
                WHERE meal->>'type' IN ('breakfast', 'lunch', 'dinner')
            ) refs
            WHERE refs.meals IS NOT NULL
            ON CONFLICT (family_id, plan_date) WHERE is_shared DO UPDATE
            SET meal_sources = excluded.meal_sources, version = plan.version + 1, updated_at = excluded.updated_at
            WHERE plan.meal_sources = '{}'::jsonb""",
            """WITH completed AS (
                SELECT p.id, p.actor_uid, p.selection->>'family_id' AS family_id,
                       p.selection->>'plan_date' AS day, p.snapshot, r.finished_at, r.created_at
                FROM health_initial_plan_preview p
                JOIN agent_runs r ON r.id = p.run_id AND r.uid = p.actor_uid AND r.status = 'completed'
                JOIN messages m ON m.id = r.output_message_id AND m.run_id = r.id
                    AND m.conversation_id = r.conversation_id AND m.request_id = r.request_id
                    AND m.role = 'assistant' AND m.delivery_status = 'complete'
                WHERE p.selection->>'mode' = 'reference'
                  AND nullif(p.selection->>'family_id', '') IS NOT NULL
                  AND (p.selection->>'plan_date') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                  AND pg_input_is_valid(p.selection->>'plan_date', 'date')
                  AND CASE WHEN m.content IS JSON OBJECT THEN m.content::jsonb->>'preview_id' = p.id ELSE false END
            ), candidates AS (
                SELECT DISTINCT ON (p.family_id, p.day)
                    p.family_id, p.day, p.actor_uid, p.finished_at, p.created_at, refs.meals
                FROM completed p
                CROSS JOIN LATERAL (
                    SELECT jsonb_object_agg(meal->>'meal_type', jsonb_build_object('kind', 'reference', 'id', p.id)) AS meals
                    FROM jsonb_array_elements(
                        CASE WHEN jsonb_typeof(p.snapshot->'meals') = 'array'
                             THEN p.snapshot->'meals' ELSE '[]'::jsonb END
                    ) meal
                    WHERE meal->>'meal_type' IN ('breakfast', 'lunch', 'dinner')
                ) refs
                WHERE refs.meals IS NOT NULL
                ORDER BY p.family_id, p.day, p.finished_at DESC NULLS LAST, p.created_at DESC, p.id DESC
            )
            INSERT INTO health_daily_meal_plan AS plan
                (id, actor_uid, family_id, plan_date, is_shared, version, meal_sources, pending, updated_at)
            SELECT gen_random_uuid()::text, actor_uid, family_id, day::date, true, 1, meals, '{}'::jsonb,
                   coalesce(finished_at, created_at)
            FROM candidates
            ON CONFLICT (family_id, plan_date) WHERE is_shared DO UPDATE
            SET meal_sources = excluded.meal_sources, version = plan.version + 1, updated_at = excluded.updated_at
            WHERE plan.meal_sources = '{}'::jsonb""",
        ):
            await connection.execute(text(statement))

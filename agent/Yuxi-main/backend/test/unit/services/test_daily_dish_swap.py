"""单菜候选不依赖营养热量，类型与硬限制决定资格。"""

from collections import Counter
from unittest.mock import AsyncMock, Mock

import pytest

from yuxi.services.daily_dish_swap_service import rank_candidates, recipe_kind, explicit_minutes, require_recipe_quotes
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.reference_recipe_index import prepare_reference_documents


def documents(names):
    """可完整解析的合成原文。"""
    return prepare_reference_documents(
        [
            (
                str(i),
                "kb",
                "家常菜谱_" + name + ".md",
                "hash",
                "chunk" + str(i),
                f"# {name}\n## 食材\n- 菠菜 100克\n## 做法\n- 将食材炒熟。\n",
            )
            for i, name in enumerate(names)
        ]
    )


def policy():
    """空家庭历史不会改变候选资格。"""
    return {"excluded": set(), "recent": Counter(), "popular": Counter(), "preferences": []}


def test_same_type_without_nutrition_and_no_full_meal_regeneration():
    """没有营养字段仍推荐素菜，汤和主食不混入。"""
    found = rank_candidates(
        {"name": "清炒菠菜"}, documents(["荷塘月色", "菠菜汤", "米饭", "炒西兰花"]), [], [], policy()
    )
    assert {c["dish"]["name"] for c in found} == {"荷塘月色", "炒西兰花"}
    assert all(c["dish"]["nutrition_status"] == "not_calculated" for c in found)


def test_restriction_and_occupied_dishes_are_excluded():
    """明确限制的候选和已排菜品均不推荐。"""
    rules = policy()
    rules["excluded"].add("name:炒西兰花")
    assert rank_candidates({"name": "菠菜"}, documents(["炒西兰花"]), [], [], rules) == []
    assert (
        rank_candidates({"name": "鸡肉"}, documents(["牛肉", "清蒸鸡肉"]), [], ["牛肉"], policy())[0]["dish"]["name"]
        == "清蒸鸡肉"
    )
    with pytest.raises(HealthVisionError, match=".*"):
        rank_candidates({"name": "菠菜"}, documents(["炒西兰花"]), [], ["低钾饮食"], policy())


def test_unknown_type_and_time_stay_unknown():
    """不靠缺失字段编造候选类型或总时间。"""
    assert recipe_kind("神秘菜", []) is None
    assert rank_candidates({"name": "神秘菜"}, documents(["炒西兰花"]), [], [], policy()) == []
    assert explicit_minutes("炒5分钟，炖10分钟") is None
    assert explicit_minutes("制作时间：20分钟") == 20
    assert explicit_minutes("Total time: 35 minutes") == 35
    assert recipe_kind("荷塘月色", ["虾仁 50克", "莲藕 100克"]) == "荤菜"
    assert recipe_kind("荷塘月色", ["莲藕 100克"]) == "素菜"
    assert recipe_kind("菠菜汤", ["鸡肉 100克"]) == "汤羹"


def test_product_coverage_precedes_other_preferences():
    """可购买食材参与排序，不根据缺失热量制造分数。"""
    docs = documents(["炒西兰花", "清炒菠菜"])
    docs[0]["parsed"] = type(docs[0]["parsed"])("炒西兰花", ("西兰花 100克",), ("炒熟",))
    product = {
        "product_id": "spinach",
        "product_name": "菠菜",
        "skus": [{"sku_id": "s", "sale_status": "available", "available_quantity": 5, "price_cent": 600}],
    }
    found = rank_candidates({"name": "菠菜"}, docs, [product], [], policy())
    assert found[0]["dish"]["name"] == "清炒菠菜"
    assert found[0]["snapshot"]["product_matches"][0]["ingredient_refs"] == ["菠菜 100克"]


def test_full_recipe_cannot_silently_add_an_ingredient_after_ranking():
    """分片可解析不代表完整原文中没有额外食材。"""
    doc = documents(["清炒菠菜"])[0]
    dish = {"name": "清炒菠菜", "ingredients": ["菠菜 100克"], "steps": ["将食材炒熟。"]}
    require_recipe_quotes(dish, doc)
    changed = {**doc, "content": doc["content"].replace("菠菜 100克", "菠菜 100克\n- 花生 10克")}
    with pytest.raises(HealthVisionError) as failure:
        require_recipe_quotes(dish, changed)
    assert failure.value.code == "swap_recipe_changed"


def test_plain_staple_is_excluded_from_replacement_ranking_and_readback():
    """纯米饭不可替代完整主食；完整原文回验也拒绝历史替换。"""
    docs = prepare_reference_documents(
        [
            ("rice", "kb", "米饭.md", "hash", "chunk", "# 米饭\n## 食材\n- 大米 100克\n## 做法\n- 煮熟。\n"),
            (
                "fried",
                "kb",
                "蛋炒饭.md",
                "hash",
                "chunk2",
                "# 蛋炒饭\n## 食材\n- 大米 100克\n- 鸡蛋 1个\n## 做法\n- 炒熟。\n",
            ),
        ]
    )
    found = rank_candidates({"name": "蔬菜炒饭"}, docs, [], [], policy())
    assert [item["dish"]["name"] for item in found] == ["蛋炒饭"]
    dish = {"name": "米饭", "ingredients": ["大米 100克"], "steps": ["煮熟。"]}
    with pytest.raises(HealthVisionError, match="swap_recipe_changed"):
        require_recipe_quotes(dish, docs[0])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "restriction,count,malformed,duplicates",
    [
        ([], 3, False, False),
        (["牛肉"], 3, False, False),
        (["低钾饮食"], 0, False, False),
        ([], 3, True, False),
        ([], 3, False, True),
        ([], 3, True, True),
        (["牛肉"], 3, True, True),
    ],
)
async def test_candidate_batch_uses_actual_meal_members_and_caps_three(
    monkeypatch,
    restriction,
    count,
    malformed,
    duplicates,
):
    """本餐名单独立传给授权核对；未知医嘱不以忽略限制换取候选。"""
    from yuxi.services import daily_dish_swap_service as swap
    from yuxi.services import reference_recipe_index as index
    from yuxi.services import reference_meal_plan_service as reference
    from yuxi.services import daily_commerce_service as commerce
    from yuxi.repositories import reference_variety_repository as history

    docs = documents(
        ["清炒菠菜", "清炒菠菜", "炒西兰花", "炒白菜", "炒豆腐"]
        if duplicates
        else ["清炒菠菜", "炒西兰花", "炒白菜", "炒豆腐"]
    )

    reads = []

    async def full_document(_, fid, cid):
        """模拟一个完整原文与索引分片不一致的候选。"""
        reads.append((fid, cid))
        found = next({**d["source"], **d} for d in docs if d["source"]["file_id"] == fid)
        if malformed and fid == "0":
            extra = "牛肉" if restriction == ["牛肉"] else "花生"
            found["content"] = found["content"].replace("菠菜 100克", f"菠菜 100克\n- {extra} 10克")
        return found

    context = AsyncMock(
        return_value={
            "members": [{"id": "lunch-member", "avoidances": []}],
            "memory_restrictions": restriction,
            "selection": {"family_id": "family", "plan_date": "2026-11-16"},
            "sources": {},
        }
    )
    monkeypatch.setattr(swap, "meal_context", context)
    swap.prepared_swap_documents.cache_clear()
    monkeypatch.setattr(index, "reference_recipe_rows", AsyncMock(return_value=[]))
    monkeypatch.setattr(index, "prepare_reference_documents", lambda _, **kwargs: docs)
    monkeypatch.setattr(commerce, "current_product_catalog", AsyncMock(return_value={"items": []}))
    monkeypatch.setattr(history, "reference_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        reference,
        "recipe_document",
        AsyncMock(side_effect=full_document),
    )
    monkeypatch.setattr(reference, "reference_meal_media", AsyncMock(side_effect=lambda _, m: m))
    original = {"name": "荷塘月色", "origin": {"source": {"kind": "reference", "id": "source"}}}
    members = [{"id": "lunch-member", "name": "午餐成员"}]
    plan = {
        "date": "2026-11-16",
        "version": 1,
        "meals": [
            {"meal_type": "lunch", "members": members, "meal": {"dishes": [original, {**original, "name": "蒜蓉茄子"}]}}
        ],
    }
    result = await swap.plan_candidates(None, "actor", "family", plan)
    assert context.call_args.args[-1] == members
    assert len(result[0]["dishes"]) == 2
    assert [c["candidate_id"] for c in result[0]["dishes"][0]["candidates"]] != [
        c["candidate_id"] for c in result[0]["dishes"][1]["candidates"]
    ] or count == 0
    assert [c["dish"]["file_id"] for c in result[0]["dishes"][0]["candidates"]] == [
        c["dish"]["file_id"] for c in result[0]["dishes"][1]["candidates"]
    ]
    assert len(result[0]["dishes"][0]["candidates"]) == count
    assert len(reads) == len(set(reads))
    reference.reference_meal_media.assert_not_awaited()
    chosen = [c["dish"] for c in result[0]["dishes"][0]["candidates"]]
    assert len({d["name"] for d in chosen}) == count
    if duplicates:
        assert [d["file_id"] for d in chosen] == (["1", "2", "3"] if malformed else ["0", "2", "3"])
    if malformed:
        assert "0" not in [d["file_id"] for d in chosen]


@pytest.mark.asyncio
async def test_meal_context_binds_memory_versions_and_rechecks_saved_replacement(monkeypatch):
    """新增或撤回限制改变来源依据，旧替换菜不能继续按保存时限制回读。"""
    from copy import deepcopy
    from yuxi.services import daily_dish_swap_service as swap
    from yuxi.services import health_memory_context_service as memory
    from yuxi.services import reference_meal_plan_service as reference
    from yuxi.repositories.family_repository import FamilyRepository

    current = {
        "sources": {"family_id": "family", "members": {"member": {"health_member_id": "health"}}},
        "members": [{"id": "member", "allergens": [], "avoidances": []}],
    }
    monkeypatch.setattr(FamilyRepository, "linked_health_member", AsyncMock(return_value="health"))
    monkeypatch.setattr(
        reference, "reference_context_in_session", AsyncMock(side_effect=lambda *a, **k: deepcopy(current))
    )
    facts = [{"id": "fact", "version": 1, "restriction": "牛肉"}]
    monkeypatch.setattr(memory, "account_plan_restrictions", AsyncMock(side_effect=lambda *a: deepcopy(facts)))
    members = [{"id": "member"}]
    context = await swap.meal_context(None, "actor", "family", "2026-11-16", "lunch", members)
    assert context["memory_restrictions"] == ["牛肉"]
    saved = {"context_sources": deepcopy(context["sources"])}
    monkeypatch.setattr(swap, "read_origin", AsyncMock(return_value=(None, None, members, None)))
    facts.clear()
    origin = {"anchor": {}, "actor_uid": "actor", "date": "2026-11-16", "meal_type": "lunch", "snapshot": saved}
    with pytest.raises(HealthVisionError, match="dish_members_changed"):
        await swap.read_replacement(None, "actor", "family", origin)
    assert context["memory_restrictions"] == ["牛肉"]


@pytest.mark.asyncio
async def test_account_restriction_filters_beef_candidate_with_unrestricted_profile(monkeypatch):
    """候选执行入口合并记忆限制，而不是只测试排序函数。"""
    from yuxi.services import daily_dish_swap_service as swap
    from yuxi.services import reference_recipe_index as index
    from yuxi.services import reference_meal_plan_service as reference
    from yuxi.services import daily_commerce_service as commerce
    from yuxi.repositories import reference_variety_repository as history

    docs = documents(["清蒸鸡肉", "红烧牛肉"])
    monkeypatch.setattr(
        swap,
        "meal_context",
        AsyncMock(
            return_value={
                "members": [{"id": "member", "avoidances": []}],
                "memory_restrictions": ["牛肉"],
                "selection": {"family_id": "family", "plan_date": "2026-11-16"},
                "sources": {},
            }
        ),
    )
    swap.prepared_swap_documents.cache_clear()
    monkeypatch.setattr(index, "reference_recipe_rows", AsyncMock(return_value=[]))
    monkeypatch.setattr(index, "prepare_reference_documents", lambda _, **kwargs: docs)
    monkeypatch.setattr(commerce, "current_product_catalog", AsyncMock(return_value={"items": []}))
    monkeypatch.setattr(history, "reference_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        reference,
        "recipe_document",
        AsyncMock(
            side_effect=lambda _, fid, cid: next({**d["source"], **d} for d in docs if d["source"]["file_id"] == fid)
        ),
    )
    monkeypatch.setattr(reference, "reference_meal_media", AsyncMock(side_effect=lambda _, meal: meal))
    original = {"name": "香煎鸡肉", "origin": {"source": {"kind": "reference", "id": "source"}}}
    result = await swap.plan_candidates(
        None,
        "actor",
        "family",
        {
            "date": "2026-11-16",
            "version": 1,
            "meals": [{"meal_type": "lunch", "members": [{"id": "member"}], "meal": {"dishes": [original]}}],
        },
    )
    assert [item["dish"]["name"] for item in result[0]["dishes"][0]["candidates"]] == ["清蒸鸡肉"]


@pytest.mark.asyncio
async def test_scoped_candidates_skip_other_meals_share_matching_and_never_probe_images(monkeypatch):
    """单菜只核目标成员；公共原文和匹配复用，图片探测不进入读取链路。"""
    from yuxi.services import daily_dish_swap_service as swap
    from yuxi.services import reference_recipe_index as index
    from yuxi.services import reference_meal_plan_service as reference
    from yuxi.services import reference_recipe_presentation as media
    from yuxi.services import reference_recipe_matching as matching
    from yuxi.services import daily_commerce_service as commerce
    from yuxi.repositories import reference_variety_repository as history

    docs = documents(["炒西兰花", "炒白菜", "炒豆腐"])
    original = {"dish_key": "spinach", "name": "清炒菠菜", "origin": {"source": {"kind": "reference", "id": "source"}}}
    plan = {
        "date": "2026-11-28",
        "version": 1,
        "meals": [
            {"meal_type": "breakfast", "members": [{"id": "first"}], "meal": {"dishes": [original]}},
            {"meal_type": "dinner", "members": [{"id": "other"}], "meal": {"dishes": [original]}},
        ],
    }
    swap.prepared_swap_documents.cache_clear()
    monkeypatch.setattr(index, "reference_recipe_rows", AsyncMock(return_value=[]))
    monkeypatch.setattr(index, "prepare_reference_documents", lambda _, **kwargs: docs)
    monkeypatch.setattr(commerce, "current_product_catalog", AsyncMock(return_value={"items": []}))
    monkeypatch.setattr(history, "reference_history", AsyncMock(return_value=[]))
    context = AsyncMock(
        return_value={
            "members": [{"id": "first"}],
            "selection": {"family_id": "family", "plan_date": "2026-11-28"},
            "sources": {},
        }
    )
    monkeypatch.setattr(swap, "meal_context", context)
    monkeypatch.setattr(
        reference,
        "recipe_document",
        AsyncMock(
            side_effect=lambda _, fid, cid: next({**d["source"], **d} for d in docs if d["source"]["file_id"] == fid)
        ),
    )
    monkeypatch.setattr(
        media, "stored_recipe_image", AsyncMock(side_effect=AssertionError("image storage must not be queried"))
    )
    matches = matching.reference_ingredient_matches
    monkeypatch.setattr(matching, "reference_ingredient_matches", count_matches := Mock(wraps=matches))
    result = await swap.plan_candidates(None, "actor", "family", plan, meal_type="breakfast", dish_key_filter="spinach")
    assert [m["meal_type"] for m in result] == ["breakfast"]
    assert context.await_count == 1 and context.call_args.args[-1] == [{"id": "first"}]
    assert count_matches.call_count == 1
    assert len(result[0]["dishes"][0]["candidates"]) == 3
    assert all(
        c["dish"]["image_url"].startswith("/minio/public/recipe-illustrations/")
        for c in result[0]["dishes"][0]["candidates"]
    )
    media.stored_recipe_image.assert_not_awaited()
    with pytest.raises(HealthVisionError, match="swap_target_changed"):
        await swap.plan_candidates(None, "actor", "family", plan, meal_type="breakfast", dish_key_filter="missing")
    with pytest.raises(HealthVisionError, match="swap_target_invalid"):
        await swap.plan_candidates(None, "actor", "family", plan, dish_key_filter="spinach")
    assert context.await_count == 1


def test_public_prepared_recipe_cache_changes_with_content(monkeypatch):
    """相同公开分片只准备一次，原文变化不复用旧结果。"""
    from yuxi.services import daily_dish_swap_service as swap
    from yuxi.services import reference_recipe_index as index
    from unittest.mock import Mock

    swap.prepared_swap_documents.cache_clear()
    prepare = Mock(return_value=[])
    monkeypatch.setattr(index, "prepare_reference_documents", prepare)
    rows = (("file", "kb", "recipe", "hash", "chunk", "first"),)
    swap.prepared_swap_documents(rows)
    swap.prepared_swap_documents(rows)
    assert prepare.call_count == 1
    swap.prepared_swap_documents(((*rows[0][:-1], "changed"),))
    assert prepare.call_count == 2
    swap.prepared_swap_documents.cache_clear()


@pytest.mark.asyncio
async def test_image_deferral_is_scoped_and_does_not_skip_strict_existence_checks(monkeypatch):
    """并行普通读取和生成前严格检查不继承另一个请求的图片延后模式。"""
    import asyncio
    from yuxi.services import reference_recipe_presentation as media

    probe = AsyncMock(return_value={"image_url": "checked"})
    monkeypatch.setattr(media, "stored_recipe_image", probe)
    dish = {"name": "合成菜", "ingredients": [], "steps": [], "source": {}}
    ready = asyncio.Event()

    async def deferred_read():
        with media.defer_recipe_images():
            ready.set()
            await asyncio.sleep(0)
            assert (await media.generated_recipe_image(dish))["image_url"].startswith("/minio/public/")
            assert (await media.generated_recipe_image(dish, strict=True))["image_url"] == "checked"

    async def ordinary_read():
        await ready.wait()
        assert (await media.generated_recipe_image(dish))["image_url"] == "checked"

    await asyncio.gather(deferred_read(), ordinary_read())
    assert probe.await_count == 2
    try:
        with media.defer_recipe_images():
            raise RuntimeError("cancelled")
    except RuntimeError:
        pass
    assert (await media.generated_recipe_image(dish))["image_url"] == "checked"
    assert probe.await_count == 3


@pytest.mark.asyncio
async def test_candidate_entry_defers_images_during_current_plan_read(monkeypatch):
    """从实际候选入口验证前置餐单回读也不访问图片对象存储。"""
    from contextlib import asynccontextmanager
    from yuxi.services import daily_dish_swap_service as swap
    from yuxi.services import daily_meal_plan_service as daily
    from yuxi.services import reference_recipe_presentation as media
    from yuxi.storage.postgres.manager import pg_manager

    @asynccontextmanager
    async def session():
        yield None

    async def read(*args, **kwargs):
        result = await media.generated_recipe_image({"name": "合成菜", "source": {}})
        assert result["image_url"].startswith("/minio/public/")
        return {"version": 3, "meals": []}

    monkeypatch.setattr(swap, "require_today", lambda day: None)
    monkeypatch.setattr(pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(daily, "read_current_plan", read)
    monkeypatch.setattr(media, "stored_recipe_image", AsyncMock(side_effect=AssertionError("must not probe")))
    selected = AsyncMock(return_value=[])
    monkeypatch.setattr(swap, "plan_candidates", selected)
    result = await swap.swap_candidates(
        "actor", "family", "2026-11-28", 3, meal_type="breakfast", dish_key_filter="rice"
    )
    assert result == {"date": "2026-11-28", "version": 3, "meals": [], "needs_regeneration": []}
    assert selected.call_args.kwargs == {"meal_type": "breakfast", "dish_key_filter": "rice"}
    media.stored_recipe_image.assert_not_awaited()

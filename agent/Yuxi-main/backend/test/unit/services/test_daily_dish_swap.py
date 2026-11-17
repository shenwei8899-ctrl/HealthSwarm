"""单菜候选不依赖营养热量，类型与硬限制决定资格。"""

from collections import Counter
from unittest.mock import AsyncMock

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
    "restriction,count,malformed", [([], 3, False), (["牛肉"], 3, False), (["低钾饮食"], 0, False), ([], 3, True)]
)
async def test_candidate_batch_uses_actual_meal_members_and_caps_three(monkeypatch, restriction, count, malformed):
    """本餐名单独立传给授权核对；未知医嘱不以忽略限制换取候选。"""
    from yuxi.services import daily_dish_swap_service as swap
    from yuxi.services import reference_recipe_index as index
    from yuxi.services import reference_meal_plan_service as reference
    from yuxi.services import daily_commerce_service as commerce
    from yuxi.repositories import reference_variety_repository as history

    docs = documents(["清炒菠菜", "炒西兰花", "炒白菜", "炒豆腐"])

    async def full_document(_, fid, cid):
        """模拟一个完整原文与索引分片不一致的候选。"""
        found = next({**d["source"], **d} for d in docs if d["source"]["file_id"] == fid)
        if malformed and fid == "0":
            found["content"] = found["content"].replace("菠菜 100克", "菠菜 100克\n- 花生 10克")
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
    monkeypatch.setattr(index, "reference_recipe_rows", AsyncMock(return_value=[]))
    monkeypatch.setattr(index, "prepare_reference_documents", lambda _: docs)
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
        "meals": [{"meal_type": "lunch", "members": members, "meal": {"dishes": [original]}}],
    }
    result = await swap.plan_candidates(None, "actor", "family", plan)
    assert context.call_args.args[-1] == members
    assert len(result[0]["dishes"][0]["candidates"]) == count
    if malformed:
        assert "清炒菠菜" not in [c["dish"]["name"] for c in result[0]["dishes"][0]["candidates"]]


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
    monkeypatch.setattr(index, "reference_recipe_rows", AsyncMock(return_value=[]))
    monkeypatch.setattr(index, "prepare_reference_documents", lambda _: docs)
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

"""当前餐单中的单菜选择与范围采购；不创建实际饮食记录。"""

import copy
import re
import time
from datetime import date, datetime, timedelta, time as day_time
from decimal import Decimal, ROUND_CEILING
from uuid import uuid4, uuid5, NAMESPACE_URL
from zoneinfo import ZoneInfo

from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.utils.datetime_utils import utc_now_naive


async def add_saved_dish(uid, family_id, day, data):
    """在同一当前计划事务中追加所选菜，重复确认不重复加入。"""
    from yuxi.storage.postgres.manager import pg_manager
    from yuxi.services.daily_meal_plan_service import current_row, legacy_sources, read_current_plan
    from yuxi.storage.postgres.models_health import HealthDailyMealPlan

    if day != datetime.now(ZoneInfo("Asia/Shanghai")).date():
        raise HealthVisionError("dish_date_invalid", "请从今日餐单选择要烹饪的菜", 422)
    async with pg_manager.get_async_session_context() as session:
        row = await current_row(session, uid, family_id, day, lock=True)
        plan = await read_current_plan(uid, family_id, day, session=session)
        target = next((m for m in plan["meals"] if m["meal_type"] == data.meal_type), None)
        if target and any(dish_key(d) == data.dish_key for d in target["meal"]["dishes"]):
            return plan
        if plan["version"] != data.version:
            raise HealthVisionError("daily_plan_version_changed", "餐单已更新，请重新打开后添加", 409)
        source = next((m for m in plan["meals"] if m["meal_type"] == data.source_meal), None)
        dish = next((d for d in (source or {}).get("meal", {}).get("dishes", []) if dish_key(d) == data.dish_key), None)
        if dish is None:
            raise HealthVisionError("dish_source_changed", "餐单已没有这道菜，请重新读取", 409)
        if target and {m["id"] for m in target["members"]} != {m["id"] for m in source["members"]}:
            raise HealthVisionError("dish_members_changed", "两餐就餐成员不同，请先统一本餐成员", 409)
        dishes = (target or {}).get("meal", {}).get("dishes", [])
        if len(dishes) >= 10:
            raise HealthVisionError("meal_dishes_limit", "本餐菜品已满，请先调整餐单", 422)
        refs = dict(row.meal_sources) if row else await legacy_sources(session, uid, family_id, day)
        refs[data.meal_type] = {
            "kind": "selection",
            "id": str(uuid4()),
            "version": plan["version"] + 1,
            "dish_sources": [await freeze_origin(session, d["origin"]) for d in [*dishes, dish]],
            "member_ids": [m["id"] for m in source["members"]],
            "request_id": str(data.client_request_id),
        }
        if row is None:
            row = HealthDailyMealPlan(id=str(uuid4()), actor_uid=uid, family_id=family_id, plan_date=day, pending={})
            session.add(row)
        row.meal_sources, row.version, row.updated_at = refs, plan["version"] + 1, utc_now_naive()
        await session.flush()
        result = await read_current_plan(uid, family_id, day, session=session)
        await session.commit()
        return result


async def scoped_purchase(uid, family_id, day, meal_type, version, keys, *, publish=False):
    """服务端限定菜品范围后装配采购，读取不会发布商品包。"""
    from yuxi.storage.postgres.manager import pg_manager
    from yuxi.services.daily_meal_plan_service import read_current_plan
    from yuxi.services.daily_commerce_service import current_catalog, commerce_request
    from yuxi.services.health_commerce_service import sign_commerce_source

    async with pg_manager.get_async_session_context() as session:
        plan = await read_current_plan(uid, family_id, day, session=session)
        if plan["version"] != version:
            raise HealthVisionError("daily_plan_version_changed", "餐单已更新，请重新打开采购", 409)
        meal = next((m["meal"] for m in plan["meals"] if m["meal_type"] == meal_type), None)
        if not meal or len(keys) != len(set(keys)) or any(k not in {dish_key(d) for d in meal["dishes"]} for k in keys):
            raise HealthVisionError("dish_scope_invalid", "采购菜品不属于本餐，请重新读取", 422)
        dishes = [d for d in meal["dishes"] if not keys or dish_key(d) in keys]
        catalog = await current_catalog()
        items, requirements, gaps = await purchase_items(session, uid, family_id, dishes, catalog)
        source = {
            "kind": "meal_selection",
            "uid": uid,
            "family_id": family_id,
            "date": day.isoformat(),
            "meal_type": meal_type,
            "version": version,
            "dish_keys": sorted(keys),
            "scope_hash": purchase_scope_hash(dishes),
            "items": [
                {"sku_id": i["sku_id"], "quantity": i["quantity"], "identity": merchant_facts(i["sku"])} for i in items
            ],
        }
        purchase = {"available": bool(items), "items": items, "ingredient_requirements": requirements, "gaps": gaps}
        result = {"version": version, "purchase": purchase}
    if not publish:
        return result
    expiry = datetime.combine(day + timedelta(days=1), day_time.min, ZoneInfo("Asia/Shanghai"))
    if expiry.timestamp() <= time.time():
        raise HealthVisionError("purchase_expired", "该餐单已过期，请打开今日餐单", 410)
    source["expires_at"] = int(expiry.timestamp())
    source["catalog_version"] = catalog["version"]
    source["menu_version_ref"] = "meal-selection:" + input_fingerprint(source)
    task = str(uuid5(NAMESPACE_URL, source["menu_version_ref"]))
    payload = {
        "agent_task_id": task,
        "family_ref": "meal-selection:" + family_id,
        "user_ref": "uid:" + uid,
        "menu_version_ref": source["menu_version_ref"],
        "catalog_version": catalog["version"],
        "ingredient_requirements": [],
        "items": [{"sku_id": i["sku_id"], "quantity": i["quantity"]} for i in items],
        "expires_at": expiry.isoformat(),
        "nutrition_validation": {
            "status": "reference_only",
            "validation_id": task,
            "rules_version": "",
            "summary": "用户选择的菜品食材",
        },
        "agent_source_proof": sign_commerce_source(source),
    }
    package = await commerce_request("POST", "/api/v1/integration/ai/recommendation-packages", payload, request_id=task)
    result["purchase"] = {**purchase, **package}
    return result


def purchase_scope_hash(dishes):
    """展示助译和媒体不参与采购身份，原文、来源及份量仍需一致。"""
    presentation = {"display_zh", "translation_status", "image_url", "image_source", "step_images"}
    return input_fingerprint([{key: value for key, value in dish.items() if key not in presentation} for dish in dishes])


async def validate_selection_purchase(source):
    """商城回源核对当前餐单、所选菜品和商品包装。"""
    if source["expires_at"] <= time.time():
        raise HealthVisionError("source_invalidated", "餐单采购已过期", 410)
    result = await scoped_purchase(
        source["uid"],
        source["family_id"],
        date.fromisoformat(source["date"]),
        source["meal_type"],
        source["version"],
        source["dish_keys"],
    )
    expected = [
        {"sku_id": i["sku_id"], "quantity": i["quantity"], "identity": merchant_facts(i["sku"])}
        for i in result["purchase"]["items"]
    ]
    if expected != source["items"]:
        raise HealthVisionError("source_invalidated", "菜品食材或商品已变化，请重新采购", 410)
    return {
        "available": True,
        "selection_mode": "reference",
        "items": [{"sku_id": i["sku_id"], "quantity": i["quantity"]} for i in expected],
    }


async def selected_source(session, uid, family_id, ref, meal_type):
    """用户选菜只存原引用；读取时重新装配单餐内容。"""
    if not ref.get("dish_sources") or not ref.get("member_ids"):
        raise HealthVisionError("dish_source_invalid", "本餐菜品来源不完整，请重新读取", 409)
    dishes, member_notes = [], {}
    expected = set(ref["member_ids"])
    for origin in ref["dish_sources"]:
        dish, original, members, _ = await read_origin(session, uid, family_id, origin)
        if {m["id"] for m in members} != expected:
            raise HealthVisionError("dish_members_changed", "就餐成员已有变化，请重新读取餐单", 409)
        dish.update(dish_key=dish_key(dish), origin=origin)
        dishes.append(dish)
        for note in original.get("memberNotes", []):
            target = member_notes.setdefault(
                note["memberId"], {"memberId": note["memberId"], "name": note["name"], "dishes": []}
            )
            target["dishes"].extend(
                copy.deepcopy(p) for p in note.get("dishes", []) if str(p.get("dishId")) == dish_key(dish)
            )
    meal = {
        "type": meal_type,
        "meal_type": meal_type,
        "dishes": dishes,
        "members": members,
        "memberNotes": list(member_notes.values()),
    }
    meal["nutrition"] = selection_nutrition(meal)
    return {"meals": [meal], "members": members}


async def read_origin(session, uid, family_id, origin):
    """每次回读原业务来源的权限、版本和菜谱内容。"""
    from yuxi.services.daily_arrangement_service import authorize_sources, validate_daily_quality
    from yuxi.repositories.daily_arrangement_repository import DailyArrangementRepository
    from yuxi.services.reference_meal_plan_service import read_reference_plan_in_session

    ref = origin["source"]
    if ref["kind"] == "reference":
        _, source = await read_reference_plan_in_session(session, uid, ref["id"])
        if source["sources"]["family_id"] != family_id or source["plan_date"] != origin["date"]:
            raise HealthVisionError("dish_source_changed", "菜谱来源已变化，请重新打开餐单", 409)
    elif ref["kind"] == "formal":
        from types import SimpleNamespace

        frozen = origin.get("frozen")
        if frozen:
            receipt = SimpleNamespace(
                family_id=family_id, status="ready", selection={}, sources=frozen["sources"], snapshot=frozen["quality"]
            )
            await authorize_sources(session, uid, receipt, published=True)
            source = {"meals": [frozen["meal"]]}
        else:
            _, row = await DailyArrangementRepository(session, uid, family_id).context(
                date.fromisoformat(origin["date"])
            )
            if not row or row.id != ref["id"] or not row.snapshot or row.snapshot["version"] != ref["version"]:
                raise HealthVisionError("dish_source_changed", "菜谱来源已变化，请重新打开餐单", 409)
            await authorize_sources(session, uid, row, published=True)
            await validate_daily_quality(session, uid, row.snapshot)
            source = row.snapshot
    else:
        raise HealthVisionError("dish_source_invalid", "菜谱来源无法读取", 409)
    meal = next((m for m in source["meals"] if m.get("meal_type", m.get("type")) == origin["meal_type"]), None)
    dish = next((d for d in (meal or {}).get("dishes", []) if dish_key(d) == origin["dish_key"]), None)
    if dish is None:
        raise HealthVisionError("dish_source_changed", "原餐单已没有这道菜，请重新读取", 409)
    members = meal.get("members", source.get("members", []))
    if ref["kind"] == "reference":
        from yuxi.services.reference_meal_plan_service import reference_meal_media

        decorated = await reference_meal_media(session, {"dishes": [dish]})
        dish = decorated["dishes"][0]
    return copy.deepcopy(dish), meal, members, source


async def freeze_origin(session, origin):
    """用户采用正式菜时保留原授权和份量，其他餐次更新不改写已选菜。"""
    from yuxi.storage.postgres.models_health import HealthDailyArrangement

    result = copy.deepcopy(origin)
    if origin["source"]["kind"] != "formal" or origin.get("frozen"):
        return result
    row = await session.get(HealthDailyArrangement, origin["source"]["id"])
    if not row or not row.snapshot or row.snapshot.get("version") != origin["source"]["version"]:
        raise HealthVisionError("dish_source_changed", "菜谱来源已变化，请重新读取", 409)
    meal = next(m for m in row.snapshot["meals"] if m.get("meal_type", m.get("type")) == origin["meal_type"])
    selected = copy.deepcopy(meal)
    selected["dishes"] = [d for d in selected["dishes"] if dish_key(d) == origin["dish_key"]]
    for note in selected.get("memberNotes", []):
        note["dishes"] = [p for p in note.get("dishes", []) if str(p.get("dishId")) == origin["dish_key"]]
    result["frozen"] = {
        "meal": selected,
        "sources": copy.deepcopy(
            row.selection.get("published_sources", row.sources) if row.status != "ready" else row.sources
        ),
        "quality": {key: row.snapshot.get(key) for key in ("quality_check_id", "plan_id", "plan_version")},
    }
    return result


async def purchase_items(session, uid, family_id, dishes, catalog):
    """正式菜谱按已发布映射凑包，参考菜谱只采用原文对应的商品。"""
    from yuxi.services.daily_arrangement_projection import ingredient_requirements
    from yuxi.services.reference_meal_plan_service import product_facts
    from yuxi.storage.postgres.models_health import HealthRecipeCommerceSource

    requirements, reference_items, gaps = [], {}, []
    current = {str(s["sku_id"]): s for s in catalog["items"]}
    for dish in dishes:
        original, original_meal, _, source = await read_origin(session, uid, family_id, dish["origin"])
        if dish["origin"]["source"]["kind"] == "formal":
            rid = original["recipeVersion"]
            mapping = await session.get(HealthRecipeCommerceSource, rid)
            if mapping is None:
                raise HealthVisionError("dish_mapping_missing", "该菜品的食材采购映射尚未发布", 409)
            snapshot = {
                "meals": [
                    {
                        "meal_type": "selected",
                        "dishes": [{"recipe_version_id": rid, "ingredients": original["ingredients"]}],
                    }
                ]
            }
            required = ingredient_requirements(snapshot, {rid: mapping})
            if not required:
                raise HealthVisionError("dish_mapping_missing", "该菜品的食材用量或采购映射不完整", 409)
            requirements.extend(required)
        else:
            ingredients = set(original["ingredients"])
            chosen = [i for i in source.get("purchase_items", []) if ingredients.intersection(i["ingredient_refs"])]
            covered = {r for i in chosen for r in i["ingredient_refs"] if r in ingredients}
            dish_gaps = _scoped_reference_gaps(original, source)
            exempt = {gap["ingredient"] for gap in dish_gaps}
            if covered & exempt or covered | exempt != ingredients:
                raise HealthVisionError("dish_ingredients_missing", "这道菜有食材尚未匹配商品，请先完善食材清单", 409)
            gaps.extend(gap for gap in dish_gaps if gap not in gaps)
            for item in chosen:
                sid = str(item["sku_id"])
                sku = current.get(sid)
                if (
                    not sku
                    or input_fingerprint(product_facts(sku, include_description=item.get("facts_version") == 2))
                    != item["facts_hash"]
                ):
                    raise HealthVisionError("dish_product_changed", "食材商品或包装已变化，请重新匹配", 409)
                refs = ingredients.intersection(item["ingredient_refs"])
                quantity = reference_pack_quantity(refs, sku)
                if quantity is None:
                    # 原建议只在其所引用食材均属于本菜时可沿用，不能带入别菜数量。
                    owners = [
                        d for m in source["meals"] for d in m["dishes"] if set(d["ingredients"]).intersection(refs)
                    ]
                    if set(item["ingredient_refs"]) != refs or len(owners) != 1:
                        raise HealthVisionError(
                            "dish_quantity_missing", "原食谱缺少独立用量，暂不能计算这道菜的采购数量", 409
                        )
                    quantity = item["quantity"]
                entry = reference_items.setdefault(sid, {"sku_id": sid, "quantity": 0, "sku": sku, "mass_refs": []})
                if reference_pack_quantity(refs, sku) is not None:
                    entry["mass_refs"].extend(refs)
                else:
                    entry["quantity"] += quantity
    grouped = {}
    for requirement in requirements:
        identity = (requirement.get("sku_id"), requirement.get("food_id"), requirement.get("ingredient_code"))
        if identity in grouped:
            grouped[identity]["required_value"] = str(
                Decimal(grouped[identity]["required_value"]) + Decimal(requirement["required_value"])
            )
        else:
            grouped[identity] = copy.deepcopy(requirement)
    requirements = list(grouped.values())
    fractions = {}
    from yuxi.services.commerce_sku_selection import pack_grams

    for sid, entry in reference_items.items():
        refs = entry.pop("mass_refs")
        net = pack_grams(entry["sku"])
        mass = reference_mass(refs) if refs else Decimal(0)
        fractions[sid] = Decimal(entry["quantity"]) + (mass / net if mass and net else 0)
    items = selection_packages(requirements, catalog, fractions)
    if not items:
        raise HealthVisionError("dish_stock_missing", "所选菜品的食材暂时无法配齐，请稍后再试", 409)
    return items, requirements, gaps


def _scoped_reference_gaps(original, source):
    """只投影本菜已保存且合法的自备或可选决定，不生成商品映射。"""
    from yuxi.services.reference_cooking_water import cooking_water
    from yuxi.services.reference_recipe_matching import optional_reference_ingredient

    ingredients = original["ingredients"]
    labels = dict(zip(ingredients, original.get("display_zh", {}).get("ingredients", [])))
    result, seen = [], set()
    for gap in source.get("purchase_gaps", []):
        ingredient, reason = gap.get("ingredient"), gap.get("reason")
        if ingredient not in ingredients:
            continue
        if ingredient in seen or "sku_id" in gap:
            raise HealthVisionError("dish_ingredients_missing", "食材采购对应重复或不完整，请重新核对餐单", 409)
        seen.add(ingredient)
        if reason == "not_sold" and cooking_water(ingredient):
            detail = "烹饪用水，需自行准备。"
        elif reason == "optional_not_selected" and optional_reference_ingredient(ingredient):
            detail = "原谱可选，本次未采用。"
        elif reason in {"no_match", "needs_confirmation"} and not cooking_water(ingredient) and not optional_reference_ingredient(ingredient):
            detail = (
                "需自行准备：商城尚未匹配到此食材。"
                if reason == "no_match"
                else "需自行准备并核对原谱品种、形态和用量。"
            )
        else:
            raise HealthVisionError("dish_ingredients_missing", "食材缺口说明与原谱不一致，请重新核对餐单", 409)
        result.append({"ingredient": ingredient, "ingredient_label": labels.get(ingredient, ingredient), "reason": reason, "detail": detail})
    return result


def selection_packages(requirements, catalog, base):
    """对选定范围合并包装；组合包同时提供成分，库存冲突时回溯候选。"""
    from yuxi.services.commerce_sku_selection import pack_grams, direct_sku_matches
    from yuxi.services.daily_commerce_service import sku_matches_plan

    current = {str(s["sku_id"]): s for s in catalog["items"]}
    fractions = dict(base)
    if any(r.get("sku_id") for r in requirements):
        if not all(r.get("sku_id") for r in requirements):
            return None
        for row in requirements:
            sid = str(row["sku_id"])
            sku = current.get(sid)
            if not sku or not direct_sku_matches(sku, requirements):
                return None
            fractions[sid] = fractions.get(sid, Decimal(0)) + Decimal(row["required_value"]) / pack_grams(sku)
    else:
        groups = []
        for row in requirements:
            code = row["ingredient_code"]
            candidates = []
            for sid, sku in current.items():
                if not sku_matches_plan(sku, requirements):
                    continue
                for mapping in sku["ingredients"]:
                    if mapping["ingredient_code"] != code:
                        continue
                    net = (
                        Decimal(str(mapping["net_value"]))
                        * Decimal(str(mapping.get("convert_ratio", 1)))
                        * (1 - Decimal(str(mapping.get("loss_rate", 0))))
                    )
                    fraction = Decimal(row["required_value"]) / net
                    cost = int(fraction.to_integral_value(rounding=ROUND_CEILING)) * sku["price_cent"]
                    candidates.append((cost, sid, code, fraction))
            if not candidates:
                return None
            groups.append(sorted(candidates))
        groups.sort(key=len)
        assigned = {}

        def allocate(index):
            """只计算实际由该SKU承接的成分；同成分叠加，不同成分共用包装。"""
            if index == len(groups):
                return True
            for _, sid, code, fraction in groups[index]:
                previous = assigned.get(sid, {}).get(code, Decimal(0))
                own = assigned.setdefault(sid, {})
                own[code] = previous + fraction
                total = base.get(sid, Decimal(0)) + max(own.values())
                if total.to_integral_value(rounding=ROUND_CEILING) <= int(
                    current[sid].get("available_quantity") or 0
                ) and allocate(index + 1):
                    return True
                if previous:
                    own[code] = previous
                else:
                    del own[code]
                if not own:
                    del assigned[sid]
            return False

        if not allocate(0):
            return None
        for sid, own in assigned.items():
            fractions[sid] = fractions.get(sid, Decimal(0)) + max(own.values())
    items = []
    for sid, fraction in fractions.items():
        sku = current[sid]
        quantity = int(fraction.to_integral_value(rounding=ROUND_CEILING))
        if quantity <= 0 or quantity > int(sku.get("available_quantity") or 0) or sku.get("sale_status") != "available":
            return None
        items.append({"sku_id": sid, "quantity": quantity, "sku": sku})
    return items


def selection_nutrition(meal):
    """只按已保存的成品份量换算；任一道缺失时不输出部分合计。"""
    fields = {
        "kcal": "energyKcal",
        "protein": "proteinG",
        "fat": "fatG",
        "carbs": "carbohydrateG",
        "fiber": "fiberG",
        "sodium": "sodiumMg",
    }
    result = {}
    for label, field in fields.items():
        values = []
        for dish in meal["dishes"]:
            nutrition = dish.get("nutrition") or {}
            portions = [
                p
                for n in meal.get("memberNotes", [])
                for p in n.get("dishes", [])
                if str(p.get("dishId")) == dish_key(dish)
            ]
            amount = nutrition.get(field)
            valid = nutrition.get("basis") == "per_100g" and nutrition.get("foodState") in {
                "recipe_edible",
                "cooked_edible",
            }
            if (
                not valid
                or not portions
                or type(amount) not in (int, float)
                or any(type(p.get("grams")) not in (int, float) for p in portions)
            ):
                values = []
                break
            values.append(Decimal(str(amount)) * sum(Decimal(str(p["grams"])) for p in portions) / 100)
        result[label] = round(float(sum(values)), 2) if values else None
    return result


def attach_origins(meal, ref, day, meal_type):
    """只附加来源位置，不改写原始菜谱。"""
    result = copy.deepcopy(meal)
    for dish in result["dishes"]:
        dish["dish_key"] = dish_key(dish)
        dish["origin"] = {"source": ref, "date": str(day), "meal_type": meal_type, "dish_key": dish["dish_key"]}
    return result


def dish_key(dish):
    """身份使用已保存菜谱字段，展示名称不参与客户端写入。"""
    return str(
        dish.get("dish_key")
        or dish.get("id")
        or dish.get("recipe_ref")
        or ":".join(str(dish[k]) for k in ("file_id", "chunk_id", "name") if dish.get(k))
    )


def merchant_facts(sku):
    """价格可刷新；配料及包装身份改变使旧采购失效。"""
    from yuxi.services.reference_meal_plan_service import product_facts

    return product_facts(sku, include_description=True)


def reference_pack_quantity(ingredients, sku):
    """用已知质量与包装计算数量，不把毫升当克。"""
    from yuxi.services.commerce_sku_selection import pack_grams

    grams, net = reference_mass(ingredients), pack_grams(sku)
    return int((grams / net).to_integral_value(rounding=ROUND_CEILING)) if grams and net else None


def reference_mass(ingredients):
    """只读取原文明确质量，杯、勺或件数保持未知。"""
    grams = Decimal(0)
    for text in ingredients:
        match = re.fullmatch(r"[^\d.+\-*/×^=~～至到–—]*?(\d+(?:\.\d+)?)\s*(千克|公斤|kg|克|g)\s*", text.strip(), re.I)
        if not match:
            return None
        amount, unit = match.groups()
        grams += Decimal(amount) * (1000 if unit.lower() in {"千克", "公斤", "kg"} else 1)
    return grams if grams > 0 else None

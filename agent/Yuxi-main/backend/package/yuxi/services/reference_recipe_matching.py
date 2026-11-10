"""从知识库原谱提取完整食材，并只匹配可确认身份的商城商品。"""

from dataclasses import dataclass
from hashlib import sha256
import re

from yuxi.services.reference_cooking_water import cooking_water as cooking_water_ingredient


@dataclass(frozen=True)
class ParsedReferenceRecipe:
    """一份可完整核对的原谱正文。"""

    name: str
    ingredients: tuple[str, ...]
    steps: tuple[str, ...]
    review_sections: tuple[str, ...] = ()


_FOODS = {
    "大米": (r"\brice\b", r"大米|米饭"),
    "红薯": (r"\bsweet potatoes?\b", r"红薯|地瓜"),
    "土豆": (r"\bpotatoes?\b", r"土豆|马铃薯"),
    "鸡蛋": (r"\beggs?\b", r"鸡蛋|鷄蛋|雞蛋|煮蛋|蒸蛋"),
    "番茄": (r"\btomato(?:es)?\b", r"番茄|西红柿"),
    "洋葱": (r"\bonions?\b", r"洋葱|洋蔥"),
    "橄榄油": (r"\bolive oil\b", r"橄榄油|橄欖油"),
    "菠菜": (r"\bspinach\b", r"菠菜"),
    "西兰花": (r"\bbroccoli\b", r"西兰花|西蘭花"),
    "花菜": (r"\bcauliflower\b", r"花菜|菜花"),
    "胡萝卜": (r"\bcarrots?\b", r"胡萝卜|胡蘿蔔"),
    "西葫芦": (r"\bzucchini\b", r"西葫芦|西葫蘆"),
    "鸡胸肉": (r"\bchicken breasts?\b", r"鸡胸肉|雞胸肉"),
    "三文鱼": (r"\bsalmon\b", r"三文鱼|三文魚"),
    "鳕鱼": (r"\bcod\b", r"鳕鱼|鱈魚"),
    "黄瓜": (r"\bcucumbers?\b", r"黄瓜|黃瓜"),
    "牛奶": (r"\bmilk\b", r"牛奶"),
    "燕麦": (r"\boats?\b|\boatmeal\b", r"燕麦|燕麥"),
    "大蒜": (r"\bgarlic\b", r"大蒜|蒜"),
    "水": (r"\bwater\b", r"水"),
    "盐": (r"\bsalt\b", r"食盐|盐"),
    "糖": (r"\bsugar\b", r"白糖|糖"),
    "豆腐": (r"\btofu\b", r"豆腐"),
    "圆白菜": (r"\bcabbage\b", r"圆白菜|圓白菜|卷心菜|包菜"),
    "大白菜": (r"\bnapa cabbage\b|\bChinese cabbage\b", r"大白菜"),
    "蘑菇": (r"\bmushrooms?\b", r"蘑菇"),
    "香菇": (r"\bshiitake(?: mushrooms?)?\b", r"香菇"),
    "金针菇": (r"\benoki(?: mushrooms?)?\b", r"金针菇|金針菇"),
    "茄子": (r"\beggplants?\b|\baubergines?\b", r"茄子"),
    "彩椒": (r"\bbell peppers?\b", r"彩椒|甜椒"),
    "芦笋": (r"\basparagus\b", r"芦笋|蘆筍"),
    "西芹": (r"\bcelery\b", r"西芹|芹菜"),
    "生菜": (r"\blettuce\b", r"生菜"),
    "姜": (r"\bginger\b", r"生姜|姜"),
    "黑胡椒": (r"\bblack pepper\b", r"黑胡椒"),
    "鹰嘴豆": (r"\bchickpeas?\b", r"鹰嘴豆|鷹嘴豆"),
    "核桃仁": (r"\bwalnuts?\b", r"核桃仁"),
    "鸡肉": (r"\bchicken\b", r"鸡肉|雞肉"),
    "牛肉": (r"\bbeef\b", r"牛肉"),
    "猪肉": (r"\bpork\b", r"猪肉|豬肉"),
}
_SINGLE_FOOD = {food: tuple(re.compile(term, re.IGNORECASE) for term in terms) for food, terms in _FOODS.items()}
# 召回只需词法提示；大段正文使用单次分词，避免逐字符尝试全部身份正则。
_RECALL_WORDS = {
    "rice": "大米", "potato": "土豆", "potatoes": "土豆", "egg": "鸡蛋", "eggs": "鸡蛋",
    "tomato": "番茄", "tomatoes": "番茄", "onion": "洋葱", "onions": "洋葱",
    "spinach": "菠菜", "broccoli": "西兰花", "cauliflower": "花菜", "carrot": "胡萝卜", "carrots": "胡萝卜",
    "zucchini": "西葫芦", "chicken": "鸡肉", "salmon": "三文鱼", "cod": "鳕鱼",
    "cucumber": "黄瓜", "cucumbers": "黄瓜", "milk": "牛奶", "oat": "燕麦", "oats": "燕麦", "oatmeal": "燕麦",
    "garlic": "大蒜", "water": "水", "salt": "盐", "sugar": "糖", "tofu": "豆腐", "cabbage": "圆白菜",
    "mushroom": "蘑菇", "mushrooms": "蘑菇", "shiitake": "香菇", "enoki": "金针菇",
    "eggplant": "茄子", "eggplants": "茄子", "aubergine": "茄子", "asparagus": "芦笋", "celery": "西芹",
    "lettuce": "生菜", "ginger": "姜", "chickpea": "鹰嘴豆", "chickpeas": "鹰嘴豆",
    "walnut": "核桃仁", "walnuts": "核桃仁", "beef": "牛肉", "pork": "猪肉",
}
_RECALL_PHRASES = {
    "sweet potato": "红薯",
    "olive oil": "橄榄油",
    "chicken breast": "鸡胸肉",
    "bell pepper": "彩椒",
    "black pepper": "黑胡椒",
    "napa cabbage": "大白菜",
    "chinese cabbage": "大白菜",
}
_UNSUPPORTED_FORMS = re.compile(
    r"\b(?:canned|frozen|dried|powder|flour|paste|sauce|broth|stock|juice|skinless|boneless|"
    r"smoked|pickled|brown rice|glutinous rice|sticky rice|sweet rice|wild rice|black rice|"
    r"red rice|rice vinegar|rice noodles?|water chestnuts|soy milk|coconut milk)\b|"
    r"罐头|罐頭|酱|醬|汁|粉|高汤|高湯|去骨|去皮",
    re.IGNORECASE,
)
_HEADING = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
_INGREDIENT_HEADINGS = {"食材与用量（原文）", "材料", "食材", "ingredients", "ingredient"}
_STEP_HEADINGS = {"做法（原文）", "做法", "作法", "步骤", "procedure", "directions", "method", "instructions"}
_AFTER_RECIPE_HEADINGS = {
    "备注",
    "说明",
    "份量",
    "notes",
    "note",
    "source",
    "来源",
    "nutrition",
    "营养",
    "portion",
    "yield",
    "servings",
    "原文营养信息",
    "份量与时间",
}
_REFERENCE_PROVENANCE = {
    "未出现的营养字段保持未知；原文 % 数值和单位原样保留，未换算。正文保留原文烹饪方法；本资料未经本项目专业审核。",
    "- 食材熟/生、杯/勺及份量按原文解释；未推断未标明的生熟状态。",
    "- 原文未说明的熟制净产量克数、配料品牌、过敏原完整清单和个体适用性保持未知。",
    "- 营养数据保留原文计量基准；未知值与零值分别处理，未与 USDA 成分表自动拼接。",
    "- 原始单位：cup/tbsp/tsp/oz 等按来源；不直接作为本项目按克计算的正式食谱。",
    "- Publication status: source_reference; professional_approval: false.",
}
_OPTIONAL_MARKER = re.compile(r"(?:\s*\((?:optional|可选)\)|\s*[（](?:optional|可选)[）])\s*$", re.I)
_ALLOWED_ENGLISH_REMAINDER = {
    "fl", "unpeeled", "pinch", "pinches", "of",
    "white", "uncooked", "rinsed", "washed", "drained", "cut", "into", "florets",
    "crushed", "finely", "roughly", "thinly", "thickly", "and", "trimmed",
    "grams", "gram", "kilograms", "pounds", "pound", "ounces", "ounce", "lbs",
    "big", "size", "sized", "to", "taste", "chunk", "chunks", "shredded",
    "c",
    "cup",
    "cups",
    "g",
    "kg",
    "ml",
    "l",
    "oz",
    "lb",
    "tsp",
    "tbsp",
    "teaspoon",
    "teaspoons",
    "tablespoon",
    "tablespoons",
    "small",
    "medium",
    "large",
    "fresh",
    "cold",
    "warm",
    "hot",
    "boiling",
    "drinking",
    "whole",
    "chopped",
    "diced",
    "sliced",
    "minced",
    "peeled",
    "raw",
    "ripe",
    "stalk",
    "stalks",
    "clove",
    "cloves",
    "pieces",
    "piece",
}
_ALLOWED_CHINESE_REMAINDER = (
    "切小朵", "洗净", "洗淨", "沥干", "瀝乾", "切段", "拍碎", "剁碎", "去根",
    "适量",
    "新鲜",
    "冷",
    "温",
    "热",
    "开",
    "沸",
    "清",
    "大",
    "中",
    "小",
    "切碎",
    "切丁",
    "切片",
    "去皮",
    "克",
    "千克",
    "毫升",
    "升",
    "杯",
    "碗",
    "个",
    "枚",
    "片",
    "根",
    "瓣",
    "勺",
    "茶匙",
    "汤匙",
)


def parse_reference_recipe(content: str) -> ParsedReferenceRecipe | None:
    """兼容常见标题和列表格式，完整保留食材；边界不明返回待核对。"""
    lines = content.splitlines()
    title_index = next((i for i, line in enumerate(lines) if line.strip()), None)
    if title_index is None:
        return None
    title = lines[title_index].strip().lstrip("#").strip().removeprefix("烹饪菜谱｜")
    if not title or len(title) > 120:
        return None
    sections = []
    for i, line in enumerate(lines[title_index + 1:], title_index + 1):
        value = line.strip()
        label = value.lstrip("#").strip().strip("*").strip().rstrip(":：").casefold()
        label = label.removesuffix("（原文）").removesuffix("(original)").strip()
        kind = (
            "ingredients"
            if label in {"食材与用量", "食材", "材料", "配料", "ingredients", "ingredient"}
            else "steps"
            if label
            in {"做法", "作法", "步骤", "制作步骤", "烹饪步骤", "procedure", "directions", "method", "instructions"}
            else "review"
            if label in {"notes", "note", "备注", "说明", "notes, tips, and variations"}
            else "equipment"
            if label in {"equipment", "器具", "工具"}
            else "citations"
            if label in {"references", "external links", "see also", "原文引用与附加署名", "外部链接"}
            else "notes"
            if label in _AFTER_RECIPE_HEADINGS
            else None
        )
        if label == "原文说明与缺失项":
            # 只略过收录器已知的来源说明；原文附注/Tip 等仍需人工核对。
            following = [item.strip() for item in lines[i + 1:] if item.strip()]
            kind = "notes" if following and all(
                item in _REFERENCE_PROVENANCE or item.startswith("Recipe Source: ") for item in following
            ) else "review"
        explicit = bool(re.match(r"^#{1,6}\s+", value) or re.fullmatch(r"\*\*.+\*\*", value)
                        or re.search(r"(?:ingredients?|食材|材料|配料).*[:：]$", value, re.I))
        if kind or explicit:
            heading = re.match(r"^(#{1,6})\s+", value)
            sections.append((i, kind, len(heading[1]) if heading else 2))
    ingredients_at = [i for i, (_, kind, _) in enumerate(sections) if kind == "ingredients"]
    steps_at = [i for i, (_, kind, _) in enumerate(sections) if kind == "steps"]
    if len(ingredients_at) != 1 or len(steps_at) != 1:
        return None
    i, j = ingredients_at[0], steps_at[0]
    if j <= i or any(kind != "equipment" for _, kind, _ in sections[i + 1:j]):
        return None
    ingredient_start, step_start = sections[i][0], sections[j][0]
    step_end = sections[j + 1][0] if j + 1 < len(sections) else len(lines)
    ingredients = recipe_list_items(lines[ingredient_start + 1:sections[i + 1][0]])
    steps = recipe_list_items(lines[step_start + 1:step_end])
    review_sections = []
    for section_index in range(j + 1, len(sections)):
        start, kind, level = sections[section_index]
        end = sections[section_index + 1][0] if section_index + 1 < len(sections) else len(lines)
        section = "\n".join(lines[start:end]).strip()
        body = "\n".join(lines[start + 1:end]).strip()
        if kind == "notes" and level <= sections[j][2]:
            continue
        if kind == "citations" and (not body or all(
            re.fullmatch(r"(?:- )?(?:\[[^\]]+\]\(https?://[^\s)]+\)|https?://\S+)", line)
            for line in body.splitlines()
        )):
            continue
        # 后续章节保留为诊断，不因附注边界问题丢掉已经识别的食材。
        if body:
            informational = kind == "review" and all(re.fullmatch(
                r"(?:- )?(?:Keep refrigerated|Serve (?:immediately|hot|warm|cold)|"
                r"Allow to cool before serving|冷藏保存|趁热食用|放凉后食用)[.!。]?",
                line.strip(), re.I,
            ) for line in body.splitlines() if line.strip())
            if informational:
                steps += (section,)
            else:
                review_sections.append(section)
        elif kind not in {"review", "citations"}:
            review_sections.append(section)
    if (not 1 <= len(ingredients) <= 30 or not 1 <= len(steps) <= 20
            or len(set(ingredients)) != len(ingredients)
            or any(len(value) > 1200 for value in ingredients)):
        return None
    # 有些来源把油或配菜只写在步骤里；不能把清单可匹配误称为整谱完整。
    ingredient_text = " ".join(ingredients)
    declared_foods = reference_food_mentions(ingredient_text)
    extra_terms = r"\b(?:butter|oil|flour|vinegar|pepper|parsley|saffron|bread|cheese|honey)\b"
    declared_terms = set(re.findall(extra_terms, ingredient_text.casefold()))
    for step in steps:
        if (reference_food_mentions(step) - declared_foods - {"水"}
                or set(re.findall(extra_terms, step.casefold())) - declared_terms):
            review_sections.append(step)
    return ParsedReferenceRecipe(title, ingredients, steps, tuple(review_sections))


def recipe_list_items(lines: list[str]) -> tuple[str, ...]:
    """去除列表标记，保留条目文本及缩进续行，不推断缺失食材。"""
    result = []
    for line in lines:
        if not line.strip():
            continue
        marker = re.match(r"^\s*(?:[-*+•]\s+|\d+\.\s+|\d+[)、]\s*)", line)
        value = line[marker.end():].strip() if marker else line.strip()
        if not marker and line[:1].isspace() and result:
            result[-1] += "\n" + line.rstrip()
        else:
            result.append(value)
    return tuple(result)


def product_food(product_name: str) -> str | None:
    """示例前缀只影响食材名识别，商城商品身份仍保留原值。"""
    name = product_name.removeprefix("示例·").strip()
    if name in _SINGLE_FOOD:
        return name
    if name in {"食盐", "白糖"}:
        return {"食盐": "盐", "白糖": "糖"}[name]
    for prefix, food in (
        ("富硒鸡蛋", "鸡蛋"),
        ("五常大米", "大米"),
        ("特级初榨橄榄油", "橄榄油"),
        ("三文鱼排", "三文鱼"),
        ("鳕鱼块", "鳕鱼"),
        ("燕麦片", "燕麦"),
    ):
        if name == prefix:
            return food
    return None


def product_foods(product: dict) -> set[str]:
    """从商城结构化食材映射取得身份；商品标题硬编码仅作历史兼容。"""
    foods: set[str] = set()
    for mapping in product.get("ingredients") or []:
        name = str(mapping.get("name") or "").strip()
        if name:
            foods.add(name)
    legacy = product_food(str(product.get("product_name") or ""))
    if legacy:
        foods.add(legacy)
    return foods


def _dynamic_alias_index(products: list[dict]) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for product in products:
        for mapping in product.get("ingredients") or []:
            name = str(mapping.get("name") or "").strip()
            if not name:
                continue
            terms = {name, str(mapping.get("ingredient_code") or "").strip()}
            terms.update(str(value).strip() for value in mapping.get("aliases") or [])
            for term in terms:
                if term:
                    aliases.setdefault(term.casefold(), set()).add(name)
    return aliases


def ingredient_food_for_products(ingredient: str, products: list[dict]) -> str | None:
    """先沿用严格旧识别，再用商城别名严格匹配；歧义时保持待确认。"""
    aliases = _dynamic_alias_index(products)
    legacy = ingredient_food(ingredient)
    if legacy is not None:
        mapped = aliases.get(legacy.casefold(), set())
        return next(iter(mapped)) if len(mapped) == 1 else legacy if not mapped else None
    if _UNSUPPORTED_FORMS.search(ingredient) or re.search(r"\b(?:or|optional)\b|或|可选", ingredient, re.I):
        return None
    value = _OPTIONAL_MARKER.sub("", _without_preparation_suffix(ingredient)).casefold()
    matches = set()
    for alias, foods in aliases.items():
        if re.search(r"[a-z0-9]", alias):
            found = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", value, re.I)
        else:
            found = alias in value
        if found:
            matches.update(foods)
    return next(iter(matches)) if len(matches) == 1 else None




def optional_reference_ingredient(ingredient: str) -> bool:
    """只有原谱明确标记为可选的独立食材才能不采购。"""
    value = _without_preparation_suffix(ingredient)
    if _OPTIONAL_MARKER.search(value) is None:
        return False
    value = _OPTIONAL_MARKER.sub("", value)
    value = re.sub(r"\d+\s*[/／]\s*\d+", "", value)
    return re.search(r"\b(?:and|or|with|plus)\b|[、及和，,;；/／&＆+＋]", value, re.I) is None


def ingredient_food(ingredient: str) -> str | None:
    """不把多种食材、加工形态或不确定替代品硬配到单个商品。"""
    if cooking_water_ingredient(ingredient):
        return "水"
    if _UNSUPPORTED_FORMS.search(ingredient):
        return None
    ingredient = _OPTIONAL_MARKER.sub("", _without_preparation_suffix(ingredient)).strip()
    # 括号中的单位换算不是食材替代；只消除纯数字与量具单位构成的说明。
    ingredient = re.sub(
        r"\((?:[\d\s./¼½¾⅓⅔⅛⅜⅝⅞-]|\b(?:or|ml|l|g|kg|oz|fl|cup|cups|lb)\b)+\)",
        "", ingredient, flags=re.I,
    )
    ingredient = re.sub(r",\s*depending on appetite\s*$", "", ingredient, flags=re.I)
    if _UNSUPPORTED_FORMS.search(ingredient) or re.search(r"\b(?:or|optional)\b|或|可选", ingredient, re.I):
        return None
    matches = {
        food for food, patterns in _SINGLE_FOOD.items() if any(pattern.search(ingredient) for pattern in patterns)
    }
    for specific, generic in [("红薯", "土豆"), ("鸡胸肉", "鸡肉"), ("大白菜", "圆白菜"),
                              ("香菇", "蘑菇"), ("金针菇", "蘑菇")]:
        if specific in matches:
            matches.discard(generic)
    if len(matches) != 1:
        return None
    food = next(iter(matches))
    match = next((found for pattern in _SINGLE_FOOD[food] if (found := pattern.search(ingredient))), None)
    if match is None:
        return None
    remaining = ingredient[: match.start()] + ingredient[match.end() :]
    # 只消除已识别菜品的切配/用量修饰，不消除加工形态或替代关系。
    remaining = remaining.replace("，", ",").replace("–", "-").replace("—", "-")
    words = re.findall(r"[A-Za-z]+", remaining)
    if any(word.casefold() not in _ALLOWED_ENGLISH_REMAINDER
           and not (food == "洋葱" and word.casefold() == "yellow")
           and not (food == "大米" and word.casefold() == "dry") for word in words):
        return None
    remaining = re.sub(r"[A-Za-z]+", "", remaining)
    for allowed in _ALLOWED_CHINESE_REMAINDER:
        remaining = remaining.replace(allowed, "")
    if re.search(r"[^\d\s.,/()\-¼½¾⅓⅔⅛⅜⅝⅞]", remaining):
        return None
    return food if food != "水" or cooking_water_ingredient(ingredient) else None


def _without_preparation_suffix(ingredient: str) -> str:
    """去掉末尾独立切配说明，保留任何额外食材与连接词。"""
    return re.sub(
        r"[,，]\s*(?:(?:finely|roughly|thinly|thickly|coarsely)\s+)?"
        r"(?:chopped|sliced|diced|minced|grated|crushed|peeled|seeded|切片|切碎|切丁|剁碎|磨碎|去皮|去籽)\s*$",
        "",
        ingredient,
        flags=re.I,
    )


def match_reference_ingredients(ingredients: tuple[str, ...], products: list[dict]) -> dict[str, dict] | None:
    """每条原谱食材必须精确落到当前在售商品，烹饪用水独立豁免。"""
    by_food = {}
    for sku in products:
        if sku.get("sale_status", "available") == "available" and int(sku.get("available_quantity", 0)) > 0:
            for food in product_foods(sku):
                by_food.setdefault(food, []).append(sku)
    result = {}
    for ingredient in ingredients:
        food = ingredient_food_for_products(ingredient, products)
        if food is None:
            if optional_reference_ingredient(ingredient):
                result[ingredient] = {"optional_not_selected": True}
                continue
            return None
        if food == "水":
            result[ingredient] = {"water": True}
            continue
        candidates = by_food.get(food, [])
        if not candidates:
            if optional_reference_ingredient(ingredient):
                result[ingredient] = {"optional_not_selected": True}
                continue
            return None
        result[ingredient] = min(candidates, key=lambda sku: (int(sku.get("price_cent") or 0), str(sku["sku_id"])))
    return result


def reference_ingredient_candidates(ingredients: tuple[str, ...], products: list[dict]) -> list[dict]:
    """按结构化食材映射与别名生成在售 SKU 候选，不读取商品详情推断身份。"""
    by_food: dict[str, list[dict]] = {}
    for product in products:
        if (
            product.get("sale_status", "available") == "available"
            and int(product.get("available_quantity") or 0) > 0
        ):
            for food in product_foods(product):
                by_food.setdefault(food, []).append(product)
    result = []
    for ingredient in ingredients:
        food = ingredient_food_for_products(ingredient, products)
        if food == "水":
            status = "cooking_water"
            candidates = []
        elif optional_reference_ingredient(ingredient):
            status = "optional_not_selected"
            candidates = []
        elif food is None:
            status = "needs_confirmation"
            candidates = []
        else:
            candidates = sorted(
                by_food.get(food, []),
                key=lambda product: (int(product.get("price_cent") or 0), str(product.get("sku_id") or "")),
            )
            status = "matched" if candidates else "missing_product"
        result.append(
            {
                "candidate_key": reference_candidate_key(ingredient),
                "ingredient": ingredient,
                "food": food,
                "status": status,
                "candidate_skus": [
                    {
                        key: product.get(key)
                        for key in (
                            "sku_id",
                            "product_name",
                            "sku_name",
                            "net_content",
                            "price_cent",
                            "available_quantity",
                        )
                    }
                    for product in candidates
                ],
            }
        )
    return result


def reference_candidate_key(ingredient: str) -> str:
    """把逐字食材引用变为只供本轮选择使用的稳定候选键。"""
    return "ingredient:" + sha256(ingredient.encode("utf-8")).hexdigest()[:20]


def reference_ingredient_matches(ingredients: tuple[str, ...], products: list[dict]) -> list[dict]:
    """逐项说明已匹配、缺商品和待确认，缺项不丢弃整份候选。"""
    result = []
    for group in reference_ingredient_candidates(ingredients, products):
        item = {key: group[key] for key in ("ingredient", "food", "status")}
        item["sku_id"] = str(group["candidate_skus"][0]["sku_id"]) if group["candidate_skus"] else None
        result.append(item)
    return result


def reference_food_mentions(text: str) -> set[str]:
    """召回用食材别名命中，不作为商品身份或个人适用性证明。"""
    if len(text) < 300:
        return {food for food, patterns in _SINGLE_FOOD.items() if any(p.search(text) for p in patterns)}
    lowered = text.casefold()
    words = set(re.findall(r"[a-z]+", lowered))
    foods = {_RECALL_WORDS[word] for word in words if word in _RECALL_WORDS}
    foods.update(food for phrase, food in _RECALL_PHRASES.items() if phrase in lowered)
    foods.update(food for food in _FOODS if food in text)
    return foods

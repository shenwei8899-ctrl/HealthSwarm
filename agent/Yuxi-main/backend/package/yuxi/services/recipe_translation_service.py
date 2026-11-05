"""原文版本绑定的中文辅助译文；读取不调用模型或修改完成回执。"""

import copy
import re
import unicodedata
from fractions import Fraction

from pydantic import ValidationError

from yuxi.services.health_nutrition_service import input_fingerprint
from yuxi.services.health_vision_types import HealthVisionError
from yuxi.services.recipe_translation_types import RecipeChineseDisplay

TRANSLATION_VERSION = "recipe-zh-v1"
QUOTE_FIELDS = ("name", "ingredients", "steps", "portion_quote", "nutrition_quote")


def translation_key(dish):
    """以完整来源身份及本次引用内容绑定译文，保持原始菜品身份。"""
    source = dish["source"]
    return input_fingerprint(
        {
            "source": {k: source[k] for k in ("kb_id", "file_id", "chunk_id", "file_hash", "chunks_hash")},
            "quotes": {k: dish.get(k) for k in QUOTE_FIELDS},
            "locale": "zh-CN",
            "version": TRANSLATION_VERSION,
        }
    )


def checked_chinese_display(dish, display):
    """逐项验证中文、数字及单位；不把结构校验当作语义审核。"""
    originals = list(quote_pairs(dish))
    if display is None:
        if any(needs_translation(text) for _, text in originals):
            raise HealthVisionError("recipe_translation_missing", "英文菜谱缺少中文译文，请补充后保存", 422)
        return {k: copy.deepcopy(dish.get(k)) for k in QUOTE_FIELDS}
    translated = RecipeChineseDisplay.model_validate(display).model_dump(mode="json")
    if any(len(translated[k]) != len(dish[k]) for k in ("ingredients", "steps")):
        raise HealthVisionError("recipe_translation_invalid", "中文食材及步骤须与原文逐项对应", 422)
    for (path, original), (_, chinese) in zip(originals, quote_pairs(translated), strict=True):
        if bool(original) != bool(chinese):
            raise HealthVisionError("recipe_translation_invalid", "中文译文不能增删原食谱说明", 422)
        if not original:
            continue
        if (
            not chinese.strip()
            or len(chinese) > 6000
            or needs_translation(chinese)
            or needs_translation(original)
            and not re.search(r"[\u3400-\u9fff]", chinese)
        ):
            raise HealthVisionError("recipe_translation_invalid", f"{path} 缺少完整中文译文", 422)
        try:
            if quantity_signature(original) != quantity_signature(chinese):
                raise HealthVisionError("recipe_translation_invalid", "数量、时间或单位与原文不一致", 422)
        except HealthVisionError as error:
            raise HealthVisionError(error.code, f"菜谱 {dish['name'][:120]} 的 {path}：{error.message}", 422) from error
    return translated


async def attach_chinese_display(session, meal):
    """调用方完成权限及原文版本校验后，只读附加匹配译文。"""
    from yuxi.repositories.recipe_translation_repository import RecipeTranslationRepository

    result = copy.deepcopy(meal)
    repository = RecipeTranslationRepository(session)
    for dish in result["dishes"]:
        # 保存快照之外的展示数据不成为下一次读取的事实依据。
        dish.pop("display_zh", None)
        record = await repository.get(translation_key(dish))
        if record is not None:
            dish["display_zh"] = checked_chinese_display(dish, record.display)
            dish["translation_status"] = "ready"
        elif any(needs_translation(text) for _, text in quote_pairs(dish)):
            dish["translation_status"] = "missing"
    return result


async def save_chinese_display(session, dish, display, producer):
    """程序计算来源键并幂等保存，译文不写入原始餐单快照。"""
    from yuxi.repositories.recipe_translation_repository import RecipeTranslationRepository

    translated = checked_chinese_display(dish, display)
    await RecipeTranslationRepository(session).save(
        translation_key(dish), dish["source"], translated, producer, TRANSLATION_VERSION
    )


async def cached_chinese_display(session, dish):
    """只读复用同一完整来源和引句的有效译文，缺失或无效保持未知。"""
    from yuxi.repositories.recipe_translation_repository import RecipeTranslationRepository

    record = await RecipeTranslationRepository(session).get(translation_key(dish))
    if record is None or record.source != dish["source"]:
        return None
    try:
        return checked_chinese_display(dish, record.display)
    except (HealthVisionError, ValidationError):
        return None


def quote_pairs(dish):
    """保持食材、步骤及可选说明的原始顺序。"""
    for field in QUOTE_FIELDS:
        value = dish.get(field)
        if isinstance(value, list):
            for index, text in enumerate(value):
                yield f"{field}[{index}]", text
        else:
            yield field, value or ""


def needs_translation(text):
    """识别未翻译英文词，允许中文里的标准计量缩写。"""
    allowed = {"g", "kg", "mg", "ml", "l", "kcal", "kj", "c", "f", "min", "cm", "mm"}
    words = re.findall(r"[a-zA-Z]+", text or "")
    return any(word.lower() not in allowed for word in words)


def quantity_signature(text):
    """规范化数字、分数和计量名称，拒绝修改或虚构数量单位。"""
    text = re.sub(r"(?<=\d)([¼½¾⅐⅑⅒⅓⅔⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞])", r" \1", text)
    text = unicodedata.normalize("NFKC", text).lower().replace("⁄", "/")
    text = re.sub(
        r"\b(?:a|an|another)\s+(?=(?:minute|hour|second|cup|tablespoon|teaspoon|ounce|pound|"
        r"kilogram|gram|milligram|microgram|milliliter|liter|inch|pinch)\b)",
        lambda m: "" if re.search(r"\b(?:half|quarter)\s+$", text[: m.start()]) else "1 ",
        text,
    )
    text = re.sub(r"\b(?:a|an|one|single)\s+(?:(?:thin|thick|even|single)\s+)?layer\b", "1 layer", text)
    text = re.sub(r"\b(?:thin|thick|even)\s+(?=layers?\b)", "", text)
    text = normalize_count_aliases(text)
    counts = dict(
        zip(
            (
                "one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                "fifteen sixteen seventeen eighteen nineteen"
            ).split(),
            range(1, 20),
            strict=True,
        )
    )
    denominators = {
        "half": 2,
        "halves": 2,
        "third": 3,
        "thirds": 3,
        "fourth": 4,
        "fourths": 4,
        "quarter": 4,
        "quarters": 4,
        "fifth": 5,
        "fifths": 5,
        "sixth": 6,
        "sixths": 6,
        "eighth": 8,
        "eighths": 8,
        "tenth": 10,
        "tenths": 10,
    }
    text = re.sub(
        r"\b(" + "|".join(counts) + r")[ -](" + "|".join(denominators) + r")\b",
        lambda m: f"{counts[m[1]]}/{denominators[m[2]]}",
        text,
    )
    tens = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10), strict=True))
    text = re.sub(
        r"\b(" + "|".join(tens) + r")(?:[ -](" + "|".join(list(counts)[:9]) + r"))?\b",
        lambda m: str(tens[m[1]] + counts.get(m[2], 0)),
        text,
    )
    for word, number in {"a half": "1/2", "half": "1/2", "quarter": "1/4", **counts}.items():
        text = re.sub(r"\b" + word + r"\b", str(number), text)
    text = re.sub(r"(\d+)\s+and\s+(\d+/\d+)", r"\1 \2", text)
    text = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", text)
    text = re.sub(r"(?<![\d/])(\d+)\s*-\s*(\d+\s*/\s*\d+)", r"\1 \2", text)
    text = re.sub(r"(?<=\d)\s*(?:[-–—~～至到]|\bto\b)\s*(?=\d)", "↔", text)
    numbers = []
    for match in re.finditer(r"[-+]?\d+\s+\d+\s*/\s*\d+|[-+]?\d+\s*/\s*\d+|[-+]?\d+(?:\.\d+)?", text):
        token = match[0]
        mixed = re.fullmatch(r"(\d+)\s+(\d+\s*/\s*\d+)", token)
        try:
            value = (
                Fraction(mixed[1]) + Fraction(mixed[2].replace(" ", "")) if mixed else Fraction(token.replace(" ", ""))
            )
        except (ValueError, ZeroDivisionError):
            raise HealthVisionError("recipe_translation_invalid", "原食谱或译文包含无法核对的数量", 422) from None
        numbers.append((match.start(), match.end(), str(value)))
    unit_patterns = {
        "tbsp": r"(?<![a-z])tbsp(?![a-z])|(?<![a-z])tablespoons?(?![a-z])|汤匙|大匙",
        "tsp": r"(?<![a-z])tsp(?![a-z])|(?<![a-z])teaspoons?(?![a-z])|茶匙|小匙",
        "cup": r"(?<![a-z])cups?(?![a-z])|(?<=\d)\s*c(?![a-z])|杯",
        "oz": r"(?<![a-z])oz(?![a-z])|(?<![a-z])ounces?(?![a-z])|盎司",
        "lb": r"(?<![a-z])lbs?(?![a-z])|(?<![a-z])pounds?(?![a-z])|磅",
        "kg": r"(?<![a-z])kg(?![a-z])|(?<![a-z])kilograms?(?![a-z])|千克|公斤",
        "g": r"(?<![a-zμ])g(?![a-z])|(?<![a-z])grams?(?![a-z])|(?<![\u3400-\u9fff])克",
        "mg": r"(?<![a-z])mg(?![a-z])|(?<![a-z])milligrams?(?![a-z])|毫克",
        "mcg": r"(?:μg|mcg)(?![a-z])|(?<![a-z])micrograms?(?![a-z])|微克",
        "ml": r"(?<![a-z])ml(?![a-z])|(?<![a-z])milliliters?(?![a-z])|毫升",
        "l": r"(?<![a-z])l(?![a-z])|(?<![a-z])liters?(?![a-z])|(?<!毫)升",
        "minute": r"(?<![a-z])minutes?(?![a-z])|(?<![a-z])mins?(?![a-z])|分钟|分鐘",
        "hour": r"(?<![a-z])(?:hours?|hrs?)(?![a-z])|小时",
        "second": r"(?<![a-z])(?:seconds?|secs?)(?![a-z])|秒",
        "inch": r"(?<![a-z])inch(?:es)?(?![a-z])|英寸",
        "fahrenheit": r"(?:°|degrees?)\s*f(?![a-z])|(?<![a-z])fahrenheit(?![a-z])|华氏度|华氏",
        "celsius": r"(?:°|degrees?)\s*c(?![a-z])|(?<![a-z])celsius(?![a-z])|摄氏度|摄氏",
        "kcal": r"(?<![a-z])kcal(?![a-z])|千卡",
        "pinch": r"(?<![a-z])pinch(?:es)?(?![a-z])|小撮|撮",
        "layer": r"(?<![a-z])layers?(?![a-z])|层|層",
    }
    units = sorted((m.start(), unit) for unit, pattern in unit_patterns.items() for m in re.finditer(pattern, text))
    # 数量与单位绑定；同单位多次出现仍保持顺序，避免交换两种食材的克重。
    measures, used, unbound_units = {}, set(), []
    for position, unit in units:
        index = next((i for i in range(len(numbers) - 1, -1, -1) if numbers[i][1] <= position), None)
        if (
            index is None
            or index in used
            or not re.fullmatch(r"[\s-]*(?:(?:degrees?|additional|more|extra)\s*)?", text[numbers[index][1] : position])
        ):
            unbound_units.append(unit)
            continue
        values = [numbers[index][2]]
        used.add(index)
        if index > 0 and index - 1 not in used and text[numbers[index - 1][1] : numbers[index][0]] == "↔":
            values.insert(0, numbers[index - 1][2])
            used.add(index - 1)
        measures.setdefault(unit, []).append(tuple(values))
    return (
        [value for i, (_, _, value) in enumerate(numbers) if i not in used],
        sorted((unit, values) for unit, values in measures.items()),
        unbound_units,
        text.count("↔"),
    )


def normalize_count_aliases(text):
    """只接受完整的一小撮或单层，复合中文数量不能截成整数。"""
    if re.search(r"(?:小撮|撮|层|層)\s*半", text):
        raise HealthVisionError("recipe_translation_invalid", "中文复合数量需用明确数字表达", 422)

    def replace(match):
        """按最近的非空白字符拒绝分数、小数或负数前缀。"""
        prefix = text[: match.start()].rstrip()
        if prefix and prefix[-1] in "0123456789一二三四五六七八九十百千零〇两兩万萬亿億之点點负負半/.-+":
            raise HealthVisionError("recipe_translation_invalid", "中文复合数量需用明确数字表达", 422)
        return "1 pinch " if "撮" in match[0] else "1 layer "

    return re.sub(r"(?<![\d./+-])(?:(?:一|1)\s*小撮|一撮|单层|單層|一层|一層)", replace, text)

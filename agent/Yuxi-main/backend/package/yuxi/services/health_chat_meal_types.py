"""对话记餐只采用可回溯的已吃自述，未知份量不换算。"""

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID, NAMESPACE_URL, uuid5

from pydantic import Field

from yuxi.services.health_vision_types import HealthDTO, HealthVisionError, MealItem, MealPayload


class ChatMealFood(HealthDTO):
    """菜名和份量原文，不接受模型生成营养数值。"""

    name: str = Field(min_length=1, max_length=120, description="用户原文中连续出现的菜名或食物名")
    quantity_text: str = Field(default="", max_length=80, description="原文份量，如一碗、200克；未说留空")


class ChatMealStatement(HealthDTO):
    """模型提供本轮及追问前的完整原文，服务端决定身份与日期。"""

    subject: str = Field(default="我", min_length=1, max_length=80, description="原文明确称呼；未指明他人默认我")
    source_quotes: list[str] = Field(
        min_length=1,
        max_length=6,
        description="按时间顺序引用最近用户消息的完整正文，必须包含当前消息；缺信息先追问，不能截掉否定或计划语气",
    )
    intake_quote: str = Field(
        default="",
        max_length=4000,
        description="原文中已经吃过的一餐的完整独立分句；混合咨询时只取实际进食分句，不截掉否定或疑问词。留空采用完整原文",
    )
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"]
    day_text: str = Field(
        default="", max_length=30, description="原文日期，例如今天、昨天、2026-11-02；未说默认陈述当天"
    )
    items: list[ChatMealFood] = Field(min_length=1, max_length=30)


class ChatMealWithdrawal(HealthDTO):
    """撤销携带原版本和稳定请求键。"""

    client_request_id: UUID
    expected_version: int = Field(ge=1)


class ChatMealRecordingInput(HealthDTO):
    """已核对原文的实际摄入允许重量未知。"""

    member_id: UUID
    client_request_id: UUID
    meal: MealPayload
    accept_incomplete: bool = True


def meal_from_statement(statement, sources, member_id):
    """核对完整原文、已吃语气、餐次和实际份量，生成稳定的个人记录。"""
    quotes = statement.source_quotes
    available = {source.content.strip(): source for source in sources}
    current = sources[-1]
    if len(set(quotes)) != len(quotes) or any(quote not in available for quote in quotes):
        raise HealthVisionError("meal_source_invalid", "记餐必须引用最近用户消息的完整原文", 422)
    if current.content.strip() not in quotes:
        raise HealthVisionError("meal_source_invalid", "记餐必须包含当前用户消息，不能重新记录历史陈述", 422)
    positions = [sources.index(available[quote]) for quote in quotes]
    if positions != sorted(positions):
        raise HealthVisionError("meal_source_invalid", "请按对话顺序核对饮食信息", 422)
    text = "\n".join(quotes)
    if len(text) > 12000:
        raise HealthVisionError("meal_source_invalid", "请分别说明每餐吃过的食物", 422)
    actual_pattern = r"吃了|喝了|吃过|喝过|吃的是|喝的是|吃完|喝完|已吃|已喝|用餐了|用过餐"
    reports = [row for row in sources if re.search(actual_pattern, row.content)]
    if not reports:
        raise HealthVisionError("meal_not_actual", "请先说明这是已经吃过的一餐", 422)
    dated_source = reports[-1]
    if dated_source.content.strip() not in quotes:
        raise HealthVisionError("meal_source_invalid", "请核对最近一次实际进食陈述", 422)
    report_text = statement.intake_quote or dated_source.content.strip()
    start = dated_source.content.find(report_text)
    stop = start + len(report_text)
    separators = "，,。；;！!？?\n"
    if (
        start < 0
        or start
        and dated_source.content[start - 1] not in separators
        or stop < len(dated_source.content)
        and dated_source.content[stop] not in separators
        or stop < len(dated_source.content)
        and dated_source.content[stop] in "？?"
        or re.search(r"如果|假如|假设|比如|例如|听说|据说|[说问][，,:：]", dated_source.content[:start])
    ):
        raise HealthVisionError("meal_source_invalid", "实际进食必须引用完整独立分句，不能截掉语气", 422)
    if re.search(r"不要记录|不用记录|别记|不记|不要保存|取消记录|撤销", text):
        raise HealthVisionError("meal_not_actual", "用户未要求保存这条饮食陈述", 422)
    followups = [
        row.content.strip() for row in sources[sources.index(dated_source) + 1 :] if row.content.strip() in quotes
    ]
    intake_text = "\n".join([report_text, *followups])
    non_actual = (
        r"[?？]|如果|假如|比如|例如|假设|据说|听说|他说|她说|想吃|要吃|准备吃|打算|计划|明天|明日|后天|推荐|"
        r"没(?:有)?吃|未吃|不(?:要|用|想|需要|能)?(?:再)?(?:吃|记|保存)|取消记录|不要记录|别记|能不能|是否|会不会|怎么样|怎么做|怎么吃"
    )
    if re.search(non_actual, report_text):
        raise HealthVisionError("meal_not_actual", "这段话含计划、否定或疑问，请先明确实际吃过的食物", 422)
    if not re.search(actual_pattern, report_text):
        raise HealthVisionError("meal_not_actual", "请先说明这是已经吃过的一餐", 422)
    patterns = {
        "breakfast": r"早餐|早饭|早上|今早",
        "lunch": r"午餐|午饭|中午",
        "dinner": r"晚餐|晚饭|晚上|今晚",
        "snack": r"加餐|零食|夜宵|下午茶",
    }
    if not re.search(patterns[statement.meal_type], intake_text):
        raise HealthVisionError("meal_type_missing", "这是早餐、午餐、晚餐还是加餐？", 422)
    prefix = re.split(actual_pattern, report_text, maxsplit=1)[0]
    known_meals = [key for key, pattern in patterns.items() if re.search(pattern, prefix)]
    if known_meals and statement.meal_type not in known_meals:
        raise HealthVisionError("meal_type_missing", "请核对这段已吃原文对应的餐次", 422)
    explicit_days = re.findall(r"今天|今日|昨天|昨日|\d{4}[-年]\d{1,2}[-月]\d{1,2}日?", prefix)
    day_text = statement.day_text or (explicit_days[0] if len(explicit_days) == 1 else "")
    if explicit_days and day_text not in explicit_days:
        raise HealthVisionError("meal_date_invalid", "请核对这段已吃原文对应的日期", 422)
    # 去除时间和餐次后，谓语前仍有专名时不能默认是本人。
    subject_prefix = meal_subject_text(prefix)
    subject_pattern = (
        r"(?:我|本人|自己|我自己|我本人)?(?:在[^，。！？；]{1,40})?"
        if statement.subject == "我"
        else rf"(?:我)?{re.escape(statement.subject)}(?:在[^，。！？；]{{1,40}})?"
    )
    if not re.fullmatch(subject_pattern, subject_prefix):
        raise HealthVisionError("meal_subject_unclear", "请明确是哪位成员实际吃了这些食物", 422)
    timestamp = dated_source.created_at
    timestamp = timestamp.replace(tzinfo=UTC) if timestamp.tzinfo is None else timestamp
    day = (timestamp + timedelta(hours=8)).date()
    if day_text and day_text not in intake_text:
        raise HealthVisionError("meal_date_invalid", "日期必须来自用户原文", 422)
    if day_text in {"昨天", "昨日"}:
        day -= timedelta(days=1)
    elif day_text and day_text not in {"今天", "今日", "今早", "今晚", "刚才", "刚刚"}:
        try:
            day = datetime.strptime(day_text.replace("年", "-").replace("月", "-").rstrip("日"), "%Y-%m-%d").date()
        except ValueError:
            raise HealthVisionError("meal_date_invalid", "请明确具体就餐日期", 422) from None
    elif not day_text and re.search(r"昨天|昨日|前天|上周|\d{1,2}月|\d{4}-\d", intake_text):
        raise HealthVisionError("meal_date_invalid", "请核对原文中的就餐日期", 422)
    current_time = current.created_at.replace(tzinfo=UTC) if current.created_at.tzinfo is None else current.created_at
    if day > (current_time + timedelta(hours=8)).date():
        raise HealthVisionError("meal_not_actual", "未来日期不能保存为已经吃过", 422)
    if len({food.name for food in statement.items}) != len(statement.items):
        raise HealthVisionError("meal_item_duplicate", "同一餐请合并重复食物", 422)
    # 身份固定在已吃陈述原文，不能因模型重试拆分菜名/份量的方式变化而新增摄入。
    report = re.sub(r"[\s，,。；;！!]+", "", dated_source.content)
    key = f"chat-meal:{member_id}:{day}:{statement.meal_type}:{report}"
    request_id = uuid5(NAMESPACE_URL, key)
    items = []
    for food in statement.items:
        quantity_pattern = (
            rf"{re.escape(food.quantity_text)}\s*{re.escape(food.name)}|"
            rf"{re.escape(food.name)}[\s，,：:]*(?:约|大约)?\s*{re.escape(food.quantity_text)}"
        )
        if food.name not in intake_text or food.quantity_text and not re.search(quantity_pattern, intake_text):
            raise HealthVisionError("meal_item_invalid", "菜名和份量必须来自用户原文", 422)
        weight = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:克|g)", food.quantity_text, re.IGNORECASE)
        grams = Decimal(weight.group(1)) if weight else None
        if grams is not None and not 0 < grams <= 10000:
            raise HealthVisionError("meal_item_invalid", "请核对实际克数", 422)
        items.append(
            MealItem(
                item_id=uuid5(request_id, food.name),
                name=food.name,
                grams=grams,
                share_ratio=1 if grams else None,
                portion_source="manual" if grams else "unknown",
                uncertainties=[
                    "用户对话自述；具体用餐时间未提供，仅按餐次归档",
                    "本人份量原文：" + (food.quantity_text or "未知"),
                ],
            )
        )
    validate_report_clauses(statement, [dated_source.content, *followups], actual_pattern, patterns, subject_pattern)
    hour = {"breakfast": 8, "lunch": 12, "dinner": 18, "snack": 15}[statement.meal_type]
    meal = MealPayload(
        meal_type=statement.meal_type,
        eaten_at=f"{day}T{hour:02d}:00:00+08:00",
        items=sorted(items, key=lambda item: item.name),
    )
    return request_id, meal


def validate_report_clauses(statement, originals, actual_pattern, meal_patterns, subject_pattern):
    """完整报告中的未归属分句必须澄清，其他餐次的独立陈述不推翻本餐。"""
    original = "\n".join(originals)
    selected_start = original.find(statement.intake_quote) if statement.intake_quote else 0
    selected_prefix = re.split(actual_pattern, statement.intake_quote or originals[0], maxsplit=1)[0]
    selected_dates = set(re.findall(r"今天|今日|昨天|昨日|\d{4}[-年]\d{1,2}[-月]\d{1,2}日?", selected_prefix))
    for match in re.finditer(r"([^，,。；;！？?\n]+)([，,。；;！？?\n]*)", original):
        clause, punctuation = match.group(1).strip(), match.group(2)
        meals = {key for key, pattern in meal_patterns.items() if re.search(pattern, clause)}
        dates = set(re.findall(r"今天|今日|昨天|昨日|\d{4}[-年]\d{1,2}[-月]\d{1,2}日?", clause))
        if meals and statement.meal_type not in meals or selected_dates and dates and not selected_dates & dates:
            continue
        if match.end(1) <= selected_start and re.fullmatch(
            r"对了|其实|补充一下|顺便说一下|跟你说一下|记一下|帮我记一餐", clause
        ):
            continue
        if re.fullmatch(
            r"(?:请|麻烦)?(?:帮我|给我)?(?:记下来|记录下来|记一下|记录一下|记一餐|保存一下|记录|保存|记下)"
            r"(?:这餐|这一餐|这顿饭|饮食记录)?(?:吧|一下)?|谢谢|谢谢你|辛苦了",
            clause,
        ):
            continue
        # 健康评价问题不改变已经吃过的事实；进食是否发生的问句仍不接受。
        if (
            any(mark in punctuation for mark in "？?")
            and re.search(r"健康|营养|搭配|合适|建议|均衡", clause)
            and re.fullmatch(
                r"(?:这样|这么|这餐|这顿饭?|这些食物|吃得?|搭配|是否|是不是|算不算|够不够|有什么|还有什么|"
                r"营养|健康|均衡|合适|合理|足够|够|吗|呢|么|建议|的|不|有点|偏多|偏少|\s)+",
                clause,
            )
        ):
            continue
        parts = re.split(actual_pattern, clause, maxsplit=1)
        if (
            len(parts) == 2
            and meal_subject_text(parts[0])
            and not re.fullmatch(subject_pattern, meal_subject_text(parts[0]))
        ):
            raise HealthVisionError("meal_subject_unclear", "同一消息中的进食主体需要分别核对", 422)
        if len(parts) == 1 and (
            not meal_subject_text(clause) or re.fullmatch(subject_pattern, meal_subject_text(clause))
        ):
            continue
        remainder = parts[-1]
        for food in sorted(statement.items, key=lambda item: len(item.name), reverse=True):
            remainder = remainder.replace(food.name, "")
            if food.quantity_text:
                remainder = remainder.replace(food.quantity_text, "")
        remainder = re.sub(
            r"[一二两三四五六七八九十半几\d.]+(?:小|大)?(?:碗|份|个|块|片|口|克|g|公斤|kg|杯|勺|毫升|ml)|"
            r"以及|还有|并且|另外|总共|总计|一共|大约|大概|少量|一些|一点|和|及|与|并|又|还|也|约|共|了|[、\s]",
            "",
            remainder,
        )
        if remainder:
            raise HealthVisionError("meal_not_actual", "完整陈述还有未核对的内容，请明确实际吃过的一餐", 422)


def meal_subject_text(prefix):
    """移除已知时间和餐次表达，保留真正的主体词。"""
    return re.sub(
        r"\d{4}[-年]\d{1,2}[-月]\d{1,2}日?|\d{1,2}:\d{2}|今天|今日|昨天|昨日|刚才|刚刚|今早|今晚|"
        r"早餐|早饭|早上|午餐|午饭|中午|晚餐|晚饭|晚上|加餐|零食|夜宵|下午茶|已经|刚|还|又|也|的|[，,\s]",
        "",
        prefix,
    )

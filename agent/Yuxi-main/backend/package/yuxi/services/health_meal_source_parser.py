"""从现有资料明确的营养表读取数值，保留基准和缺失项。"""

import re
from decimal import Decimal, InvalidOperation

from yuxi.services.health_vision_types import NUTRIENTS

PARSER_VERSION = "meal-source-v1"


def parse_meal_source(content: str) -> dict | None:
    """仅接受明确每百克或每份表，避免将配料和能量换算系数当营养。"""
    # 只解析营养区，后续原始 JSON、配料、故事和参考文献不能提供隐含数值。
    sections = re.split(r"(?m)^##\s+", content)
    nutrition = [section for section in sections if re.match(r"[^\n]*(?:营养|nutrient)", section, re.I)]
    if len(nutrition) != 1:
        return None
    section = nutrition[0]
    if re.search(r"未[另\s]*明写|基准[^\n]*(?:不明确|未知)|不推断", section):
        return None
    per100 = bool(re.search(r"每\s*100\s*(?:克|g)|per\s*100\s*g", section, re.I))
    serving = re.search(r"Nutrients\s+Per\s+Serving\s*\(([^)\n]{1,80})\)\s*:", section, re.I)
    if per100 == bool(serving):
        return None
    nutrients, energy_methods = {code: None for code in NUTRIENTS}, {}
    if per100:
        codes = {"1003": "protein_g", "1004": "fat_g", "1005": "carbohydrate_g", "1093": "sodium_mg"}
        rows = {}
        for line in section.splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) != 6 or not cells[0].isdigit():
                continue
            nid, _, amount, unit, _, loq = cells
            value = _number(amount)
            if value == 0 and (_number(loq) or 0) > 0:
                value = None
            code = codes.get(nid)
            if code and unit.lower() == NUTRIENTS[code]:
                rows.setdefault(code, set()).add(value)
            if nid in {"1008", "2047", "2048"} and unit.lower() == "kcal":
                energy_methods.setdefault(nid, set()).add(value)
        for code, values in rows.items():
            nutrients[code] = next(iter(values)) if len(values) == 1 else None
        # 原表通用 Energy 优先，其次明确的 Atwater General；方法编号进入快照。
        energy_id = next((key for key in ("1008", "2047", "2048") if key in energy_methods), None)
        if energy_id and len(energy_methods[energy_id]) == 1:
            nutrients["energy_kcal"] = next(iter(energy_methods[energy_id]))
        basis, label = "per100g", "100 克可食部"
    else:
        section = section[serving.end() :]
        labels = {
            "energy_kcal": r"Calories",
            "protein_g": r"Protein",
            "fat_g": r"Total Fat",
            "carbohydrate_g": r"Carbohydrates?",
            "sodium_mg": r"Sodium",
        }
        for code, label in labels.items():
            if code == "energy_kcal":
                tokens = re.findall(r"\bCalories\s*[:：]?\s*([^,\n]+)(?:,(?!\d)|\n|$)", section, re.I)
                matches = [
                    match.group(1)
                    for token in tokens
                    if (match := re.fullmatch(r"(\d+(?:\.\d+)?)(?:\s*kcal)?", token.strip(), re.I))
                ]
            else:
                unit = r"\s*" + NUTRIENTS[code] + r"\b"
                matches = re.findall(r"\b" + label + r"\s*[:：]?\s*(\d+(?:\.\d+)?)" + unit, section, re.I)
            values = {_number(value) for value in matches}
            if len(values) == 1:
                nutrients[code] = next(iter(values))
        energy_id, basis, label = None, "per_serving", serving.group(1).strip()
    if not any(value is not None for value in nutrients.values()):
        return None
    title = re.search(r"(?m)^#\s+(.+)", content)
    name = title.group(1).strip() if title else ""
    name = re.sub(r"^(?:USDA食物成分|USDA FNS 家庭菜谱)\s*[｜|]\s*", "", name)
    name = re.sub(r"\s*[｜|]\s*FDC\s*\d+.*$", "", name)
    return {
        "name": name[:120],
        "basis": basis,
        "basis_label": label,
        "nutrients": {code: str(value) if value is not None else None for code, value in nutrients.items()},
        "energy_method": energy_id,
        "parser_version": PARSER_VERSION,
        "professional_approval": False,
    }


def _number(value: str) -> Decimal | None:
    """缺失、界限与非法数值保持未知。"""
    if re.fullmatch(r"\d+(?:\.\d+)?", value) is None:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    return number if number.is_finite() and 0 <= number <= 100000 else None

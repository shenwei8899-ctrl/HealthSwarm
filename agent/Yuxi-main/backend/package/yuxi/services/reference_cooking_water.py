"""只识别明确的纯烹饪用水，不豁免调味料、汤底或复合食材。"""

import re


def cooking_water(text):
    """允许原食谱中的水量和等值单位括注，其余成分必须另行采购。"""
    number = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?[¼½¾⅓⅔⅛⅜⅝⅞]?|[¼½¾⅓⅔⅛⅜⅝⅞])"
    unit = r"(?:cups?|ml|millilit(?:er|re)s?|l|lit(?:er|re)s?|g|grams?|tablespoons?|teaspoons?)"
    amount = rf"{number}\s*{unit}"
    english = (
        rf"(?:{amount}\s*(?:\(\s*{amount}\s*\)\s*)?)?"
        r"(?:(?:cold|hot|warm|boiling|drinking)\s+)?water(?:,?\s+as needed)?"
    )
    chinese = (
        r"(?:水|清水|饮用水|温水|开水|凉开水|冷开水)\s*"
        rf"(?:适量|少许|{number}\s*(?:毫升|升|ml|l|克|g|杯))?"
    )
    return isinstance(text, str) and bool(re.fullmatch(rf"\s*(?:{chinese}|{english})\s*", text, re.I))

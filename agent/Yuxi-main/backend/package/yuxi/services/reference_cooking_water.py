"""只识别明确的纯烹饪用水，不豁免调味料、汤底或复合食材。"""

import re


def cooking_water(text):
    """允许原食谱中的水量和等值单位括注，其余成分必须另行采购。"""
    fraction = r"[¼½¾⅓⅔⅛⅜⅝⅞]"
    single = rf"(?:\d+\s+(?:\d+/\d+|{fraction})|\d+/\d+|\d+(?:\.\d+)?{fraction}?|{fraction})"
    number = rf"{single}(?:\s*-\s*{single})?"
    unit = r"(?:c|cups?|ml|millilit(?:er|re)s?|l|lit(?:er|re)s?|g|grams?|tablespoons?|teaspoons?)"
    amount = rf"{number}\s*-?\s*{unit}"
    quantity = rf"(?:{amount}|{number}|{unit})"
    chinese_unit = r"(?:毫升|升|ml|l|克|g|杯|碗)"
    english = (
        rf"(?:{quantity}\s*(?:\(\s*{amount}\s*\)\s*)?)?"
        r"(?:(?:cold|hot|warm|boiling|drinking)\s+)?water(?:,?\s+as needed|适量)?"
    )
    chinese = (
        rf"(?:{number}\s*{chinese_unit}\s*)?"
        r"(?:水|(?:清|饮用|温|热|凉|冷|沸|开|凉开|冷开)\s*水)\s*"
        rf"(?:适量|少许|{number}\s*{chinese_unit})?"
    )
    water_first = rf"water\s*[,，]\s*{amount}"
    return isinstance(text, str) and bool(re.fullmatch(rf"\s*(?:{chinese}|{english}|{water_first})\s*", text, re.I))

"""菜谱目录的标题相关性排序。"""

from sqlalchemy import case, func, literal


def reference_title_match_score(filename, terms):
    """优先保留命中更多查询词的标题，避免字母排序挤掉精确菜名。"""
    return sum(
        (case((func.lower(filename).contains(term.casefold(), autoescape=True), 1), else_=0) for term in terms),
        literal(0),
    )

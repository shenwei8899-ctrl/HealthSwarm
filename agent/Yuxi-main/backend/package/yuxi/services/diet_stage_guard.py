"""旧客户端不能绕过阶段目标的唯一编辑入口。"""

from fastapi import HTTPException


def require_stage_goal_entry(original, merged):
    """比较实际变更，其他档案修改不受影响。"""
    if not original.get("diet_stage_managed"):
        return
    for field in ("goal", "health_goals"):
        if merged.get(field) != original.get(field):
            raise HTTPException(409, "请在我的家「饮食目标与行动」中调整阶段目标")
    if merged.get("dietary_details", {}).get("goals") != original.get("dietary_details", {}).get("goals"):
        raise HTTPException(409, "请在我的家「饮食目标与行动」中调整阶段目标")

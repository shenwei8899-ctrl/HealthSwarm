"""归档展示的白名单和局部替换语义。"""

from types import SimpleNamespace

from yuxi.services.meal_archive_projection import archive_meal, merge_archive


def test_archive_removes_private_health_data_and_action_proofs():
    """共享展示不复制健康字段、成员分析和采购凭据。"""
    meal = {
        "type": "dinner",
        "members": [{"id": "member", "name": "合成人物", "allergens": ["private"]}],
        "memberNotes": [{"medical_history": "private"}],
        "purchase": {"proof": "private"},
        "dishes": [
            {
                "name": "青菜",
                "ingredients": ["青菜100克"],
                "steps": ["煮熟"],
                "origin": {"token": "private"},
                "source": {"profile": "private"},
            }
        ],
    }
    saved = archive_meal(meal)
    assert saved == {
        "meal_type": "dinner",
        "members": [{"id": "member", "name": "合成人物"}],
        "dishes": [{"name": "青菜", "ingredients": ["青菜100克"], "steps": ["煮熟"]}],
    }
    meal["dishes"][0]["steps"].append("修改")
    assert saved["dishes"][0]["steps"] == ["煮熟"]


def test_partial_archive_replacement_keeps_other_meals():
    """仅晚餐成功时早餐和午餐保持原样。"""
    row = SimpleNamespace(archive_meals={"breakfast": {"dishes": ["旧早餐"]}, "lunch": {"dishes": ["旧午餐"]}})
    merge_archive(row, [{"meal_type": "dinner", "dishes": [{"name": "新晚餐"}]}])
    assert row.archive_meals["breakfast"] == {"dishes": ["旧早餐"]}
    assert row.archive_meals["lunch"] == {"dishes": ["旧午餐"]}
    assert row.archive_meals["dinner"]["dishes"] == [{"name": "新晚餐"}]


def test_archive_uses_source_members_when_meal_has_no_members():
    """餐次成员由每日来源携带时仍保存共餐姓名。"""
    row = SimpleNamespace(archive_meals={})
    merge_archive(row, [{"type": "lunch", "dishes": [{"name": "菜"}]}], [{"id": "one", "name": "家人"}])
    assert row.archive_meals["lunch"]["members"] == [{"id": "one", "name": "家人"}]

from yuxi.services.health_dish_suggestions import split_dish_suggestions, stored_dish_suggestions


def test_dish_suggestions_survive_final_message_metadata():
    """正文和建议可分别投影到即时回复与历史。"""
    text, cards = split_dish_suggestions(
        '可选番茄豆腐，做法简单。\n<dish_suggestions>[{"name":"番茄豆腐","reason":"做法简单"}]</dish_suggestions>'
    )
    assert text == "可选番茄豆腐，做法简单。"
    assert cards == [{"name": "番茄豆腐", "reason": "做法简单"}]
    assert stored_dish_suggestions({"additional_kwargs": {"dish_suggestions": cards}}) == cards


def test_invalid_suggestion_retains_text_without_cards():
    """可选卡片格式错误时保留正文。"""
    assert split_dish_suggestions("先说明原则。\n<dish_suggestions>[{}]</dish_suggestions>") == ("先说明原则。", [])
    assert split_dish_suggestions("只解释原则。") == ("只解释原则。", [])
